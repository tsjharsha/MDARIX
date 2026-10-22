"""Authenticator-app MFA (TOTP, RFC 6238) with the shared secret encrypted at rest (AES-GCM).

Codes are 6 digits for 30-second steps, checked one step either side for clock drift. A code is accepted once:
the last used step is stored so a seen code cannot be replayed. The secret is encrypted with
MDARIX_MFA_ENCRYPTION_KEY (URL-safe base64 of 16, 24 or 32 bytes) and bound to the account it belongs to. Local
development and tests use a fixed key so they work without configuration; any other environment without the key cannot
enroll (fail closed).

The key can rotate (security/keyring.py): with MDARIX_MFA_ENCRYPTION_KEY_ID set (for example k2), new secrets are
sealed as "MDARIXMFA2" with that key ID, and older keys stay readable in MDARIX_MFA_ENCRYPTION_KEYS ("k1:<base64>").
Without a key ID, secrets are sealed as "MDARIXMFA1" exactly as before key IDs existed; those are opened with the
current key and then with each older key. ``python scripts/reseal_mfa_secrets.py --apply`` re-seals every stored
secret with the current key after a rotation.
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
from security import keyring as keys

DIGITS = 6
STEP_SECONDS = 30
DRIFT_STEPS = 1
ISSUER = "MDARIX"
_LEGACY_PREFIX = b"MDARIXMFA1"
_PREFIX = b"MDARIXMFA2"
SETTING = "MDARIX_MFA_ENCRYPTION_KEY"
_LOCAL_KEY = hashlib.sha256(b"mdarix-local-development-mfa-key").digest()


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


def keyring() -> keys.Keyring:
    """The current MFA key (with its ID, if set) and the older keys still readable."""
    try:
        ring = keys.load(SETTING, local_key=_LOCAL_KEY if is_local() else None)
    except keys.KeyringError as exc:
        raise MfaUnavailable(str(exc)) from exc
    if ring is None:
        raise MfaUnavailable("MDARIX_MFA_ENCRYPTION_KEY is not configured")
    return ring


def _context(user_id: str, key_id: str | None = None) -> bytes:
    return (str(user_id) if key_id is None else f"{user_id}:{key_id}").encode("ascii")


def encrypt_secret(secret: str, user_id: str) -> str:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    ring = keyring()
    nonce = os.urandom(12)
    if ring.current_id is None:
        sealed = AESGCM(ring.current).encrypt(nonce, secret.encode("ascii"), _context(user_id))
        return base64.urlsafe_b64encode(_LEGACY_PREFIX + nonce + sealed).decode("ascii")
    sealed = AESGCM(ring.current).encrypt(nonce, secret.encode("ascii"), _context(user_id, ring.current_id))
    header = keys.labelled_header(_PREFIX, ring.current_id)
    return base64.urlsafe_b64encode(header + nonce + sealed).decode("ascii")


def sealed_key_id(token: str) -> str | None:
    """The key ID a secret was sealed with (None for one sealed without a key ID)."""
    blob = base64.urlsafe_b64decode(token.encode("ascii"))
    if blob.startswith(_PREFIX):
        return keys.split_labelled(blob, _PREFIX)[0]
    if blob.startswith(_LEGACY_PREFIX):
        return None
    raise ValueError("MFA_SECRET_FORMAT")


def decrypt_secret(token: str, user_id: str, ring: keys.Keyring | None = None) -> str:
    """The secret, opened with the key it names (labelled) or with the current and then each older key (unlabelled).
    ``ring`` limits the keys tried (scripts/reseal_mfa_secrets.py checks a re-sealed secret with the current key only).
    """
    from cryptography.exceptions import InvalidTag
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    blob = base64.urlsafe_b64decode(token.encode("ascii"))
    ring = ring or keyring()
    if blob.startswith(_PREFIX):
        key_id, rest = keys.split_labelled(blob, _PREFIX)
        key = ring.key_for(key_id)
        if key is None:
            raise ValueError(f"MFA_KEY_ID_UNKNOWN:{key_id}")
        try:
            return AESGCM(key).decrypt(rest[:12], rest[12:], _context(user_id, key_id)).decode("ascii")
        except InvalidTag as exc:
            raise ValueError("MFA_SECRET_UNREADABLE") from exc
    if not blob.startswith(_LEGACY_PREFIX):
        raise ValueError("MFA_SECRET_FORMAT")
    nonce, sealed = blob[len(_LEGACY_PREFIX) : len(_LEGACY_PREFIX) + 12], blob[len(_LEGACY_PREFIX) + 12 :]
    for key in ring.unlabelled_candidates():
        try:
            return AESGCM(key).decrypt(nonce, sealed, _context(user_id)).decode("ascii")
        except InvalidTag:
            continue
    raise ValueError("MFA_SECRET_UNREADABLE")
