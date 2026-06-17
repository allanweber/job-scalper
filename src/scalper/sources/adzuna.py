"""Adzuna adapter — company-agnostic job-search API .

Adzuna aggregates listings from across the web behind an official search API:
    https://api.adzuna.com/v1/api/jobs/{country}/search/{page}?app_id=..&app_key=..&what=..

This is a *search* source: each query term is sent as `what` and results are
unioned (an OR across terms). Unlike the other backbone sources it needs a free
`app_id`/`app_key` (register at https://developer.adzuna.com). Keys are read from
config or the env vars `ADZUNA_APP_ID` / `ADZUNA_APP_KEY`. With no keys the
adapter fetches nothing and logs a hint, so `collect` never breaks.
"""

from __future__ import annotations

import os

import httpx

from scalper.models import JobPosting, SearchQuery
from scalper.sources._util import looks_remote, parse_iso_dt, strip_html
from scalper.sources.base import TIER_STRUCTURED, SourceAdapter, register

_API = "https://api.adzuna.com/v1/api/jobs/{country}/search/{page}"
# Adzuna salary figures are in the country's local currency.
_CURRENCY = {
    "gb": "GBP", "us": "USD", "ca": "CAD", "au": "AUD", "de": "EUR",
    "fr": "EUR", "nl": "EUR", "at": "EUR", "in": "INR", "br": "BRL",
}


@register
class AdzunaAdapter(SourceAdapter):
    type = "adzuna"
    tier = TIER_STRUCTURED

    def __init__(
        self,
        app_id: str | None = None,
        app_key: str | None = None,
        country: str = "gb",
        max_pages: int = 1,
        results_per_page: int = 50,
        remote_only: bool | None = None,
        timeout: float = 30.0,
    ):
        self.app_id = app_id or os.environ.get("ADZUNA_APP_ID")
        self.app_key = app_key or os.environ.get("ADZUNA_APP_KEY")
        self.country = country.lower()
        self.max_pages = max_pages
        self.results_per_page = results_per_page
        # If unset, follow the query's remote flag at fetch time.
        self.remote_only = remote_only
        self.timeout = timeout

    @property
    def name(self) -> str:
        return "adzuna"

    def fetch(self, query: SearchQuery) -> list[JobPosting]:
        if not (self.app_id and self.app_key):
            print(
                "    adzuna: skipped — no API keys. Set app_id/app_key in config "
                "or ADZUNA_APP_ID/ADZUNA_APP_KEY env vars (free at developer.adzuna.com)."
            )
            return []
        remote_only = self.remote_only if self.remote_only is not None else query.remote
        terms = query.terms or [""]
        seen: dict[str, JobPosting] = {}
        with self._client(timeout=self.timeout) as client:
            for term in terms:
                for page in range(1, self.max_pages + 1):
                    rows = self._search(client, term, page, query.limit_per_source)
                    if not rows:
                        break
                    for row in rows:
                        p = self._to_posting(row)
                        if remote_only and not p.remote:
                            continue
                        seen[p.source_id] = p  # union/dedup across terms by Adzuna id
                if len(seen) >= query.limit_per_source:
                    break
        return list(seen.values())[: query.limit_per_source]

    def _search(self, client: httpx.Client, term: str, page: int, limit: int) -> list[dict]:
        params: dict[str, object] = {
            "app_id": self.app_id,
            "app_key": self.app_key,
            "results_per_page": min(self.results_per_page, limit),
            "content-type": "application/json",
        }
        if term:
            params["what"] = term
        url = _API.format(country=self.country, page=page)
        resp = client.get(url, params=params)
        resp.raise_for_status()
        return resp.json().get("results", [])

    def _to_posting(self, job: dict) -> JobPosting:
        salary_min = job.get("salary_min") or None
        salary_max = job.get("salary_max") or None
        company = (job.get("company") or {}).get("display_name") or ""
        location = (job.get("location") or {}).get("display_name") or None
        title = strip_html(job.get("title") or "")
        description = strip_html(job.get("description") or "")
        return JobPosting(
            source=self.name,
            source_id=str(job.get("id")),
            url=job.get("redirect_url", ""),
            company=company.strip(),
            title=title,
            description=description,
            location=location,
            remote=looks_remote(title, description, location),
            salary_min=float(salary_min) if salary_min else None,
            salary_max=float(salary_max) if salary_max else None,
            salary_currency=_CURRENCY.get(self.country) if (salary_min or salary_max) else None,
            published_at=parse_iso_dt(job.get("created")),
            raw=job,
        )
