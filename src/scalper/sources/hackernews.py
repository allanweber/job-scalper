"""Hacker News "Who is hiring?" adapter — company-agnostic (ADR 0005).

Each month user `whoishiring` posts an "Ask HN: Who is hiring?" thread whose
top-level comments are individual job posts. This adapter finds the latest such
thread via the keyless Algolia API, pulls its comments, and treats each as a
posting:
    https://hn.algolia.com/api/v1/search_by_date?tags=story,author_whoishiring
    https://hn.algolia.com/api/v1/items/{story_id}

It's a *broad-feed* source: comments are free text, so we filter locally against
the query terms. Comment headers conventionally read "Company | Role | … |
Remote", which we parse best-effort; the full text is kept for scoring.
"""

from __future__ import annotations

import re

import httpx

from scalper.models import JobPosting, SearchQuery
from scalper.sources._util import looks_remote, matches_any_term, parse_epoch_s, strip_html
from scalper.sources.base import TIER_STRUCTURED, SourceAdapter, register

_SEARCH = "https://hn.algolia.com/api/v1/search_by_date"
_ITEM = "https://hn.algolia.com/api/v1/items/{id}"
_ITEM_URL = "https://news.ycombinator.com/item?id={id}"
_PARA = re.compile(r"<p>|</p>|<br\s*/?>", re.IGNORECASE)


@register
class HackerNewsAdapter(SourceAdapter):
    type = "hackernews"
    tier = TIER_STRUCTURED

    def __init__(self, timeout: float = 30.0):
        self.timeout = timeout

    @property
    def name(self) -> str:
        return "hackernews"

    def fetch(self, query: SearchQuery) -> list[JobPosting]:
        with httpx.Client(timeout=self.timeout, follow_redirects=True) as client:
            story_id = self._latest_thread(client)
            if story_id is None:
                return []
            story = client.get(_ITEM.format(id=story_id))
            story.raise_for_status()
            children = story.json().get("children", [])

        postings: list[JobPosting] = []
        for c in children:
            text = c.get("text")
            if c.get("type") != "comment" or not text:
                continue  # skip deleted/empty/non-comment nodes
            p = self._to_posting(c, text)
            if matches_any_term(f"{p.company} {p.title} {p.description}", query.terms):
                postings.append(p)
            if len(postings) >= query.limit_per_source:
                break
        return postings

    def _latest_thread(self, client: httpx.Client) -> int | None:
        resp = client.get(
            _SEARCH,
            params={"tags": "story,author_whoishiring", "query": "who is hiring", "hitsPerPage": 20},
        )
        resp.raise_for_status()
        for hit in resp.json().get("hits", []):
            title = (hit.get("title") or "").lower()
            if "who is hiring" in title:  # skip the sibling "who wants to be hired" thread
                return int(hit["objectID"])
        return None

    def _to_posting(self, comment: dict, text: str) -> JobPosting:
        # The header is the first paragraph; conventionally "Company | Role | …".
        header = strip_html(_PARA.split(text, 1)[0])
        parts = [s.strip() for s in header.split("|") if s.strip()]
        company = parts[0] if parts else ""
        title = parts[1] if len(parts) > 1 else (header[:120] or "Job posting")
        cid = str(comment.get("id"))
        full = strip_html(text)
        return JobPosting(
            source=self.name,
            source_id=cid,
            url=comment.get("url") or _ITEM_URL.format(id=cid),
            company=company,
            title=title,
            description=full,
            location=None,
            remote=looks_remote(header, full),
            published_at=parse_epoch_s(comment.get("created_at_i")),
            raw=comment,
        )
