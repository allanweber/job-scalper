"""Tests for the optional Stage 2 LLM enrichment layer (Phase 2).

A stub provider stands in for a real LLM, so these run with no network and no
`[llm]` extra. They cover: prompt construction, JSON parsing (clean + messy +
broken), top-N bounding, the store cache (hit / no recompute), and the
disabled/no-provider paths.
"""

import json

import pytest

from scalper.config import LLMConfig, Profile
from scalper.enrich import (
    Enricher,
    Enrichment,
    Usage,
    build_enricher,
    build_prompt,
    format_usage,
    profile_hash,
    _parse,
)
from scalper.llm.base import Completion
from scalper.models import JobPosting
from scalper.scoring import score_all
from scalper.store import JobStore


def _posting(n=1, **kw):
    base = dict(
        source="test", source_id=str(n), url="https://x",
        company="Co", title="Backend Engineer", remote=True,
        description="We build distributed systems in Python and Postgres.",
    )
    base.update(kw)
    return JobPosting(**base)


class StubProvider:
    """Counts calls and returns a canned JSON reply, so no network is touched."""

    name = "stub"

    def __init__(self, reply=None):
        self.calls = 0
        self._reply = reply or json.dumps({"remote": True})

    def complete(self, prompt, *, model, system=None, max_tokens=1024, temperature=0.2):
        self.calls += 1
        self.last_prompt = prompt
        return Completion(text=self._reply, model=model, input_tokens=100, output_tokens=20)


def _profile():
    return Profile(titles=["Backend Engineer"], required_skills=["python", "postgres"],
                   keywords=["distributed systems"])


def _enricher(store=None, reply=None):
    return Enricher(StubProvider(reply), model="stub-model", store=store)


# --- parsing ---------------------------------------------------------------

def test_parse_clean_json():
    assert _parse('{"remote": true}').remote is True


def test_parse_json_with_surrounding_prose():
    assert _parse('Sure! ```json\n{"remote": false}\n``` done').remote is False


def test_parse_unparseable_falls_back_to_none():
    assert _parse("totally not json").remote is None


def test_parse_non_bool_remote_is_none():
    # The model must answer with a real boolean; anything else → undeterminable.
    assert _parse('{"remote": "yes"}').remote is None
    assert _parse('{"matches": ["a"]}').remote is None


# --- prompt ----------------------------------------------------------------

def test_prompt_includes_posting_and_is_trimmed():
    profile = _profile()
    long_desc = "word " * 1000
    scored = score_all(profile, [_posting(description=long_desc)])[0]
    prompt = build_prompt(profile, scored)
    assert "Backend Engineer" in prompt  # title carried for context
    assert len(prompt) < 2200  # description trimmed to the cap, not the full 5000 chars


# --- enrichment + cache ----------------------------------------------------

def test_enrich_bounds_to_top_n():
    profile = _profile()
    scored = score_all(profile, [_posting(n=i) for i in range(5)])
    enr = _enricher()
    out = enr.enrich(profile, scored, top_n=2)
    assert len(out) == 2
    assert enr.provider.calls == 2


def test_enrich_round_trips_and_avoids_recompute(tmp_path):
    profile = _profile()
    posting = _posting()
    db = tmp_path / "s.db"
    with JobStore(db) as store:
        store.upsert_many([posting])
        scored = score_all(profile, [posting])

        first = _enricher(store)
        out = first.enrich(profile, scored, top_n=5)
        assert posting.uid in out
        assert first.provider.calls == 1

        # Persisted under (uid, profile_hash, model).
        cached = store.get_enrichments([posting.uid], profile_hash(profile), "stub-model")
        assert posting.uid in cached

        # A fresh enricher serves from cache without calling the provider.
        second = _enricher(store)
        out2 = second.enrich(profile, scored, top_n=5)
        assert second.provider.calls == 0
        assert out2[posting.uid].remote == out[posting.uid].remote


def test_profile_change_invalidates_cache(tmp_path):
    posting = _posting()
    db = tmp_path / "s.db"
    with JobStore(db) as store:
        store.upsert_many([posting])
        p1 = _profile()
        scored = score_all(p1, [posting])
        _enricher(store).enrich(p1, scored, top_n=5)

        p2 = Profile(titles=["Data Engineer"], required_skills=["spark"])
        e2 = _enricher(store)
        e2.enrich(p2, score_all(p2, [posting]), top_n=5)
        assert e2.provider.calls == 1  # different profile_hash → recomputed


# --- factory / disabled paths ---------------------------------------------

def test_build_disabled_returns_none():
    assert build_enricher(LLMConfig(), enabled=False) is None


def test_build_returns_none_without_provider(monkeypatch):
    # An unknown provider name has no factory → None (mirrors a missing [llm] dep).
    cfg = LLMConfig(provider="does-not-exist")
    assert build_enricher(cfg, enabled=True) is None


def test_enrichment_model_json_round_trip():
    enr = Enrichment(remote=False)
    assert Enrichment.model_validate_json(enr.model_dump_json()) == enr


# --- usage, cost, logging --------------------------------------------------

def test_usage_accumulates_tokens_calls_and_cache(tmp_path):
    profile = _profile()
    posting = _posting()
    db = tmp_path / "s.db"
    with JobStore(db) as store:
        store.upsert_many([posting])
        scored = score_all(profile, [posting])

        first = _enricher(store)
        first.enrich(profile, scored, top_n=5)
        assert first.usage.calls == 1
        assert first.usage.cached == 0
        assert first.usage.input_tokens == 100 and first.usage.output_tokens == 20

        # Second run is served from cache: no calls, counted as cached.
        second = _enricher(store)
        second.enrich(profile, scored, top_n=5)
        assert second.usage.calls == 0
        assert second.usage.cached == 1
        assert second.usage.input_tokens == 0


def test_cost_uses_builtin_pricing_and_override():
    u = Usage(model="claude-haiku-4-5", input_tokens=1_000_000, output_tokens=1_000_000)
    in_c, out_c = u.cost()  # built-in haiku estimate: $1 / $5 per MTok
    assert in_c == pytest.approx(1.0) and out_c == pytest.approx(5.0)
    # Explicit override wins over the table.
    in_c, out_c = u.cost(input_price=2.0, output_price=10.0)
    assert in_c == pytest.approx(2.0) and out_c == pytest.approx(10.0)


def test_cost_unknown_model_is_none():
    assert Usage(model="mystery-model", input_tokens=10).cost() is None


def test_format_usage_renders_cost_and_na():
    u = Usage(model="claude-haiku-4-5", calls=3, cached=1,
              input_tokens=12_000, output_tokens=800)
    out = format_usage(u, LLMConfig())
    assert "calls:          3  (1 served from cache)" in out
    assert "input tokens:   12,000" in out
    assert "est. cost:      $" in out
    # Unknown model → n/a guidance.
    na = format_usage(Usage(model="mystery", input_tokens=5), LLMConfig())
    assert "n/a" in na


def test_logger_receives_request_and_response():
    profile = _profile()
    scored = score_all(profile, [_posting()])
    logs = []
    enr = Enricher(StubProvider(), model="stub-model", logger=logs.append)
    enr.enrich(profile, scored, top_n=1)
    blob = "\n".join(logs)
    assert "REQUEST (model=stub-model)" in blob
    assert "RESPONSE (in=100 out=20 tok)" in blob
    assert '"remote": true' in blob  # the stub's response body was logged
