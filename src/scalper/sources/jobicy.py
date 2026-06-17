"""Jobicy adapter — company-agnostic remote-job search .

Jobicy exposes a public, keyless JSON API of remote jobs across all employers:
    https://jobicy.com/api/v2/remote-jobs?count=<n>&tag=<term>

This is a *search* source: it takes a `tag` keyword and returns matching remote
postings from any company. Each query term is sent as its own `tag` request and
the results are unioned (an OR across terms). Tag search is keyword-based, so it
works best with single-tech terms ("java", "python") — multi-word phrases match
little. Jobicy asks for attribution and infrequent polling.
"""

from __future__ import annotations

import httpx

from scalper.models import JobPosting, SearchQuery
from scalper.sources._util import parse_iso_dt, strip_html
from scalper.sources.base import TIER_STRUCTURED, SourceAdapter, register

_API = "https://jobicy.com/api/v2/remote-jobs"
_UA = "job-scalper/0.1 (personal job-search tool; +https://jobicy.com)"


@register
class JobicyAdapter(SourceAdapter):
    type = "jobicy"
    tier = TIER_STRUCTURED

    def __init__(self, geo: str | None = None, industry: str | None = None, timeout: float = 30.0):
        # Optional Jobicy filters (e.g. geo="usa", industry="dev"); usually unset.
        self.geo = geo
        self.industry = industry
        self.timeout = timeout

    @property
    def name(self) -> str:
        return "jobicy"

    def fetch(self, query: SearchQuery) -> list[JobPosting]:
        terms = query.terms or [""]  # empty tag => Jobicy returns its recent feed
        seen: dict[str, JobPosting] = {}
        with self._client(timeout=self.timeout) as client:
            for term in terms:
                for job in self._search(client, term, query.limit_per_source):
                    p = self._to_posting(job)
                    seen[p.source_id] = p  # union/dedup across terms by Jobicy id
        return list(seen.values())[: query.limit_per_source]  # cap the unioned total

    def _search(self, client: httpx.Client, term: str, limit: int) -> list[dict]:
        params: dict[str, object] = {"count": min(limit, 50)}  # API caps count at 50
        if term:
            params["tag"] = term
        if self.geo:
            params["geo"] = self.geo
        if self.industry:
            params["industry"] = self.industry
        resp = client.get(_API, params=params, headers={"User-Agent": _UA})
        resp.raise_for_status()
        return resp.json().get("jobs", [])

    def _to_posting(self, job: dict) -> JobPosting:
        return JobPosting(
            source=self.name,
            source_id=str(job.get("id")),
            url=job.get("url", ""),
            company=(job.get("companyName") or "").strip(),
            title=(job.get("jobTitle") or "").strip(),
            description=strip_html(job.get("jobDescription") or job.get("jobExcerpt", "")),
            location=job.get("jobGeo") or None,
            remote=True,  # Jobicy is remote-only by definition
            published_at=parse_iso_dt(job.get("pubDate")),
            raw=job,
        )
