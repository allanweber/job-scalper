"""We Work Remotely adapter — company-agnostic remote-job RSS feed .

We Work Remotely publishes per-category RSS feeds of remote jobs across all
employers, e.g.:
    https://weworkremotely.com/categories/remote-programming-jobs.rss

There is no keyword API, so this is a *broad-feed* source: it pulls a category
feed and filters locally against the user's query terms. The feed is remote-only
by nature. Each item's title is formatted "Company: Role"; we split on the first
colon to recover company and title separately.
"""

from __future__ import annotations


from scalper.models import JobPosting, SearchQuery
from scalper.sources._util import matches_any_term, parse_rss_dt, rss_items, strip_html
from scalper.sources.base import TIER_STRUCTURED, SourceAdapter, register

_FEED = "https://weworkremotely.com/categories/remote-programming-jobs.rss"
_UA = "job-scalper/0.1 (personal job-search tool; +https://weworkremotely.com)"


@register
class WeWorkRemotelyAdapter(SourceAdapter):
    type = "weworkremotely"
    tier = TIER_STRUCTURED

    def __init__(self, feed: str | None = None, timeout: float = 30.0):
        # Override `feed` to target a different WWR category RSS.
        self.feed = feed or _FEED
        self.timeout = timeout

    @property
    def name(self) -> str:
        return "weworkremotely"

    def fetch(self, query: SearchQuery) -> list[JobPosting]:
        with self._client(timeout=self.timeout) as client:
            resp = client.get(self.feed, headers={"User-Agent": _UA})
            resp.raise_for_status()
            items = rss_items(resp.text)

        postings: list[JobPosting] = []
        for item in items:
            p = self._to_posting(item)
            haystack = f"{p.title} {p.description} {item.get('category', '')} {p.company}"
            if matches_any_term(haystack, query.terms):
                postings.append(p)
            if len(postings) >= query.limit_per_source:
                break
        return postings

    def _to_posting(self, item: dict[str, str]) -> JobPosting:
        raw_title = item.get("title", "")
        company, _, role = raw_title.partition(": ")
        if not role:  # title without the "Company: Role" shape
            company, role = "", raw_title
        url = item.get("link") or item.get("guid", "")
        return JobPosting(
            source=self.name,
            source_id=item.get("guid") or url,
            url=url,
            company=company.strip(),
            title=role.strip(),
            description=strip_html(item.get("description", "")),
            location=item.get("region") or None,
            remote=True,  # We Work Remotely is remote-only by definition
            published_at=parse_rss_dt(item.get("pubDate")),
            raw=dict(item),
        )
