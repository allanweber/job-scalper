"""Phase 5: store counts, `--since` parsing, and report rendering of the new
cross-source-dedup and timezone-fallback fields."""

from datetime import datetime, timezone

import pytest

from scalper.cli import _parse_since
from scalper.config import Profile, Weights
from scalper.models import JobPosting
from scalper.report import ReportPanel, render_combined_report, render_report
from scalper.scoring import ScoreBreakdown, ScoredPosting
from scalper.store import JobStore


def _posting(**kw):
    base = dict(
        source="remotive", source_id="1", url="https://x", company="Co",
        title="Backend Engineer", description="Python.", remote=True,
    )
    base.update(kw)
    return JobPosting(**base)


def _scored(posting, **kw):
    base = dict(
        posting=posting, percent=80, breakdown=ScoreBreakdown(skill_coverage=0.8),
        matched_skills=["python"], missing_skills=[], matched_nice_to_have=[],
        matched_keywords=[],
    )
    base.update(kw)
    return ScoredPosting(**base)


# --- store.counts_by_source ------------------------------------------------

def test_counts_by_source(tmp_path):
    db = tmp_path / "s.db"
    with JobStore(db) as store:
        store.upsert_many([
            _posting(source="remotive", source_id="1"),
            _posting(source="remotive", source_id="2"),
            _posting(source="linkedin", source_id="3"),
        ])
        assert store.counts_by_source() == {"linkedin": 1, "remotive": 2}


def test_counts_by_source_empty(tmp_path):
    with JobStore(tmp_path / "s.db") as store:
        assert store.counts_by_source() == {}


# --- --since parsing -------------------------------------------------------

def test_parse_since_day_count():
    cutoff = _parse_since("7")
    delta = datetime.now(timezone.utc) - cutoff
    assert 6.9 < delta.days + delta.seconds / 86400 < 7.1


def test_parse_since_iso_date():
    assert _parse_since("2026-06-01") == datetime(2026, 6, 1, tzinfo=timezone.utc)


def test_parse_since_rejects_garbage():
    with pytest.raises(ValueError):
        _parse_since("last tuesday")


# --- report rendering of Phase 5 fields ------------------------------------

def _profile():
    return Profile(titles=["backend engineer"], required_skills=["python"],
                   weights=Weights(skill_coverage=1.0))


def test_report_renders_also_seen_on():
    s = _scored(_posting(), also_seen_on=["linkedin", "indeed"])
    html = render_report("backend", _profile(), [s])
    assert "also: linkedin, indeed" in html


def test_report_timezone_fallback_from_location():
    # Source supplied no timezone, but the location carries one.
    s = _scored(_posting(location="Remote (UTC+2)", timezone=None))
    html = render_report("backend", _profile(), [s])
    assert "UTC+2" in html


def test_combined_report_has_tab_per_profile():
    s = _scored(_posting())
    html = render_combined_report([
        ReportPanel("backend", _profile(), [s], {}),
        ReportPanel("empty", _profile(), [], {}),
    ])
    # one tab + one panel per profile, including the zero-match one
    assert 'data-target="backend"' in html
    assert 'data-target="empty"' in html
    assert html.count('class="panel"') == 2
    assert "No postings matched this profile" in html
