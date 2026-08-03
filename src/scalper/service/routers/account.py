"""Account endpoints: profile, resume, sources, LLM keys, legal, quota.

All scoped to the authenticated user. Heavy work (profile-from-resume) is enqueued
as a job; everything else is synchronous DB work.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, UploadFile, status

from scalper.resume import extract_resume_text
from scalper.service.content_repos import JobRepo, ProfileRepo, ResumeRepo, UserSourceRepo
from scalper.service.deps import RequestContext, current_user, get_ctx
from scalper.service.jobs import KIND_PROFILE, JobQueue
from scalper.service.models import User
from scalper.service.quota import METRICS, QuotaService
from scalper.service.repositories import LLMCredentialRepo, UserRepo
from scalper.service.routers._helpers import profile_response, user_response
from scalper.service.push_repos import NotificationPrefsRepo, PushDeviceRepo
from scalper.service.schemas import (
    DeviceRegisterRequest,
    JobAccepted,
    LLMKeyInfo,
    LLMKeyRequest,
    LLMKeysResponse,
    MessageResponse,
    NotificationPrefsRequest,
    NotificationPrefsResponse,
    ProfileFields,
    ProfileResponse,
    QuotaMetric,
    QuotaResponse,
    ResumeResponse,
    SourcesRequest,
    SourcesResponse,
    UserResponse,
)

router = APIRouter(prefix="/me", tags=["account"])

_VALID_PROVIDERS = {"anthropic", "openai"}
#: Free-tier board cap; the "3 boards" limit gates feed visibility (ADR 0011).
_FREE_MAX_SOURCES = 3
_DEFAULT_MAX_UPLOAD = 5_000_000


def _has_profile(ctx: RequestContext, user_id: str) -> bool:
    return ProfileRepo(ctx.conn).primary_for(user_id) is not None


@router.get("", response_model=UserResponse)
def me(ctx: RequestContext = Depends(get_ctx), user: User = Depends(current_user)):
    return user_response(user, has_profile=_has_profile(ctx, user.id))


@router.post("/legal/accept", response_model=UserResponse)
def accept_legal(ctx: RequestContext = Depends(get_ctx), user: User = Depends(current_user)):
    UserRepo(ctx.conn).accept_legal(user.id)
    return user_response(UserRepo(ctx.conn).get(user.id),
                         has_profile=_has_profile(ctx, user.id))


# --- profile ---

@router.get("/profile", response_model=ProfileResponse)
def get_profile(ctx: RequestContext = Depends(get_ctx), user: User = Depends(current_user)):
    profile = ProfileRepo(ctx.conn).primary_for(user.id)
    if profile is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no profile yet")
    return profile_response(profile)


@router.put("/profile", response_model=ProfileResponse)
def put_profile(body: ProfileFields, ctx: RequestContext = Depends(get_ctx),
                user: User = Depends(current_user)):
    repo = ProfileRepo(ctx.conn)
    existing = repo.primary_for(user.id)
    fields = body.model_dump(exclude={"name"})
    stored = repo.upsert(user.id, body.name, fields, origin="manual",
                         profile_id=existing.id if existing else None)
    return profile_response(stored)


@router.post("/profile/from-resume", response_model=JobAccepted,
             status_code=status.HTTP_202_ACCEPTED)
def profile_from_resume(ctx: RequestContext = Depends(get_ctx),
                        user: User = Depends(current_user)):
    if ResumeRepo(ctx.conn).get_text(user.id) is None:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "upload a resume first")
    job_id = JobQueue(ctx.container).enqueue(ctx.conn, KIND_PROFILE, user_id=user.id,
                                             params={})
    return JobAccepted(job_id=job_id, status=JobRepo(ctx.conn).get(job_id).status)


# --- resume ---

@router.get("/resume", response_model=ResumeResponse)
def get_resume(ctx: RequestContext = Depends(get_ctx), user: User = Depends(current_user)):
    meta = ResumeRepo(ctx.conn).get_meta(user.id)
    if meta is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no resume uploaded")
    return ResumeResponse(
        filename=meta.filename, content_type=meta.content_type,
        size_bytes=meta.size_bytes, text_chars=len(meta.extracted_text),
        updated_at=meta.updated_at,
    )


@router.put("/resume", response_model=ResumeResponse)
async def upload_resume(file: UploadFile, ctx: RequestContext = Depends(get_ctx),
                        user: User = Depends(current_user)):
    max_bytes = int(ctx.settings.get("upload.max_bytes", _DEFAULT_MAX_UPLOAD)
                    or _DEFAULT_MAX_UPLOAD)
    allowed = ctx.settings.get("upload.allowed_content_types", []) or []
    ext_ok = (file.filename or "").lower().endswith((".pdf", ".md", ".markdown", ".txt"))
    if allowed and file.content_type not in allowed and not ext_ok:
        raise HTTPException(status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                            f"unsupported upload type '{file.content_type}' "
                            "(allowed: PDF, markdown, plain text)")
    data = await file.read()
    if not data:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "empty upload")
    if len(data) > max_bytes:
        # 413 literal: the named constant was renamed across Starlette versions.
        raise HTTPException(413, f"resume exceeds {max_bytes} bytes")
    text = extract_resume_text(data, filename=file.filename,
                               content_type=file.content_type)
    if not text.strip():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            "could not extract any text (scanned/image-only PDF?)")
    ResumeRepo(ctx.conn).upsert(user.id, filename=file.filename,
                                content_type=file.content_type, blob=data,
                                extracted_text=text)
    meta = ResumeRepo(ctx.conn).get_meta(user.id)
    return ResumeResponse(
        filename=meta.filename, content_type=meta.content_type,
        size_bytes=meta.size_bytes, text_chars=len(meta.extracted_text),
        updated_at=meta.updated_at,
    )


# --- sources ---

@router.get("/sources", response_model=SourcesResponse)
def get_sources(ctx: RequestContext = Depends(get_ctx), user: User = Depends(current_user)):
    enabled = list(ctx.settings.get("sources.enabled", []) or [])
    chosen = UserSourceRepo(ctx.conn).list_for(user.id)
    if not chosen:
        chosen = list(ctx.settings.get("sources.default", []) or [])
    return SourcesResponse(sources=chosen, available=enabled,
                           max_allowed=_FREE_MAX_SOURCES)


@router.put("/sources", response_model=SourcesResponse)
def put_sources(body: SourcesRequest, ctx: RequestContext = Depends(get_ctx),
                user: User = Depends(current_user)):
    enabled = set(ctx.settings.get("sources.enabled", []) or [])
    chosen = list(dict.fromkeys(body.sources))  # de-dupe, keep order
    unknown = [s for s in chosen if s not in enabled]
    if unknown:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            f"unknown/disabled sources: {', '.join(unknown)}")
    if user.plan == "free" and len(chosen) > _FREE_MAX_SOURCES:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            f"free plan allows at most {_FREE_MAX_SOURCES} sources")
    UserSourceRepo(ctx.conn).set_for(user.id, chosen)
    return SourcesResponse(sources=chosen, available=sorted(enabled),
                           max_allowed=_FREE_MAX_SOURCES)


# --- LLM keys (BYO) ---

@router.get("/keys", response_model=LLMKeysResponse)
def list_keys(ctx: RequestContext = Depends(get_ctx), user: User = Depends(current_user)):
    infos = LLMCredentialRepo(ctx.conn).list_for(user.id)
    return LLMKeysResponse(keys=[
        LLMKeyInfo(provider=i.provider, valid=i.valid, last_validated_at=i.last_validated_at)
        for i in infos
    ])


@router.put("/keys", response_model=LLMKeysResponse)
def put_key(body: LLMKeyRequest, ctx: RequestContext = Depends(get_ctx),
            user: User = Depends(current_user)):
    if body.provider not in _VALID_PROVIDERS:
        raise HTTPException(status.HTTP_400_BAD_REQUEST,
                            f"provider must be one of {sorted(_VALID_PROVIDERS)}")
    if ctx.container.vault is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE,
                            "BYO keys are not available (encryption not configured)")
    if not body.api_key.strip():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "api_key is empty")
    sealed = ctx.container.vault.seal(body.api_key.strip(), aad=user.id.encode())
    LLMCredentialRepo(ctx.conn).upsert(user.id, body.provider, sealed)
    return list_keys(ctx, user)


@router.delete("/keys/{provider}", response_model=LLMKeysResponse)
def delete_key(provider: str, ctx: RequestContext = Depends(get_ctx),
               user: User = Depends(current_user)):
    LLMCredentialRepo(ctx.conn).delete(user.id, provider)
    return list_keys(ctx, user)


# --- quota ---

@router.get("/quota", response_model=QuotaResponse)
def get_quota(ctx: RequestContext = Depends(get_ctx), user: User = Depends(current_user)):
    quota = QuotaService(conn=ctx.conn, settings=ctx.settings)
    byo = ctx.container.vault is not None and LLMCredentialRepo(ctx.conn).has_valid(user.id)
    metrics = []
    for metric in METRICS:
        s = quota.status(user, metric, unlimited=byo)
        metrics.append(QuotaMetric(metric=metric, limit=s.limit, used=s.used,
                                   remaining=s.remaining, unlimited=s.unlimited))
    return QuotaResponse(plan=user.plan, period=quota.period(), byo_key=byo,
                         metrics=metrics)


@router.delete("", response_model=MessageResponse)
def delete_account(ctx: RequestContext = Depends(get_ctx), user: User = Depends(current_user)):
    """GDPR-style self-service deletion: cascades to all the user's owned rows."""
    UserRepo(ctx.conn).delete(user.id)
    return MessageResponse(message="account deleted")


# --- push notifications ---

@router.post("/devices", response_model=MessageResponse)
def register_device(body: DeviceRegisterRequest, ctx: RequestContext = Depends(get_ctx),
                    user: User = Depends(current_user)):
    """Register (or refresh) this device's push token for the current user."""
    PushDeviceRepo(ctx.conn).register(user.id, body.token, body.platform)
    return MessageResponse(message="device registered")


@router.delete("/devices/{token}", response_model=MessageResponse)
def unregister_device(token: str, ctx: RequestContext = Depends(get_ctx),
                      user: User = Depends(current_user)):
    """Remove one of the user's device tokens (sign-out / notifications off)."""
    PushDeviceRepo(ctx.conn).unregister(user.id, token)
    return MessageResponse(message="device removed")


@router.get("/notifications", response_model=NotificationPrefsResponse)
def get_notification_prefs(ctx: RequestContext = Depends(get_ctx),
                           user: User = Depends(current_user)):
    prefs = NotificationPrefsRepo(ctx.conn).get(user.id)
    return NotificationPrefsResponse(match_alerts=prefs.match_alerts,
                                     min_score=prefs.min_score)


@router.put("/notifications", response_model=NotificationPrefsResponse)
def set_notification_prefs(body: NotificationPrefsRequest,
                           ctx: RequestContext = Depends(get_ctx),
                           user: User = Depends(current_user)):
    prefs = NotificationPrefsRepo(ctx.conn).upsert(
        user.id, match_alerts=body.match_alerts, min_score=body.min_score)
    return NotificationPrefsResponse(match_alerts=prefs.match_alerts,
                                     min_score=prefs.min_score)
