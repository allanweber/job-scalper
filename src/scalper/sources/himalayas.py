"""Himalayas adapter — company-agnostic remote-job feed (ADR 0005).

Himalayas exposes a public, keyless, paginated JSON API of remote jobs across
all employers:
    https://himalayas.app/jobs/api?limit=<n>&offset=<n>

It has no server-side keyword search, so this is a *broad-feed* source: it pages
through recent postings and filters locally against the user's query terms. The
feed is remote-only by nature and exposes structured salary min/max + currency.
"""

from __future__ import annotations

import httpx

from scalper.models import JobPosting, SearchQuery
from scalper.sources._util import matches_any_term, parse_epoch_s, strip_html
from scalper.sources.base import TIER_STRUCTURED, SourceAdapter, register

_API = "https://himalayas.app/jobs/api"
_PAGE = 100  # API page size


@register
class HimalayasAdapter(SourceAdapter):
    type = "himalayas"
    tier = TIER_STRUCTURED

    def __init__(self, max_pages: int = 5, timeout: float = 30.0):
        self.max_pages = max_pages
        self.timeout = timeout

    @property
    def name(self) -> str:
        return "himalayas"

    def fetch(self, query: SearchQuery) -> list[JobPosting]:
        postings: list[JobPosting] = []
        with httpx.Client(timeout=self.timeout, follow_redirects=True) as client:
            for page in range(self.max_pages):
                rows = self._page(client, offset=page * _PAGE)
                if not rows:
                    break
                for row in rows:
                    p = self._to_posting(row)
                    cats = " ".join(row.get("categories") or [])
                    if matches_any_term(f"{p.title} {p.description} {cats}", query.terms):
                        postings.append(p)
                    if len(postings) >= query.limit_per_source:
                        return postings
        return postings

    def _page(self, client: httpx.Client, offset: int) -> list[dict]:
        resp = client.get(_API, params={"limit": _PAGE, "offset": offset})
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
            remote=True,  # Himalayas is remote-only by definition
            salary_min=float(salary_min) if salary_min else None,
            salary_max=float(salary_max) if salary_max else None,
            salary_currency=(job.get("currency") or None) if (salary_min or salary_max) else None,
            published_at=parse_epoch_s(job.get("pubDate")),
            raw=job,
        )
