"""`sources` command core: registered adapters + configured sources with counts."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from scalper.config import Config
from scalper.sources import REGISTRY
from scalper.sources.base import TIER_STRUCTURED
from scalper.store import JobStore


@dataclass
class SourceRow:
    type: str
    tier: str
    stored: int


@dataclass
class SourcesResult:
    db: str
    configured: list[SourceRow] = field(default_factory=list)
    #: Adapters registered but absent from the config.
    registered_unconfigured: list[str] = field(default_factory=list)
    #: Sources with stored postings but no longer in the config.
    orphaned: list[SourceRow] = field(default_factory=list)
    total_stored: int = 0
    source_count: int = 0


def run_sources(config: Config, *, db: str | None = None) -> SourcesResult:
    """Cross-reference the adapter registry, the config, and the stored counts."""
    db = config.database_path(db)

    counts: dict[str, int] = {}
    if Path(db).exists():
        with JobStore(db) as store:
            counts = store.counts_by_source()

    configured_types = [sc.type for sc in config.sources]
    configured = []
    for stype in configured_types:
        cls = REGISTRY.get(stype)
        tier = getattr(cls, "tier", TIER_STRUCTURED) if cls else "unregistered"
        configured.append(SourceRow(stype, tier, counts.get(stype, 0)))

    extra = sorted(set(REGISTRY) - set(configured_types))
    orphan_types = sorted(set(counts) - set(configured_types))
    orphaned = [SourceRow(stype, "", counts[stype]) for stype in orphan_types]

    return SourcesResult(
        db=str(db),
        configured=configured,
        registered_unconfigured=extra,
        orphaned=orphaned,
        total_stored=sum(counts.values()),
        source_count=len(counts),
    )
