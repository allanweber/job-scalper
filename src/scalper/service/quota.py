"""Quota engine: resolve plan limits, check, and consume usage (ADR 0009).

Limits come from the hot `quota.<plan>` setting, overridable per user in
`user_quota_overrides`. Only LLM-bound metrics exist (drafts, profile-builds,
enrich) on a monthly period — users never scrape (ADR 0011). Callers routing a
request to a user's BYO key pass `unlimited=True`, which never blocks but still
records usage for admin visibility.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable

from scalper.service.models import QuotaStatus, User, now
from scalper.service.repositories import QuotaOverrideRepo, UsageRepo
from scalper.service.settings import Settings

#: metric -> the key inside the `quota.<plan>` settings object.
_METRIC_SETTING_KEY = {
    "draft": "draft_per_month",
    "profile_build": "profile_build_per_month",
    "enrich": "enrich_per_month",
}
METRICS = tuple(_METRIC_SETTING_KEY)


class QuotaExceeded(Exception):
    def __init__(self, status: QuotaStatus):
        self.status = status
        super().__init__(
            f"quota exceeded for '{status.metric}': "
            f"{status.used}/{status.limit} used this period"
        )


@dataclass
class QuotaService:
    conn: Any
    settings: Settings
    clock: Callable[[], datetime] = now

    def __post_init__(self) -> None:
        self._usage = UsageRepo(self.conn)
        self._overrides = QuotaOverrideRepo(self.conn)

    def period(self) -> str:
        """Current monthly period key, e.g. '2026-07'."""
        return self.clock().strftime("%Y-%m")

    def limit_for(self, user: User, metric: str) -> int:
        """Resolved limit: per-user override wins, else the plan default.

        Returns -1 for unlimited, or the plan default 0 if the metric is unknown
        (fail-closed: an unconfigured metric grants nothing rather than infinity).
        """
        if metric not in _METRIC_SETTING_KEY:
            raise ValueError(f"unknown quota metric: {metric!r}")
        override = self._overrides.get(user.id, metric)
        if override is not None:
            return override
        plan_quota = self.settings.get(f"quota.{user.plan}", {}) or {}
        return int(plan_quota.get(_METRIC_SETTING_KEY[metric], 0))

    def status(self, user: User, metric: str, *, unlimited: bool = False) -> QuotaStatus:
        limit = -1 if unlimited else self.limit_for(user, metric)
        used = self._usage.get_count(user.id, metric, self.period())
        return QuotaStatus(metric=metric, limit=limit, used=used, period=self.period())

    def check(self, user: User, metric: str, *, unlimited: bool = False) -> QuotaStatus:
        """Non-mutating: current status (use `.allowed`)."""
        return self.status(user, metric, unlimited=unlimited)

    def consume(self, user: User, metric: str, n: int = 1, *,
                unlimited: bool = False) -> QuotaStatus:
        """Reserve `n` units, raising QuotaExceeded if it would exceed the limit.

        Usage is recorded even when `unlimited` (BYO), so admins still see spend;
        it simply never blocks.
        """
        current = self.status(user, metric, unlimited=unlimited)
        if not unlimited and current.used + n > current.limit:
            raise QuotaExceeded(current)
        new_used = self._usage.increment(user.id, metric, self.period(), n)
        return QuotaStatus(metric=metric, limit=current.limit, used=new_used,
                           period=self.period())
