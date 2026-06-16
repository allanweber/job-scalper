"""RemoteOK adapter — company-agnostic remote-job feed .

RemoteOK exposes a single public JSON endpoint of recent remote jobs across all
employers:
    https://remoteok.com/api

It does not support server-side keyword search, so this is a *broad-feed*
source: it pulls the recent feed and filters locally against the user's query
terms. The first element of the response is a legal/metadata object, not a job.
RemoteOK asks for attribution and a descriptive User-Agent.
"""

from __future__ import annotations

import httpx

from scalper.models import JobPosting, SearchQuery
from scalper.sources._util import matches_any_term, parse_epoch_s, strip_html
from scalper.sources.base import TIER_STRUCTURED, SourceAdapter, register

_API = "https://remoteok.com/api"
_UA = "job-scalper/0.1 (personal job-search tool; +https://remoteok.com)"


@register
class RemoteOKAdapter(SourceAdapter):
    type = "remoteok"
    tier = TIER_STRUCTURED

    def __init__(self, timeout: float = 30.0):
        self.timeout = timeout

    @property
    def name(self) -> str:
        return "remoteok"

    def fetch(self, query: SearchQuery) -> list[JobPosting]:
        with httpx.Client(timeout=self.timeout, follow_redirects=True) as client:
            resp = client.get(_API, headers={"User-Agent": _UA, "Accept": "application/json"})
            resp.raise_for_status()
            rows = resp.json()

        postings: list[JobPosting] = []
        for row in rows:
            if not isinstance(row, dict) or "position" not in row:
                continue  # skip the leading legal/metadata element
            p = self._to_posting(row)
            haystack = f"{p.title} {p.description} {' '.join(row.get('tags') or [])}"
            if matches_any_term(haystack, query.terms):
                postings.append(p)
            if len(postings) >= query.limit_per_source:
                break
        return postings

    def _to_posting(self, job: dict) -> JobPosting:
        salary_min = job.get("salary_min") or None
        salary_max = job.get("salary_max") or None
        return JobPosting(
            source=self.name,
            source_id=str(job.get("id") or job.get("slug")),
            url=job.get("url", ""),
            company=(job.get("company") or "").strip(),
            title=(job.get("position") or "").strip(),
            description=strip_html(job.get("description", "")),
            location=job.get("location") or None,
            remote=True,  # RemoteOK is remote-only by definition
            salary_min=float(salary_min) if salary_min else None,
            salary_max=float(salary_max) if salary_max else None,
            salary_currency="USD" if (salary_min or salary_max) else None,
            published_at=parse_epoch_s(job.get("epoch")),
            raw=job,
        )
