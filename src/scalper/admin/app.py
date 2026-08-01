"""Admin web app (FastAPI + Jinja2 + HTMX). See ADR 0010 / DESIGN.md.

Google web-OAuth login gated by the admin allowlist, server-side sessions, and an
operator console over the same DB: dashboard, user management (plan/quota/suspend/
delete), hot settings (incl. scrape interval + enabled sources + run-now), job/pool
monitoring, and the audit log. Every state change is written to `admin_audit`.

`create_admin_app()` builds the production app from env (uvicorn factory mode);
tests pass an `AdminContainer` with a fake OAuth client + in-memory sessions.
"""

from __future__ import annotations

import json
import secrets
from typing import Any
from urllib.parse import quote

from fastapi import Depends, FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from jinja2 import Environment, PackageLoader, select_autoescape

from scalper.admin.container import AdminContainer
from scalper.admin.deps import (
    AdminContext,
    _Redirect,
    current_admin,
    get_admin_ctx,
    redirect,
    sign_sid,
    unsign_sid,
)
from scalper.admin.oauth import OAuthError
from scalper.db import apply_pending
from scalper.service.content_repos import AuditRepo, JobRepo, LLMUsageRepo, PostingRepo
from scalper.service.jobs import KIND_PURGE, KIND_SCRAPE, JobQueue
from scalper.service.models import User
from scalper.service.quota import METRICS
from scalper.service.repositories import QuotaOverrideRepo, UserRepo

_STATE_COOKIE = "scalper_admin_state"
_PLANS = ["free", "pro"]

_env = Environment(loader=PackageLoader("scalper.admin", "templates"),
                   autoescape=select_autoescape(["html"]))

#: LLM actions surfaced on the usage page (order = filter chip order).
_USAGE_ACTIONS = ["draft", "profile_build", "enrich"]


def _fmt_duration(seconds: float | None) -> str:
    if seconds is None:
        return "—"
    if seconds < 1:
        return f"{int(seconds * 1000)}ms"
    return f"{seconds:.1f}s"


_env.filters["usd"] = lambda v: "—" if v is None else f"${v:,.4f}"
_env.filters["commas"] = lambda v: f"{int(v or 0):,}"
_env.filters["dur"] = _fmt_duration


def _base_url(ctx: AdminContext, request: Request) -> str:
    override = ctx.admin.service.environ.get("SCALPER_ADMIN_BASE_URL")
    return (override or str(request.base_url)).rstrip("/")


def _render(request: Request, template: str, *, admin: User | None = None,
            **context: Any) -> HTMLResponse:
    context.setdefault("flash", request.query_params.get("flash"))
    html = _env.get_template(template).render(request=request, admin=admin, **context)
    return HTMLResponse(html)


def _flash_redirect(location: str, message: str) -> RedirectResponse:
    return redirect(f"{location}?flash={quote(message)}")


def _audit(ctx: AdminContext, admin: User, action: str, **kw: Any) -> None:
    AuditRepo(ctx.conn).record(admin_user_id=admin.id, action=action, **kw)


def create_admin_app(admin_container: AdminContainer | None = None) -> FastAPI:
    admin_container = admin_container or AdminContainer.from_env()

    conn = admin_container.service.connect()
    try:
        apply_pending(conn)
    finally:
        conn.close()

    app = FastAPI(title="Job Scalper Admin", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.admin = admin_container

    @app.exception_handler(_Redirect)
    async def _on_redirect(_request: Request, exc: _Redirect):
        return RedirectResponse(exc.location, status_code=303)

    # -- auth --

    @app.get("/login", response_class=HTMLResponse)
    def login(request: Request):
        return _render(request, "login.html", error=request.query_params.get("error"))

    @app.get("/auth/login")
    def auth_login(request: Request, ctx: AdminContext = Depends(get_admin_ctx)):
        state = secrets.token_urlsafe(24)
        redirect_uri = f"{_base_url(ctx, request)}/auth/callback"
        url = ctx.admin.oauth.authorize_url(state=state, redirect_uri=redirect_uri)
        resp = RedirectResponse(url, status_code=303)
        resp.set_cookie(_STATE_COOKIE, sign_sid(ctx.admin.cookie_secret, state),
                        max_age=600, httponly=True, samesite="lax",
                        secure=ctx.admin.cookie_secure)
        return resp

    @app.get("/auth/callback")
    def auth_callback(request: Request, code: str = "", state: str = "",
                      ctx: AdminContext = Depends(get_admin_ctx)):
        expected = unsign_sid(ctx.admin.cookie_secret, request.cookies.get(_STATE_COOKIE, ""))
        if not code or not state or state != expected:
            return redirect("/login?error=" + quote("Invalid or expired login attempt."))
        redirect_uri = f"{_base_url(ctx, request)}/auth/callback"
        try:
            identity = ctx.admin.oauth.exchange_code(code=code, redirect_uri=redirect_uri)
        except OAuthError:
            return redirect("/login?error=" + quote("Google sign-in failed."))
        role = ctx.admin.service.allowlist.role_for(identity.email)
        if role != "admin":
            return redirect("/login?error=" + quote("This account is not an admin."))
        user = UserRepo(ctx.conn).upsert_from_google(identity, role="admin")
        sid = ctx.admin.sessions.create({"user_id": user.id, "email": user.email})
        resp = redirect("/")
        resp.set_cookie(ctx.admin.cookie_name, sign_sid(ctx.admin.cookie_secret, sid),
                        httponly=True, samesite="lax", secure=ctx.admin.cookie_secure)
        resp.delete_cookie(_STATE_COOKIE)
        _audit(ctx, user, "admin.login")
        return resp

    @app.post("/logout")
    def logout(request: Request, ctx: AdminContext = Depends(get_admin_ctx)):
        raw = request.cookies.get(ctx.admin.cookie_name, "")
        sid = unsign_sid(ctx.admin.cookie_secret, raw)
        if sid:
            ctx.admin.sessions.delete(sid)
        resp = redirect("/login")
        resp.delete_cookie(ctx.admin.cookie_name)
        return resp

    # -- dashboard --

    @app.get("/", response_class=HTMLResponse)
    def dashboard(request: Request, ctx: AdminContext = Depends(get_admin_ctx),
                  admin: User = Depends(current_admin)):
        users = UserRepo(ctx.conn)
        by_status = users.count_by_status()
        s = ctx.settings
        return _render(request, "dashboard.html", admin=admin, active="dashboard",
                       users_total=users.count(),
                       users_active=by_status.get("active", 0),
                       users_suspended=by_status.get("suspended", 0),
                       pool_count=PostingRepo(ctx.conn).count(),
                       job_counts=JobRepo(ctx.conn).counts_by_status(),
                       scrape_interval=s.get("scrape.interval_minutes"),
                       last_run=s.get("scrape.last_run_at"),
                       enabled_sources=s.get("sources.enabled", []) or [],
                       maintenance=bool(s.get("maintenance.enabled", False)))

    # -- users --

    @app.get("/users", response_class=HTMLResponse)
    def users_list(request: Request, q: str | None = None,
                   ctx: AdminContext = Depends(get_admin_ctx),
                   admin: User = Depends(current_admin)):
        return _render(request, "users.html", admin=admin, active="users", q=q,
                       users=UserRepo(ctx.conn).list(query=q, limit=100))

    @app.get("/users/{user_id}", response_class=HTMLResponse)
    def user_detail(request: Request, user_id: str,
                    ctx: AdminContext = Depends(get_admin_ctx),
                    admin: User = Depends(current_admin)):
        u = UserRepo(ctx.conn).get(user_id)
        if u is None:
            return redirect("/users?flash=" + quote("User not found."))
        overrides = {m: v for m in METRICS
                     if (v := QuotaOverrideRepo(ctx.conn).get(user_id, m)) is not None}
        return _render(request, "user_detail.html", admin=admin, active="users", u=u,
                       plans=_PLANS, metrics=list(METRICS), overrides=overrides,
                       tokens_used=LLMUsageRepo(ctx.conn).total_tokens_for(user_id))

    @app.post("/users/{user_id}/plan")
    def set_plan(user_id: str, plan: str = Form(...),
                 ctx: AdminContext = Depends(get_admin_ctx),
                 admin: User = Depends(current_admin)):
        u = UserRepo(ctx.conn).get(user_id)
        if u is None:
            return redirect("/users")
        UserRepo(ctx.conn).set_plan(user_id, plan)
        _audit(ctx, admin, "user.plan", target_type="user", target_id=user_id,
               before={"plan": u.plan}, after={"plan": plan})
        return _flash_redirect(f"/users/{user_id}", "Plan updated.")

    @app.post("/users/{user_id}/quota")
    async def set_quota(user_id: str, request: Request,
                        ctx: AdminContext = Depends(get_admin_ctx),
                        admin: User = Depends(current_admin)):
        form = await request.form()
        repo = QuotaOverrideRepo(ctx.conn)
        changed = {}
        for metric in METRICS:
            raw = (form.get(metric) or "").strip()
            if raw == "":
                continue
            try:
                repo.set(user_id, metric, int(raw))
                changed[metric] = int(raw)
            except ValueError:
                pass
        _audit(ctx, admin, "user.quota", target_type="user", target_id=user_id,
               after=changed)
        return _flash_redirect(f"/users/{user_id}", "Quota overrides saved.")

    @app.post("/users/{user_id}/suspend")
    def suspend(user_id: str, ctx: AdminContext = Depends(get_admin_ctx),
                admin: User = Depends(current_admin)):
        UserRepo(ctx.conn).set_status(user_id, "suspended")
        _audit(ctx, admin, "user.suspend", target_type="user", target_id=user_id)
        return _flash_redirect(f"/users/{user_id}", "User suspended.")

    @app.post("/users/{user_id}/unsuspend")
    def unsuspend(user_id: str, ctx: AdminContext = Depends(get_admin_ctx),
                  admin: User = Depends(current_admin)):
        UserRepo(ctx.conn).set_status(user_id, "active")
        _audit(ctx, admin, "user.unsuspend", target_type="user", target_id=user_id)
        return _flash_redirect(f"/users/{user_id}", "User reactivated.")

    @app.post("/users/{user_id}/delete")
    def delete_user(user_id: str, ctx: AdminContext = Depends(get_admin_ctx),
                    admin: User = Depends(current_admin)):
        u = UserRepo(ctx.conn).get(user_id)
        UserRepo(ctx.conn).delete(user_id)
        _audit(ctx, admin, "user.delete", target_type="user", target_id=user_id,
               before={"email": u.email if u else None})
        return _flash_redirect("/users", "User and all their data deleted.")

    # -- settings --

    @app.get("/settings", response_class=HTMLResponse)
    def settings_page(request: Request, ctx: AdminContext = Depends(get_admin_ctx),
                      admin: User = Depends(current_admin)):
        raw = {k: json.dumps(v) for k, v in sorted(ctx.settings.all().items())}
        return _render(request, "settings.html", admin=admin, active="settings",
                       settings=raw)

    @app.post("/settings")
    async def settings_save(request: Request, ctx: AdminContext = Depends(get_admin_ctx),
                            admin: User = Depends(current_admin)):
        form = await request.form()
        current = ctx.settings.all()
        changed, invalid = {}, []
        for field, value in form.items():
            if not field.startswith("key__"):
                continue
            key = field[len("key__"):]
            try:
                parsed = json.loads(value)
            except json.JSONDecodeError:
                invalid.append(key)
                continue
            if current.get(key) != parsed:
                ctx.settings.set(key, parsed, updated_by=admin.email)
                changed[key] = parsed
        if changed:
            _audit(ctx, admin, "settings.update", after=changed)
        msg = f"Saved {len(changed)} setting(s)."
        if invalid:
            msg += f" Skipped invalid JSON: {', '.join(invalid)}."
        return _flash_redirect("/settings", msg)

    # -- jobs & pool --

    @app.get("/jobs", response_class=HTMLResponse)
    def jobs_page(request: Request, ctx: AdminContext = Depends(get_admin_ctx),
                  admin: User = Depends(current_admin)):
        return _render(request, "jobs.html", admin=admin, active="jobs",
                       pool_count=PostingRepo(ctx.conn).count(),
                       job_counts=JobRepo(ctx.conn).counts_by_status(),
                       jobs=JobRepo(ctx.conn).list_recent(limit=50))

    @app.post("/jobs/scrape-now")
    def scrape_now(ctx: AdminContext = Depends(get_admin_ctx),
                   admin: User = Depends(current_admin)):
        jid = JobQueue(ctx.admin.service).enqueue(ctx.conn, KIND_SCRAPE, user_id=None,
                                                  params={})
        _audit(ctx, admin, "scrape.run_now", target_type="job", target_id=jid)
        return _flash_redirect("/jobs", "Scrape enqueued.")

    @app.post("/jobs/purge-now")
    def purge_now(ctx: AdminContext = Depends(get_admin_ctx),
                  admin: User = Depends(current_admin)):
        jid = JobQueue(ctx.admin.service).enqueue(ctx.conn, KIND_PURGE, user_id=None,
                                                  params={})
        _audit(ctx, admin, "purge.run_now", target_type="job", target_id=jid)
        return _flash_redirect("/jobs", "Purge enqueued.")

    @app.post("/jobs/{job_id}/retry")
    def retry_job(job_id: str, ctx: AdminContext = Depends(get_admin_ctx),
                  admin: User = Depends(current_admin)):
        rec = JobRepo(ctx.conn).get(job_id)
        if rec is None:
            return redirect("/jobs")
        jid = JobQueue(ctx.admin.service).enqueue(ctx.conn, rec.kind,
                                                  user_id=rec.user_id, params=rec.params)
        _audit(ctx, admin, "job.retry", target_type="job", target_id=jid,
               before={"of": job_id})
        return _flash_redirect("/jobs", "Job re-enqueued.")

    # -- LLM usage / activity (per-draft metrics: tokens, cost, duration) --

    @app.get("/usage", response_class=HTMLResponse)
    def usage_page(request: Request, action: str | None = None,
                   ctx: AdminContext = Depends(get_admin_ctx),
                   admin: User = Depends(current_admin)):
        repo = LLMUsageRepo(ctx.conn)
        action = action if action in _USAGE_ACTIONS else None
        events = repo.list_recent(limit=100, action=action)
        summary = repo.summary(action=action)
        durations = [e.duration_seconds for e in events
                     if e.duration_seconds is not None]
        summary["avg_duration"] = (sum(durations) / len(durations)
                                   if durations else None)
        return _render(request, "usage.html", admin=admin, active="usage",
                       events=events, summary=summary, action=action or "",
                       actions=_USAGE_ACTIONS)

    # -- postings (browse the scraped job pool) --

    @app.get("/postings", response_class=HTMLResponse)
    def postings_page(request: Request, q: str | None = None,
                      source: str | None = None, remote: str | None = None,
                      days: str | None = None, page: int = 1,
                      ctx: AdminContext = Depends(get_admin_ctx),
                      admin: User = Depends(current_admin)):
        per_page = 50
        page = max(1, page)
        remote_flag = {"remote": True, "onsite": False}.get(remote or "")
        days_val = int(days) if (days or "").isdigit() else None
        repo = PostingRepo(ctx.conn)
        posts, total = repo.search(
            q=q, source=source or None, remote=remote_flag,
            seen_within_days=days_val, limit=per_page, offset=(page - 1) * per_page)
        pages = max(1, (total + per_page - 1) // per_page)
        return _render(request, "postings.html", admin=admin, active="postings",
                       posts=posts, total=total, page=page, pages=pages,
                       q=q or "", source=source or "", remote=remote or "",
                       days=days or "", pool_total=repo.count(),
                       sources=[s for s, _ in repo.counts_by_source()])

    # -- sources / audit --

    @app.get("/sources", response_class=HTMLResponse)
    def sources_page(request: Request, ctx: AdminContext = Depends(get_admin_ctx),
                     admin: User = Depends(current_admin)):
        counts = dict(PostingRepo(ctx.conn).counts_by_source())
        enabled = list(ctx.settings.get("sources.enabled", []) or [])
        # Every source that's enabled or has postings, with its pool count.
        names = sorted(set(counts) | set(enabled))
        rows = [{"source": s, "count": counts.get(s, 0), "enabled": s in enabled}
                for s in names]
        rows.sort(key=lambda r: (-r["count"], r["source"]))
        return _render(request, "sources.html", admin=admin, active="sources",
                       rows=rows, pool_total=PostingRepo(ctx.conn).count())

    @app.post("/sources/{source}/delete")
    def delete_source_postings(source: str, ctx: AdminContext = Depends(get_admin_ctx),
                               admin: User = Depends(current_admin)):
        n = PostingRepo(ctx.conn).delete_by_source(source)
        _audit(ctx, admin, "sources.delete_postings", target_type="source",
               target_id=source, after={"deleted": n})
        return _flash_redirect("/sources", f"Deleted {n} posting(s) from {source}.")

    @app.get("/audit", response_class=HTMLResponse)
    def audit_page(request: Request, ctx: AdminContext = Depends(get_admin_ctx),
                   admin: User = Depends(current_admin)):
        return _render(request, "audit.html", admin=admin, active="audit",
                       entries=AuditRepo(ctx.conn).list_recent(limit=200))

    @app.get("/healthz", response_class=HTMLResponse)
    def healthz():
        return HTMLResponse("ok")

    return app
