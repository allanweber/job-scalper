"""Offline tests for the LinkedIn 'hard' adapter (Phase 4).

A captured guest-search HTML fragment drives the parser and a fetcher is
injected into the adapter, so these run with no browser and no `[scrape]` extra.
They cover: card parsing, field mapping, server-side-term union/dedup, the limit
cap, remote inference, and the fail-soft (blocked / empty) path.
"""

from scalper.models import SearchQuery
from scalper.report import _tier
from scalper.sources.base import TIER_HARD, TIER_STRUCTURED
from scalper.sources.linkedin import LinkedInAdapter, parse_search_cards

# Two job cards as the guest endpoint returns them (trimmed but structurally real).
_FRAGMENT = """
<li>
  <div class="base-card base-search-card" data-entity-urn="urn:li:jobPosting:3812345678">
    <a class="base-card__full-link" href="https://www.linkedin.com/jobs/view/senior-backend-engineer-at-acme-3812345678?refId=abc&trackingId=xyz"></a>
    <h3 class="base-search-card__title">
            Senior Backend Engineer
          </h3>
    <h4 class="base-search-card__subtitle">
      <a class="hidden-nested-link" href="#">Acme Corp</a>
    </h4>
    <span class="job-search-card__location">
            Remote
          </span>
    <time class="job-search-card__listdate" datetime="2026-06-10">2 days ago</time>
  </div>
</li>
<li>
  <div class="base-card base-search-card" data-entity-urn="urn:li:jobPosting:3899999999">
    <a class="base-card__full-link" href="https://www.linkedin.com/jobs/view/platform-engineer-3899999999?x=1"></a>
    <h3 class="base-search-card__title">Platform Engineer</h3>
    <h4 class="base-search-card__subtitle">Globex</h4>
    <span class="job-search-card__location">Berlin, Germany</span>
    <time class="job-search-card__listdate" datetime="2026-06-12">today</time>
  </div>
</li>
"""


def test_parse_search_cards_extracts_fields():
    cards = parse_search_cards(_FRAGMENT)
    assert len(cards) == 2
    first = cards[0]
    assert first["job_id"] == "3812345678"
    assert first["title"] == "Senior Backend Engineer"  # whitespace collapsed
    assert first["company"] == "Acme Corp"               # unwrapped from the <a>
    assert first["location"] == "Remote"
    assert first["url"] == "https://www.linkedin.com/jobs/view/senior-backend-engineer-at-acme-3812345678"
    assert first["published"] == "2026-06-10"
    assert cards[1]["company"] == "Globex"  # bare-text subtitle (no nested link)


def test_parse_ignores_non_card_chunks():
    assert parse_search_cards("<ul><li>nothing here</li></ul>") == []


def _fetch_once(fragment):
    """A fetcher that serves `fragment` on the first call, then '' (stops paging)."""
    calls = {"n": 0}

    def get(_url):
        calls["n"] += 1
        return fragment if calls["n"] == 1 else ""

    return get


def test_adapter_maps_postings_and_marks_remote():
    adapter = LinkedInAdapter(max_pages=1, fetcher=_fetch_once(_FRAGMENT))
    out = adapter.fetch(SearchQuery(terms=["backend"], remote=True))
    assert {p.uid for p in out} == {"linkedin::3812345678", "linkedin::3899999999"}
    p = next(p for p in out if p.source_id == "3812345678")
    assert p.title == "Senior Backend Engineer" and p.company == "Acme Corp"
    assert p.remote is True  # remote-only query → all flagged remote
    assert p.published_at is not None and p.published_at.date().isoformat() == "2026-06-10"


def test_adapter_infers_remote_from_location_when_not_remote_only():
    adapter = LinkedInAdapter(max_pages=1, fetcher=_fetch_once(_FRAGMENT))
    out = {p.source_id: p for p in adapter.fetch(SearchQuery(terms=["x"], remote=False))}
    assert out["3812345678"].remote is True   # location says "Remote"
    assert out["3899999999"].remote is False  # Berlin


def test_adapter_dedups_across_terms_and_caps_to_limit():
    # Fetcher always returns the same two cards, regardless of term/page.
    adapter = LinkedInAdapter(max_pages=1, fetcher=lambda _u: _FRAGMENT)
    out = adapter.fetch(SearchQuery(terms=["backend", "platform"], remote=True))
    assert len(out) == 2  # unioned + deduped by uid, not 4

    capped = adapter.fetch(SearchQuery(terms=["backend"], remote=True, limit_per_source=1))
    assert len(capped) == 1


def test_adapter_fails_soft_when_blocked():
    # A blocked/empty page (None) yields nothing instead of raising.
    adapter = LinkedInAdapter(fetcher=lambda _u: None)
    assert adapter.fetch(SearchQuery(terms=["backend"])) == []


def test_tier_lookup_marks_hard_sources():
    assert _tier("linkedin") == TIER_HARD
    assert _tier("indeed") == TIER_HARD
    assert _tier("remotive") == TIER_STRUCTURED
    assert _tier("does-not-exist") == TIER_STRUCTURED
