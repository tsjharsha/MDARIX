"""Password hashing and the rules a new password must meet.

Hashes are scrypt with a random 16-byte salt. New hashes record their cost:

    scrypt$<log2 N>$<r>$<p>$<salt hex>$<digest hex>

Hashes written before that format (``<salt hex>:<digest hex>``, N=2^14, r=8, p=1) still verify; ``needs_rehash``
reports them (and any hash below the current cost) so sign-in can upgrade them while the password is at hand.

The cost defaults to N=2^17, r=8, p=1 (OWASP Password Storage guidance; 128 MiB per hash).
``MDARIX_PASSWORD_SCRYPT_LOG2_N`` may lower it for automated tests only; production refuses a value below 17
(``backend/app/config_check.py``). At most ``MDARIX_PASSWORD_HASH_CONCURRENCY`` hashes (default 3) run at once in a
process; the rest wait, so a burst of sign-ins cannot exhaust memory.

Passwords follow NIST SP 800-63B: 12 to 128 characters, no composition rules, no periodic expiry, and refused when
they appear in a list of breached passwords or contain the person's email name.
"""

from __future__ import annotations

import gzip
import hashlib
import hmac
import logging
import os
import secrets
import threading
from functools import lru_cache
from pathlib import Path

MIN_LENGTH = 12
MAX_LENGTH = 128
DEFAULT_LOG2_N = 17
_R = 8
_P = 1
_LEGACY_LOG2_N = 14
_PREFIX = "scrypt$"
_BREACHED = Path(__file__).resolve().parent / "data" / "breached_passwords.txt.gz"

logger = logging.getLogger(__name__)


def _log2_n() -> int:
    try:
        value = int(os.getenv("MDARIX_PASSWORD_SCRYPT_LOG2_N", str(DEFAULT_LOG2_N)))
    except ValueError:
        return DEFAULT_LOG2_N
    return min(max(value, 10), 20)


def _hash_concurrency() -> int:
    """How many password hashes may run at once in this process (MDARIX_PASSWORD_HASH_CONCURRENCY, default 3).

    Each scrypt at the production cost holds about 128 MiB while it runs, so a burst of sign-in attempts (an attack
    or just Monday morning) must queue rather than exhaust the server's memory. Three keeps a small VM safe; a
    larger host may raise it. Waiting attempts hold no memory.
    """
    try:
        value = int(os.getenv("MDARIX_PASSWORD_HASH_CONCURRENCY", "3"))
    except ValueError:
        value = 3
    return max(1, min(value, 64))


# Process-wide: every hash and verification in this process, whatever thread serves the request, takes a slot.
_HASH_SLOTS = threading.BoundedSemaphore(_hash_concurrency())


def _scrypt(password: str, salt: bytes, log2_n: int, r: int, p: int) -> bytes:
    n = 2**log2_n
    with _HASH_SLOTS:
        # scrypt needs 128 * r * N bytes (plus a little); give it head room above hashlib's 32 MiB default.
        return hashlib.scrypt(password.encode("utf-8"), salt=salt, n=n, r=r, p=p, maxmem=256 * r * n + 1024 * 1024)


def _hash(password: str, salt: bytes | None = None) -> str:
    """A new scrypt hash of ``password`` at the current cost."""
    salt = salt or secrets.token_bytes(16)
    log2_n = _log2_n()
    digest = _scrypt(password, salt, log2_n, _R, _P)
    return f"{_PREFIX}{log2_n}${_R}${_P}${salt.hex()}${digest.hex()}"


def _parse(stored: str) -> tuple[int, int, int, bytes, bytes]:
    if stored.startswith(_PREFIX):
        log2_n, r, p, salt, digest = stored[len(_PREFIX) :].split("$")
        return int(log2_n), int(r), int(p), bytes.fromhex(salt), bytes.fromhex(digest)
    salt, digest = stored.split(":", 1)
    return _LEGACY_LOG2_N, 8, 1, bytes.fromhex(salt), bytes.fromhex(digest)


def _verify(password: str, stored: str) -> bool:
    """True when ``password`` matches ``stored``; raises ValueError for a value that is not a password hash."""
    log2_n, r, p, salt, digest = _parse(stored)
    return hmac.compare_digest(_scrypt(password, salt, log2_n, r, p), digest)


def needs_rehash(stored: str) -> bool:
    """True when ``stored`` uses an older format or a lower cost than new hashes get."""
    try:
        log2_n, r, p, _salt, _digest = _parse(stored)
    except ValueError:
        return False
    return not stored.startswith(_PREFIX) or log2_n < _log2_n() or r < _R or p < _P


@lru_cache(maxsize=4)
def _dummy_hash(cost_key: int) -> str:
    """A hash of a random password at the current cost; ``cost_key`` keys the cache so a cost change refreshes it."""
    del cost_key
    return _hash(secrets.token_urlsafe(24))


def burn_verification_time(password: str) -> None:
    """Spend the time of one password check, so an unknown email answers as slowly as a wrong password."""
    try:
        _verify(password, _dummy_hash(_log2_n()))
    except ValueError:
        pass


@lru_cache(maxsize=1)
def _breached_passwords() -> frozenset[str]:
    try:
        with gzip.open(_BREACHED, "rt", encoding="utf-8") as handle:
            return frozenset(line.strip() for line in handle if line.strip())
    except OSError:
        logger.error("Breached-password list %s could not be read; only the length rules apply", _BREACHED)
        return frozenset()


def password_problem(password: str, *, email: str | None = None) -> str | None:
    """The code of the first rule ``password`` breaks, or None. Codes are shown to the person as messages."""
    if len(password) < MIN_LENGTH:
        return "PASSWORD_TOO_SHORT"
    if len(password) > MAX_LENGTH:
        return "PASSWORD_TOO_LONG"
    lowered = password.strip().lower()
    if len(set(lowered)) < 4:
        return "PASSWORD_TOO_SIMPLE"
    if lowered in _breached_passwords():
        return "PASSWORD_BREACHED"
    local = (email or "").split("@", 1)[0].strip().lower()
    if len(local) >= 4 and local in lowered:
        return "PASSWORD_CONTAINS_EMAIL"
    return None


PASSWORD_MESSAGES = {
    "PASSWORD_TOO_SHORT": f"Use at least {MIN_LENGTH} characters.",
    "PASSWORD_TOO_LONG": f"Use at most {MAX_LENGTH} characters.",
    "PASSWORD_TOO_SIMPLE": "Use a password with more variety; a phrase of several words works well.",
    "PASSWORD_BREACHED": "This password has appeared in a data breach. Choose a different one.",
    "PASSWORD_CONTAINS_EMAIL": "Do not include your email name in your password.",
    "PASSWORD_REUSE_NOT_ALLOWED": "Choose a password you have not used recently.",
}
