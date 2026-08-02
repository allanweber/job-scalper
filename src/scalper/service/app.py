"""FastAPI application factory for the public API (Phase 3).

Wires the routers over a `Container`. `create_app()` with no argument builds the
production container from the environment (use uvicorn's factory mode:
`uvicorn --factory scalper.service.app:create_app`); tests pass a container built
with fakes and a temp DB. Migrations are applied at construction so a fresh deploy
is self-provisioning.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from scalper.db import apply_pending
from scalper.service.container import Container
from scalper.service.logging_setup import (
    RequestLoggingMiddleware,
    configure_logging,
    unhandled_exception_handler,
)
from scalper.service.routers import account, auth, drafts, feed, jobs, postings, system

_TITLE = "Job Scalper API"
_VERSION = "0.1.0"


def create_app(container: Container | None = None) -> FastAPI:
    configure_logging()
    container = container or Container.from_env()

    # Self-provision: apply any pending migrations against the target DB.
    conn = container.connect()
    try:
        apply_pending(conn)
    finally:
        conn.close()

    app = FastAPI(title=_TITLE, version=_VERSION)
    app.state.container = container

    origins = [o for o in container.environ.get("SCALPER_CORS_ORIGINS", "*").split(",") if o]
    app.add_middleware(
        CORSMiddleware,
        allow_origins=origins or ["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    # Added last so it's the outermost middleware — it times the whole request.
    app.add_middleware(RequestLoggingMiddleware)
    app.add_exception_handler(Exception, unhandled_exception_handler)

    for module in (system, auth, account, feed, drafts, postings, jobs):
        app.include_router(module.router)

    return app
