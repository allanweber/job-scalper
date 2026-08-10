"""Posting detail + acquisition endpoints.

`GET /postings/{id}` returns a single pool posting's full text and the requesting
user's match breakdown — the feed list omits the description to stay light, so the
mobile detail screen fetches it here. `POST /import/url` fetches, parses, scores,
and pools an arbitrary job URL (SSRF-hardened) so a user can pull in a posting the
scheduler hasn't collected.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from scalper.service.content_repos import PostingRepo
from scalper.service.deps import RequestContext, current_user, get_ctx
from scalper.service.feed import FeedService
from scalper.service.models import User
from scalper.service.schemas import (
    ImportTextRequest,
    ImportUrlRequest,
    PostingDetailResponse,
)
from scalper.service.url_import import (
    UrlImportError,
    import_posting_from_text,
    import_posting_from_url,
)

router = APIRouter(tags=["postings"])


def _detail_response(ctx: RequestContext, user: User, posting_id: str) -> PostingDetailResponse:
    posting = PostingRepo(ctx.conn).get(posting_id)
    if posting is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "posting not found")
    detail = FeedService(ctx.conn, ctx.settings).detail(user.id, posting)
    return PostingDetailResponse(**detail.__dict__)


@router.get("/postings/{posting_id}", response_model=PostingDetailResponse)
def get_posting(posting_id: str, ctx: RequestContext = Depends(get_ctx),
                user: User = Depends(current_user)):
    return _detail_response(ctx, user, posting_id)


@router.post("/import/url", response_model=PostingDetailResponse,
             status_code=status.HTTP_201_CREATED)
def import_url(body: ImportUrlRequest, ctx: RequestContext = Depends(get_ctx),
               user: User = Depends(current_user)):
    try:
        posting_id = import_posting_from_url(
            ctx.conn, str(body.url), fetcher=ctx.container.url_fetcher)
    except UrlImportError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e)) from e
    return _detail_response(ctx, user, posting_id)


@router.post("/import/text", response_model=PostingDetailResponse,
             status_code=status.HTTP_201_CREATED)
def import_text(body: ImportTextRequest, ctx: RequestContext = Depends(get_ctx),
                user: User = Depends(current_user)):
    try:
        posting_id = import_posting_from_text(
            ctx.conn, body.text, title=body.title, company=body.company,
            url=str(body.url) if body.url else None)
    except UrlImportError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e)) from e
    return _detail_response(ctx, user, posting_id)
