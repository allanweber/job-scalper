"""`collect` command core: search every configured source into the local store."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from scalper.commands import CommandError
from scalper.config import Config
from scalper.sources import build_adapter
from scalper.store import JobStore


class NoSourcesError(CommandError):
    """No usable sources to collect from (none configured, or none matched a filter)."""


@dataclass
class SourceOutcome:
    """What one source contributed in a collect run."""

    name: str
    fetched: int
    fresh: int
    new: int
    updated: int


@dataclass
class CollectResult:
    db: str
    total_new: int
    total_updated: int
    total_stored: int
    outcomes: list[SourceOutcome] = field(default_factory=list)


def _noop(_msg: str) -> None:
    pass


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _freshness_cutoff(config: Config) -> datetime | None:
    """Oldest publish date worth storing (from the global freshness_days setting).

    Returns None when freshness_days is unset (no pre-filter applied).
    Postings with no published_at are always kept (unknown date → err on inclusion).
    """
    if config.freshness_days is None:
        return None
    return datetime.now(timezone.utc) - timedelta(days=config.freshness_days)


def run_collect(
    config: Config,
    *,
    db: str | None = None,
    only_sources: list[str] | None = None,
    on_info: Callable[[str], None] = _noop,
    on_warning: Callable[[str], None] = _noop,
    on_source_log: Callable[[str], None] | None = None,
) -> CollectResult:
    """Fetch from each configured source and upsert into the store.

    Postings whose ``published_at`` falls outside every profile's freshness window
    are dropped before storage so they never consume the per-source limit. Postings
    with no publish date are kept (unknown date → include). Per-source progress is
    streamed through ``on_info``; recoverable problems go to ``on_warning`` and the
    run continues. When ``on_source_log`` is provided (or ``config.verbose_sources``
    is true), every HTTP request/response made by adapters is logged through it.
    Raises :class:`NoSourcesError` when there is nothing to collect.
    """
    db = db or config.database
    query = config.search
    if query.terms:
        on_info(f"Searching for: {', '.join(query.terms)}")

    sources = config.sources
    if not sources:
        raise NoSourcesError("no sources configured. Add some under `sources:` in your config.")
    if only_sources:
        wanted = {s.lower() for s in only_sources}
        sources = [sc for sc in sources if sc.type.lower() in wanted]
        missing = wanted - {sc.type.lower() for sc in config.sources}
        for name in sorted(missing):
            on_warning(f"source {name!r} not found in config; skipping.")
        if not sources:
            raise NoSourcesError("no matching sources to collect from.")
        on_info(f"Collecting from: {', '.join(sc.type for sc in sources)}")

    cutoff = _freshness_cutoff(config)
    source_logger = on_source_log or (on_info if config.verbose_sources else None)

    total_new = total_updated = 0
    outcomes: list[SourceOutcome] = []
    with JobStore(db) as store:
        for sc in sources:
            try:
                adapter = build_adapter(sc.type, sc.params, logger=source_logger)
            except (KeyError, ValueError, TypeError) as e:
                on_warning(f"skipping source {sc.type} {sc.params}: {e}")
                continue
            src_query = query
            if sc.limit is not None:
                src_query = query.model_copy(update={"limit_per_source": sc.limit})
            try:
                postings = adapter.fetch(src_query)
            except Exception as e:  # noqa: BLE001 — one bad source must not abort the run
                on_warning(f"{adapter.name}: fetch failed: {e}")
                continue

            fetched = len(postings)
            if cutoff is not None:
                postings = [
                    p for p in postings
                    if p.published_at is None or _aware(p.published_at) >= cutoff
                ]

            new, updated = store.upsert_many(postings)
            total_new += new
            total_updated += updated
            stale = fetched - len(postings)
            stale_note = f", {stale} stale skipped" if stale else ""
            outcomes.append(SourceOutcome(adapter.name, fetched, len(postings), new, updated))
            on_info(f"  {adapter.name}: {fetched} fetched, {len(postings)} fresh"
                    f" ({new} new, {updated} updated{stale_note})")
        total_stored = store.count()

    return CollectResult(str(db), total_new, total_updated, total_stored, outcomes)
