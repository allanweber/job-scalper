"""FastAPI dependencies: request-scoped DB connection + authenticated user.

Each request opens its own connection from the container (matching libsql/worker
semantics) and closes it when the request ends. `current_user` verifies the access
JWT, loads the user, and rejects suspended accounts.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterator

from fastapi import Depends, Header, HTTPException, Request, status

from scalper.service.auth import InvalidToken
from scalper.service.container import Container
from scalper.service.models import User
from scalper.service.repositories import UserRepo
from scalper.service.settings import Settings


@dataclass
class RequestContext:
    container: Container
    conn: Any

    @property
    def settings(self) -> Settings:
        return self.container.settings(self.conn)


def get_container(request: Request) -> Container:
    return request.app.state.container


def get_ctx(request: Request) -> Iterator[RequestContext]:
    container: Container = request.app.state.container
    conn = container.connect()
    try:
        yield RequestContext(container=container, conn=conn)
    finally:
        conn.close()


def _bearer(authorization: str | None) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing bearer token",
                            headers={"WWW-Authenticate": "Bearer"})
    return authorization.split(" ", 1)[1].strip()


def current_user(
    ctx: RequestContext = Depends(get_ctx),
    authorization: str | None = Header(default=None),
) -> User:
    token = _bearer(authorization)
    auth = ctx.container.auth_service(ctx.conn)
    try:
        claims = auth.verify_access(token)
    except InvalidToken as e:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, str(e),
                            headers={"WWW-Authenticate": "Bearer"}) from e
    user = UserRepo(ctx.conn).get(claims["sub"])
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "user not found")
    if not user.is_active:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "account is suspended")
    return user


def require_admin(user: User = Depends(current_user)) -> User:
    if not user.is_admin:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "admin only")
    return user
