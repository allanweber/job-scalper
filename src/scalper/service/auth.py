"""Authentication: Google sign-in -> app JWT + rotating refresh tokens (ADR 0010).

Mobile flow: the app sends a Google **ID token**; we verify it, upsert the user
(role resolved from the admin allowlist), and issue a short-lived **access JWT**
plus a **refresh token** whose hash is stored server-side (revocable, rotated on
every use). The admin web app reuses `AdminAllowlist` + Google verification but
keeps a server-side session (Phase 4), not these bearer tokens.

Google verification is behind `IDTokenVerifier` so tests inject a fake and the
real `google-auth` dependency is only imported when actually used.
"""

from __future__ import annotations

import hashlib
import secrets
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Protocol

import jwt

from scalper.service.models import GoogleIdentity, TokenPair, User, now
from scalper.service.repositories import RefreshTokenRepo, UserRepo


class AuthError(Exception):
    """Base for authentication failures."""


class InvalidToken(AuthError):
    pass


class AccountInactive(AuthError):
    pass


# --- Google ID-token verification ----------------------------------------

class IDTokenVerifier(Protocol):
    def verify(self, id_token: str) -> GoogleIdentity: ...


class GoogleIDTokenVerifier:
    """Verifies Google ID tokens against the configured OAuth client IDs.

    `allowed_audiences` are the Google client IDs the mobile app / server accept
    (the token's `aud` must match one). google-auth is imported lazily.
    """

    def __init__(self, allowed_audiences: list[str]):
        if not allowed_audiences:
            raise ValueError("at least one allowed audience (client id) is required")
        self._aud = set(allowed_audiences)

    def verify(self, id_token: str) -> GoogleIdentity:
        try:
            from google.auth.transport import requests as g_requests  # type: ignore
            from google.oauth2 import id_token as g_id_token  # type: ignore
        except ModuleNotFoundError as e:  # pragma: no cover - env-dependent
            raise RuntimeError(
                "google-auth is not installed; install the '.[api]' extras."
            ) from e
        try:
            claims = g_id_token.verify_oauth2_token(id_token, g_requests.Request())
        except Exception as e:
            raise InvalidToken(f"Google ID token verification failed: {e}") from e
        if claims.get("aud") not in self._aud:
            raise InvalidToken("ID token audience mismatch")
        if not claims.get("email"):
            raise InvalidToken("ID token has no email")
        return GoogleIdentity(
            sub=claims["sub"],
            email=claims["email"],
            email_verified=bool(claims.get("email_verified", False)),
            name=claims.get("name"),
            picture=claims.get("picture"),
        )


# --- Admin allowlist ------------------------------------------------------

class AdminAllowlist:
    """The set of emails granted the admin role (source of truth for `role`)."""

    def __init__(self, emails: list[str]):
        self._emails = {e.strip().lower() for e in emails if e.strip()}

    @classmethod
    def from_env(cls, environ: dict[str, str], key: str = "SCALPER_ADMIN_EMAILS") -> "AdminAllowlist":
        raw = environ.get(key, "")
        return cls(raw.split(",") if raw else [])

    def role_for(self, email: str) -> str:
        return "admin" if email.strip().lower() in self._emails else "user"


# --- Token issuing / verification ----------------------------------------

@dataclass
class AuthConfig:
    jwt_secret: str
    access_ttl_seconds: int = 900              # 15 minutes
    refresh_ttl_seconds: int = 60 * 60 * 24 * 30  # 30 days
    issuer: str = "job-scalper"
    algorithm: str = "HS256"

    @classmethod
    def from_env(cls, environ: dict[str, str]) -> "AuthConfig":
        secret = environ.get("SCALPER_JWT_SECRET")
        if not secret:
            raise RuntimeError("SCALPER_JWT_SECRET is not set")
        return cls(
            jwt_secret=secret,
            access_ttl_seconds=int(environ.get("SCALPER_ACCESS_TTL", 900)),
            refresh_ttl_seconds=int(environ.get("SCALPER_REFRESH_TTL", 60 * 60 * 24 * 30)),
        )


def _hash_refresh(raw: str) -> str:
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class AuthService:
    """Orchestrates sign-in, refresh, and logout over the user/token repos."""

    def __init__(self, conn: Any, verifier: IDTokenVerifier, allowlist: AdminAllowlist,
                 config: AuthConfig):
        self._users = UserRepo(conn)
        self._refresh = RefreshTokenRepo(conn)
        self._verifier = verifier
        self._allowlist = allowlist
        self._cfg = config

    # -- access JWTs --

    def issue_access(self, user: User) -> str:
        iat = now()
        payload = {
            "sub": user.id,
            "email": user.email,
            "role": user.role,
            "plan": user.plan,
            "type": "access",
            "iss": self._cfg.issuer,
            "iat": iat,
            "exp": iat + timedelta(seconds=self._cfg.access_ttl_seconds),
        }
        return jwt.encode(payload, self._cfg.jwt_secret, algorithm=self._cfg.algorithm)

    def verify_access(self, token: str) -> dict[str, Any]:
        try:
            claims = jwt.decode(
                token, self._cfg.jwt_secret, algorithms=[self._cfg.algorithm],
                issuer=self._cfg.issuer,
            )
        except jwt.PyJWTError as e:
            raise InvalidToken(f"access token invalid: {e}") from e
        if claims.get("type") != "access":
            raise InvalidToken("not an access token")
        return claims

    # -- refresh tokens (opaque, hashed, rotated) --

    def _new_refresh(self, user_id: str, device_info: str | None) -> str:
        raw = secrets.token_urlsafe(48)
        expires = (now() + timedelta(seconds=self._cfg.refresh_ttl_seconds)).isoformat()
        self._refresh.create(user_id, _hash_refresh(raw), expires, device_info)
        return raw

    def _issue_pair(self, user: User, device_info: str | None) -> TokenPair:
        return TokenPair(
            access_token=self.issue_access(user),
            refresh_token=self._new_refresh(user.id, device_info),
            expires_in=self._cfg.access_ttl_seconds,
        )

    # -- public flows --

    def sign_in_with_google(self, id_token: str, *, device_info: str | None = None) -> tuple[User, TokenPair]:
        identity = self._verifier.verify(id_token)
        if not identity.email_verified:
            raise InvalidToken("Google email is not verified")
        role = self._allowlist.role_for(identity.email)
        user = self._users.upsert_from_google(identity, role=role)
        if not user.is_active:
            raise AccountInactive("account is suspended")
        return user, self._issue_pair(user, device_info)

    def refresh(self, raw_refresh: str, *, device_info: str | None = None) -> tuple[User, TokenPair]:
        rec = self._refresh.get_by_hash(_hash_refresh(raw_refresh))
        if rec is None:
            raise InvalidToken("unknown refresh token")
        if rec.revoked_at is not None:
            # Reuse of a rotated/revoked token: revoke the whole family defensively.
            self._refresh.revoke_all_for_user(rec.user_id)
            raise InvalidToken("refresh token already used or revoked")
        if _parse_iso(rec.expires_at) < now():
            raise InvalidToken("refresh token expired")
        user = self._users.get(rec.user_id)
        if user is None:
            raise InvalidToken("user no longer exists")
        if not user.is_active:
            raise AccountInactive("account is suspended")
        self._refresh.revoke(rec.id)  # rotate
        return user, self._issue_pair(user, device_info)

    def logout(self, raw_refresh: str) -> None:
        rec = self._refresh.get_by_hash(_hash_refresh(raw_refresh))
        if rec is not None:
            self._refresh.revoke(rec.id)

    def logout_all(self, user_id: str) -> None:
        self._refresh.revoke_all_for_user(user_id)


def _parse_iso(value: str) -> datetime:
    dt = datetime.fromisoformat(value)
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
