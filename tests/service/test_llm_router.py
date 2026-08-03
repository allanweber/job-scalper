from __future__ import annotations

from _helpers import FakeProvider

from scalper.service.content_repos import LLMUsageRepo
from scalper.service.llm_router import LLMDecision, LLMRouter, LLMUnavailable
from scalper.service.models import GoogleIdentity
from scalper.service.repositories import LLMCredentialRepo, UserRepo


def _router(conn, settings, vault, *, provider=None, environ=None):
    prov = provider or FakeProvider()
    return LLMRouter(conn, settings, vault, environ=environ or {},
                     provider_builder=lambda name, api_key=None: prov)


def _user(conn):
    return UserRepo(conn).upsert_from_google(
        GoogleIdentity(sub="s", email="u@example.com"), role="user")


def test_platform_default_when_no_byo(conn, settings, vault):
    user = _user(conn)
    r = _router(conn, settings, vault, environ={"SCALPER_PLATFORM_ANTHROPIC_KEY": "k"})
    d = r.resolve(user.id, "draft")
    assert isinstance(d, LLMDecision)
    assert d.key_source == "platform" and d.unlimited is False
    # 'draft'/'profile_build' share the draft model slot; platform model from seed.
    assert d.model == "claude-haiku-4-5"


def test_platform_unavailable_without_key(conn, settings, vault):
    user = _user(conn)
    # provider_builder returns None (as build_provider does with no key/SDK).
    r = LLMRouter(conn, settings, vault, environ={},
                  provider_builder=lambda name, api_key=None: None)
    try:
        r.resolve(user.id, "draft")
        assert False, "expected LLMUnavailable"
    except LLMUnavailable:
        pass


def test_byo_preferred_and_unlimited(conn, settings, vault):
    user = _user(conn)
    sealed = vault.seal("sk-user-key")
    LLMCredentialRepo(conn).upsert(user.id, "anthropic", sealed)
    r = _router(conn, settings, vault)
    d = r.resolve(user.id, "draft")
    assert d.key_source == "byo" and d.unlimited is True
    assert d.model == "claude-sonnet-4-6"     # byo draft model from seed


def test_enrich_uses_cheaper_slot(conn, settings, vault):
    user = _user(conn)
    r = _router(conn, settings, vault, environ={"SCALPER_PLATFORM_ANTHROPIC_KEY": "k"})
    assert r.resolve(user.id, "enrich").model == "claude-haiku-4-5"


def test_token_ceiling_from_settings(conn, settings, vault):
    settings.set("llm.per_request_token_ceiling", 1234)
    r = _router(conn, settings, vault, environ={"SCALPER_PLATFORM_ANTHROPIC_KEY": "k"})
    assert r.resolve(_user(conn).id, "draft").max_output_tokens == 1234


def test_record_usage_writes_ledger(conn, settings, vault):
    user = _user(conn)
    r = _router(conn, settings, vault, environ={"SCALPER_PLATFORM_ANTHROPIC_KEY": "k"})
    d = r.resolve(user.id, "draft")
    r.record_usage(user.id, action="draft", decision=d, input_tokens=5, output_tokens=7)
    assert LLMUsageRepo(conn).total_tokens_for(user.id) == 12


def test_record_usage_estimates_cost(conn, settings, vault):
    user = _user(conn)
    r = _router(conn, settings, vault, environ={"SCALPER_PLATFORM_ANTHROPIC_KEY": "k"})
    d = r.resolve(user.id, "draft")  # platform model claude-haiku-4-5 ($1/$5 per Mtok)
    r.record_usage(user.id, action="draft", decision=d,
                   input_tokens=1000, output_tokens=2000)
    event = LLMUsageRepo(conn).list_recent()[0]
    assert event.est_cost_usd == 0.011  # (1000*1 + 2000*5)/1e6


def test_record_usage_cost_uses_price_overrides(conn, settings, vault):
    settings.set("llm.model_prices", {"claude-haiku-4-5": {"input": 10.0, "output": 0.0}})
    user = _user(conn)
    r = _router(conn, settings, vault, environ={"SCALPER_PLATFORM_ANTHROPIC_KEY": "k"})
    d = r.resolve(user.id, "draft")
    r.record_usage(user.id, action="draft", decision=d,
                   input_tokens=1_000_000, output_tokens=0)
    assert LLMUsageRepo(conn).list_recent()[0].est_cost_usd == 10.0
