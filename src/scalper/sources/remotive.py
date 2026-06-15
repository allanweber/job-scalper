"""Remotive adapter — company-agnostic remote-job search (ADR 0005).

Remotive exposes a public, keyless JSON API of remote jobs across all employers:
    https://remotive.com/api/remote-jobs?search=<term>&limit=<n>

This is a *search* source: it takes the user's query terms and returns matching
postings from any company — exactly what a job scalper needs. Each term is
queried independently and the results are unioned (an OR across terms).
"""

from __future__ import annotations

import httpx

from scalper.models import JobPosting, SearchQuery
from scalper.sources._util import parse_iso_dt, strip_html
from scalper.sources.base import TIER_STRUCTURED, SourceAdapter, register

_API = "https://remotive.com/api/remote-jobs"


@register
class RemotiveAdapter(SourceAdapter):
    type = "remotive"
    tier = TIER_STRUCTURED

    def __init__(self, category: str | None = None, timeout: float = 30.0):
        # Optional Remotive category filter (e.g. "software-dev"); usually unset.
        self.category = category
        self.timeout = timeout

    @property
    def name(self) -> str:
        return "remotive"

    def fetch(self, query: SearchQuery) -> list[JobPosting]:
        terms = query.terms or [""]  # empty term => Remotive returns its full feed
        seen: dict[str, JobPosting] = {}
        with httpx.Client(timeout=self.timeout, follow_redirects=True) as client:
            for term in terms:
                for job in self._search(client, term, query.limit_per_source):
                    p = self._to_posting(job)
                    seen[p.source_id] = p  # union/dedup across terms by Remotive id
        return list(seen.values())[: query.limit_per_source]  # cap the unioned total

    def _search(self, client: httpx.Client, term: str, limit: int) -> list[dict]:
        params: dict[str, object] = {"limit": limit}
        if term:
            params["search"] = term
        if self.category:
            params["category"] = self.category
        resp = client.get(_API, params=params)
        resp.raise_for_status()
        return resp.json().get("jobs", [])

    def _to_posting(self, job: dict) -> JobPosting:
        return JobPosting(
            source=self.name,
            source_id=str(job.get("id")),
            url=job.get("url", ""),
            company=(job.get("company_name") or "").strip(),
            title=(job.get("title") or "").strip(),
            description=strip_html(job.get("description", "")),
            location=job.get("candidate_required_location") or None,
            remote=True,  # Remotive is remote-only by definition
            published_at=parse_iso_dt(job.get("publication_date")),
            raw=job,
        )
