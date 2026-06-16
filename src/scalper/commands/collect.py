"""`collect` command core: search every configured source into the local store."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

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


def run_collect(
    config: Config,
    *,
    db: str | None = None,
    only_sources: list[str] | None = None,
    on_info: Callable[[str], None] = _noop,
    on_warning: Callable[[str], None] = _noop,
) -> CollectResult:
    """Fetch from each configured source and upsert into the store.

    Per-source progress is streamed through ``on_info``; recoverable problems
    (unknown source, bad adapter, failed fetch) go to ``on_warning`` and the run
    continues. Raises :class:`NoSourcesError` when there is nothing to collect.
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

    total_new = total_updated = 0
    outcomes: list[SourceOutcome] = []
    with JobStore(db) as store:
        for sc in sources:
            try:
                adapter = build_adapter(sc.type, sc.params)
            except (KeyError, ValueError, TypeError) as e:
                on_warning(f"skipping source {sc.type} {sc.params}: {e}")
                continue
            # Apply a per-source cap if configured (keeps high-volume sources
            # like hackernews from dominating the store).
            src_query = query
            if sc.limit is not None:
                src_query = query.model_copy(update={"limit_per_source": sc.limit})
            try:
                postings = adapter.fetch(src_query)
            except Exception as e:  # noqa: BLE001 — one bad source must not abort the run
                on_warning(f"{adapter.name}: fetch failed: {e}")
                continue
            new, updated = store.upsert_many(postings)
            total_new += new
            total_updated += updated
            outcomes.append(SourceOutcome(adapter.name, len(postings), new, updated))
            on_info(f"  {adapter.name}: {len(postings)} fetched ({new} new, {updated} updated)")
        total_stored = store.count()

    return CollectResult(str(db), total_new, total_updated, total_stored, outcomes)
