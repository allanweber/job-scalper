"""Indeed adapter — 'hard' tier, Cloudflare-aware, anonymous only (Phase 4).

Indeed has no open API and sits behind Cloudflare, so a real headless browser is
needed to reach the public search results page. We browse **anonymously — never
the user's account** — at low frequency, and treat the source as a fragile
gap-filler.

Indeed renders its result cards from a JSON blob embedded in the page:

    window.mosaic.providerData["mosaic-provider-jobcards"] = { ... }

…whose `metaData.mosaicProviderJobCardsModel.results` array holds the postings.
We extract and parse that blob (isolated, offline-testable functions). If the
page is a Cloudflare challenge, the markup changed, or the `[scrape]` extra is
absent, the fetch fails soft and contributes nothing — the collect run goes on.
"""

from __future__ import annotations

import json
import re
from urllib.parse import urlencode

from scalper.models import JobPosting, SearchQuery
from scalper.sources._browser import BrowserSession, Fetcher, playwright_available
from scalper.sources._util import looks_remote, parse_epoch_ms, strip_html
from scalper.sources.base import TIER_HARD, SourceAdapter, register

# The job-card blob is assigned as `…providerData["mosaic-provider-jobcards"]={…}`.
# Anchor on the assignment itself: the bare key also appears in an array of
# provider names elsewhere on the page, and matching that decoy grabs the wrong
# JSON object (and zero results).
_JOBCARDS_ASSIGN = re.compile(r'mosaic-provider-jobcards"\]\s*=\s*')
# Phrases that mark a Cloudflare interstitial rather than real results. These
# only appear on an actual challenge page — NOT the "/cdn-cgi/challenge-platform"
# script Cloudflare injects into every page it fronts (including successful ones),
# which previously false-positived real result pages as blocked.
_CHALLENGE = re.compile(
    r"just a moment"
    r"|cf-chl"  # _cf_chl_opt / cf-chl-bypass tokens on real challenge pages
    r"|cf-challenge"
    r"|challenge-error"
    r"|verifying you are human"
    r"|enable javascript and cookies to continue",
    re.IGNORECASE,
)


def _extract_json_object(text: str, start: int) -> str | None:
    """Return the brace-balanced JSON object beginning at/after `start`, or None.

    A regex can't match nested braces, so we scan for the matching close brace,
    respecting string literals and escapes.
    """
    i = text.find("{", start)
    if i < 0:
        return None
    depth = 0
    in_str = esc = False
    for j in range(i, len(text)):
        ch = text[j]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
        elif ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[i : j + 1]
    return None


def is_challenge_page(page_html: str) -> bool:
    """True if the page looks like a Cloudflare challenge rather than results."""
    return bool(_CHALLENGE.search(page_html or ""))


def parse_jobcards(page_html: str) -> list[dict]:
    """Pull the embedded job-card result objects out of an Indeed results page.

    Returns [] for a challenge page, a missing blob, or unparseable JSON — the
    caller treats an empty list as "nothing this run", never an error.
    """
    if not page_html or is_challenge_page(page_html):
        return []
    m = _JOBCARDS_ASSIGN.search(page_html)
    if m is None:
        return []
    blob = _extract_json_object(page_html, m.end())
    if not blob:
        return []
    try:
        data = json.loads(blob)
        results = data["metaData"]["mosaicProviderJobCardsModel"]["results"]
    except (json.JSONDecodeError, KeyError, TypeError):
        return []
    return [r for r in results if isinstance(r, dict)]


@register
class IndeedAdapter(SourceAdapter):
    type = "indeed"
    tier = TIER_HARD

    def __init__(
        self,
        domain: str = "www.indeed.com",
        max_pages: int = 1,
        delay: float = 4.0,
        timeout: float = 45.0,
        headless: bool = True,
        user_data_dir: str | None = None,
        challenge_wait: float | None = None,
        fetcher: Fetcher | None = None,
    ):
        # Country domain (www.indeed.com, ca.indeed.com, …). One page by default
        # — Indeed is the most hostile source here, so we stay light and polite.
        self.domain = domain
        self.max_pages = max_pages
        self.delay = delay
        self.timeout = timeout
        self.headless = headless
        # A persistent profile dir keeps a cleared challenge's cookies between
        # runs; pair with headless=false to solve an interactive challenge by hand.
        self.user_data_dir = user_data_dir
        # Seconds to wait for a challenge to clear. Default: none when headless
        # (passive challenges still get the wait_selector window), but give a
        # human two minutes when a visible window is shown.
        if challenge_wait is None:
            challenge_wait = 0.0 if headless else 120.0
        self.challenge_wait = challenge_wait
        # Tests inject a fetcher to supply a canned page with no browser.
        self._fetcher = fetcher

    @property
    def name(self) -> str:
        return "indeed"

    def fetch(self, query: SearchQuery) -> list[JobPosting]:
        if self._fetcher is not None:
            return self._collect(self._fetcher, query)
        if not playwright_available():
            print(
                "    indeed: needs the [scrape] extra — "
                "pip install -e '.[scrape]' && playwright install chromium; skipping."
            )
            return []
        try:
            with BrowserSession(
                headless=self.headless, timeout=self.timeout, delay=self.delay,
                user_data_dir=self.user_data_dir, challenge_timeout=self.challenge_wait,
                log=print,
            ) as session:
                get = lambda u: session.get(  # noqa: E731
                    u, wait_selector="#mosaic-provider-jobcards",
                    is_blocked=is_challenge_page,
                )
                return self._collect(get, query)
        except Exception as exc:  # noqa: BLE001 — hard source must never abort collect
            print(f"    indeed: browser unavailable ({type(exc).__name__}); skipping.")
            return []

    def _collect(self, get: Fetcher, query: SearchQuery) -> list[JobPosting]:
        seen: dict[str, JobPosting] = {}
        for term in query.terms or [""]:
            for page in range(self.max_pages):
                page_html = get(self._search_url(term, query, page * 10))
                if page_html and is_challenge_page(page_html):
                    print("    indeed: blocked by a challenge page; skipping.")
                    break
                cards = parse_jobcards(page_html or "")
                if not cards:
                    break
                for card in cards:
                    p = self._to_posting(card, query)
                    if p is not None:
                        seen.setdefault(p.uid, p)
                if len(seen) >= query.limit_per_source:
                    return list(seen.values())[: query.limit_per_source]
        return list(seen.values())[: query.limit_per_source]

    def _search_url(self, term: str, query: SearchQuery, start: int) -> str:
        params: dict[str, str | int] = {"q": term}
        params["l"] = query.location or ("Remote" if query.remote else "")
        if start:
            params["start"] = start
        return f"https://{self.domain}/jobs?{urlencode(params)}"

    def _to_posting(self, card: dict, query: SearchQuery) -> JobPosting | None:
        job_key = card.get("jobkey") or card.get("jobKey")
        if not job_key:
            return None
        location = card.get("formattedLocation") or card.get("jobLocationCity") or None
        remote_model = bool(card.get("remoteWorkModel") or card.get("remoteLocation"))
        return JobPosting(
            source=self.name,
            source_id=str(job_key),
            url=f"https://{self.domain}/viewjob?jk={job_key}",
            company=card.get("company", "") or "",
            title=card.get("title", "") or "",
            description=strip_html(card.get("snippet", "")),
            location=location,
            remote=remote_model or query.remote or looks_remote(location),
            published_at=parse_epoch_ms(card.get("pubDate")),
            raw=dict(card),
        )
