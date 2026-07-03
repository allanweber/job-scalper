"""Remote.co adapter — hard tier, Playwright.

Remote.co is a dedicated remote job board covering worldwide positions across
software engineering, design, and other disciplines. It is WordPress-based and
includes Schema.org JSON-LD in job listing pages.

Search results are at:
    https://remote.co/remote-jobs/search/?search_keywords=<term>

Job cards link to individual posting pages that carry JSON-LD. We parse the
search results page for card links/titles/companies and use JSON-LD where
available. If the structure changes, set SCALPER_DEBUG_HTML=./debug and rerun.
"""

from __future__ import annotations

import hashlib
import re
from urllib.parse import quote_plus

from scalper.models import JobPosting, SearchQuery
from scalper.sources._browser import BrowserSession, Fetcher, playwright_available
from scalper.sources._util import jsonld_to_fields, looks_remote, parse_iso_dt, parse_jsonld_jobs, strip_html
from scalper.sources.base import TIER_HARD, SourceAdapter, register

_SEARCH = "https://remote.co/remote-jobs/search/"

# WordPress job listing card patterns
_CARD = re.compile(r'<li[^>]+class="[^"]*job_listing[^"]*".*?</li>', re.DOTALL | re.IGNORECASE)
_TITLE = re.compile(r'<h3[^>]*>\s*<a[^>]+>(.*?)</a>', re.DOTALL)
_COMPANY = re.compile(r'class="[^"]*company[^"]*"[^>]*>(.*?)</(?:span|div|p)', re.DOTALL)
_LINK = re.compile(r'<a\s+href="(https?://[^"]+)"')
_DATE = re.compile(r'datetime="([^"]+)"')


def parse_remoteco_page(html: str) -> list[dict]:
    """Extract job cards from a Remote.co search results page."""
    # JSON-LD is present on individual listing pages; on the search page we get
    # card-level HTML. Try JSON-LD first (works if we land on a listing page).
    jobs = parse_jsonld_jobs(html)
    if jobs:
        return jobs

    # Parse WordPress job_listing cards from the search results HTML
    cards: list[dict] = []
    for m in _CARD.finditer(html):
        chunk = m.group(0)
        title_m = _TITLE.search(chunk)
        company_m = _COMPANY.search(chunk)
        link_m = _LINK.search(chunk)
        date_m = _DATE.search(chunk)
        title = strip_html(title_m.group(1)) if title_m else ""
        if not title:
            continue
        cards.append({
            "_raw": {
                "title": title,
                "company": strip_html(company_m.group(1)) if company_m else "",
                "url": link_m.group(1) if link_m else "",
                "date": date_m.group(1) if date_m else "",
            }
        })
    return cards


@register
class RemoteCoAdapter(SourceAdapter):
    type = "remoteco"
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
        return "remoteco"

    def fetch(self, query: SearchQuery) -> list[JobPosting]:
        if self._fetcher is not None:
            return self._collect(self._fetcher, query)
        if not playwright_available():
            print(
                "    remoteco: needs the [scrape] extra — "
                "pip install -e '.[scrape]' && playwright install chromium; skipping."
            )
            return []
        try:
            with BrowserSession(
                headless=self.headless, timeout=self.timeout, delay=self.delay, log=print
            ) as session:
                return self._collect(lambda u: session.get(u, wait_until="networkidle"), query)
        except Exception as exc:  # noqa: BLE001
            print(f"    remoteco: browser error ({type(exc).__name__}); skipping.")
            return []

    def _collect(self, get: Fetcher, query: SearchQuery) -> list[JobPosting]:
        seen: dict[str, JobPosting] = {}
        for term in query.terms or [""]:
            for page in range(1, self.max_pages + 1):
                html = get(self._search_url(term, page))
                if not html:
                    break
                cards = parse_remoteco_page(html)
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
        params = f"?pg={page}"
        if term:
            params += f"&search_keywords={quote_plus(term)}"
        return f"{_SEARCH}{params}"

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
        title = (raw.get("title") or "").strip()
        if not title:
            return None
        url = raw.get("url") or ""
        return JobPosting(
            source=self.name,
            source_id=hashlib.sha1(url.encode()).hexdigest()[:16] if url else title,
            url=url,
            company=(raw.get("company") or "").strip(),
            title=title,
            description="",
            location=None,
            remote=True,  # Remote.co is a remote-only board
            published_at=parse_iso_dt(raw.get("date")),
            raw=raw,
        )
