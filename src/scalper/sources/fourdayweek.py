"""4dayweek.io adapter — free keyless JSON API.

4dayweek.io lists roles at companies offering 4-day work weeks. It covers many
software engineering positions and is remote-heavy. The API is fully public
with no auth and a 60-req/min rate limit:
    https://4dayweek.io/api/v2/jobs

Each query term is searched independently (server-side) and results are unioned.
"""

from __future__ import annotations

import httpx

from scalper.models import JobPosting, SearchQuery
from scalper.sources._util import parse_iso_dt, strip_html
from scalper.sources.base import TIER_STRUCTURED, SourceAdapter, register

_API = "https://4dayweek.io/api/v2/jobs"


@register
class FourDayWeekAdapter(SourceAdapter):
    type = "fourdayweek"
    tier = TIER_STRUCTURED

    def __init__(self, max_pages: int = 3, timeout: float = 30.0):
        self.max_pages = max_pages
        self.timeout = timeout

    @property
    def name(self) -> str:
        return "fourdayweek"

    def fetch(self, query: SearchQuery) -> list[JobPosting]:
        terms = query.terms or [""]
        seen: dict[str, JobPosting] = {}
        with self._client(timeout=self.timeout) as client:
            for term in terms:
                for page in range(1, self.max_pages + 1):
                    jobs, has_more = self._search(client, term, page, query)
                    for job in jobs:
                        p = self._to_posting(job)
                        seen[p.source_id] = p
                    if not has_more or len(seen) >= query.limit_per_source:
                        break
        return list(seen.values())[: query.limit_per_source]

    def _search(
        self, client: httpx.Client, term: str, page: int, query: SearchQuery
    ) -> tuple[list[dict], bool]:
        params: dict[str, object] = {
            "limit": min(100, query.limit_per_source),
            "page": page,
            "work_arrangement": "remote",
        }
        if term:
            params["search"] = term
        resp = client.get(_API, params=params)
        resp.raise_for_status()
        data = resp.json()
        return data.get("data", []), bool(data.get("has_more"))

    def _to_posting(self, job: dict) -> JobPosting:
        company = job.get("company") or {}
        locations = job.get("locations") or []
        location = (
            ", ".join(
                loc.get("city") or loc.get("country") or ""
                for loc in locations
                if loc.get("city") or loc.get("country")
            )
            or None
        )
        work_arr = (job.get("work_arrangement") or "").lower()
        return JobPosting(
            source=self.name,
            source_id=str(job.get("id") or job.get("slug")),
            url=job.get("url") or f"https://4dayweek.io/job/{job.get('slug', '')}",
            company=(company.get("name") if isinstance(company, dict) else "").strip(),
            title=(job.get("title") or "").strip(),
            description=strip_html(job.get("description", "")),
            location=location,
            remote=work_arr in ("remote", "hybrid") or not location,
            published_at=parse_iso_dt(job.get("posted_at")),
            raw=job,
        )
