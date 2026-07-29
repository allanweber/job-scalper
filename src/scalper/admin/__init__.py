"""Admin web app (Phase 4): FastAPI + Jinja2 + HTMX operator console.

Runs as its own service on a separate subdomain (ADR 0010). Admins sign in with
Google web OAuth gated by the admin-email allowlist; a server-side session (Redis,
or in-memory for local/CI) keeps them logged in. Every state-changing action is
recorded in `admin_audit`. See docs/DESIGN.md.
"""
