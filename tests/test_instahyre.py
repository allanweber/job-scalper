"""Offline tests for the Instahyre 'hard' adapter.

A canned JSON-LD job page and an inlined-``objects`` search payload drive the
parser, and a fetcher is injected into the adapter, so these run with no browser
and no ``[scrape]`` extra. They cover: both parse strategies, field mapping,
term matching, cross-term dedup / limit cap, and the fail-soft path.
"""

from scalper.models import SearchQuery
from scalper.report import _tier
from scalper.sources.base import TIER_HARD, REGISTRY
from scalper.sources.instahyre import (
    InstahyreAdapter,
    _json_array_after,
    parse_instahyre_page,
)

# A job-detail style page carrying Schema.org JSON-LD.
_JSONLD = """
<html><head>
<script type="application/ld+json">
{"@context":"https://schema.org","@type":"JobPosting",
 "title":"Senior Backend Engineer",
 "description":"<p>Build <b>Django</b> and Python services at scale.</p>",
 "hiringOrganization":{"@type":"Organization","name":"Razorpay"},
 "jobLocation":{"@type":"Place","address":{"@type":"PostalAddress",
   "addressLocality":"Bengaluru","addressCountry":"IN"}},
 "datePosted":"2026-07-01",
 "url":"https://www.instahyre.com/job/998877/senior-backend-engineer"}
</script></head><body><div ng-app></div></body></html>
"""

# A search page with the API's own {"meta":..., "objects":[...]} shape inlined.
_OBJECTS = """
<html><body><script>
window.__PRELOAD__ = {"meta": {"total_count": 2}, "objects": [
  {"id": 12345, "job_title": "Python Backend Developer",
   "employer": {"company_name": "Swiggy"},
   "job_description": "<p>FastAPI and Python microservices.</p>",
   "locations": ["Bengaluru", "Remote"], "created_at": "2026-07-10"},
  {"id": 67890, "job_title": "Frontend Engineer",
   "employer": {"company_name": "Zomato"},
   "job_description": "React and TypeScript.", "locations": ["Gurgaon"]}
]};
</script></body></html>
"""


def test_registered_as_hard_source():
    assert REGISTRY["instahyre"] is InstahyreAdapter
    assert _tier("instahyre") == TIER_HARD


def test_json_array_after_handles_nesting():
    blob = '{"total": 2, "objects":[{"a":[1,2]},{"b":"]"}], "meta":{}}'
    arr = _json_array_after(blob, "objects")
    # A nested array and a literal ']' inside a string don't truncate the match.
    assert arr == [{"a": [1, 2]}, {"b": "]"}]


def test_parse_prefers_jsonld():
    rows = parse_instahyre_page(_JSONLD)
    assert len(rows) == 1 and rows[0]["@type"] == "JobPosting"


def test_parse_falls_back_to_objects():
    rows = parse_instahyre_page(_OBJECTS)
    assert [r["_raw"]["id"] for r in rows] == [12345, 67890]


def test_adapter_maps_jsonld_posting():
    adapter = InstahyreAdapter(max_pages=1, fetcher=_once(_JSONLD))
    out = adapter.fetch(SearchQuery(terms=["backend"], remote=False))
    assert len(out) == 1
    p = out[0]
    assert p.source == "instahyre"
    assert p.title == "Senior Backend Engineer"
    assert p.company == "Razorpay"
    assert p.location == "Bengaluru, IN"
    assert "Django" in p.description and "<" not in p.description
    assert p.published_at is not None and p.published_at.date().isoformat() == "2026-07-01"
    assert p.url == "https://www.instahyre.com/job/998877/senior-backend-engineer"


def test_adapter_maps_objects_and_filters_by_term():
    adapter = InstahyreAdapter(max_pages=1, fetcher=_once(_OBJECTS))
    out = {p.source_id: p for p in adapter.fetch(SearchQuery(terms=["python"], remote=False))}
    # Only the Python role matches the term; the React one is filtered out.
    assert set(out) == {"12345"}
    p = out["12345"]
    assert p.company == "Swiggy"
    assert p.url == "https://www.instahyre.com/job/12345"
    assert p.remote is True  # "Remote" among its locations


def test_adapter_dedups_across_terms_and_caps():
    adapter = InstahyreAdapter(max_pages=1, fetcher=lambda _u: _OBJECTS)
    out = adapter.fetch(SearchQuery(terms=["python", "backend"], remote=False))
    assert len(out) == 1  # same row unioned across terms, deduped by uid
    capped = adapter.fetch(
        SearchQuery(terms=["engineer", "developer"], remote=False, limit_per_source=1))
    assert len(capped) == 1


def test_adapter_fails_soft_when_blocked():
    adapter = InstahyreAdapter(fetcher=lambda _u: None)
    assert adapter.fetch(SearchQuery(terms=["backend"])) == []


def _once(page):
    """A fetcher that serves `page` once, then '' so paging stops."""
    calls = {"n": 0}

    def get(_url):
        calls["n"] += 1
        return page if calls["n"] == 1 else ""

    return get
