"""`insights` command: read-only aggregate view of the stored job market.

No LLM, no profile argument required. Returns a typed result containing the
computed ``InsightData`` and its formatted text summary.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from scalper.commands import CommandError
from scalper.config import Config
from scalper.insights import InsightData, compute_insights, format_insights
from scalper.store import JobStore


class StoreNotFoundError(CommandError):
    """No store exists yet — `collect` has not been run."""


@dataclass
class InsightsResult:
    data: InsightData
    text: str


def run_insights(
    config: Config,
    *,
    since: datetime | None = None,
    extra_skills: list[str] | None = None,
    db: str | None = None,
) -> InsightsResult:
    """Compute and format market insights over the stored postings.

    Parameters
    ----------
    config:
        Loaded config; profiles are used to build the skill vocabulary.
    since:
        If given, only postings collected on/after this datetime are included.
    extra_skills:
        Additional skills to include in demand counting (supplements profiles;
        useful when no profiles are configured).
    db:
        Database path override (default: ``config.database``).
    """
    db_path = Path(db or config.database)
    if not db_path.exists():
        raise StoreNotFoundError(
            f"no database at {db_path} — run 'scalper collect' first"
        )

    # Build skill vocabulary: union of all profiles' required + nice-to-have,
    # then any caller-supplied extras.
    seen: set[str] = set()
    skills: list[str] = []
    for profile in config.profiles.values():
        for s in list(profile.required_skills) + list(profile.nice_to_have_skills):
            key = s.lower()
            if key not in seen:
                skills.append(key)
                seen.add(key)
    for s in extra_skills or []:
        key = s.strip().lower()
        if key and key not in seen:
            skills.append(key)
            seen.add(key)

    with JobStore(db_path) as store:
        data = compute_insights(store, since=since, skills=skills or None)

    return InsightsResult(data=data, text=format_insights(data))
