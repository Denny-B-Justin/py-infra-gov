"""
Cryptographic helpers.

* Field-level encryption at rest: AES-256-GCM with a random 96-bit nonce per
  value. Ciphertext is stored as ``enc:v1:<base64url(nonce|ciphertext|tag)>``.
  Values without the prefix are treated as legacy plaintext (so migrated data
  stays readable) and are encrypted the next time they are written.
* Token hashing: random tokens (sessions, password resets, invitations) are
  only ever stored as SHA-256 digests, so a database leak cannot be replayed.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import os
import secrets

import constants as C

log = logging.getLogger("infragov.crypto")
_PREFIX = "enc:v1:"
_aesgcm = None


def _cipher():
    global _aesgcm
    if _aesgcm is not None:
        return _aesgcm
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    key_b64 = C.FIELD_ENCRYPTION_KEY
    if not key_b64:
        if C.IS_PRODUCTION:
            raise RuntimeError("FIELD_ENCRYPTION_KEY is not configured")
        # Development only: deterministic throw-away key so local data works.
        key = hashlib.sha256(b"infragov-local-development-key").digest()
    else:
        key = base64.urlsafe_b64decode(key_b64 + "=" * (-len(key_b64) % 4))
        if len(key) != 32:
            raise RuntimeError("FIELD_ENCRYPTION_KEY must decode to exactly 32 bytes")
    _aesgcm = AESGCM(key)
    return _aesgcm


def encrypt_field(plaintext: str | None) -> str:
    if not plaintext:
        return ""
    if plaintext.startswith(_PREFIX):
        return plaintext
    nonce = os.urandom(12)
    ct = _cipher().encrypt(nonce, plaintext.encode("utf-8"), b"infragov")
    return _PREFIX + base64.urlsafe_b64encode(nonce + ct).decode("ascii").rstrip("=")


def decrypt_field(value: str | None) -> str:
    if not value:
        return ""
    if not value.startswith(_PREFIX):
        return value  # legacy plaintext (pre-migration)
    raw = value[len(_PREFIX):]
    try:
        blob = base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4))
        return _cipher().decrypt(blob[:12], blob[12:], b"infragov").decode("utf-8")
    except Exception:  # noqa: BLE001
        log.error("Field decryption failed (wrong FIELD_ENCRYPTION_KEY?)")
        return ""


def new_token(nbytes: int = 32) -> str:
    return secrets.token_urlsafe(nbytes)


def sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def keyed_hash(value: str) -> str:
    """HMAC used to pseudonymise IPs in the security log."""
    key = (C.SECRET_KEY or "dev").encode("utf-8")
    return hmac.new(key, value.encode("utf-8"), hashlib.sha256).hexdigest()[:24]


def constant_time_equals(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))


def generate_field_key() -> str:
    return base64.urlsafe_b64encode(os.urandom(32)).decode("ascii")
