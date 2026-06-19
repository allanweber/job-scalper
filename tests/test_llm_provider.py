"""Tests for provider construction and the config-vs-env API key (build_provider)."""

from scalper.llm.base import REGISTRY, build_provider


def test_build_provider_passes_api_key_to_factory(monkeypatch):
    seen = {}

    def factory(api_key=None):
        seen["api_key"] = api_key
        return object()

    monkeypatch.setitem(REGISTRY, "anthropic", factory)
    build_provider("anthropic", api_key="sk-from-config")
    assert seen["api_key"] == "sk-from-config"


def test_build_provider_falls_back_for_no_arg_factory(monkeypatch):
    class NoArgStub:
        name = "stub"  # default __init__ rejects kwargs -> TypeError -> plain call

    monkeypatch.setitem(REGISTRY, "anthropic", NoArgStub)
    provider = build_provider("anthropic", api_key="ignored")
    assert isinstance(provider, NoArgStub)


def test_build_provider_unknown_name_is_none():
    assert build_provider("nope") is None


def test_anthropic_provider_prefers_config_key_over_env(monkeypatch):
    import scalper.llm.anthropic_provider as ap

    monkeypatch.setattr(ap, "anthropic_available", lambda: True)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "env-key")
    captured = {}

    class FakeAnthropic:
        def __init__(self, api_key=None):
            captured["api_key"] = api_key

    monkeypatch.setattr("anthropic.Anthropic", FakeAnthropic, raising=False)
    import sys
    import types

    # Ensure `from anthropic import Anthropic` resolves to the fake.
    fake_mod = types.ModuleType("anthropic")
    fake_mod.Anthropic = FakeAnthropic
    monkeypatch.setitem(sys.modules, "anthropic", fake_mod)

    ap.AnthropicProvider(api_key="config-key")
    assert captured["api_key"] == "config-key"

    ap.AnthropicProvider()  # no explicit key -> env fallback
    assert captured["api_key"] == "env-key"
