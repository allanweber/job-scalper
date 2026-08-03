"""Admin dependencies: request-scoped DB connection + session-authenticated admin.

The admin cookie carries an HMAC-signed session id; the session payload lives in
the store. `current_admin` loads the session, re-checks the allowlist role and
active status on every request (so revoking admin takes effect immediately), and
redirects to /login when unauthenticated.
"""

from __future__ import annotations

import hashlib
import hmac
from dataclasses import dataclass
from typing import Any, Iterator

from fastapi import Depends, Request
from fastapi.responses import RedirectResponse

from scalper.admin.container import AdminContainer
from scalper.service.models import User
from scalper.service.repositories import UserRepo
from scalper.service.settings import Settings


class _Redirect(Exception):
    """Signals an auth redirect; the app's exception handler renders it."""

    def __init__(self, location: str):
        self.location = location


@dataclass
class AdminContext:
    admin: AdminContainer
    conn: Any

    @property
    def settings(self) -> Settings:
        return self.admin.service.settings(self.conn)


def sign_sid(secret: str, sid: str) -> str:
    mac = hmac.new(secret.encode(), sid.encode(), hashlib.sha256).hexdigest()
    return f"{sid}.{mac}"


def unsign_sid(secret: str, value: str) -> str | None:
    if not value or "." not in value:
        return None
    sid, _, mac = value.rpartition(".")
    expected = hmac.new(secret.encode(), sid.encode(), hashlib.sha256).hexdigest()
    return sid if hmac.compare_digest(mac, expected) else None


def get_admin(request: Request) -> AdminContainer:
    return request.app.state.admin


def get_admin_ctx(request: Request) -> Iterator[AdminContext]:
    admin: AdminContainer = request.app.state.admin
    conn = admin.service.connect()
    try:
        yield AdminContext(admin=admin, conn=conn)
    finally:
        conn.close()


def current_admin(request: Request, ctx: AdminContext = Depends(get_admin_ctx)) -> User:
    raw = request.cookies.get(ctx.admin.cookie_name, "")
    sid = unsign_sid(ctx.admin.cookie_secret, raw)
    session = ctx.admin.sessions.get(sid) if sid else None
    if not session:
        raise _Redirect("/login")
    user = UserRepo(ctx.conn).get(session.get("user_id", ""))
    if user is None or not user.is_admin or not user.is_active:
        # Role revoked or account suspended since login: drop the session.
        if sid:
            ctx.admin.sessions.delete(sid)
        raise _Redirect("/login")
    # Attribute the request line to this admin (see logging middleware).
    request.state.user_id = user.id
    return user


def redirect(location: str) -> RedirectResponse:
    # 303 so a POST handler's redirect becomes a GET (post/redirect/get).
    return RedirectResponse(location, status_code=303)
