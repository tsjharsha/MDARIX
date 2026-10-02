import hashlib
import logging
import os
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy import case, func
from sqlalchemy.orm import Session

from auth.durable import (
    consume,
    hash_token,
    issue_reset,
    persist_session,
    revoke_session,
)
from auth.emailer import send_password_reset_email
from auth.service import _hash, _verify, auth_service
from backend.app.db.models.foundation import AuthUser, TenantMembership
from backend.app.db.models.stage2 import (
    AuthSession,
    LoginThrottle,
    OnboardingRequest,
    PasswordHistory,
)
from backend.app.db.session import get_db
from backend.app.request_context import ensure_tenant_access
from backend.app.runtime_env import is_development
from backend.app.db.tenant_scope import bind_system, bind_tenant

router = APIRouter(prefix="/api/v1/auth", tags=["Authentication"])


class Signup(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    # Not stored: the password is created from the invitation after approval. Accepted for older clients.
    password: str | None = Field(default=None, max_length=128)
    display_name: str = Field(min_length=1, max_length=120)
    organization: str = Field(min_length=1, max_length=160)


class Signin(BaseModel):
    email: str
    password: str
    # Which organization to sign in to, when the email and password match accounts in several.
    tenant_id: uuid.UUID | None = None


class Verify(BaseModel):
    token: str


class ResetRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)


class Reset(BaseModel):
    token: str
    password: str = Field(min_length=12, max_length=128)


class MfaCode(BaseModel):
    code: str = Field(min_length=6, max_length=6)


class MfaVerify(BaseModel):
    # A 6-digit authenticator code, or a one-time recovery code (xxxxxxxx-xxxxxxxx).
    code: str = Field(min_length=6, max_length=32)


def fail(exc):
    return HTTPException(400, detail={"code": str(exc), "message": "Request could not be completed"})


def _development_token(token: str | None) -> str | None:
    return token if is_development() else None


def _legacy_compat_enabled() -> bool:
    """Allow in-process compatibility only for explicitly enabled local tests."""
    return is_development() and os.getenv("MDARIX_ALLOW_LEGACY_AUTH_FALLBACK", "").lower() == "true"


def _password_reuse(db, row, new_password: str) -> bool:
    """Return true when the proposed password matches the current or last five passwords."""
    from auth.service import _verify

    if _verify(new_password, row.password_hash):
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
            id=__import__("uuid").uuid4(),
            tenant_id=row.tenant_id,
            user_id=row.id,
            password_hash=password_hash,
            created_at=now,
        )
    )
    row.password_changed_at = now
    row.password_expires_at = now + timedelta(days=int(os.getenv("MDARIX_PASSWORD_MAX_AGE_DAYS", "90")))


def _mfa_hash(code: str) -> str:
    return hashlib.sha256(code.encode("ascii")).hexdigest()


def _mfa_session(request: Request, db: Session):
    """The signed-in session and its user, for the MFA steps (which a session that still owes MFA may use)."""
    token = request.cookies.get("mdarix_session", "")
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


@router.post("/mfa/enroll")
def mfa_enroll(request: Request, db: Session = Depends(get_db)):
    """Start setting up an authenticator app: returns the secret (and its otpauth link for a QR code).

    Replacing an existing authenticator needs a fully verified session, so a stolen password alone cannot do it.
    """
    from backend.app import mfa

    session_row, user = _mfa_session(request, db)
    if mfa.is_enrolled(user) and session_row.mfa_state:
        raise HTTPException(403, detail={"code": "MFA_REQUIRED", "message": "Verify your current code first"})
    started = mfa.start_enrollment(user)
    db.commit()
    return started


@router.post("/mfa/verify-enrollment")
def mfa_verify_enrollment(data: MfaCode, request: Request, db: Session = Depends(get_db)):
    """Confirm the new authenticator with its first code; returns one-time recovery codes (shown once)."""
    from backend.app import mfa

    session_row, user = _mfa_session(request, db)
    mfa.ensure_not_locked(db, user)
    now = datetime.now(timezone.utc)
    if not user.mfa_pending_secret_encrypted:
        raise HTTPException(
            400, detail={"code": "MFA_CHALLENGE_INVALID", "message": "Start MFA setup before verifying a code"}
        )
    codes = mfa.finish_enrollment(user, data.code, now)
    if codes is None:
        mfa.record_failure(db, user)
        db.commit()
        raise HTTPException(403, detail={"code": "MFA_CODE_INVALID", "message": "MFA code is invalid"})
    mfa.record_success(db, user)
    session_row.mfa_state = None
    db.commit()
    return {"status": "MFA_ENROLLED", "user_id": str(user.id), "enrolled_at": now, "recovery_codes": codes}


@router.post("/mfa/verify")
def mfa_verify(data: MfaVerify, request: Request, db: Session = Depends(get_db)):
    """Complete sign-in with an authenticator code (or a one-time recovery code). Also confirms a new authenticator
    when one is being set up, for clients that use this endpoint for both."""
    from backend.app import mfa

    session_row, user = _mfa_session(request, db)
    if user.mfa_pending_secret_encrypted and (not mfa.is_enrolled(user) or not session_row.mfa_state):
        if len(data.code) != 6:
            raise HTTPException(403, detail={"code": "MFA_CODE_INVALID", "message": "MFA code is invalid"})
        return mfa_verify_enrollment(MfaCode(code=data.code), request, db)
    mfa.ensure_not_locked(db, user)
    if not mfa.is_enrolled(user):
        raise HTTPException(400, detail={"code": "MFA_NOT_ENROLLED", "message": "Set up an authenticator app first"})
    if not mfa.check_code(user, data.code, allow_recovery=True):
        mfa.record_failure(db, user)
        db.commit()
        raise HTTPException(403, detail={"code": "MFA_CODE_INVALID", "message": "MFA code is invalid"})
    mfa.record_success(db, user)
    session_row.mfa_state = None
    db.commit()
    return {"status": "MFA_VERIFIED", "recovery_codes_left": len(user.mfa_recovery_hashes or [])}


@router.post("/mfa/recovery-codes")
def mfa_recovery_codes(request: Request, db: Session = Depends(get_db)):
    """Replace the recovery codes (fully verified session only); the old ones stop working."""
    from backend.app import mfa
    from security.mfa_recovery import hash_recovery_codes, issue_recovery_codes

    session_row, user = _mfa_session(request, db)
    if session_row.mfa_state or not mfa.is_enrolled(user):
        raise HTTPException(403, detail={"code": "MFA_REQUIRED", "message": "Verify your code first"})
    codes = issue_recovery_codes(8)
    user.mfa_recovery_hashes = hash_recovery_codes(codes)
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


def _alert_trial_request(organization: str, display_name: str, email: str) -> None:
    """Email the Platform Admin about a new trial request. Runs after the response; failures are only logged."""
    recipient = os.getenv("MDARIX_TRIAL_ALERT_EMAIL", "").strip()
    if not recipient:
        return
    from auth.emailer import send_trial_request_alert

    try:
        send_trial_request_alert(recipient, organization=organization, display_name=display_name, email=email)
    except Exception as exc:  # the request is already saved; an alert failure must never surface to the visitor
        logging.getLogger(__name__).warning("Trial request alert failed: %s", type(exc).__name__)


@router.post("/signup")
def signup(data: Signup, background: BackgroundTasks, db: Session = Depends(get_db)):
    try:
        email = data.email.strip().lower()
        if db.query(AuthUser).filter(AuthUser.username == email).first():
            raise ValueError("ACCOUNT_EXISTS")
        existing = db.query(OnboardingRequest).filter(OnboardingRequest.email == email).first()
        if existing:
            return {
                "status": "ONBOARDING_REQUEST_ACCEPTED",
                "request_id": str(existing.id),
                "request_status": existing.status,
            }
        now = datetime.now(timezone.utc)
        request = OnboardingRequest(
            id=__import__("uuid").uuid4(),
            email=email,
            display_name=data.display_name.strip(),
            organization=data.organization.strip(),
            status="PENDING_REVIEW",
            created_at=now,
            updated_at=now,
        )
        db.add(request)
        db.commit()
        background.add_task(_alert_trial_request, request.organization, request.display_name, email)
        return {
            "status": "ONBOARDING_REQUEST_ACCEPTED",
            "request_id": str(request.id),
            "request_status": request.status,
            "tenant_created": False,
            "next_step": "A Platform Administrator must provision the tenant and invite the initial Customer Administrator.",
        }
    except ValueError as e:
        raise fail(e)
    except Exception as e:
        db.rollback()
        raise HTTPException(
            400,
            detail={"code": "ONBOARDING_REQUEST_FAILED", "message": "The onboarding request could not be recorded."},
        ) from e


@router.post("/verify-email")
def verify(data: Verify, db: Session = Depends(get_db)):
    try:
        result = auth_service.verify_email(data.token)
        account = next(item for item in auth_service.accounts.values() if item.user_id == result["user_id"])
        row = db.query(AuthUser).filter(AuthUser.username == account.email).first()
        if row:
            row.status = "ACTIVE"
            row.email_verified = True
            row.updated_at = datetime.now(timezone.utc)
            db.commit()
        return result
    except ValueError as e:
        raise fail(e)


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
    """Every active account with this email whose password matches (one per organization)."""
    matches = []
    for row in db.query(AuthUser).filter(AuthUser.username == email, func.upper(AuthUser.status) == "ACTIVE").all():
        try:
            if row.password_hash and _verify(password, row.password_hash):
                matches.append(row)
        except ValueError:
            continue
    return matches


def _organizations(db: Session, accounts: list) -> list[dict]:
    """The organizations a person may choose between: names only, and only those that are open to them."""
    from backend.app.db.models.foundation import Tenant

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


@router.post("/signin")
def signin(data: Signin, response: Response, db: Session = Depends(get_db)):
    try:
        identifier = data.email.strip().lower()
        now = datetime.now(timezone.utc)
        throttle_query = db.query(LoginThrottle).filter(LoginThrottle.identifier == identifier)
        throttle = (
            throttle_query.with_for_update().first()
            if hasattr(throttle_query, "with_for_update")
            else throttle_query.first()
        )
        if throttle is not None and not hasattr(throttle, "failure_count"):
            throttle = None
        if throttle and throttle.locked_until and throttle.locked_until > now:
            raise HTTPException(
                429,
                detail={
                    "code": "ACCOUNT_TEMPORARILY_LOCKED",
                    "message": "Too many failed sign-in attempts. Try again later.",
                },
            )
        bind_system(db, "sign-in: find this person's accounts across organizations")
        matches = _accounts_for_password(db, identifier, data.password)
        chosen_tenant = getattr(data, "tenant_id", None)
        if chosen_tenant is not None:
            row = next((item for item in matches if item.tenant_id == chosen_tenant), None)
        elif len(matches) > 1:
            choices = _organizations(db, matches)
            if len(choices) > 1:
                # The password is right for several organizations: the person chooses; no session exists yet.
                return {"status": "TENANT_SELECTION_REQUIRED", "organizations": choices}
            row = next(
                (item for item in matches if choices and str(item.tenant_id) == choices[0]["tenant_id"]), matches[0]
            )
        else:
            row = matches[0] if matches else _account_for_email(db, identifier, data.password)
        if not row:
            raise ValueError("INVALID_CREDENTIALS")
        bind_tenant(db, row.tenant_id)
        if getattr(row, "password_expires_at", None) and row.password_expires_at <= now:
            raise HTTPException(
                403, detail={"code": "PASSWORD_EXPIRED", "message": "Password change is required before sign-in."}
            )
        token = auth_service.signin_persisted(
            data.email,
            data.password,
            user_id=row.id,
            display_name=row.display_name,
            tenant_id=row.tenant_id,
            password_hash=row.password_hash,
            role=row.role,
            status=row.status,
            email_verified=row.email_verified,
        )
        # Checked only after the password is verified, so it cannot be used to probe accounts.
        ensure_tenant_access(db, row)
        if throttle:
            throttle.failure_count = 0
            throttle.locked_until = None
            throttle.last_failure_at = None
            throttle.updated_at = now
        if hasattr(db, "commit"):
            db.commit()
        from backend.app import mfa

        # The new session owes MFA when the account is enrolled (VERIFY) or policy requires setting it up (ENROLL);
        # until then it can only use the MFA steps.
        mfa_state = mfa.session_state_for(row)
        persist_session(db, token, row.id, row.tenant_id, mfa_state=mfa_state)
        development = is_development()
        secure_cookie = True if not development else os.getenv("MDARIX_COOKIE_SECURE", "false").lower() == "true"
        response.set_cookie("mdarix_session", token, httponly=True, samesite="lax", secure=secure_cookie, max_age=3600)
        return {
            **auth_service.context(token),
            "mfa_required": mfa_state == "VERIFY",
            "mfa_enrollment_required": mfa_state == "ENROLL",
        }
    except ValueError as e:
        identifier = data.email.strip().lower()
        now = datetime.now(timezone.utc)
        throttle_query = db.query(LoginThrottle).filter(LoginThrottle.identifier == identifier)
        throttle = (
            throttle_query.with_for_update().first()
            if hasattr(throttle_query, "with_for_update")
            else throttle_query.first()
        )
        if throttle is not None and not hasattr(throttle, "failure_count"):
            throttle = None
        if throttle is None:
            throttle = LoginThrottle(identifier=identifier, failure_count=0, updated_at=now)
            db.add(throttle)
        throttle.failure_count += 1
        throttle.last_failure_at = now
        throttle.updated_at = now
        if throttle.failure_count >= 5:
            from datetime import timedelta

            throttle.locked_until = now + timedelta(minutes=15)
        db.commit()
        raise HTTPException(401, detail={"code": "INVALID_CREDENTIALS", "message": "Invalid credentials."}) from e


@router.post("/signout")
def signout(request: Request, response: Response, db: Session = Depends(get_db)):
    token = request.cookies.get("mdarix_session")
    if token:
        auth_service.signout(token)
        revoke_session(db, token)
    response.delete_cookie("mdarix_session")
    return {"status": "SIGNED_OUT"}


@router.get("/session")
def session(request: Request, db: Session = Depends(get_db)):
    token = request.cookies.get("mdarix_session", "")
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
    user = (
        db.query(AuthUser)
        .filter(AuthUser.id == row.user_id, AuthUser.tenant_id == row.tenant_id, AuthUser.status == "ACTIVE")
        .first()
        if row
        else None
    )
    if not user:
        raise HTTPException(401, detail={"code": "UNAUTHENTICATED", "message": "Authentication required"})
    bind_tenant(db, user.tenant_id)
    ensure_tenant_access(db, user)
    from backend.app import mfa
    from backend.app.request_context import _idle_limit

    now = datetime.now(timezone.utc)
    if row.last_seen_at and now - row.last_seen_at > _idle_limit():
        row.revoked_at = now
        db.commit()
        raise HTTPException(401, detail={"code": "SESSION_IDLE_TIMEOUT", "message": "Signed out after inactivity"})
    row.last_seen_at = now
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
    from backend.app.db.models.foundation import Tenant

    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    return (tenant.display_name or tenant.name) if tenant else None


def _send_reset_quietly(email: str, token: str, organization: str | None = None) -> None:
    """Runs after the response: a delivery problem is logged, never shown to whoever asked."""
    try:
        send_password_reset_email(email, token, organization=organization)
    except Exception as exc:  # the answer is already the same for every request
        logging.getLogger(__name__).warning("Password reset email failed: %s", type(exc).__name__)


@router.post("/forgot-password")
def forgot(data: ResetRequest, background: BackgroundTasks, db: Session = Depends(get_db)):
    """The same answer, in the same time, for every email: known, unknown or blocked. The email itself is sent
    after the response, so neither the body nor its timing reveals whether an account exists."""
    accepted = {"status": "RESET_REQUEST_ACCEPTED", "email_delivery": "ACCEPTED"}
    email = data.email.strip().lower()
    bind_system(db, "password reset: find this email's accounts across organizations")
    accounts = [row for row in db.query(AuthUser).filter(AuthUser.username == email) if not _admin_blocked(row)]
    if not accounts:
        return accepted
    from auth.emailer import smtp_configuration_status

    # One link per organization (each account has its own password); each email names its organization.
    tokens = []
    for row in accounts:
        token = issue_reset(db, row.id, row.tenant_id)
        tokens.append(token)
        background.add_task(_send_reset_quietly, row.username, token, _organization_name(db, row.tenant_id))
    if is_development() and not smtp_configuration_status().get("configured"):
        background.tasks.clear()  # local development without email: the link is shown instead
        return {**accepted, "development_token": _development_token(tokens[0])}
    return accepted


@router.post("/reset-password")
def reset(data: Reset, db: Session = Depends(get_db)):
    try:
        bind_system(db, "redeem single-use password reset token")
        user_id = consume(db, data.token, "reset")
        row = db.query(AuthUser).filter(AuthUser.id == user_id).first()
        if row is None or _admin_blocked(row):
            raise ValueError("INVALID_RESET")
        bind_tenant(db, row.tenant_id)
        now = datetime.now(timezone.utc)
        if _password_reuse(db, row, data.password):
            raise ValueError("PASSWORD_REUSE_NOT_ALLOWED")
        row.password_hash = _hash(data.password)
        row.status = "ACTIVE"
        row.email_verified = True
        row.updated_at = now
        _record_password_change(db, row, row.password_hash, now)
        _activate_invited_memberships(db, row)
        db.commit()
        return {"status": "PASSWORD_RESET"}
    except ValueError:
        if not _legacy_compat_enabled():
            raise fail("INVALID_RESET")
        try:
            return auth_service.reset(data.token, data.password)
        except ValueError as e:
            raise fail(e)


@router.post("/activate-account")
def activate(data: Reset, db: Session = Depends(get_db)):
    try:
        bind_system(db, "redeem single-use activation token")
        user_id = consume(db, data.token, "activation")
        row = db.query(AuthUser).filter(AuthUser.id == user_id).first()
        if row is None or _admin_blocked(row):
            raise ValueError("INVALID_ACTIVATION")
        bind_tenant(db, row.tenant_id)
        now = datetime.now(timezone.utc)
        if _password_reuse(db, row, data.password):
            raise ValueError("PASSWORD_REUSE_NOT_ALLOWED")
        row.password_hash = _hash(data.password)
        row.status = "ACTIVE"
        row.email_verified = True
        row.updated_at = now
        _record_password_change(db, row, row.password_hash, now)
        _activate_invited_memberships(db, row)
        db.commit()
        return {"status": "ACTIVE", "user_id": str(row.id), "email": row.username}
    except ValueError as e:
        raise fail(e)
