"""Authenticator-app MFA (TOTP, RFC 6238) with the shared secret encrypted at rest (AES-GCM).

Codes are 6 digits for 30-second steps, checked one step either side for clock drift. A code is accepted once:
the last used step is stored so a seen code cannot be replayed. The secret is encrypted with
MDARIX_MFA_ENCRYPTION_KEY (URL-safe base64 of 16, 24 or 32 bytes). Local development and tests use a fixed key
so they work without configuration; any other environment without the key cannot enroll (fail closed).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
import struct
import time
from urllib.parse import quote

from backend.app.runtime_env import is_local

DIGITS = 6
STEP_SECONDS = 30
DRIFT_STEPS = 1
ISSUER = "MDARIX"
_PREFIX = b"MDARIXMFA1"


class MfaUnavailable(RuntimeError):
    """MFA secrets cannot be protected in this environment (no encryption key configured)."""


def new_secret() -> str:
    return base64.b32encode(secrets.token_bytes(20)).decode("ascii").rstrip("=")


def provisioning_uri(secret: str, account: str) -> str:
    """The otpauth:// link an authenticator app reads (usually shown as a QR code)."""
    label = quote(f"{ISSUER}:{account}", safe=":@")
    return f"otpauth://totp/{label}?secret={secret}&issuer={ISSUER}&digits={DIGITS}&period={STEP_SECONDS}"


def _step(at: float | None = None) -> int:
    return int((time.time() if at is None else at) // STEP_SECONDS)


def code_at(secret: str, step: int) -> str:
    key = base64.b32decode(secret + "=" * (-len(secret) % 8), casefold=True)
    digest = hmac.new(key, struct.pack(">Q", step), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    number = struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF
    return str(number % 10**DIGITS).zfill(DIGITS)


def current_code(secret: str) -> str:
    return code_at(secret, _step())


def matching_step(secret: str, code: str, last_used_step: int | None = None, at: float | None = None) -> int | None:
    """The time step the code belongs to (within the drift window), or None. A step at or before the last used
    one is refused, so each code works once."""
    candidate = str(code or "").strip()
    if len(candidate) != DIGITS or not candidate.isdigit():
        return None
    now = _step(at)
    for step in range(now - DRIFT_STEPS, now + DRIFT_STEPS + 1):
        if last_used_step is not None and step <= last_used_step:
            continue
        if hmac.compare_digest(code_at(secret, step), candidate):
            return step
    return None


def _key() -> bytes:
    raw = os.getenv("MDARIX_MFA_ENCRYPTION_KEY", "").strip()
    if not raw:
        if is_local():
            return hashlib.sha256(b"mdarix-local-development-mfa-key").digest()
        raise MfaUnavailable("MDARIX_MFA_ENCRYPTION_KEY is not configured")
    key = base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4))
    if len(key) not in {16, 24, 32}:
        raise MfaUnavailable("MDARIX_MFA_ENCRYPTION_KEY must decode to 16, 24 or 32 bytes")
    return key


def encrypt_secret(secret: str, user_id: str) -> str:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    nonce = os.urandom(12)
    sealed = AESGCM(_key()).encrypt(nonce, secret.encode("ascii"), str(user_id).encode("ascii"))
    return base64.urlsafe_b64encode(_PREFIX + nonce + sealed).decode("ascii")


def decrypt_secret(token: str, user_id: str) -> str:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    blob = base64.urlsafe_b64decode(token.encode("ascii"))
    if not blob.startswith(_PREFIX):
        raise ValueError("MFA_SECRET_FORMAT")
    nonce, sealed = blob[len(_PREFIX) : len(_PREFIX) + 12], blob[len(_PREFIX) + 12 :]
    return AESGCM(_key()).decrypt(nonce, sealed, str(user_id).encode("ascii")).decode("ascii")
