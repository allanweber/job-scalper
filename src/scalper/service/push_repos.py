"""Repositories for push notifications: registered devices + per-user prefs.

Same conventions as the other repos (raw SQL over the DB-API conn, ISO-8601 UTC
timestamps). Devices are keyed by their FCM registration token; preferences
default to the product promise (alerts on, notify at score >= 90) so an opted-in
user needs no extra setup.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from scalper.service.models import now_iso

#: Default notify threshold — the "scores 90+" promise from onboarding.
DEFAULT_MIN_SCORE = 90


@dataclass
class Device:
    token: str
    user_id: str
    platform: str | None
    created_at: str
    last_seen_at: str


@dataclass
class NotificationPrefs:
    user_id: str
    match_alerts: bool
    min_score: int


class PushDeviceRepo:
    """Registered push devices (one row per FCM token)."""

    def __init__(self, conn: Any):
        self._c = conn

    def register(self, user_id: str, token: str, platform: str | None) -> None:
        """Upsert a device token for a user (idempotent re-registration).

        If the same token was previously registered to another user (a shared
        device, a re-install), it is reassigned to the current user.
        """
        ts = now_iso()
        self._c.execute(
            "INSERT INTO push_devices (token, user_id, platform, created_at, "
            "last_seen_at) VALUES (?,?,?,?,?) ON CONFLICT(token) DO UPDATE SET "
            "user_id=excluded.user_id, platform=excluded.platform, "
            "last_seen_at=excluded.last_seen_at",
            (token, user_id, platform, ts, ts),
        )
        self._c.commit()

    def unregister(self, user_id: str, token: str) -> bool:
        """Remove one of the user's device tokens. Returns True if a row went."""
        cur = self._c.execute(
            "DELETE FROM push_devices WHERE token=? AND user_id=?", (token, user_id)
        )
        self._c.commit()
        return bool(cur.rowcount)

    def tokens_for(self, user_id: str) -> list[str]:
        rows = self._c.execute(
            "SELECT token FROM push_devices WHERE user_id=?", (user_id,)
        ).fetchall()
        return [r[0] for r in rows]

    def user_ids_with_devices(self) -> list[str]:
        """Active users who have at least one registered device (notify scope)."""
        rows = self._c.execute(
            "SELECT DISTINCT d.user_id FROM push_devices d "
            "JOIN users u ON u.id = d.user_id WHERE u.status='active'"
        ).fetchall()
        return [r[0] for r in rows]

    def delete_token(self, token: str) -> None:
        """Drop a token FCM reported as unregistered/invalid."""
        self._c.execute("DELETE FROM push_devices WHERE token=?", (token,))
        self._c.commit()


class NotificationPrefsRepo:
    """Per-user notification preferences; absent row = defaults."""

    def __init__(self, conn: Any):
        self._c = conn

    def get(self, user_id: str) -> NotificationPrefs:
        row = self._c.execute(
            "SELECT match_alerts, min_score FROM notification_prefs WHERE user_id=?",
            (user_id,),
        ).fetchone()
        if row is None:
            return NotificationPrefs(user_id, match_alerts=True,
                                     min_score=DEFAULT_MIN_SCORE)
        return NotificationPrefs(user_id, match_alerts=bool(row[0]), min_score=row[1])

    def upsert(self, user_id: str, *, match_alerts: bool, min_score: int) -> NotificationPrefs:
        self._c.execute(
            "INSERT INTO notification_prefs (user_id, match_alerts, min_score, "
            "updated_at) VALUES (?,?,?,?) ON CONFLICT(user_id) DO UPDATE SET "
            "match_alerts=excluded.match_alerts, min_score=excluded.min_score, "
            "updated_at=excluded.updated_at",
            (user_id, 1 if match_alerts else 0, min_score, now_iso()),
        )
        self._c.commit()
        return self.get(user_id)
