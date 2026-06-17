"""The Muse adapter — company-agnostic job-board feed.

The Muse exposes a public, keyless, paginated JSON API of jobs across all
employers:
    https://www.themuse.com/api/public/jobs?category=Software%20Engineering&page=<n>

When the search query's remote flag is set we pass `location=Flexible / Remote`
to filter server-side rather than locally, which dramatically improves precision.
The feed still has no free-text keyword search, so results are filtered locally
against the query terms after fetching.
"""

from __future__ import annotations

import httpx

from scalper.models import JobPosting, SearchQuery
from scalper.sources._util import looks_remote, matches_any_term, parse_iso_dt, strip_html
from scalper.sources.base import TIER_STRUCTURED, SourceAdapter, register

_API = "https://www.themuse.com/api/public/jobs"
_DEFAULT_CATEGORIES = ("Software Engineering", "Data Science", "IT")
_REMOTE_LOCATION = "Flexible / Remote"


@register
class TheMuseAdapter(SourceAdapter):
    type = "themuse"
    tier = TIER_STRUCTURED

    def __init__(self, categories: list[str] | None = None, max_pages: int = 5, timeout: float = 30.0):
        self.categories = categories or list(_DEFAULT_CATEGORIES)
        self.max_pages = max_pages
        self.timeout = timeout

    @property
    def name(self) -> str:
        return "themuse"

    def fetch(self, query: SearchQuery) -> list[JobPosting]:
        seen: dict[str, JobPosting] = {}
        with self._client(timeout=self.timeout) as client:
            for page in range(1, self.max_pages + 1):
                rows = self._page(client, page, remote=query.remote)
                if not rows:
                    break
                for row in rows:
                    p = self._to_posting(row)
                    if matches_any_term(f"{p.title} {p.description}", query.terms):
                        seen[p.source_id] = p
                if len(seen) >= query.limit_per_source:
                    break
        return list(seen.values())[: query.limit_per_source]

    def _page(self, client: httpx.Client, page: int, *, remote: bool = False) -> list[dict]:
        params: list[tuple[str, object]] = [("page", page)]
        params += [("category", c) for c in self.categories]
        if remote:
            params.append(("location", _REMOTE_LOCATION))
        resp = client.get(_API, params=params)
        resp.raise_for_status()
        return resp.json().get("results", [])

    def _to_posting(self, job: dict) -> JobPosting:
        locations = [loc.get("name", "") for loc in (job.get("locations") or [])]
        location = ", ".join(filter(None, locations)) or None
        company = (job.get("company") or {}).get("name") or ""
        url = (job.get("refs") or {}).get("landing_page") or ""
        return JobPosting(
            source=self.name,
            source_id=str(job.get("id")),
            url=url,
            company=company.strip(),
            title=(job.get("name") or "").strip(),
            description=strip_html(job.get("contents", "")),
            location=location,
            remote=looks_remote(location, *locations),
            published_at=parse_iso_dt(job.get("publication_date")),
            raw=job,
        )
