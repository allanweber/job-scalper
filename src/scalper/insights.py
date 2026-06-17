"""Phase 12: Market Insights — aggregate view of the stored job market.

No LLM, no profile argument. Reads the store directly and reports:
- Skill demand: how often each skill appears across postings
- Salary distribution: min / median / max from native + enriched salary data
- Postings per source
- Weekly collection volume (last 8 ISO weeks)

The skill vocabulary comes from the union of all profiles' skills (required +
nice-to-have) in the config, supplemented by any --skills the caller passes.
"""

from __future__ import annotations

import statistics
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from scalper.scoring import _contains_term

if TYPE_CHECKING:
    from scalper.store import JobStore


@dataclass
class SkillHit:
    skill: str
    count: int
    pct: float  # percentage of postings that mention this skill


@dataclass
class SalaryStats:
    count: int  # postings with salary data (native or enriched)
    min: float
    median: float
    max: float
    currency: str | None = None


@dataclass
class InsightData:
    total: int
    since: datetime | None
    skill_demand: list[SkillHit] = field(default_factory=list)
    salary: SalaryStats | None = None
    source_counts: dict[str, int] = field(default_factory=dict)
    weekly_volume: list[tuple[str, int]] = field(default_factory=list)


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _iso_week(dt: datetime) -> str:
    iso = dt.isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


def compute_insights(
    store: "JobStore",
    *,
    since: datetime | None = None,
    skills: list[str] | None = None,
) -> InsightData:
    """Compute market insights over the stored postings.

    Parameters
    ----------
    store:
        Open ``JobStore`` to read from.
    since:
        If given, only postings with ``collected_at >= since`` are included.
    skills:
        Vocabulary for skill-demand counting. When ``None`` or empty, the
        skill demand section is omitted.
    """
    postings = list(store.iter_postings())
    if since is not None:
        cutoff = _aware(since)
        postings = [
            p for p in postings
            if p.collected_at is None or _aware(p.collected_at) >= cutoff
        ]

    total = len(postings)

    # --- skill demand -------------------------------------------------------
    skill_hits: list[SkillHit] = []
    if skills:
        for skill in skills:
            count = sum(
                1 for p in postings
                if _contains_term(p.search_text, skill)
            )
            pct = (count / total * 100) if total else 0.0
            skill_hits.append(SkillHit(skill=skill, count=count, pct=pct))
        skill_hits.sort(key=lambda h: (-h.count, h.skill))
        # Only keep skills that appear at least once
        skill_hits = [h for h in skill_hits if h.count > 0]

    # --- salary stats -------------------------------------------------------
    enr_salary = store.get_salary_enrichments()

    salaries: list[float] = []
    currencies: list[str] = []
    for p in postings:
        s_min, s_max, cur = p.salary_min, p.salary_max, p.salary_currency
        if s_min is None and s_max is None:
            if p.uid in enr_salary:
                s_min, s_max, cur = enr_salary[p.uid]
        if s_min is not None or s_max is not None:
            # Represent as midpoint when both ends are known; else use the available end.
            if s_min is not None and s_max is not None:
                val = (s_min + s_max) / 2.0
            else:
                val = s_min if s_min is not None else s_max
            salaries.append(val)  # type: ignore[arg-type]
            if cur:
                currencies.append(cur.strip().upper())

    salary_stats: SalaryStats | None = None
    if salaries:
        most_common_cur = max(set(currencies), key=currencies.count) if currencies else None
        salary_stats = SalaryStats(
            count=len(salaries),
            min=min(salaries),
            median=statistics.median(salaries),
            max=max(salaries),
            currency=most_common_cur,
        )

    # --- source counts (descending) -----------------------------------------
    src: dict[str, int] = {}
    for p in postings:
        src[p.source] = src.get(p.source, 0) + 1
    source_counts = dict(sorted(src.items(), key=lambda x: x[1], reverse=True))

    # --- weekly volume (last 8 ISO weeks, oldest first) ----------------------
    week_counts: dict[str, int] = {}
    for p in postings:
        if p.collected_at is not None:
            w = _iso_week(_aware(p.collected_at))
            week_counts[w] = week_counts.get(w, 0) + 1
    weekly = sorted(week_counts.items(), reverse=True)[:8]
    weekly.reverse()

    return InsightData(
        total=total,
        since=since,
        skill_demand=skill_hits,
        salary=salary_stats,
        source_counts=source_counts,
        weekly_volume=weekly,
    )


def _bar(fraction: float, width: int = 24) -> str:
    filled = round(fraction * width)
    return "█" * filled + "░" * (width - filled)


def format_insights(data: InsightData) -> str:
    lines: list[str] = []

    since_str = f"since {data.since.strftime('%Y-%m-%d')}" if data.since else "all time"
    lines.append(f"Market Insights  ({data.total} postings, {since_str})")

    # --- skill demand -------------------------------------------------------
    if data.skill_demand:
        lines.append("")
        lines.append("Skill demand")
        max_count = data.skill_demand[0].count or 1
        for h in data.skill_demand:
            bar = _bar(h.count / max_count)
            lines.append(f"  {h.skill:<22}  {h.count:>5}  {bar}  {h.pct:.0f}%")

    # --- salary -------------------------------------------------------------
    if data.salary:
        s = data.salary
        cur = f" {s.currency}" if s.currency else ""
        lines.append("")
        lines.append(f"Salary distribution  ({s.count} postings with salary data)")
        lines.append(f"  min       {s.min:>10,.0f}{cur}")
        lines.append(f"  median    {s.median:>10,.0f}{cur}")
        lines.append(f"  max       {s.max:>10,.0f}{cur}")

    # --- source counts ------------------------------------------------------
    if data.source_counts:
        lines.append("")
        lines.append("Postings by source")
        for src, n in data.source_counts.items():
            lines.append(f"  {src:<22}  {n:>5}")

    # --- weekly volume ------------------------------------------------------
    if data.weekly_volume:
        max_n = max(n for _, n in data.weekly_volume) or 1
        lines.append("")
        lines.append("Weekly volume (last 8 weeks)")
        for week, n in data.weekly_volume:
            bar = _bar(n / max_n)
            lines.append(f"  {week}  {n:>5}  {bar}")

    return "\n".join(lines)
