"""Wellfound (formerly AngelList Talent) adapter — hard tier, Playwright.

Wellfound is one of the most prominent startup job boards, with a large volume
of software engineering roles including remote worldwide positions. It has no
public API, so we scrape the search page anonymously via headless browser.

Job data is embedded in the page as Schema.org JSON-LD for Google Jobs indexing.
If the structure changes, set SCALPER_DEBUG_HTML=./debug and rerun collect to
capture the actual HTML for inspection.
"""

from __future__ import annotations

import hashlib
import re
from urllib.parse import quote_plus

from scalper.models import JobPosting, SearchQuery
from scalper.sources._browser import BrowserSession, Fetcher, playwright_available
from scalper.sources._util import jsonld_to_fields, looks_remote, parse_jsonld_jobs, parse_iso_dt
from scalper.sources.base import TIER_HARD, SourceAdapter, register

_BASE = "https://wellfound.com/jobs"


def parse_wellfound_page(html: str) -> list[dict]:
    """Extract job cards from a Wellfound search results page.

    Tries Schema.org JSON-LD first (most reliable), then falls back to
    __NEXT_DATA__ traversal for the React/Next.js embedded state.
    """
    jobs = parse_jsonld_jobs(html)
    if jobs:
        return jobs

    # Fallback: Next.js embeds page props in __NEXT_DATA__
    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(\{.*?\})</script>', html, re.DOTALL)
    if not m:
        return []
    import json
    try:
        data = json.loads(m.group(1))
    except (json.JSONDecodeError, ValueError):
        return []

    # Traverse common paths where job arrays are nested in Wellfound's page props
    props = data.get("props", {}).get("pageProps", {})
    for key in ("jobs", "jobListings", "startupJobListings", "results"):
        val = props.get(key)
        if isinstance(val, list):
            return [{"_raw": j} for j in val]
        # One level deeper
        if isinstance(props, dict):
            for v in props.values():
                if isinstance(v, dict):
                    val = v.get(key)
                    if isinstance(val, list):
                        return [{"_raw": j} for j in val]
    return []


@register
class WellfoundAdapter(SourceAdapter):
    type = "wellfound"
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
        return "wellfound"

    def fetch(self, query: SearchQuery) -> list[JobPosting]:
        if self._fetcher is not None:
            return self._collect(self._fetcher, query)
        if not playwright_available():
            print(
                "    wellfound: needs the [scrape] extra — "
                "pip install -e '.[scrape]' && playwright install chromium; skipping."
            )
            return []
        try:
            with BrowserSession(
                headless=self.headless, timeout=self.timeout, delay=self.delay, log=print
            ) as session:
                return self._collect(lambda u: session.get(u, wait_until="networkidle"), query)
        except Exception as exc:  # noqa: BLE001
            print(f"    wellfound: browser error ({type(exc).__name__}); skipping.")
            return []

    def _collect(self, get: Fetcher, query: SearchQuery) -> list[JobPosting]:
        seen: dict[str, JobPosting] = {}
        for term in query.terms or [""]:
            for page in range(1, self.max_pages + 1):
                html = get(self._search_url(term, query, page))
                if not html:
                    break
                cards = parse_wellfound_page(html)
                if not cards:
                    break
                for card in cards:
                    p = self._to_posting(card, query)
                    if p:
                        seen.setdefault(p.uid, p)
                if len(seen) >= query.limit_per_source:
                    return list(seen.values())[: query.limit_per_source]
        return list(seen.values())[: query.limit_per_source]

    def _search_url(self, term: str, query: SearchQuery, page: int) -> str:
        params = f"?remote=true&page={page}"
        if term:
            params += f"&q={quote_plus(term)}"
        return f"{_BASE}{params}"

    def _to_posting(self, card: dict, query: SearchQuery) -> JobPosting | None:
        # JSON-LD path
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
        # __NEXT_DATA__ raw dict path
        raw = card.get("_raw") or {}
        title = (raw.get("title") or raw.get("name") or "").strip()
        if not title:
            return None
        company_obj = raw.get("startup") or raw.get("company") or {}
        company = (company_obj.get("name") if isinstance(company_obj, dict) else "").strip()
        url = raw.get("url") or raw.get("remote_url") or ""
        job_id = str(raw.get("id") or hashlib.sha1(url.encode()).hexdigest()[:16])
        location = raw.get("locationNames") or raw.get("location") or None
        if isinstance(location, list):
            location = ", ".join(location)
        return JobPosting(
            source=self.name,
            source_id=job_id,
            url=url,
            company=company,
            title=title,
            description=(raw.get("description") or "").strip(),
            location=location,
            remote=bool(raw.get("remote")) or query.remote or looks_remote(location),
            published_at=parse_iso_dt(raw.get("created_at") or raw.get("published_at")),
            raw=raw,
        )
