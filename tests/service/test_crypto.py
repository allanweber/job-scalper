from __future__ import annotations

import base64

import pytest

from scalper.service.crypto import KeyVault, generate_master_key_b64


def test_seal_open_roundtrip(vault):
    sealed = vault.seal("sk-secret-123")
    assert sealed.key_version == 1
    assert sealed.ciphertext != b"sk-secret-123"
    assert vault.open(sealed) == "sk-secret-123"


def test_ciphertext_is_nondeterministic(vault):
    a = vault.seal("same")
    b = vault.seal("same")
    assert a.nonce != b.nonce
    assert a.ciphertext != b.ciphertext
    assert vault.open(a) == vault.open(b) == "same"


def test_aad_binding(vault):
    sealed = vault.seal("secret", aad=b"user:1|anthropic")
    assert vault.open(sealed, aad=b"user:1|anthropic") == "secret"
    with pytest.raises(Exception):
        vault.open(sealed, aad=b"user:2|anthropic")


def test_rotation_detection_and_multi_version():
    k1 = base64.b64decode(generate_master_key_b64())
    k2 = base64.b64decode(generate_master_key_b64())
    old = KeyVault({1: k1}, active_version=1)
    sealed_v1 = old.seal("legacy")
    # New vault knows both keys, active is 2.
    new = KeyVault({1: k1, 2: k2}, active_version=2)
    assert new.open(sealed_v1) == "legacy"          # still decrypts old version
    assert new.needs_rotation(sealed_v1) is True
    resealed = new.seal("legacy")
    assert resealed.key_version == 2
    assert new.needs_rotation(resealed) is False


def test_missing_key_version_fails(vault):
    sealed = vault.seal("x")
    object.__setattr__(sealed, "key_version", 99)
    with pytest.raises(KeyError):
        vault.open(sealed)


def test_from_env(monkeypatch):
    key_b64 = generate_master_key_b64()
    monkeypatch.setenv("SCALPER_ENC_KEYS", f'{{"1": "{key_b64}"}}')
    monkeypatch.setenv("SCALPER_ENC_ACTIVE_VERSION", "1")
    v = KeyVault.from_env()
    assert v.active_version == 1
    assert v.open(v.seal("hi")) == "hi"


def test_rejects_wrong_key_size():
    with pytest.raises(ValueError):
        KeyVault({1: b"tooshort"}, active_version=1)
