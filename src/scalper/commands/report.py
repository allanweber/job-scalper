"""`report` command core: score stored postings against a profile, render HTML.

Returns the rendered HTML as a string rather than writing a file or opening a
browser — those are CLI concerns. A future app can serve ``result.html`` directly.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from scalper.commands import CommandError
from scalper.config import Config, Profile
from scalper.enrich import build_enricher, format_usage
from scalper.report import ReportPanel, render_combined_report, render_report
from scalper.scoring import ScoredPosting, dedup_scored, score_all
from scalper.semantic import DEFAULT_MODEL, build_semantic_scorer, sentence_transformers_available
from scalper.store import JobStore


class ProfileNotFoundError(CommandError):
    """The requested profile is not defined in the config."""


class StoreNotFoundError(CommandError):
    """No store exists yet — `collect` has not been run."""


class NoProfilesError(CommandError):
    """`--all-profiles` was requested but the config defines no profiles."""


@dataclass
class ReportResult:
    profile_name: str
    html: str
    scored: list[ScoredPosting] = field(default_factory=list)
    #: Stored postings considered (after the optional `since` filter).
    total_considered: int = 0
    #: Postings that matched the profile and survived the optional limit.
    matched: int = 0
    enriched_count: int = 0


@dataclass
class ProfileReport:
    """One profile's outcome within a Combined Report (one tab)."""

    profile_name: str
    scored: list[ScoredPosting] = field(default_factory=list)
    #: Postings that matched the profile and survived the optional limit.
    matched: int = 0
    enriched_count: int = 0


@dataclass
class MultiReportResult:
    html: str
    profiles: list[ProfileReport] = field(default_factory=list)
    #: Stored postings considered (after the optional `since` filter); shared
    #: across every profile in the run.
    total_considered: int = 0
    #: Aggregate enriched count across all profiles.
    enriched_count: int = 0


def _noop(_msg: str) -> None:
    pass


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _prepare(
    store: JobStore,
    *,
    since: datetime | None,
    semantic: bool,
    model: str,
    on_info: Callable[[str], None],
    on_warning: Callable[[str], None],
):
    """Load postings (applying the shared ``since`` pre-filter) and build the
    semantic scorer once. The scorer is reusable across every profile in the run.
    """
    postings = list(store.iter_postings())
    if since is not None:
        # Keep postings with no known date (consistent with the freshness
        # filter); drop those published before the cutoff.
        postings = [
            p for p in postings
            if p.published_at is None or _aware(p.published_at) >= since
        ]

    scorer = build_semantic_scorer(store, model_name=model, enabled=semantic)
    if scorer is not None:
        try:
            scorer.prepare(postings)
        except Exception as e:  # noqa: BLE001 — semantic is optional; never abort report
            on_warning(f"semantic scoring unavailable ({e}); using deterministic scores.")
            scorer = None
    elif semantic and not sentence_transformers_available():
        on_info("note: semantic scoring off — install it with: pip install -e '.[semantic]'")
    return postings, scorer


def _make_enricher(
    config: Config,
    store: JobStore,
    *,
    enrich: bool,
    enrich_model: str | None,
    on_info: Callable[[str], None],
    on_enrich_log: Callable[[str], None] | None,
):
    """Build the (optional) shared enricher, or ``None`` when disabled/unavailable.

    Built once per run so its usage tally accumulates across every profile.
    """
    if not (enrich or config.llm.enabled):
        return None
    enricher = build_enricher(
        config.llm, store,
        model=enrich_model or config.llm.enrich_model,
        logger=on_enrich_log,
    )
    if enricher is None:
        on_info("note: enrichment off — install it with: pip install -e '.[llm]' "
                "and set ANTHROPIC_API_KEY")
    return enricher


def _score_one(
    profile: Profile,
    postings: list,
    scorer,
    enricher,
    *,
    freshness_days: int | None,
    dedup: bool,
    top_n: int,
    limit: int | None,
    on_info: Callable[[str], None],
    on_warning: Callable[[str], None],
) -> tuple[list[ScoredPosting], dict, bool]:
    """Score, optionally dedup, optionally enrich one profile. Returns
    ``(scored, enrichments, enrich_ran)``; enrichment is applied to the full
    sorted list before the ``limit`` truncation, matching single-profile order.
    """
    scored = score_all(profile, postings, semantic_scorer=scorer, freshness_days=freshness_days)
    if dedup:
        before = len(scored)
        scored = dedup_scored(scored)
        collapsed = before - len(scored)
        if collapsed:
            on_info(f"Deduped {collapsed} cross-source duplicate(s).")

    enrichments: dict = {}
    enrich_ran = False
    if enricher is not None:
        try:
            enrichments = enricher.enrich(profile, scored, top_n)
            enrich_ran = True
        except Exception as e:  # noqa: BLE001 — enrichment is optional; never abort report
            on_warning(f"enrichment failed ({e}); rendering deterministic report.")

    if limit:
        scored = scored[:limit]
    return scored, enrichments, enrich_ran


def run_report(
    config: Config,
    profile_name: str,
    *,
    db: str | None = None,
    limit: int | None = None,
    since: datetime | None = None,
    dedup: bool = False,
    semantic: bool = True,
    model: str = DEFAULT_MODEL,
    enrich: bool = False,
    top: int | None = None,
    enrich_model: str | None = None,
    on_info: Callable[[str], None] = _noop,
    on_warning: Callable[[str], None] = _noop,
    on_enrich_log: Callable[[str], None] | None = None,
) -> ReportResult:
    """Score the stored postings against ``profile_name`` and render the report HTML.

    ``since`` is an already-parsed aware cutoff (the CLI parses ``--since`` text).
    Optional, fail-soft semantic scoring and LLM enrichment stream notes through
    ``on_info``/``on_warning``; per-request enrichment logs go through
    ``on_enrich_log`` (``None`` to silence them). Raises :class:`ProfileNotFoundError`
    or :class:`StoreNotFoundError` instead of exiting.
    """
    db = db or config.database
    try:
        profile: Profile = config.profile(profile_name)
    except KeyError as e:
        # config.profile raises KeyError with a friendly message; preserve it
        # verbatim (str(KeyError) keeps the surrounding quotes, as before).
        raise ProfileNotFoundError(str(e)) from None

    if not Path(db).exists():
        raise StoreNotFoundError(f"no store at {db}. Run `scalper collect` first.")

    top_n = top if top is not None else config.llm.top_n
    with JobStore(db) as store:
        postings, scorer = _prepare(
            store, since=since, semantic=semantic, model=model,
            on_info=on_info, on_warning=on_warning,
        )
        enricher = _make_enricher(
            config, store, enrich=enrich, enrich_model=enrich_model,
            on_info=on_info, on_enrich_log=on_enrich_log,
        )
        scored, enrichments, enrich_ran = _score_one(
            profile, postings, scorer, enricher,
            freshness_days=config.freshness_days,
            dedup=dedup, top_n=top_n, limit=limit,
            on_info=on_info, on_warning=on_warning,
        )
        if enrich_ran:
            on_info(format_usage(enricher.usage, config.llm))

    html = render_report(profile_name, profile, scored, enrichments,
                         freshness_days=config.freshness_days)
    return ReportResult(
        profile_name=profile_name,
        html=html,
        scored=scored,
        total_considered=len(postings),
        matched=len(scored),
        enriched_count=len(enrichments),
    )


def run_report_all(
    config: Config,
    profile_names: list[str],
    *,
    db: str | None = None,
    limit: int | None = None,
    since: datetime | None = None,
    dedup: bool = False,
    semantic: bool = True,
    model: str = DEFAULT_MODEL,
    enrich: bool = False,
    top: int | None = None,
    enrich_model: str | None = None,
    on_info: Callable[[str], None] = _noop,
    on_warning: Callable[[str], None] = _noop,
    on_enrich_log: Callable[[str], None] | None = None,
) -> MultiReportResult:
    """Score the stored postings against every named profile and render one
    Combined Report (a tab per profile).

    The store is opened once and the semantic model loaded once for the whole
    run; a single enricher is shared so its usage/cost tally aggregates across
    profiles. ``since`` is the run-level pre-filter; each profile still applies
    its own hard filters (including its own freshness window) via ``score_all``.
    Raises :class:`NoProfilesError`, :class:`ProfileNotFoundError`, or
    :class:`StoreNotFoundError` instead of exiting.
    """
    db = db or config.database
    if not profile_names:
        raise NoProfilesError("no profiles defined in config; add one under `profiles:`.")
    try:
        profiles = [(name, config.profile(name)) for name in profile_names]
    except KeyError as e:
        raise ProfileNotFoundError(str(e)) from None

    if not Path(db).exists():
        raise StoreNotFoundError(f"no store at {db}. Run `scalper collect` first.")

    top_n = top if top is not None else config.llm.top_n
    reports: list[ProfileReport] = []
    panels: list[ReportPanel] = []
    enricher = None
    any_enrich = False
    with JobStore(db) as store:
        postings, scorer = _prepare(
            store, since=since, semantic=semantic, model=model,
            on_info=on_info, on_warning=on_warning,
        )
        enricher = _make_enricher(
            config, store, enrich=enrich, enrich_model=enrich_model,
            on_info=on_info, on_enrich_log=on_enrich_log,
        )
        for name, profile in profiles:
            scored, enrichments, enrich_ran = _score_one(
                profile, postings, scorer, enricher,
                freshness_days=config.freshness_days,
                dedup=dedup, top_n=top_n, limit=limit,
                on_info=on_info, on_warning=on_warning,
            )
            any_enrich = any_enrich or enrich_ran
            reports.append(ProfileReport(
                profile_name=name, scored=scored, matched=len(scored),
                enriched_count=len(enrichments),
            ))
            panels.append(ReportPanel(name, profile, scored, enrichments))
        if any_enrich:
            on_info(format_usage(enricher.usage, config.llm))

    html = render_combined_report(panels, freshness_days=config.freshness_days)
    return MultiReportResult(
        html=html,
        profiles=reports,
        total_considered=len(postings),
        enriched_count=sum(r.enriched_count for r in reports),
    )
