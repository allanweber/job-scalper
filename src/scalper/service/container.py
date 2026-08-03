"""Service container: the wiring that request handlers and jobs draw from.

Holds process-wide configuration and factories (not a live DB connection — each
request and each job opens its own connection via `conn_factory`, matching how the
Postgres client and the RQ worker run). `from_env` builds the production container;
tests construct one directly with fakes (an injected verifier, a temp-file DB
factory, a stub provider/adapter builder).
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Callable

from scalper.db import connect
from scalper.llm import build_provider
from scalper.service.auth import (
    AdminAllowlist,
    AuthConfig,
    AuthService,
    GoogleIDTokenVerifier,
    IDTokenVerifier,
)
from scalper.service.crypto import KeyVault
from scalper.service.push import NullPushSender, PushSender, build_push_sender
from scalper.service.settings import Settings
from scalper.service.url_import import UrlFetcher, default_url_fetch
from scalper.sources import build_adapter

ConnFactory = Callable[[], Any]


@dataclass
class Container:
    conn_factory: ConnFactory
    verifier: IDTokenVerifier
    allowlist: AdminAllowlist
    auth_config: AuthConfig
    environ: dict[str, str] = field(default_factory=lambda: dict(os.environ))
    vault: KeyVault | None = None
    redis_url: str | None = None
    provider_builder: Callable[..., Any] = build_provider
    adapter_builder: Callable[..., Any] = build_adapter
    url_fetcher: UrlFetcher = default_url_fetch
    push_sender: PushSender = field(default_factory=NullPushSender)
    settings_ttl: float = 5.0

    # -- per-request/-job helpers --

    def connect(self) -> Any:
        return self.conn_factory()

    def settings(self, conn: Any) -> Settings:
        return Settings(conn, ttl_seconds=self.settings_ttl)

    def auth_service(self, conn: Any) -> AuthService:
        return AuthService(conn, verifier=self.verifier, allowlist=self.allowlist,
                           config=self.auth_config)

    @property
    def eager_jobs(self) -> bool:
        """True when no Redis is configured: jobs run inline instead of via RQ."""
        return not self.redis_url

    @classmethod
    def from_env(cls, environ: dict[str, str] | None = None) -> "Container":
        env = dict(environ if environ is not None else os.environ)
        audiences = [a for a in env.get("SCALPER_GOOGLE_AUDIENCES", "").split(",") if a.strip()]
        if not audiences:
            raise RuntimeError("SCALPER_GOOGLE_AUDIENCES (Google client ids) is not set")
        vault: KeyVault | None
        try:
            vault = KeyVault.from_env(env)
        except RuntimeError:
            vault = None  # BYO keys disabled until a master key is configured
        return cls(
            conn_factory=connect,
            verifier=GoogleIDTokenVerifier(audiences),
            allowlist=AdminAllowlist.from_env(env),
            auth_config=AuthConfig.from_env(env),
            environ=env,
            vault=vault,
            redis_url=env.get("SCALPER_REDIS_URL") or env.get("REDIS_URL"),
            push_sender=build_push_sender(env),
        )
