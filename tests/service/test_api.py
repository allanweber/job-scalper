from __future__ import annotations

from _helpers import make_container, posting

from scalper.service.content_repos import PostingRepo, ProfileRepo, ResumeRepo
from scalper.service.models import GoogleIdentity
from scalper.service.repositories import UserRepo


# --- public / system ---

def test_health_and_legal(client):
    assert client.get("/healthz").json() == {"message": "ok"}
    assert client.get("/readyz").json()["message"] == "ready"
    assert client.get("/legal/tos").json()["title"] == "Terms of Service"
    assert client.get("/legal/privacy").json()["version"]


# --- auth ---

def test_sign_in_and_me(client):
    r = client.post("/auth/google", json={"id_token": "good"})
    assert r.status_code == 200
    body = r.json()
    assert body["user"]["email"] == "user@example.com"
    tokens = body["tokens"]
    h = {"Authorization": f"Bearer {tokens['access_token']}"}
    assert client.get("/me", headers=h).json()["email"] == "user@example.com"


def test_sign_in_rejects_bad_token(client):
    assert client.post("/auth/google", json={"id_token": "bad"}).status_code == 401


def test_refresh_rotates(client):
    tokens = client.post("/auth/google", json={"id_token": "good"}).json()["tokens"]
    r = client.post("/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert r.status_code == 200
    # Old refresh token is now revoked (rotation) -> reuse fails.
    again = client.post("/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
    assert again.status_code == 401


def test_protected_requires_bearer(client):
    assert client.get("/me").status_code == 401


def test_suspended_account_blocked(client, conn):
    tokens = client.post("/auth/google", json={"id_token": "good"}).json()["tokens"]
    user = UserRepo(conn).get_by_email("user@example.com")
    UserRepo(conn).set_status(user.id, "suspended")
    h = {"Authorization": f"Bearer {tokens['access_token']}"}
    assert client.get("/me", headers=h).status_code == 403


# --- resume upload ---

def test_resume_upload_validations(client, auth_headers, settings):
    # empty
    r = client.put("/me/resume", headers=auth_headers,
                   files={"file": ("cv.txt", b"", "text/plain")})
    assert r.status_code == 400
    # size cap
    settings.set("upload.max_bytes", 10)
    r = client.put("/me/resume", headers=auth_headers,
                   files={"file": ("cv.txt", b"x" * 50, "text/plain")})
    assert r.status_code == 413
    settings.set("upload.max_bytes", 5_000_000)
    # disallowed content type + non-resume extension -> 415
    r = client.put("/me/resume", headers=auth_headers,
                   files={"file": ("cv.bin", b"\x00\x01binary", "application/octet-stream")})
    assert r.status_code == 415
    # ok
    r = client.put("/me/resume", headers=auth_headers,
                   files={"file": ("cv.txt", b"Jane Python FastAPI backend", "text/plain")})
    assert r.status_code == 200 and r.json()["text_chars"] > 0


def test_profile_from_resume_requires_resume_then_builds(client, auth_headers, conn):
    # No resume yet -> 400
    assert client.post("/me/profile/from-resume", headers=auth_headers).status_code == 400
    client.put("/me/resume", headers=auth_headers,
               files={"file": ("cv.txt", b"Jane Python FastAPI backend", "text/plain")})
    r = client.post("/me/profile/from-resume", headers=auth_headers)
    assert r.status_code == 202
    job_id = r.json()["job_id"]
    # Eager execution: job is already done by the time we poll.
    job = client.get(f"/jobs/{job_id}", headers=auth_headers).json()
    assert job["status"] == "succeeded"
    assert client.get("/me/profile", headers=auth_headers).json()["titles"] == ["Python Engineer"]


# --- sources ---

def test_sources_validation(client, auth_headers):
    r = client.put("/me/sources", headers=auth_headers, json={"sources": ["nope"]})
    assert r.status_code == 400
    r = client.put("/me/sources", headers=auth_headers,
                   json={"sources": ["remotive", "remoteok", "arbeitnow", "jobicy"]})
    assert r.status_code == 400 and "at most 3" in r.json()["detail"]
    r = client.put("/me/sources", headers=auth_headers,
                   json={"sources": ["remotive", "remoteok"]})
    assert r.status_code == 200 and r.json()["sources"] == ["remotive", "remoteok"]


# --- feed + draft + quota ---

def _seed_user_content(conn):
    user = UserRepo(conn).get_by_email("user@example.com")
    ResumeRepo(conn).upsert(user.id, filename="cv.txt", content_type="text/plain",
                            blob=b"Jane Python FastAPI", extracted_text="Jane Python FastAPI")
    ProfileRepo(conn).upsert(user.id, "default", {
        "titles": ["Python Engineer"], "required_skills": ["python", "fastapi"],
        "keywords": ["backend"]})
    p = posting("remotive", "a", company="Acme", title="Senior Python Engineer",
                description="python fastapi backend remote")
    PostingRepo(conn).ingest([p])
    return user, p.dedup_key


def test_posting_detail_returns_description_and_breakdown(client, auth_headers, conn):
    client.get("/me", headers=auth_headers)
    _user, pid = _seed_user_content(conn)
    r = client.get(f"/postings/{pid}", headers=auth_headers)
    assert r.status_code == 200
    body = r.json()
    # The feed omits the description; the detail endpoint carries it.
    assert body["description"] == "python fastapi backend remote"
    assert body["score"] > 0
    assert "python" in body["matched_skills"]


def test_posting_detail_unknown_404(client, auth_headers):
    assert client.get("/postings/nope", headers=auth_headers).status_code == 404


def test_user_payload_reports_profile_presence(client, auth_headers, conn):
    # A freshly signed-in account has no profile yet — the client uses this to
    # decide onboarding is needed, independent of any device-local flag.
    signin = client.post("/auth/google", json={"id_token": "good"}).json()
    assert signin["user"]["has_profile"] is False
    assert client.get("/me", headers=auth_headers).json()["has_profile"] is False

    user = UserRepo(conn).get_by_email("user@example.com")
    ProfileRepo(conn).upsert(user.id, "default", {"titles": ["Dev"]})
    assert client.get("/me", headers=auth_headers).json()["has_profile"] is True


def test_delete_account_removes_user_and_cascades(client, auth_headers, conn):
    client.get("/me", headers=auth_headers)  # ensure the user row exists
    user, _pid = _seed_user_content(conn)
    assert ProfileRepo(conn).primary_for(user.id) is not None

    r = client.request("DELETE", "/me", headers=auth_headers)
    assert r.status_code == 200, r.text

    # The user and their owned rows are gone (ON DELETE CASCADE), and the old
    # access token no longer resolves to a user.
    assert UserRepo(conn).get(user.id) is None
    assert ProfileRepo(conn).primary_for(user.id) is None
    assert client.get("/me", headers=auth_headers).status_code == 401


def test_draft_edit_persists(client, auth_headers, conn):
    client.get("/me", headers=auth_headers)
    _user, pid = _seed_user_content(conn)
    r = client.post("/drafts", headers=auth_headers, json={"posting_id": pid})
    assert r.status_code == 201
    draft_id = r.json()["id"]
    upd = client.put(f"/drafts/{draft_id}", headers=auth_headers,
                     json={"resume_md": "# Edited Resume"})
    assert upd.status_code == 200 and upd.json()["resume_md"] == "# Edited Resume"
    # Persisted across a fresh GET.
    assert client.get(f"/drafts/{draft_id}",
                      headers=auth_headers).json()["resume_md"] == "# Edited Resume"


def test_draft_edit_requires_a_field(client, auth_headers, conn):
    client.get("/me", headers=auth_headers)
    _user, pid = _seed_user_content(conn)
    r = client.post("/drafts", headers=auth_headers, json={"posting_id": pid})
    draft_id = r.json()["id"]
    assert client.put(f"/drafts/{draft_id}", headers=auth_headers,
                      json={}).status_code == 422


def test_draft_edit_other_user_404(client, auth_headers, conn):
    assert client.put("/drafts/nope", headers=auth_headers,
                      json={"resume_md": "x"}).status_code == 404


def test_import_url_pools_and_returns_detail(container, conn):
    from fastapi.testclient import TestClient

    from scalper.service.app import create_app

    html = ("<html><head><title>Staff Backend Engineer</title>"
            "<meta property='og:site_name' content='Finch Payments'>"
            "<meta property='og:description' content='Build payment APIs in python.'>"
            "</head><body>Remote role. Salary $120,000 - 150,000. python fastapi</body></html>")
    container.url_fetcher = lambda url: html
    with TestClient(create_app(container)) as c:
        h = {"Authorization": f"Bearer "
             f"{c.post('/auth/google', json={'id_token': 'good'}).json()['tokens']['access_token']}"}
        r = c.post("/import/url", headers=h,
                   json={"url": "https://finchpayments.example/jobs/42"})
        assert r.status_code == 201, r.text
        body = r.json()
        assert body["title"] == "Staff Backend Engineer"
        assert body["company"] == "Finch Payments"
        assert body["remote"] is True
        assert body["salary_min"] == 120000 and body["salary_max"] == 150000
        # Now fetchable by its pool id.
        assert c.get(f"/postings/{body['posting_id']}", headers=h).status_code == 200


def test_import_url_rejects_unfetchable(container):
    from fastapi.testclient import TestClient

    from scalper.service.app import create_app
    from scalper.service.url_import import UrlImportError

    def _boom(url):
        raise UrlImportError("could not fetch the page")

    container.url_fetcher = _boom
    with TestClient(create_app(container)) as c:
        h = {"Authorization": f"Bearer "
             f"{c.post('/auth/google', json={'id_token': 'good'}).json()['tokens']['access_token']}"}
        r = c.post("/import/url", headers=h, json={"url": "https://x.example/j"})
        assert r.status_code == 422


def test_feed_and_draft_flow(client, auth_headers, conn):
    client.get("/me", headers=auth_headers)  # ensure user row exists
    _user, pid = _seed_user_content(conn)
    client.put("/me/sources", headers=auth_headers, json={"sources": ["remotive"]})
    feed = client.get("/feed", headers=auth_headers).json()
    assert feed["count"] == 1 and feed["items"][0]["posting_id"] == pid
    # Thin-feed meta rides along for the client's first-run nudges.
    assert feed["meta"]["sources_count"] == 1
    assert feed["meta"]["sources_max"] == 3
    assert feed["meta"]["has_profile"] is True
    assert feed["meta"]["pool_size"] >= 1
    # draft — the row is returned immediately; the eager job fills it inline, so
    # by the time the request returns it's already 'ready' with content.
    r = client.post("/drafts", headers=auth_headers, json={"posting_id": pid})
    assert r.status_code == 201
    created = r.json()
    assert created["status"] == "ready"
    draft_id = created["id"]
    assert created["resume_md"].startswith("# Jane")
    d = client.get(f"/drafts/{draft_id}", headers=auth_headers).json()
    assert d["resume_md"].startswith("# Jane")
    listing = client.get("/drafts", headers=auth_headers).json()
    assert len(listing) == 1
    # The Applications list is joined to the pool posting for a readable row.
    assert listing[0]["title"] == "Senior Python Engineer"
    assert listing[0]["company"] == "Acme"
    assert listing[0]["url"]  # the posting URL, for an Apply link
    assert listing[0]["status"] == "ready"


def test_draft_tone_and_regenerate(client, auth_headers, conn):
    client.get("/me", headers=auth_headers)
    _user, pid = _seed_user_content(conn)

    # Create in a chosen tone; the "why this draft" skills ride along.
    r = client.post("/drafts", headers=auth_headers,
                    json={"posting_id": pid, "tone": "warm"})
    assert r.status_code == 201, r.text
    created = r.json()
    draft_id = created["id"]
    assert created["tone"] == "warm"
    assert created["status"] == "ready"
    assert len(created["matched_skills"]) >= 1

    # An unknown tone is rejected up front.
    bad = client.post("/drafts", headers=auth_headers,
                      json={"posting_id": pid, "tone": "sassy"})
    assert bad.status_code == 422

    # Regenerate re-fills the same draft and can switch tone.
    rg = client.post(f"/drafts/{draft_id}/regenerate", headers=auth_headers,
                     json={"tone": "concise"})
    assert rg.status_code == 202, rg.text
    body = rg.json()
    assert body["id"] == draft_id
    assert body["tone"] == "concise"
    assert body["status"] == "ready"
    assert body["resume_md"].startswith("# Jane")


def test_mark_applied_visible_everywhere(client, auth_headers, conn):
    client.get("/me", headers=auth_headers)
    _user, pid = _seed_user_content(conn)
    client.put("/me/sources", headers=auth_headers, json={"sources": ["remotive"]})
    r = client.post("/drafts", headers=auth_headers, json={"posting_id": pid})
    draft_id = r.json()["id"]

    # Not applied to begin with — on every surface.
    assert client.get(f"/drafts/{draft_id}", headers=auth_headers).json()["applied"] is False
    assert client.get("/drafts", headers=auth_headers).json()[0]["applied"] is False
    assert client.get(f"/postings/{pid}", headers=auth_headers).json()["applied"] is False
    assert client.get("/feed", headers=auth_headers).json()["items"][0]["applied"] is False

    # Mark applied from the draft detail screen.
    up = client.put(f"/drafts/{draft_id}/applied", headers=auth_headers,
                    json={"applied": True})
    assert up.status_code == 200 and up.json()["applied"] is True

    # Now visible as applied everywhere the posting shows up.
    assert client.get(f"/drafts/{draft_id}", headers=auth_headers).json()["applied"] is True
    assert client.get("/drafts", headers=auth_headers).json()[0]["applied"] is True
    assert client.get(f"/postings/{pid}", headers=auth_headers).json()["applied"] is True
    assert client.get("/feed", headers=auth_headers).json()["items"][0]["applied"] is True

    # Unmark — clears back to not-applied everywhere.
    down = client.put(f"/drafts/{draft_id}/applied", headers=auth_headers,
                      json={"applied": False})
    assert down.status_code == 200 and down.json()["applied"] is False
    assert client.get(f"/postings/{pid}", headers=auth_headers).json()["applied"] is False
    assert client.get("/feed", headers=auth_headers).json()["items"][0]["applied"] is False


def test_mark_applied_other_user_404(client, auth_headers):
    assert client.put("/drafts/nope/applied", headers=auth_headers,
                      json={"applied": True}).status_code == 404


def test_application_status_pipeline(client, auth_headers, conn):
    client.get("/me", headers=auth_headers)
    _user, pid = _seed_user_content(conn)
    client.put("/me/sources", headers=auth_headers, json={"sources": ["remotive"]})
    draft_id = client.post("/drafts", headers=auth_headers,
                           json={"posting_id": pid}).json()["id"]

    # A fresh draft has no stage and isn't applied.
    d = client.get(f"/drafts/{draft_id}", headers=auth_headers).json()
    assert d["application_status"] is None and d["applied"] is False

    # Advance through the funnel; each stage implies applied=True and shows up
    # on both the detail and the Applications list.
    for stage in ("applied", "interviewing", "offer", "rejected"):
        up = client.put(f"/drafts/{draft_id}/status", headers=auth_headers,
                        json={"status": stage})
        assert up.status_code == 200
        assert up.json()["application_status"] == stage
        assert up.json()["applied"] is True
        listing = client.get("/drafts", headers=auth_headers).json()[0]
        assert listing["application_status"] == stage and listing["applied"] is True
        # The feed still exposes a simple applied flag for the posting.
        assert client.get("/feed", headers=auth_headers).json()["items"][0]["applied"] is True

    # Clearing the stage returns to not-applied everywhere.
    cleared = client.put(f"/drafts/{draft_id}/status", headers=auth_headers,
                         json={"status": None})
    assert cleared.status_code == 200
    assert cleared.json()["application_status"] is None
    assert cleared.json()["applied"] is False
    assert client.get("/drafts", headers=auth_headers).json()[0]["application_status"] is None
    assert client.get("/feed", headers=auth_headers).json()["items"][0]["applied"] is False


def test_mark_applied_sets_stage(client, auth_headers, conn):
    """The legacy /applied toggle maps onto the pipeline's 'applied' stage."""
    client.get("/me", headers=auth_headers)
    _user, pid = _seed_user_content(conn)
    client.put("/me/sources", headers=auth_headers, json={"sources": ["remotive"]})
    draft_id = client.post("/drafts", headers=auth_headers,
                           json={"posting_id": pid}).json()["id"]

    client.put(f"/drafts/{draft_id}/applied", headers=auth_headers,
               json={"applied": True})
    assert client.get(f"/drafts/{draft_id}", headers=auth_headers) \
        .json()["application_status"] == "applied"


def test_application_status_rejects_unknown(client, auth_headers, conn):
    client.get("/me", headers=auth_headers)
    _user, pid = _seed_user_content(conn)
    client.put("/me/sources", headers=auth_headers, json={"sources": ["remotive"]})
    draft_id = client.post("/drafts", headers=auth_headers,
                           json={"posting_id": pid}).json()["id"]
    bad = client.put(f"/drafts/{draft_id}/status", headers=auth_headers,
                     json={"status": "on_the_moon"})
    assert bad.status_code == 422


def test_application_status_other_user_404(client, auth_headers):
    assert client.put("/drafts/nope/status", headers=auth_headers,
                      json={"status": "applied"}).status_code == 404


def test_application_insights_funnel(client, auth_headers, conn):
    client.get("/me", headers=auth_headers)
    _user, pid = _seed_user_content(conn)
    client.put("/me/sources", headers=auth_headers, json={"sources": ["remotive"]})
    draft_id = client.post("/drafts", headers=auth_headers,
                           json={"posting_id": pid}).json()["id"]

    # One draft, no stage set yet — it counts as an application in 'applied'.
    ins = client.get("/drafts/insights", headers=auth_headers).json()
    assert ins["total"] == 1
    # Every stage is present (zero-filled) so the client needn't post-process.
    for stage in ("applied", "pre_screen", "interviewing", "offer",
                  "ghosted", "rejected"):
        assert stage in ins["counts"]
    assert ins["counts"]["applied"] == 1
    assert sum(ins["counts"].values()) == ins["total"]

    # Move it into the pipeline; the funnel follows.
    client.put(f"/drafts/{draft_id}/status", headers=auth_headers,
               json={"status": "interviewing"})
    ins = client.get("/drafts/insights", headers=auth_headers).json()
    assert ins["counts"]["interviewing"] == 1 and ins["counts"]["applied"] == 0
    assert sum(ins["counts"].values()) == 1


def test_application_insights_empty(client, auth_headers):
    client.get("/me", headers=auth_headers)
    ins = client.get("/drafts/insights", headers=auth_headers).json()
    assert ins["total"] == 0
    assert sum(ins["counts"].values()) == 0


def test_new_stages_accepted(client, auth_headers, conn):
    """The expanded stage set (pre_screen, ghosted) is valid."""
    client.get("/me", headers=auth_headers)
    _user, pid = _seed_user_content(conn)
    client.put("/me/sources", headers=auth_headers, json={"sources": ["remotive"]})
    draft_id = client.post("/drafts", headers=auth_headers,
                           json={"posting_id": pid}).json()["id"]
    for stage in ("pre_screen", "ghosted"):
        up = client.put(f"/drafts/{draft_id}/status", headers=auth_headers,
                        json={"status": stage})
        assert up.status_code == 200 and up.json()["application_status"] == stage


def test_notification_prefs_defaults_and_update(client, auth_headers):
    client.get("/me", headers=auth_headers)  # ensure user row
    # Defaults mirror the onboarding promise: alerts on, notify at 90+.
    p = client.get("/me/notifications", headers=auth_headers).json()
    assert p == {"match_alerts": True, "min_score": 90}
    up = client.put("/me/notifications", headers=auth_headers,
                    json={"match_alerts": False, "min_score": 80})
    assert up.status_code == 200
    assert up.json() == {"match_alerts": False, "min_score": 80}
    assert client.get("/me/notifications", headers=auth_headers).json()["min_score"] == 80


def test_notification_prefs_validates_score(client, auth_headers):
    client.get("/me", headers=auth_headers)
    assert client.put("/me/notifications", headers=auth_headers,
                      json={"min_score": 150}).status_code == 422


def test_register_and_unregister_device(client, auth_headers):
    client.get("/me", headers=auth_headers)
    r = client.post("/me/devices", headers=auth_headers,
                    json={"token": "tok-1", "platform": "android"})
    assert r.status_code == 200
    # Re-registering the same token is idempotent.
    assert client.post("/me/devices", headers=auth_headers,
                       json={"token": "tok-1", "platform": "android"}).status_code == 200
    assert client.request("DELETE", "/me/devices/tok-1",
                          headers=auth_headers).status_code == 200


def test_register_device_requires_token(client, auth_headers):
    client.get("/me", headers=auth_headers)
    assert client.post("/me/devices", headers=auth_headers,
                       json={"token": ""}).status_code == 422


class _FakeSender:
    """Records notification sends; reports one token as unregistered."""

    def __init__(self, invalid=()):
        self.calls = []
        self._invalid = list(invalid)

    def send(self, tokens, *, title, body, data):
        from scalper.service.push import SendResult
        self.calls.append({"tokens": list(tokens), "title": title,
                           "body": body, "data": data})
        invalid = [t for t in tokens if t in self._invalid]
        return SendResult(sent=len(tokens) - len(invalid), invalid_tokens=invalid)


def _prime_notify_user(conn):
    """Seed a user with a profile, a matching pooled posting, sources, prefs,
    and a device — everything run_notify needs to push one match."""
    from scalper.service.content_repos import UserSourceRepo
    from scalper.service.push_repos import NotificationPrefsRepo, PushDeviceRepo

    user, pid = _seed_user_content(conn)
    UserSourceRepo(conn).set_for(user.id, ["remotive"])
    # Low threshold so the test doesn't depend on the exact match score.
    NotificationPrefsRepo(conn).upsert(user.id, match_alerts=True, min_score=1)
    PushDeviceRepo(conn).register(user.id, "tok-1", "android")
    return user, pid


def test_run_notify_pushes_new_matches_once(client, auth_headers, container, conn):
    from scalper.service.content_repos import JobRepo
    from scalper.service.jobs import run_notify

    client.get("/me", headers=auth_headers)  # create the user row
    _user, pid = _prime_notify_user(conn)
    fake = _FakeSender()
    container.push_sender = fake

    jid = JobRepo(conn).create("notify", user_id=None)
    res = run_notify(container, conn, jid, {})
    assert res["users_notified"] == 1 and res["pushes"] == 1
    assert fake.calls[0]["tokens"] == ["tok-1"]
    assert fake.calls[0]["data"] == {"type": "match", "posting_id": pid}

    # Dedup: the same match is not pushed again.
    res2 = run_notify(container, conn, jid, {})
    assert res2["users_notified"] == 0
    assert len(fake.calls) == 1


def test_run_notify_skips_when_alerts_off(client, auth_headers, container, conn):
    from scalper.service.content_repos import JobRepo
    from scalper.service.jobs import run_notify
    from scalper.service.push_repos import NotificationPrefsRepo

    client.get("/me", headers=auth_headers)
    user, _pid = _prime_notify_user(conn)
    NotificationPrefsRepo(conn).upsert(user.id, match_alerts=False, min_score=1)
    fake = _FakeSender()
    container.push_sender = fake

    jid = JobRepo(conn).create("notify", user_id=None)
    res = run_notify(container, conn, jid, {})
    assert res["users_notified"] == 0 and not fake.calls


def test_run_notify_prunes_invalid_tokens(client, auth_headers, container, conn):
    from scalper.service.content_repos import JobRepo
    from scalper.service.jobs import run_notify
    from scalper.service.push_repos import PushDeviceRepo

    client.get("/me", headers=auth_headers)
    user, _pid = _prime_notify_user(conn)
    fake = _FakeSender(invalid=["tok-1"])
    container.push_sender = fake

    jid = JobRepo(conn).create("notify", user_id=None)
    run_notify(container, conn, jid, {})
    # The token FCM rejected is removed so it isn't tried again.
    assert PushDeviceRepo(conn).tokens_for(user.id) == []


def test_draft_blocked_when_quota_exhausted(client, auth_headers, conn, settings):
    client.get("/me", headers=auth_headers)
    _user, pid = _seed_user_content(conn)
    settings.set("quota.free", {"draft_per_month": 0, "profile_build_per_month": 5,
                                "enrich_per_month": 30})
    r = client.post("/drafts", headers=auth_headers, json={"posting_id": pid})
    assert r.status_code == 402


def test_draft_unknown_posting_404(client, auth_headers):
    assert client.post("/drafts", headers=auth_headers,
                       json={"posting_id": "nope"}).status_code == 404


def test_draft_marked_failed_when_no_resume(client, auth_headers, conn):
    """A drafting failure flips the pending row to 'failed' with the reason,
    rather than leaving it stuck pending — so the client stops polling."""
    client.get("/me", headers=auth_headers)  # user row, but no resume/profile
    p = posting("remotive", "z", company="Zed", title="Backend Engineer",
                description="python remote")
    PostingRepo(conn).ingest([p])
    r = client.post("/drafts", headers=auth_headers, json={"posting_id": p.dedup_key})
    assert r.status_code == 201
    body = r.json()
    assert body["status"] == "failed"
    assert "resume" in (body["error"] or "").lower()
    # Visible as failed on the Applications list too.
    assert client.get("/drafts", headers=auth_headers).json()[0]["status"] == "failed"


# --- jobs isolation ---

def test_cannot_read_another_users_job(client, auth_headers, conn):
    from scalper.service.content_repos import JobRepo
    other = UserRepo(conn).upsert_from_google(
        GoogleIdentity(sub="other", email="other@example.com"), role="user")
    jid = JobRepo(conn).create("draft", user_id=other.id, params={})
    assert client.get(f"/jobs/{jid}", headers=auth_headers).status_code == 404


# --- LLM keys ---

def test_keys_crud(client, auth_headers):
    r = client.put("/me/keys", headers=auth_headers,
                   json={"provider": "anthropic", "api_key": "sk-secret"})
    assert r.status_code == 200 and r.json()["keys"][0]["provider"] == "anthropic"
    r = client.put("/me/keys", headers=auth_headers,
                   json={"provider": "invalid", "api_key": "x"})
    assert r.status_code == 400
    r = client.delete("/me/keys/anthropic", headers=auth_headers)
    assert r.json()["keys"] == []


def test_keys_unavailable_without_vault(conn, vault):
    # Container with no vault -> BYO keys disabled (503).
    from fastapi.testclient import TestClient

    from scalper.service.app import create_app
    container = make_container(None)  # vault=None
    with TestClient(create_app(container)) as c:
        h = {"Authorization": "Bearer " +
             c.post("/auth/google", json={"id_token": "good"}).json()["tokens"]["access_token"]}
        r = c.put("/me/keys", headers=h, json={"provider": "anthropic", "api_key": "k"})
        assert r.status_code == 503


# --- quota endpoint + account deletion ---

def test_quota_endpoint_reflects_byo(client, auth_headers):
    q = client.get("/me/quota", headers=auth_headers).json()
    assert q["byo_key"] is False
    assert {m["metric"] for m in q["metrics"]} == {"draft", "profile_build", "enrich"}
    client.put("/me/keys", headers=auth_headers,
               json={"provider": "anthropic", "api_key": "sk"})
    q2 = client.get("/me/quota", headers=auth_headers).json()
    assert q2["byo_key"] is True
    assert all(m["unlimited"] for m in q2["metrics"])


def test_account_deletion(client, auth_headers, conn):
    client.get("/me", headers=auth_headers)
    assert UserRepo(conn).get_by_email("user@example.com") is not None
    assert client.delete("/me", headers=auth_headers).json()["message"] == "account deleted"
    assert UserRepo(conn).get_by_email("user@example.com") is None


def test_legal_acceptance(client, auth_headers):
    assert client.get("/me", headers=auth_headers).json()["tos_accepted"] is False
    r = client.post("/me/legal/accept", headers=auth_headers)
    assert r.json()["tos_accepted"] is True and r.json()["privacy_accepted"] is True
