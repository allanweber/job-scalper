from __future__ import annotations

from conftest import ADMIN_EMAIL, FakeOAuth, _do_login

from scalper.admin.container import AdminContainer
from scalper.admin.sessions import MemorySessionStore
from scalper.models import JobPosting
from scalper.service.content_repos import AuditRepo, JobRepo, LLMUsageRepo, PostingRepo
from scalper.service.models import GoogleIdentity
from scalper.service.quota import QuotaService
from scalper.service.repositories import QuotaOverrideRepo, UserRepo


# --- auth gating ---

def test_requires_login_redirects(client):
    r = client.get("/", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/login"


def test_login_page_renders(client):
    r = client.get("/login")
    assert r.status_code == 200 and "Sign in with Google" in r.text


def test_full_login_flow_grants_dashboard(client, conn):
    _do_login(client)
    r = client.get("/")
    assert r.status_code == 200 and "Overview" in r.text
    # The admin user was upserted with the admin role.
    assert UserRepo(conn).get_by_email(ADMIN_EMAIL).is_admin


def test_non_admin_email_is_rejected(service_container, admin_container):
    # OAuth returns a non-allowlisted identity -> login denied.
    from fastapi.testclient import TestClient

    from scalper.admin.app import create_admin_app
    ac = AdminContainer(
        service=service_container,
        oauth=FakeOAuth(GoogleIdentity(sub="x", email="stranger@example.com",
                                       email_verified=True)),
        sessions=MemorySessionStore(), cookie_secret="s", cookie_secure=False)
    with TestClient(create_admin_app(ac)) as c:
        r = c.get("/auth/login", follow_redirects=False)
        state = r.headers["location"].split("state=", 1)[1].split("&", 1)[0]
        cb = c.get(f"/auth/callback?code=good&state={state}", follow_redirects=False)
        assert cb.status_code == 303 and "/login?error=" in cb.headers["location"]
        assert c.get("/", follow_redirects=False).headers["location"] == "/login"


def test_bad_oauth_state_rejected(client):
    client.get("/auth/login", follow_redirects=False)
    cb = client.get("/auth/callback?code=good&state=WRONG", follow_redirects=False)
    assert "/login?error=" in cb.headers["location"]


def test_logout_clears_session(logged_in):
    assert logged_in.get("/", follow_redirects=False).status_code == 200
    logged_in.post("/logout", follow_redirects=False)
    assert logged_in.get("/", follow_redirects=False).headers["location"] == "/login"


# --- user management ---

def _make_user(conn, email="jane@example.com", sub="jane"):
    return UserRepo(conn).upsert_from_google(
        GoogleIdentity(sub=sub, email=email, name="Jane"), role="user")


def test_users_list_and_search(logged_in, conn):
    _make_user(conn)
    assert "jane@example.com" in logged_in.get("/users").text
    assert "jane@example.com" in logged_in.get("/users?q=jane").text
    assert "jane@example.com" not in logged_in.get("/users?q=zzz").text


def test_suspend_and_delete_user_audited(logged_in, conn):
    u = _make_user(conn)
    logged_in.post(f"/users/{u.id}/suspend", follow_redirects=False)
    assert UserRepo(conn).get(u.id).status == "suspended"
    logged_in.post(f"/users/{u.id}/unsuspend", follow_redirects=False)
    assert UserRepo(conn).get(u.id).status == "active"
    logged_in.post(f"/users/{u.id}/delete", follow_redirects=False)
    assert UserRepo(conn).get(u.id) is None
    actions = {e["action"] for e in AuditRepo(conn).list_recent()}
    assert {"user.suspend", "user.unsuspend", "user.delete"} <= actions


def test_set_plan_and_quota_override(logged_in, conn, settings):
    u = _make_user(conn)
    logged_in.post(f"/users/{u.id}/plan", data={"plan": "pro"}, follow_redirects=False)
    assert UserRepo(conn).get(u.id).plan == "pro"
    logged_in.post(f"/users/{u.id}/quota", data={"draft": "99"}, follow_redirects=False)
    assert QuotaOverrideRepo(conn).get(u.id, "draft") == 99
    # The override wins over the plan default in the quota engine.
    quota = QuotaService(conn=conn, settings=settings)
    assert quota.limit_for(UserRepo(conn).get(u.id), "draft") == 99


# --- settings ---

def test_settings_edit_applies_and_audits(logged_in, conn, settings):
    r = logged_in.post("/settings",
                       data={"key__scrape.interval_minutes": "120"},
                       follow_redirects=False)
    assert r.status_code == 303
    assert settings.get("scrape.interval_minutes") == 120
    assert any(e["action"] == "settings.update" for e in AuditRepo(conn).list_recent())


def test_settings_rejects_invalid_json(logged_in, conn, settings):
    before = settings.get("sources.enabled")
    logged_in.post("/settings", data={"key__sources.enabled": "not json ["},
                   follow_redirects=False)
    assert settings.get("sources.enabled") == before  # unchanged


# --- jobs & pool ---

def test_scrape_now_enqueues_and_audits(logged_in, conn):
    r = logged_in.post("/jobs/scrape-now", follow_redirects=False)
    assert r.status_code == 303
    from scalper.service.content_repos import JobRepo
    kinds = [j.kind for j in JobRepo(conn).list_recent()]
    assert "scrape" in kinds
    assert any(e["action"] == "scrape.run_now" for e in AuditRepo(conn).list_recent())


def test_jobs_page_lists_pool_and_jobs(logged_in, conn):
    PostingRepo(conn).ingest([JobPosting(
        source="remotive", source_id="1", url="http://x/1", company="Acme",
        title="Dev", remote=True)])
    logged_in.post("/jobs/purge-now", follow_redirects=False)
    page = logged_in.get("/jobs").text
    assert "Pool postings" in page and "Recent jobs" in page


def test_audit_page_renders(logged_in, conn):
    u = _make_user(conn)
    logged_in.post(f"/users/{u.id}/suspend", follow_redirects=False)
    assert "user.suspend" in logged_in.get("/audit").text


def test_postings_page_lists_and_filters(logged_in, conn):
    PostingRepo(conn).ingest([
        JobPosting(source="remotive", source_id="1", url="http://x/1", company="Acme",
                   title="Python Engineer", remote=True),
        JobPosting(source="remoteok", source_id="2", url="http://x/2", company="Beta",
                   title="Go Developer", remote=False),
    ])
    page = logged_in.get("/postings").text
    assert "Job postings" in page
    assert "Python Engineer" in page and "Go Developer" in page
    # Text filter narrows the result set.
    filtered = logged_in.get("/postings?q=python").text
    assert "Python Engineer" in filtered and "Go Developer" not in filtered
    # Source filter narrows by provenance.
    by_source = logged_in.get("/postings?source=remoteok").text
    assert "Go Developer" in by_source and "Python Engineer" not in by_source


def test_delete_all_jobs_from_source(logged_in, conn):
    PostingRepo(conn).ingest([
        JobPosting(source="remotive", source_id="1", url="http://x/1", company="Acme",
                   title="Dev", remote=True),
        JobPosting(source="remoteok", source_id="2", url="http://x/2", company="Beta",
                   title="Eng", remote=True),
    ])
    r = logged_in.post("/sources/remoteok/delete", follow_redirects=False)
    assert r.status_code == 303
    counts = dict(PostingRepo(conn).counts_by_source())
    assert "remoteok" not in counts and counts.get("remotive") == 1
    assert any(e["action"] == "sources.delete_postings"
               for e in AuditRepo(conn).list_recent())


def test_sources_page_shows_counts_by_source(logged_in, conn):
    PostingRepo(conn).ingest([
        JobPosting(source="remotive", source_id="1", url="http://x/1", company="Acme",
                   title="Dev", remote=True),
        JobPosting(source="remoteok", source_id="2", url="http://x/2", company="Beta",
                   title="Eng", remote=True),
    ])
    page = logged_in.get("/sources").text
    assert "Jobs by source" in page
    assert "remotive" in page and "remoteok" in page


# --- LLM usage / draft metrics ---

def test_usage_page_shows_draft_metrics(logged_in, conn):
    u = _make_user(conn)
    jobs = JobRepo(conn)
    jid = jobs.create("draft", user_id=u.id, params={"posting_id": "p"})
    conn.execute("UPDATE jobs SET started_at=?, finished_at=?, status='succeeded' "
                 "WHERE id=?",
                 ("2026-08-01T10:00:00+00:00", "2026-08-01T10:00:02+00:00", jid))
    conn.commit()
    LLMUsageRepo(conn).record(u.id, action="draft", provider="anthropic",
                              model="claude-haiku-4-5", key_source="platform",
                              input_tokens=1000, output_tokens=2000,
                              est_cost_usd=0.011, job_id=jid)

    page = logged_in.get("/usage").text
    assert "LLM Usage" in page
    assert "jane@example.com" in page      # joined user email
    assert "claude-haiku-4-5" in page      # model
    assert "$0.0110" in page               # estimated cost
    assert "2.0s" in page                  # job duration


def test_usage_page_filters_to_drafts(logged_in, conn):
    u = _make_user(conn)
    repo = LLMUsageRepo(conn)
    repo.record(u.id, action="draft", provider="anthropic", model="m",
                key_source="platform", input_tokens=10, output_tokens=20)
    repo.record(u.id, action="enrich", provider="anthropic", model="m2-enrich-only",
                key_source="platform", input_tokens=5, output_tokens=5)

    page = logged_in.get("/usage?action=draft").text
    assert "m2-enrich-only" not in page    # enrich row filtered out
