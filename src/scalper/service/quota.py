"""Quota engine: resolve plan limits, check, and consume usage (ADR 0009).

Limits come from the hot `quota.<plan>` setting, overridable per user in
`user_quota_overrides`. Only LLM-bound metrics exist (drafts, profile-builds,
enrich) on a monthly period — users never scrape (ADR 0011). Callers routing a
request to a user's BYO key pass `unlimited=True`, which never blocks but still
records usage for admin visibility.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable

from scalper.service.models import QuotaStatus, User, now
from scalper.service.repositories import (
    QuotaOverrideRepo,
    UsageLedgerRepo,
    UsageRepo,
    subject_hash,
)
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
    #: Salt for the identity ledger's subject hash. Defaults to the server's
    #: usage pepper (or the JWT secret) from the environment; only stability per
    #: deployment matters, so an empty fallback is fine for dev/tests.
    pepper: str | None = None

    def __post_init__(self) -> None:
        self._usage = UsageRepo(self.conn)
        self._ledger = UsageLedgerRepo(self.conn)
        self._overrides = QuotaOverrideRepo(self.conn)
        if self.pepper is None:
            self.pepper = (os.environ.get("SCALPER_USAGE_PEPPER")
                           or os.environ.get("SCALPER_JWT_SECRET") or "")

    def _subject(self, user: User) -> str:
        return subject_hash(user.google_sub, self.pepper or "")

    def _used(self, user: User, metric: str, period: str) -> int:
        """Effective usage: the higher of the per-account counter and the durable
        identity ledger. The ledger survives account deletion, so a
        delete-and-recreate can't drop this below what was already consumed this
        period; the counter covers usage recorded before the ledger existed."""
        return max(self._usage.get_count(user.id, metric, period),
                   self._ledger.get_count(self._subject(user), metric, period))

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
        used = self._used(user, metric, self.period())
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
        # Record on both counters: the per-account one (admin display) and the
        # durable identity ledger (survives deletion, so it's what actually gates
        # a delete-and-recreate).
        self._usage.increment(user.id, metric, self.period(), n)
        self._ledger.increment(self._subject(user), metric, self.period(), n)
        return QuotaStatus(metric=metric, limit=current.limit,
                           used=self._used(user, metric, self.period()),
                           period=self.period())

    def refund(self, user: User, metric: str, n: int = 1) -> None:
        """Return up to `n` previously-consumed units for this period.

        Quota is reserved up-front (before the LLM call); when that call fails,
        the reservation should be released so a timeout/provider error doesn't
        cost the user a credit. Never drives the counter below zero.
        """
        if metric not in _METRIC_SETTING_KEY:
            raise ValueError(f"unknown quota metric: {metric!r}")
        period = self.period()
        # Release from both counters, each clamped so neither goes below zero.
        counter = self._usage.get_count(user.id, metric, period)
        if counter > 0:
            self._usage.increment(user.id, metric, period, -min(n, counter))
        subject = self._subject(user)
        ledger = self._ledger.get_count(subject, metric, period)
        if ledger > 0:
            self._ledger.increment(subject, metric, period, -min(n, ledger))
