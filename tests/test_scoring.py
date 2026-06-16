from datetime import datetime, timedelta, timezone

from scalper.config import Profile, Weights
from scalper.models import JobPosting
from scalper.scoring import passes_filters, score_all, score_posting


def _posting(**kw):
    base = dict(
        source="test:co", source_id="1", url="https://x", company="Co",
        title="Backend Engineer", description="We use Python, Postgres and Docker on AWS.",
        remote=True, published_at=datetime.now(timezone.utc),
    )
    base.update(kw)
    return JobPosting(**base)


def _profile(**kw):
    base = dict(
        titles=["backend engineer"],
        required_skills=["python", "postgres", "docker", "aws", "kafka"],
        weights=Weights(skill_coverage=1.0, title_match=0.0, keyword=0.0, semantic=0.0),
    )
    base.update(kw)
    return Profile(**base)


def test_skill_coverage_is_fraction_of_required_found():
    s = score_posting(_profile(), _posting())
    # 4 of 5 skills present (kafka missing)
    assert s.breakdown.skill_coverage == 0.8
    assert set(s.matched_skills) == {"python", "postgres", "docker", "aws"}
    assert s.missing_skills == ["kafka"]
    assert s.percent == 80


def test_word_boundary_avoids_substring_false_positive():
    p = _profile(required_skills=["go"])
    # "go" must not match inside "category"
    s = score_posting(p, _posting(description="We work on category systems."))
    assert s.breakdown.skill_coverage == 0.0


def test_title_full_match_scores_one():
    p = _profile(weights=Weights(skill_coverage=0.0, title_match=1.0, keyword=0.0, semantic=0.0))
    s = score_posting(p, _posting(title="Senior Backend Engineer"))
    assert s.breakdown.title_match == 1.0


def test_weights_renormalize_over_present_components():
    # semantic has no scorer -> None -> dropped; keyword has no keywords -> None.
    p = _profile(
        keywords=[],
        weights=Weights(skill_coverage=0.45, title_match=0.30, keyword=0.10, semantic=0.15),
    )
    s = score_posting(p, _posting())
    # only skill_coverage(0.8) and title_match(1.0) present
    expected = round(100 * (0.45 * 0.8 + 0.30 * 1.0) / (0.45 + 0.30))
    assert s.percent == expected
    assert "keyword" not in s.breakdown.components()
    assert "semantic" not in s.breakdown.components()


def test_remote_filter_drops_non_remote():
    kept, reason = passes_filters(_profile(remote_only=True), _posting(remote=False))
    assert not kept and reason == "not remote"


def test_exclude_keyword_drops():
    kept, reason = passes_filters(
        _profile(exclude_keywords=["clearance"]),
        _posting(description="Requires security clearance."),
    )
    assert not kept and "clearance" in reason


def test_excludes_cjk_listing_by_default():
    kept, reason = passes_filters(
        _profile(),
        _posting(title="软件工程师", description="后端开发，使用 Python。"),
    )
    assert not kept and "CJK" in reason


def test_keeps_english_title_with_stray_cjk_city():
    # A Chinese city name in an otherwise-English listing stays (below threshold).
    kept, _ = passes_filters(_profile(), _posting(title="Senior Backend Engineer (深圳)"))
    assert kept


def test_exclude_non_latin_can_be_disabled():
    kept, _ = passes_filters(
        _profile(exclude_non_latin=False),
        _posting(title="软件工程师", description="后端开发"),
    )
    assert kept


def test_freshness_window_drops_old_postings():
    old = datetime.now(timezone.utc) - timedelta(days=60)
    kept, reason = passes_filters(_profile(freshness_days=30), _posting(published_at=old))
    assert not kept and reason == "outside freshness window"


def test_score_all_sorts_descending_and_filters():
    good = _posting(source_id="a", title="Backend Engineer")
    bad = _posting(source_id="b", title="Sales Manager", description="No tech here.")
    dropped = _posting(source_id="c", remote=False)
    results = score_all(_profile(), [bad, good, dropped])
    assert [r.posting.source_id for r in results] == ["a", "b"]  # remote-only drops 'c'
    assert results[0].percent >= results[1].percent
