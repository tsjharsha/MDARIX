"""Signed-in user context: /me and /session endpoints."""

import os
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func
from sqlalchemy.orm import Session

from access_control.personas import get_persona
from access_control.policy import PermissionSet, Role, User, effective_permissions
from auth.service import auth_service
from backend.app.db.models.foundation import (
    FeatureEntitlement,
    PermissionSetDefinition,
    PersonaAssignment,
    PlanDefinition,
    RoleAssignment,
    RoleDefinition,
    RolePermissionSet,
    Tenant,
    TenantMembership,
    TenantPlanAssignment,
)
from backend.app.db.session import get_db
from backend.app.access.schemas import RoleSwitch, TenantSwitchRequest
from backend.app.access.authz import _authenticated_user, _is_customer_admin, _is_platform_admin

router = APIRouter(prefix="/api/v1", tags=["Access Control"])


@router.get("/me/context")
def context(request: Request, db: Session = Depends(get_db)):
    user = _authenticated_user(request, db)
    # Legacy AuthUser.role remains the compatibility default until every
    # existing tenant has durable role assignments. New assignments always
    # take precedence and are constrained to the authenticated tenant.
    role_name = user.role or "Viewer"
    role_version = "legacy"
    permission_sets = [PermissionSet("persisted", {})]
    try:
        membership = (
            db.query(TenantMembership)
            .filter(
                TenantMembership.tenant_id == user.tenant_id,
                TenantMembership.user_id == user.id,
                TenantMembership.status == "ACTIVE",
            )
            .first()
        )
        if membership is not None:
            assignments = (
                db.query(RoleAssignment)
                .filter(
                    RoleAssignment.tenant_id == user.tenant_id,
                    RoleAssignment.user_id == user.id,
                    RoleAssignment.status == "ACTIVE",
                )
                .all()
            )
            for assignment in assignments:
                role_row = (
                    db.query(RoleDefinition)
                    .filter(
                        RoleDefinition.tenant_id == user.tenant_id,
                        RoleDefinition.id == assignment.role_id,
                        RoleDefinition.status == "ACTIVE",
                    )
                    .first()
                )
                if role_row is None:
                    continue
                role_name = role_row.name
                role_version = role_row.version
                links = (
                    db.query(RolePermissionSet)
                    .filter(
                        RolePermissionSet.tenant_id == user.tenant_id,
                        RolePermissionSet.role_id == role_row.id,
                    )
                    .all()
                )
                permission_sets = []
                for link in links:
                    definition = (
                        db.query(PermissionSetDefinition)
                        .filter(
                            PermissionSetDefinition.tenant_id == user.tenant_id,
                            PermissionSetDefinition.id == link.permission_set_id,
                            PermissionSetDefinition.status == "ACTIVE",
                        )
                        .first()
                    )
                    if definition is not None:
                        permission_sets.append(
                            PermissionSet(
                                definition.code,
                                {
                                    **(definition.object_permissions or {}),
                                    **(definition.action_permissions or {}),
                                },
                            )
                        )
                break
    except Exception:
        # Keep the endpoint usable against pre-migration test doubles and
        # legacy databases; durable records are used whenever available.
        pass
    role = Role(str(user.tenant_id), role_name, permission_sets, role_version, "ACTIVE")
    persisted = User(str(user.tenant_id), str(user.id), user.display_name, [role], role.name)
    permissions = effective_permissions(persisted)
    personas = []
    try:
        assignments = (
            db.query(PersonaAssignment)
            .filter(
                PersonaAssignment.tenant_id == user.tenant_id,
                PersonaAssignment.user_id == user.id,
                PersonaAssignment.status == "ACTIVE",
            )
            .all()
        )
        personas = [{"code": row.persona_code, "label": get_persona(row.persona_code).label} for row in assignments]
    except Exception:
        personas = []
    return {
        "user_id": str(user.id),
        "display_name": user.display_name,
        "email": user.username,
        "tenant_id": str(user.tenant_id),
        "active_role": role.name,
        "role_version": role.version,
        "personas": personas,
        "permissions": permissions,
    }


@router.get("/session/context")
def session_context(request: Request, db: Session = Depends(get_db)):
    """Canonical server-derived identity, tenancy and authorization context.

    The client may use this for rendering, but every protected route still
    evaluates the authenticated request context server-side.  No tenant,
    role, menu, plan or license value is accepted from the request body or
    route slug.
    """
    user = _authenticated_user(request, db)
    base = context(request, db)
    memberships = []
    for membership in (
        db.query(TenantMembership)
        .filter(
            TenantMembership.user_id == user.id,
            TenantMembership.status == "ACTIVE",
        )
        .all()
    ):
        tenant = (
            db.query(Tenant).filter(Tenant.id == membership.tenant_id, func.upper(Tenant.status) == "ACTIVE").first()
        )
        if tenant is not None:
            memberships.append(
                {
                    "membership_id": str(membership.id),
                    "tenant_id": str(tenant.id),
                    "tenant_key": tenant.tenant_key,
                    "tenant_name": tenant.name,
                    "is_default": bool(membership.is_default),
                }
            )

    assignment = (
        db.query(TenantPlanAssignment)
        .join(PlanDefinition, PlanDefinition.id == TenantPlanAssignment.plan_id)
        .filter(
            TenantPlanAssignment.tenant_id == user.tenant_id,
            TenantPlanAssignment.status == "ACTIVE",
            PlanDefinition.status == "ACTIVE",
        )
        .first()
    )
    plan = None
    entitlements = []
    if assignment is not None:
        plan_row = db.query(PlanDefinition).filter(PlanDefinition.id == assignment.plan_id).first()
        if plan_row is not None:
            plan = {"id": str(plan_row.id), "code": plan_row.code, "name": plan_row.name, "version": plan_row.version}
            entitlements = [
                {"feature_code": item.feature_code, "enabled": bool(item.enabled), "limits": item.limits or {}}
                for item in db.query(FeatureEntitlement)
                .filter(
                    FeatureEntitlement.plan_id == plan_row.id,
                    FeatureEntitlement.status == "ACTIVE",
                )
                .all()
            ]

    platform = _is_platform_admin(user)
    customer = _is_customer_admin(user)
    allowed_menu = (
        ["home", "products", "investigations", "evidence", "decision-center", "assurance", "audit", "admin"]
        if platform
        else [
            "home",
            "products",
            "investigations",
            "evidence",
            "decision-center",
            "assurance",
            "audit",
            "customer-admin",
        ]
        if customer
        else ["home", "products", "investigations", "evidence", "decision-center", "assurance", "audit"]
    )
    tenant = db.query(Tenant).filter(Tenant.id == user.tenant_id).first()
    license_state = (
        "ACTIVE" if tenant is not None and tenant.status == "active" and assignment is not None else "INACTIVE"
    )
    return {
        **base,
        "memberships": memberships,
        "current_tenant": next(
            (item for item in memberships if item["tenant_id"] == str(user.tenant_id)),
            {"tenant_id": str(user.tenant_id)},
        ),
        "plan": plan,
        "license": {"state": license_state, "effective": license_state == "ACTIVE"},
        "entitlements": entitlements,
        "branding": {"name": tenant.name if tenant is not None else "MDARIX", "logo_url": None, "theme": "mdarix-teal"},
        "feature_toggles": {item["feature_code"]: item["enabled"] for item in entitlements},
        "allowed_menu": allowed_menu,
        "allowed_actions": base.get("permissions", {}),
        "policy_version": base.get("role_version", "legacy"),
        "environment": os.getenv("MDARIX_ENV", "development"),
    }


@router.post("/me/active-role")
def active_role(request: RoleSwitch, http_request: Request, db: Session = Depends(get_db)):
    user = _authenticated_user(http_request, db)
    if request.role != user.role:
        raise HTTPException(
            403,
            detail={"code": "ROLE_NOT_ASSIGNED", "message": "Requested role is not assigned to the authenticated user"},
        )
    return context(http_request, db)


@router.post("/me/tenant-context")
def switch_tenant(payload: TenantSwitchRequest, request: Request, db: Session = Depends(get_db)):
    user = _authenticated_user(request, db)
    membership = (
        db.query(TenantMembership)
        .filter(
            TenantMembership.user_id == user.id,
            TenantMembership.tenant_id == payload.tenant_id,
            TenantMembership.status == "ACTIVE",
        )
        .first()
    )
    if membership is None:
        raise HTTPException(
            403,
            detail={"code": "TENANT_MEMBERSHIP_REQUIRED", "message": "Active membership is required for this tenant"},
        )
    token = request.cookies.get("mdarix_session", "")
    try:
        auth_service.switch_tenant(token, str(payload.tenant_id))
    except ValueError as exc:
        raise HTTPException(401, detail={"code": "UNAUTHENTICATED", "message": "Authentication required"}) from exc
    return {"status": "SWITCHED", "tenant_id": str(payload.tenant_id)}


@router.get("/me/entitlements/{feature_code}")
def entitlement(feature_code: str, request: Request, db: Session = Depends(get_db)):
    user = _authenticated_user(request, db)
    now = datetime.now(timezone.utc)
    row = (
        db.query(TenantPlanAssignment)
        .join(PlanDefinition, PlanDefinition.id == TenantPlanAssignment.plan_id)
        .join(FeatureEntitlement, FeatureEntitlement.plan_id == PlanDefinition.id)
        .filter(
            TenantPlanAssignment.tenant_id == user.tenant_id,
            TenantPlanAssignment.status == "ACTIVE",
            PlanDefinition.status == "ACTIVE",
            FeatureEntitlement.feature_code == feature_code,
            FeatureEntitlement.status == "ACTIVE",
            FeatureEntitlement.enabled == True,
            TenantPlanAssignment.effective_from <= now,
        )
        .first()
    )
    return {
        "feature": feature_code,
        "entitled": row is not None,
        "limits": (row[0].limits if isinstance(row, tuple) else row.limits) if row else {},
    }
