"""Reddit job-subreddit adapter — company-agnostic .

Reddit's JSON API requires OAuth and 403s anonymous library clients, but the
public per-subreddit Atom feeds are reachable without auth or registration:
    https://www.reddit.com/r/{subreddit}/.rss

This is a *broad-feed* source over one or more job subreddits, filtered locally
against the query terms. Reddit rate-limits anonymous clients — a burst yields
HTTP 429 with an empty body — so we pause `delay` seconds between subreddit
requests and retry a 429 once, honoring any `Retry-After`. Throttling is far
harsher from datacenter/cloud IPs than from a residential connection, so this
works best run locally. Every fetch fails soft: a throttled or missing
subreddit yields nothing rather than breaking the run.

`hiring_only` keeps only `[Hiring]`-style posts and drops `[For Hire]` seekers
and pinned mod threads — right for mixed subs like r/forhire. For dedicated job
boards (r/java_jobs, r/techjobs, …) where *every* post is a listing, set
`hiring_only: false` so real listings aren't filtered out.
"""

from __future__ import annotations

import time

import httpx

from scalper.models import JobPosting, SearchQuery
from scalper.sources._util import (
    atom_entries,
    looks_remote,
    matches_any_term,
    parse_iso_dt,
    strip_html,
)
from scalper.sources.base import TIER_STRUCTURED, SourceAdapter, register

_FEED = "https://www.reddit.com/r/{subreddit}/.rss"
# Reddit blocks generic library User-Agents; present a browser-like one.
_UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36"
_DEFAULT_SUBS = ("forhire", "remotejs", "jobbit")


@register
class RedditAdapter(SourceAdapter):
    type = "reddit"
    tier = TIER_STRUCTURED

    def __init__(
        self,
        subreddits: list[str] | None = None,
        hiring_only: bool = True,
        delay: float = 2.0,
        max_retries: int = 1,
        timeout: float = 30.0,
    ):
        self.subreddits = subreddits or list(_DEFAULT_SUBS)
        # Keep only "[Hiring]" posts (drops "[For Hire]" seekers + mod threads).
        self.hiring_only = hiring_only
        # Politeness: seconds to pause between subreddit requests, and how many
        # times to retry a 429 before giving up on that subreddit.
        self.delay = delay
        self.max_retries = max_retries
        self.timeout = timeout

    @property
    def name(self) -> str:
        return "reddit"

    def fetch(self, query: SearchQuery) -> list[JobPosting]:
        postings: list[JobPosting] = []
        with httpx.Client(timeout=self.timeout, follow_redirects=True) as client:
            for i, sub in enumerate(self.subreddits):
                if i:  # pause between requests; anonymous bursts get 429'd
                    time.sleep(self.delay)
                for entry in self._feed(client, sub):
                    title = entry.get("title", "")
                    if self.hiring_only and not self._is_hiring(title):
                        continue
                    p = self._to_posting(entry, sub)
                    if matches_any_term(f"{p.title} {p.description}", query.terms):
                        postings.append(p)
                    if len(postings) >= query.limit_per_source:
                        return postings
        return postings

    def _feed(self, client: httpx.Client, subreddit: str) -> list[dict[str, str]]:
        url = _FEED.format(subreddit=subreddit)
        for attempt in range(self.max_retries + 1):
            try:
                resp = client.get(url, headers={"User-Agent": _UA})
                if resp.status_code == 429 and attempt < self.max_retries:
                    time.sleep(self._retry_after(resp, self.delay * (attempt + 2)))
                    continue
                resp.raise_for_status()
                return atom_entries(resp.text)
            except httpx.HTTPError as exc:
                if attempt < self.max_retries:
                    time.sleep(self.delay)
                    continue
                code = getattr(getattr(exc, "response", None), "status_code", "?")
                hint = " (rate-limited; raise `delay` or run from a home IP)" if code == 429 else ""
                print(f"    reddit: r/{subreddit} unavailable (HTTP {code}){hint}; skipping.")
                return []
        return []

    @staticmethod
    def _is_hiring(title: str) -> bool:
        low = title.lower()
        return "hiring" in low and "for hire" not in low

    @staticmethod
    def _retry_after(resp: httpx.Response, fallback: float) -> float:
        """Honor a numeric `Retry-After` header, capped; else use `fallback`."""
        raw = resp.headers.get("Retry-After")
        if raw:
            try:
                return min(float(raw), 30.0)
            except ValueError:
                pass
        return fallback

    def _to_posting(self, entry: dict[str, str], subreddit: str) -> JobPosting:
        url = entry.get("link", "")
        title = entry.get("title", "").strip()
        description = strip_html(entry.get("content", ""))
        return JobPosting(
            source=self.name,
            source_id=entry.get("id") or url,
            url=url,
            company=f"r/{subreddit}",  # subreddit posts rarely name a company field
            title=title,
            description=description,
            location=None,
            remote=looks_remote(title, description),  # posts vary; infer from text
            published_at=parse_iso_dt(entry.get("published") or entry.get("updated")),
            raw=dict(entry),
        )
