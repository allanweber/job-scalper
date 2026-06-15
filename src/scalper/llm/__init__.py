"""LLM providers. Import side-effects register each provider in the registry."""

from scalper.llm.base import (
    REGISTRY,
    Completion,
    LLMProvider,
    build_provider,
    register_provider,
)

# Register built-in providers by importing them.
from scalper.llm import anthropic_provider  # noqa: E402,F401

__all__ = ["REGISTRY", "Completion", "LLMProvider", "build_provider", "register_provider"]
