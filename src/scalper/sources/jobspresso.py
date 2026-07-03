"""Jobspresso adapter — RSS broad-feed for remote tech/design roles.

Jobspresso is a curated remote job board for software engineers, designers,
and product roles. It publishes listings via RSS:
    https://jobspresso.co/feed/

Broad-feed source: pulls the full feed and filters locally against query terms.
No API key required.
"""

from __future__ import annotations

from scalper.models import JobPosting, SearchQuery
from scalper.sources._util import matches_any_term, parse_rss_dt, rss_items, strip_html
from scalper.sources.base import TIER_STRUCTURED, SourceAdapter, register

_FEED = "https://jobspresso.co/feed/"


@register
class JobspressoAdapter(SourceAdapter):
    type = "jobspresso"
    tier = TIER_STRUCTURED

    def __init__(self, timeout: float = 30.0):
        self.timeout = timeout

    @property
    def name(self) -> str:
        return "jobspresso"

    def fetch(self, query: SearchQuery) -> list[JobPosting]:
        try:
            with self._client(timeout=self.timeout) as client:
                resp = client.get(_FEED)
                resp.raise_for_status()
        except Exception as exc:  # noqa: BLE001
            print(f"    jobspresso: unavailable ({exc}); skipping.")
            return []
        postings: list[JobPosting] = []
        for item in rss_items(resp.text):
            p = self._to_posting(item)
            if matches_any_term(f"{p.title} {p.description} {p.company}", query.terms):
                postings.append(p)
            if len(postings) >= query.limit_per_source:
                break
        return postings

    def _to_posting(self, item: dict[str, str]) -> JobPosting:
        url = item.get("link") or item.get("guid", "")
        return JobPosting(
            source=self.name,
            source_id=item.get("guid") or url,
            url=url,
            company=(item.get("creator") or "").strip(),
            title=(item.get("title") or "").strip(),
            description=strip_html(item.get("description", "")),
            location=item.get("region") or None,
            remote=True,
            published_at=parse_rss_dt(item.get("pubDate")),
            raw=dict(item),
        )
