"""Push delivery: an FCM HTTP v1 sender behind a small protocol.

The notify job talks to a :class:`PushSender`; production wires an
:class:`FcmPushSender` (Firebase Cloud Messaging HTTP v1), tests inject a fake,
and an unconfigured environment falls back to :class:`NullPushSender` so the app
runs fine with no push credentials. Sending returns the invalid/unregistered
tokens so the caller can prune them.

Configuration (all via env):
  SCALPER_FCM_PROJECT_ID    – the Firebase project id
  SCALPER_FCM_CREDENTIALS   – the service-account JSON (inline), OR
  GOOGLE_APPLICATION_CREDENTIALS – path to the service-account JSON file
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Protocol

logger = logging.getLogger("scalper.push")

_FCM_SCOPE = "https://www.googleapis.com/auth/firebase.messaging"
_FCM_ENDPOINT = "https://fcm.googleapis.com/v1/projects/{project}/messages:send"


@dataclass
class SendResult:
    sent: int = 0
    #: Tokens FCM rejected as unregistered/invalid — safe to delete.
    invalid_tokens: list[str] = field(default_factory=list)


class PushSender(Protocol):
    def send(self, tokens: list[str], *, title: str, body: str,
             data: dict[str, str]) -> SendResult:
        ...


class NullPushSender:
    """No-op sender used when push isn't configured (dev / missing creds)."""

    def send(self, tokens: list[str], *, title: str, body: str,
             data: dict[str, str]) -> SendResult:
        logger.debug("push disabled — would send to %d device(s): %s",
                     len(tokens), title)
        return SendResult()


class FcmPushSender:
    """Firebase Cloud Messaging HTTP v1 sender (one request per token)."""

    def __init__(self, project_id: str, credentials: Any):
        self._project_id = project_id
        self._credentials = credentials  # google.oauth2 service-account creds

    def _access_token(self) -> str:
        from google.auth.transport.requests import Request

        if not self._credentials.valid:
            self._credentials.refresh(Request())
        return self._credentials.token

    def send(self, tokens: list[str], *, title: str, body: str,
             data: dict[str, str]) -> SendResult:
        if not tokens:
            return SendResult()
        import httpx

        result = SendResult()
        try:
            token_header = self._access_token()
        except Exception:  # pragma: no cover - network/credential failure
            logger.exception("FCM auth failed; dropping notification")
            return result
        url = _FCM_ENDPOINT.format(project=self._project_id)
        headers = {"Authorization": f"Bearer {token_header}"}
        # FCM data values must be strings.
        str_data = {k: str(v) for k, v in data.items()}
        for token in tokens:
            payload = {"message": {
                "token": token,
                "notification": {"title": title, "body": body},
                "data": str_data,
            }}
            try:
                r = httpx.post(url, headers=headers, json=payload, timeout=10.0)
            except Exception:  # pragma: no cover - transient network
                logger.warning("FCM send failed for a token (network)")
                continue
            if r.status_code == 200:
                result.sent += 1
            elif r.status_code in (404, 400):
                # UNREGISTERED (stale token) or invalid — prune it.
                result.invalid_tokens.append(token)
            else:  # pragma: no cover - server-side hiccup
                logger.warning("FCM send returned %s", r.status_code)
        return result


def _parse_credentials(raw: str) -> dict:
    """Parse the service-account JSON from an env value.

    Tolerates the two ways an env editor mangles a big JSON blob: surrounding
    quotes, and — because raw JSON with spaces/braces/newlines is fragile in
    many env UIs — a base64-encoded form. Tries plain JSON first, then base64.
    """
    raw = raw.strip()
    if len(raw) >= 2 and raw[0] == raw[-1] and raw[0] in "\"'":
        raw = raw[1:-1].strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        import base64

        return json.loads(base64.b64decode(raw))


def build_push_sender(env: dict[str, str]) -> PushSender:
    """Build the configured sender, or a no-op when push isn't set up.

    Never raises: any missing config or unavailable google-auth degrades to
    :class:`NullPushSender` with a log line, so the service always starts.

    Credentials come from ``SCALPER_FCM_CREDENTIALS`` (the service-account JSON,
    or that JSON base64-encoded) or ``GOOGLE_APPLICATION_CREDENTIALS`` (a path).
    """
    project_id = env.get("SCALPER_FCM_PROJECT_ID")
    raw = env.get("SCALPER_FCM_CREDENTIALS")
    cred_path = env.get("GOOGLE_APPLICATION_CREDENTIALS")
    if not project_id or not (raw or cred_path):
        return NullPushSender()
    try:
        from google.oauth2 import service_account

        info = _parse_credentials(raw) if raw else json.load(open(cred_path))
        creds = service_account.Credentials.from_service_account_info(
            info, scopes=[_FCM_SCOPE])
        return FcmPushSender(project_id, creds)
    except Exception:
        logger.exception(
            "FCM credentials invalid/unavailable — push disabled. Set "
            "SCALPER_FCM_CREDENTIALS to the service-account JSON or its base64.")
        return NullPushSender()
