"""Multi-factor authentication policy and checks (authenticator app, auth/totp.py).

- Who must use MFA at sign-in: everyone who has enrolled; and, by policy, people in the roles that can change the
  record of an investigation or sign for it must set it up before they can do anything else
  (MDARIX_REQUIRE_MFA_ROLES; default platform and customer administrators, Leaders and Approvers outside local
  development; backend/app/config_check.py refuses a weaker production setting).
- Governed decision signatures need a fresh authenticator code (MDARIX_REQUIRE_MFA_FOR_SIGNATURES, default on).
- Wrong codes are limited: 5 failures lock MFA checks for the account for 15 minutes.
"""

from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException

from auth import totp
from backend.app.db.models.stage2 import LoginThrottle
from backend.app.runtime_env import is_development, is_local
from security.mfa_recovery import consume_recovery_code, hash_recovery_codes, issue_recovery_codes
from backend.app.role_codes import PLATFORM_ADMIN, role_code

MAX_FAILURES = 5
LOCK_MINUTES = 15
def _normalize(role) -> str:
    return role_code(role)


DEFAULT_REQUIRED_ROLES = f"{PLATFORM_ADMIN},CUSTOMER_ADMIN,LEADER,APPROVER"


def required_roles() -> set[str]:
    configured = os.getenv("MDARIX_REQUIRE_MFA_ROLES")
    if configured is None:
        configured = "" if is_local() else DEFAULT_REQUIRED_ROLES
    return {_normalize(role) for role in configured.split(",") if role.strip()}


def signatures_require_mfa() -> bool:
    return os.getenv("MDARIX_REQUIRE_MFA_FOR_SIGNATURES", "true").strip().lower() in {"1", "true", "yes"}


def is_enrolled(user) -> bool:
    return bool(getattr(user, "mfa_enrolled_at", None) and getattr(user, "mfa_secret_encrypted", None))


def session_state_for(user) -> str | None:
    """The MFA step a new session still owes: VERIFY (enrolled), ENROLL (policy requires it), or None."""
    if is_enrolled(user):
        return "VERIFY"
    if _normalize(user.role) in required_roles():
        return "ENROLL"
    return None


def _throttle(db, user, scope: str) -> LoginThrottle:
    key = f"{scope}:{user.id}"
    row = db.query(LoginThrottle).filter(LoginThrottle.identifier == key).with_for_update().first()
    if row is None:
        row = LoginThrottle(identifier=key, failure_count=0, updated_at=datetime.now(timezone.utc))
        db.add(row)
    return row


def ensure_not_locked(db, user, scope: str = "mfa") -> None:
    """scope: "mfa" for sign-in codes, "sign" for signatures (wrong passwords and codes count together)."""
    row = db.query(LoginThrottle).filter(LoginThrottle.identifier == f"{scope}:{user.id}").first()
    if row is not None and row.locked_until and row.locked_until > datetime.now(timezone.utc):
        code = "SIGNATURE_TEMPORARILY_LOCKED" if scope == "sign" else "MFA_TEMPORARILY_LOCKED"
        raise HTTPException(429, detail={"code": code, "message": "Too many failed attempts. Try again in 15 minutes."})


def record_failure(db, user, scope: str = "mfa") -> bool:
    """Count one wrong code (or password, for signatures). True when this failure locked the account's checks."""
    now = datetime.now(timezone.utc)
    row = _throttle(db, user, scope)
    row.failure_count += 1
    row.last_failure_at = now
    row.updated_at = now
    if row.failure_count >= MAX_FAILURES:
        row.locked_until = now + timedelta(minutes=LOCK_MINUTES)
        row.failure_count = 0
        return True
    return False


def record_success(db, user, scope: str = "mfa") -> None:
    row = db.query(LoginThrottle).filter(LoginThrottle.identifier == f"{scope}:{user.id}").first()
    if row is not None:
        row.failure_count = 0
        row.locked_until = None


def unavailable() -> HTTPException:
    return HTTPException(
        503,
        detail={
            "code": "MFA_UNAVAILABLE",
            "message": "Multi-factor authentication is not configured on this server (MDARIX_MFA_ENCRYPTION_KEY).",
        },
    )


def start_enrollment(user) -> dict:
    """A new secret for the user's authenticator app; it becomes active only after a code from it is verified."""
    secret = totp.new_secret()
    try:
        user.mfa_pending_secret_encrypted = totp.encrypt_secret(secret, str(user.id))
    except totp.MfaUnavailable as exc:
        raise unavailable() from exc
    return {
        "status": "MFA_ENROLLMENT_PENDING",
        "secret": secret,
        "otpauth_uri": totp.provisioning_uri(secret, user.username),
        # Local development only: the current code, so the flow can be exercised without a phone.
        "development_code": totp.current_code(secret) if is_development() else None,
    }


def finish_enrollment(user, code: str, now: datetime) -> list[str] | None:
    """Activate the pending secret when the code matches; returns one-time recovery codes, or None."""
    if not user.mfa_pending_secret_encrypted:
        return None
    try:
        secret = totp.decrypt_secret(user.mfa_pending_secret_encrypted, str(user.id))
    except totp.MfaUnavailable as exc:
        raise unavailable() from exc
    step = totp.matching_step(secret, code)
    if step is None:
        return None
    codes = issue_recovery_codes(8)
    user.mfa_secret_encrypted = user.mfa_pending_secret_encrypted
    user.mfa_pending_secret_encrypted = None
    user.mfa_last_step = step
    user.mfa_recovery_hashes = hash_recovery_codes(codes)
    user.mfa_required = True
    user.mfa_enrolled_at = now
    return codes


def check_code(user, code: str, *, allow_recovery: bool) -> bool:
    """A fresh authenticator code (each code works once), or, where allowed, an unused recovery code."""
    if not is_enrolled(user):
        return False
    candidate = str(code or "").strip()
    if allow_recovery and "-" in candidate:
        used, remaining = consume_recovery_code(candidate.lower(), list(user.mfa_recovery_hashes or []))
        if used:
            user.mfa_recovery_hashes = remaining
        return used
    try:
        secret = totp.decrypt_secret(user.mfa_secret_encrypted, str(user.id))
    except totp.MfaUnavailable as exc:
        raise unavailable() from exc
    step = totp.matching_step(secret, candidate, user.mfa_last_step)
    if step is None:
        return False
    user.mfa_last_step = step
    return True


def reset(db, user, now: datetime) -> int:
    """Remove the user's authenticator and recovery codes (an administrator's recovery for a lost device).

    The person sets up a new authenticator at their next sign-in (administrators must; others may). Every session
    of theirs ends, and their MFA lockout is lifted. Returns how many sessions were ended. The caller audits and
    commits.
    """
    from auth.durable import revoke_user_sessions

    user.mfa_secret_encrypted = None
    user.mfa_pending_secret_encrypted = None
    user.mfa_recovery_hashes = None
    user.mfa_last_step = None
    user.mfa_enrolled_at = None
    user.updated_at = now
    db.query(LoginThrottle).filter(LoginThrottle.identifier.in_([f"mfa:{user.id}", f"sign:{user.id}"])).delete(
        synchronize_session=False
    )
    return revoke_user_sessions(db, user.id, user.tenant_id)
