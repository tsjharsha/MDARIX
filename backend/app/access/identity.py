"""Tenant identity administration: users, memberships, personas, roles and permission sets."""

import logging
import secrets
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from access_control.personas import R1_PERSONAS as PERSONAS
from access_control.personas import get_persona
from auth.durable import issue_invitation, issue_reset, revoke_user_sessions
from auth.emailer import (
    TEAM_INVITED,
    TEAM_MFA_RESET,
    TEAM_ROLE_CHANGED,
    EmailDeliveryError,
    send_activation_email,
    send_password_reset_email,
)
from auth.service import _hash
from backend.app.db.models.foundation import (
    AuditEvent,
    AuthUser,
    PermissionSetDefinition,
    PersonaAssignment,
    RoleAssignment,
    RoleDefinition,
    RolePermissionSet,
    Tenant,
    TenantMembership,
)
from backend.app.db.models.workflow import UserAdditionalRole
from backend.app.db.session import get_db
from backend.app import team_notices
from backend.app.access.schemas import (
    AdditionalRolesRequest,
    MembershipRequest,
    MfaResetRequest,
    PersonalDataErasureRequest,
    PasswordActionRequest,
    PermissionSetRequest,
    PersonaRequest,
    RoleAssignmentRequest,
    RolePermissionRequest,
    RoleRequest,
    StatusRequest,
    UserCreateRequest,
    UserStatusRequest,
)
from backend.app.access.authz import (
    _admin_tenant,
    _guard_user_administration,
    _is_platform_admin,
    _is_platform_role,
    _require_administrator,
    ensure_user_visible,
    hidden_platform_user_ids,
    is_hidden_from,
    visible_user_filters,
)
from backend.app.access.common import (
    _ensure_email_not_used_elsewhere,
    _admin_target_tenant,
    _audit_configuration,
    _development_token,
    _enforce_invite_limits,
    erasure_refused,
)
from backend.app.access.session import context
from backend.app.role_codes import WORKFLOW_ROLES, is_administrator_name, is_administrator_role, role_label

router = APIRouter(prefix="/api/v1", tags=["Access Control"])
logger = logging.getLogger(__name__)


@router.get("/admin/identity/personas")
def persona_catalog(request: Request, db: Session = Depends(get_db)):
    """Read-only administrator catalog used by the identity control plane."""
    _require_administrator(request, db)
    return [
        {"code": persona.code, "label": persona.label, "dashboard_emphasis": list(persona.dashboard_emphasis)}
        for persona in PERSONAS
    ]


def _belongs_to_hidden_account(db: Session, viewer, user_id) -> bool:
    """True when the record belongs to a platform account the viewer may not see or change."""
    owner = db.query(AuthUser).filter(AuthUser.id == user_id).first()
    return bool(owner and is_hidden_from(viewer, owner))


@router.get("/admin/identity/users/{user_id}")
def admin_user(user_id: uuid.UUID, request: Request, db: Session = Depends(get_db)):
    admin = _admin_tenant(request, db)
    user = db.query(AuthUser).filter(AuthUser.id == user_id, AuthUser.tenant_id == admin.tenant_id).first()
    ensure_user_visible(admin, user)
    return (
        context(request, db)
        if user.id == admin.id
        else {
            "user_id": str(user.id),
            "business_id": user.business_id,
            "display_name": user.display_name,
            "email": user.username,
            "tenant_id": str(user.tenant_id),
            "role": user.role,
            "role_label": role_label(user.role),
            "status": user.status,
        }
    )


@router.post("/admin/identity/memberships")
def create_membership(payload: MembershipRequest, request: Request, db: Session = Depends(get_db)):
    admin = _admin_tenant(request, db)
    user = db.query(AuthUser).filter(AuthUser.id == payload.user_id, AuthUser.tenant_id == admin.tenant_id).first()
    ensure_user_visible(admin, user)
    existing = db.query(TenantMembership).filter_by(tenant_id=admin.tenant_id, user_id=user.id).first()
    if existing:
        existing.status = "ACTIVE"
        existing.is_default = payload.is_default
        result = existing
    else:
        result = TenantMembership(
            id=uuid.uuid4(),
            tenant_id=admin.tenant_id,
            user_id=user.id,
            status="ACTIVE",
            is_default=payload.is_default,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        db.add(result)
    db.commit()
    return {
        "membership_id": str(result.id),
        "tenant_id": str(admin.tenant_id),
        "user_id": str(user.id),
        "status": result.status,
    }


@router.post("/admin/identity/persona-assignments")
def assign_persona(payload: PersonaRequest, request: Request, db: Session = Depends(get_db)):
    admin = _admin_tenant(request, db)
    try:
        persona = get_persona(payload.persona_code)
    except ValueError as exc:
        raise HTTPException(
            422, detail={"code": "UNKNOWN_PERSONA", "message": "Persona is not in the R1 catalog"}
        ) from exc
    user = db.query(AuthUser).filter(AuthUser.id == payload.user_id, AuthUser.tenant_id == admin.tenant_id).first()
    ensure_user_visible(admin, user)
    row = (
        db.query(PersonaAssignment)
        .filter_by(tenant_id=admin.tenant_id, user_id=user.id, persona_code=persona.code)
        .first()
    )
    if row is None:
        row = PersonaAssignment(
            id=uuid.uuid4(),
            tenant_id=admin.tenant_id,
            user_id=user.id,
            persona_code=persona.code,
            status="ACTIVE",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        db.add(row)
    else:
        row.status = "ACTIVE"
    db.commit()
    return {"assignment_id": str(row.id), "user_id": str(user.id), "persona_code": persona.code, "status": row.status}


@router.post("/admin/identity/permission-sets")
def create_permission_set(payload: PermissionSetRequest, request: Request, db: Session = Depends(get_db)):
    admin = _admin_tenant(request, db)
    now = datetime.now(timezone.utc)
    row = PermissionSetDefinition(
        id=uuid.uuid4(),
        tenant_id=admin.tenant_id,
        code=payload.code,
        object_permissions=payload.object_permissions,
        field_permissions=payload.field_permissions,
        action_permissions=payload.action_permissions,
        version=payload.version,
        status="DRAFT",
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    db.commit()
    return {
        "permission_set_id": str(row.id),
        "tenant_id": str(admin.tenant_id),
        "code": row.code,
        "version": row.version,
        "status": row.status,
    }


@router.post("/admin/identity/roles")
def create_role(payload: RoleRequest, request: Request, db: Session = Depends(get_db)):
    admin = _admin_tenant(request, db)
    refuse_administrator_role_name(payload.name, payload.code)
    now = datetime.now(timezone.utc)
    row = RoleDefinition(
        id=uuid.uuid4(),
        tenant_id=admin.tenant_id,
        code=payload.code,
        name=payload.name,
        version=payload.version,
        status="DRAFT",
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    db.commit()
    return {
        "role_id": str(row.id),
        "tenant_id": str(admin.tenant_id),
        "code": row.code,
        "name": row.name,
        "version": row.version,
        "status": row.status,
    }


def refuse_administrator_role_name(*names: str | None) -> None:
    """An administrator's code ("Admin") or the label people see ("Platform Administrator") is never a custom role's
    name or code (R11): administrator roles are given on the account only."""
    if any(is_administrator_name(name) for name in names):
        raise HTTPException(
            422,
            detail={
                "code": "ADMINISTRATOR_ROLE_NOT_ASSIGNABLE",
                "message": "Administrator roles are given on the account, not as custom roles",
            },
        )


def _guard_custom_role_assignment(admin: AuthUser, user: AuthUser, role: RoleDefinition) -> None:
    """R11: a custom role never makes an administrator an approver, and never carries an administrator role.

    The same rules as for the account role and additional roles: nobody changes their own role, an administrator
    account keeps its administrator role, and administrator roles are given on the account, never as custom roles
    (platform roles only by the platform)."""
    for name in (role.name, role.code):
        _guard_user_administration(admin, new_role=name)
    _guard_user_administration(admin, target=user, changes_access=True)
    refuse_administrator_role_name(role.name, role.code)
    if is_administrator_role(user.role):
        raise HTTPException(
            409,
            detail={
                "code": "ADMINISTRATOR_ROLE_FIXED",
                "message": "An administrator's role is set on the account; a custom role cannot change it",
            },
        )


@router.post("/admin/identity/role-assignments")
def assign_role(payload: RoleAssignmentRequest, request: Request, db: Session = Depends(get_db)):
    admin = _admin_tenant(request, db)
    user = db.query(AuthUser).filter(AuthUser.id == payload.user_id, AuthUser.tenant_id == admin.tenant_id).first()
    if user is not None:
        ensure_user_visible(admin, user)
    role = (
        db.query(RoleDefinition)
        .filter(
            RoleDefinition.id == payload.role_id,
            RoleDefinition.tenant_id == admin.tenant_id,
            RoleDefinition.status == "ACTIVE",
        )
        .first()
    )
    if user is None or role is None:
        raise HTTPException(
            404,
            detail={
                "code": "ROLE_ASSIGNMENT_SCOPE_INVALID",
                "message": "User and role must belong to this tenant and be active",
            },
        )
    _guard_custom_role_assignment(admin, user, role)
    row = db.query(RoleAssignment).filter_by(tenant_id=admin.tenant_id, user_id=user.id, role_id=role.id).first()
    if row is None or str(row.status).upper() != "ACTIVE":
        # The person is told which role they were given (backend/app/team_notices.py).
        team_notices.queue_organization_change(db, admin, user, TEAM_ROLE_CHANGED, custom_roles_added=(role.id,))
    if row is None:
        row = RoleAssignment(
            id=uuid.uuid4(),
            tenant_id=admin.tenant_id,
            user_id=user.id,
            role_id=role.id,
            status="ACTIVE",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        db.add(row)
    else:
        row.status = "ACTIVE"
    db.commit()
    return {"assignment_id": str(row.id), "user_id": str(user.id), "role_id": str(role.id), "status": row.status}


@router.post("/admin/identity/role-permission-sets")
def link_permission_set(payload: RolePermissionRequest, request: Request, db: Session = Depends(get_db)):
    admin = _admin_tenant(request, db)
    role = (
        db.query(RoleDefinition)
        .filter(RoleDefinition.id == payload.role_id, RoleDefinition.tenant_id == admin.tenant_id)
        .first()
    )
    permission_set = (
        db.query(PermissionSetDefinition)
        .filter(
            PermissionSetDefinition.id == payload.permission_set_id,
            PermissionSetDefinition.tenant_id == admin.tenant_id,
        )
        .first()
    )
    if role is None or permission_set is None:
        raise HTTPException(
            404,
            detail={
                "code": "PERMISSION_LINK_SCOPE_INVALID",
                "message": "Role and permission set must belong to this tenant",
            },
        )
    row = (
        db.query(RolePermissionSet)
        .filter_by(tenant_id=admin.tenant_id, role_id=role.id, permission_set_id=permission_set.id)
        .first()
    )
    if row is None:
        row = RolePermissionSet(
            id=uuid.uuid4(),
            tenant_id=admin.tenant_id,
            role_id=role.id,
            permission_set_id=permission_set.id,
            created_at=datetime.now(timezone.utc),
        )
        db.add(row)
        db.commit()
    return {"link_id": str(row.id), "role_id": str(role.id), "permission_set_id": str(permission_set.id)}


@router.patch("/admin/identity/users/{user_id}/status")
def update_user_status(user_id: uuid.UUID, payload: UserStatusRequest, request: Request, db: Session = Depends(get_db)):
    admin = _admin_tenant(request, db)
    user = db.query(AuthUser).filter(AuthUser.id == user_id, AuthUser.tenant_id == admin.tenant_id).first()
    if user is None:
        raise HTTPException(404, detail={"code": "USER_NOT_FOUND", "message": "User is not available for this tenant"})
    _guard_user_administration(admin, target=user, changes_access=True)
    previous_status = user.status
    now = datetime.now(timezone.utc)
    user.status = payload.status
    user.updated_at = now
    revoked = revoke_user_sessions(db, user.id, user.tenant_id) if payload.status != "ACTIVE" else 0
    change = team_notices.status_change(previous_status, user.status)
    if change:
        # The person, and for an administrator account the other administrators, are told by email.
        team_notices.queue_organization_change(db, admin, user, change, now=now)
    db.add(
        AuditEvent(
            id=uuid.uuid4(),
            tenant_id=admin.tenant_id,
            actor_ref=str(admin.id),
            action="USER_STATUS_CHANGED",
            entity_type="AuthUser",
            entity_id=user.id,
            details={"sessions_revoked": revoked, "source": "ADMIN_CONTROL_PLANE"},
            old_values={"status": previous_status},
            new_values={"status": user.status},
            created_at=now,
        )
    )
    db.commit()
    return {
        "user_id": str(user.id),
        "business_id": user.business_id,
        "tenant_id": str(user.tenant_id),
        "status": user.status,
    }


@router.post("/admin/identity/users/{user_id}/mfa-reset")
def reset_user_mfa(user_id: uuid.UUID, payload: MfaResetRequest, request: Request, db: Session = Depends(get_db)):
    """Remove a user's authenticator after they lost it (and their recovery codes). They set up a new one at their
    next sign-in. A customer administrator cannot reset their own MFA or a platform account's."""
    from backend.app import mfa

    admin = _admin_tenant(request, db)
    user = db.query(AuthUser).filter(AuthUser.id == user_id, AuthUser.tenant_id == admin.tenant_id).first()
    user = ensure_user_visible(admin, user)
    _guard_user_administration(admin, target=user, changes_access=True)
    now = datetime.now(timezone.utc)
    revoked = mfa.reset(db, user, now)
    team_notices.queue_organization_change(db, admin, user, TEAM_MFA_RESET, now=now)
    db.add(
        AuditEvent(
            id=uuid.uuid4(),
            tenant_id=admin.tenant_id,
            actor_ref=str(admin.id),
            action="USER_MFA_RESET",
            entity_type="AuthUser",
            entity_id=user.id,
            details={"reason": payload.reason.strip(), "sessions_revoked": revoked, "source": "ADMIN_CONTROL_PLANE"},
            created_at=now,
        )
    )
    db.commit()
    return {
        "user_id": str(user.id),
        "business_id": user.business_id,
        "status": "MFA_RESET",
        "sessions_revoked": revoked,
    }


@router.post("/admin/identity/users/{user_id}/erase")
def erase_user_personal_data(
    user_id: uuid.UUID, payload: PersonalDataErasureRequest, request: Request, db: Session = Depends(get_db)
):
    """Erase an offboarded person's personal data on their request (irreversible; docs/runbooks/DATA_REQUESTS.md)."""
    from backend.app.tenant_purge import PurgeFailed, erase_person

    admin = _admin_tenant(request, db)
    user = db.query(AuthUser).filter(AuthUser.id == user_id, AuthUser.tenant_id == admin.tenant_id).first()
    user = ensure_user_visible(admin, user)
    _guard_user_administration(admin, target=user, changes_access=True)
    try:
        result = erase_person(db, user, str(admin.id), payload.reason.strip())
    except PurgeFailed as exc:
        raise erasure_refused(str(exc)) from exc
    db.commit()
    return {**result, "business_id": user.business_id, "status": "ERASED"}


ROLE_NOT_ALLOWED = (
    "ROLE_NOT_ALLOWED",
    "Additional roles must be workflow roles (PMS / Signal Triage Lead, Quality Investigator, Risk Reviewer, "
    "Regulatory Reviewer, Quality Reviewer, Authorized Decision Maker, Leader), never an administrator role or the "
    "person's account role",
)


def _additional_roles(db: Session, admin, user: AuthUser) -> dict:
    """The person's account role, the workflow roles they hold besides it, and the ones they could be given."""
    from backend.app.access.permissions import normalize_role, role_of_user

    account = role_of_user(db, user)
    account_code = normalize_role(account)
    rows = (
        db.query(UserAdditionalRole)
        .filter(
            UserAdditionalRole.tenant_id == admin.tenant_id,
            UserAdditionalRole.user_id == user.id,
            UserAdditionalRole.status == "ACTIVE",
        )
        .all()
    )
    held = {normalize_role(row.role_code): row for row in rows}
    granters = {str(row.granted_by) for row in rows if row.granted_by}
    names = {}
    for granter in granters:
        try:
            granter_id = uuid.UUID(granter)
        except ValueError:
            continue
        person = db.query(AuthUser).filter(AuthUser.id == granter_id, AuthUser.tenant_id == admin.tenant_id).first()
        if person is not None and not is_hidden_from(admin, person):
            names[granter] = person.display_name
    return {
        "user_id": str(user.id),
        "business_id": user.business_id,
        "account_role": {"code": account_code, "label": role_label(account)},
        "additional_roles": [
            {
                "code": code,
                "label": role_label(code),
                "granted_at": held[code].granted_at,
                "granted_by_name": names.get(str(held[code].granted_by or "")),
            }
            for code in WORKFLOW_ROLES
            if code in held and code != account_code
        ],
        "available_roles": [
            {"code": code, "label": role_label(code)} for code in WORKFLOW_ROLES if code != account_code
        ],
    }


@router.get("/admin/identity/users/{user_id}/roles")
def user_roles(user_id: uuid.UUID, request: Request, db: Session = Depends(get_db)):
    """The workflow roles a person holds besides their account role (a small company's Investigator may also be
    its Risk Reviewer). What they may do is the union of all their roles."""
    admin = _admin_tenant(request, db)
    user = db.query(AuthUser).filter(AuthUser.id == user_id, AuthUser.tenant_id == admin.tenant_id).first()
    user = ensure_user_visible(admin, user)
    return _additional_roles(db, admin, user)


@router.put("/admin/identity/users/{user_id}/roles")
def set_user_roles(
    user_id: uuid.UUID, payload: AdditionalRolesRequest, request: Request, db: Session = Depends(get_db)
):
    """Set the complete list of a person's additional workflow roles: missing ones are granted, removed ones revoked
    (the row is kept as REVOKED). Each change is audited with the reason. Administrators cannot change their own."""
    from backend.app.access.permissions import normalize_role, role_of_user

    admin = _admin_tenant(request, db)
    user = db.query(AuthUser).filter(AuthUser.id == user_id, AuthUser.tenant_id == admin.tenant_id).first()
    user = ensure_user_visible(admin, user)
    _guard_user_administration(admin, target=user, changes_access=True)
    reason = payload.reason.strip()
    if len(reason) < 10:
        raise HTTPException(
            422, detail={"code": "REASON_REQUIRED", "message": "Give a reason of at least 10 characters"}
        )
    account_code = normalize_role(role_of_user(db, user))
    if account_code in {"PLATFORM_ADMIN", "CUSTOMER_ADMIN"} and payload.additional_roles:
        # Administrators stay outside the case workflow; removing roles granted earlier is still allowed.
        raise HTTPException(
            422,
            detail={
                "code": ROLE_NOT_ALLOWED[0],
                "message": "Administrator accounts cannot hold workflow roles; use a separate account for investigation work",
            },
        )
    wanted: list[str] = []
    for value in payload.additional_roles:
        code = normalize_role(value)
        if code not in WORKFLOW_ROLES or code == account_code:
            raise HTTPException(
                422, detail={"code": ROLE_NOT_ALLOWED[0], "message": ROLE_NOT_ALLOWED[1], "role": str(value)[:60]}
            )
        if code not in wanted:
            wanted.append(code)
    rows = {
        normalize_role(row.role_code): row
        for row in db.query(UserAdditionalRole).filter(
            UserAdditionalRole.tenant_id == admin.tenant_id, UserAdditionalRole.user_id == user.id
        )
    }
    now = datetime.now(timezone.utc)
    changes = []
    for code in wanted:
        row = rows.get(code)
        if row is not None and row.status == "ACTIVE":
            continue
        if row is None:
            db.add(
                UserAdditionalRole(
                    id=uuid.uuid4(),
                    tenant_id=admin.tenant_id,
                    user_id=user.id,
                    role_code=code,
                    status="ACTIVE",
                    reason=reason,
                    granted_by=str(admin.id),
                    granted_at=now,
                )
            )
        else:
            # Granted again after a revocation: the same row, with the new grant's details.
            row.status = "ACTIVE"
            row.reason = reason
            row.granted_by = str(admin.id)
            row.granted_at = now
            row.revoked_by = None
            row.revoked_at = None
        changes.append(("ROLE_GRANTED", code))
    for code, row in rows.items():
        if row.status == "ACTIVE" and code not in wanted:
            row.status = "REVOKED"
            row.reason = reason
            row.revoked_by = str(admin.id)
            row.revoked_at = now
            changes.append(("ROLE_REVOKED", code))
    if changes:
        team_notices.queue_organization_change(
            db,
            admin,
            user,
            TEAM_ROLE_CHANGED,
            now=now,
            roles_added=tuple(code for action, code in changes if action == "ROLE_GRANTED"),
            roles_removed=tuple(code for action, code in changes if action == "ROLE_REVOKED"),
        )
    for action, code in changes:
        db.add(
            AuditEvent(
                id=uuid.uuid4(),
                tenant_id=admin.tenant_id,
                actor_ref=str(admin.id),
                action=action,
                entity_type="AuthUser",
                entity_id=user.id,
                reason=reason,
                details={"role": code, "role_label": role_label(code), "source": "ADMIN_CONTROL_PLANE"},
                created_at=now,
            )
        )
    db.commit()
    return _additional_roles(db, admin, user)


DELIVERY_FAILED = "FAILED"
DELIVERY_FAILED_MESSAGE = (
    "The account was created, but the invitation email could not be delivered. Ask MDARIX support for an "
    "activation link to pass on to the person."
)


def _inviter(admin: AuthUser) -> str | None:
    """How an invitation names the administrator who sent it: by name; MDARIX staff are not named."""
    if _is_platform_admin(admin):
        return None
    return (admin.display_name or "").strip() or admin.username


def _send_invitation(user: AuthUser, token: str, organization: str | None, invited_by: str | None = None) -> str:
    """Email the activation link; the delivery result ("SENT", "NOT_CONFIGURED", or "FAILED").

    The account and its link are already committed (``issue_invitation`` commits), so a mail outage must not turn
    into an error that hides a created account: the failure is recorded (audit ``email_delivery``) and answered,
    and MDARIX support can issue a fresh activation link (``POST /api/v1/platform-admin/users/{id}/activation-link``).
    """
    try:
        return send_activation_email(user.username, token, organization or "", invited_by=invited_by)
    except EmailDeliveryError as exc:
        # No address in the log: the account id is enough to find the person.
        logger.warning("Invitation email for user %s was not delivered: %s", user.id, exc)
        return DELIVERY_FAILED


def _invitation_response(body: dict, delivery: str, token: str):
    """The answer to an invitation: 200 when the email went (or, locally, when there is no email server); 201 with
    ``delivery: "FAILED"`` and what to do next when the account exists but the email did not go out."""
    body = {
        **body,
        "email_delivery": delivery,
        # Local development shows the link's token instead of an email that never arrives.
        "development_token": _development_token(token) if delivery in {"NOT_CONFIGURED", DELIVERY_FAILED} else None,
    }
    if delivery != DELIVERY_FAILED:
        return body
    return JSONResponse(
        status_code=201,
        content={
            **body,
            "invitation_status": "NOT_SENT",
            "delivery": DELIVERY_FAILED,
            "message": DELIVERY_FAILED_MESSAGE,
        },
    )


@router.post("/admin/identity/users/{user_id}/reactivate")
def reactivate_user(user_id: uuid.UUID, request: Request, db: Session = Depends(get_db)):
    admin = _admin_tenant(request, db)
    user = db.query(AuthUser).filter(AuthUser.id == user_id, AuthUser.tenant_id == admin.tenant_id).first()
    if user is None:
        raise HTTPException(404, detail={"code": "USER_NOT_FOUND", "message": "User is not available for this tenant"})
    _guard_user_administration(admin, target=user)
    if (user.status or "").upper() != "OFFBOARDED":
        raise HTTPException(
            409, detail={"code": "USER_NOT_OFFBOARDED", "message": "Only an offboarded user can be reactivated"}
        )
    _enforce_invite_limits(db, user.tenant_id, user.role)
    now = datetime.now(timezone.utc)
    user.status = "INVITED"
    user.email_verified = False
    user.password_hash = _hash(secrets.token_urlsafe(48))
    user.updated_at = now
    membership = (
        db.query(TenantMembership)
        .filter(TenantMembership.tenant_id == user.tenant_id, TenantMembership.user_id == user.id)
        .first()
    )
    if membership is not None:
        membership.status = "INVITED"
        membership.updated_at = now
    token = issue_invitation(db, user.id, user.tenant_id, admin.id)
    delivery = _send_invitation(user, token, user.company, _inviter(admin))
    # Inviting a Customer Administrator is told to the other administrators (the invitation is its own email).
    team_notices.queue_organization_change(db, admin, user, TEAM_INVITED, now=now, tell_person=False)
    db.add(
        AuditEvent(
            id=uuid.uuid4(),
            tenant_id=user.tenant_id,
            actor_ref=str(admin.id),
            action="USER_REACTIVATED",
            entity_type="AuthUser",
            entity_id=user.id,
            details={"email_delivery": delivery, "source": "ADMIN_CONTROL_PLANE"},
            created_at=now,
        )
    )
    db.commit()
    return _invitation_response(
        {
            "user_id": str(user.id),
            "business_id": user.business_id,
            "email": user.username,
            "status": user.status,
            "invitation_status": "RESENT",
        },
        delivery,
        token,
    )


@router.get("/admin/identity/users")
def list_users(request: Request, db: Session = Depends(get_db)):
    admin = _admin_tenant(request, db)
    # MDARIX staff accounts in the tenant are listed for platform administrators only.
    rows = (
        db.query(AuthUser)
        .filter(AuthUser.tenant_id == admin.tenant_id, *visible_user_filters(admin))
        .order_by(AuthUser.username)
        .all()
    )
    return [
        {
            "id": str(row.id),
            "business_id": row.business_id,
            "email": row.username,
            "display_name": row.display_name,
            "company": row.company,
            "role": row.role,
            "role_label": role_label(row.role),
            "status": row.status,
            "tenant_id": str(row.tenant_id),
        }
        for row in rows
    ]


# Roles every tenant has. A tenant may also define its own (Roles & Access); anything else is refused, so a typo
# cannot create an account whose role means nothing.
STANDARD_ROLES = frozenset(
    {
        "VIEWER",
        "TRIAGE_LEAD",
        "INVESTIGATOR",
        "RISK_REVIEWER",
        "REGULATORY_REVIEWER",
        "REVIEWER",
        "APPROVER",
        "LEADER",
        "CUSTOMER_ADMIN",
    }
)


def _ensure_known_role(db: Session, tenant_id, role: str) -> None:
    from backend.app.access.permissions import normalize_role

    wanted = normalize_role(role)
    if wanted in STANDARD_ROLES or _is_platform_role(role):
        return  # platform roles are already limited to platform administrators by the guard
    custom = {
        normalize_role(name)
        for (name,) in db.query(RoleDefinition.name).filter(
            RoleDefinition.tenant_id == tenant_id, func.upper(RoleDefinition.status) == "ACTIVE"
        )
    }
    if wanted not in custom:
        raise HTTPException(
            422,
            detail={
                "code": "ROLE_NOT_RECOGNIZED",
                "message": "Choose one of the organization's roles (Viewer, PMS / Signal Triage Lead, Quality "
                "Investigator, Risk Reviewer, Regulatory Reviewer, Quality Reviewer, Authorized Decision Maker, "
                "Leader (Quality Manager), Customer Administrator, or an active custom role)",
            },
        )


@router.post("/admin/identity/users")
def create_user(payload: UserCreateRequest, request: Request, db: Session = Depends(get_db)):
    admin = _admin_tenant(request, db)
    target_tenant_id = _admin_target_tenant(admin, payload.target_tenant_id, payload.company, db)
    if db.query(Tenant).filter(Tenant.id == target_tenant_id, func.upper(Tenant.status) == "ACTIVE").first() is None:
        raise HTTPException(
            404, detail={"code": "TENANT_NOT_FOUND", "message": "Customer / Tenant ID is not an active tenant UUID"}
        )
    from backend.app.role_codes import canonical_stored_role

    role = canonical_stored_role(payload.role)
    _guard_user_administration(admin, new_role=role)
    _ensure_known_role(db, target_tenant_id, role)
    if role == "PLATFORM_ADMIN" and not _is_platform_admin(admin):
        raise HTTPException(
            403,
            detail={
                "code": "PLATFORM_ROLE_NOT_ALLOWED",
                "message": "Customer administrators cannot assign platform roles",
            },
        )
    if role == "PLATFORM_ADMIN" and target_tenant_id != admin.tenant_id:
        raise HTTPException(
            403,
            detail={
                "code": "PLATFORM_ROLE_NOT_ALLOWED",
                "message": "Platform roles are not assigned inside customer tenants",
            },
        )
    _enforce_invite_limits(db, target_tenant_id, role)
    email = payload.email.strip().lower()
    from backend.app.access.authz import lock_account_email

    lock_account_email(db, target_tenant_id, email)  # a second invitation of this address waits, then sees this one
    _ensure_email_not_used_elsewhere(db, email, target_tenant_id)
    if (
        db.query(AuthUser)
        .filter(
            AuthUser.tenant_id == target_tenant_id,
            AuthUser.username == email,
            func.upper(AuthUser.status) != "OFFBOARDED",
        )
        .first()
    ):
        raise HTTPException(
            409, detail={"code": "ACCOUNT_EXISTS", "message": "A user with this email already exists in this tenant"}
        )
    now = datetime.now(timezone.utc)
    row = (
        db.query(AuthUser)
        .filter(
            AuthUser.tenant_id == target_tenant_id,
            AuthUser.username == email,
            func.upper(AuthUser.status) == "OFFBOARDED",
        )
        .first()
    )
    if row is None:
        row = AuthUser(
            id=uuid.uuid4(),
            tenant_id=target_tenant_id,
            username=email,
            display_name=payload.display_name.strip(),
            company=payload.company.strip(),
            password_hash=_hash(secrets.token_urlsafe(48)),
            role=role,
            status="INVITED",
            email_verified=False,
            created_at=now,
            updated_at=now,
        )
        db.add(row)
        db.flush()
        db.add(
            TenantMembership(
                id=uuid.uuid4(),
                tenant_id=target_tenant_id,
                user_id=row.id,
                status="INVITED",
                is_default=True,
                created_at=now,
                updated_at=now,
            )
        )
    else:
        row.display_name = payload.display_name.strip()
        row.company = payload.company.strip()
        row.role = role
        row.password_hash = _hash(secrets.token_urlsafe(48))
        row.status = "INVITED"
        row.email_verified = False
        row.updated_at = now
        membership = (
            db.query(TenantMembership)
            .filter(TenantMembership.tenant_id == target_tenant_id, TenantMembership.user_id == row.id)
            .first()
        )
        if membership is not None:
            membership.status = "INVITED"
            membership.updated_at = now
    token = issue_invitation(db, row.id, row.tenant_id, admin.id)
    delivery = _send_invitation(row, token, payload.company.strip(), _inviter(admin))
    team_notices.queue_organization_change(db, admin, row, TEAM_INVITED, now=now, tell_person=False)
    db.add(
        AuditEvent(
            id=uuid.uuid4(),
            tenant_id=target_tenant_id,
            actor_ref=str(admin.id),
            action="USER_INVITATION_SENT",
            entity_type="AuthUser",
            entity_id=row.id,
            details={"role": role, "email_delivery": delivery, "source": "ADMIN_CONTROL_PLANE"},
            created_at=now,
        )
    )
    db.commit()
    return _invitation_response(
        {
            "id": str(row.id),
            "business_id": row.business_id,
            "email": row.username,
            "display_name": row.display_name,
            "tenant_id": str(row.tenant_id),
            "role": row.role,
            "status": row.status,
            "invitation_status": "SENT",
        },
        delivery,
        token,
    )


@router.post("/admin/identity/users/password-reset")
def admin_password_reset(payload: PasswordActionRequest, request: Request, db: Session = Depends(get_db)):
    admin = _admin_tenant(request, db)
    row = (
        db.query(AuthUser)
        .filter(AuthUser.tenant_id == admin.tenant_id, AuthUser.username == payload.email.strip().lower())
        .first()
    )
    if row is None or is_hidden_from(admin, row):
        return {"status": "RESET_REQUEST_ACCEPTED", "email_delivery": "NOT_SENT"}
    token = issue_reset(db, row.id, row.tenant_id, admin.id)
    delivery = send_password_reset_email(row.username, token)
    db.add(
        AuditEvent(
            id=uuid.uuid4(),
            tenant_id=admin.tenant_id,
            actor_ref=str(admin.id),
            action="PASSWORD_RESET_REQUESTED",
            entity_type="AuthUser",
            entity_id=row.id,
            details={"email_delivery": delivery, "source": "ADMIN_CONTROL_PLANE"},
            created_at=datetime.now(timezone.utc),
        )
    )
    db.commit()
    return {
        "status": "RESET_REQUEST_ACCEPTED",
        "email_delivery": delivery,
        "development_token": _development_token(token) if delivery == "NOT_CONFIGURED" else None,
    }


@router.get("/admin/identity/persona-assignments")
def list_persona_assignments(request: Request, db: Session = Depends(get_db)):
    admin = _admin_tenant(request, db)
    query = db.query(PersonaAssignment).filter(PersonaAssignment.tenant_id == admin.tenant_id)
    hidden = hidden_platform_user_ids(db, admin, admin.tenant_id)
    if hidden is not None:
        query = query.filter(PersonaAssignment.user_id.notin_(hidden))
    rows = query.order_by(PersonaAssignment.user_id, PersonaAssignment.persona_code).all()
    return [
        {
            "id": str(row.id),
            "user_id": str(row.user_id),
            "tenant_id": str(row.tenant_id),
            "persona_code": row.persona_code,
            "status": row.status,
        }
        for row in rows
    ]


@router.get("/admin/identity/role-assignments")
def list_role_assignments(request: Request, db: Session = Depends(get_db)):
    admin = _admin_tenant(request, db)
    query = db.query(RoleAssignment).filter(RoleAssignment.tenant_id == admin.tenant_id)
    hidden = hidden_platform_user_ids(db, admin, admin.tenant_id)
    if hidden is not None:
        query = query.filter(RoleAssignment.user_id.notin_(hidden))
    rows = query.order_by(RoleAssignment.user_id).all()
    return [
        {
            "id": str(row.id),
            "user_id": str(row.user_id),
            "role_id": str(row.role_id),
            "tenant_id": str(row.tenant_id),
            "status": row.status,
        }
        for row in rows
    ]


@router.get("/admin/identity/role-permission-sets")
def list_role_permission_sets(request: Request, db: Session = Depends(get_db)):
    admin = _admin_tenant(request, db)
    rows = db.query(RolePermissionSet).filter(RolePermissionSet.tenant_id == admin.tenant_id).all()
    return [
        {
            "id": str(row.id),
            "role_id": str(row.role_id),
            "permission_set_id": str(row.permission_set_id),
            "tenant_id": str(row.tenant_id),
        }
        for row in rows
    ]


@router.patch("/admin/identity/roles/{role_id}/status")
def update_role_status(role_id: uuid.UUID, payload: StatusRequest, request: Request, db: Session = Depends(get_db)):
    admin = _admin_tenant(request, db)
    row = (
        db.query(RoleDefinition)
        .filter(RoleDefinition.id == role_id, RoleDefinition.tenant_id == admin.tenant_id)
        .first()
    )
    if row is None:
        raise HTTPException(404, detail={"code": "ROLE_NOT_FOUND", "message": "Role is not available for this tenant"})
    row.status = payload.status
    row.updated_at = datetime.now(timezone.utc)
    _audit_configuration(db, admin, "ROLE_STATUS_CHANGED", "RoleDefinition", row.id, row.version)
    db.commit()
    return {"id": str(row.id), "status": row.status, "version": row.version}


@router.patch("/admin/identity/permission-sets/{permission_set_id}/status")
def update_permission_status(
    permission_set_id: uuid.UUID, payload: StatusRequest, request: Request, db: Session = Depends(get_db)
):
    admin = _admin_tenant(request, db)
    row = (
        db.query(PermissionSetDefinition)
        .filter(PermissionSetDefinition.id == permission_set_id, PermissionSetDefinition.tenant_id == admin.tenant_id)
        .first()
    )
    if row is None:
        raise HTTPException(
            404,
            detail={"code": "PERMISSION_SET_NOT_FOUND", "message": "Permission set is not available for this tenant"},
        )
    row.status = payload.status
    row.updated_at = datetime.now(timezone.utc)
    _audit_configuration(db, admin, "PERMISSION_SET_STATUS_CHANGED", "PermissionSetDefinition", row.id, row.version)
    db.commit()
    return {"id": str(row.id), "status": row.status, "version": row.version}


@router.patch("/admin/identity/memberships/{membership_id}/status")
def update_membership_status(
    membership_id: uuid.UUID, payload: StatusRequest, request: Request, db: Session = Depends(get_db)
):
    admin = _admin_tenant(request, db)
    row = (
        db.query(TenantMembership)
        .filter(TenantMembership.id == membership_id, TenantMembership.tenant_id == admin.tenant_id)
        .first()
    )
    if row is None or _belongs_to_hidden_account(db, admin, row.user_id):
        raise HTTPException(
            404, detail={"code": "MEMBERSHIP_NOT_FOUND", "message": "Membership is not available for this tenant"}
        )
    row.status = payload.status
    row.updated_at = datetime.now(timezone.utc)
    _audit_configuration(db, admin, "MEMBERSHIP_STATUS_CHANGED", "TenantMembership", row.id, "v1")
    db.commit()
    return {"id": str(row.id), "status": row.status}


@router.patch("/admin/identity/persona-assignments/{assignment_id}/status")
def update_persona_status(
    assignment_id: uuid.UUID, payload: StatusRequest, request: Request, db: Session = Depends(get_db)
):
    admin = _admin_tenant(request, db)
    row = (
        db.query(PersonaAssignment)
        .filter(PersonaAssignment.id == assignment_id, PersonaAssignment.tenant_id == admin.tenant_id)
        .first()
    )
    if row is None or _belongs_to_hidden_account(db, admin, row.user_id):
        raise HTTPException(
            404,
            detail={
                "code": "PERSONA_ASSIGNMENT_NOT_FOUND",
                "message": "Persona assignment is not available for this tenant",
            },
        )
    row.status = payload.status
    row.updated_at = datetime.now(timezone.utc)
    _audit_configuration(db, admin, "PERSONA_ASSIGNMENT_STATUS_CHANGED", "PersonaAssignment", row.id, "v1")
    db.commit()
    return {"id": str(row.id), "status": row.status, "persona_code": row.persona_code}


@router.patch("/admin/identity/role-assignments/{assignment_id}/status")
def update_role_assignment_status(
    assignment_id: uuid.UUID, payload: StatusRequest, request: Request, db: Session = Depends(get_db)
):
    admin = _admin_tenant(request, db)
    row = (
        db.query(RoleAssignment)
        .filter(RoleAssignment.id == assignment_id, RoleAssignment.tenant_id == admin.tenant_id)
        .first()
    )
    if row is None or _belongs_to_hidden_account(db, admin, row.user_id):
        raise HTTPException(
            404,
            detail={"code": "ROLE_ASSIGNMENT_NOT_FOUND", "message": "Role assignment is not available for this tenant"},
        )
    was_active, active = str(row.status).upper() == "ACTIVE", str(payload.status).upper() == "ACTIVE"
    if active and not was_active:
        # Switching an assignment on is an assignment (R11); switching it off always removes access, so is allowed.
        person = db.query(AuthUser).filter(AuthUser.id == row.user_id, AuthUser.tenant_id == admin.tenant_id).first()
        role = db.query(RoleDefinition).filter(RoleDefinition.id == row.role_id).first()
        if person is not None and role is not None:
            _guard_custom_role_assignment(admin, person, role)
    row.status = payload.status
    row.updated_at = datetime.now(timezone.utc)
    person = db.query(AuthUser).filter(AuthUser.id == row.user_id, AuthUser.tenant_id == admin.tenant_id).first()
    if person is not None and was_active != active:
        team_notices.queue_organization_change(
            db,
            admin,
            person,
            TEAM_ROLE_CHANGED,
            custom_roles_added=(row.role_id,) if active else (),
            custom_roles_removed=() if active else (row.role_id,),
        )
    _audit_configuration(db, admin, "ROLE_ASSIGNMENT_STATUS_CHANGED", "RoleAssignment", row.id, "v1")
    db.commit()
    return {"id": str(row.id), "status": row.status}


@router.get("/admin/identity/users/{user_id}/effective-access")
def user_effective_access(user_id: uuid.UUID, request: Request, db: Session = Depends(get_db)):
    admin = _admin_tenant(request, db)
    user = db.query(AuthUser).filter(AuthUser.id == user_id, AuthUser.tenant_id == admin.tenant_id).first()
    ensure_user_visible(admin, user)
    # An administrator's custom roles grant nothing (R11; permissions.role_of_user), so they are not listed as
    # access; any left from before 0.10.49 still show among the assignments, where they can be removed.
    assignments = (
        []
        if is_administrator_role(user.role)
        else db.query(RoleAssignment)
        .filter(
            RoleAssignment.user_id == user.id,
            RoleAssignment.tenant_id == admin.tenant_id,
            RoleAssignment.status == "ACTIVE",
        )
        .all()
    )
    roles = []
    for assignment in assignments:
        role = (
            db.query(RoleDefinition)
            .filter(RoleDefinition.id == assignment.role_id, RoleDefinition.tenant_id == admin.tenant_id)
            .first()
        )
        if role:
            roles.append(
                {
                    "id": str(role.id),
                    "code": role.code,
                    "name": role.name,
                    "version": role.version,
                    "status": role.status,
                }
            )
    personas = (
        db.query(PersonaAssignment)
        .filter(
            PersonaAssignment.user_id == user.id,
            PersonaAssignment.tenant_id == admin.tenant_id,
            PersonaAssignment.status == "ACTIVE",
        )
        .all()
    )
    return {
        "user_id": str(user.id),
        "business_id": user.business_id,
        "tenant_id": str(admin.tenant_id),
        "status": user.status,
        "roles": roles,
        "personas": [{"code": row.persona_code, "status": row.status} for row in personas],
    }


@router.get("/admin/identity/roles/{role_id}/permission-sets")
def role_permission_detail(role_id: uuid.UUID, request: Request, db: Session = Depends(get_db)):
    admin = _admin_tenant(request, db)
    role = (
        db.query(RoleDefinition)
        .filter(RoleDefinition.id == role_id, RoleDefinition.tenant_id == admin.tenant_id)
        .first()
    )
    if role is None:
        raise HTTPException(404, detail={"code": "ROLE_NOT_FOUND", "message": "Role is not available for this tenant"})
    links = (
        db.query(RolePermissionSet)
        .filter(RolePermissionSet.role_id == role.id, RolePermissionSet.tenant_id == admin.tenant_id)
        .all()
    )
    result = []
    for link in links:
        row = (
            db.query(PermissionSetDefinition)
            .filter(
                PermissionSetDefinition.id == link.permission_set_id,
                PermissionSetDefinition.tenant_id == admin.tenant_id,
            )
            .first()
        )
        if row:
            result.append(
                {
                    "id": str(row.id),
                    "code": row.code,
                    "version": row.version,
                    "status": row.status,
                    "object_permissions": row.object_permissions,
                    "field_permissions": row.field_permissions,
                    "action_permissions": row.action_permissions,
                }
            )
    return {"role_id": str(role.id), "role_code": role.code, "permission_sets": result}


@router.get("/admin/identity/roles")
def list_roles(request: Request, db: Session = Depends(get_db)):
    admin = _admin_tenant(request, db)
    rows = (
        db.query(RoleDefinition)
        .filter(RoleDefinition.tenant_id == admin.tenant_id)
        .order_by(RoleDefinition.code, RoleDefinition.version)
        .all()
    )
    return [
        {"id": str(row.id), "code": row.code, "name": row.name, "version": row.version, "status": row.status}
        for row in rows
    ]


@router.get("/admin/identity/permission-sets")
def list_permission_sets(request: Request, db: Session = Depends(get_db)):
    admin = _admin_tenant(request, db)
    rows = (
        db.query(PermissionSetDefinition)
        .filter(PermissionSetDefinition.tenant_id == admin.tenant_id)
        .order_by(PermissionSetDefinition.code, PermissionSetDefinition.version)
        .all()
    )
    return [
        {
            "id": str(row.id),
            "code": row.code,
            "version": row.version,
            "status": row.status,
            "object_permissions": row.object_permissions,
            "field_permissions": row.field_permissions,
            "action_permissions": row.action_permissions,
        }
        for row in rows
    ]


@router.get("/admin/identity/memberships")
def list_memberships(request: Request, db: Session = Depends(get_db)):
    admin = _admin_tenant(request, db)
    query = db.query(TenantMembership).filter(TenantMembership.tenant_id == admin.tenant_id)
    hidden = hidden_platform_user_ids(db, admin, admin.tenant_id)
    if hidden is not None:
        query = query.filter(TenantMembership.user_id.notin_(hidden))
    rows = query.all()
    return [
        {
            "id": str(row.id),
            "user_id": str(row.user_id),
            "tenant_id": str(row.tenant_id),
            "status": row.status,
            "is_default": row.is_default,
        }
        for row in rows
    ]
