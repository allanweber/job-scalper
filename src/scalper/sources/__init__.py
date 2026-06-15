"""Source adapters. Import side-effects register each adapter in the registry."""

from scalper.sources.base import REGISTRY, SourceAdapter, build_adapter, register

# Register built-in adapters by importing them.
from scalper.sources import (  # noqa: E402,F401
    adzuna,
    arbeitnow,
    hackernews,
    himalayas,
    indeed,
    jobicy,
    linkedin,
    reddit,
    remoteok,
    remotive,
    themuse,
    weworkremotely,
    workingnomads,
)

__all__ = ["REGISTRY", "SourceAdapter", "build_adapter", "register"]
