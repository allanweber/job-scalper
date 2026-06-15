"""LLM provider contract and registry (ADR 0003 / ADR 0004).

Stage 2 enrichment and the future `add-source` codegen both talk to an LLM, but
must stay decoupled from any one vendor. A provider is anything that can turn a
prompt into text; models are chosen *per task* (cheap Haiku for enrichment, a
stronger model for builds), so the model is a per-call argument, not baked into
the provider. The whole layer is optional: if the chosen provider's SDK isn't
installed (the `[llm]` extra), `build_provider` returns ``None`` and callers fall
back to their deterministic, no-LLM behaviour.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Protocol, runtime_checkable


@dataclass
class Completion:
    """A model reply plus the token usage it cost (for logging and costing)."""

    text: str
    model: str = ""
    input_tokens: int = 0
    output_tokens: int = 0


@runtime_checkable
class LLMProvider(Protocol):
    """Minimal text-completion interface every provider implements."""

    name: str

    def complete(
        self,
        prompt: str,
        *,
        model: str,
        system: str | None = None,
        max_tokens: int = 1024,
        temperature: float = 0.2,
    ) -> Completion:
        """Return the model's completion (text + token usage) for `prompt`."""
        ...


# provider name -> factory() -> LLMProvider
REGISTRY: dict[str, Callable[[], "LLMProvider"]] = {}


def register_provider(name: str) -> Callable[[Callable[[], "LLMProvider"]], Callable[[], "LLMProvider"]]:
    """Decorator registering a provider factory under `name`."""

    def deco(factory: Callable[[], "LLMProvider"]) -> Callable[[], "LLMProvider"]:
        REGISTRY[name] = factory
        return factory

    return deco


def build_provider(name: str = "anthropic") -> "LLMProvider | None":
    """Instantiate a provider by name, or ``None`` if its optional dep is missing.

    Import errors (the SDK isn't installed) and missing credentials fail soft to
    ``None`` so enrichment is skipped rather than aborting the report.
    """
    factory = REGISTRY.get(name)
    if factory is None:
        return None
    try:
        return factory()
    except Exception:  # noqa: BLE001 — missing SDK / key → no provider, no crash
        return None
