"""Draft + enrich endpoints (async jobs) and draft retrieval.

Drafting a tailored resume/cover letter and LLM-enriching a posting are heavy LLM
operations, so they return a `job_id` to poll (see /jobs). Quota is pre-checked
here for a fast 402 before enqueuing; the job consumes authoritatively.
"""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response

from scalper.service.content_repos import DraftRepo, JobRepo, OverlayRepo, PostingRepo
from scalper.service.deps import RequestContext, current_user, get_ctx
from scalper.service.jobs import KIND_DRAFT, KIND_ENRICH, JobQueue
from scalper.service.models import User
from scalper.service.quota import QuotaService
from scalper.service.repositories import LLMCredentialRepo
from scalper.service.schemas import (
    APPLICATION_STATUSES,
    AppliedRequest,
    ApplicationInsights,
    ApplicationStatusRequest,
    DraftRegenerateRequest,
    DraftRequest,
    DraftResponse,
    DraftSummary,
    DraftUpdateRequest,
    EnrichRequest,
    JobAccepted,
)


def _draft_response(d: "object", *, applied: bool = False,
                    application_status: str | None = None) -> DraftResponse:
    matched = []
    raw = getattr(d, "matched_skills", None)
    if raw:
        try:
            matched = list(json.loads(raw))
        except (ValueError, TypeError):
            matched = []
    return DraftResponse(
        id=d.id, posting_id=d.posting_id, job_source=d.job_source,
        resume_md=d.resume_md, cover_letter_md=d.cover_letter_md,
        stretch_claims_md=d.stretch_claims_md, provider=d.provider, model=d.model,
        key_source=d.key_source, created_at=d.created_at, applied=applied,
        application_status=application_status, status=d.status, error=d.error,
        tone=getattr(d, "tone", None), matched_skills=matched,
    )

router = APIRouter(tags=["drafts"])


def _overlay_state_for(
    ctx: RequestContext, user_id: str, posting_id: str | None
) -> tuple[bool, str | None]:
    """The user's (applied, application_status) for `posting_id` (overlay lookup).

    ``applied`` is derived from the applied timestamp; ``application_status`` is
    the pipeline stage (or None when not applied / no overlay row).
    """
    if not posting_id:
        return False, None
    ov = OverlayRepo(ctx.conn).get_many(user_id, [posting_id]).get(posting_id)
    if ov is None:
        return False, None
    return bool(ov.applied_at), ov.application_status


def _has_byo(ctx: RequestContext, user: User) -> bool:
    return ctx.container.vault is not None and LLMCredentialRepo(ctx.conn).has_valid(user.id)


def _precheck_quota(ctx: RequestContext, user: User, metric: str) -> None:
    quota = QuotaService(conn=ctx.conn, settings=ctx.settings)
    status_ = quota.check(user, metric, unlimited=_has_byo(ctx, user))
    if not status_.allowed:
        raise HTTPException(
            status.HTTP_402_PAYMENT_REQUIRED,
            f"monthly {metric} limit reached ({status_.used}/{status_.limit}); "
            "add a personal LLM key or wait for reset",
        )


@router.post("/drafts", response_model=DraftResponse, status_code=status.HTTP_201_CREATED,
             tags=["drafts"])
def create_draft(body: DraftRequest, ctx: RequestContext = Depends(get_ctx),
                 user: User = Depends(current_user)):
    """Create a draft and start generating it.

    A 'pending' draft row is created synchronously and returned immediately so
    the client can show it and navigate to it; the worker fills the content and
    flips the status to 'ready' (or 'failed'). The client polls GET /drafts/{id}.
    """
    if PostingRepo(ctx.conn).get(body.posting_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "posting not found in the pool")
    _precheck_quota(ctx, user, "draft")
    draft_id = DraftRepo(ctx.conn).create_pending(
        user.id, posting_id=body.posting_id, job_source="pool", tone=body.tone)
    JobQueue(ctx.container).enqueue(
        ctx.conn, KIND_DRAFT, user_id=user.id,
        params={"posting_id": body.posting_id, "draft_id": draft_id,
                "tone": body.tone})
    return _draft_response(DraftRepo(ctx.conn).get(draft_id, user.id), applied=False)


@router.post("/drafts/{draft_id}/regenerate", response_model=DraftResponse,
             status_code=status.HTTP_202_ACCEPTED, tags=["drafts"])
def regenerate_draft(draft_id: str, body: DraftRegenerateRequest,
                     ctx: RequestContext = Depends(get_ctx),
                     user: User = Depends(current_user)):
    """Re-draft an existing draft, optionally in a different tone.

    Puts the draft back to 'pending' and re-runs the LLM against the same posting
    (a fresh generation, so it consumes draft quota). The client polls
    GET /drafts/{id} as with a first draft.
    """
    d = DraftRepo(ctx.conn).get(draft_id, user.id)
    if d is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "draft not found")
    if not d.posting_id or PostingRepo(ctx.conn).get(d.posting_id) is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            "this draft's posting is no longer available to redraft")
    _precheck_quota(ctx, user, "draft")
    tone = body.tone if body.tone is not None else d.tone
    DraftRepo(ctx.conn).reset_pending(draft_id, user.id, tone=tone)
    JobQueue(ctx.container).enqueue(
        ctx.conn, KIND_DRAFT, user_id=user.id,
        params={"posting_id": d.posting_id, "draft_id": draft_id, "tone": tone})
    applied, app_status = _overlay_state_for(ctx, user.id, d.posting_id)
    return _draft_response(DraftRepo(ctx.conn).get(draft_id, user.id),
                           applied=applied, application_status=app_status)


@router.post("/enrich", response_model=JobAccepted, status_code=status.HTTP_202_ACCEPTED,
             tags=["feed"])
def enrich(body: EnrichRequest, ctx: RequestContext = Depends(get_ctx),
           user: User = Depends(current_user)):
    if PostingRepo(ctx.conn).get(body.posting_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "posting not found in the pool")
    # No pre-check here: enrich is free on a shared-cache hit and only consumes
    # quota on a real LLM call, so the job enforces the limit authoritatively
    # (a pre-check would wrongly block a user who'd get a cached result).
    job_id = JobQueue(ctx.container).enqueue(
        ctx.conn, KIND_ENRICH, user_id=user.id, params={"posting_id": body.posting_id})
    return JobAccepted(job_id=job_id, status=JobRepo(ctx.conn).get(job_id).status)


@router.get("/drafts", response_model=list[DraftSummary], tags=["drafts"])
def list_drafts(ctx: RequestContext = Depends(get_ctx), user: User = Depends(current_user)):
    return [
        DraftSummary(id=d.id, posting_id=d.posting_id, job_source=d.job_source,
                     key_source=d.key_source, created_at=d.created_at,
                     title=d.title, company=d.company, url=d.url, applied=d.applied,
                     application_status=d.application_status,
                     status=d.status, error=d.error)
        for d in DraftRepo(ctx.conn).list_summaries(user.id)
    ]


@router.get("/drafts/insights", response_model=ApplicationInsights, tags=["drafts"])
def application_insights(ctx: RequestContext = Depends(get_ctx),
                        user: User = Depends(current_user)):
    """Aggregate funnel of the user's applications for the Insights flow chart.

    Declared before ``/drafts/{draft_id}`` so the literal path wins over the
    parameter. Returns the total plus a count for every pipeline stage (zero
    when none), so the client can render the Sankey without post-processing.
    """
    total, counts = DraftRepo(ctx.conn).application_status_counts(user.id)
    full = {stage: counts.get(stage, 0) for stage in APPLICATION_STATUSES}
    return ApplicationInsights(total=total, counts=full)


@router.get("/drafts/{draft_id}", response_model=DraftResponse, tags=["drafts"])
def get_draft(draft_id: str, ctx: RequestContext = Depends(get_ctx),
              user: User = Depends(current_user)):
    d = DraftRepo(ctx.conn).get(draft_id, user.id)
    if d is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "draft not found")
    applied, app_status = _overlay_state_for(ctx, user.id, d.posting_id)
    return _draft_response(d, applied=applied, application_status=app_status)


@router.put("/drafts/{draft_id}/applied", response_model=DraftResponse, tags=["drafts"])
def set_draft_applied(draft_id: str, body: AppliedRequest,
                      ctx: RequestContext = Depends(get_ctx),
                      user: User = Depends(current_user)):
    """Manually mark this draft's posting as applied (or unmark it).

    "Applied" is per-posting user state on the overlay, so it shows up wherever
    the posting appears — feed, detail, saved — and on the Applications list.
    """
    d = DraftRepo(ctx.conn).get(draft_id, user.id)
    if d is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "draft not found")
    if d.posting_id is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            "this draft has no linked posting to mark applied")
    OverlayRepo(ctx.conn).set_applied(user.id, d.posting_id, body.applied)
    return _draft_response(d, applied=body.applied,
                           application_status="applied" if body.applied else None)


@router.put("/drafts/{draft_id}/status", response_model=DraftResponse, tags=["drafts"])
def set_draft_status(draft_id: str, body: ApplicationStatusRequest,
                     ctx: RequestContext = Depends(get_ctx),
                     user: User = Depends(current_user)):
    """Set this draft's application pipeline stage (or clear it).

    Stages advance applied → interviewing → offer, with rejected as an off-ramp;
    ``null`` clears back to not-applied. Like "applied", the stage is per-posting
    overlay state, so it's the source of truth for the applied flag everywhere
    the posting appears while the richer stage shows on the Applications surface.
    """
    d = DraftRepo(ctx.conn).get(draft_id, user.id)
    if d is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "draft not found")
    if d.posting_id is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            "this draft has no linked posting to track")
    OverlayRepo(ctx.conn).set_application_status(user.id, d.posting_id, body.status)
    return _draft_response(d, applied=body.status is not None,
                           application_status=body.status)


@router.put("/drafts/{draft_id}", response_model=DraftResponse, tags=["drafts"])
def update_draft(draft_id: str, body: DraftUpdateRequest,
                 ctx: RequestContext = Depends(get_ctx),
                 user: User = Depends(current_user)):
    d = DraftRepo(ctx.conn).update_content(
        draft_id, user.id, resume_md=body.resume_md,
        cover_letter_md=body.cover_letter_md)
    if d is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "draft not found")
    applied, app_status = _overlay_state_for(ctx, user.id, d.posting_id)
    return _draft_response(d, applied=applied, application_status=app_status)


@router.get("/drafts/{draft_id}/{which}.pdf", tags=["drafts"])
def get_draft_pdf(draft_id: str, which: str, ctx: RequestContext = Depends(get_ctx),
                  user: User = Depends(current_user)):
    import httpx
    if which not in {"resume", "cover_letter"}:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "unknown document")
    d = DraftRepo(ctx.conn).get(draft_id, user.id)
    if d is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "draft not found")
    md = d.resume_md if which == "resume" else d.cover_letter_md
    if not md or not md.strip():
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY,
                            "no content to render — edit the draft first")
    pdf_url = ctx.container.environ.get("PDF_SERVICE_URL", "http://pdf-service:8090")
    try:
        r = httpx.post(
            f"{pdf_url}/render",
            json={"markdown": md, "document_type": which, "template": "default"},
            timeout=10.0,
        )
        r.raise_for_status()
    except httpx.TimeoutException:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE,
                            "PDF service timed out — try again shortly")
    except Exception:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE,
                            "PDF service unavailable — try again shortly")
    return Response(content=r.content, media_type="application/pdf")
