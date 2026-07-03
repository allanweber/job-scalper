"""Jobgether adapter — hard tier, Playwright.

Jobgether is a worldwide remote job board with strong software engineering
coverage and explicit remote-only filtering. It has no public API.

Search URL: https://jobgether.com/offers?search=<term>&flexible=remote

Job data is extracted from Schema.org JSON-LD or embedded JSON state.
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

_BASE = "https://jobgether.com/offers"

_NEXTDATA = re.compile(r'<script id="__NEXT_DATA__"[^>]*>(\{.*?\})</script>', re.DOTALL)
# Jobgether embeds its initial Apollo/GraphQL state in a window variable
_APOLLO = re.compile(r'window\.__APOLLO_STATE__\s*=\s*(\{.*?\});', re.DOTALL)


def parse_jobgether_page(html: str) -> list[dict]:
    """Extract job cards from a Jobgether search results page."""
    jobs = parse_jsonld_jobs(html)
    if jobs:
        return jobs

    for pattern in (_NEXTDATA, _APOLLO):
        m = pattern.search(html or "")
        if not m:
            continue
        try:
            data = json.loads(m.group(1))
        except (json.JSONDecodeError, ValueError):
            continue
        # Flatten Apollo cache objects that look like job postings
        results: list[dict] = []
        for obj in data.values() if isinstance(data, dict) else []:
            if isinstance(obj, dict) and (
                obj.get("__typename") in ("Offer", "Job", "JobPosting")
                or ("title" in obj and "company" in obj)
            ):
                results.append(obj)
        if results:
            return [{"_raw": r} for r in results]
    return []


@register
class JobgetherAdapter(SourceAdapter):
    type = "jobgether"
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
        return "jobgether"

    def fetch(self, query: SearchQuery) -> list[JobPosting]:
        if self._fetcher is not None:
            return self._collect(self._fetcher, query)
        if not playwright_available():
            print(
                "    jobgether: needs the [scrape] extra — "
                "pip install -e '.[scrape]' && playwright install chromium; skipping."
            )
            return []
        try:
            with BrowserSession(
                headless=self.headless, timeout=self.timeout, delay=self.delay, log=print
            ) as session:
                return self._collect(lambda u: session.get(u, wait_until="networkidle"), query)
        except Exception as exc:  # noqa: BLE001
            print(f"    jobgether: browser error ({type(exc).__name__}); skipping.")
            return []

    def _collect(self, get: Fetcher, query: SearchQuery) -> list[JobPosting]:
        seen: dict[str, JobPosting] = {}
        for term in query.terms or [""]:
            for page in range(1, self.max_pages + 1):
                html = get(self._search_url(term, page))
                if not html:
                    break
                cards = parse_jobgether_page(html)
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
        params = "?flexible=remote"
        if term:
            params += f"&search={quote_plus(term)}"
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
        title = (raw.get("title") or raw.get("name") or "").strip()
        if not title:
            return None
        company_obj = raw.get("company") or {}
        company = (company_obj.get("name") if isinstance(company_obj, dict) else str(company_obj)).strip()
        url = raw.get("url") or raw.get("offerUrl") or raw.get("applyUrl") or ""
        job_id = str(raw.get("id") or raw.get("slug") or hashlib.sha1(url.encode()).hexdigest()[:16])
        location = raw.get("location") or raw.get("locationText") or None
        return JobPosting(
            source=self.name,
            source_id=job_id,
            url=url,
            company=company,
            title=title,
            description=strip_html(raw.get("description") or raw.get("summary") or ""),
            location=location,
            remote=True,  # Jobgether is remote-only
            published_at=parse_iso_dt(raw.get("publishedAt") or raw.get("created_at")),
            raw=raw,
        )
