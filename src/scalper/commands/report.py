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
from scalper.report import render_report
from scalper.scoring import ScoredPosting, dedup_scored, score_all
from scalper.semantic import DEFAULT_MODEL, build_semantic_scorer, sentence_transformers_available
from scalper.store import JobStore


class ProfileNotFoundError(CommandError):
    """The requested profile is not defined in the config."""


class StoreNotFoundError(CommandError):
    """No store exists yet — `collect` has not been run."""


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


def _noop(_msg: str) -> None:
    pass


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


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

    with JobStore(db) as store:
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

        scored = score_all(profile, postings, semantic_scorer=scorer)
        if dedup:
            before = len(scored)
            scored = dedup_scored(scored)
            collapsed = before - len(scored)
            if collapsed:
                on_info(f"Deduped {collapsed} cross-source duplicate(s).")

        enrichments: dict = {}
        if enrich or config.llm.enabled:
            top_n = top if top is not None else config.llm.top_n
            enricher = build_enricher(
                config.llm, store,
                model=enrich_model or config.llm.enrich_model,
                logger=on_enrich_log,
            )
            if enricher is None:
                on_info("note: enrichment off — install it with: pip install -e '.[llm]' "
                        "and set ANTHROPIC_API_KEY")
            else:
                try:
                    enrichments = enricher.enrich(profile, scored, top_n)
                    on_info(format_usage(enricher.usage, config.llm))
                except Exception as e:  # noqa: BLE001 — enrichment is optional; never abort report
                    on_warning(f"enrichment failed ({e}); rendering deterministic report.")

    considered = len(postings)
    if limit:
        scored = scored[:limit]

    html = render_report(profile_name, profile, scored, enrichments)
    return ReportResult(
        profile_name=profile_name,
        html=html,
        scored=scored,
        total_considered=considered,
        matched=len(scored),
        enriched_count=len(enrichments),
    )
