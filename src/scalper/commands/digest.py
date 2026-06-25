"""`digest` command core: collect, then report only the Fresh Catch (ADR 0005).

One verb that runs the normal collect path and renders only the postings whose
preserved first-seen `collected_at` falls at or after this run's `run_start` —
the Fresh Catch (see the term in CONTEXT.md). A posting already in the store
that merely re-appears this run is not a Fresh Catch.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone

from scalper.commands import CommandError
from scalper.commands.collect import run_collect
from scalper.config import Config
from scalper.report import ReportPanel, render_combined_report, render_report
from scalper.scoring import ScoredPosting, score_all
from scalper.semantic import DEFAULT_MODEL, build_semantic_scorer, sentence_transformers_available
from scalper.store import JobStore


class ProfileNotFoundError(CommandError):
    """The requested profile is not defined in the config."""


class NoProfilesError(CommandError):
    """`--all-profiles` was requested but the config defines no profiles."""


def _noop(_msg: str) -> None:
    pass


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


@dataclass
class ProfileDigest:
    """One profile's Fresh Catch slice."""

    profile_name: str
    scored: list[ScoredPosting] = field(default_factory=list)
    new: int = 0


@dataclass
class DigestResult:
    html: str
    run_start: datetime
    #: Size of the Fresh Catch universe this run (before per-profile filtering).
    total_new: int = 0
    profiles: list[ProfileDigest] = field(default_factory=list)


def run_digest(
    config: Config,
    profile_names: list[str],
    *,
    db: str | None = None,
    only_sources: list[str] | None = None,
    semantic: bool = True,
    model: str = DEFAULT_MODEL,
    on_info: Callable[[str], None] = _noop,
    on_warning: Callable[[str], None] = _noop,
    on_source_log: Callable[[str], None] | None = None,
) -> DigestResult:
    """Collect, then score+render only postings first seen during this run.

    Captures `run_start` before collecting; a posting counts as Fresh Catch only
    when its first-seen `collected_at` (preserved across re-collection by the
    store's upsert) is at or after `run_start`. Raises :class:`NoProfilesError`
    or :class:`ProfileNotFoundError` instead of exiting; collect-time problems
    stream through `on_info`/`on_warning` exactly as `collect` does.
    """
    if not profile_names:
        raise NoProfilesError("no profiles defined in config; add one under `profiles:`.")
    try:
        profiles = [(name, config.profile(name)) for name in profile_names]
    except KeyError as e:
        raise ProfileNotFoundError(str(e)) from None

    db = config.database_path(db)
    run_start = datetime.now(timezone.utc)
    run_collect(config, db=db, only_sources=only_sources, on_info=on_info, on_warning=on_warning,
                on_source_log=on_source_log)

    with JobStore(db) as store:
        postings = [
            p for p in store.iter_postings()
            if p.collected_at is not None and _aware(p.collected_at) >= run_start
        ]

        scorer = build_semantic_scorer(store, model_name=model, enabled=semantic)
        if scorer is not None:
            try:
                scorer.prepare(postings)
            except Exception as e:  # noqa: BLE001 — semantic is optional; never abort digest
                on_warning(f"semantic scoring unavailable ({e}); using deterministic scores.")
                scorer = None
        elif semantic and not sentence_transformers_available():
            on_info("note: semantic scoring off — install it with: pip install -e '.[semantic]'")

        results: list[ProfileDigest] = []
        panels: list[ReportPanel] = []
        for name, profile in profiles:
            scored = score_all(profile, postings, semantic_scorer=scorer,
                               freshness_days=config.freshness_days)
            results.append(ProfileDigest(profile_name=name, scored=scored, new=len(scored)))
            panels.append(ReportPanel(name, profile, scored, {}))
        drafted_uids = store.get_drafted_uids()

    if len(profiles) == 1:
        name, profile = profiles[0]
        html = render_report(name, profile, results[0].scored, {},
                             freshness_days=config.freshness_days, drafted_uids=drafted_uids)
    else:
        html = render_combined_report(panels, freshness_days=config.freshness_days,
                                      drafted_uids=drafted_uids)

    return DigestResult(
        html=html, run_start=run_start, total_new=len(postings), profiles=results,
    )
