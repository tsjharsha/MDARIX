"""Reusable authenticated, tenant-scoped request context."""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from auth.durable import hash_token
from auth.service import auth_service
from backend.app.db.models.foundation import (
    AuthUser,
    RoleAssignment,
    RoleDefinition,
    Tenant,
    TenantMembership,
)
from backend.app.db.models.stage2 import AuthSession
from backend.app.db.session import get_db
from backend.app.runtime_env import is_development
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
    from backend.app.trial.service import trial_has_ended

    if trial_has_ended(db, tenant_id):
        raise HTTPException(
            403,
            detail={
                "code": "TRIAL_ENDED",
                "message": "Your MDARIX free trial has ended. Contact us to continue with your data intact.",
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
    token = request.cookies.get("mdarix_session")
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
        # Legacy in-process sessions are a narrowly scoped test compatibility
        # path. They are disabled by default, including in development, and
        # can only be enabled explicitly for legacy unit tests. This prevents
        # an accidental environment mismatch from weakening authentication.
        import os

        legacy_fallback = is_development() and os.getenv("MDARIX_ALLOW_LEGACY_AUTH_FALLBACK", "").lower() == "true"
        if not legacy_fallback:
            raise HTTPException(401, detail={"code": "UNAUTHENTICATED", "message": "Authentication required"})
        try:
            legacy = auth_service.context(token)
        except ValueError:
            raise HTTPException(401, detail={"code": "UNAUTHENTICATED", "message": "Authentication required"})
        try:
            legacy_user_id = UUID(str(legacy["user_id"]))
            set_database_tenant_context(db, str(legacy["tenant_id"]))
            user = (
                db.query(AuthUser)
                .filter(
                    AuthUser.id == legacy_user_id,
                    AuthUser.tenant_id == legacy["tenant_id"],
                    AuthUser.status == "ACTIVE",
                )
                .first()
            )
        except (ValueError, TypeError):
            user = (
                db.query(AuthUser)
                .filter(
                    AuthUser.username == str(legacy["user_id"]).lower(),
                    AuthUser.tenant_id == legacy["tenant_id"],
                    AuthUser.status == "ACTIVE",
                )
                .first()
            )
        if user is not None and str(user.tenant_id) != str(legacy["tenant_id"]):
            raise HTTPException(401, detail={"code": "UNAUTHENTICATED", "message": "Authentication required"})
        if user is not None:
            ensure_tenant_access(db, user)
        if user is None:
            # Legacy unit-test clients do not create a database user. This
            # compatibility identity is development-only and never reaches
            # production deployments.
            return AuthenticatedRequestContext(
                str(legacy["user_id"]),
                token,
                str(legacy["tenant_id"]),
                None,
                legacy.get("active_role") or "Viewer",
                None,
                (),
                None,
                {},
                request.headers.get("X-Correlation-ID") or str(uuid4()),
            )
        membership = (
            db.query(TenantMembership)
            .filter(
                TenantMembership.user_id == user.id,
                TenantMembership.tenant_id == user.tenant_id,
                TenantMembership.status == "ACTIVE",
            )
            .first()
        )
        role_id = None
        role_name = user.role
        assignment = (
            db.query(RoleAssignment)
            .filter(
                RoleAssignment.tenant_id == user.tenant_id,
                RoleAssignment.user_id == user.id,
                RoleAssignment.status == "ACTIVE",
            )
            .first()
        )
        if assignment is not None and hasattr(assignment, "role_id"):
            role_id = str(assignment.role_id)
            role_row = (
                db.query(RoleDefinition)
                .filter(
                    RoleDefinition.tenant_id == user.tenant_id,
                    RoleDefinition.id == assignment.role_id,
                    RoleDefinition.status == "ACTIVE",
                )
                .first()
            )
            if role_row is not None:
                role_name = role_row.name
        return AuthenticatedRequestContext(
            str(user.id),
            token,
            str(user.tenant_id),
            str(membership.id) if membership else None,
            role_id or role_name,
            None,
            (),
            None,
            {},
            request.headers.get("X-Correlation-ID") or str(uuid4()),
        )
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
        request.headers.get("X-Correlation-ID") or str(uuid4()),
    )
