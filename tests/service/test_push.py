"""Tests for the FCM credential loader and sender selection."""

from __future__ import annotations

import base64
import json

from scalper.service.push import (
    NullPushSender,
    _parse_credentials,
    build_push_sender,
)


def test_parse_credentials_plain_json():
    d = {"type": "service_account", "project_id": "p"}
    assert _parse_credentials(json.dumps(d)) == d


def test_parse_credentials_strips_wrapping_quotes():
    d = {"a": 1}
    assert _parse_credentials("'" + json.dumps(d) + "'") == d
    assert _parse_credentials('"' + json.dumps(d) + '"') == d


def test_parse_credentials_accepts_base64():
    # Newlines in a private_key are exactly what makes raw JSON fragile in env
    # editors; base64 sidesteps that.
    d = {"private_key": "-----BEGIN-----\nabc\n-----END-----\n", "x": 1}
    encoded = base64.b64encode(json.dumps(d).encode()).decode()
    assert _parse_credentials(encoded) == d


def test_build_push_sender_without_config_is_null():
    assert isinstance(build_push_sender({}), NullPushSender)
    # project id but no credentials → still null (no crash).
    assert isinstance(
        build_push_sender({"SCALPER_FCM_PROJECT_ID": "p"}), NullPushSender)


def test_build_push_sender_bad_credentials_degrades_to_null():
    # Non-JSON, non-base64 junk must not crash the service.
    sender = build_push_sender(
        {"SCALPER_FCM_PROJECT_ID": "p", "SCALPER_FCM_CREDENTIALS": "not json"})
    assert isinstance(sender, NullPushSender)
