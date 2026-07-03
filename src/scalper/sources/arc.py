"""Arc.dev adapter — hard tier, Playwright.

Arc.dev is a remote-first job board specifically for software developers, with
worldwide remote positions across engineering disciplines. It has no public API.

Job data is extracted from Schema.org JSON-LD embedded in the search results
page. If the structure changes, set SCALPER_DEBUG_HTML=./debug and rerun.
"""

from __future__ import annotations

import hashlib
import re
from urllib.parse import quote_plus

from scalper.models import JobPosting, SearchQuery
from scalper.sources._browser import BrowserSession, Fetcher, playwright_available
from scalper.sources._util import jsonld_to_fields, looks_remote, parse_iso_dt, parse_jsonld_jobs
from scalper.sources.base import TIER_HARD, SourceAdapter, register

_BASE = "https://arc.dev/remote-jobs"


def parse_arc_page(html: str) -> list[dict]:
    """Extract job cards from an Arc.dev search results page."""
    jobs = parse_jsonld_jobs(html)
    if jobs:
        return jobs

    # Fallback: look for embedded JSON state in script tags
    m = re.search(r'window\.__INITIAL_STATE__\s*=\s*(\{.*?\});', html, re.DOTALL)
    if not m:
        m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(\{.*?\})</script>', html, re.DOTALL)
    if not m:
        return []
    import json
    try:
        data = json.loads(m.group(1))
    except (json.JSONDecodeError, ValueError):
        return []

    # Walk common paths for job arrays
    for path in [["jobs"], ["results"], ["props", "pageProps", "jobs"]]:
        node: object = data
        for key in path:
            if isinstance(node, dict):
                node = node.get(key)
            else:
                break
        if isinstance(node, list):
            return [{"_raw": j} for j in node]
    return []


@register
class ArcAdapter(SourceAdapter):
    type = "arc"
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
        return "arc"

    def fetch(self, query: SearchQuery) -> list[JobPosting]:
        if self._fetcher is not None:
            return self._collect(self._fetcher, query)
        if not playwright_available():
            print(
                "    arc: needs the [scrape] extra — "
                "pip install -e '.[scrape]' && playwright install chromium; skipping."
            )
            return []
        try:
            with BrowserSession(
                headless=self.headless, timeout=self.timeout, delay=self.delay, log=print
            ) as session:
                return self._collect(lambda u: session.get(u, wait_until="networkidle"), query)
        except Exception as exc:  # noqa: BLE001
            print(f"    arc: browser error ({type(exc).__name__}); skipping.")
            return []

    def _collect(self, get: Fetcher, query: SearchQuery) -> list[JobPosting]:
        seen: dict[str, JobPosting] = {}
        for term in query.terms or [""]:
            for page in range(1, self.max_pages + 1):
                html = get(self._search_url(term, page))
                if not html:
                    break
                cards = parse_arc_page(html)
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
        title = (raw.get("title") or raw.get("name") or "").strip()
        if not title:
            return None
        company_obj = raw.get("company") or {}
        company = (company_obj.get("name") if isinstance(company_obj, dict) else str(company_obj)).strip()
        url = raw.get("url") or raw.get("apply_url") or raw.get("job_url") or ""
        job_id = str(raw.get("id") or raw.get("slug") or hashlib.sha1(url.encode()).hexdigest()[:16])
        location = raw.get("location") or raw.get("locationNames") or None
        if isinstance(location, list):
            location = ", ".join(str(l) for l in location)
        return JobPosting(
            source=self.name,
            source_id=job_id,
            url=url,
            company=company,
            title=title,
            description=(raw.get("description") or "").strip(),
            location=location,
            remote=bool(raw.get("remote") or raw.get("is_remote")) or query.remote,
            published_at=parse_iso_dt(raw.get("published_at") or raw.get("created_at")),
            raw=raw,
        )
