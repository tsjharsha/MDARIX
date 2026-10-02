"""Authorization helpers for the access API: authenticated user, administrator and platform-administrator checks."""

import uuid

from fastapi import HTTPException, Request
from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.app.db.models.foundation import (
    AuthUser,
)
from backend.app.request_context import get_request_context
from backend.app.runtime_env import is_development
from backend.app.db.tenant_scope import bind_system


def _require_administrator(request: Request, db: Session) -> AuthUser:
    user = _authenticated_user(request, db)
    if (user.role or "").upper() not in {
        "ADMINISTRATOR",
        "ADMIN",
        "MDARIX ADMINISTRATOR",
        "PLATFORM_ADMIN",
        "CUSTOMER_ADMIN",
    }:
        raise HTTPException(403, detail={"code": "ADMINISTRATOR_REQUIRED", "message": "Administrator role required"})
    return user


def _role_code(user: AuthUser) -> str:
    return (user.role or "").strip().upper().replace(" ", "_")


PLATFORM_ROLE_CODES = frozenset({"PLATFORM_ADMIN", "MDARIX_ADMINISTRATOR", "ADMINISTRATOR", "ADMIN"})


def _is_platform_role(role: str | None) -> bool:
    return (role or "").strip().upper().replace(" ", "_") in PLATFORM_ROLE_CODES


def _is_platform_admin(user: AuthUser) -> bool:
    return _is_platform_role(user.role)


def platform_account_clause():
    """SQL: the AuthUser row is a platform (MDARIX staff) account, with the same normalization as _is_platform_role."""
    normalized = func.upper(func.replace(func.trim(func.coalesce(AuthUser.role, "")), " ", "_"))
    return normalized.in_(sorted(PLATFORM_ROLE_CODES))


def visible_user_filters(viewer: AuthUser) -> list:
    """Filters for AuthUser queries: platform accounts are visible to platform administrators only.

    MDARIX staff accounts can sit in a customer tenant (for example the tenant platform administrators sign in to);
    the customer's administrators and users must not see, open or change them.
    """
    return [] if _is_platform_admin(viewer) else [~platform_account_clause()]


def hidden_platform_user_ids(db: Session, viewer: AuthUser, tenant_id):
    """Ids of the tenant's platform accounts the viewer may not see (None when the viewer sees everyone)."""
    if _is_platform_admin(viewer):
        return None
    return db.query(AuthUser.id).filter(AuthUser.tenant_id == tenant_id, platform_account_clause())


def is_hidden_from(viewer: AuthUser, user) -> bool:
    """True when ``user`` is a platform account that ``viewer`` (not a platform administrator) may not see."""
    return user.id != viewer.id and not _is_platform_admin(viewer) and _is_platform_role(user.role)


def ensure_user_visible(viewer: AuthUser, user: AuthUser | None) -> AuthUser:
    """404 for a user the viewer may not see, exactly as for one that does not exist (nothing to enumerate)."""
    if user is None or is_hidden_from(viewer, user):
        raise HTTPException(404, detail={"code": "USER_NOT_FOUND", "message": "User is not available for this tenant"})
    return user


def _guard_user_administration(
    admin: AuthUser, target: AuthUser | None = None, new_role: str | None = None, changes_access: bool = False
) -> None:
    """Stop privilege escalation and self-lockout in tenant user administration.

    Only platform administrators may grant or change a platform-level role; every spelling the
    platform-admin check accepts is covered. A customer administrator cannot modify a user who
    holds a platform role. No administrator can change their own role or status.
    """
    if new_role is not None and _is_platform_role(new_role) and not _is_platform_admin(admin):
        raise HTTPException(
            403,
            detail={
                "code": "PLATFORM_ROLE_NOT_ALLOWED",
                "message": "Customer administrators cannot assign platform roles",
            },
        )
    if target is None:
        return
    if _is_platform_role(target.role) and not _is_platform_admin(admin):
        raise HTTPException(
            403,
            detail={"code": "PLATFORM_USER_PROTECTED", "message": "Platform users can only be changed by the platform"},
        )
    if changes_access and target.id == admin.id:
        raise HTTPException(
            409,
            detail={"code": "SELF_CHANGE_NOT_ALLOWED", "message": "You cannot change your own role or status"},
        )


def _is_customer_admin(user: AuthUser) -> bool:
    return _role_code(user) == "CUSTOMER_ADMIN"


def _require_platform_admin(request: Request, db: Session) -> AuthUser:
    user = _authenticated_user(request, db)
    if not _is_platform_admin(user):
        raise HTTPException(
            403, detail={"code": "PLATFORM_ADMIN_REQUIRED", "message": "Platform administrator role required"}
        )
    # Platform administration spans tenants (customer directory, provisioning, trials), so only after the role is
    # verified does this request leave its own tenant's row-level scope.
    bind_system(db, "platform administrator")
    return user


def _authenticated_user(request: Request, db: Session) -> AuthUser:
    context = get_request_context(request, db)
    try:
        user = (
            db.query(AuthUser)
            .filter(AuthUser.id == uuid.UUID(context.user_id), AuthUser.tenant_id == context.tenant_id)
            .first()
        )
    except (ValueError, TypeError):
        user = None
    if user is None and is_development():
        user = (
            db.query(AuthUser)
            .filter(AuthUser.username == context.user_id.lower(), AuthUser.tenant_id == context.tenant_id)
            .first()
        )
    if user is None or user.status != "ACTIVE":
        raise HTTPException(401, detail={"code": "UNAUTHENTICATED", "message": "Authentication required"})
    return user


def _admin_tenant(request: Request, db: Session) -> AuthUser:
    return _require_administrator(request, db)


def _admin_detail_tenant(request: Request, db: Session):
    return _admin_tenant(request, db).tenant_id
