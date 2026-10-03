"""A connector's API key for the customer's system, encrypted at rest (AES-GCM), with a key ID so keys can rotate.

The current key is MDARIX_CONNECTOR_ENCRYPTION_KEY (URL-safe base64 of 16, 24 or 32 bytes), identified by
MDARIX_CONNECTOR_ENCRYPTION_KEY_ID (default "k1"). Every sealed value records the key ID it was sealed with and is
bound to its tenant and connector, so a value copied to another connector cannot be opened. To rotate: set the new
key and a new key ID, keep the old one readable in MDARIX_CONNECTOR_ENCRYPTION_KEYS ("k1:<base64>,k0:<base64>"),
run ``python scripts/reseal_connector_keys.py --apply`` to re-seal every stored key with the new one, then remove
the old key. Values sealed before key IDs existed ("MDARIXCON1") are opened with any configured key.

Local development and tests use a fixed key so they work without configuration; any other environment without the
key cannot store one (fail closed). The key is never returned by the API: only its last four characters are kept.
"""

from __future__ import annotations

import base64
import hashlib
import os
import re

from backend.app.runtime_env import is_local

_LEGACY_PREFIX = b"MDARIXCON1"
_PREFIX = b"MDARIXCON2"
API_KEY_PATTERN = re.compile(r"^[\x21-\x7e]{8,512}$")
KEY_ID_PATTERN = re.compile(r"^[A-Za-z0-9_.-]{1,32}$")
LOCAL_KEY_ID = "local"


class ConnectorSecretsUnavailable(RuntimeError):
    """Connector keys cannot be protected in this environment (no encryption key configured)."""


def _decode(raw: str, name: str) -> bytes:
    try:
        key = base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4))
    except (ValueError, TypeError) as exc:
        raise ConnectorSecretsUnavailable(f"{name} is not valid base64") from exc
    if len(key) not in {16, 24, 32}:
        raise ConnectorSecretsUnavailable(f"{name} must decode to 16, 24 or 32 bytes")
    return key


def current_key() -> tuple[str, bytes]:
    """(key ID, key) used to seal new values."""
    raw = os.getenv("MDARIX_CONNECTOR_ENCRYPTION_KEY", "").strip()
    if not raw:
        if is_local():
            return LOCAL_KEY_ID, hashlib.sha256(b"mdarix-local-development-connector-key").digest()
        raise ConnectorSecretsUnavailable("MDARIX_CONNECTOR_ENCRYPTION_KEY is not configured")
    key_id = os.getenv("MDARIX_CONNECTOR_ENCRYPTION_KEY_ID", "k1").strip() or "k1"
    if not KEY_ID_PATTERN.match(key_id):
        raise ConnectorSecretsUnavailable("MDARIX_CONNECTOR_ENCRYPTION_KEY_ID may use letters, digits, '_', '.', '-'")
    return key_id, _decode(raw, "MDARIX_CONNECTOR_ENCRYPTION_KEY")


def keyring() -> dict[str, bytes]:
    """Every key that may open a stored value: the current one and the older ones still listed."""
    key_id, key = current_key()
    keys = {key_id: key}
    for item in os.getenv("MDARIX_CONNECTOR_ENCRYPTION_KEYS", "").split(","):
        if not item.strip():
            continue
        old_id, _, raw = item.strip().partition(":")
        if not KEY_ID_PATTERN.match(old_id) or not raw:
            raise ConnectorSecretsUnavailable("MDARIX_CONNECTOR_ENCRYPTION_KEYS entries must be <key id>:<base64 key>")
        keys.setdefault(old_id, _decode(raw, f"MDARIX_CONNECTOR_ENCRYPTION_KEYS[{old_id}]"))
    return keys


def _context(tenant_id, connector_id, key_id: str | None = None) -> bytes:
    base = f"{tenant_id}:{connector_id}"
    return (base if key_id is None else f"{base}:{key_id}").encode("ascii")


def seal(api_key: str, tenant_id, connector_id) -> str:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    if not API_KEY_PATTERN.match(api_key):
        raise ValueError("CONNECTOR_API_KEY_INVALID")
    key_id, key = current_key()
    nonce = os.urandom(12)
    sealed = AESGCM(key).encrypt(nonce, api_key.encode("ascii"), _context(tenant_id, connector_id, key_id))
    header = _PREFIX + bytes([len(key_id)]) + key_id.encode("ascii")
    return base64.urlsafe_b64encode(header + nonce + sealed).decode("ascii")


def sealed_key_id(token: str) -> str | None:
    """The key ID a value was sealed with (None for values sealed before key IDs)."""
    blob = base64.urlsafe_b64decode(token.encode("ascii"))
    if blob.startswith(_PREFIX):
        length = blob[len(_PREFIX)]
        return blob[len(_PREFIX) + 1 : len(_PREFIX) + 1 + length].decode("ascii")
    return None


def open_sealed(token: str, tenant_id, connector_id) -> str:
    from cryptography.exceptions import InvalidTag
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    blob = base64.urlsafe_b64decode(token.encode("ascii"))
    keys = keyring()
    if blob.startswith(_PREFIX):
        length = blob[len(_PREFIX)]
        start = len(_PREFIX) + 1
        key_id = blob[start : start + length].decode("ascii")
        nonce, sealed = blob[start + length : start + length + 12], blob[start + length + 12 :]
        if key_id not in keys:
            raise ValueError(f"CONNECTOR_KEY_ID_UNKNOWN:{key_id}")
        return AESGCM(keys[key_id]).decrypt(nonce, sealed, _context(tenant_id, connector_id, key_id)).decode("ascii")
    if blob.startswith(_LEGACY_PREFIX):
        nonce, sealed = blob[len(_LEGACY_PREFIX) : len(_LEGACY_PREFIX) + 12], blob[len(_LEGACY_PREFIX) + 12 :]
        candidates = list(keys.values())
        if is_local():
            candidates.append(hashlib.sha256(b"mdarix-local-development-connector-key").digest())
        for key in candidates:
            try:
                return AESGCM(key).decrypt(nonce, sealed, _context(tenant_id, connector_id)).decode("ascii")
            except InvalidTag:
                continue
        raise ValueError("CONNECTOR_API_KEY_UNREADABLE")
    raise ValueError("CONNECTOR_API_KEY_FORMAT")
