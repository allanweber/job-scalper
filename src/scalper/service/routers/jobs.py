"""Job polling: clients GET a job by id to track async work to completion."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from scalper.service.content_repos import JobRepo
from scalper.service.deps import RequestContext, current_user, get_ctx
from scalper.service.models import User
from scalper.service.routers._helpers import job_response
from scalper.service.schemas import JobResponse

router = APIRouter(prefix="/jobs", tags=["jobs"])


@router.get("/{job_id}", response_model=JobResponse)
def get_job(job_id: str, ctx: RequestContext = Depends(get_ctx),
            user: User = Depends(current_user)):
    rec = JobRepo(ctx.conn).get(job_id)
    # Users can only see their own jobs (system jobs have no user_id).
    if rec is None or rec.user_id != user.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "job not found")
    return job_response(rec)
