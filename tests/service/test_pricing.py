from __future__ import annotations

from scalper.service.pricing import DEFAULT_PRICES, estimate_cost_usd


def test_default_price_table_costs_a_call():
    # claude-haiku-4-5 = $1/Mtok in, $5/Mtok out.
    cost = estimate_cost_usd("claude-haiku-4-5", 1_000_000, 1_000_000)
    assert cost == 6.0


def test_small_token_counts_round_to_six_places():
    cost = estimate_cost_usd("claude-haiku-4-5", 1200, 800)
    # (1200*1 + 800*5) / 1e6 = 0.0052
    assert cost == 0.0052


def test_unknown_model_has_no_price():
    assert estimate_cost_usd("mystery-model-x", 1000, 1000) is None


def test_override_beats_default_mapping_form():
    cost = estimate_cost_usd("claude-haiku-4-5", 1_000_000, 0,
                             overrides={"claude-haiku-4-5": {"input": 2.0, "output": 9.0}})
    assert cost == 2.0


def test_override_pair_form_and_new_model():
    cost = estimate_cost_usd("brand-new", 1_000_000, 1_000_000,
                             overrides={"brand-new": [4.0, 6.0]})
    assert cost == 10.0


def test_malformed_override_falls_through_to_default():
    cost = estimate_cost_usd("gpt-4o-mini", 1_000_000, 0,
                             overrides={"gpt-4o-mini": {"input": "oops"}})
    assert cost == DEFAULT_PRICES["gpt-4o-mini"][0]
