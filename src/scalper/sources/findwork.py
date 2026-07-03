"""Findwork.dev adapter — REST API for tech remote jobs (free key required).

Findwork aggregates remote tech jobs and exposes a paginated REST API:
    https://findwork.dev/api/jobs/?remote=true&search=<term>
    Authorization: Token <api_key>

Get a free key at https://findwork.dev/register. Without a key the adapter
skips silently. Note: Findwork aggregates from sources already in this tool
(RemoteOK, We Work Remotely), so overlap with those sources is expected.
"""

from __future__ import annotations

import httpx

from scalper.models import JobPosting, SearchQuery
from scalper.sources._util import parse_iso_dt, strip_html
from scalper.sources.base import TIER_STRUCTURED, SourceAdapter, register

_API = "https://findwork.dev/api/jobs/"


@register
class FindworkAdapter(SourceAdapter):
    type = "findwork"
    tier = TIER_STRUCTURED

    def __init__(self, api_key: str = "", timeout: float = 30.0):
        self.api_key = api_key
        self.timeout = timeout

    @property
    def name(self) -> str:
        return "findwork"

    def fetch(self, query: SearchQuery) -> list[JobPosting]:
        if not self.api_key:
            print("    findwork: no api_key configured; skipping.")
            return []
        terms = query.terms or [""]
        seen: dict[str, JobPosting] = {}
        headers = {"Authorization": f"Token {self.api_key}"}
        with self._client(timeout=self.timeout) as client:
            for term in terms:
                url: str | None = _API
                first = True
                while url and len(seen) < query.limit_per_source:
                    try:
                        if first:
                            params: dict[str, object] = {"remote": "true"}
                            if term:
                                params["search"] = term
                            resp = client.get(url, headers=headers, params=params)
                            first = False
                        else:
                            resp = client.get(url, headers=headers)
                        resp.raise_for_status()
                    except httpx.HTTPStatusError as exc:
                        print(f"    findwork: HTTP {exc.response.status_code}; skipping.")
                        return list(seen.values())[: query.limit_per_source]
                    data = resp.json()
                    for job in data.get("results", []):
                        p = self._to_posting(job)
                        seen[p.source_id] = p
                    url = data.get("next")
        return list(seen.values())[: query.limit_per_source]

    def _to_posting(self, job: dict) -> JobPosting:
        return JobPosting(
            source=self.name,
            source_id=str(job.get("id")),
            url=job.get("url", ""),
            company=(job.get("company_name") or "").strip(),
            title=(job.get("role") or "").strip(),
            description=strip_html(job.get("text", "")),
            location=job.get("location") or None,
            remote=bool(job.get("remote")),
            published_at=parse_iso_dt(job.get("date_posted")),
            raw=job,
        )
