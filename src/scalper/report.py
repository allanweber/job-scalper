"""Render scored postings into a single self-contained HTML report."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from jinja2 import Environment, PackageLoader, select_autoescape

from scalper.config import Profile
from scalper.scoring import ScoredPosting

_env = Environment(
    loader=PackageLoader("scalper", "templates"),
    autoescape=select_autoescape(["html"]),
)


def _excerpt(text: str, limit: int = 320) -> str:
    text = text.strip()
    return text if len(text) <= limit else text[:limit].rsplit(" ", 1)[0] + "…"


def _row(scored: ScoredPosting) -> dict:
    p = scored.posting
    return {
        "percent": scored.percent,
        "title": p.title,
        "company": p.company,
        "location": p.location or ("Remote" if p.remote else "—"),
        "remote": p.remote,
        "timezone": p.timezone or "",
        "salary": p.salary_display or "",
        "source": p.source,
        "url": p.url,
        "published": p.published_at.date().isoformat() if p.published_at else "",
        "matched_skills": scored.matched_skills,
        "missing_skills": scored.missing_skills,
        "matched_nice_to_have": scored.matched_nice_to_have,
        "matched_keywords": scored.matched_keywords,
        "breakdown": {k: round(v * 100) for k, v in scored.breakdown.components().items()},
        "excerpt": _excerpt(p.description),
    }


def render_report(profile_name: str, profile: Profile, scored: list[ScoredPosting]) -> str:
    template = _env.get_template("report.html")
    return template.render(
        profile_name=profile_name,
        profile=profile,
        rows=[_row(s) for s in scored],
        total=len(scored),
        generated_at=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
    )


def write_report(path: str | Path, html: str) -> Path:
    path = Path(path)
    path.write_text(html, encoding="utf-8")
    return path
