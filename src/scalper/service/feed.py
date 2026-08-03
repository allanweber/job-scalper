"""Per-user match feed over the shared pool (ADR 0011).

The feed is the ranked list of pool postings that match the user's profile, drawn
only from the user's chosen sources (the "3 boards" limit gates *visibility*, not
scraping). Scores are computed deterministically (Stage-1 `scoring`) and persisted
to the per-user overlay so the "new" badge (unseen) and saved/drafted flags work.
Users never scrape; this only reads the pool the scheduler fills.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from scalper.scoring import score_all, score_posting
from scalper.service.content_repos import (
    OverlayRepo,
    PoolPosting,
    PostingRepo,
    ProfileRepo,
    StoredProfile,
    UserSourceRepo,
)
from scalper.service.settings import Settings


@dataclass
class FeedItem:
    posting_id: str
    company: str
    title: str
    url: str
    location: str | None
    remote: bool
    salary_min: float | None
    salary_max: float | None
    salary_currency: str | None
    published_at: str | None
    score: int
    matched_skills: list[str]
    missing_skills: list[str]
    matched_keywords: list[str]
    sources: list[str]
    is_new: bool
    saved: bool
    drafted: bool
    applied: bool = False
    breakdown: dict[str, float] = field(default_factory=dict)


@dataclass
class PostingDetail:
    """A single posting with its full text and the user's match breakdown."""

    posting_id: str
    company: str
    title: str
    url: str
    description: str
    location: str | None
    remote: bool
    timezone: str | None
    salary_min: float | None
    salary_max: float | None
    salary_currency: str | None
    published_at: str | None
    score: int
    matched_skills: list[str]
    missing_skills: list[str]
    matched_keywords: list[str]
    sources: list[str]
    is_new: bool
    saved: bool
    drafted: bool
    applied: bool = False
    breakdown: dict[str, float] = field(default_factory=dict)


class FeedService:
    def __init__(self, conn: Any, settings: Settings):
        self._conn = conn
        self._settings = settings
        self._postings = PostingRepo(conn)
        self._overlay = OverlayRepo(conn)
        self._profiles = ProfileRepo(conn)
        self._sources = UserSourceRepo(conn)

    def allowed_sources(self, user_id: str) -> list[str]:
        """The user's chosen boards, or the platform defaults if none chosen yet."""
        chosen = self._sources.list_for(user_id)
        if chosen:
            return chosen
        return list(self._settings.get("sources.default", []) or [])

    def build(self, user_id: str, *, profile: StoredProfile | None = None,
              limit: int = 100, min_score: int = 1,
              candidate_limit: int = 500) -> list[FeedItem]:
        """Score the user's visible pool and return ranked feed items.

        Persists each score to the overlay (setting first_matched_at on first
        match) so ordering and the "new" badge are stable across calls.
        """
        profile = profile or self._profiles.primary_for(user_id)
        if profile is None:
            return []
        sources = self.allowed_sources(user_id)
        candidates = self._postings.candidates_for_sources(sources, limit=candidate_limit)
        if not candidates:
            return []

        by_id = {c.id: c for c in candidates}
        scored = score_all(profile.criteria(), [c.to_job_posting() for c in candidates])

        overlays = self._overlay.get_many(user_id, list(by_id))
        items: list[FeedItem] = []
        for s in scored:
            if s.percent < min_score:
                continue
            pid = s.posting.source_id
            pool = by_id[pid]
            self._overlay.upsert_score(user_id, pid, s.percent,
                                       s.breakdown.model_dump())
            ov = overlays.get(pid)
            items.append(FeedItem(
                posting_id=pid, company=pool.company, title=pool.title, url=pool.url,
                location=pool.location, remote=pool.remote, salary_min=pool.salary_min,
                salary_max=pool.salary_max, salary_currency=pool.salary_currency,
                published_at=pool.published_at, score=s.percent,
                matched_skills=s.matched_skills, missing_skills=s.missing_skills,
                matched_keywords=s.matched_keywords, sources=pool.sources,
                is_new=(ov is None or ov.seen_at is None),
                saved=bool(ov and ov.saved),
                drafted=bool(ov and ov.drafted_at),
                applied=bool(ov and ov.applied_at),
                breakdown=s.breakdown.components(),
            ))
            if len(items) >= limit:
                break
        return items

    def detail(self, user_id: str, posting: PoolPosting,
               *, profile: StoredProfile | None = None) -> PostingDetail:
        """Full posting text + this user's match breakdown and overlay flags.

        Unlike `build`, this scores a single posting regardless of the user's
        source filter, so it also backs postings reached by URL import.
        """
        profile = profile or self._profiles.primary_for(user_id)
        s = score_posting(profile.criteria(), posting.to_job_posting()) if profile else None
        if s is not None:
            self._overlay.upsert_score(user_id, posting.id, s.percent,
                                       s.breakdown.model_dump())
        ov = self._overlay.get_many(user_id, [posting.id]).get(posting.id)
        return PostingDetail(
            posting_id=posting.id, company=posting.company, title=posting.title,
            url=posting.url, description=posting.description, location=posting.location,
            remote=posting.remote, timezone=posting.timezone,
            salary_min=posting.salary_min, salary_max=posting.salary_max,
            salary_currency=posting.salary_currency, published_at=posting.published_at,
            score=s.percent if s else 0,
            matched_skills=s.matched_skills if s else [],
            missing_skills=s.missing_skills if s else [],
            matched_keywords=s.matched_keywords if s else [],
            sources=posting.sources,
            is_new=(ov is None or ov.seen_at is None),
            saved=bool(ov and ov.saved),
            drafted=bool(ov and ov.drafted_at),
            applied=bool(ov and ov.applied_at),
            breakdown=s.breakdown.components() if s else {},
        )
