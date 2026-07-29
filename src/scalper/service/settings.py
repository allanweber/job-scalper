"""Hot-applied settings backed by the `settings` table (ADR 0010).

Runtime configuration (scrape interval, quotas, enabled sources, models,
maintenance flag) lives in the DB and is edited from the admin app. Readers get
a short in-process TTL cache so a busy path doesn't hit the DB every call, while
an admin edit still takes effect within a few seconds. Secrets never live here —
they stay in the environment.
"""

from __future__ import annotations

import json
import threading
import time
from typing import Any, Callable

from scalper.service.models import now_iso

_DEFAULT_TTL_SECONDS = 5.0


class Settings:
    def __init__(self, conn: Any, *, ttl_seconds: float = _DEFAULT_TTL_SECONDS,
                 clock: Callable[[], float] = time.monotonic):
        self._conn = conn
        self._ttl = ttl_seconds
        self._clock = clock
        self._cache: dict[str, Any] | None = None
        self._loaded_at = 0.0
        self._lock = threading.Lock()

    def _fresh(self) -> bool:
        return self._cache is not None and (self._clock() - self._loaded_at) < self._ttl

    def _load(self) -> dict[str, Any]:
        rows = self._conn.execute("SELECT key, value FROM settings").fetchall()
        cache: dict[str, Any] = {}
        for row in rows:
            key, value = row[0], row[1]
            try:
                cache[key] = json.loads(value)
            except (json.JSONDecodeError, TypeError):
                cache[key] = value
        return cache

    def _ensure(self) -> dict[str, Any]:
        if self._fresh():
            return self._cache  # type: ignore[return-value]
        with self._lock:
            if self._fresh():
                return self._cache  # type: ignore[return-value]
            self._cache = self._load()
            self._loaded_at = self._clock()
            return self._cache

    def get(self, key: str, default: Any = None) -> Any:
        return self._ensure().get(key, default)

    def all(self) -> dict[str, Any]:
        return dict(self._ensure())

    def set(self, key: str, value: Any, *, updated_by: str | None = None) -> None:
        """Upsert a setting (JSON-encoded) and invalidate the cache."""
        self._conn.execute(
            "INSERT INTO settings (key, value, updated_at, updated_by) VALUES (?, ?, ?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value, "
            "updated_at=excluded.updated_at, updated_by=excluded.updated_by",
            (key, json.dumps(value), now_iso(), updated_by),
        )
        self._conn.commit()
        self.invalidate()

    def invalidate(self) -> None:
        with self._lock:
            self._cache = None
