"""A connector's API key for the customer's system, encrypted at rest (AES-GCM).

The key is sealed with MDARIX_CONNECTOR_ENCRYPTION_KEY (URL-safe base64 of 16, 24 or 32 bytes) and bound to its
tenant and connector, so a sealed value copied to another connector cannot be opened. Local development and tests
use a fixed key so they work without configuration; any other environment without the key cannot store one (fail
closed). The key is never returned by the API: only its last four characters are kept as a hint.
"""

from __future__ import annotations

import base64
import hashlib
import os
import re

from backend.app.runtime_env import is_local

_PREFIX = b"MDARIXCON1"
API_KEY_PATTERN = re.compile(r"^[\x21-\x7e]{8,512}$")


class ConnectorSecretsUnavailable(RuntimeError):
    """Connector keys cannot be protected in this environment (no encryption key configured)."""


def _key() -> bytes:
    raw = os.getenv("MDARIX_CONNECTOR_ENCRYPTION_KEY", "").strip()
    if not raw:
        if is_local():
            return hashlib.sha256(b"mdarix-local-development-connector-key").digest()
        raise ConnectorSecretsUnavailable("MDARIX_CONNECTOR_ENCRYPTION_KEY is not configured")
    key = base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4))
    if len(key) not in {16, 24, 32}:
        raise ConnectorSecretsUnavailable("MDARIX_CONNECTOR_ENCRYPTION_KEY must decode to 16, 24 or 32 bytes")
    return key


def _context(tenant_id, connector_id) -> bytes:
    return f"{tenant_id}:{connector_id}".encode("ascii")


def seal(api_key: str, tenant_id, connector_id) -> str:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    if not API_KEY_PATTERN.match(api_key):
        raise ValueError("CONNECTOR_API_KEY_INVALID")
    nonce = os.urandom(12)
    sealed = AESGCM(_key()).encrypt(nonce, api_key.encode("ascii"), _context(tenant_id, connector_id))
    return base64.urlsafe_b64encode(_PREFIX + nonce + sealed).decode("ascii")


def open_sealed(token: str, tenant_id, connector_id) -> str:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    blob = base64.urlsafe_b64decode(token.encode("ascii"))
    if not blob.startswith(_PREFIX):
        raise ValueError("CONNECTOR_API_KEY_FORMAT")
    nonce, sealed = blob[len(_PREFIX) : len(_PREFIX) + 12], blob[len(_PREFIX) + 12 :]
    return AESGCM(_key()).decrypt(nonce, sealed, _context(tenant_id, connector_id)).decode("ascii")
