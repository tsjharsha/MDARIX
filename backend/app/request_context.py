"""Reusable authenticated, tenant-scoped request context."""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from auth.cookies import read_session_token
from backend.app.logging_setup import current_request_id
from auth.durable import hash_token
from backend.app.db.models.foundation import (
    AuthUser,
    Tenant,
    TenantMembership,
)
from backend.app.db.models.stage2 import AuthSession
from backend.app.db.session import get_db
from backend.app.db.tenant_scope import bind_tenant


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
                    "Your MDARIX free trial has ended. Contact us to continue with your data intact"
                    + (f"; otherwise it is deleted on {deleted_on}." if deleted_on else ".")
                ),
                "ended_on": ended_on,
                "data_deleted_on": deleted_on,
            },
        )


def ensure_tenant_access(db: Session, user) -> None:
    """Refuse access when the user's organization or their membership in it has been suspended or revoked."""
    tenant = db.query(Tenant).filter(Tenant.id == user.tenant_id).first()
    if tenant is None or str(tenant.status or "").upper() in BLOCKED_TENANT_STATUSES:
        raise HTTPException(
            403, detail={"code": "TENANT_ACCESS_SUSPENDED", "message": "Access to this organization is suspended"}
        )
    memberships = db.query(TenantMembership).filter(
        TenantMembership.user_id == user.id, TenantMembership.tenant_id == user.tenant_id
    )
    _ensure_trial_open(db, tenant.id)
    if memberships.filter(TenantMembership.status == "ACTIVE").first() is not None:
        return
    if memberships.filter(TenantMembership.status.in_(sorted(BLOCKED_MEMBERSHIP_STATUSES))).first() is not None:
        raise HTTPException(
            403, detail={"code": "MEMBERSHIP_SUSPENDED", "message": "Your access to this organization is suspended"}
        )


def _idle_limit() -> timedelta:
    import os

    return timedelta(minutes=max(1, int(os.getenv("MDARIX_SESSION_IDLE_MINUTES", "30"))))


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


def get_request_context(request: Request, db: Session = Depends(get_db)) -> AuthenticatedRequestContext:
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
    durable.last_seen_at = now
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
    ensure_tenant_access(db, user)
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
