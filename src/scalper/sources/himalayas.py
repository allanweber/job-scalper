"""Himalayas adapter — search source using the /jobs/api/search endpoint.

Himalayas exposes a public, keyless search API:
    https://himalayas.app/jobs/api/search?q=<term>&page=<n>

This is a *search* source: each configured query term is searched independently
and results are unioned (OR across terms, deduped by guid). Passes
`worldwide=true` when the search query's remote flag is set, restricting to
globally-available positions.
"""

from __future__ import annotations

import httpx

from scalper.models import JobPosting, SearchQuery
from scalper.sources._util import parse_epoch_s, strip_html
from scalper.sources.base import TIER_STRUCTURED, SourceAdapter, register

_API = "https://himalayas.app/jobs/api/search"


@register
class HimalayasAdapter(SourceAdapter):
    type = "himalayas"
    tier = TIER_STRUCTURED

    def __init__(self, max_pages: int = 3, timeout: float = 30.0):
        self.max_pages = max_pages
        self.timeout = timeout

    @property
    def name(self) -> str:
        return "himalayas"

    def fetch(self, query: SearchQuery) -> list[JobPosting]:
        terms = query.terms or [""]
        seen: dict[str, JobPosting] = {}
        with self._client(timeout=self.timeout) as client:
            for term in terms:
                for page in range(1, self.max_pages + 1):
                    rows = self._search(client, term, page, query.remote)
                    if not rows:
                        break
                    for row in rows:
                        p = self._to_posting(row)
                        seen[p.source_id] = p
                    if len(seen) >= query.limit_per_source:
                        break
        return list(seen.values())[: query.limit_per_source]

    def _search(self, client: httpx.Client, term: str, page: int, remote: bool) -> list[dict]:
        params: dict[str, object] = {"page": page}
        if term:
            params["q"] = term
        if remote:
            params["worldwide"] = "true"
        resp = client.get(_API, params=params)
        resp.raise_for_status()
        return resp.json().get("jobs", [])

    def _to_posting(self, job: dict) -> JobPosting:
        locations = job.get("locationRestrictions") or []
        location = ", ".join(locations) or None
        salary_min = job.get("minSalary") or None
        salary_max = job.get("maxSalary") or None
        return JobPosting(
            source=self.name,
            source_id=str(job.get("guid") or job.get("applicationLink")),
            url=job.get("applicationLink", ""),
            company=(job.get("companyName") or "").strip(),
            title=(job.get("title") or "").strip(),
            description=strip_html(job.get("description", "")),
            location=location,
            remote=True,
            salary_min=float(salary_min) if salary_min else None,
            salary_max=float(salary_max) if salary_max else None,
            salary_currency=(job.get("currency") or None) if (salary_min or salary_max) else None,
            published_at=parse_epoch_s(job.get("pubDate")),
            raw=job,
        )
