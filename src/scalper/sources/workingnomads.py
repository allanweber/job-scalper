"""Working Nomads adapter — company-agnostic remote-job feed .

Working Nomads exposes a public, keyless JSON endpoint of recent remote jobs
across all employers:
    https://www.workingnomads.com/api/exposed_jobs/

It has no server-side keyword search, so this is a *broad-feed* source: it pulls
the recent feed and filters locally against the user's query terms. The feed is
remote-only by nature. Tags arrive as a comma-separated string.
"""

from __future__ import annotations


from scalper.models import JobPosting, SearchQuery
from scalper.sources._util import matches_any_term, parse_iso_dt, strip_html
from scalper.sources.base import TIER_STRUCTURED, SourceAdapter, register

_API = "https://www.workingnomads.com/api/exposed_jobs/"
_UA = "job-scalper/0.1 (personal job-search tool; +https://www.workingnomads.com)"


@register
class WorkingNomadsAdapter(SourceAdapter):
    type = "workingnomads"
    tier = TIER_STRUCTURED

    def __init__(self, timeout: float = 30.0):
        self.timeout = timeout

    @property
    def name(self) -> str:
        return "workingnomads"

    def fetch(self, query: SearchQuery) -> list[JobPosting]:
        with self._client(timeout=self.timeout) as client:
            resp = client.get(_API, headers={"User-Agent": _UA, "Accept": "application/json"})
            resp.raise_for_status()
            rows = resp.json()

        postings: list[JobPosting] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            p = self._to_posting(row)
            haystack = f"{p.title} {p.description} {row.get('tags') or ''}"
            if matches_any_term(haystack, query.terms):
                postings.append(p)
            if len(postings) >= query.limit_per_source:
                break
        return postings

    def _to_posting(self, job: dict) -> JobPosting:
        url = job.get("url", "")
        return JobPosting(
            source=self.name,
            source_id=url or (job.get("title") or ""),  # feed has no stable id; url is unique
            url=url,
            company=(job.get("company_name") or "").strip(),
            title=(job.get("title") or "").strip(),
            description=strip_html(job.get("description", "")),
            location=job.get("location") or None,
            remote=True,  # Working Nomads is remote-only by definition
            published_at=parse_iso_dt(job.get("pub_date")),
            raw=job,
        )
