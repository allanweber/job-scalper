"""System endpoints: health check + ToS/Privacy stubs (served publicly)."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from scalper.service.content_repos import PostingRepo
from scalper.service.deps import RequestContext, get_ctx
from scalper.service.schemas import LegalDoc, MessageResponse

router = APIRouter(tags=["system"])

_TOS_VERSION = "2026-07-01"
_PRIVACY_VERSION = "2026-07-01"

_TOS_BODY = (
    "By using Job Scalper you agree to use it for lawful personal job-seeking only. "
    "The service aggregates publicly available job postings and helps you tailor "
    "application materials. Generated resumes and cover letters are drafts for your "
    "review; you are responsible for their accuracy before sending. The service is "
    "provided as-is without warranty. We may suspend accounts that abuse the platform."
)
_PRIVACY_BODY = (
    "We store the Google account identity you sign in with, the resume you upload "
    "(treated as sensitive personal data), the search profile derived from it, and "
    "the drafts you generate. Personal LLM API keys are encrypted at rest. Job "
    "postings are shared, non-personal data. You can delete your account and all "
    "associated personal data at any time from the app (DELETE /me), which removes "
    "your resume, profile, drafts, and identity."
)


@router.get("/healthz", response_model=MessageResponse)
def healthz():
    return MessageResponse(message="ok")


@router.get("/readyz", response_model=MessageResponse)
def readyz(ctx: RequestContext = Depends(get_ctx)):
    # A trivial query proves the DB connection + schema are reachable.
    PostingRepo(ctx.conn).count()
    return MessageResponse(message="ready")


@router.get("/legal/tos", response_model=LegalDoc, tags=["legal"])
def tos():
    return LegalDoc(title="Terms of Service", version=_TOS_VERSION, body=_TOS_BODY)


@router.get("/legal/privacy", response_model=LegalDoc, tags=["legal"])
def privacy():
    return LegalDoc(title="Privacy Policy", version=_PRIVACY_VERSION, body=_PRIVACY_BODY)
