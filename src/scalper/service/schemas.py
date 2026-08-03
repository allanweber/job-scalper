"""Pydantic request/response schemas for the public API (Phase 3).

These are the transport contract the OpenAPI spec — and the generated Dart client —
are derived from. Kept separate from the internal dataclass records so the wire
shape can evolve independently of storage.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, HttpUrl, field_validator, model_validator


# --- auth ---

class GoogleSignInRequest(BaseModel):
    id_token: str
    device_info: str | None = None


class RefreshRequest(BaseModel):
    refresh_token: str
    device_info: str | None = None


class LogoutRequest(BaseModel):
    refresh_token: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "Bearer"
    expires_in: int


class UserResponse(BaseModel):
    id: str
    email: str
    display_name: str | None = None
    avatar_url: str | None = None
    role: str
    plan: str
    tos_accepted: bool
    privacy_accepted: bool
    #: Whether the user has a saved search profile — the client's source of truth
    #: for "has this account finished onboarding" (independent of device state).
    has_profile: bool = False


class SignInResponse(BaseModel):
    user: UserResponse
    tokens: TokenResponse


# --- profile / sources / keys ---

class ProfileFields(BaseModel):
    name: str = "default"
    titles: list[str] = Field(default_factory=list)
    required_skills: list[str] = Field(default_factory=list)
    nice_to_have_skills: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    exclude_keywords: list[str] = Field(default_factory=list)
    remote_only: bool = True
    salary_floor: float = 0.0
    exclude_non_latin: bool = True


class ProfileResponse(ProfileFields):
    id: str
    origin: str


class SourcesRequest(BaseModel):
    sources: list[str]


class SourcesResponse(BaseModel):
    sources: list[str]
    available: list[str]
    max_allowed: int


class LLMKeyRequest(BaseModel):
    provider: str  # 'anthropic' | 'openai'
    api_key: str


class LLMKeyInfo(BaseModel):
    provider: str
    valid: bool
    last_validated_at: str | None = None


class LLMKeysResponse(BaseModel):
    keys: list[LLMKeyInfo]


# --- resume ---

class ResumeResponse(BaseModel):
    filename: str | None
    content_type: str | None
    size_bytes: int
    text_chars: int
    updated_at: str


# --- feed ---

class FeedItemResponse(BaseModel):
    posting_id: str
    company: str
    title: str
    url: str
    location: str | None = None
    remote: bool
    salary_min: float | None = None
    salary_max: float | None = None
    salary_currency: str | None = None
    published_at: str | None = None
    score: int
    matched_skills: list[str]
    missing_skills: list[str]
    matched_keywords: list[str]
    sources: list[str]
    is_new: bool
    saved: bool
    drafted: bool
    applied: bool = False
    breakdown: dict[str, float]


class FeedMetaResponse(BaseModel):
    """Thin-feed context so the client can nudge a new user precisely."""

    pool_size: int
    sources_count: int
    sources_max: int
    has_profile: bool


class FeedResponse(BaseModel):
    items: list[FeedItemResponse]
    count: int
    meta: FeedMetaResponse


class PostingDetailResponse(BaseModel):
    """A single posting's full text plus the requesting user's match breakdown."""

    posting_id: str
    company: str
    title: str
    url: str
    description: str
    location: str | None = None
    remote: bool
    timezone: str | None = None
    salary_min: float | None = None
    salary_max: float | None = None
    salary_currency: str | None = None
    published_at: str | None = None
    score: int
    matched_skills: list[str]
    missing_skills: list[str]
    matched_keywords: list[str]
    sources: list[str]
    is_new: bool
    saved: bool
    drafted: bool
    applied: bool = False
    breakdown: dict[str, float]


# --- jobs ---

class JobResponse(BaseModel):
    id: str
    kind: str
    status: str
    result: dict[str, Any] | None = None
    error: str | None = None
    created_at: str
    finished_at: str | None = None


class JobAccepted(BaseModel):
    job_id: str
    status: str


class DraftRequest(BaseModel):
    posting_id: str


class EnrichRequest(BaseModel):
    posting_id: str


class ImportUrlRequest(BaseModel):
    url: HttpUrl


class DraftUpdateRequest(BaseModel):
    """Edit a draft's resume and/or cover-letter markdown (mobile edit sheets)."""

    resume_md: str | None = None
    cover_letter_md: str | None = None

    @model_validator(mode="after")
    def _at_least_one(self) -> "DraftUpdateRequest":
        if self.resume_md is None and self.cover_letter_md is None:
            raise ValueError("provide resume_md and/or cover_letter_md")
        return self


class AppliedRequest(BaseModel):
    """Mark (or unmark) a draft's posting as applied (draft detail screen)."""

    applied: bool = True


#: The application pipeline stages, in funnel order. NULL/None means "not
#: applied". 'applied' is the entry point and 'offer' the success end; 'ghosted'
#: (no response) and 'rejected' (denied) are off-ramps rather than later stages.
APPLICATION_STATUSES = (
    "applied", "pre_screen", "interviewing", "offer", "ghosted", "rejected")


class ApplicationStatusRequest(BaseModel):
    """Set (or clear) a draft's application pipeline stage (Applications tab).

    ``status`` is one of :data:`APPLICATION_STATUSES`, or ``None`` to clear it
    back to not-applied.
    """

    status: str | None = None

    @field_validator("status")
    @classmethod
    def _known_status(cls, v: str | None) -> str | None:
        if v is not None and v not in APPLICATION_STATUSES:
            raise ValueError(
                f"status must be one of {APPLICATION_STATUSES} or null")
        return v


# --- drafts ---

class DraftResponse(BaseModel):
    id: str
    posting_id: str | None
    job_source: str
    resume_md: str | None
    cover_letter_md: str | None
    stretch_claims_md: str | None
    provider: str | None
    model: str | None
    key_source: str | None
    created_at: str
    applied: bool = False
    application_status: str | None = None  # applied|interviewing|offer|rejected
    status: str = "ready"  # 'pending' | 'ready' | 'failed'
    error: str | None = None


class ApplicationInsights(BaseModel):
    """Aggregate application funnel for the Insights flow chart.

    ``total`` is the number of drafts (each is one application). ``counts`` maps
    every stage in :data:`APPLICATION_STATUSES` to how many applications sit
    there now, with unmarked drafts folded into ``applied`` (submitted, awaiting
    a response). The counts sum to ``total``, so the client can lay out a Sankey
    directly.
    """

    total: int
    counts: dict[str, int]


class DraftSummary(BaseModel):
    id: str
    posting_id: str | None
    job_source: str
    key_source: str | None
    created_at: str
    title: str | None = None
    company: str | None = None
    url: str | None = None
    applied: bool = False
    application_status: str | None = None  # applied|interviewing|offer|rejected
    status: str = "ready"  # 'pending' | 'ready' | 'failed'
    error: str | None = None


# --- quota ---

class QuotaMetric(BaseModel):
    metric: str
    limit: int
    used: int
    remaining: int
    unlimited: bool


class QuotaResponse(BaseModel):
    plan: str
    period: str
    byo_key: bool
    metrics: list[QuotaMetric]


# --- legal ---

class LegalDoc(BaseModel):
    title: str
    version: str
    body: str


class MessageResponse(BaseModel):
    message: str


# --- push notifications ---

class DeviceRegisterRequest(BaseModel):
    """Register this device's push token so the backend can notify it."""

    token: str = Field(min_length=1)
    platform: str | None = None  # 'android' | 'ios' | 'web'


class NotificationPrefsResponse(BaseModel):
    match_alerts: bool
    min_score: int


class NotificationPrefsRequest(BaseModel):
    """Update notification preferences (Profile → Notifications)."""

    match_alerts: bool = True
    min_score: int = Field(default=90, ge=0, le=100)
