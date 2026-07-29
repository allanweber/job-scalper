"""Google web OAuth for admin login (ADR 0010).

The admin app uses the Google **authorization-code** web flow (distinct from the
mobile ID-token flow): redirect to Google, exchange the returned code for the
user's identity, then gate on the admin allowlist. The exchange is behind an
`OAuthClient` protocol so tests inject a fake and the real `authlib`/httpx
dependency is only used in production.
"""

from __future__ import annotations

from typing import Any, Protocol
from urllib.parse import urlencode

from scalper.service.models import GoogleIdentity

_AUTH_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
_TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
_USERINFO_ENDPOINT = "https://openidconnect.googleapis.com/v1/userinfo"


class OAuthError(Exception):
    pass


class OAuthClient(Protocol):
    def authorize_url(self, *, state: str, redirect_uri: str) -> str: ...
    def exchange_code(self, *, code: str, redirect_uri: str) -> GoogleIdentity: ...


class GoogleOAuthClient:
    """Real Google OAuth code-flow client (uses httpx; no heavy SDK)."""

    def __init__(self, client_id: str, client_secret: str):
        if not client_id or not client_secret:
            raise ValueError("Google OAuth client id/secret are required")
        self._id = client_id
        self._secret = client_secret

    def authorize_url(self, *, state: str, redirect_uri: str) -> str:
        params = {
            "client_id": self._id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": "openid email profile",
            "state": state,
            "access_type": "online",
            "prompt": "select_account",
        }
        return f"{_AUTH_ENDPOINT}?{urlencode(params)}"

    def exchange_code(self, *, code: str, redirect_uri: str) -> GoogleIdentity:  # pragma: no cover - network
        import httpx

        with httpx.Client(timeout=30.0) as client:
            token_resp = client.post(_TOKEN_ENDPOINT, data={
                "code": code, "client_id": self._id, "client_secret": self._secret,
                "redirect_uri": redirect_uri, "grant_type": "authorization_code",
            })
            if token_resp.status_code != 200:
                raise OAuthError(f"token exchange failed: {token_resp.text}")
            access_token = token_resp.json().get("access_token")
            if not access_token:
                raise OAuthError("no access_token in token response")
            info = client.get(_USERINFO_ENDPOINT,
                              headers={"Authorization": f"Bearer {access_token}"})
            if info.status_code != 200:
                raise OAuthError(f"userinfo failed: {info.text}")
            claims: dict[str, Any] = info.json()
        if not claims.get("email"):
            raise OAuthError("userinfo has no email")
        return GoogleIdentity(
            sub=claims["sub"], email=claims["email"],
            email_verified=bool(claims.get("email_verified", False)),
            name=claims.get("name"), picture=claims.get("picture"),
        )
