"""Draft + enrich endpoints (async jobs) and draft retrieval.

Drafting a tailored resume/cover letter and LLM-enriching a posting are heavy LLM
operations, so they return a `job_id` to poll (see /jobs). Quota is pre-checked
here for a fast 402 before enqueuing; the job consumes authoritatively.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response

from scalper.service.content_repos import DraftRepo, JobRepo, OverlayRepo, PostingRepo
from scalper.service.deps import RequestContext, current_user, get_ctx
from scalper.service.jobs import KIND_DRAFT, KIND_ENRICH, JobQueue
from scalper.service.models import User
from scalper.service.quota import QuotaService
from scalper.service.repositories import LLMCredentialRepo
from scalper.service.schemas import (
    AppliedRequest,
    DraftRequest,
    DraftResponse,
    DraftSummary,
    DraftUpdateRequest,
    EnrichRequest,
    JobAccepted,
)


def _draft_response(d: "object", *, applied: bool = False) -> DraftResponse:
    return DraftResponse(
        id=d.id, posting_id=d.posting_id, job_source=d.job_source,
        resume_md=d.resume_md, cover_letter_md=d.cover_letter_md,
        stretch_claims_md=d.stretch_claims_md, provider=d.provider, model=d.model,
        key_source=d.key_source, created_at=d.created_at, applied=applied,
        status=d.status, error=d.error,
    )

router = APIRouter(tags=["drafts"])


def _applied_for(ctx: RequestContext, user_id: str, posting_id: str | None) -> bool:
    """Whether the user has marked `posting_id` applied (overlay lookup)."""
    if not posting_id:
        return False
    ov = OverlayRepo(ctx.conn).get_many(user_id, [posting_id]).get(posting_id)
    return bool(ov and ov.applied_at)


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
        user.id, posting_id=body.posting_id, job_source="pool")
    JobQueue(ctx.container).enqueue(
        ctx.conn, KIND_DRAFT, user_id=user.id,
        params={"posting_id": body.posting_id, "draft_id": draft_id})
    return _draft_response(DraftRepo(ctx.conn).get(draft_id, user.id), applied=False)


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
                     status=d.status, error=d.error)
        for d in DraftRepo(ctx.conn).list_summaries(user.id)
    ]


@router.get("/drafts/{draft_id}", response_model=DraftResponse, tags=["drafts"])
def get_draft(draft_id: str, ctx: RequestContext = Depends(get_ctx),
              user: User = Depends(current_user)):
    d = DraftRepo(ctx.conn).get(draft_id, user.id)
    if d is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "draft not found")
    return _draft_response(d, applied=_applied_for(ctx, user.id, d.posting_id))


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
    return _draft_response(d, applied=body.applied)


@router.put("/drafts/{draft_id}", response_model=DraftResponse, tags=["drafts"])
def update_draft(draft_id: str, body: DraftUpdateRequest,
                 ctx: RequestContext = Depends(get_ctx),
                 user: User = Depends(current_user)):
    d = DraftRepo(ctx.conn).update_content(
        draft_id, user.id, resume_md=body.resume_md,
        cover_letter_md=body.cover_letter_md)
    if d is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "draft not found")
    return _draft_response(d)


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
