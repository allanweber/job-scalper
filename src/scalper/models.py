"""Canonical domain models — the contract every Source adapter emits (see ADR 0001)."""

from __future__ import annotations

import hashlib
import re
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator

_WS = re.compile(r"\s+")
_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def _normalize(text: str) -> str:
    """Lowercase, collapse non-alphanumerics to single spaces. Used for dedup keys."""
    return _NON_ALNUM.sub(" ", text.lower()).strip()


class SearchQuery(BaseModel):
    """What the user is looking for, passed into every adapter at collect time.

    Job Scalper is company-agnostic: sources are searched by *criteria*, not by
    enumerating employers. Query-based sources (Remotive, Adzuna, LinkedIn, …)
    translate this into their native search request; broad-feed sources that
    can't search server-side use `terms` to filter locally. See ADR 0004.
    """

    #: Free-text query terms (e.g. "python backend", "platform engineer").
    #: Each term is searched independently and results are unioned.
    terms: list[str] = Field(default_factory=list)
    #: Desired location hint (e.g. "remote", "europe"). Interpretation is
    #: source-specific; many sources are remote-only and ignore it.
    location: str | None = None
    #: Whether to restrict to remote roles where the source supports it.
    remote: bool = True
    #: Upper bound on postings to pull from a single source per collect run.
    limit_per_source: int = 100


class JobPosting(BaseModel):
    """A single open position, normalized across all sources.

    This is the load-bearing contract of the whole tool (ADR 0001): adapters
    produce it, the store persists it, scoring reads it, the report renders it.
    Change it deliberately and rarely.
    """

    source: str = Field(description="Adapter name that produced this posting, e.g. 'remotive'.")
    source_id: str = Field(description="Stable id within the source; used for exact within-source dedup.")
    url: str

    company: str
    title: str
    description: str = ""

    location: str | None = None
    remote: bool = False
    timezone: str | None = None

    salary_min: float | None = None
    salary_max: float | None = None
    salary_currency: str | None = None

    published_at: datetime | None = None
    collected_at: datetime | None = None

    raw: dict[str, Any] = Field(default_factory=dict, repr=False)

    @field_validator("description", mode="before")
    @classmethod
    def _none_to_empty(cls, v: Any) -> Any:
        return v or ""

    @property
    def uid(self) -> str:
        """Globally unique key for exact persistence (source + source_id)."""
        return f"{self.source}::{self.source_id}"

    @property
    def dedup_key(self) -> str:
        """Normalized company+title+location key.

        Stored even though cross-source dedup is OFF for now, so enabling it
        later (ADR 0002) is a reporting-only change with no re-collection.
        """
        basis = "|".join(
            _normalize(p) for p in (self.company, self.title, self.location or "")
        )
        return hashlib.sha1(basis.encode("utf-8")).hexdigest()

    @property
    def search_text(self) -> str:
        """Lowercased title+description used by scoring and filters."""
        return _WS.sub(" ", f"{self.title} {self.description}".lower())

    @property
    def salary_display(self) -> str | None:
        if self.salary_min is None and self.salary_max is None:
            return None
        cur = (self.salary_currency or "").strip()
        cur = f"{cur} " if cur else ""
        if self.salary_min is not None and self.salary_max is not None:
            return f"{cur}{self.salary_min:,.0f}–{self.salary_max:,.0f}"
        amount = self.salary_min if self.salary_min is not None else self.salary_max
        return f"{cur}{amount:,.0f}"
