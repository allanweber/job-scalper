"""Server-side admin sessions (ADR 0010).

The admin cookie holds only an opaque session id; the session payload (admin user
id + email) lives server-side. Redis is the production store (shared across admin
replicas, TTL-expiring); an in-memory store backs local/CI where no Redis is
configured. Both implement the same tiny `SessionStore` interface.
"""

from __future__ import annotations

import json
import secrets
import time
from typing import Any, Protocol


class SessionStore(Protocol):
    def create(self, data: dict[str, Any]) -> str: ...
    def get(self, sid: str) -> dict[str, Any] | None: ...
    def delete(self, sid: str) -> None: ...


def _new_sid() -> str:
    return secrets.token_urlsafe(32)


class MemorySessionStore:
    """Process-local sessions (local dev / CI / tests). Not shared across replicas."""

    def __init__(self, *, ttl_seconds: int = 60 * 60 * 12):
        self._ttl = ttl_seconds
        self._data: dict[str, tuple[float, dict[str, Any]]] = {}

    def create(self, data: dict[str, Any]) -> str:
        sid = _new_sid()
        self._data[sid] = (time.time() + self._ttl, dict(data))
        return sid

    def get(self, sid: str) -> dict[str, Any] | None:
        item = self._data.get(sid)
        if item is None:
            return None
        expires, data = item
        if time.time() > expires:
            self._data.pop(sid, None)
            return None
        return dict(data)

    def delete(self, sid: str) -> None:
        self._data.pop(sid, None)


class RedisSessionStore:  # pragma: no cover - requires Redis
    """Redis-backed sessions keyed `admin_session:<sid>` with a TTL."""

    def __init__(self, redis: Any, *, ttl_seconds: int = 60 * 60 * 12,
                 prefix: str = "admin_session:"):
        self._r = redis
        self._ttl = ttl_seconds
        self._prefix = prefix

    def create(self, data: dict[str, Any]) -> str:
        sid = _new_sid()
        self._r.setex(self._prefix + sid, self._ttl, json.dumps(data))
        return sid

    def get(self, sid: str) -> dict[str, Any] | None:
        raw = self._r.get(self._prefix + sid)
        if raw is None:
            return None
        return json.loads(raw)

    def delete(self, sid: str) -> None:
        self._r.delete(self._prefix + sid)


def build_session_store(redis_url: str | None) -> SessionStore:
    """Redis store when a URL is configured, else the in-memory fallback."""
    if redis_url:
        from redis import Redis  # pragma: no cover

        return RedisSessionStore(Redis.from_url(redis_url))
    return MemorySessionStore()
