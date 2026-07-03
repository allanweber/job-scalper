"""Just Join IT adapter — hard tier, Playwright.

Just Join IT is the leading Central/Eastern European tech job board, with a
large volume of software engineering roles that include worldwide remote
positions. Their public REST API was retired; the site is now a React SPA.

Search URL: https://justjoin.it/job-offers/all/remote?search=<term>

Job data is extracted from Schema.org JSON-LD or the embedded Nuxt/React
application state. If the structure changes, set SCALPER_DEBUG_HTML=./debug
and rerun collect to capture the actual rendered HTML for inspection.
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

_BASE = "https://justjoin.it/job-offers/all/remote"

# Nuxt.js (Vue) apps embed their initial state here
_NUXT = re.compile(r'window\.__NUXT__\s*=\s*(\(.*?\))\s*;', re.DOTALL)
# Next.js apps use __NEXT_DATA__
_NEXTDATA = re.compile(r'<script id="__NEXT_DATA__"[^>]*>(\{.*?\})</script>', re.DOTALL)


def parse_justjoinit_page(html: str) -> list[dict]:
    """Extract job offers from a Just Join IT search results page."""
    jobs = parse_jsonld_jobs(html)
    if jobs:
        return jobs

    # Try Nuxt state (older site version)
    m = _NUXT.search(html or "")
    if m:
        try:
            # Nuxt wraps state in a self-executing function; eval-safe with json after stripping
            raw = m.group(1)
            # Attempt to extract the JSON object portion
            brace_start = raw.find("{")
            if brace_start >= 0:
                data = json.loads(raw[brace_start:raw.rfind("}") + 1])
                offers = (
                    data.get("data", [{}])[0].get("offers")
                    or data.get("offers")
                    or []
                )
                if offers:
                    return [{"_raw": o} for o in offers]
        except (json.JSONDecodeError, ValueError, IndexError, KeyError):
            pass

    # Try Next.js data
    m2 = _NEXTDATA.search(html or "")
    if m2:
        try:
            data = json.loads(m2.group(1))
            props = data.get("props", {}).get("pageProps", {})
            for key in ("offers", "jobs", "jobOffers", "results"):
                val = props.get(key)
                if isinstance(val, list):
                    return [{"_raw": o} for o in val]
        except (json.JSONDecodeError, ValueError, KeyError):
            pass

    return []


@register
class JustJoinITAdapter(SourceAdapter):
    type = "justjoinit"
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
        return "justjoinit"

    def fetch(self, query: SearchQuery) -> list[JobPosting]:
        if self._fetcher is not None:
            return self._collect(self._fetcher, query)
        if not playwright_available():
            print(
                "    justjoinit: needs the [scrape] extra — "
                "pip install -e '.[scrape]' && playwright install chromium; skipping."
            )
            return []
        try:
            with BrowserSession(
                headless=self.headless, timeout=self.timeout, delay=self.delay, log=print
            ) as session:
                return self._collect(lambda u: session.get(u, wait_until="networkidle"), query)
        except Exception as exc:  # noqa: BLE001
            print(f"    justjoinit: browser error ({type(exc).__name__}); skipping.")
            return []

    def _collect(self, get: Fetcher, query: SearchQuery) -> list[JobPosting]:
        seen: dict[str, JobPosting] = {}
        for term in query.terms or [""]:
            for page in range(1, self.max_pages + 1):
                html = get(self._search_url(term, page))
                if not html:
                    break
                cards = parse_justjoinit_page(html)
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
        params = f"?page={page}"
        if term:
            params += f"&search={quote_plus(term)}"
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
        title = (raw.get("title") or raw.get("offerTitle") or "").strip()
        if not title:
            return None
        company_obj = raw.get("companyName") or raw.get("company") or {}
        company = (
            company_obj if isinstance(company_obj, str)
            else (company_obj.get("name") or "") if isinstance(company_obj, dict)
            else ""
        ).strip()
        slug = raw.get("slug") or raw.get("id") or ""
        url = f"https://justjoin.it/offers/{slug}" if slug else ""
        job_id = str(slug or hashlib.sha1(url.encode()).hexdigest()[:16])
        location = raw.get("city") or raw.get("location") or raw.get("country") or None
        sal = raw.get("salary") or {}
        sal_min = sal_max = sal_cur = None
        if isinstance(sal, dict):
            sal_cur = sal.get("currency")
            sal_min = sal.get("from") or sal.get("min")
            sal_max = sal.get("to") or sal.get("max")
        elif isinstance(sal, list) and sal:
            first = sal[0]
            if isinstance(first, dict):
                sal_cur = first.get("currency")
                sal_min = first.get("from") or first.get("min")
                sal_max = first.get("to") or first.get("max")
        return JobPosting(
            source=self.name,
            source_id=job_id,
            url=url,
            company=company,
            title=title,
            description=strip_html(raw.get("body") or raw.get("description") or ""),
            location=location,
            remote=bool(raw.get("remote") or raw.get("workplaceType") == "remote") or query.remote,
            salary_min=float(sal_min) if sal_min is not None else None,
            salary_max=float(sal_max) if sal_max is not None else None,
            salary_currency=sal_cur,
            published_at=parse_iso_dt(raw.get("publishedAt") or raw.get("expirationDate")),
            raw=raw,
        )
