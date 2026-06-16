"""LinkedIn adapter — 'hard' tier, anonymous guest endpoint only (Phase 4).

LinkedIn has no public jobs API, but its website backs an unauthenticated
*guest* search endpoint used to lazy-load result cards:

    https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search

It returns an HTML fragment of job cards — no login, no account, no cookies. We
fetch it through a headless browser (the endpoint rate-limits bare clients) as
an **anonymous visitor only**; the user's own LinkedIn credentials are never
used. This is a *search* source: terms are queried server-side and unioned.

This source is fragile by nature — LinkedIn changes its markup and throttles
aggressively. Parsing lives in pure module-level functions (testable offline
against a captured fragment), and every fetch fails soft: a block, a markup
change, or a missing `[scrape]` extra yields no postings rather than aborting
the collect run.
"""

from __future__ import annotations

import re
from urllib.parse import urlencode

from scalper.models import JobPosting, SearchQuery
from scalper.sources._browser import BrowserSession, Fetcher, playwright_available
from scalper.sources._util import looks_remote, parse_iso_dt, strip_html
from scalper.sources.base import TIER_HARD, SourceAdapter, register

_SEARCH = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
_PAGE_SIZE = 25  # the guest endpoint pages in blocks of 25

_JOB_ID = re.compile(r"urn:li:jobPosting:(\d+)")
_JOB_ID_URL = re.compile(r"/jobs/view/[^\"?]*?-(\d+)")
_DATETIME = re.compile(r'datetime="([^"]+)"')
_FULL_LINK = re.compile(r'base-card__full-link"[^>]*href="([^"]+)"')
_ANY_VIEW_LINK = re.compile(r'href="(https://[^"]*?/jobs/view/[^"]+)"')


def _between(chunk: str, pattern: str) -> str:
    """Return the cleaned text captured by `pattern` (DOTALL), or ''."""
    m = re.search(pattern, chunk, re.DOTALL)
    return strip_html(m.group(1)) if m else ""


def parse_search_cards(fragment: str) -> list[dict[str, str]]:
    """Parse a guest-search HTML fragment into a list of raw card dicts.

    Each `<li>` wraps one job card. We key on the `jobPosting` URN (falling back
    to the job id embedded in the view URL) and pull title/company/location/date
    by their stable CSS class names. Unparseable cards are skipped.
    """
    cards: list[dict[str, str]] = []
    for chunk in re.split(r"<li[ >]", fragment):
        m = _JOB_ID.search(chunk) or _JOB_ID_URL.search(chunk)
        if not m:
            continue
        link = _FULL_LINK.search(chunk) or _ANY_VIEW_LINK.search(chunk)
        url = (link.group(1).split("?")[0] if link else "").strip()
        date = _DATETIME.search(chunk)
        cards.append(
            {
                "job_id": m.group(1),
                "title": _between(chunk, r'base-search-card__title"[^>]*>(.*?)</h3>'),
                "company": _between(chunk, r'base-search-card__subtitle"[^>]*>(.*?)</h4>'),
                "location": _between(chunk, r'job-search-card__location"[^>]*>(.*?)</span>'),
                "url": url,
                "published": date.group(1) if date else "",
            }
        )
    return cards


@register
class LinkedInAdapter(SourceAdapter):
    type = "linkedin"
    tier = TIER_HARD

    def __init__(
        self,
        max_pages: int = 2,
        delay: float = 3.0,
        timeout: float = 30.0,
        headless: bool = True,
        user_data_dir: str | None = None,
        fetcher: Fetcher | None = None,
    ):
        # Pages of 25 to pull per search term (kept low — this is a polite,
        # low-frequency gap-filler, not a backbone source).
        self.max_pages = max_pages
        self.delay = delay
        self.timeout = timeout
        self.headless = headless
        # Optional persistent profile dir (reuses cookies across runs).
        self.user_data_dir = user_data_dir
        # Tests inject a fetcher to supply canned fragments with no browser.
        self._fetcher = fetcher

    @property
    def name(self) -> str:
        return "linkedin"

    def fetch(self, query: SearchQuery) -> list[JobPosting]:
        if self._fetcher is not None:
            return self._collect(self._fetcher, query)
        if not playwright_available():
            print(
                "    linkedin: needs the [scrape] extra — "
                "pip install -e '.[scrape]' && playwright install chromium; skipping."
            )
            return []
        try:
            with BrowserSession(
                headless=self.headless, timeout=self.timeout, delay=self.delay,
                user_data_dir=self.user_data_dir, log=print,
            ) as session:
                return self._collect(lambda u: session.get(u), query)
        except Exception as exc:  # noqa: BLE001 — hard source must never abort collect
            print(f"    linkedin: browser unavailable ({type(exc).__name__}); skipping.")
            return []

    def _collect(self, get: Fetcher, query: SearchQuery) -> list[JobPosting]:
        seen: dict[str, JobPosting] = {}
        remote_only = query.remote
        for term in query.terms or [""]:
            for page in range(self.max_pages):
                fragment = get(self._search_url(term, query, page * _PAGE_SIZE))
                if not fragment:
                    break
                cards = parse_search_cards(fragment)
                if not cards:
                    break
                for card in cards:
                    p = self._to_posting(card, remote_only)
                    seen.setdefault(p.uid, p)
                if len(seen) >= query.limit_per_source:
                    return list(seen.values())[: query.limit_per_source]
        return list(seen.values())[: query.limit_per_source]

    def _search_url(self, term: str, query: SearchQuery, start: int) -> str:
        params: dict[str, str | int] = {"keywords": term, "start": start}
        if query.location:
            params["location"] = query.location
        if query.remote:
            params["f_WT"] = 2  # LinkedIn's "Remote" workplace-type filter
        return f"{_SEARCH}?{urlencode(params)}"

    def _to_posting(self, card: dict[str, str], remote_only: bool) -> JobPosting:
        url = card.get("url") or f"https://www.linkedin.com/jobs/view/{card['job_id']}"
        location = card.get("location") or None
        return JobPosting(
            source=self.name,
            source_id=card["job_id"],
            url=url,
            company=card.get("company", ""),
            title=card.get("title", ""),
            description="",  # guest cards omit the body; scoring leans on the title
            location=location,
            remote=remote_only or looks_remote(location),
            published_at=parse_iso_dt(card.get("published")),
            raw=dict(card),
        )
