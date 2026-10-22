"""Keyrings for the keys that encrypt stored data: the current key, its ID, and older keys still readable.

A key setting such as MDARIX_MFA_ENCRYPTION_KEY (URL-safe base64 of 16, 24 or 32 bytes) has two companions, named as
the connector key's are (access_control/connector_secrets.py):

- ``<setting>_ID`` (MDARIX_MFA_ENCRYPTION_KEY_ID): the ID of the current key, such as ``k2``. Unset, the key has no ID
  and everything is sealed in the unlabelled format it was always sealed in, so a server that sets neither companion
  behaves exactly as before.
- ``<setting>S`` (MDARIX_MFA_ENCRYPTION_KEYS): older keys that can still be read during a rotation,
  ``<key id>:<base64>`` separated by commas.

Values sealed in the unlabelled format are opened with the current key and then with each older key, so the key in use
before the first rotation is simply listed under an ID of its own (``k1:<old key>``). Values sealed in a labelled format
name their key ID and are opened with that key only. Used by auth/totp.py (MDARIX_MFA_ENCRYPTION_KEY) and
object_storage/service.py (MDARIX_OBJECT_STORAGE_ENCRYPTION_KEY); backend/app/config_check.py checks the settings.
"""

from __future__ import annotations

import base64
import os
import re
from collections.abc import Mapping
from dataclasses import dataclass, field

KEY_ID_PATTERN = re.compile(r"^[A-Za-z0-9_.-]{1,32}$")
KEY_SIZES = {16, 24, 32}


class KeyringError(ValueError):
    """A key setting is missing or malformed. The message names the setting, never a key."""


@dataclass(frozen=True)
class Keyring:
    setting: str
    current: bytes
    # None: the current key has no ID (<setting>_ID unset), and new values use the unlabelled format.
    current_id: str | None = None
    older: dict[str, bytes] = field(default_factory=dict)

    def key_for(self, key_id: str) -> bytes | None:
        """The key a labelled value names, or None when this server does not hold it."""
        if key_id == self.current_id:
            return self.current
        return self.older.get(key_id)

    def unlabelled_candidates(self) -> list[bytes]:
        """The keys to try on a value sealed without a key ID: the current one first, then the older ones."""
        keys = [self.current]
        for key in self.older.values():
            if key not in keys:
                keys.append(key)
        return keys


def decode_key(raw: str, name: str) -> bytes:
    try:
        key = base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4))
    except (ValueError, TypeError) as exc:
        raise KeyringError(f"{name} is not valid base64") from exc
    if len(key) not in KEY_SIZES:
        raise KeyringError(f"{name} must decode to 16, 24 or 32 bytes")
    return key


def _read(environ: Mapping[str, str | None] | None, name: str) -> str:
    value = (os.environ if environ is None else environ).get(name)
    return str(value or "").strip()


def settings(setting: str) -> dict[str, str | None]:
    """The key setting and its two companions as they are now, for a keyring loaded later (``environ``)."""
    return {name: os.environ.get(name) for name in (setting, f"{setting}_ID", f"{setting}S")}


def current_id(setting: str, environ: Mapping[str, str | None] | None = None) -> str | None:
    """<setting>_ID, or None when it is unset (the key has no ID)."""
    key_id = _read(environ, f"{setting}_ID")
    if not key_id:
        return None
    if not KEY_ID_PATTERN.match(key_id):
        raise KeyringError(f"{setting}_ID may use letters, digits, '_', '.', '-' (at most 32)")
    return key_id


def older_keys(setting: str, environ: Mapping[str, str | None] | None = None) -> dict[str, bytes]:
    """<setting>S as {key id: key}. A malformed entry or an ID listed twice is refused, not skipped."""
    keys: dict[str, bytes] = {}
    for item in _read(environ, f"{setting}S").split(","):
        if not item.strip():
            continue
        key_id, _, raw = item.strip().partition(":")
        key_id, raw = key_id.strip(), raw.strip()
        if not KEY_ID_PATTERN.match(key_id) or not raw:
            raise KeyringError(f"{setting}S entries must be <key id>:<base64 key>")
        if key_id in keys:
            raise KeyringError(f"{setting}S lists the key ID {key_id} twice")
        keys[key_id] = decode_key(raw, f"{setting}S[{key_id}]")
    return keys


def load(
    setting: str, *, local_key: bytes | None = None, environ: Mapping[str, str | None] | None = None
) -> Keyring | None:
    """The keyring of a key setting, from the process environment or from ``environ`` (settings() taken earlier).
    Without the key: a keyring of ``local_key`` (local development and tests), or None. The current key ID may not also
    be listed among the older keys."""
    raw = _read(environ, setting)
    if not raw:
        return Keyring(setting, local_key) if local_key is not None else None
    key_id = current_id(setting, environ)
    older = older_keys(setting, environ)
    if key_id is not None and key_id in older:
        raise KeyringError(f"{setting}S must not list the current key ID {key_id}")
    return Keyring(setting, decode_key(raw, setting), key_id, older)


def labelled_header(prefix: bytes, key_id: str) -> bytes:
    """The start of a labelled value: its format prefix, the key ID's length (one byte) and the key ID."""
    encoded = key_id.encode("ascii")
    return prefix + bytes([len(encoded)]) + encoded


def split_labelled(blob: bytes, prefix: bytes) -> tuple[str, bytes]:
    """(key ID, the rest) of a value that starts with ``prefix`` and a key ID written by labelled_header."""
    start = len(prefix) + 1
    if len(blob) < start:
        raise ValueError("KEY_ID_MISSING")
    end = start + blob[len(prefix)]
    key_id = blob[start:end].decode("ascii", errors="replace")
    if len(blob) < end or not KEY_ID_PATTERN.match(key_id):
        raise ValueError("KEY_ID_MALFORMED")
    return key_id, blob[end:]


def problems(setting: str) -> list[str]:
    """What is wrong with the key setting's ID and older keys (for backend/app/config_check.py). The key itself is
    checked there as before."""
    found: list[str] = []
    try:
        key_id = current_id(setting)
    except KeyringError as exc:
        found.append(str(exc))
        key_id = None
    try:
        older = older_keys(setting)
    except KeyringError as exc:
        found.append(str(exc))
        older = {}
    if key_id is not None and key_id in older:
        found.append(f"{setting}S must not list the current key ID {key_id} (set it as {setting}_ID only)")
    current = os.getenv(setting, "").strip()
    if current and older:
        try:
            if decode_key(current, setting) in older.values():
                found.append(f"{setting}S lists the current key under another ID")
        except KeyringError:
            pass  # the key's own problem is reported with it
    return found


def warnings(setting: str) -> list[str]:
    """What an operator should know but that does not stop the server: older keys still loaded."""
    try:
        older = older_keys(setting)
    except KeyringError:
        return []
    if not older:
        return []
    ids = ", ".join(sorted(older))
    return [
        f"{setting}S still holds older keys ({ids}): once everything is re-encrypted with the current key and no "
        "backup made with them is still kept, remove them (docs/runbooks/KEY_ROTATION.md)"
    ]
