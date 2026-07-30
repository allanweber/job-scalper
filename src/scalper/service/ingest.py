"""Scheduled/admin scrape: fill the shared pool (ADR 0011).

Scraping is **never user-triggered**. A run fetches every admin-**enabled** source
(`sources.enabled`) using the **union of active users' profile terms** (active =
seen within `scrape.active_user_window_days`) and ingests results into the pool,
deduped at storage time. The scheduler enqueues it on `scrape.interval_minutes`;
the admin portal can trigger a run or change the interval live.

Sources are built via an injectable `adapter_builder` (defaults to the real
registry) so tests drive ingestion with a fake adapter and no network.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from scalper.models import JobPosting, SearchQuery
from scalper.service.content_repos import ActiveUsersRepo, PostingRepo
from scalper.service.models import now_iso
from scalper.service.settings import Settings
from scalper.sources import build_adapter

Logger = Callable[[str], None]

#: Last-resort scope if neither active users nor `scrape.default_terms` yield any.
_FALLBACK_TERMS = ["software engineer", "developer"]


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


class Ingestor:
    def __init__(self, conn: Any, settings: Settings, *,
                 adapter_builder: Callable[..., Any] = build_adapter,
                 logger: Logger | None = None):
        self._conn = conn
        self._settings = settings
        self._build = adapter_builder
        self._log = logger or (lambda _m: None)

    def scope_terms(self) -> list[str]:
        """Scrape scope: the union of active users' profile terms, or — when there
        are none yet — the admin-configured `scrape.default_terms` (see ADR 0011)."""
        window = int(self._settings.get("scrape.active_user_window_days", 30) or 30)
        terms = ActiveUsersRepo(self._conn).profile_terms(window)
        if terms:
            return terms
        default = self._settings.get("scrape.default_terms") or []
        return [t for t in default if str(t).strip()] or list(_FALLBACK_TERMS)

    def _freshness_cutoff(self) -> datetime | None:
        raw = self._settings.get("scrape.freshness_days")
        if raw is None:
            return None
        try:
            days = int(raw)
        except (TypeError, ValueError):
            return None
        return datetime.now(timezone.utc) - timedelta(days=days)

    def enabled_sources(self) -> list[str]:
        return list(self._settings.get("sources.enabled", []) or [])

    def run(self, *, sources: list[str] | None = None,
            terms: list[str] | None = None, limit_per_source: int = 100) -> dict[str, Any]:
        """Fetch enabled sources for the scope terms and ingest into the pool.

        Per-source failures are isolated (logged, counted) so one flaky board
        never aborts the whole run. Returns aggregate + per-source stats.
        """
        sources = sources if sources is not None else self.enabled_sources()
        terms = terms if terms is not None else self.scope_terms()
        query = SearchQuery(terms=terms, remote=True, limit_per_source=limit_per_source)

        repo = PostingRepo(self._conn)
        collected: list[JobPosting] = []
        per_source: dict[str, Any] = {}
        errors: dict[str, str] = {}
        for stype in sources:
            try:
                adapter = self._build(stype, {})
                found = adapter.fetch(query)
                collected.extend(found)
                per_source[stype] = len(found)
                self._log(f"scrape {stype}: {len(found)} postings")
            except Exception as e:  # noqa: BLE001 — isolate per-source failures
                errors[stype] = str(e)
                self._log(f"scrape {stype} FAILED: {e}")

        # Drop stale postings before ingest if a freshness window is configured
        # (postings without a published date are always kept).
        cutoff = self._freshness_cutoff()
        dropped_stale = 0
        if cutoff is not None:
            kept = [p for p in collected
                    if p.published_at is None or _aware(p.published_at) >= cutoff]
            dropped_stale = len(collected) - len(kept)
            collected = kept

        stats = repo.ingest(collected)
        self._settings.set("scrape.last_run_at", now_iso())
        return {
            "fetched": len(collected),
            "dropped_stale": dropped_stale,
            "ingested": stats,
            "per_source": per_source,
            "errors": errors,
            "terms": terms,
            "sources": sources,
        }

    def purge(self) -> dict[str, Any]:
        """Retention: trim pool postings older than `retention.days`."""
        # None-aware: retention.days=0 is a legitimate "purge everything", so it
        # must not be treated as missing (a falsy `or` default would hide it).
        raw = self._settings.get("retention.days", 30)
        days = 30 if raw is None else int(raw)
        deleted = PostingRepo(self._conn).purge_older_than(days)
        return {"deleted": deleted, "retention_days": days}
