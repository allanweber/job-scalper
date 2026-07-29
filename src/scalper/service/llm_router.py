"""Route an LLM request to the platform key or the user's BYO key (ADR 0009).

Every user starts on a **platform-provided** key (operator pays), subject to hard
monthly quotas. Adding a valid personal Anthropic/OpenAI key flips the user to
**BYO** for all LLM work: it runs on their tokens, lifts the LLM quota (the caller
passes `unlimited=True` to the quota engine), and uses the admin-configured
higher-quality model. Model IDs are hot settings (`llm.platform_models` /
`llm.byo_models`); the per-request token ceiling (`llm.per_request_token_ceiling`)
is a backstop applied to output length.

The provider is built lazily and injectably (`provider_builder`) so tests never
need a real SDK or network. Actions map to a model *slot*: 'enrich' -> the cheap
enrich model; 'draft'/'profile_build' -> the better draft model.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Callable

from scalper.llm import build_provider
from scalper.llm.base import LLMProvider
from scalper.service.content_repos import LLMUsageRepo
from scalper.service.crypto import KeyVault
from scalper.service.repositories import LLMCredentialRepo
from scalper.service.settings import Settings

#: Preference order for a user's BYO providers when more than one key is valid.
_BYO_PREFERENCE = ("anthropic", "openai")

#: Which model slot ('enrich' | 'draft') an action uses.
_ACTION_SLOT = {"enrich": "enrich", "draft": "draft", "profile_build": "draft"}

#: Fallbacks if a hot setting is missing/misconfigured (keeps jobs runnable).
_PLATFORM_FALLBACK = {"anthropic": {"enrich": "claude-haiku-4-5", "draft": "claude-haiku-4-5"}}
_BYO_FALLBACK = {
    "anthropic": {"enrich": "claude-haiku-4-5", "draft": "claude-sonnet-4-6"},
    "openai": {"enrich": "gpt-4o-mini", "draft": "gpt-4o"},
}


class LLMUnavailable(RuntimeError):
    """No usable LLM provider could be built (missing platform key / SDK)."""


@dataclass
class LLMDecision:
    provider: LLMProvider
    provider_name: str
    model: str
    key_source: str          # 'platform' | 'byo'
    unlimited: bool          # BYO => quota never blocks (still recorded)
    max_output_tokens: int


class LLMRouter:
    """Resolves which provider/model/key a user's LLM action should run on."""

    def __init__(self, conn: Any, settings: Settings, vault: KeyVault | None, *,
                 environ: dict[str, str] | None = None,
                 provider_builder: Callable[..., LLMProvider | None] = build_provider):
        self._conn = conn
        self._settings = settings
        self._vault = vault
        self._env = environ if environ is not None else os.environ
        self._build = provider_builder
        self._creds = LLMCredentialRepo(conn)

    # -- model selection --

    def _slot(self, action: str) -> str:
        try:
            return _ACTION_SLOT[action]
        except KeyError:
            raise ValueError(f"unknown LLM action: {action!r}") from None

    def _model(self, key_source: str, provider: str, slot: str) -> str:
        setting_key = "llm.byo_models" if key_source == "byo" else "llm.platform_models"
        fallback = _BYO_FALLBACK if key_source == "byo" else _PLATFORM_FALLBACK
        models = self._settings.get(setting_key, {}) or {}
        by_provider = models.get(provider) or fallback.get(provider, {})
        return by_provider.get(slot) or fallback.get(provider, {}).get(slot, "")

    def token_ceiling(self) -> int:
        try:
            return int(self._settings.get("llm.per_request_token_ceiling", 20000))
        except (TypeError, ValueError):
            return 20000

    # -- resolution --

    def _try_byo(self, user_id: str, slot: str) -> LLMDecision | None:
        if self._vault is None:
            return None
        for provider_name in _BYO_PREFERENCE:
            if not self._creds.has_valid(user_id, provider_name):
                continue
            sealed = self._creds.get_sealed(user_id, provider_name)
            if sealed is None:
                continue
            try:
                api_key = self._vault.open(sealed)
            except Exception:  # noqa: BLE001 — undecryptable key: skip, fall through
                continue
            provider = self._build(provider_name, api_key=api_key)
            if provider is None:
                continue
            return LLMDecision(
                provider=provider, provider_name=provider_name,
                model=self._model("byo", provider_name, slot),
                key_source="byo", unlimited=True,
                max_output_tokens=self.token_ceiling(),
            )
        return None

    def _platform(self, slot: str) -> LLMDecision:
        provider_name = self._env.get("SCALPER_PLATFORM_LLM_PROVIDER", "anthropic")
        api_key = self._env.get("SCALPER_PLATFORM_ANTHROPIC_KEY") or \
            self._env.get("SCALPER_PLATFORM_LLM_KEY")
        provider = self._build(provider_name, api_key=api_key)
        if provider is None:
            raise LLMUnavailable(
                "platform LLM provider unavailable — set SCALPER_PLATFORM_ANTHROPIC_KEY "
                "and install the LLM SDK, or add a personal key."
            )
        return LLMDecision(
            provider=provider, provider_name=provider_name,
            model=self._model("platform", provider_name, slot),
            key_source="platform", unlimited=False,
            max_output_tokens=self.token_ceiling(),
        )

    def resolve(self, user_id: str, action: str) -> LLMDecision:
        """Pick BYO if the user has a valid key, else the platform key."""
        slot = self._slot(action)
        byo = self._try_byo(user_id, slot)
        return byo if byo is not None else self._platform(slot)

    def record_usage(self, user_id: str, *, action: str, decision: LLMDecision,
                     input_tokens: int, output_tokens: int,
                     job_id: str | None = None) -> None:
        LLMUsageRepo(self._conn).record(
            user_id, action=action, provider=decision.provider_name,
            model=decision.model, key_source=decision.key_source,
            input_tokens=input_tokens, output_tokens=output_tokens, job_id=job_id,
        )
