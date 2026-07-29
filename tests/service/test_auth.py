from __future__ import annotations

import pytest

from scalper.service.auth import AccountInactive, InvalidToken
from scalper.service.models import GoogleIdentity
from scalper.service.repositories import UserRepo

from _helpers import make_auth

IDENT = GoogleIdentity(sub="g-1", email="Alice@example.com", email_verified=True, name="Alice")


def test_sign_in_creates_user_and_tokens(conn):
    auth = make_auth(conn, IDENT)
    user, pair = auth.sign_in_with_google("good")
    assert user.email == "alice@example.com"      # normalized
    assert user.role == "user"
    assert user.plan == "free"
    assert pair.access_token and pair.refresh_token
    assert pair.expires_in == 900
    claims = auth.verify_access(pair.access_token)
    assert claims["sub"] == user.id
    assert claims["role"] == "user"
    assert claims["type"] == "access"


def test_admin_allowlist_grants_role(conn):
    auth = make_auth(conn, IDENT, admin_emails=["alice@example.com"])
    user, _ = auth.sign_in_with_google("good")
    assert user.role == "admin"


def test_sign_in_is_idempotent_by_sub(conn):
    auth = make_auth(conn, IDENT)
    u1, _ = auth.sign_in_with_google("good")
    u2, _ = auth.sign_in_with_google("good")
    assert u1.id == u2.id
    assert UserRepo(conn).count() == 1


def test_unverified_email_rejected(conn):
    auth = make_auth(conn, GoogleIdentity(sub="g-2", email="b@x.com", email_verified=False))
    with pytest.raises(InvalidToken):
        auth.sign_in_with_google("good")


def test_bad_token_rejected(conn):
    auth = make_auth(conn, IDENT)
    with pytest.raises(InvalidToken):
        auth.sign_in_with_google("bad")


def test_suspended_account_cannot_sign_in(conn):
    auth = make_auth(conn, IDENT)
    user, _ = auth.sign_in_with_google("good")
    UserRepo(conn).set_status(user.id, "suspended")
    with pytest.raises(AccountInactive):
        auth.sign_in_with_google("good")


def test_refresh_rotates_and_revokes_old(conn):
    auth = make_auth(conn, IDENT)
    _, pair = auth.sign_in_with_google("good")
    _, pair2 = auth.refresh(pair.refresh_token)
    assert pair2.refresh_token != pair.refresh_token
    assert auth.verify_access(pair2.access_token)["type"] == "access"
    # Reusing the old (now rotated) refresh token is rejected...
    with pytest.raises(InvalidToken):
        auth.refresh(pair.refresh_token)
    # ...and reuse detection revokes the whole family, so the new one dies too.
    with pytest.raises(InvalidToken):
        auth.refresh(pair2.refresh_token)


def test_logout_revokes_refresh(conn):
    auth = make_auth(conn, IDENT)
    _, pair = auth.sign_in_with_google("good")
    auth.logout(pair.refresh_token)
    with pytest.raises(InvalidToken):
        auth.refresh(pair.refresh_token)


def test_unknown_refresh_rejected(conn):
    auth = make_auth(conn, IDENT)
    with pytest.raises(InvalidToken):
        auth.refresh("never-issued")


def test_access_token_wrong_secret_rejected(conn):
    auth = make_auth(conn, IDENT)
    _, pair = auth.sign_in_with_google("good")
    auth._cfg.jwt_secret = "different"
    with pytest.raises(InvalidToken):
        auth.verify_access(pair.access_token)
