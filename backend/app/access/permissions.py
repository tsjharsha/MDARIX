"""Fine-grained permissions for business actions: changing records, running AI, exporting, regulatory approval.

Reading data needs only a signed-in tenant session. Actions that change records, run AI, export data or approve a
regulatory document also need the permission below, derived from the user's role on the server. Unknown or custom
roles get no business permissions (read-only), so a new role can never silently gain write access.
Signing decisions is governed separately by approval authorities and segregation of duties.

A person may hold workflow roles in addition to their account role (``user_additional_roles``); what they may do is
the union of the permissions of all their roles.
"""

from __future__ import annotations

import uuid

from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session

from backend.app.db.models.foundation import AuthUser, RoleAssignment, RoleDefinition
from backend.app.db.models.workflow import UserAdditionalRole
from backend.app.db.session import get_db
from backend.app.request_context import AuthenticatedRequestContext, get_request_context
from backend.app.role_codes import (
    CUSTOMER_ADMIN,
    PLATFORM_ADMIN,
    WORKFLOW_ROLES,
    is_administrator_name,
    is_administrator_role,
    role_code,
)

RECORDS_WRITE = "records.write"
AI_RUN = "ai.run"
DATA_EXPORT = "data.export"
REGULATORY_APPROVE = "regulatory.approve"
# Workflow permissions: who may triage signals, open and assign investigations, work on them, review evidence, risk,
# regulatory and quality content, ask for evidence, and sign decisions.
SIGNAL_TRIAGE = "signal.triage"
INVESTIGATION_CREATE = "investigation.create"
INVESTIGATION_ASSIGN = "investigation.assign"
INVESTIGATION_WORK = "investigation.work"
EVIDENCE_REVIEW = "evidence.review"
EVIDENCE_REQUEST = "evidence.request"
RISK_REVIEW = "risk.review"
REGULATORY_REVIEW = "regulatory.review"
QUALITY_REVIEW = "quality.review"
DECISION_SIGN = "decision.sign"
ALL = frozenset(
    {
        RECORDS_WRITE,
        AI_RUN,
        DATA_EXPORT,
        REGULATORY_APPROVE,
        SIGNAL_TRIAGE,
        INVESTIGATION_CREATE,
        INVESTIGATION_ASSIGN,
        INVESTIGATION_WORK,
        EVIDENCE_REVIEW,
        EVIDENCE_REQUEST,
        RISK_REVIEW,
        REGULATORY_REVIEW,
        QUALITY_REVIEW,
        DECISION_SIGN,
    }
)

_WORK = frozenset({RECORDS_WRITE, AI_RUN, DATA_EXPORT})
_EVIDENCE = frozenset({EVIDENCE_REVIEW, EVIDENCE_REQUEST})
ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    "VIEWER": frozenset(),
    "TRIAGE_LEAD": _WORK | {SIGNAL_TRIAGE, INVESTIGATION_CREATE, INVESTIGATION_ASSIGN},
    "INVESTIGATOR": _WORK | _EVIDENCE | {INVESTIGATION_CREATE, INVESTIGATION_WORK},
    # Reviewers of risk and regulatory content read, ask and export; they do not change case records.
    "RISK_REVIEWER": frozenset({AI_RUN, DATA_EXPORT, RISK_REVIEW}) | _EVIDENCE,
    "REGULATORY_REVIEWER": frozenset({AI_RUN, DATA_EXPORT, REGULATORY_REVIEW, REGULATORY_APPROVE}) | _EVIDENCE,
    "REVIEWER": _WORK | _EVIDENCE | {QUALITY_REVIEW, INVESTIGATION_ASSIGN},
    "APPROVER": _WORK | {REGULATORY_APPROVE, DECISION_SIGN},
    "LEADER": ALL,
    # Platform administrators (MDARIX staff) keep full access to their own tenant's records.
    PLATFORM_ADMIN: ALL,
    # Customer administrators manage people and settings and, in the same account (one per person), may switch into
    # the workspace with an Investigator's rights: work on cases, evidence and Ask, and export. Never regulatory
    # approval, and never a signature: signing needs an approval authority (Approver, Leader), which they lack.
    CUSTOMER_ADMIN: _WORK,
}


def normalize_role(role: str | None) -> str:
    """'Approver', 'APPROVER' and 'approver ' are the same role everywhere roles are compared; the administrator
    aliases ('Administrator', 'Customer Admin', ...) resolve to their canonical role (backend/app/role_codes.py)."""
    return role_code(role)


_normalize = normalize_role  # original name, kept for existing imports


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
    return role_of_user(db, user)


def role_of_user(db: Session, user: AuthUser) -> str | None:
    """An active role assignment, else the account's role.

    An administrator account keeps its administrator role: no assignment replaces it (R11), so a custom role named
    like "Approver" never turns an administrator into someone who signs. A custom role named like an administrator
    role (refused since 0.10.49) is ignored."""
    if is_administrator_role(user.role):
        return user.role
    assigned = (
        db.query(RoleDefinition.name)
        .join(RoleAssignment, RoleAssignment.role_id == RoleDefinition.id)
        .filter(
            RoleAssignment.user_id == user.id,
            RoleAssignment.tenant_id == user.tenant_id,
            RoleAssignment.status == "ACTIVE",
            RoleDefinition.status == "ACTIVE",
        )
        .all()
    )
    return next((name for (name,) in assigned if not is_administrator_name(name)), user.role)


def additional_roles_of_user(db: Session, user: AuthUser) -> list[str]:
    """The workflow roles the person holds besides their account role (ACTIVE only), in workflow order.

    Only workflow roles count: an administrator role or an unknown code stored here grants nothing."""
    rows = (
        db.query(UserAdditionalRole.role_code)
        .filter(
            UserAdditionalRole.tenant_id == user.tenant_id,
            UserAdditionalRole.user_id == user.id,
            UserAdditionalRole.status == "ACTIVE",
        )
        .all()
    )
    held = {_normalize(code) for (code,) in rows}
    return [code for code in WORKFLOW_ROLES if code in held]


def roles_of_user(db: Session, user: AuthUser) -> list[str]:
    """Every role the person holds: the account role first (as ``role_of_user`` gives it), then the additional
    workflow roles, each role once (compared by normalized code)."""
    roles: list[str] = []
    seen: set[str] = set()
    account = role_of_user(db, user)
    # Administrators stay outside the case workflow: additional roles never widen an administrator account.
    extra = [] if _normalize(account) in {PLATFORM_ADMIN, CUSTOMER_ADMIN} else additional_roles_of_user(db, user)
    for role in [account, *extra]:
        code = _normalize(role)
        if not code or code in seen:
            continue
        seen.add(code)
        roles.append(role)
    return roles


def permissions_for_roles(roles) -> frozenset[str]:
    """The union of the permissions of several roles."""
    granted: frozenset[str] = frozenset()
    for role in roles or ():
        granted = granted | permissions_for_role(role)
    return granted


def effective_roles(db: Session, ctx: AuthenticatedRequestContext) -> list[str]:
    """Every role the server trusts for this session's user (``roles_of_user``). Never a request value."""
    try:
        user_id = uuid.UUID(str(ctx.user_id))
    except (TypeError, ValueError):
        # Legacy in-process sessions (tests only) carry their role on the context.
        return [ctx.active_role_id] if ctx.active_role_id else []
    user = db.query(AuthUser).filter(AuthUser.id == user_id, AuthUser.tenant_id == ctx.tenant_id).first()
    if user is None:
        return []
    return roles_of_user(db, user)


def effective_permissions(db: Session, ctx: AuthenticatedRequestContext) -> frozenset[str]:
    """What this session's user may do: the union over their account role and their active additional roles."""
    return permissions_for_roles(effective_roles(db, ctx))


def require_permission(permission: str):
    if permission not in ALL:
        raise ValueError(f"Unknown permission {permission}")

    def dependency(
        ctx: AuthenticatedRequestContext = Depends(get_request_context), db: Session = Depends(get_db)
    ) -> None:
        if permission not in effective_permissions(db, ctx):
            raise HTTPException(
                403,
                detail={
                    "code": "PERMISSION_DENIED",
                    "message": "Your role does not allow this action",
                    "permission": permission,
                },
            )

    return dependency
