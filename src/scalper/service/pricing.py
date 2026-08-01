"""Estimated LLM cost from token counts (admin cost visibility, not billing).

Every LLM call records its token usage in ``llm_usage_events``; this turns those
tokens into a dollar *estimate* the operator can see per draft/profile/enrich.
Rates are USD per 1,000,000 tokens as ``(input, output)``. The built-in table
covers the models the router selects; the ``llm.model_prices`` hot setting
overrides or extends it so prices can be corrected without a redeploy.
"""

from __future__ import annotations

from typing import Any

#: USD per 1,000,000 tokens: model -> (input_rate, output_rate). Estimates only.
DEFAULT_PRICES: dict[str, tuple[float, float]] = {
    "claude-haiku-4-5": (1.0, 5.0),
    "claude-sonnet-4-6": (3.0, 15.0),
    "claude-opus-4-6": (15.0, 75.0),
    "gpt-4o": (2.5, 10.0),
    "gpt-4o-mini": (0.15, 0.6),
}

_PER_MTOK = 1_000_000


def _rates(model: str, overrides: dict[str, Any] | None) -> tuple[float, float] | None:
    """Resolve (input, output) USD/Mtok for `model`: overrides win, else defaults.

    An override entry may be a ``{"input": x, "output": y}`` mapping or a
    ``[input, output]`` pair. Malformed entries fall through to the built-ins.
    """
    if overrides:
        raw = overrides.get(model)
        if isinstance(raw, dict):
            try:
                return float(raw["input"]), float(raw["output"])
            except (KeyError, TypeError, ValueError):
                pass
        elif isinstance(raw, (list, tuple)) and len(raw) == 2:
            try:
                return float(raw[0]), float(raw[1])
            except (TypeError, ValueError):
                pass
    return DEFAULT_PRICES.get(model)


def estimate_cost_usd(model: str, input_tokens: int, output_tokens: int,
                      *, overrides: dict[str, Any] | None = None) -> float | None:
    """USD estimate for one call, or ``None`` when the model has no known price."""
    rates = _rates(model, overrides)
    if rates is None:
        return None
    in_rate, out_rate = rates
    cost = (input_tokens * in_rate + output_tokens * out_rate) / _PER_MTOK
    return round(cost, 6)
