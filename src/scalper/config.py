"""Configuration loading: global settings, sources, and named search Profiles."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, Field

from scalper.models import SearchQuery


class Weights(BaseModel):
    skill_coverage: float = 0.45
    title_match: float = 0.30
    keyword: float = 0.10
    semantic: float = 0.15


class Profile(BaseModel):
    """A named set of Search Criteria."""

    titles: list[str] = Field(default_factory=list)
    required_skills: list[str] = Field(default_factory=list)
    nice_to_have_skills: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    exclude_keywords: list[str] = Field(default_factory=list)

    remote_only: bool = True
    salary_floor: float = 0.0
    freshness_days: int | None = 30

    weights: Weights = Field(default_factory=Weights)


class SourceConfig(BaseModel):
    """A Source Definition: which adapter to build and its parameters."""

    type: str
    # Optional per-source override of the global `search.limit_per_source`, so a
    # high-volume source (e.g. hackernews) can't dominate the store.
    limit: int | None = None
    # Remaining keys are adapter-specific (e.g. `category` for remotive).
    params: dict[str, Any] = Field(default_factory=dict)


class Config(BaseModel):
    database: str = "scalper.db"
    # The global search spec that drives every source at collect time (ADR 0005).
    search: SearchQuery = Field(default_factory=SearchQuery)
    sources: list[SourceConfig] = Field(default_factory=list)
    profiles: dict[str, Profile] = Field(default_factory=dict)

    def profile(self, name: str) -> Profile:
        try:
            return self.profiles[name]
        except KeyError:
            available = ", ".join(sorted(self.profiles)) or "(none)"
            raise KeyError(f"Unknown profile '{name}'. Available: {available}") from None


def _parse_source(raw: dict[str, Any]) -> SourceConfig:
    raw = dict(raw)
    stype = raw.pop("type")
    limit = raw.pop("limit", None)
    return SourceConfig(type=stype, limit=limit, params=raw)


def load_config(path: str | Path) -> Config:
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(
            f"Config not found at {path}. Copy config.example.yaml to config.yaml and edit it."
        )
    data = yaml.safe_load(path.read_text()) or {}
    sources = [_parse_source(s) for s in data.get("sources", [])]
    profiles = {name: Profile.model_validate(p) for name, p in data.get("profiles", {}).items()}
    return Config(
        database=data.get("database", "scalper.db"),
        search=SearchQuery.model_validate(data.get("search", {})),
        sources=sources,
        profiles=profiles,
    )
