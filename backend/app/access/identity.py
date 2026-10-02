"""Tenant identity administration: users, memberships, personas, roles and permission sets."""

import secrets
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func
from sqlalchemy.orm import Session

from access_control.personas import R1_PERSONAS as PERSONAS
from access_control.personas import get_persona
from auth.durable import issue_invitation, issue_reset, revoke_user_sessions
from auth.emailer import (
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
from backend.app.db.session import get_db
from backend.app.access.schemas import (
    MembershipRequest,
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
)
from backend.app.access.session import context

router = APIRouter(prefix="/api/v1", tags=["Access Control"])


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
            "display_name": user.display_name,
            "email": user.username,
            "tenant_id": str(user.tenant_id),
            "role": user.role,
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
    row = db.query(RoleAssignment).filter_by(tenant_id=admin.tenant_id, user_id=user.id, role_id=role.id).first()
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
    return {"user_id": str(user.id), "tenant_id": str(user.tenant_id), "status": user.status}


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
    try:
        delivery = send_activation_email(user.username, token, user.company)
    except EmailDeliveryError as exc:
        db.rollback()
        raise HTTPException(502, detail={"code": "SMTP_DELIVERY_FAILED", "message": str(exc)}) from exc
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
    return {
        "user_id": str(user.id),
        "email": user.username,
        "status": user.status,
        "invitation_status": "RESENT",
        "email_delivery": delivery,
        "development_token": _development_token(token) if delivery == "NOT_CONFIGURED" else None,
    }


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
            "email": row.username,
            "display_name": row.display_name,
            "company": row.company,
            "role": row.role,
            "status": row.status,
            "tenant_id": str(row.tenant_id),
        }
        for row in rows
    ]


@router.post("/admin/identity/users")
def create_user(payload: UserCreateRequest, request: Request, db: Session = Depends(get_db)):
    admin = _admin_tenant(request, db)
    target_tenant_id = _admin_target_tenant(admin, payload.target_tenant_id, payload.company, db)
    if db.query(Tenant).filter(Tenant.id == target_tenant_id, func.upper(Tenant.status) == "ACTIVE").first() is None:
        raise HTTPException(
            404, detail={"code": "TENANT_NOT_FOUND", "message": "Customer / Tenant ID is not an active tenant UUID"}
        )
    role = payload.role.strip().upper()
    _guard_user_administration(admin, new_role=role)
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
    try:
        delivery = send_activation_email(row.username, token, payload.company.strip())
    except EmailDeliveryError as exc:
        db.rollback()
        raise HTTPException(502, detail={"code": "SMTP_DELIVERY_FAILED", "message": str(exc)}) from exc
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
    return {
        "id": str(row.id),
        "email": row.username,
        "display_name": row.display_name,
        "tenant_id": str(row.tenant_id),
        "role": row.role,
        "status": row.status,
        "invitation_status": "SENT",
        "email_delivery": delivery,
        "development_token": _development_token(token) if delivery == "NOT_CONFIGURED" else None,
    }


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
    row.status = payload.status
    row.updated_at = datetime.now(timezone.utc)
    _audit_configuration(db, admin, "ROLE_ASSIGNMENT_STATUS_CHANGED", "RoleAssignment", row.id, "v1")
    db.commit()
    return {"id": str(row.id), "status": row.status}


@router.get("/admin/identity/users/{user_id}/effective-access")
def user_effective_access(user_id: uuid.UUID, request: Request, db: Session = Depends(get_db)):
    admin = _admin_tenant(request, db)
    user = db.query(AuthUser).filter(AuthUser.id == user_id, AuthUser.tenant_id == admin.tenant_id).first()
    ensure_user_visible(admin, user)
    assignments = (
        db.query(RoleAssignment)
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
