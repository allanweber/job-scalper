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
    #: Drop postings written predominantly in CJK (Chinese/Japanese/Korean)
    #: script — i.e. non-English listings. On by default; set false to keep them.
    exclude_non_latin: bool = True

    weights: Weights = Field(default_factory=Weights)


class LLMConfig(BaseModel):
    """LLM settings: provider, per-task models, and enrichment config."""

    #: Provider key in the LLM registry (currently only "anthropic").
    provider: str = "anthropic"
    #: Cheap model for per-job enrichment (summary + skill-gap).
    enrich_model: str = "claude-haiku-4-5"
    #: Model used by `scalper draft` and `scalper profile from-resume`.
    draft_model: str = "claude-sonnet-4-6"
    #: How many top-scored postings to enrich per report.
    top_n: int = 10
    #: Enrich without needing the `--enrich` flag when true.
    enabled: bool = False
    #: Override USD price per 1M tokens for cost reporting. When unset, a built-in
    #: estimate table is used (and "n/a" is shown if the model is unknown).
    input_price_per_mtok: float | None = None
    output_price_per_mtok: float | None = None


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
    # The global search spec that drives every source at collect time .
    search: SearchQuery = Field(default_factory=SearchQuery)
    sources: list[SourceConfig] = Field(default_factory=list)
    profiles: dict[str, Profile] = Field(default_factory=dict)
    llm: LLMConfig = Field(default_factory=LLMConfig)
    #: Default folder `scalper draft` saves its `[profile]_[position]_[uid].md`
    #: files into. `--out` overrides it; if neither is set, files save to the
    #: current directory.
    draft_output_dir: str | None = None
    #: Oldest posting worth collecting or scoring. Postings published before this
    #: many days ago are dropped at collect time and at report time. None = no limit.
    freshness_days: int | None = 3
    #: When true, every HTTP request/response made by a source adapter is logged
    #: to stderr during `collect` and `digest`. False by default.
    verbose_sources: bool = False

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
        llm=LLMConfig.model_validate(data.get("llm", {})),
        draft_output_dir=data.get("draft_output_dir"),
        freshness_days=data.get("freshness_days", 3),
        verbose_sources=data.get("verbose_sources", False),
    )
