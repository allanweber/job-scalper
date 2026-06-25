"""Render scored postings into a single self-contained HTML report."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from jinja2 import Environment, PackageLoader, select_autoescape

import scalper.sources  # noqa: F401 — import side-effect populates the adapter REGISTRY
from scalper.config import Profile
from scalper.enrich import Enrichment
from scalper.scoring import ScoredPosting
from scalper.sources._util import extract_timezone
from scalper.sources.base import REGISTRY, TIER_HARD, TIER_STRUCTURED

_env = Environment(
    loader=PackageLoader("scalper", "templates"),
    autoescape=select_autoescape(["html"]),
)


def _tier(source: str) -> str:
    """The acquisition tier of a posting's source (defaults to structured)."""
    cls = REGISTRY.get(source)
    return getattr(cls, "tier", TIER_STRUCTURED) if cls is not None else TIER_STRUCTURED


def _excerpt(text: str, limit: int = 320) -> str:
    text = text.strip()
    return text if len(text) <= limit else text[:limit].rsplit(" ", 1)[0] + "…"


def _row(
    scored: ScoredPosting,
    enrichment: Enrichment | None = None,
    *,
    drafted: bool = False,
) -> dict:
    p = scored.posting
    return {
        "enrichment": enrichment.model_dump() if enrichment else None,
        "uid": p.uid,
        "percent": scored.percent,
        "title": p.title,
        "company": p.company,
        "location": p.location or ("Remote" if p.remote else "—"),
        "remote": p.remote,
        # Fall back to a timezone parsed from the location when the source
        # didn't supply one — reporting-only, so it works on existing stores.
        "timezone": p.timezone or extract_timezone(p.location) or "",
        "salary": p.salary_display or "",
        "source": p.source,
        "also_seen_on": scored.also_seen_on,
        "tier": _tier(p.source),
        "hard": _tier(p.source) == TIER_HARD,
        "url": p.url,
        "published": p.published_at.date().isoformat() if p.published_at else "",
        "matched_skills": scored.matched_skills,
        "missing_skills": scored.missing_skills,
        "matched_nice_to_have": scored.matched_nice_to_have,
        "matched_keywords": scored.matched_keywords,
        "breakdown": {k: round(v * 100) for k, v in scored.breakdown.components().items()},
        "excerpt": _excerpt(p.description),
        "drafted": drafted,
    }


@dataclass
class ReportPanel:
    """One profile's slice of a Combined Report (one tab in the rendered HTML)."""

    profile_name: str
    profile: Profile
    scored: list[ScoredPosting]
    enrichments: dict[str, Enrichment] = field(default_factory=dict)


def _rows_for(
    scored: list[ScoredPosting],
    enrichments: dict[str, Enrichment],
    drafted_uids: set[str] | None = None,
) -> list[dict]:
    drafted_uids = drafted_uids or set()
    return [_row(s, enrichments.get(s.posting.uid), drafted=s.posting.uid in drafted_uids) for s in scored]


def _panel_context(panel: ReportPanel, *, show_head: bool, drafted_uids: set[str] | None = None) -> dict:
    rows = _rows_for(panel.scored, panel.enrichments, drafted_uids)
    return {
        "profile_name": panel.profile_name,
        "profile": panel.profile,
        "rows": rows,
        "total": len(panel.scored),
        "show_head": show_head,
    }


def _now_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def render_report(
    profile_name: str,
    profile: Profile,
    scored: list[ScoredPosting],
    enrichments: dict[str, Enrichment] | None = None,
    *,
    freshness_days: int | None = None,
    drafted_uids: set[str] | None = None,
) -> str:
    enrichments = enrichments or {}
    panel = _panel_context(
        ReportPanel(profile_name, profile, scored, enrichments), show_head=False,
        drafted_uids=drafted_uids,
    )
    template = _env.get_template("report.html")
    return template.render(
        profile_name=profile_name,
        profile=profile,
        panel=panel,
        total=panel["total"],
        enriched=bool(enrichments),
        has_hard=any(r["hard"] for r in panel["rows"]),
        generated_at=_now_str(),
        freshness_days=freshness_days,
    )


def render_combined_report(
    panels: list[ReportPanel],
    *,
    freshness_days: int | None = None,
    drafted_uids: set[str] | None = None,
) -> str:
    """Render several profiles into one tabbed, self-contained Combined Report."""
    contexts = [_panel_context(p, show_head=True, drafted_uids=drafted_uids) for p in panels]
    template = _env.get_template("report_combined.html")
    return template.render(
        panels=contexts,
        enriched=any(p.enrichments for p in panels),
        has_hard=any(r["hard"] for c in contexts for r in c["rows"]),
        generated_at=_now_str(),
        freshness_days=freshness_days,
    )


def write_report(path: str | Path, html: str) -> Path:
    path = Path(path)
    path.write_text(html, encoding="utf-8")
    return path
