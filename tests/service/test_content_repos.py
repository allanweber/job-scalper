from __future__ import annotations

import pytest
from _helpers import posting

from scalper.service.content_repos import (
    ActiveUsersRepo,
    DraftRepo,
    EnrichmentRepo,
    JobRepo,
    LLMUsageRepo,
    OverlayRepo,
    PostingRepo,
    ProfileRepo,
    ResumeRepo,
    UserSourceRepo,
)
from scalper.service.models import GoogleIdentity
from scalper.service.repositories import UserRepo


@pytest.fixture
def user(conn):
    return UserRepo(conn).upsert_from_google(
        GoogleIdentity(sub="s1", email="u@example.com", name="U"), role="user")


# --- postings pool / storage-time dedup ---

def test_ingest_dedups_by_key_and_keeps_provenance(conn):
    repo = PostingRepo(conn)
    # Same company+title+location from two sources => one physical row, two sources.
    same_a = posting("remotive", "a", company="Acme", title="Python Dev")
    same_b = posting("remoteok", "b", company="Acme", title="Python Dev")
    other = posting("remotive", "c", company="Beta", title="Go Dev")
    stats = repo.ingest([same_a, same_b, other])
    assert stats["new"] == 2          # two distinct dedup_keys
    assert repo.count() == 2
    dedup_id = same_a.dedup_key
    pool = repo.get(dedup_id)
    assert set(pool.sources) == {"remotive", "remoteok"}


def test_ingest_second_run_updates_last_seen(conn):
    repo = PostingRepo(conn)
    p = posting("remotive", "a", company="Acme", title="Python Dev")
    repo.ingest([p])
    before = repo.get(p.dedup_key).last_seen_at
    stats = repo.ingest([p])
    assert stats["new"] == 0 and stats["updated"] == 1
    assert repo.get(p.dedup_key).last_seen_at >= before


def test_counts_by_source(conn):
    repo = PostingRepo(conn)
    repo.ingest([
        posting("remotive", "a", company="Acme", title="Python Dev"),
        posting("remoteok", "b", company="Acme", title="Python Dev"),  # same dedup, 2nd source
        posting("remotive", "c", company="Beta", title="Go Dev"),
    ])
    counts = dict(repo.counts_by_source())
    assert counts == {"remotive": 2, "remoteok": 1}


def test_search_filters_and_paginates(conn):
    repo = PostingRepo(conn)
    repo.ingest([
        posting("remotive", "a", company="Acme", title="Python Dev", remote=True),
        posting("remoteok", "b", company="Beta", title="Go Dev", remote=False),
        posting("remotive", "c", company="Acme", title="Rust Dev", remote=True),
    ])
    # Text search matches title/company (case-insensitive).
    got, total = repo.search(q="python")
    assert total == 1 and got[0].title == "Python Dev"
    assert repo.search(q="acme")[1] == 2
    # Source filter (provenance).
    assert repo.search(source="remoteok")[1] == 1
    # Remote filter.
    assert repo.search(remote=True)[1] == 2
    assert repo.search(remote=False)[1] == 1
    # Pagination: total reflects all matches, page is bounded by limit.
    page, total = repo.search(limit=2, offset=0)
    assert total == 3 and len(page) == 2
    assert len(repo.search(limit=2, offset=2)[0]) == 1
    # Provenance is attached to returned rows.
    assert repo.search(q="python")[0][0].sources == ["remotive"]


def test_candidates_filtered_by_source(conn):
    repo = PostingRepo(conn)
    repo.ingest([
        posting("remotive", "a", company="Acme", title="Python Dev"),
        posting("weworkremotely", "b", company="Beta", title="Rust Dev"),
    ])
    got = repo.candidates_for_sources(["remotive"])
    assert [p.title for p in got] == ["Python Dev"]
    assert repo.candidates_for_sources([]) == []


def test_purge_older_than(conn):
    repo = PostingRepo(conn)
    repo.ingest([posting("remotive", "a", company="Acme", title="Python Dev")])
    assert repo.purge_older_than(0) == 1
    assert repo.count() == 0


def test_delete_by_source(conn):
    repo = PostingRepo(conn)
    repo.ingest([
        posting("remotive", "a", company="Acme", title="Python Dev"),
        posting("remoteok", "b", company="Beta", title="Go Dev"),
        posting("remoteok", "c", company="Gamma", title="Rust Dev"),
    ])
    assert repo.count() == 3
    deleted = repo.delete_by_source("remoteok")
    assert deleted == 2 and repo.count() == 1
    # remoteok is fully cleared from provenance; the remotive posting is untouched.
    assert dict(repo.counts_by_source()) == {"remotive": 1}


# --- profiles ---

def test_profile_upsert_and_criteria(conn, user):
    repo = ProfileRepo(conn)
    stored = repo.upsert(user.id, "default", {
        "titles": ["Python Engineer"], "required_skills": ["python", "fastapi"],
        "keywords": ["backend"]}, origin="resume")
    assert repo.count_for(user.id) == 1
    crit = stored.criteria()
    assert crit.titles == ["Python Engineer"]
    assert "python" in crit.required_skills
    assert set(stored.search_terms()) >= {"Python Engineer", "backend", "python"}


def test_profile_upsert_replaces_when_id_given(conn, user):
    repo = ProfileRepo(conn)
    p1 = repo.upsert(user.id, "default", {"titles": ["A"]})
    repo.upsert(user.id, "default", {"titles": ["B"]}, profile_id=p1.id)
    assert repo.count_for(user.id) == 1
    assert repo.primary_for(user.id).titles == ["B"]


def test_active_users_terms(conn, user):
    ProfileRepo(conn).upsert(user.id, "default",
                             {"titles": ["Data Engineer"], "keywords": ["spark"]})
    terms = ActiveUsersRepo(conn).profile_terms(window_days=30)
    assert "Data Engineer" in terms and "spark" in terms


# --- resume / sources ---

def test_resume_upsert_and_get(conn, user):
    repo = ResumeRepo(conn)
    repo.upsert(user.id, filename="cv.pdf", content_type="application/pdf",
                blob=b"%PDF-bytes", extracted_text="hello resume")
    assert repo.get_text(user.id) == "hello resume"
    meta = repo.get_meta(user.id)
    assert meta.size_bytes == len(b"%PDF-bytes") and meta.filename == "cv.pdf"


def test_user_sources_replace(conn, user):
    repo = UserSourceRepo(conn)
    repo.set_for(user.id, ["remotive", "remoteok"])
    assert repo.list_for(user.id) == ["remotive", "remoteok"]
    repo.set_for(user.id, ["arbeitnow"])
    assert repo.list_for(user.id) == ["arbeitnow"]


# --- overlay ---

def test_overlay_score_saved_seen(conn, user):
    PostingRepo(conn).ingest([posting("remotive", "a", company="Acme", title="Dev")])
    pid = posting("remotive", "a", company="Acme", title="Dev").dedup_key
    ov = OverlayRepo(conn)
    ov.upsert_score(user.id, pid, 88.0, {"skill_coverage": 1.0})
    ov.set_saved(user.id, pid, True)
    got = ov.get_many(user.id, [pid])[pid]
    assert got.score == 88.0 and got.saved and got.seen_at is None
    ov.mark_seen(user.id, pid)
    assert ov.get_many(user.id, [pid])[pid].seen_at is not None


# --- enrichment cache (shared) ---

def test_enrichment_cache_roundtrip(conn):
    p = posting("remotive", "a", company="Acme", title="Dev")
    PostingRepo(conn).ingest([p])          # enrichments.posting_id -> postings(id) FK
    pid = p.dedup_key
    repo = EnrichmentRepo(conn)
    assert repo.get(pid, "h1", "m1") is None
    repo.put(pid, "h1", "m1", '{"remote":true}')
    assert repo.get(pid, "h1", "m1") == '{"remote":true}'


# --- drafts ---

def test_draft_create_get_list(conn, user):
    repo = DraftRepo(conn)
    did = repo.create(user.id, profile_id=None, posting_id=None, job_source="pool",
                      source_url=None, resume_md="# R", cover_letter_md="Dear",
                      stretch_claims_md=None, provider="anthropic", model="m",
                      key_source="platform")
    d = repo.get(did, user.id)
    assert d.resume_md == "# R" and d.key_source == "platform"
    assert repo.get(did, "other-user") is None      # private per user
    assert len(repo.list_for(user.id)) == 1


def test_draft_update_content(conn, user):
    repo = DraftRepo(conn)
    did = repo.create(user.id, profile_id=None, posting_id=None, job_source="pool",
                      source_url=None, resume_md="# R", cover_letter_md="Dear",
                      stretch_claims_md=None, provider="anthropic", model="m",
                      key_source="platform")
    # Only the provided field changes; the other is untouched.
    upd = repo.update_content(did, user.id, cover_letter_md="Dear team,")
    assert upd.cover_letter_md == "Dear team," and upd.resume_md == "# R"
    # Not the owner -> no update.
    assert repo.update_content(did, "other-user", resume_md="x") is None


# --- jobs / usage ledger ---

def test_job_lifecycle(conn, user):
    repo = JobRepo(conn)
    jid = repo.create("draft", user_id=user.id, params={"posting_id": "p"})
    assert repo.get(jid).status == "queued"
    repo.mark_running(jid)
    assert repo.get(jid).status == "running"
    repo.mark_succeeded(jid, {"draft_id": "d"})
    rec = repo.get(jid)
    assert rec.status == "succeeded" and rec.result == {"draft_id": "d"}


def test_llm_usage_ledger(conn, user):
    repo = LLMUsageRepo(conn)
    repo.record(user.id, action="draft", provider="anthropic", model="m",
                key_source="platform", input_tokens=10, output_tokens=20)
    assert repo.total_tokens_for(user.id) == 30


def test_llm_usage_list_recent_joins_user_and_job_duration(conn, user):
    jobs = JobRepo(conn)
    jid = jobs.create("draft", user_id=user.id, params={"posting_id": "p"})
    jobs.mark_running(jid)
    # Force a measurable elapsed time on the job record.
    conn.execute("UPDATE jobs SET started_at=?, finished_at=?, status='succeeded' "
                 "WHERE id=?",
                 ("2026-08-01T10:00:00+00:00", "2026-08-01T10:00:03+00:00", jid))
    conn.commit()

    repo = LLMUsageRepo(conn)
    repo.record(user.id, action="draft", provider="anthropic", model="m",
                key_source="platform", input_tokens=100, output_tokens=200,
                est_cost_usd=0.0042, job_id=jid)

    events = repo.list_recent()
    assert len(events) == 1
    e = events[0]
    assert e.user_email == "u@example.com"
    assert e.total_tokens == 300
    assert e.est_cost_usd == 0.0042
    assert e.job_status == "succeeded"
    assert e.duration_seconds == 3.0


def test_llm_usage_summary_filters_by_action(conn, user):
    repo = LLMUsageRepo(conn)
    repo.record(user.id, action="draft", provider="anthropic", model="m",
                key_source="platform", input_tokens=10, output_tokens=20,
                est_cost_usd=0.01)
    repo.record(user.id, action="enrich", provider="anthropic", model="m",
                key_source="platform", input_tokens=5, output_tokens=5,
                est_cost_usd=0.002)

    overall = repo.summary()
    assert overall["events"] == 2 and overall["total_tokens"] == 40
    assert overall["cost_usd"] == 0.012

    drafts = repo.summary(action="draft")
    assert drafts["events"] == 1 and drafts["total_tokens"] == 30
    assert repo.list_recent(action="draft")[0].action == "draft"
