"""Data-access repositories for the service layer (raw SQL over the DB-API conn).

Rows are read positionally (explicit column lists) so the code is identical on
the sqlite fallback and the libsql client. Timestamps are ISO-8601 UTC strings.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from scalper.service.crypto import Sealed
from scalper.service.models import GoogleIdentity, User, now_iso

_USER_COLS = (
    "id, google_sub, email, display_name, avatar_url, role, status, plan, "
    "tos_accepted_at, privacy_accepted_at, created_at, updated_at, last_login_at"
)


def _new_id() -> str:
    return uuid.uuid4().hex


def _to_user(row: Any) -> User:
    return User(
        id=row[0], google_sub=row[1], email=row[2], display_name=row[3],
        avatar_url=row[4], role=row[5], status=row[6], plan=row[7],
        tos_accepted_at=row[8], privacy_accepted_at=row[9],
        created_at=row[10], updated_at=row[11], last_login_at=row[12],
    )


class UserRepo:
    def __init__(self, conn: Any):
        self._c = conn

    def _get_one(self, where: str, params: tuple) -> User | None:
        row = self._c.execute(
            f"SELECT {_USER_COLS} FROM users WHERE {where}", params
        ).fetchone()
        return _to_user(row) if row else None

    def get(self, user_id: str) -> User | None:
        return self._get_one("id = ?", (user_id,))

    def get_by_google_sub(self, sub: str) -> User | None:
        return self._get_one("google_sub = ?", (sub,))

    def get_by_email(self, email: str) -> User | None:
        return self._get_one("email = ?", (email.lower(),))

    def upsert_from_google(self, identity: GoogleIdentity, *, role: str) -> User:
        """Create the user on first sign-in, else refresh mutable identity fields.

        `role` is resolved from the admin allowlist on every sign-in, so the
        allowlist stays the source of truth for admin status.
        """
        ts = now_iso()
        existing = self.get_by_google_sub(identity.sub)
        email = identity.email.lower()
        if existing is None:
            user = User(
                id=_new_id(), google_sub=identity.sub, email=email,
                display_name=identity.name, avatar_url=identity.picture,
                role=role, status="active", plan="free",
                created_at=ts, updated_at=ts, last_login_at=ts,
            )
            self._c.execute(
                f"INSERT INTO users ({_USER_COLS}) VALUES "
                "(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (user.id, user.google_sub, user.email, user.display_name,
                 user.avatar_url, user.role, user.status, user.plan,
                 user.tos_accepted_at, user.privacy_accepted_at,
                 user.created_at, user.updated_at, user.last_login_at),
            )
            self._c.commit()
            return user
        self._c.execute(
            "UPDATE users SET email=?, display_name=?, avatar_url=?, role=?, "
            "updated_at=?, last_login_at=? WHERE id=?",
            (email, identity.name, identity.picture, role, ts, ts, existing.id),
        )
        self._c.commit()
        return self.get(existing.id)  # type: ignore[return-value]

    def accept_legal(self, user_id: str, *, tos: bool = True, privacy: bool = True) -> None:
        ts = now_iso()
        sets, params = [], []
        if tos:
            sets.append("tos_accepted_at=?"); params.append(ts)
        if privacy:
            sets.append("privacy_accepted_at=?"); params.append(ts)
        if not sets:
            return
        sets.append("updated_at=?"); params.append(ts)
        params.append(user_id)
        self._c.execute(f"UPDATE users SET {', '.join(sets)} WHERE id=?", tuple(params))
        self._c.commit()

    # --- admin operations -------------------------------------------------

    def set_status(self, user_id: str, status: str) -> None:
        self._c.execute(
            "UPDATE users SET status=?, updated_at=? WHERE id=?",
            (status, now_iso(), user_id),
        )
        self._c.commit()

    def set_plan(self, user_id: str, plan: str) -> None:
        self._c.execute(
            "UPDATE users SET plan=?, updated_at=? WHERE id=?",
            (plan, now_iso(), user_id),
        )
        self._c.commit()

    def delete(self, user_id: str) -> None:
        # ON DELETE CASCADE clears the user's owned rows (see schema).
        self._c.execute("DELETE FROM users WHERE id=?", (user_id,))
        self._c.commit()

    def count(self) -> int:
        return self._c.execute("SELECT COUNT(*) FROM users").fetchone()[0]

    def list(self, *, query: str | None = None, limit: int = 50,
             offset: int = 0) -> list[User]:
        """List users (admin), optionally filtered by an email/name substring."""
        where, params = "", []
        if query:
            where = "WHERE email LIKE ? OR display_name LIKE ?"
            like = f"%{query.lower()}%"
            params = [like, like]
        rows = self._c.execute(
            f"SELECT {_USER_COLS} FROM users {where} "
            "ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (*params, limit, offset),
        ).fetchall()
        return [_to_user(r) for r in rows]

    def count_by_status(self) -> dict[str, int]:
        rows = self._c.execute(
            "SELECT status, COUNT(*) FROM users GROUP BY status"
        ).fetchall()
        return {r[0]: r[1] for r in rows}


@dataclass
class RefreshRecord:
    id: str
    user_id: str
    expires_at: str
    revoked_at: str | None


class RefreshTokenRepo:
    def __init__(self, conn: Any):
        self._c = conn

    def create(self, user_id: str, token_hash: str, expires_at: str,
               device_info: str | None = None) -> str:
        rid = _new_id()
        self._c.execute(
            "INSERT INTO refresh_tokens (id, user_id, token_hash, device_info, "
            "issued_at, expires_at) VALUES (?,?,?,?,?,?)",
            (rid, user_id, token_hash, device_info, now_iso(), expires_at),
        )
        self._c.commit()
        return rid

    def get_by_hash(self, token_hash: str) -> RefreshRecord | None:
        row = self._c.execute(
            "SELECT id, user_id, expires_at, revoked_at FROM refresh_tokens "
            "WHERE token_hash=?", (token_hash,),
        ).fetchone()
        return RefreshRecord(row[0], row[1], row[2], row[3]) if row else None

    def revoke(self, token_id: str) -> None:
        self._c.execute(
            "UPDATE refresh_tokens SET revoked_at=? WHERE id=? AND revoked_at IS NULL",
            (now_iso(), token_id),
        )
        self._c.commit()

    def revoke_all_for_user(self, user_id: str) -> None:
        self._c.execute(
            "UPDATE refresh_tokens SET revoked_at=? WHERE user_id=? AND revoked_at IS NULL",
            (now_iso(), user_id),
        )
        self._c.commit()


@dataclass
class CredentialInfo:
    provider: str
    valid: bool
    last_validated_at: str | None


class LLMCredentialRepo:
    def __init__(self, conn: Any):
        self._c = conn

    def upsert(self, user_id: str, provider: str, sealed: Sealed) -> None:
        ts = now_iso()
        self._c.execute(
            "INSERT INTO llm_credentials (user_id, provider, ciphertext, nonce, "
            "key_version, valid, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?) "
            "ON CONFLICT(user_id, provider) DO UPDATE SET ciphertext=excluded.ciphertext, "
            "nonce=excluded.nonce, key_version=excluded.key_version, valid=excluded.valid, "
            "updated_at=excluded.updated_at",
            (user_id, provider, sealed.ciphertext, sealed.nonce, sealed.key_version,
             1, ts, ts),
        )
        self._c.commit()

    def get_sealed(self, user_id: str, provider: str) -> Sealed | None:
        row = self._c.execute(
            "SELECT ciphertext, nonce, key_version FROM llm_credentials "
            "WHERE user_id=? AND provider=?", (user_id, provider),
        ).fetchone()
        if not row:
            return None
        return Sealed(ciphertext=bytes(row[0]), nonce=bytes(row[1]), key_version=row[2])

    def list_for(self, user_id: str) -> list[CredentialInfo]:
        rows = self._c.execute(
            "SELECT provider, valid, last_validated_at FROM llm_credentials "
            "WHERE user_id=? ORDER BY provider", (user_id,),
        ).fetchall()
        return [CredentialInfo(r[0], bool(r[1]), r[2]) for r in rows]

    def has_valid(self, user_id: str, provider: str | None = None) -> bool:
        if provider:
            row = self._c.execute(
                "SELECT 1 FROM llm_credentials WHERE user_id=? AND provider=? AND valid=1",
                (user_id, provider),
            ).fetchone()
        else:
            row = self._c.execute(
                "SELECT 1 FROM llm_credentials WHERE user_id=? AND valid=1 LIMIT 1",
                (user_id,),
            ).fetchone()
        return row is not None

    def set_valid(self, user_id: str, provider: str, valid: bool) -> None:
        self._c.execute(
            "UPDATE llm_credentials SET valid=?, last_validated_at=?, updated_at=? "
            "WHERE user_id=? AND provider=?",
            (1 if valid else 0, now_iso(), now_iso(), user_id, provider),
        )
        self._c.commit()

    def delete(self, user_id: str, provider: str) -> None:
        self._c.execute(
            "DELETE FROM llm_credentials WHERE user_id=? AND provider=?",
            (user_id, provider),
        )
        self._c.commit()


class UsageRepo:
    """Per-user, per-metric, per-period counters for quota enforcement."""

    def __init__(self, conn: Any):
        self._c = conn

    def get_count(self, user_id: str, metric: str, period: str) -> int:
        row = self._c.execute(
            "SELECT count FROM usage_counters WHERE user_id=? AND metric=? AND period=?",
            (user_id, metric, period),
        ).fetchone()
        return row[0] if row else 0

    def increment(self, user_id: str, metric: str, period: str, n: int = 1) -> int:
        self._c.execute(
            "INSERT INTO usage_counters (user_id, metric, period, count, updated_at) "
            "VALUES (?,?,?,?,?) ON CONFLICT(user_id, metric, period) DO UPDATE SET "
            "count=count+excluded.count, updated_at=excluded.updated_at",
            (user_id, metric, period, n, now_iso()),
        )
        self._c.commit()
        return self.get_count(user_id, metric, period)


class QuotaOverrideRepo:
    def __init__(self, conn: Any):
        self._c = conn

    def get(self, user_id: str, metric: str) -> int | None:
        row = self._c.execute(
            "SELECT limit_value FROM user_quota_overrides WHERE user_id=? AND metric=?",
            (user_id, metric),
        ).fetchone()
        return row[0] if row else None

    def set(self, user_id: str, metric: str, limit_value: int) -> None:
        self._c.execute(
            "INSERT INTO user_quota_overrides (user_id, metric, limit_value, updated_at) "
            "VALUES (?,?,?,?) ON CONFLICT(user_id, metric) DO UPDATE SET "
            "limit_value=excluded.limit_value, updated_at=excluded.updated_at",
            (user_id, metric, limit_value, now_iso()),
        )
        self._c.commit()
