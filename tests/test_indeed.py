"""Offline tests for the Indeed 'hard' adapter (Phase 4).

A captured results page (embedded job-card JSON) drives the parser and a fetcher
is injected, so these run with no browser and no `[scrape]` extra. They cover:
balanced JSON extraction, job-card parsing, Cloudflare-challenge detection,
field mapping, and the fail-soft paths.
"""

from scalper.models import SearchQuery
from scalper.sources.indeed import (
    IndeedAdapter,
    _extract_json_object,
    is_challenge_page,
    parse_jobcards,
)

# An Indeed results page boils down to this embedded blob (two cards). The
# snippet carries braces-free HTML; one is reachable via `jobkey`, one `jobKey`.
_BLOB = (
    'window.mosaic.providerData["mosaic-provider-jobcards"]={"metaData":'
    '{"mosaicProviderJobCardsModel":{"results":['
    '{"jobkey":"abc123","title":"Backend Engineer","company":"Acme",'
    '"formattedLocation":"Remote","pubDate":1718000000000,'
    '"snippet":"<b>Python</b> and Postgres."},'
    '{"jobkey":"def456","title":"Platform Engineer","company":"Globex",'
    '"formattedLocation":"Berlin","pubDate":1718200000000,"snippet":"Go and k8s"}'
    ']}}};'
)
_PAGE = f"<html><head></head><body><script>{_BLOB}</script></body></html>"

_CHALLENGE_PAGE = (
    "<html><head><title>Just a moment...</title></head>"
    "<body><div id='cf-challenge'></div></body></html>"
)


def test_extract_json_object_balances_braces_and_strings():
    text = 'x = {"a":"}{","b":{"c":1}} trailing'
    obj = _extract_json_object(text, text.index("="))
    assert obj == '{"a":"}{","b":{"c":1}}'


def test_parse_jobcards_extracts_results():
    cards = parse_jobcards(_PAGE)
    assert [c["jobkey"] for c in cards] == ["abc123", "def456"]


def test_parse_jobcards_empty_when_blob_missing():
    assert parse_jobcards("<html>no cards here</html>") == []


def test_challenge_page_detected_and_yields_nothing():
    assert is_challenge_page(_CHALLENGE_PAGE) is True
    assert parse_jobcards(_CHALLENGE_PAGE) == []


def test_adapter_maps_postings():
    adapter = IndeedAdapter(max_pages=1, fetcher=lambda _u: _PAGE)
    out = {p.source_id: p for p in adapter.fetch(SearchQuery(terms=["backend"], remote=True))}
    assert set(out) == {"abc123", "def456"}
    p = out["abc123"]
    assert p.title == "Backend Engineer" and p.company == "Acme"
    assert p.url == "https://www.indeed.com/viewjob?jk=abc123"
    assert p.description == "Python and Postgres."  # HTML stripped
    assert p.remote is True
    assert p.published_at is not None  # epoch-ms parsed


def test_adapter_dedups_across_terms_and_caps():
    adapter = IndeedAdapter(max_pages=1, fetcher=lambda _u: _PAGE)
    out = adapter.fetch(SearchQuery(terms=["backend", "platform"], remote=True))
    assert len(out) == 2  # unioned + deduped by jobkey
    capped = adapter.fetch(SearchQuery(terms=["backend"], limit_per_source=1))
    assert len(capped) == 1


def test_adapter_fails_soft_on_challenge():
    adapter = IndeedAdapter(fetcher=lambda _u: _CHALLENGE_PAGE)
    assert adapter.fetch(SearchQuery(terms=["backend"])) == []
