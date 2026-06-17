"""Tests for Phase 12: Market Insights (no LLM, no profile argument).

Covers: skill-demand ranking, salary stats (native + enriched fallback, ignoring
unparsed rows), per-source counts, weekly volume, and the --since filter.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from scalper.insights import compute_insights, format_insights
from scalper.models import JobPosting
from scalper.store import JobStore

_NOW = datetime.now(timezone.utc)
_WEEK_AGO = _NOW - timedelta(weeks=1)
_MONTH_AGO = _NOW - timedelta(days=30)


def _posting(n: int = 1, **kw) -> JobPosting:
    base = dict(
        source="remotive",
        source_id=str(n),
        url="https://x",
        company="Co",
        title="Backend Engineer",
        remote=True,
        description="We build distributed systems in Python and Postgres.",
        collected_at=_NOW,
    )
    base.update(kw)
    return JobPosting(**base)


# --- skill demand -----------------------------------------------------------

def test_skill_demand_ranks_by_count(tmp_path):
    postings = [
        _posting(n=1, description="We use Python and Docker"),
        _posting(n=2, description="FastAPI and Kubernetes environment"),
        _posting(n=3, description="Docker containers for Go services"),
    ]
    db = tmp_path / "s.db"
    with JobStore(db) as store:
        store.upsert_many(postings)
        data = compute_insights(store, skills=["python", "docker", "kubernetes"])

    counts = {h.skill: h.count for h in data.skill_demand}
    assert counts["python"] == 1
    assert counts["docker"] == 2
    assert counts["kubernetes"] == 1
    # docker appears most; kubernetes last (tied with python, falls after alphabetically)
    assert data.skill_demand[0].skill == "docker"


def test_skill_demand_omits_zero_count_skills(tmp_path):
    db = tmp_path / "s.db"
    with JobStore(db) as store:
        store.upsert_many([_posting(n=1, description="Only python here")])
        data = compute_insights(store, skills=["python", "cobol"])

    skill_names = [h.skill for h in data.skill_demand]
    assert "python" in skill_names
    assert "cobol" not in skill_names


def test_no_skills_gives_empty_demand(tmp_path):
    db = tmp_path / "s.db"
    with JobStore(db) as store:
        store.upsert_many([_posting()])
        data = compute_insights(store, skills=None)

    assert data.skill_demand == []


# --- salary stats -----------------------------------------------------------

def test_salary_ignores_rows_without_salary(tmp_path):
    postings = [
        _posting(n=1, salary_min=80_000, salary_max=120_000, salary_currency="USD"),
        _posting(n=2),  # no salary
        _posting(n=3, salary_min=60_000, salary_currency="USD"),
    ]
    db = tmp_path / "s.db"
    with JobStore(db) as store:
        store.upsert_many(postings)
        data = compute_insights(store, skills=[])

    assert data.salary is not None
    assert data.salary.count == 2
    assert data.salary.min == pytest.approx(60_000)
    assert data.salary.max == pytest.approx(100_000)  # midpoint of 80k-120k


def test_salary_uses_enrichment_fallback(tmp_path):
    posting = _posting(n=1)  # no native salary
    db = tmp_path / "s.db"
    with JobStore(db) as store:
        store.upsert_many([posting])
        # Insert a fake enrichment with salary data
        enr_json = json.dumps({
            "remote": True,
            "seniority": "mid",
            "salary_range": {"min": 90000, "max": 130000, "currency": "USD"},
            "timezone_requirement": None,
        })
        store.put_enrichments("hash1", "model1/v2", [(posting.uid, enr_json)])
        data = compute_insights(store, skills=[])

    assert data.salary is not None
    assert data.salary.count == 1
    assert data.salary.min == pytest.approx(110_000)  # midpoint of 90k-130k


def test_salary_none_when_no_data(tmp_path):
    db = tmp_path / "s.db"
    with JobStore(db) as store:
        store.upsert_many([_posting()])
        data = compute_insights(store, skills=[])

    assert data.salary is None


# --- source counts ----------------------------------------------------------

def test_source_counts_aggregated_correctly(tmp_path):
    postings = [
        _posting(n=1, source="remotive"),
        _posting(n=2, source="remotive"),
        _posting(n=3, source="jobicy"),
    ]
    db = tmp_path / "s.db"
    with JobStore(db) as store:
        store.upsert_many(postings)
        data = compute_insights(store, skills=[])

    assert data.source_counts["remotive"] == 2
    assert data.source_counts["jobicy"] == 1
    # Sorted descending by count
    assert list(data.source_counts.keys())[0] == "remotive"


# --- weekly volume ----------------------------------------------------------

def test_weekly_volume_groups_by_iso_week(tmp_path):
    postings = [
        _posting(n=1, collected_at=_NOW),
        _posting(n=2, collected_at=_NOW),
        _posting(n=3, collected_at=_WEEK_AGO),
    ]
    db = tmp_path / "s.db"
    with JobStore(db) as store:
        store.upsert_many(postings)
        data = compute_insights(store, skills=[])

    total_in_weeks = sum(n for _, n in data.weekly_volume)
    assert total_in_weeks == 3
    # Two distinct weeks
    assert len(data.weekly_volume) == 2


def test_weekly_volume_capped_at_8(tmp_path):
    # Create 10 postings spread over 10 different ISO weeks
    postings = [
        _posting(n=i, collected_at=_NOW - timedelta(weeks=i))
        for i in range(10)
    ]
    db = tmp_path / "s.db"
    with JobStore(db) as store:
        store.upsert_many(postings)
        data = compute_insights(store, skills=[])

    assert len(data.weekly_volume) <= 8


# --- since filter -----------------------------------------------------------

def test_since_excludes_older_collected_postings(tmp_path):
    postings = [
        _posting(n=1, collected_at=_NOW),        # recent
        _posting(n=2, collected_at=_MONTH_AGO),  # old
    ]
    db = tmp_path / "s.db"
    with JobStore(db) as store:
        store.upsert_many(postings)
        cutoff = _NOW - timedelta(days=7)
        data = compute_insights(store, since=cutoff, skills=[])

    assert data.total == 1


def test_since_none_includes_all(tmp_path):
    postings = [
        _posting(n=1, collected_at=_NOW),
        _posting(n=2, collected_at=_MONTH_AGO),
    ]
    db = tmp_path / "s.db"
    with JobStore(db) as store:
        store.upsert_many(postings)
        data = compute_insights(store, since=None, skills=[])

    assert data.total == 2


# --- formatting -------------------------------------------------------------

def test_format_includes_all_sections(tmp_path):
    postings = [
        _posting(n=1, source="remotive", salary_min=80_000, salary_max=120_000, salary_currency="USD"),
    ]
    db = tmp_path / "s.db"
    with JobStore(db) as store:
        store.upsert_many(postings)
        data = compute_insights(store, skills=["python"])

    text = format_insights(data)
    assert "Market Insights" in text
    assert "Skill demand" in text
    assert "Salary distribution" in text
    assert "Postings by source" in text
    assert "Weekly volume" in text
    assert "remotive" in text
