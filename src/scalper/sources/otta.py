"""Otta adapter — hard tier, Playwright.

Otta is a tech-focused job board covering software engineering roles across
Europe, the UK, US, and worldwide remote. It has no public API and runs a
React SPA backed by GraphQL.

The page embeds job data in a Next.js __NEXT_DATA__ blob or Schema.org JSON-LD.
Search URL: https://app.otta.com/jobs?searchText=<term>&workArrangement=FULLY_REMOTE

If the structure changes, set SCALPER_DEBUG_HTML=./debug and rerun collect.
"""

from __future__ import annotations

import hashlib
import json
import re
from urllib.parse import quote_plus

from scalper.models import JobPosting, SearchQuery
from scalper.sources._browser import BrowserSession, Fetcher, playwright_available
from scalper.sources._util import jsonld_to_fields, looks_remote, parse_iso_dt, parse_jsonld_jobs, strip_html
from scalper.sources.base import TIER_HARD, SourceAdapter, register

_BASE = "https://app.otta.com/jobs"

_NEXTDATA = re.compile(r'<script id="__NEXT_DATA__"[^>]*>(\{.*?\})</script>', re.DOTALL)


def _walk_for_jobs(obj: object, depth: int = 0) -> list[dict]:
    """Recursively walk a parsed JSON structure for arrays that look like job listings."""
    if depth > 6 or not isinstance(obj, (dict, list)):
        return []
    if isinstance(obj, list) and obj and isinstance(obj[0], dict) and (
        "title" in obj[0] or "jobTitle" in obj[0]
    ):
        return obj
    candidates: list[dict] = []
    items = obj.values() if isinstance(obj, dict) else obj
    for v in items:
        found = _walk_for_jobs(v, depth + 1)
        if found:
            candidates.extend(found)
    return candidates


def parse_otta_page(html: str) -> list[dict]:
    """Extract job entries from an Otta search results page."""
    jobs = parse_jsonld_jobs(html)
    if jobs:
        return jobs

    m = _NEXTDATA.search(html or "")
    if not m:
        return []
    try:
        data = json.loads(m.group(1))
    except (json.JSONDecodeError, ValueError):
        return []
    found = _walk_for_jobs(data)
    return [{"_raw": j} for j in found]


@register
class OttaAdapter(SourceAdapter):
    type = "otta"
    tier = TIER_HARD

    def __init__(
        self,
        max_pages: int = 2,
        delay: float = 3.0,
        timeout: float = 30.0,
        headless: bool = True,
        fetcher: Fetcher | None = None,
    ):
        self.max_pages = max_pages
        self.delay = delay
        self.timeout = timeout
        self.headless = headless
        self._fetcher = fetcher

    @property
    def name(self) -> str:
        return "otta"

    def fetch(self, query: SearchQuery) -> list[JobPosting]:
        if self._fetcher is not None:
            return self._collect(self._fetcher, query)
        if not playwright_available():
            print(
                "    otta: needs the [scrape] extra — "
                "pip install -e '.[scrape]' && playwright install chromium; skipping."
            )
            return []
        try:
            with BrowserSession(
                headless=self.headless, timeout=self.timeout, delay=self.delay, log=print
            ) as session:
                return self._collect(lambda u: session.get(u, wait_until="networkidle"), query)
        except Exception as exc:  # noqa: BLE001
            print(f"    otta: browser error ({type(exc).__name__}); skipping.")
            return []

    def _collect(self, get: Fetcher, query: SearchQuery) -> list[JobPosting]:
        seen: dict[str, JobPosting] = {}
        for term in query.terms or [""]:
            for page in range(1, self.max_pages + 1):
                html = get(self._search_url(term, page))
                if not html:
                    break
                cards = parse_otta_page(html)
                if not cards:
                    break
                for card in cards:
                    p = self._to_posting(card, query)
                    if p:
                        seen.setdefault(p.uid, p)
                if len(seen) >= query.limit_per_source:
                    return list(seen.values())[: query.limit_per_source]
        return list(seen.values())[: query.limit_per_source]

    def _search_url(self, term: str, page: int) -> str:
        params = "?workArrangement=FULLY_REMOTE"
        if term:
            params += f"&searchText={quote_plus(term)}"
        if page > 1:
            params += f"&page={page}"
        return f"{_BASE}{params}"

    def _to_posting(self, card: dict, query: SearchQuery) -> JobPosting | None:
        if card.get("@type") == "JobPosting":
            fields = jsonld_to_fields(card)
            if not fields["title"]:
                return None
            raw_url = fields["url"]
            return JobPosting(
                source=self.name,
                source_id=hashlib.sha1(raw_url.encode()).hexdigest()[:16] if raw_url else fields["title"],
                url=raw_url,
                company=fields["company"],
                title=fields["title"],
                description=fields["description"],
                location=fields["location"],
                remote=fields["remote"] or query.remote or looks_remote(fields["location"]),
                salary_min=fields["salary_min"],
                salary_max=fields["salary_max"],
                salary_currency=fields["salary_currency"],
                published_at=parse_iso_dt(fields["published_at"]),
                raw=card,
            )
        raw = card.get("_raw") or {}
        title = (raw.get("jobTitle") or raw.get("title") or raw.get("name") or "").strip()
        if not title:
            return None
        company_obj = raw.get("company") or raw.get("employer") or {}
        company = (company_obj.get("name") if isinstance(company_obj, dict) else str(company_obj)).strip()
        url = raw.get("url") or raw.get("externalUrl") or ""
        job_id = str(raw.get("id") or raw.get("externalId") or hashlib.sha1(url.encode()).hexdigest()[:16])
        location = raw.get("location") or raw.get("locationText") or None
        sal = raw.get("salary") or {}
        sal_min = sal.get("min") if isinstance(sal, dict) else None
        sal_max = sal.get("max") if isinstance(sal, dict) else None
        sal_cur = sal.get("currency") if isinstance(sal, dict) else None
        return JobPosting(
            source=self.name,
            source_id=job_id,
            url=url,
            company=company,
            title=title,
            description=strip_html(raw.get("description") or raw.get("summary") or ""),
            location=location,
            remote=bool(raw.get("remote") or raw.get("workArrangement") == "FULLY_REMOTE") or query.remote,
            salary_min=float(sal_min) if sal_min is not None else None,
            salary_max=float(sal_max) if sal_max is not None else None,
            salary_currency=sal_cur,
            published_at=parse_iso_dt(raw.get("publishedAt") or raw.get("created_at")),
            raw=raw,
        )
