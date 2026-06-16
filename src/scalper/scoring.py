"""Stage 1 scoring: hard filters + deterministic, explainable Match % (ADR 0003).

The headline percentage is a weighted blend of components computed in code, so it is
reproducible and auditable. The LLM enrichment layer (Stage 2) and the semantic
similarity component are added later; `semantic_scorer` is the hook for the latter.
"""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Callable

from pydantic import BaseModel

from scalper.config import Profile
from scalper.models import JobPosting

# Hook: (profile, posting) -> cosine-like similarity in [0,1], or None if unavailable.
SemanticScorer = Callable[[Profile, JobPosting], float | None]


def _aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _contains_term(text: str, term: str) -> bool:
    """Word-boundary match so short skills like 'go' don't match 'category'."""
    term = term.strip().lower()
    if not term:
        return False
    return re.search(rf"\b{re.escape(term)}\b", text) is not None


def _tokens(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", text.lower()))


# CJK scripts: Hiragana/Katakana, CJK ideographs (+ extensions A & compat), Hangul.
# A posting whose text is largely these is a non-English listing.
_CJK = re.compile(r"[぀-ヿ㐀-䶿一-鿿豈-﫿가-힯]")
_LATIN = re.compile(r"[A-Za-z]")


def _is_cjk_dominant(text: str, threshold: float = 0.2) -> bool:
    """True if CJK characters make up at least `threshold` of the letters.

    A stray Chinese city name in an otherwise-English title stays (below the
    threshold); a title/body that's mostly CJK is dropped.
    """
    cjk = len(_CJK.findall(text))
    if not cjk:
        return False
    latin = len(_LATIN.findall(text))
    return cjk / (cjk + latin) >= threshold


class ScoreBreakdown(BaseModel):
    """Per-component scores in [0,1] (None = component not applicable)."""

    skill_coverage: float | None = None
    title_match: float | None = None
    keyword: float | None = None
    semantic: float | None = None

    def components(self) -> dict[str, float]:
        return {k: v for k, v in self.model_dump().items() if v is not None}


class ScoredPosting(BaseModel):
    posting: JobPosting
    percent: int
    breakdown: ScoreBreakdown
    matched_skills: list[str]
    missing_skills: list[str]
    matched_nice_to_have: list[str]
    matched_keywords: list[str]
    #: Other source names the same job was also seen on, set by `dedup_scored`
    #: when cross-source dedup is enabled (empty otherwise).
    also_seen_on: list[str] = []


# --------------------------------------------------------------------------- filters


def passes_filters(profile: Profile, posting: JobPosting, now: datetime | None = None) -> tuple[bool, str]:
    """Hard gates (not score components). Returns (kept, reason_if_dropped)."""
    text = posting.search_text

    if profile.remote_only and not posting.remote:
        return False, "not remote"

    if profile.exclude_non_latin and _is_cjk_dominant(f"{posting.title} {posting.description}"):
        return False, "non-English (CJK) listing"

    for bad in profile.exclude_keywords:
        if _contains_term(text, bad):
            return False, f"excluded keyword: {bad}"

    if profile.salary_floor and posting.salary_max is not None:
        if posting.salary_max < profile.salary_floor:
            return False, "below salary floor"

    if profile.freshness_days is not None and posting.published_at is not None:
        now = now or datetime.now(timezone.utc)
        cutoff = now - timedelta(days=profile.freshness_days)
        if _aware(posting.published_at) < cutoff:
            return False, "outside freshness window"

    return True, ""


# --------------------------------------------------------------------------- scoring


def _skill_coverage(profile: Profile, text: str) -> tuple[float | None, list[str], list[str]]:
    if not profile.required_skills:
        return None, [], []
    matched = [s for s in profile.required_skills if _contains_term(text, s)]
    missing = [s for s in profile.required_skills if s not in matched]
    return len(matched) / len(profile.required_skills), matched, missing


def _title_match(profile: Profile, posting: JobPosting) -> float | None:
    if not profile.titles:
        return None
    title = posting.title.lower()
    title_tokens = _tokens(title)
    best = 0.0
    for pattern in profile.titles:
        p = pattern.strip().lower()
        if p and p in title:
            return 1.0
        ptoks = _tokens(p)
        if ptoks:
            best = max(best, len(ptoks & title_tokens) / len(ptoks))
    return best


def _keyword_match(profile: Profile, text: str) -> tuple[float | None, list[str]]:
    if not profile.keywords:
        return None, []
    matched = [k for k in profile.keywords if _contains_term(text, k)]
    return len(matched) / len(profile.keywords), matched


def score_posting(
    profile: Profile,
    posting: JobPosting,
    semantic_scorer: SemanticScorer | None = None,
) -> ScoredPosting:
    text = posting.search_text

    coverage, matched_skills, missing_skills = _skill_coverage(profile, text)
    title = _title_match(profile, posting)
    kw, matched_keywords = _keyword_match(profile, text)
    sem = semantic_scorer(profile, posting) if semantic_scorer else None

    matched_nice = [s for s in profile.nice_to_have_skills if _contains_term(text, s)]

    breakdown = ScoreBreakdown(
        skill_coverage=coverage, title_match=title, keyword=kw, semantic=sem
    )

    weights = profile.weights.model_dump()
    present = breakdown.components()
    weight_sum = sum(weights[k] for k in present)
    if weight_sum > 0:
        blended = sum(weights[k] * present[k] for k in present) / weight_sum
    else:
        blended = 0.0

    return ScoredPosting(
        posting=posting,
        percent=round(100 * blended),
        breakdown=breakdown,
        matched_skills=matched_skills,
        missing_skills=missing_skills,
        matched_nice_to_have=matched_nice,
        matched_keywords=matched_keywords,
    )


def score_all(
    profile: Profile,
    postings: list[JobPosting],
    semantic_scorer: SemanticScorer | None = None,
    now: datetime | None = None,
) -> list[ScoredPosting]:
    """Filter then score; returned sorted by Match % descending."""
    now = now or datetime.now(timezone.utc)
    kept = [p for p in postings if passes_filters(profile, p, now)[0]]
    scored = [score_posting(profile, p, semantic_scorer) for p in kept]
    scored.sort(key=lambda s: s.percent, reverse=True)
    return scored


def dedup_scored(scored: list[ScoredPosting]) -> list[ScoredPosting]:
    """Collapse the same job seen on multiple sources into one row (ADR 0002).

    Reporting-only: groups by the posting's stored `dedup_key` (normalized
    company+title+location), keeps the highest-scoring record, and records the
    other sources it appeared on in `also_seen_on`. Input is assumed already
    sorted by Match % descending (as `score_all` returns), so the first record
    seen for a key is the one kept; relative order is otherwise preserved.
    """
    best: dict[str, ScoredPosting] = {}
    order: list[str] = []
    for s in scored:
        key = s.posting.dedup_key
        keep = best.get(key)
        if keep is None:
            best[key] = s
            order.append(key)
            continue
        other = s.posting.source
        if other != keep.posting.source and other not in keep.also_seen_on:
            keep.also_seen_on.append(other)
    return [best[k] for k in order]
