"""Sign-in, sign-up requests, multi-factor authentication and password management.

Every session and one-time link is stored in Postgres (auth/durable.py); nothing about who is signed in lives in
process memory. Public endpoints are rate limited per client address and per account (backend/app/rate_limit.py);
repeated wrong passwords from one address lock that address out of the account for 15 minutes.

Every authentication event is audited (sign-in and its failures, lockouts, sign-out, each MFA step, password
resets and activations) with ``make_audit_event``: the record holds account ids, outcomes and the client address,
never an email address, password, code or link. A failed sign-in is audited in its own short transaction, so the
record survives the rollback of the attempt; everything else is written in the transaction of the change itself.
"""

import hashlib
import logging
import os
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import case, func
from sqlalchemy.orm import Session

from auth.cookies import (
    PENDING_MFA_SECONDS,
    SESSION_SECONDS,
    SESSION_WINDOW_SECONDS,
    clear_session_cookie,
    read_session_token,
    set_session_cookie,
)
from auth.durable import (
    consume,
    hash_token,
    issue_reset,
    peek,
    new_session,
    revoke_session,
    revoke_user_sessions,
)
from auth.emailer import send_password_reset_email
from auth.security_notices import queue_security_notice
from auth.service import (
    PASSWORD_MESSAGES,
    _hash,
    _verify,
    burn_verification_time,
    needs_rehash,
    password_problem,
)
from backend.app.client_ip import client_ip
from backend.app.db.models.foundation import AuthUser, Tenant, TenantMembership
from backend.app.db.models.stage2 import (
    AuthSession,
    LoginThrottle,
    OnboardingRequest,
    PasswordHistory,
)
from backend.app.db.session import get_db
from backend.app.db.tenant_scope import bind_system, bind_tenant
from backend.app.enterprise_audit import make_audit_event
from backend.app.rate_limit import enforce
from backend.app.request_context import ensure_tenant_access, renew_session_if_due, session_expiry
from backend.app.runtime_env import is_development

router = APIRouter(prefix="/api/v1/auth", tags=["Authentication"])
logger = logging.getLogger(__name__)

LOCK_AFTER_FAILURES = 5
LOCK_MINUTES = 15
# Failed sign-ins for an email nobody has are recorded under the MDARIX operator organization, when it exists
# (scripts/create_platform_admin.py creates it), so guessing against unknown names is visible to the platform team.
PLATFORM_TENANT_KEY = "MDARIX_PLATFORM"
ANONYMOUS_ACTOR = "ANONYMOUS"


class Signup(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    # Not stored: the password is created from the invitation after approval. Accepted for older clients.
    password: str | None = Field(default=None, max_length=128)
    display_name: str = Field(min_length=1, max_length=120)
    organization: str = Field(min_length=1, max_length=160)


class Signin(BaseModel):
    email: str = Field(max_length=254)
    password: str = Field(max_length=128)
    # Which organization to sign in to, when the email and password match accounts in several.
    tenant_id: uuid.UUID | None = None


class ResetRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)


class Reset(BaseModel):
    token: str = Field(max_length=200)
    password: str = Field(max_length=128)


class PasswordChange(BaseModel):
    current_password: str = Field(max_length=128)
    new_password: str = Field(max_length=128)


class MfaCode(BaseModel):
    code: str = Field(min_length=6, max_length=6)


class MfaVerify(BaseModel):
    # A 6-digit authenticator code, or a one-time recovery code (xxxxxxxx-xxxxxxxx).
    code: str = Field(min_length=6, max_length=32)


class Reauthentication(BaseModel):
    """Proof that the person at the keyboard is the account's owner, for changes to how they sign in: the current
    password or a fresh authenticator code. A stolen, still-open session gives neither."""

    password: str | None = Field(default=None, max_length=128)
    mfa_code: str | None = Field(default=None, min_length=6, max_length=6)


def fail(exc):
    return HTTPException(400, detail={"code": str(exc), "message": "Request could not be completed"})


def _development_token(token: str | None) -> str | None:
    return token if is_development() else None


def _check_new_password(password: str, email: str | None) -> None:
    problem = password_problem(password, email=email)
    if problem:
        raise HTTPException(422, detail={"code": problem, "message": PASSWORD_MESSAGES[problem]})


def _password_reuse(db, row, new_password: str) -> bool:
    """Return true when the proposed password matches the current or last five passwords."""
    if row.password_hash and _verify(new_password, row.password_hash):
        return True
    history = (
        db.query(PasswordHistory)
        .filter_by(tenant_id=row.tenant_id, user_id=row.id)
        .order_by(PasswordHistory.created_at.desc())
        .limit(5)
        .all()
    )
    return any(_verify(new_password, item.password_hash) for item in history)


def _record_password_change(db, row, password_hash: str, now: datetime) -> None:
    db.add(
        PasswordHistory(
            id=uuid.uuid4(),
            tenant_id=row.tenant_id,
            user_id=row.id,
            password_hash=password_hash,
            created_at=now,
        )
    )
    row.password_changed_at = now
    # No periodic expiry (NIST SP 800-63B): passwords change when there is a reason to, not on a timer.
    row.password_expires_at = None


def _set_password(db, row, password: str, now: datetime) -> None:
    if _password_reuse(db, row, password):
        raise HTTPException(
            422,
            detail={"code": "PASSWORD_REUSE_NOT_ALLOWED", "message": PASSWORD_MESSAGES["PASSWORD_REUSE_NOT_ALLOWED"]},
        )
    row.password_hash = _hash(password)
    row.updated_at = now
    _record_password_change(db, row, row.password_hash, now)


def _mfa_hash(code: str) -> str:
    return hashlib.sha256(code.encode("ascii")).hexdigest()


# ------------------------------------------------------------------------------------------- audit trail


def _audit(
    db: Session,
    *,
    tenant_id,
    action: str,
    actor_ref: str,
    entity_id=None,
    details: dict | None = None,
    request: Request | None = None,
    now: datetime | None = None,
) -> None:
    """Add one authentication audit event to the current transaction (the caller commits).

    ``details`` carry ids and outcomes only; ``make_audit_event`` redacts secret-named keys as a second line.
    """
    db.add(
        make_audit_event(
            tenant_id=tenant_id,
            actor_ref=actor_ref,
            action=action,
            entity_type="AuthUser",
            entity_id=entity_id,
            details=details,
            request=request,
            created_at=now,
        )
    )


def _audit_user(db: Session, user, action: str, request: Request, details: dict | None = None, now=None) -> None:
    _audit(
        db,
        tenant_id=user.tenant_id,
        action=action,
        actor_ref=str(user.id),
        entity_id=user.id,
        details=details,
        request=request,
        now=now,
    )


def _platform_tenant_id(db: Session):
    row = db.query(Tenant.id).filter(Tenant.tenant_key == PLATFORM_TENANT_KEY).first()
    return row[0] if row else None


# ------------------------------------------------------------------------------------------- MFA


def _mfa_session(request: Request, db: Session):
    """The signed-in session and its user, for the MFA steps (which a session that still owes MFA may use)."""
    token = read_session_token(request)
    row = (
        db.query(AuthSession)
        .filter(
            AuthSession.session_hash == hash_token(token),
            AuthSession.revoked_at.is_(None),
            AuthSession.expires_at > datetime.now(timezone.utc),
        )
        .first()
        if token
        else None
    )
    if not row:
        raise HTTPException(401, detail={"code": "UNAUTHENTICATED", "message": "Authentication required"})
    bind_tenant(db, row.tenant_id)
    user = (
        db.query(AuthUser)
        .filter(AuthUser.id == row.user_id, AuthUser.tenant_id == row.tenant_id, AuthUser.status == "ACTIVE")
        .first()
    )
    if not user:
        raise HTTPException(401, detail={"code": "UNAUTHENTICATED", "message": "Authentication required"})
    return row, user


def _limit_mfa(request: Request, user) -> None:
    enforce("mfa:ip", client_ip(request))
    enforce("mfa:user", str(user.id))


def _mfa_complete(session_row, response: Response | None, token: str | None) -> None:
    """The second factor is done: the session gets a full window, counted from now and capped at the absolute limit
    from sign-in, and the browser's cookie is extended to match."""
    now = datetime.now(timezone.utc)
    session_row.mfa_state = None
    session_row.expires_at = min(
        now + timedelta(seconds=SESSION_WINDOW_SECONDS),
        session_row.created_at + timedelta(seconds=SESSION_SECONDS),
    )
    if response is not None and token:
        set_session_cookie(response, token, max_age=int((session_row.expires_at - now).total_seconds()))


def _record_mfa_failure(db: Session, user, request: Request, step: str) -> None:
    """A wrong code or password at an MFA step: counted towards the lockout, audited, committed."""
    from backend.app import mfa

    locked = mfa.record_failure(db, user)
    _audit_user(db, user, "MFA_FAILED", request, {"step": step})
    if locked:
        _audit_user(db, user, "ACCOUNT_LOCKED", request, {"scope": "MFA", "minutes": mfa.LOCK_MINUTES})
    db.commit()


def _reauthenticate(db: Session, request: Request, user, proof: Reauthentication | None) -> None:
    """Changing how an account signs in needs the current password or a fresh authenticator code, even from a fully
    verified session: a session left open on a shared screen must not be enough to replace the authenticator."""
    from backend.app import mfa

    if proof is None or not (proof.password or proof.mfa_code):
        raise HTTPException(
            403,
            detail={
                "code": "REAUTHENTICATION_REQUIRED",
                "message": "Confirm with your current password or an authenticator code",
            },
        )
    _limit_mfa(request, user)
    mfa.ensure_not_locked(db, user)
    if proof.mfa_code:
        ok = mfa.check_code(user, proof.mfa_code, allow_recovery=False)
    else:
        try:
            ok = bool(user.password_hash) and _verify(proof.password, user.password_hash)
        except ValueError:
            ok = False
    if not ok:
        _record_mfa_failure(db, user, request, "REAUTHENTICATION")
        raise HTTPException(403, detail={"code": "REAUTHENTICATION_FAILED", "message": "The password or code is wrong"})
    mfa.record_success(db, user)


@router.post("/mfa/enroll")
def mfa_enroll(request: Request, proof: Reauthentication | None = None, db: Session = Depends(get_db)):
    """Start setting up an authenticator app: returns the secret (and its otpauth link for a QR code).

    Replacing an existing authenticator needs a fully verified session and, in the body, the current password or
    a fresh code from the current app (``{"password": ...}`` or ``{"mfa_code": ...}``), so neither a stolen
    password nor a stolen session alone can do it.
    """
    from backend.app import mfa

    session_row, user = _mfa_session(request, db)
    if mfa.is_enrolled(user):
        if session_row.mfa_state:
            raise HTTPException(403, detail={"code": "MFA_REQUIRED", "message": "Verify your current code first"})
        _reauthenticate(db, request, user, proof)
    started = mfa.start_enrollment(user)
    db.commit()
    return started


@router.post("/mfa/verify-enrollment")
def mfa_verify_enrollment(data: MfaCode, request: Request, response: Response, db: Session = Depends(get_db)):
    """Confirm the new authenticator with its first code; returns one-time recovery codes (shown once)."""
    from backend.app import mfa

    session_row, user = _mfa_session(request, db)
    _limit_mfa(request, user)
    mfa.ensure_not_locked(db, user)
    now = datetime.now(timezone.utc)
    if not user.mfa_pending_secret_encrypted:
        raise HTTPException(
            400, detail={"code": "MFA_CHALLENGE_INVALID", "message": "Start MFA setup before verifying a code"}
        )
    replaced = mfa.is_enrolled(user)
    codes = mfa.finish_enrollment(user, data.code, now)
    if codes is None:
        _record_mfa_failure(db, user, request, "ENROLLMENT")
        raise HTTPException(403, detail={"code": "MFA_CODE_INVALID", "message": "MFA code is invalid"})
    mfa.record_success(db, user)
    _mfa_complete(session_row, response, read_session_token(request))
    _audit_user(db, user, "MFA_ENROLLED", request, {"replaced": replaced, "recovery_codes": len(codes)}, now)
    queue_security_notice(db, user, "MFA_REPLACED" if replaced else "MFA_ENROLLED", now)
    db.commit()
    return {"status": "MFA_ENROLLED", "user_id": str(user.id), "enrolled_at": now, "recovery_codes": codes}


@router.post("/mfa/verify")
def mfa_verify(data: MfaVerify, request: Request, response: Response, db: Session = Depends(get_db)):
    """Complete sign-in with an authenticator code (or a one-time recovery code). Also confirms a new authenticator
    when one is being set up, for clients that use this endpoint for both."""
    from backend.app import mfa

    session_row, user = _mfa_session(request, db)
    if user.mfa_pending_secret_encrypted and (not mfa.is_enrolled(user) or not session_row.mfa_state):
        if len(data.code) != 6:
            raise HTTPException(403, detail={"code": "MFA_CODE_INVALID", "message": "MFA code is invalid"})
        return mfa_verify_enrollment(MfaCode(code=data.code), request, response, db)
    _limit_mfa(request, user)
    mfa.ensure_not_locked(db, user)
    if not mfa.is_enrolled(user):
        raise HTTPException(400, detail={"code": "MFA_NOT_ENROLLED", "message": "Set up an authenticator app first"})
    recovery = "-" in data.code.strip()
    if not mfa.check_code(user, data.code, allow_recovery=True):
        _record_mfa_failure(db, user, request, "SIGN_IN")
        raise HTTPException(403, detail={"code": "MFA_CODE_INVALID", "message": "MFA code is invalid"})
    mfa.record_success(db, user)
    _mfa_complete(session_row, response, read_session_token(request))
    left = len(user.mfa_recovery_hashes or [])
    _audit_user(db, user, "MFA_VERIFIED", request, {"method": "RECOVERY_CODE" if recovery else "AUTHENTICATOR"})
    if recovery:
        _audit_user(db, user, "MFA_RECOVERY_CODE_USED", request, {"recovery_codes_left": left})
    db.commit()
    return {"status": "MFA_VERIFIED", "recovery_codes_left": left}


@router.post("/mfa/recovery-codes")
def mfa_recovery_codes(request: Request, proof: Reauthentication | None = None, db: Session = Depends(get_db)):
    """Replace the recovery codes (fully verified session, plus the current password or a fresh authenticator code
    in the body); the old ones stop working."""
    from backend.app import mfa
    from security.mfa_recovery import hash_recovery_codes, issue_recovery_codes

    session_row, user = _mfa_session(request, db)
    if session_row.mfa_state or not mfa.is_enrolled(user):
        raise HTTPException(403, detail={"code": "MFA_REQUIRED", "message": "Verify your code first"})
    _reauthenticate(db, request, user, proof)
    now = datetime.now(timezone.utc)
    codes = issue_recovery_codes(8)
    user.mfa_recovery_hashes = hash_recovery_codes(codes)
    _audit_user(db, user, "MFA_RECOVERY_CODES_REGENERATED", request, {"recovery_codes": len(codes)}, now)
    queue_security_notice(db, user, "MFA_RECOVERY_CODES_REGENERATED", now)
    db.commit()
    return {"status": "RECOVERY_CODES_ISSUED", "recovery_codes": codes}


@router.post("/mfa/challenge")
def mfa_challenge(request: Request, db: Session = Depends(get_db)):
    """Signatures take the current code from the authenticator app; nothing is sent. Kept for clients that ask
    first: it confirms the account is enrolled (and, in local development, shows the current code)."""
    from auth import totp
    from backend.app import mfa

    _session_row, user = _mfa_session(request, db)
    if not mfa.is_enrolled(user):
        raise HTTPException(
            403, detail={"code": "MFA_NOT_ENROLLED", "message": "Enroll MFA before requesting a signature challenge"}
        )
    development_code = None
    if is_development():
        try:
            development_code = totp.current_code(totp.decrypt_secret(user.mfa_secret_encrypted, str(user.id)))
        except totp.MfaUnavailable:
            development_code = None
    return {"status": "USE_AUTHENTICATOR_CODE", "development_code": development_code}


# ------------------------------------------------------------------------------------------- sign-up


def _alert_trial_request(organization: str, display_name: str, email: str) -> None:
    """Email the Platform Admin about a new trial request. Runs after the response; failures are only logged."""
    recipient = os.getenv("MDARIX_TRIAL_ALERT_EMAIL", "").strip()
    if not recipient:
        return
    from auth.emailer import send_trial_request_alert

    try:
        send_trial_request_alert(recipient, organization=organization, display_name=display_name, email=email)
    except Exception as exc:  # the request is already saved; an alert failure must never surface to the visitor
        logger.warning("Trial request alert failed: %s", type(exc).__name__)


SIGNUP_ACCEPTED = {
    "status": "ONBOARDING_REQUEST_ACCEPTED",
    "tenant_created": False,
    "next_step": "We review every request, usually within one business day, and email an invitation once approved.",
}


@router.post("/signup")
def signup(data: Signup, request: Request, background: BackgroundTasks, db: Session = Depends(get_db)):
    """Record a free-trial request. The answer is the same whether or not the email already has an account or a
    pending request, so this endpoint cannot be used to find out who uses MDARIX."""
    email = data.email.strip().lower()
    enforce("signup:ip", client_ip(request))
    enforce("signup:email", email)
    if "@" not in email or email.startswith("@") or email.endswith("@") or " " in email:
        raise HTTPException(422, detail={"code": "VALID_EMAIL_REQUIRED", "message": "Enter a valid work email"})
    try:
        bind_system(db, "trial sign-up: is this email already known")
        known = (
            db.query(AuthUser.id).filter(AuthUser.username == email).first() is not None
            or db.query(OnboardingRequest.id).filter(OnboardingRequest.email == email).first() is not None
        )
        if known:
            return dict(SIGNUP_ACCEPTED)
        now = datetime.now(timezone.utc)
        row = OnboardingRequest(
            id=uuid.uuid4(),
            email=email,
            display_name=" ".join(data.display_name.split()),
            organization=" ".join(data.organization.split()),
            status="PENDING_REVIEW",
            created_at=now,
            updated_at=now,
        )
        db.add(row)
        db.commit()
        background.add_task(_alert_trial_request, row.organization, row.display_name, email)
        return dict(SIGNUP_ACCEPTED)
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.exception("Trial request could not be recorded")
        raise HTTPException(
            400,
            detail={"code": "ONBOARDING_REQUEST_FAILED", "message": "The request could not be recorded."},
        ) from e


# ------------------------------------------------------------------------------------------- sign-in


def _account_for_email(db: Session, email: str, password: str | None = None):
    """The account an email signs in as.

    The same email can exist in several tenants (for example an active account plus an unused invitation, or
    older accounts created before one email meant one account). Prefer an ACTIVE, verified account, then the one
    whose password was set most recently (the invitation the person just accepted), then the newest. When the
    password is known, the account it belongs to wins: a person never lands in another tenant's account, with
    another role, just because that account is newer.
    """
    rows = (
        db.query(AuthUser)
        .filter(AuthUser.username == email)
        .order_by(
            case((func.upper(AuthUser.status) == "ACTIVE", 0), else_=1),
            case((AuthUser.email_verified.is_(True), 0), else_=1),
            AuthUser.password_changed_at.desc().nulls_last(),
            AuthUser.created_at.desc(),
        )
        .all()
    )
    if password is not None and len(rows) > 1:
        for row in rows:
            try:
                if row.password_hash and _verify(password, row.password_hash):
                    return row
            except ValueError:
                continue
    return rows[0] if rows else None


def _accounts_for_password(db: Session, email: str, password: str) -> list:
    """Every active, verified account with this email whose password matches (one per organization).

    An email with no account still spends the time of one password check, so timing does not reveal accounts.
    """
    rows = (
        db.query(AuthUser)
        .filter(AuthUser.username == email, func.upper(AuthUser.status) == "ACTIVE", AuthUser.email_verified.is_(True))
        .all()
    )
    if not rows:
        burn_verification_time(password)
        return []
    matches = []
    for row in rows:
        try:
            if row.password_hash and _verify(password, row.password_hash):
                matches.append(row)
        except ValueError:
            continue
    return matches


def _organizations(db: Session, accounts: list) -> list[dict]:
    """The organizations a person may choose between: names only, and only those that are open to them."""
    choices = []
    for account in accounts:
        try:
            ensure_tenant_access(db, account)
        except HTTPException:
            continue
        tenant = db.query(Tenant).filter(Tenant.id == account.tenant_id).first()
        if tenant is not None:
            choices.append({"tenant_id": str(tenant.id), "tenant_name": tenant.display_name or tenant.name})
    return sorted(choices, key=lambda item: item["tenant_name"].lower())


def _throttle_key(email: str, address: str | None) -> str:
    """Lockout is per account *and* client address: wrong passwords from one address cannot lock the owner out
    everywhere (the per-account rate limit still caps guessing from many addresses)."""
    return "sha256:" + hashlib.sha256(f"{email}|{address or '-'}".encode()).hexdigest()


def _throttle(db: Session, key: str):
    query = db.query(LoginThrottle).filter(LoginThrottle.identifier == key)
    return query.with_for_update().first() if hasattr(query, "with_for_update") else query.first()


def _record_failed_signin(
    db: Session, key: str, now: datetime, *, request: Request | None = None, email: str | None = None, reason: str
) -> None:
    """Count a failed sign-in and audit it, in one short transaction of its own (the attempt itself rolled back).

    The audit event is written under the account the email belongs to when there is one (its id, never the email),
    else under the operator organization; the caller's answer is the same either way.
    """
    throttle = _throttle(db, key)
    if throttle is None:
        throttle = LoginThrottle(identifier=key, failure_count=0, updated_at=now)
        db.add(throttle)
    throttle.failure_count = (throttle.failure_count or 0) + 1
    throttle.last_failure_at = now
    throttle.updated_at = now
    locked = throttle.failure_count >= LOCK_AFTER_FAILURES
    if locked:
        throttle.locked_until = now + timedelta(minutes=LOCK_MINUTES)
        # The next lock needs another full run of failures, not a single one.
        throttle.failure_count = 0
    if request is not None and email is not None:
        bind_system(db, "sign-in failure: audit under the account's organization")
        account = _account_for_email(db, email)
        tenant_id = account.tenant_id if account is not None else _platform_tenant_id(db)
        if tenant_id is not None:
            actor = str(account.id) if account is not None else ANONYMOUS_ACTOR
            entity_id = account.id if account is not None else None
            details = {"reason": reason, "account_known": account is not None}
            _audit(
                db,
                tenant_id=tenant_id,
                action="SIGN_IN_FAILED",
                actor_ref=actor,
                entity_id=entity_id,
                details=details,
                request=request,
                now=now,
            )
            if locked:
                _audit(
                    db,
                    tenant_id=tenant_id,
                    action="ACCOUNT_LOCKED",
                    actor_ref=actor,
                    entity_id=entity_id,
                    details={"scope": "SIGN_IN_ADDRESS", "minutes": LOCK_MINUTES, "account_known": account is not None},
                    request=request,
                    now=now,
                )
    db.commit()


def _forget_old_throttles(db: Session, now: datetime) -> None:
    db.query(LoginThrottle).filter(LoginThrottle.updated_at < now - timedelta(days=1)).filter(
        (LoginThrottle.locked_until.is_(None)) | (LoginThrottle.locked_until < now)
    ).delete(synchronize_session=False)


def _clear_throttle(db: Session, email: str, address: str | None) -> None:
    db.query(LoginThrottle).filter(LoginThrottle.identifier == _throttle_key(email, address)).delete(
        synchronize_session=False
    )


def _signin_response(row) -> dict:
    return {
        "user_id": str(row.id),
        "display_name": row.display_name,
        "email": row.username,
        "tenant_id": str(row.tenant_id),
        "active_role": row.role,
    }


@router.post("/signin")
def signin(data: Signin, request: Request, response: Response, db: Session = Depends(get_db)):
    identifier = data.email.strip().lower()
    address = client_ip(request)
    enforce("signin:ip", address)
    now = datetime.now(timezone.utc)
    key = _throttle_key(identifier, address)
    throttle = _throttle(db, key)
    if throttle is not None and throttle.locked_until and throttle.locked_until > now:
        raise HTTPException(
            429,
            detail={
                "code": "ACCOUNT_TEMPORARILY_LOCKED",
                "message": "Too many failed sign-in attempts. Try again later.",
            },
        )
    bind_system(db, "sign-in: find this person's accounts across organizations")
    matches = _accounts_for_password(db, identifier, data.password)
    row = None
    if data.tenant_id is not None:
        row = next((item for item in matches if item.tenant_id == data.tenant_id), None)
    elif len(matches) > 1:
        choices = _organizations(db, matches)
        if len(choices) > 1:
            # The password is right for several organizations: the person chooses; no session exists yet.
            db.rollback()
            return {"status": "TENANT_SELECTION_REQUIRED", "organizations": choices}
        row = next((item for item in matches if choices and str(item.tenant_id) == choices[0]["tenant_id"]), matches[0])
    elif matches:
        row = matches[0]
    if row is None:
        db.rollback()
        _record_failed_signin(db, key, now, request=request, email=identifier, reason="INVALID_CREDENTIALS")
        # Only failures count against the account (a correct password is never refused by this limit), so nobody
        # can lock a person out of their account by sending their email with wrong passwords from many addresses.
        enforce("signin:account", identifier)
        raise HTTPException(401, detail={"code": "INVALID_CREDENTIALS", "message": "Invalid credentials."})
    bind_tenant(db, row.tenant_id)
    # Checked only after the password is verified, so it cannot be used to probe accounts.
    try:
        ensure_tenant_access(db, row)
    except HTTPException as refused:
        db.rollback()
        code = refused.detail.get("code") if isinstance(refused.detail, dict) else str(refused.status_code)
        _audit_user(db, row, "SIGN_IN_FAILED", request, {"reason": code, "account_known": True}, now)
        db.commit()
        raise
    if needs_rehash(row.password_hash):
        row.password_hash = _hash(data.password)
        row.updated_at = now
    if throttle is not None:
        db.delete(throttle)
    _forget_old_throttles(db, now)
    db.commit()
    from backend.app import mfa

    # The new session owes MFA when the account is enrolled (VERIFY) or policy requires setting it up (ENROLL);
    # until then it can only use the MFA steps, and only for a few minutes.
    mfa_state = mfa.session_state_for(row)
    ttl = PENDING_MFA_SECONDS if mfa_state else SESSION_WINDOW_SECONDS
    # Audited in the transaction that creates the session (new_session commits both).
    _audit_user(db, row, "SIGN_IN_SUCCEEDED", request, {"mfa": mfa_state or "NONE"}, now)
    token = new_session(db, row.id, row.tenant_id, mfa_state=mfa_state, ttl=ttl)
    set_session_cookie(response, token, max_age=ttl)
    return {
        **_signin_response(row),
        "mfa_required": mfa_state == "VERIFY",
        "mfa_enrollment_required": mfa_state == "ENROLL",
    }


@router.post("/signout")
def signout(request: Request, response: Response, db: Session = Depends(get_db)):
    token = read_session_token(request)
    if token:
        row = (
            db.query(AuthSession)
            .filter(AuthSession.session_hash == hash_token(token), AuthSession.revoked_at.is_(None))
            .first()
        )
        if row is not None:
            bind_tenant(db, row.tenant_id)
            _audit(
                db,
                tenant_id=row.tenant_id,
                action="SIGN_OUT",
                actor_ref=str(row.user_id),
                entity_id=row.user_id,
                details={"mfa_pending": bool(row.mfa_state)},
                request=request,
            )
        revoke_session(db, token)  # commits the revocation together with the audit event
    clear_session_cookie(response)
    return {"status": "SIGNED_OUT"}


@router.get("/session")
def session(request: Request, response: Response, db: Session = Depends(get_db)):
    token = read_session_token(request)
    row = (
        db.query(AuthSession)
        .filter(
            AuthSession.session_hash == hash_token(token),
            AuthSession.revoked_at.is_(None),
            AuthSession.expires_at > datetime.now(timezone.utc),
        )
        .first()
        if token
        else None
    )
    if row is not None:
        bind_tenant(db, row.tenant_id)
    user = (
        db.query(AuthUser)
        .filter(AuthUser.id == row.user_id, AuthUser.tenant_id == row.tenant_id, AuthUser.status == "ACTIVE")
        .first()
        if row
        else None
    )
    if not user:
        raise HTTPException(401, detail={"code": "UNAUTHENTICATED", "message": "Authentication required"})
    ensure_tenant_access(db, user)
    from backend.app import mfa
    from backend.app.request_context import _idle_limit

    now = datetime.now(timezone.utc)
    if row.last_seen_at and now - row.last_seen_at > _idle_limit():
        row.revoked_at = now
        db.commit()
        raise HTTPException(401, detail={"code": "SESSION_IDLE_TIMEOUT", "message": "Signed out after inactivity"})
    row.last_seen_at = now
    renew_session_if_due(row, now, response, token)
    db.commit()
    return {
        "user_id": str(user.id),
        "display_name": user.display_name,
        "email": user.username,
        "tenant_id": str(user.tenant_id),
        "active_role": user.role,
        # VERIFY: a code is still due; ENROLL: MFA must be set up first; None: fully signed in.
        "mfa_state": row.mfa_state,
        "mfa_enrolled": mfa.is_enrolled(user),
        "other_organizations": _other_organization_count(db, user),
        # When this session ends if nothing happens: the browser warns shortly before idle_expires_at.
        **session_expiry(row, now),
    }


def _other_organization_count(db: Session, user) -> int:
    """How many other organizations this email has an active account in (for "Switch organization")."""
    bind_system(db, "session: count this person's other organizations")
    count = (
        db.query(AuthUser.id)
        .filter(
            AuthUser.username == user.username,
            AuthUser.tenant_id != user.tenant_id,
            func.upper(AuthUser.status) == "ACTIVE",
        )
        .count()
    )
    bind_tenant(db, user.tenant_id)
    return count


# ------------------------------------------------------------------------------------------- passwords


@router.post("/change-password")
def change_password(data: PasswordChange, request: Request, db: Session = Depends(get_db)):
    """Change the signed-in person's password. Their other sessions are signed out; this one stays."""
    from backend.app.request_context import get_request_context

    ctx = get_request_context(request, db)
    enforce("password-change:user", ctx.user_id)
    row = db.query(AuthUser).filter(AuthUser.id == uuid.UUID(ctx.user_id), AuthUser.tenant_id == ctx.tenant_id).first()
    if row is None:
        raise HTTPException(401, detail={"code": "UNAUTHENTICATED", "message": "Authentication required"})
    try:
        current_ok = bool(row.password_hash) and _verify(data.current_password, row.password_hash)
    except ValueError:
        current_ok = False
    if not current_ok:
        raise HTTPException(
            403, detail={"code": "INVALID_CURRENT_PASSWORD", "message": "Your current password is wrong"}
        )
    _check_new_password(data.new_password, row.username)
    now = datetime.now(timezone.utc)
    _set_password(db, row, data.new_password, now)
    revoked = revoke_user_sessions(db, row.id, row.tenant_id, keep_raw=ctx.session_id)
    _audit_user(db, row, "PASSWORD_CHANGED", request, {"other_sessions_signed_out": revoked}, now)
    queue_security_notice(db, row, "PASSWORD_CHANGED", now)
    db.commit()
    return {"status": "PASSWORD_CHANGED", "other_sessions_signed_out": revoked}


# Account states an administrator imposed. A password reset or activation link must never lift them.
ADMIN_BLOCKED_STATUSES = frozenset({"SUSPENDED", "OFFBOARDED", "LOCKED", "DISABLED"})


def _admin_blocked(row) -> bool:
    return str(getattr(row, "status", "") or "").upper() in ADMIN_BLOCKED_STATUSES


def _activate_invited_memberships(db: Session, row) -> None:
    """Promote only INVITED memberships; a suspended membership stays suspended."""
    db.query(TenantMembership).filter(
        TenantMembership.tenant_id == row.tenant_id,
        TenantMembership.user_id == row.id,
        TenantMembership.status == "INVITED",
    ).update({"status": "ACTIVE", "updated_at": datetime.now(timezone.utc)})


def _organization_name(db: Session, tenant_id) -> str | None:
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    return (tenant.display_name or tenant.name) if tenant else None


def _send_reset_quietly(email: str, token: str, organization: str | None = None) -> None:
    """Runs after the response: a delivery problem is logged, never shown to whoever asked."""
    try:
        send_password_reset_email(email, token, organization=organization)
    except Exception as exc:  # the answer is already the same for every request
        logger.warning("Password reset email failed: %s", type(exc).__name__)


@router.post("/forgot-password")
def forgot(data: ResetRequest, request: Request, background: BackgroundTasks, db: Session = Depends(get_db)):
    """The same answer, in the same time, for every email: known, unknown or blocked. The email itself is sent
    after the response, so neither the body nor its timing reveals whether an account exists. Each new link
    replaces the earlier unused one."""
    accepted = {"status": "RESET_REQUEST_ACCEPTED", "email_delivery": "ACCEPTED"}
    email = data.email.strip().lower()
    enforce("forgot:ip", client_ip(request))
    enforce("forgot:email", email)
    bind_system(db, "password reset: find this email's accounts across organizations")
    accounts = [row for row in db.query(AuthUser).filter(AuthUser.username == email) if not _admin_blocked(row)]
    if not accounts:
        return accepted
    from auth.emailer import smtp_configuration_status

    # One link per organization (each account has its own password); each email names its organization.
    tokens = []
    now = datetime.now(timezone.utc)
    for row in accounts:
        # Audited with the link's creation (issue_reset commits both); the record names the account, not the email.
        _audit_user(db, row, "PASSWORD_RESET_REQUESTED", request, {"source": "SELF_SERVICE"}, now)
        token = issue_reset(db, row.id, row.tenant_id)
        tokens.append(token)
        background.add_task(_send_reset_quietly, row.username, token, _organization_name(db, row.tenant_id))
    if is_development() and not smtp_configuration_status().get("configured"):
        background.tasks.clear()  # local development without email: the link is shown instead
        return {**accepted, "development_token": _development_token(tokens[0])}
    return accepted


def _redeem(db: Session, request: Request, data: Reset, kind: str) -> AuthUser:
    """Use a one-time link to set a password.

    The password is checked before the link is spent, so a refused password leaves the link usable. Then, in one
    transaction: the password is stored, the link spent, every existing session of the account signed out, the
    address's sign-in lockout for the account lifted, and the event audited. Two simultaneous uses of one link:
    only one succeeds.
    """
    enforce("token:ip", client_ip(request))
    invalid = "INVALID_RESET" if kind == "reset" else "INVALID_ACTIVATION"
    bind_system(db, f"redeem single-use {kind} token")
    try:
        user_id = peek(db, data.token, kind)
    except ValueError:
        raise fail(invalid)
    row = db.query(AuthUser).filter(AuthUser.id == user_id).first()
    if row is None or _admin_blocked(row):
        raise fail(invalid)
    _check_new_password(data.password, row.username)
    now = datetime.now(timezone.utc)
    _set_password(db, row, data.password, now)
    was_active = str(row.status or "").upper() == "ACTIVE"
    row.status = "ACTIVE"
    row.email_verified = True
    _activate_invited_memberships(db, row)
    revoked = revoke_user_sessions(db, row.id, row.tenant_id)
    _clear_throttle(db, row.username, client_ip(request))
    if kind == "reset":
        _audit_user(db, row, "PASSWORD_RESET_COMPLETED", request, {"sessions_signed_out": revoked}, now)
        queue_security_notice(db, row, "PASSWORD_RESET", now)
    else:
        _audit_user(db, row, "ACCOUNT_ACTIVATED", request, {"was_active": was_active}, now)
    try:
        consume(db, data.token, kind)  # commits the whole change, or refuses a link spent meanwhile
    except ValueError:
        db.rollback()
        raise fail(invalid)
    return row


@router.post("/reset-password")
def reset(data: Reset, request: Request, db: Session = Depends(get_db)):
    _redeem(db, request, data, "reset")
    return {"status": "PASSWORD_RESET"}


def _send_welcome_quietly(email: str, organization: str) -> None:
    try:
        from auth.emailer import send_welcome_email

        send_welcome_email(email, organization)
    except Exception as exc:  # the account is active either way
        logger.warning("Welcome email failed: %s", type(exc).__name__)


@router.post("/activate-account")
def activate(data: Reset, request: Request, background: BackgroundTasks, db: Session = Depends(get_db)):
    row = _redeem(db, request, data, "activation")
    background.add_task(
        _send_welcome_quietly, row.username, _organization_name(db, row.tenant_id) or "your organization"
    )
    return {"status": "ACTIVE", "user_id": str(row.id), "email": row.username}
