"""Envelope encryption for BYO LLM API keys (ADR 0009).

Keys are encrypted at rest with AES-256-GCM under a master key held in the
environment (never the database). Each ciphertext records the **master-key
version** used, so rotation is a background re-encrypt rather than a migration:
old versions stay available for decryption while new writes use the active
version.

Environment:
  SCALPER_ENC_KEYS            JSON {"<version>": "<base64 32-byte key>", ...}
  SCALPER_ENC_ACTIVE_VERSION  integer version used for new encryptions

The guarantee is honest about scope (ADR/DESIGN): this protects against database
theft and casual operator access, not a fully compromised running host that can
read the env.
"""

from __future__ import annotations

import base64
import json
import os
from dataclasses import dataclass

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

_NONCE_BYTES = 12
_KEY_BYTES = 32


@dataclass(frozen=True)
class Sealed:
    """An encrypted secret: ciphertext + nonce + the master-key version used."""

    ciphertext: bytes
    nonce: bytes
    key_version: int


class KeyVault:
    """Holds versioned master keys and seals/opens secrets with them."""

    def __init__(self, keys: dict[int, bytes], active_version: int):
        if not keys:
            raise ValueError("KeyVault requires at least one master key")
        if active_version not in keys:
            raise ValueError(f"active version {active_version} not in provided keys")
        for v, k in keys.items():
            if len(k) != _KEY_BYTES:
                raise ValueError(f"master key v{v} must be {_KEY_BYTES} bytes, got {len(k)}")
        self._keys = dict(keys)
        self._active = active_version

    @classmethod
    def from_env(cls, environ: dict[str, str] | None = None) -> "KeyVault":
        env = environ if environ is not None else os.environ
        raw = env.get("SCALPER_ENC_KEYS")
        if not raw:
            raise RuntimeError(
                "SCALPER_ENC_KEYS is not set — cannot encrypt/decrypt BYO keys."
            )
        parsed = json.loads(raw)
        keys = {int(v): base64.b64decode(k) for v, k in parsed.items()}
        active = int(env.get("SCALPER_ENC_ACTIVE_VERSION", max(keys)))
        return cls(keys, active)

    @property
    def active_version(self) -> int:
        return self._active

    def seal(self, plaintext: str, *, aad: bytes | None = None) -> Sealed:
        """Encrypt `plaintext` under the active master key."""
        nonce = os.urandom(_NONCE_BYTES)
        aead = AESGCM(self._keys[self._active])
        ct = aead.encrypt(nonce, plaintext.encode("utf-8"), aad)
        return Sealed(ciphertext=ct, nonce=nonce, key_version=self._active)

    def open(self, sealed: Sealed, *, aad: bytes | None = None) -> str:
        """Decrypt a `Sealed` secret using the key version it was sealed with."""
        key = self._keys.get(sealed.key_version)
        if key is None:
            raise KeyError(
                f"no master key for version {sealed.key_version}; cannot decrypt"
            )
        aead = AESGCM(key)
        return aead.decrypt(sealed.nonce, sealed.ciphertext, aad).decode("utf-8")

    def needs_rotation(self, sealed: Sealed) -> bool:
        """True if `sealed` was encrypted under a non-active key version."""
        return sealed.key_version != self._active


def generate_master_key_b64() -> str:
    """Convenience for ops: a fresh base64 32-byte master key."""
    return base64.b64encode(os.urandom(_KEY_BYTES)).decode("ascii")
