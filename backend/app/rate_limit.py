"""Fixed-window rate limits shared by every API process (counters live in Postgres).

``enforce(scope, key, limit, window_seconds)`` counts one attempt for ``key`` (an IP address, an email, a user id)
in the current window and answers 429 with ``Retry-After`` once the count passes ``limit``. Keys are stored only as
salted SHA-256 hashes. Each count is committed on its own short connection, so a request that fails afterwards
still counts.

``MDARIX_RATE_LIMITS_ENABLED=false`` turns the limits off for automated test runs; staging and production refuse to
start with it (``backend/app/config_check.py``).

When the counter table cannot be reached, authentication scopes (``AUTH_SCOPES``) refuse with 503 in staging and
production and raise an alert; everything else fails open. ``signin:account`` counts failed attempts only
(backend/app/auth_router.py), so nobody can lock a known person out by sending their email with wrong passwords.
"""

from __future__ import annotations

import hashlib
import logging
import os
import random
import time
from dataclasses import dataclass

from fastapi import HTTPException
from sqlalchemy import text

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Limit:
    limit: int
    window_seconds: int


# Attempts allowed per window. Account-level lockout (login_throttles) and MFA lockout still apply on top.
LIMITS: dict[str, Limit] = {
    "signin:ip": Limit(30, 300),
    "signin:account": Limit(10, 900),
    "signup:ip": Limit(5, 3600),
    "signup:email": Limit(3, 86400),
    "forgot:ip": Limit(10, 3600),
    "forgot:email": Limit(3, 3600),
    "token:ip": Limit(20, 3600),
    "mfa:ip": Limit(30, 300),
    "mfa:user": Limit(10, 300),
    # Replacing the authenticator or the recovery codes, per account (on top of the two MFA limits above).
    "mfa:change": Limit(10, 3600),
    "password-change:user": Limit(10, 3600),
    "demo:ip": Limit(5, 3600),
    "feedback:user": Limit(10, 86400),
    # Browser error reports are unauthenticated: a page in an error loop must not fill the table.
    "client-errors:ip": Limit(30, 300),
}


# Scopes that protect authentication. When the counter store is down, these refuse (503) in staging and production
# rather than let an attacker who can break the counters guess passwords unthrottled; other scopes (feedback, demo
# requests) fail open, because losing them costs nothing. A scope added without being listed here fails open.
AUTH_SCOPES = frozenset(
    {
        "signin:ip",
        "signin:account",
        "signup:ip",
        "signup:email",
        "forgot:ip",
        "forgot:email",
        "token:ip",
        "mfa:ip",
        "mfa:user",
        "mfa:change",
        "password-change:user",
    }
)


def enabled() -> bool:
    return os.getenv("MDARIX_RATE_LIMITS_ENABLED", "true").strip().lower() not in {"0", "false", "no"}


def fails_closed(scope: str) -> bool:
    from backend.app.runtime_env import is_production_like

    return scope in AUTH_SCOPES and is_production_like()


def _unavailable() -> HTTPException:
    return HTTPException(
        503,
        detail={
            "code": "RATE_LIMITER_UNAVAILABLE",
            "message": "Sign-in is temporarily unavailable. Please try again in a few minutes.",
        },
        headers={"Retry-After": "60"},
    )


def _key_hash(scope: str, key: str) -> str:
    salt = os.getenv("MDARIX_RATE_LIMIT_SALT") or os.getenv("MDARIX_DEMO_REQUEST_SALT") or "mdarix-rate-limits"
    return hashlib.sha256(f"{salt}:{scope}:{key.strip().lower()}".encode()).hexdigest()


def _too_many(retry_after: int) -> HTTPException:
    return HTTPException(
        429,
        detail={"code": "RATE_LIMITED", "message": "Too many attempts. Please wait a few minutes and try again."},
        headers={"Retry-After": str(max(1, retry_after))},
    )


def enforce(scope: str, key: str | None) -> None:
    """Count one attempt for ``key`` under ``scope`` (a name in LIMITS); raise 429 when over the limit."""
    if not key or not enabled():
        return
    rule = LIMITS[scope]
    from backend.app.db.session import runtime_engine

    now = int(time.time())
    window_start = now - now % rule.window_seconds
    try:
        with runtime_engine.begin() as connection:
            count = connection.execute(
                text(
                    "INSERT INTO rate_limit_counters (scope, key_hash, window_start, count) "
                    "VALUES (:scope, :key, to_timestamp(:start), 1) "
                    "ON CONFLICT (scope, key_hash, window_start) "
                    "DO UPDATE SET count = rate_limit_counters.count + 1 RETURNING count"
                ),
                {"scope": scope, "key": _key_hash(scope, key), "start": window_start},
            ).scalar_one()
            if random.random() < 0.01:
                connection.execute(
                    text("DELETE FROM rate_limit_counters WHERE window_start < now() - interval '2 days'")
                )
    except Exception:
        if fails_closed(scope):
            # Authentication without its limits is worse than no authentication for a few minutes: refuse, and
            # tell the operators (the ALERT prefix is what the log collector pages on; backend/app/alerts.py).
            logger.critical("ALERT Rate limit counter unavailable for authentication scope %s: refusing", scope)
            raise _unavailable()
        # Elsewhere a broken counter must never lock everyone out; the account lockout still applies.
        logger.exception("Rate limit counter unavailable for scope %s", scope)
        return
    if count > rule.limit:
        raise _too_many(window_start + rule.window_seconds - now)
