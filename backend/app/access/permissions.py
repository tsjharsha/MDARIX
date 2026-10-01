"""Fine-grained permissions for business actions: changing records, running AI, exporting, regulatory approval.

Reading data needs only a signed-in tenant session. Actions that change records, run AI, export data or approve a
regulatory document also need the permission below, derived from the user's role on the server. Unknown or custom
roles get no business permissions (read-only), so a new role can never silently gain write access.
Signing decisions is governed separately by approval authorities and segregation of duties.
"""

from __future__ import annotations

import uuid

from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session

from backend.app.db.models.foundation import AuthUser, RoleAssignment, RoleDefinition
from backend.app.db.session import get_db
from backend.app.request_context import AuthenticatedRequestContext, get_request_context

RECORDS_WRITE = "records.write"
AI_RUN = "ai.run"
DATA_EXPORT = "data.export"
REGULATORY_APPROVE = "regulatory.approve"
ALL = frozenset({RECORDS_WRITE, AI_RUN, DATA_EXPORT, REGULATORY_APPROVE})

_WORK = frozenset({RECORDS_WRITE, AI_RUN, DATA_EXPORT})
ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    "VIEWER": frozenset(),
    "INVESTIGATOR": _WORK,
    "REVIEWER": _WORK,
    "APPROVER": _WORK | {REGULATORY_APPROVE},
    "LEADER": ALL,
    # Platform administrators (MDARIX staff) keep full access to their own tenant's records.
    "ADMINISTRATOR": ALL,
    "ADMIN": ALL,
    "MDARIX_ADMINISTRATOR": ALL,
    "PLATFORM_ADMIN": ALL,
    # Customer administrators manage people and settings, not investigations.
    "CUSTOMER_ADMIN": frozenset({DATA_EXPORT}),
}


def _normalize(role: str | None) -> str:
    return "_".join(str(role or "").strip().upper().replace("-", " ").split())


def permissions_for_role(role: str | None) -> frozenset[str]:
    return ROLE_PERMISSIONS.get(_normalize(role), frozenset())


def effective_role(db: Session, ctx: AuthenticatedRequestContext) -> str | None:
    """The role the server trusts: an active role assignment, else the account's role. Never a request value."""
    try:
        user_id = uuid.UUID(str(ctx.user_id))
    except (TypeError, ValueError):
        # Legacy in-process sessions (tests only) carry their role on the context.
        return ctx.active_role_id
    user = db.query(AuthUser).filter(AuthUser.id == user_id, AuthUser.tenant_id == ctx.tenant_id).first()
    if user is None:
        return None
    assigned = (
        db.query(RoleDefinition.name)
        .join(RoleAssignment, RoleAssignment.role_id == RoleDefinition.id)
        .filter(
            RoleAssignment.user_id == user.id,
            RoleAssignment.tenant_id == user.tenant_id,
            RoleAssignment.status == "ACTIVE",
            RoleDefinition.status == "ACTIVE",
        )
        .first()
    )
    return assigned[0] if assigned else user.role


def require_permission(permission: str):
    if permission not in ALL:
        raise ValueError(f"Unknown permission {permission}")

    def dependency(
        ctx: AuthenticatedRequestContext = Depends(get_request_context), db: Session = Depends(get_db)
    ) -> None:
        if permission not in permissions_for_role(effective_role(db, ctx)):
            raise HTTPException(
                403,
                detail={
                    "code": "PERMISSION_DENIED",
                    "message": "Your role does not allow this action",
                    "permission": permission,
                },
            )

    return dependency
