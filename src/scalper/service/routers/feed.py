"""Feed endpoints: the user's ranked pool matches + seen/save actions (ADR 0011).

Users never scrape — this reads the shared pool the scheduler fills, filtered to
the user's chosen sources and scored against their profile.
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status

from scalper.service.content_repos import OverlayRepo, PostingRepo
from scalper.service.deps import RequestContext, current_user, get_ctx
from scalper.service.feed import FeedService
from scalper.service.models import User
from scalper.service.schemas import (
    FeedItemResponse,
    FeedMetaResponse,
    FeedResponse,
    MessageResponse,
)

router = APIRouter(prefix="/feed", tags=["feed"])


@router.get("", response_model=FeedResponse)
def get_feed(ctx: RequestContext = Depends(get_ctx), user: User = Depends(current_user),
             limit: int = Query(default=100, ge=1, le=500),
             min_score: int = Query(default=1, ge=0, le=100),
             sort: Literal["score", "newest"] = Query(default="score")):
    svc = FeedService(ctx.conn, ctx.settings)
    items = svc.build(user.id, limit=limit, min_score=min_score, sort=sort)
    meta = svc.meta(user.id)
    return FeedResponse(
        items=[FeedItemResponse(**item.__dict__) for item in items],
        count=len(items),
        meta=FeedMetaResponse(**meta.__dict__),
    )


def _require_posting(ctx: RequestContext, posting_id: str) -> None:
    if PostingRepo(ctx.conn).get(posting_id) is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "posting not found")


@router.post("/{posting_id}/seen", response_model=MessageResponse)
def mark_seen(posting_id: str, ctx: RequestContext = Depends(get_ctx),
              user: User = Depends(current_user)):
    _require_posting(ctx, posting_id)
    OverlayRepo(ctx.conn).mark_seen(user.id, posting_id)
    return MessageResponse(message="marked seen")


@router.post("/{posting_id}/save", response_model=MessageResponse)
def save(posting_id: str, ctx: RequestContext = Depends(get_ctx),
         user: User = Depends(current_user)):
    _require_posting(ctx, posting_id)
    OverlayRepo(ctx.conn).set_saved(user.id, posting_id, True)
    return MessageResponse(message="saved")


@router.delete("/{posting_id}/save", response_model=MessageResponse)
def unsave(posting_id: str, ctx: RequestContext = Depends(get_ctx),
           user: User = Depends(current_user)):
    _require_posting(ctx, posting_id)
    OverlayRepo(ctx.conn).set_saved(user.id, posting_id, False)
    return MessageResponse(message="unsaved")
