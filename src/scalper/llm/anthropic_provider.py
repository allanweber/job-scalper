"""Anthropic-backed LLM provider (default for Stage 2 enrichment).

Optional: requires the `[llm]` extra (the `anthropic` SDK) and an API key — from
`llm.api_key` in config, or the `ANTHROPIC_API_KEY` env var as a fallback. The SDK
and client are loaded lazily so importing this module never fails when the extra
isn't installed; `build_provider` catches the missing dep/key and returns ``None``.
"""

from __future__ import annotations

import importlib.util
import os

from scalper.llm.base import Completion, register_provider


def anthropic_available() -> bool:
    return importlib.util.find_spec("anthropic") is not None


class AnthropicProvider:
    name = "anthropic"

    def __init__(self, api_key: str | None = None) -> None:
        if not anthropic_available():
            raise RuntimeError("anthropic SDK not installed; `pip install -e '.[llm]'`")
        key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not key:
            raise RuntimeError("no API key — set llm.api_key in config or ANTHROPIC_API_KEY")
        from anthropic import Anthropic

        self._client = Anthropic(api_key=key)

    def complete(
        self,
        prompt: str,
        *,
        model: str,
        system: str | None = None,
        max_tokens: int = 1024,
        temperature: float = 0.2,
    ) -> Completion:
        kwargs: dict = {
            "model": model,
            "max_tokens": max_tokens,
            "temperature": temperature,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system:
            kwargs["system"] = system
        msg = self._client.messages.create(**kwargs)
        text = "".join(
            block.text for block in msg.content if getattr(block, "type", None) == "text"
        )
        usage = getattr(msg, "usage", None)
        return Completion(
            text=text,
            model=model,
            input_tokens=getattr(usage, "input_tokens", 0) or 0,
            output_tokens=getattr(usage, "output_tokens", 0) or 0,
        )


@register_provider("anthropic")
def _build(api_key: str | None = None) -> AnthropicProvider:
    return AnthropicProvider(api_key)
