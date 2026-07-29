"""OpenAI-backed LLM provider (BYO keys; ADR 0009).

Mirrors `anthropic_provider`: optional (`[api]`/`openai` extra), lazily imported,
and fails soft to ``None`` through `build_provider` when the SDK or key is absent.
Used when a user brings their own OpenAI key; the platform key is Anthropic.
"""

from __future__ import annotations

import importlib.util
import os

from scalper.llm.base import Completion, register_provider


def openai_available() -> bool:
    return importlib.util.find_spec("openai") is not None


class OpenAIProvider:
    name = "openai"

    def __init__(self, api_key: str | None = None) -> None:
        if not openai_available():
            raise RuntimeError("openai SDK not installed; `pip install -e '.[api]'`")
        key = api_key or os.environ.get("OPENAI_API_KEY")
        if not key:
            raise RuntimeError("no API key — pass a BYO key or set OPENAI_API_KEY")
        from openai import OpenAI

        self._client = OpenAI(api_key=key)

    def complete(
        self,
        prompt: str,
        *,
        model: str,
        system: str | None = None,
        max_tokens: int = 1024,
        temperature: float = 0.2,
    ) -> Completion:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        resp = self._client.chat.completions.create(
            model=model,
            messages=messages,
            max_tokens=max_tokens,
            temperature=temperature,
        )
        text = resp.choices[0].message.content or ""
        usage = getattr(resp, "usage", None)
        return Completion(
            text=text,
            model=model,
            input_tokens=getattr(usage, "prompt_tokens", 0) or 0,
            output_tokens=getattr(usage, "completion_tokens", 0) or 0,
        )


@register_provider("openai")
def _build(api_key: str | None = None) -> OpenAIProvider:
    return OpenAIProvider(api_key)
