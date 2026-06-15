"""Config loading tests, including the per-source limit override."""

from scalper.config import _parse_source
from scalper.models import SearchQuery


def test_source_without_limit_defaults_to_none():
    sc = _parse_source({"type": "remotive", "category": "software-dev"})
    assert sc.type == "remotive"
    assert sc.limit is None
    assert sc.params == {"category": "software-dev"}  # `limit` not leaked into params


def test_source_limit_is_extracted_not_passed_as_param():
    sc = _parse_source({"type": "hackernews", "limit": 25})
    assert sc.type == "hackernews"
    assert sc.limit == 25
    assert sc.params == {}  # must not reach the adapter constructor


def test_per_source_limit_overrides_global_query():
    # Mirrors what cmd_collect does: clone the global query with the source cap.
    global_query = SearchQuery(terms=["java"], limit_per_source=100)
    capped = global_query.model_copy(update={"limit_per_source": 25})
    assert global_query.limit_per_source == 100  # original untouched
    assert capped.limit_per_source == 25
    assert capped.terms == ["java"]
