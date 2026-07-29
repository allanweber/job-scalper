"""Internal domain records for the service layer (dataclasses, not API schemas).

These are plain records the repositories read/write. Phase 3 adds pydantic
request/response schemas at the API boundary; keeping the internal records as
dataclasses avoids coupling the data layer to the transport layer.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone


def now() -> datetime:
    return datetime.now(timezone.utc)


def now_iso() -> str:
    return now().isoformat()


@dataclass(frozen=True)
class GoogleIdentity:
    """The verified claims from a Google ID token / OAuth userinfo."""

    sub: str
    email: str
    email_verified: bool = True
    name: str | None = None
    picture: str | None = None


@dataclass
class User:
    id: str
    google_sub: str
    email: str
    display_name: str | None = None
    avatar_url: str | None = None
    role: str = "user"          # 'user' | 'admin'
    status: str = "active"      # 'active' | 'suspended'
    plan: str = "free"
    tos_accepted_at: str | None = None
    privacy_accepted_at: str | None = None
    created_at: str = field(default_factory=now_iso)
    updated_at: str = field(default_factory=now_iso)
    last_login_at: str | None = None

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"

    @property
    def is_active(self) -> bool:
        return self.status == "active"


@dataclass(frozen=True)
class TokenPair:
    """What a successful sign-in / refresh returns to the client."""

    access_token: str
    refresh_token: str
    token_type: str = "Bearer"
    expires_in: int = 0          # access-token lifetime, seconds


@dataclass(frozen=True)
class QuotaStatus:
    metric: str
    limit: int                   # -1 => unlimited (e.g. BYO key)
    used: int
    period: str

    @property
    def unlimited(self) -> bool:
        return self.limit < 0

    @property
    def remaining(self) -> int:
        return -1 if self.unlimited else max(0, self.limit - self.used)

    @property
    def allowed(self) -> bool:
        return self.unlimited or self.used < self.limit
