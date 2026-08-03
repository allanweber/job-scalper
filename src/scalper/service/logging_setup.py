"""Structured request logging for the public API + admin apps (shared).

One JSON line per request (method, route template, raw path, status, latency,
request id, authenticated user, client IP, user-agent, redacted query, response
size) so the same log serves debugging, rough metrics, and an audit trail. A
catch-all handler logs unhandled exceptions with a traceback and returns the
request id to the caller.

Configuration is environment-driven:
  * ``LOG_LEVEL``  — root level (default ``INFO``).
  * ``LOG_FORMAT`` — ``json`` (default) or ``text`` (human-readable, for local dev).

Wire into an app with::

    configure_logging()
    app.add_middleware(RequestLoggingMiddleware)
    app.add_exception_handler(Exception, unhandled_exception_handler)

`configure_logging` also silences uvicorn's own access log, since our request
line replaces it (the Docker CMD passes ``--no-access-log`` too, belt-and-braces).
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable
from urllib.parse import parse_qsl, urlencode
from uuid import uuid4

from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

# Request-scoped id, set by the middleware before the route runs so any log
# emitted while handling a request (including the exception handler) can carry
# it. Not used for user id — see `RequestLoggingMiddleware`.
_request_id_ctx: ContextVar[str | None] = ContextVar("request_id", default=None)

_request_log = logging.getLogger("scalper.request")
_log = logging.getLogger("scalper.service")

#: Health/readiness probes hit constantly; logged at DEBUG so they're silent at
#: the default INFO level but reappear when LOG_LEVEL=debug.
_HEALTH_PATHS = frozenset({"/healthz", "/readyz"})

#: Query-string keys whose values are replaced with a placeholder before logging.
_SENSITIVE_QUERY_KEYS = frozenset({
    "token", "api_key", "apikey", "password", "code", "id_token",
    "access_token", "refresh_token", "secret", "authorization",
})

#: Standard LogRecord attributes — everything else on a record is an `extra`
#: field we serialize.
_RESERVED_RECORD_KEYS = frozenset({
    "name", "msg", "args", "levelname", "levelno", "pathname", "filename",
    "module", "exc_info", "exc_text", "stack_info", "lineno", "funcName",
    "created", "msecs", "relativeCreated", "thread", "threadName",
    "processName", "process", "taskName", "message", "asctime",
})


def _extras(record: logging.LogRecord) -> dict[str, Any]:
    return {
        k: v
        for k, v in record.__dict__.items()
        if k not in _RESERVED_RECORD_KEYS and not k.startswith("_")
    }


class JsonFormatter(logging.Formatter):
    """Render each record as a single JSON object (one line)."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(
                record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        rid = _request_id_ctx.get()
        if rid and "request_id" not in record.__dict__:
            payload["request_id"] = rid
        payload.update(_extras(record))
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str)


class TextFormatter(logging.Formatter):
    """Human-readable single line for local dev (LOG_FORMAT=text)."""

    def format(self, record: logging.LogRecord) -> str:
        extras = _extras(record)
        rid = extras.pop("request_id", None) or _request_id_ctx.get()
        ts = datetime.fromtimestamp(
            record.created, tz=timezone.utc).strftime("%H:%M:%S")
        line = f"{ts} {record.levelname:<7} {record.name}  {record.getMessage()}"
        if extras:
            line += "  " + " ".join(f"{k}={v}" for k, v in extras.items())
        if rid:
            line += f"  request_id={rid}"
        if record.exc_info:
            line += "\n" + self.formatException(record.exc_info)
        return line


def configure_logging() -> logging.Handler:
    """Install our stdout handler on the root logger. Idempotent per process."""
    level_name = os.environ.get("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)
    fmt = os.environ.get("LOG_FORMAT", "json").strip().lower()
    formatter: logging.Formatter = (
        TextFormatter() if fmt == "text" else JsonFormatter())

    root = logging.getLogger()
    root.setLevel(level)
    # Drop a handler we installed on a previous call (e.g. across app factories
    # in tests) so re-configuration doesn't duplicate every line.
    for handler in list(root.handlers):
        if getattr(handler, "_scalper_logging", False):
            root.removeHandler(handler)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)
    handler._scalper_logging = True  # type: ignore[attr-defined]
    root.addHandler(handler)

    # Our per-request line replaces uvicorn's plain access log.
    logging.getLogger("uvicorn.access").disabled = True
    return handler


def _redact_query(raw: str) -> str:
    if not raw:
        return ""
    pairs = parse_qsl(raw, keep_blank_values=True)
    redacted = [
        (k, "[redacted]" if k.lower() in _SENSITIVE_QUERY_KEYS else v)
        for k, v in pairs
    ]
    return urlencode(redacted)


def _client_ip(request: Request) -> str | None:
    # Behind the reverse proxy the real client is the first X-Forwarded-For hop.
    xff = request.headers.get("x-forwarded-for")
    if xff:
        return xff.split(",")[0].strip()
    return request.client.host if request.client else None


def _level_for(path: str, status: int) -> int:
    if path in _HEALTH_PATHS:
        return logging.DEBUG
    if status >= 500:
        return logging.ERROR
    if status >= 400:
        return logging.WARNING
    return logging.INFO


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    """Emit one structured line per request when it completes.

    The request id is set on a contextvar (so downstream logs + the exception
    handler carry it) and on ``request.state``. The authenticated user id is read
    back from ``request.state`` — the auth dependency sets it while handling the
    route, and ``request.state`` (unlike a contextvar set downstream) survives the
    BaseHTTPMiddleware task boundary.
    """

    async def dispatch(
        self,
        request: Request,
        call_next: Callable[[Request], Awaitable[Response]],
    ) -> Response:
        rid = request.headers.get("x-request-id") or uuid4().hex
        token = _request_id_ctx.set(rid)
        request.state.request_id = rid
        request.state.user_id = None
        start = time.perf_counter()
        try:
            try:
                response = await call_next(request)
            except Exception:
                # Truly-unhandled: log the completion line, then let
                # ServerErrorMiddleware turn it into a 500 via our handler.
                self._emit(request, 500, self._elapsed_ms(start), rid)
                raise
            response.headers["X-Request-ID"] = rid
            self._emit(request, response.status_code, self._elapsed_ms(start),
                       rid, response=response)
            return response
        finally:
            _request_id_ctx.reset(token)

    @staticmethod
    def _elapsed_ms(start: float) -> float:
        return round((time.perf_counter() - start) * 1000, 2)

    def _emit(self, request: Request, status: int, latency_ms: float, rid: str,
              response: Response | None = None) -> None:
        path = request.url.path
        route = getattr(request.scope.get("route"), "path", None)
        resp_bytes: int | None = None
        if response is not None:
            cl = response.headers.get("content-length")
            resp_bytes = int(cl) if cl and cl.isdigit() else None
        _request_log.log(_level_for(path, status), "request", extra={
            "request_id": rid,
            "method": request.method,
            "route": route,
            "path": path,
            "status": status,
            "latency_ms": latency_ms,
            "user_id": getattr(request.state, "user_id", None),
            "client_ip": _client_ip(request),
            "user_agent": request.headers.get("user-agent"),
            "query": _redact_query(request.url.query),
            "response_bytes": resp_bytes,
        })


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Log an unhandled exception with its traceback and return the request id."""
    rid = getattr(request.state, "request_id", None) or _request_id_ctx.get()
    _log.error("unhandled exception", exc_info=exc, extra={
        "request_id": rid,
        "method": request.method,
        "path": request.url.path,
    })
    return JSONResponse(
        status_code=500,
        content={"detail": "internal server error", "request_id": rid},
        headers={"X-Request-ID": rid} if rid else None,
    )
