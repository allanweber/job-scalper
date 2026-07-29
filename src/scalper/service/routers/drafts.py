"""Draft + enrich endpoints (async jobs) and draft retrieval.

Drafting a tailored resume/cover letter and LLM-enriching a posting are heavy LLM
operations, so they return a `job_id` to poll (see /jobs). Quota is pre-checked
here for a fast 402 before enqueuing; the job consumes authoritatively.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response

from scalper.service.content_repos import DraftRepo, JobRepo, PostingRepo
from scalper.service.deps import RequestContext, current_user, get_ctx
from scalper.service.jobs import KIND_DRAFT, KIND_ENRICH, JobQueue
from scalper.service.models import User
from scalper.service.quota import QuotaService
from scalper.service.repositories import LLMCredentialRepo
from scalper.service.schemas import (
    DraftRequest,
    DraftResponse,
    DraftSummary,
    EnrichRequest,
    JobAccepted,
)

router = APIRouter(tags=["drafts"])


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


@router.post("/drafts", response_model=JobAccepted, status_code=status.HTTP_202_ACCEPTED,
             tags=["drafts"])
def create_draft(body: DraftRequest, ctx: RequestContext = Depends(get_ctx),
                 user: User = Depends(current_user)):
    if PostingRepo(ctx.conn).get(body.posting_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "posting not found in the pool")
    _precheck_quota(ctx, user, "draft")
    job_id = JobQueue(ctx.container).enqueue(
        ctx.conn, KIND_DRAFT, user_id=user.id, params={"posting_id": body.posting_id})
    return JobAccepted(job_id=job_id, status=JobRepo(ctx.conn).get(job_id).status)


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
                     key_source=d.key_source, created_at=d.created_at)
        for d in DraftRepo(ctx.conn).list_for(user.id)
    ]


@router.get("/drafts/{draft_id}", response_model=DraftResponse, tags=["drafts"])
def get_draft(draft_id: str, ctx: RequestContext = Depends(get_ctx),
              user: User = Depends(current_user)):
    d = DraftRepo(ctx.conn).get(draft_id, user.id)
    if d is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "draft not found")
    return DraftResponse(
        id=d.id, posting_id=d.posting_id, job_source=d.job_source,
        resume_md=d.resume_md, cover_letter_md=d.cover_letter_md,
        stretch_claims_md=d.stretch_claims_md, provider=d.provider, model=d.model,
        key_source=d.key_source, created_at=d.created_at,
    )


@router.get("/drafts/{draft_id}/{which}.pdf", tags=["drafts"])
def get_draft_pdf(draft_id: str, which: str, ctx: RequestContext = Depends(get_ctx),
                  user: User = Depends(current_user)):
    if which not in {"resume", "cover_letter"}:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "unknown document")
    pdf = DraftRepo(ctx.conn).get_pdf(draft_id, user.id, which)
    if pdf is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "no PDF for this draft")
    return Response(content=pdf, media_type="application/pdf")
