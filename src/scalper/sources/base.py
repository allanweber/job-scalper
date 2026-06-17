"""Source adapter contract and registry (ADR 0001 / ADR 0004).

Every Source is a self-contained adapter exposing
`fetch(query) -> list[JobPosting]`. Sources are company-agnostic: they are
searched by the user's `SearchQuery`, not by enumerating employers. The adapter
owns all source-specific concerns (auth/pagination/parsing/native-filtering) and
returns already-normalized postings. The core stays source-agnostic; adding a
source is one new module that registers itself.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Callable

import httpx

from scalper.models import JobPosting, SearchQuery

# Tier labels (see CONTEXT.md): structured sources have official APIs/feeds;
# hard sources resist automation (scraped, anonymous-only).
TIER_STRUCTURED = "structured"
TIER_HARD = "hard"


def _noop(_msg: str) -> None:
    pass


class SourceAdapter(ABC):
    """Base class for all source adapters."""

    #: Stable adapter type key used in config (`type:` field) and the registry.
    type: str = ""
    #: Which acquisition tier this adapter belongs to.
    tier: str = TIER_STRUCTURED
    #: Optional fetch logger; set by build_adapter when verbose_sources is on.
    _log: Callable[[str], None] = staticmethod(_noop)

    @property
    @abstractmethod
    def name(self) -> str:
        """Human/storage-facing source name, e.g. 'remotive'."""

    @abstractmethod
    def fetch(self, query: SearchQuery) -> list[JobPosting]:
        """Search the source for `query` and return normalized postings.

        Query-based sources translate `query` into a native search request;
        broad-feed sources that can't search server-side pull recent postings
        and filter locally using `query.terms`.
        """

    def _client(self, timeout: float = 30.0, **kwargs: Any) -> httpx.Client:
        """Return an httpx.Client, wiring request/response log hooks when verbose."""
        hooks: dict[str, list] = {}
        if self._log is not _noop:
            name = self.name

            def _on_request(req: httpx.Request) -> None:
                self._log(f"{name}  →  {req.method} {req.url}")

            def _on_response(resp: httpx.Response) -> None:
                size = resp.headers.get("content-length")
                kb = f"  {int(size) / 1024:.1f} KB" if size else ""
                self._log(f"{name}  ←  {resp.status_code}{kb}")

            hooks = {"request": [_on_request], "response": [_on_response]}
        return httpx.Client(timeout=timeout, follow_redirects=True,
                            event_hooks=hooks, **kwargs)


# type -> factory(**params) -> SourceAdapter
REGISTRY: dict[str, Callable[..., SourceAdapter]] = {}


def register(adapter_cls: type[SourceAdapter]) -> type[SourceAdapter]:
    """Class decorator that registers an adapter under its `type`."""
    key = adapter_cls.type
    if not key:
        raise ValueError(f"{adapter_cls.__name__} must set a non-empty `type`.")
    REGISTRY[key] = adapter_cls
    return adapter_cls


def build_adapter(
    stype: str,
    params: dict[str, Any],
    logger: Callable[[str], None] | None = None,
) -> SourceAdapter:
    """Instantiate an adapter from a Source Definition."""
    try:
        factory = REGISTRY[stype]
    except KeyError:
        known = ", ".join(sorted(REGISTRY)) or "(none)"
        raise KeyError(f"Unknown source type '{stype}'. Registered: {known}") from None
    adapter = factory(**params)
    if logger is not None:
        adapter._log = logger
    return adapter
