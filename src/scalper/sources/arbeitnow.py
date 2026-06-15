"""Arbeitnow adapter — company-agnostic job-board feed (ADR 0005).

Arbeitnow exposes a public, keyless, paginated JSON feed of jobs across all
employers:
    https://www.arbeitnow.com/api/job-board-api

It has no server-side keyword search, so this is a *broad-feed* source: it pulls
recent pages and filters locally against the user's query terms. The feed mixes
remote and on-site roles (many German), so when the query asks for remote we keep
only postings flagged `remote`.
"""

from __future__ import annotations

import httpx

from scalper.models import JobPosting, SearchQuery
from scalper.sources._util import matches_any_term, parse_epoch_s, strip_html
from scalper.sources.base import TIER_STRUCTURED, SourceAdapter, register

_API = "https://www.arbeitnow.com/api/job-board-api"


@register
class ArbeitnowAdapter(SourceAdapter):
    type = "arbeitnow"
    tier = TIER_STRUCTURED

    def __init__(self, max_pages: int = 10, timeout: float = 30.0):
        self.max_pages = max_pages
        self.timeout = timeout

    @property
    def name(self) -> str:
        return "arbeitnow"

    def fetch(self, query: SearchQuery) -> list[JobPosting]:
        postings: list[JobPosting] = []
        with httpx.Client(timeout=self.timeout, follow_redirects=True) as client:
            for page in range(1, self.max_pages + 1):
                rows = self._page(client, page)
                if not rows:
                    break
                for row in rows:
                    if query.remote and not row.get("remote"):
                        continue
                    p = self._to_posting(row)
                    haystack = f"{p.title} {p.description} {' '.join(row.get('tags') or [])}"
                    if matches_any_term(haystack, query.terms):
                        postings.append(p)
                    if len(postings) >= query.limit_per_source:
                        return postings
        return postings

    def _page(self, client: httpx.Client, page: int) -> list[dict]:
        resp = client.get(_API, params={"page": page})
        resp.raise_for_status()
        return resp.json().get("data", [])

    def _to_posting(self, job: dict) -> JobPosting:
        return JobPosting(
            source=self.name,
            source_id=str(job.get("slug")),
            url=job.get("url", ""),
            company=(job.get("company_name") or "").strip(),
            title=(job.get("title") or "").strip(),
            description=strip_html(job.get("description", "")),
            location=job.get("location") or None,
            remote=bool(job.get("remote")),
            published_at=parse_epoch_s(job.get("created_at")),
            raw=job,
        )
