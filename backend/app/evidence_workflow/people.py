"""The signed-in person as the evidence endpoints see them: their permissions (the union over all their roles), their
roles (to tell whether a request to a role is theirs) and the role they act under (recorded on review history)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session

from backend.app.business_ids import as_uuid
from backend.app.db.session import get_db
from backend.app.request_context import AuthenticatedRequestContext, get_request_context
from backend.app.role_codes import role_code


@dataclass
class Person:
    user_id: str
    user_uuid: uuid.UUID | None
    tenant_id: uuid.UUID
    permissions: frozenset[str] = field(default_factory=frozenset)
    roles: list[str] = field(default_factory=list)
    account_role: str | None = None

    @property
    def role_codes(self) -> frozenset[str]:
        return frozenset(role_code(role) for role in self.roles if role)

    def holds(self, permission: str | None) -> bool:
        return bool(permission) and permission in self.permissions

    def holds_any(self, *permissions: str) -> bool:
        return any(self.holds(permission) for permission in permissions)

    def role_for(self, permission: str | None) -> str | None:
        """The role granting ``permission``, else the account role (recorded on review history)."""
        from backend.app.workflow.people import role_granting

        try:
            found = role_granting(self.roles, permission, self.account_role)
        except Exception:
            found = self.account_role
        return (role_code(found) or None) if found else None

    def is_user(self, ref) -> bool:
        return self.user_uuid is not None and as_uuid(ref) == self.user_uuid


def current_person(control_db: Session, ctx: AuthenticatedRequestContext) -> Person:
    from backend.app.access.permissions import effective_permissions
    from backend.app.workflow.people import find_user, roles_of

    tenant_id = uuid.UUID(str(ctx.tenant_id))
    user = find_user(control_db, tenant_id, ctx.user_id, active_only=False)
    roles = roles_of(control_db, user) if user is not None else ([ctx.active_role_id] if ctx.active_role_id else [])
    return Person(
        user_id=str(ctx.user_id),
        user_uuid=as_uuid(ctx.user_id),
        tenant_id=tenant_id,
        permissions=frozenset(effective_permissions(control_db, ctx) or ()),
        roles=list(roles),
        account_role=user.role if user is not None else ctx.active_role_id,
    )


def require_any_permission(*permissions: str):
    """A dependency allowing the request when the person holds at least one of ``permissions`` (403 otherwise)."""
    from backend.app.access.permissions import ALL

    unknown = [permission for permission in permissions if permission not in ALL]
    if not permissions or unknown:
        raise ValueError(f"Unknown permission {unknown}")

    def dependency(
        ctx: AuthenticatedRequestContext = Depends(get_request_context), db: Session = Depends(get_db)
    ) -> None:
        from backend.app.access.permissions import effective_permissions

        granted = effective_permissions(db, ctx)
        if not any(permission in granted for permission in permissions):
            raise HTTPException(
                403,
                detail={
                    "code": "PERMISSION_DENIED",
                    "message": "Your role does not allow this action",
                    "permission": " or ".join(permissions),
                },
            )

    return dependency
