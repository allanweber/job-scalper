"""Offline parsing tests for the aggregator adapters: Adzuna, HN."""

from scalper.models import SearchQuery
from scalper.sources.adzuna import AdzunaAdapter
from scalper.sources.base import REGISTRY
from scalper.sources.hackernews import HackerNewsAdapter


def test_aggregator_adapters_registered():
    assert REGISTRY["adzuna"] is AdzunaAdapter
    assert REGISTRY["hackernews"] is HackerNewsAdapter


# --- Adzuna ---------------------------------------------------------------

ADZUNA_JOB = {
    "id": "5044123456",
    "title": "<strong>Java</strong> Backend Engineer",
    "description": "Build distributed systems in Java. Fully remote role.",
    "company": {"display_name": "Acme Ltd"},
    "location": {"display_name": "Remote, UK"},
    "salary_min": 70000,
    "salary_max": 95000,
    "created": "2026-06-10T09:00:00Z",
    "redirect_url": "https://www.adzuna.co.uk/jobs/details/5044123456",
}


def test_adzuna_normalizes_and_parses_salary():
    p = AdzunaAdapter(country="gb")._to_posting(ADZUNA_JOB)
    assert p.source == "adzuna"
    assert p.source_id == "5044123456"
    assert p.company == "Acme Ltd"
    assert p.title == "Java Backend Engineer" and "<" not in p.title
    assert p.remote is True                       # "remote" detected in text
    assert p.salary_min == 70000 and p.salary_max == 95000
    assert p.salary_currency == "GBP"             # country-based currency
    assert p.published_at is not None and p.published_at.year == 2026


def test_adzuna_skips_without_keys():
    # No app_id/app_key (and assuming env is unset) => fetch returns nothing,
    # never raising, so collect keeps running.
    adapter = AdzunaAdapter(app_id=None, app_key=None)
    adapter.app_id = None
    adapter.app_key = None
    assert adapter.fetch(SearchQuery(terms=["java"])) == []


# --- Hacker News ----------------------------------------------------------

HN_COMMENT = {
    "id": 48360001,
    "type": "comment",
    "author": "someco",
    "created_at_i": 1781600000,
    "text": "Acme | Senior Backend Engineer | Remote (EU) | Full-time"
            "<p>We build payments infra in Java and Postgres.</p>",
    "url": None,
}


def test_hackernews_parses_comment_header():
    p = HackerNewsAdapter()._to_posting(HN_COMMENT, HN_COMMENT["text"])
    assert p.source == "hackernews"
    assert p.source_id == "48360001"
    assert p.company == "Acme"                    # first pipe segment
    assert p.title == "Senior Backend Engineer"   # second pipe segment
    assert p.remote is True                       # "Remote" in header
    assert p.url == "https://news.ycombinator.com/item?id=48360001"
    assert "Java" in p.description and "<" not in p.description
    assert p.published_at is not None and p.published_at.year == 2026


