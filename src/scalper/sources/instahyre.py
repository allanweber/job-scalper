"""Instahyre adapter — hard tier, Playwright.

Instahyre (https://www.instahyre.com) is a large India-focused tech hiring
platform. Its candidate search at ``/search-jobs`` is an AngularJS SPA that
pulls results from an authenticated JSON endpoint (``/api/v1/job_search`` →
``{"meta": ..., "objects": [...]}``), so there is no keyless public API to hit
directly. Like the other hard sources this is a best-effort, anonymous browser
scrape that fails soft: we render the page and extract whatever public data is
present — Schema.org JSON-LD when the page carries it, or an inlined ``objects``
array — and return nothing (never raise) when the site gates or changes.

If the structure changes, set ``SCALPER_DEBUG_HTML=./debug`` and rerun collect
to capture the actual rendered HTML for inspection.
"""

from __future__ import annotations

import hashlib
import json
import re
from urllib.parse import quote_plus

from scalper.models import JobPosting, SearchQuery
from scalper.sources._browser import BrowserSession, Fetcher, playwright_available
from scalper.sources._util import (
    jsonld_to_fields,
    looks_remote,
    matches_any_term,
    parse_iso_dt,
    parse_jsonld_jobs,
    strip_html,
)
from scalper.sources.base import TIER_HARD, SourceAdapter, register

_BASE = "https://www.instahyre.com/search-jobs"
_JOB_URL = "https://www.instahyre.com/job/{id}"


def _json_array_after(text: str, key: str) -> list | None:
    """Return the JSON array that follows ``"key":`` in `text`, or None.

    A brace/bracket-depth scan (string-aware) rather than a regex, so nested
    arrays and objects inside the ``objects`` payload don't truncate the match.
    """
    marker = f'"{key}"'
    at = text.find(marker)
    while at != -1:
        i = text.find("[", at + len(marker))
        colon = text.find(":", at + len(marker))
        # Only accept a '[' that is the value for this key (right after the colon).
        if i != -1 and colon != -1 and colon < i and text[colon + 1:i].strip() == "":
            depth, in_str, esc = 0, False, False
            for j in range(i, len(text)):
                c = text[j]
                if in_str:
                    if esc:
                        esc = False
                    elif c == "\\":
                        esc = True
                    elif c == '"':
                        in_str = False
                    continue
                if c == '"':
                    in_str = True
                elif c == "[":
                    depth += 1
                elif c == "]":
                    depth -= 1
                    if depth == 0:
                        try:
                            return json.loads(text[i:j + 1])
                        except (ValueError, TypeError):
                            return None
            return None
        at = text.find(marker, at + len(marker))
    return None


def parse_instahyre_page(html: str) -> list[dict]:
    """Extract job rows from a rendered Instahyre page.

    Prefers Schema.org JSON-LD (job-detail pages and some listings carry it);
    falls back to an inlined ``objects`` array (the search API's own shape).
    Each row is either a raw JSON-LD JobPosting dict or ``{"_raw": <api-row>}``.
    """
    jobs = parse_jsonld_jobs(html or "")
    if jobs:
        return jobs
    objects = _json_array_after(html or "", "objects")
    if isinstance(objects, list):
        rows = [o for o in objects if isinstance(o, dict) and _looks_like_job(o)]
        if rows:
            return [{"_raw": o} for o in rows]
    return []


def _looks_like_job(o: dict) -> bool:
    return any(k in o for k in ("job_title", "title", "position", "designation"))


@register
class InstahyreAdapter(SourceAdapter):
    type = "instahyre"
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
        return "instahyre"

    def fetch(self, query: SearchQuery) -> list[JobPosting]:
        if self._fetcher is not None:
            return self._collect(self._fetcher, query)
        if not playwright_available():
            print(
                "    instahyre: needs the [scrape] extra — "
                "pip install -e '.[scrape]' && playwright install chromium; skipping."
            )
            return []
        try:
            with BrowserSession(
                headless=self.headless, timeout=self.timeout, delay=self.delay, log=print
            ) as session:
                return self._collect(lambda u: session.get(u, wait_until="networkidle"), query)
        except Exception as exc:  # noqa: BLE001 — a hard source must never abort collect
            print(f"    instahyre: browser error ({type(exc).__name__}); skipping.")
            return []

    def _collect(self, get: Fetcher, query: SearchQuery) -> list[JobPosting]:
        seen: dict[str, JobPosting] = {}
        for term in query.terms or [""]:
            for page in range(1, self.max_pages + 1):
                html = get(self._search_url(term, page))
                if not html:
                    break
                rows = parse_instahyre_page(html)
                if not rows:
                    break
                for row in rows:
                    p = self._to_posting(row, query)
                    if p and matches_any_term(f"{p.title} {p.description}", query.terms):
                        seen.setdefault(p.uid, p)
                if len(seen) >= query.limit_per_source:
                    return list(seen.values())[: query.limit_per_source]
        return list(seen.values())[: query.limit_per_source]

    def _search_url(self, term: str, page: int) -> str:
        parts = []
        if term:
            parts.append(f"find_query={quote_plus(term)}")
        if page > 1:
            parts.append(f"page={page}")
        return f"{_BASE}?{'&'.join(parts)}" if parts else _BASE

    def _to_posting(self, row: dict, query: SearchQuery) -> JobPosting | None:
        if row.get("@type") == "JobPosting":
            f = jsonld_to_fields(row)
            if not f["title"]:
                return None
            url = f["url"]
            return JobPosting(
                source=self.name,
                source_id=hashlib.sha1(url.encode()).hexdigest()[:16] if url else f["title"],
                url=url,
                company=f["company"],
                title=f["title"],
                description=f["description"],
                location=f["location"],
                remote=f["remote"] or query.remote or looks_remote(f["location"]),
                salary_min=f["salary_min"],
                salary_max=f["salary_max"],
                salary_currency=f["salary_currency"],
                published_at=parse_iso_dt(f["published_at"]),
                raw=row,
            )
        raw = row.get("_raw") or {}
        title = (raw.get("job_title") or raw.get("title") or raw.get("position")
                 or raw.get("designation") or "").strip()
        if not title:
            return None
        emp = raw.get("employer") or raw.get("company") or {}
        company = (emp if isinstance(emp, str)
                   else (emp.get("company_name") or emp.get("name") or "")
                   if isinstance(emp, dict) else "").strip()
        company = company or (raw.get("company_name") or "").strip()
        job_id = raw.get("id") or raw.get("job_id") or ""
        url = (raw.get("public_url") or raw.get("url")
               or (_JOB_URL.format(id=job_id) if job_id else ""))
        loc = raw.get("locations") or raw.get("location") or raw.get("job_location")
        if isinstance(loc, list):
            loc = ", ".join(str(x) for x in loc if x) or None
        location = (loc or None) if isinstance(loc, str) else (loc or None)
        return JobPosting(
            source=self.name,
            source_id=str(job_id or hashlib.sha1((url or title).encode()).hexdigest()[:16]),
            url=url,
            company=company,
            title=title,
            description=strip_html(raw.get("job_description") or raw.get("description") or ""),
            location=location,
            remote=bool(raw.get("remote") or raw.get("is_remote")) or query.remote
            or looks_remote(location),
            published_at=parse_iso_dt(raw.get("created_at") or raw.get("posted_on")
                                      or raw.get("published_at")),
            raw=raw,
        )
