"""Offline tests for the Indeed 'hard' adapter (Phase 4).

A captured results page (embedded job-card JSON) drives the parser and a fetcher
is injected, so these run with no browser and no `[scrape]` extra. They cover:
balanced JSON extraction, job-card parsing, Cloudflare-challenge detection,
field mapping, and the fail-soft paths.
"""

from scalper.models import SearchQuery
from scalper.sources._browser import wait_until_cleared
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


def test_parse_jobcards_ignores_decoy_key_before_assignment():
    # The bare key also appears in an array of provider names earlier on the page.
    # The parser must anchor on the `…"]=` assignment, not that decoy, or it
    # extracts the wrong JSON object and returns zero cards.
    decoy = '...,"mosaic-provider-jobcards"],"beforeFirstJobResult":[],...'
    page = f"<script>{decoy}{_BLOB}</script>"
    cards = parse_jobcards(page)
    assert [c["jobkey"] for c in cards] == ["abc123", "def456"]


def test_challenge_regex_ignores_benign_cloudflare_script():
    # Cloudflare injects a `/cdn-cgi/challenge-platform/...` script into every
    # page it fronts, including successful ones — that must NOT read as a block.
    real_page = (
        '<title>Python Jobs | Indeed</title>'
        '<script src="/cdn-cgi/challenge-platform/h/b/scripts/jsd/main.js"></script>'
        f"<script>{_BLOB}</script>"
    )
    assert is_challenge_page(real_page) is False
    assert len(parse_jobcards(real_page)) == 2


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


def test_headful_defaults_to_a_challenge_wait():
    # A visible window implies time for a human to solve; headless does not.
    assert IndeedAdapter(headless=False).challenge_wait == 120.0
    assert IndeedAdapter(headless=True).challenge_wait == 0.0
    assert IndeedAdapter(headless=False, challenge_wait=30).challenge_wait == 30


# --- challenge-clearance wait (pure, no browser) ---------------------------

class _FakeClock:
    """Deterministic time/sleep so the wait loop is testable without a browser."""

    def __init__(self):
        self.t = 0.0

    def now(self):
        return self.t

    def sleep(self, s):
        self.t += s


def test_wait_returns_immediately_when_timeout_zero():
    # timeout<=0 preserves the old fast-bail: first read is returned as-is.
    assert wait_until_cleared(lambda: _CHALLENGE_PAGE, is_challenge_page,
                              timeout=0, poll=2) == _CHALLENGE_PAGE


def test_wait_clears_when_real_page_appears():
    pages = iter([_CHALLENGE_PAGE, _CHALLENGE_PAGE, _PAGE])
    clock = _FakeClock()
    out = wait_until_cleared(lambda: next(pages), is_challenge_page,
                             timeout=60, poll=2, sleep=clock.sleep, now=clock.now)
    assert out == _PAGE  # polled past the challenge until results rendered


def test_wait_gives_up_after_timeout_returning_last_seen():
    clock = _FakeClock()
    out = wait_until_cleared(lambda: _CHALLENGE_PAGE, is_challenge_page,
                             timeout=10, poll=4, sleep=clock.sleep, now=clock.now)
    assert out == _CHALLENGE_PAGE  # never cleared → last non-empty page returned
