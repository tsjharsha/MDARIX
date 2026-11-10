"""Reusable authenticated, tenant-scoped request context."""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, Request, Response
from sqlalchemy.orm import Session

from auth.cookies import (
    SESSION_RENEWAL_SECONDS,
    SESSION_SECONDS,
    SESSION_WINDOW_SECONDS,
    read_session_token,
    set_session_cookie,
)
from backend.app.logging_setup import current_request_id
from auth.durable import hash_token
from backend.app.db.models.foundation import (
    AuthUser,
    Tenant,
    TenantMembership,
)
from backend.app.db.models.stage2 import AuthSession
from backend.app.db.models.customer_lifecycle import Customer
from backend.app.customer_lifecycle import customer_blocks_access
from backend.app.db.session import get_db
from backend.app.db.tenant_scope import bind_tenant
from backend.app.deployment_role import serves_account

logger = logging.getLogger(__name__)
DEFAULT_IDLE_MINUTES = 30


def set_database_tenant_context(db: Session, tenant_id: str) -> None:
    """Bind the current transaction to the authenticated tenant for RLS.

    SET LOCAL is transaction-scoped, so a pooled connection cannot retain a
    previous tenant after the request completes.
    """
    bind_tenant(db, tenant_id)


# Organization and membership states that end access. Other states (for example INVITED, PROVISIONED or
# EXPIRING_SOON) are left to the lifecycle workflows; users with no membership row are legacy and unaffected.
BLOCKED_TENANT_STATUSES = frozenset({"SUSPENDED", "TERMINATED", "ARCHIVED"})
BLOCKED_MEMBERSHIP_STATUSES = frozenset({"SUSPENDED", "REVOKED", "REMOVED", "OFFBOARDED", "RETIRED", "INACTIVE"})


def _ensure_trial_open(db: Session, tenant_id) -> None:
    """A Free Trial workspace closes on its end date, even if no admin has run the subscription job."""
    from backend.app.trial.service import trial_end_dates, trial_has_ended

    if trial_has_ended(db, tenant_id):
        ended_on, deleted_on = trial_end_dates(db, tenant_id)
        raise HTTPException(
            403,
            detail={
                "code": "TRIAL_ENDED",
                "message": (
                    "Your MDARIX free trial has ended."
                    + (f" Its data is deleted, at the earliest, on {deleted_on}." if deleted_on else "")
                    + " To continue, talk to us about a pilot: it works on your real data."
                ),
                "ended_on": ended_on,
                "data_deleted_on": deleted_on,
            },
        )


def ensure_tenant_access(db: Session, user) -> None:
    """Refuse access when the user's organization or their membership in it has been suspended or revoked."""
    tenant = db.query(Tenant).filter(Tenant.id == user.tenant_id).first()
    # A free trial past its end reads as ended (the trial-ended page), even when an older release's hourly job
    # suspended its organization at the end (J25).
    if tenant is not None:
        _ensure_trial_open(db, tenant.id)
    if tenant is None or str(tenant.status or "").upper() in BLOCKED_TENANT_STATUSES:
        raise HTTPException(
            403, detail={"code": "TENANT_ACCESS_SUSPENDED", "message": "Access to this organization is suspended"}
        )
    # A suspended (or terminated) customer blocks every tenant it owns, whatever the tenant's own status.
    customer_status = (
        db.query(Customer.lifecycle_status).filter(Customer.id == tenant.customer_id).scalar()
        if getattr(tenant, "customer_id", None)
        else None
    )
    if customer_blocks_access(customer_status):
        raise HTTPException(
            403,
            detail={
                "code": "TENANT_ACCESS_SUSPENDED",
                "message": "Your organization's access to MDARIX is suspended. Contact MDARIX support.",
            },
        )
    memberships = db.query(TenantMembership).filter(
        TenantMembership.user_id == user.id, TenantMembership.tenant_id == user.tenant_id
    )
    if memberships.filter(TenantMembership.status == "ACTIVE").first() is not None:
        return
    if memberships.filter(TenantMembership.status.in_(sorted(BLOCKED_MEMBERSHIP_STATUSES))).first() is not None:
        raise HTTPException(
            403, detail={"code": "MEMBERSHIP_SUSPENDED", "message": "Your access to this organization is suspended"}
        )


_idle_setting_warned: set[str] = set()


def _idle_limit() -> timedelta:
    """The idle timeout. A misconfigured MDARIX_SESSION_IDLE_MINUTES falls back to the default (logged once per
    value), because a typo in one setting must not turn every signed-in request into a server error."""
    import os

    raw = os.getenv("MDARIX_SESSION_IDLE_MINUTES", str(DEFAULT_IDLE_MINUTES))
    try:
        minutes = int(raw.strip())
    except (ValueError, AttributeError):
        if raw not in _idle_setting_warned:
            _idle_setting_warned.add(raw)
            logger.error(
                "MDARIX_SESSION_IDLE_MINUTES is not a whole number; using the default of %s minutes",
                DEFAULT_IDLE_MINUTES,
            )
        minutes = DEFAULT_IDLE_MINUTES
    return timedelta(minutes=max(1, minutes))


# Sent by the browser on reads the page makes on its own (a poll), not the person (frontend apiClient.ts).
BACKGROUND_HEADER = "X-MDARIX-Background"


def is_background_request(request: Request | None) -> bool:
    """A background read: it is served as usual but is no activity, so it neither restarts the idle timeout nor
    renews the session. A page left open therefore still signs out after MDARIX_SESSION_IDLE_MINUTES."""
    headers = getattr(request, "headers", None)
    return bool(headers) and headers.get(BACKGROUND_HEADER, "").strip() == "1"


def session_expiry(session_row, now: datetime | None = None) -> dict[str, str]:
    """When this session ends if nothing changes: the absolute ``expires_at`` and the ``idle_expires_at`` the idle
    timeout implies (whichever comes first wins), as ISO strings for the browser's warning."""
    now = now or datetime.now(timezone.utc)
    last_seen = getattr(session_row, "last_seen_at", None) or now
    return {
        "expires_at": session_row.expires_at.isoformat(),
        "idle_expires_at": min(session_row.expires_at, last_seen + _idle_limit()).isoformat(),
    }


def session_is_live(session_row, now: datetime | None = None) -> bool:
    """Whether a session still lets its person in: not revoked, before its absolute ``expires_at`` and used within the
    idle timeout (the rules of ``get_request_context``)."""
    now = now or datetime.now(timezone.utc)
    if getattr(session_row, "revoked_at", None) is not None or session_row.expires_at <= now:
        return False
    last_seen = getattr(session_row, "last_seen_at", None)
    return last_seen is None or now - last_seen <= _idle_limit()


def renew_session_if_due(session_row, now: datetime, response: Response | None, token: str | None) -> bool:
    """Sliding renewal: when less than SESSION_RENEWAL_SECONDS of the window remain, extend the window, never past
    SESSION_SECONDS after sign-in. Re-issues the cookie with the new lifetime when a response is at hand.

    Returns True when ``expires_at`` changed (the caller commits). Sessions that still owe MFA are not renewed:
    their short lifetime is the point.
    """
    if getattr(session_row, "mfa_state", None):
        return False
    expires_at = session_row.expires_at
    created_at = getattr(session_row, "created_at", None) or now
    if expires_at - now >= timedelta(seconds=SESSION_RENEWAL_SECONDS):
        return False
    cap = created_at + timedelta(seconds=SESSION_SECONDS)
    renewed = min(now + timedelta(seconds=SESSION_WINDOW_SECONDS), cap)
    if renewed <= expires_at:
        return False  # the absolute limit is near: the session ends when the current window does
    session_row.expires_at = renewed
    if response is not None and token:
        set_session_cookie(response, token, max_age=max(1, int((renewed - now).total_seconds())))
    return True


@dataclass(frozen=True)
class AuthenticatedRequestContext:
    user_id: str
    session_id: str
    tenant_id: str
    membership_id: str | None
    active_role_id: str | None
    persona: str | None
    permission_set_ids: tuple[str, ...]
    plan_id: str | None
    entitlements: dict
    correlation_id: str


def get_request_context(
    request: Request, db: Session = Depends(get_db), response: Response = None
) -> AuthenticatedRequestContext:
    """The signed-in, tenant-bound context of this request.

    ``response`` is filled in by FastAPI when this runs as a dependency, so a renewed session can re-issue its
    cookie; callers that invoke it directly (without a response) still get the server-side renewal.
    """
    token = read_session_token(request)
    if not token:
        raise HTTPException(401, detail={"code": "UNAUTHENTICATED", "message": "Authentication required"})
    durable = (
        db.query(AuthSession)
        .filter(
            AuthSession.session_hash == hash_token(token),
            AuthSession.revoked_at.is_(None),
            AuthSession.expires_at > datetime.now(timezone.utc),
        )
        .first()
    )
    if durable is None or not hasattr(durable, "user_id"):
        raise HTTPException(401, detail={"code": "UNAUTHENTICATED", "message": "Authentication required"})
    now = datetime.now(timezone.utc)
    last_seen = getattr(durable, "last_seen_at", None)
    if last_seen is not None and now - last_seen > _idle_limit():
        # Idle too long: the session ends on the server, not only in the browser.
        durable.revoked_at = now
        if hasattr(db, "commit"):
            db.commit()
        raise HTTPException(401, detail={"code": "SESSION_IDLE_TIMEOUT", "message": "Signed out after inactivity"})
    mfa_state = getattr(durable, "mfa_state", None)
    if mfa_state:
        # Password checked, second factor not yet: only the MFA steps (under /api/v1/auth) are open.
        code = "MFA_ENROLLMENT_REQUIRED" if mfa_state == "ENROLL" else "MFA_REQUIRED"
        raise HTTPException(403, detail={"code": code, "message": "Complete multi-factor authentication first"})
    if not is_background_request(request):
        durable.last_seen_at = now
        renew_session_if_due(durable, now, response, token)
    set_database_tenant_context(db, str(durable.tenant_id))
    if hasattr(db, "commit"):
        db.commit()
    user_id, tenant_id = str(durable.user_id), str(durable.tenant_id)
    user = (
        db.query(AuthUser)
        .filter(AuthUser.id == user_id, AuthUser.tenant_id == tenant_id, AuthUser.status == "ACTIVE")
        .first()
    )
    if user is None:
        raise HTTPException(401, detail={"code": "UNAUTHENTICATED", "message": "Authentication required"})
    if not serves_account(user.tenant_id, user.role):
        # A session this deployment does not serve (another organization's in a CELL, a customer's on the PLATFORM,
        # platform staff in a CELL) is no session here, whatever database it was created in.
        raise HTTPException(401, detail={"code": "UNAUTHENTICATED", "message": "Authentication required"})
    ensure_tenant_access(db, user)
    from backend.app import mfa

    if not mfa.is_enrolled(user) and mfa.required_for(user, db):
        # A role that now needs MFA (an added or custom role, a changed account role) reaches open sessions too: the
        # browser goes to the authenticator setup sign-in uses (/mfa/enroll accepts this session), never a dead end;
        # nothing is stored, so a role taken away again lets the same session back in (code audit 1).
        raise HTTPException(
            403,
            detail={
                "code": "MFA_ENROLLMENT_REQUIRED",
                "message": "Your role now requires two-factor sign-in: set up your authenticator app to continue",
            },
        )
    from genai.governance import set_request_tenant

    # Model calls made while handling this request apply this organization's AI switch and budget.
    set_request_tenant(tenant_id)
    membership = (
        db.query(TenantMembership)
        .filter(
            TenantMembership.user_id == user.id,
            TenantMembership.tenant_id == user.tenant_id,
            TenantMembership.status == "ACTIVE",
        )
        .first()
    )
    return AuthenticatedRequestContext(
        user_id,
        token,
        tenant_id,
        str(membership.id) if membership else None,
        None,
        None,
        (),
        None,
        {},
        current_request_id(request),
    )
