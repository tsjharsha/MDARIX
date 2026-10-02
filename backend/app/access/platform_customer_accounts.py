"""Platform administration of customers as accounts: one row per customer, and adding a tenant to a customer.

A Customer is the legal and commercial parent; a Tenant is the operational and data-isolation boundary. One
customer owns one or more tenants (for example a production tenant per region and a validation tenant). Each
tenant has its own plan, environments, users and Customer Administrators; nothing is shared between two tenants
because they belong to the same customer.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from backend.app.access.authz import _require_platform_admin
from backend.app.access.common import _development_token
from backend.app.access.platform_customer_admins import (
    ROLE,
    _row,
    create_customer_admin,
)
from backend.app.access.schemas import TenantAddRequest
from backend.app.customer_lifecycle import build_tenant_for_customer, shared_data_plane
from backend.app.db.models.customer_lifecycle import Customer, TenantEnvironment
from backend.app.db.models.foundation import AuditEvent, AuthUser, PlanDefinition, Tenant, TenantPlanAssignment
from backend.app.db.session import get_db

router = APIRouter(prefix="/api/v1", tags=["Access Control"])

# A tenant can be added only while the customer relationship is running.
CUSTOMER_STATES_ACCEPTING_TENANTS = {"ACTIVE", "EXPIRING_SOON"}


@router.get("/platform-admin/customer-accounts")
def list_customer_accounts(
    request: Request,
    q: str = "",
    status: str = "",
    plan: str = "",
    page: int = 1,
    page_size: int = 25,
    db: Session = Depends(get_db),
):
    """Every customer once, with its tenants (plan, data region, active administrators) underneath."""
    _require_platform_admin(request, db)
    page = max(1, page)
    page_size = min(100, max(1, page_size))
    query = db.query(Customer)
    if q.strip():
        like = f"%{q.strip().lower()}%"
        tenants_matching = db.query(Tenant.customer_id).filter(
            or_(func.lower(Tenant.tenant_key).like(like), func.lower(Tenant.display_name).like(like))
        )
        query = query.filter(
            or_(
                func.lower(Customer.display_name).like(like),
                func.lower(Customer.legal_name).like(like),
                func.lower(Customer.customer_identifier).like(like),
                Customer.id.in_(tenants_matching),
            )
        )
    if status.strip():
        query = query.filter(func.upper(Customer.lifecycle_status) == status.strip().upper())
    if plan.strip():
        on_plan = (
            db.query(Tenant.customer_id)
            .join(TenantPlanAssignment, TenantPlanAssignment.tenant_id == Tenant.id)
            .join(PlanDefinition, PlanDefinition.id == TenantPlanAssignment.plan_id)
            .filter(TenantPlanAssignment.status == "ACTIVE", func.lower(PlanDefinition.code) == plan.strip().lower())
        )
        query = query.filter(Customer.id.in_(on_plan))
    total = query.count()
    customers = (
        query.order_by(func.lower(Customer.display_name), Customer.customer_identifier)
        .offset((page - 1) * page_size)
        .limit(page_size)
        .all()
    )
    customer_ids = [customer.id for customer in customers]
    tenants = (
        db.query(Tenant).filter(Tenant.customer_id.in_(customer_ids)).order_by(Tenant.tenant_key).all()
        if customer_ids
        else []
    )
    tenant_ids = [tenant.id for tenant in tenants]
    plans: dict = {}
    admins: dict = {}
    if tenant_ids:
        # The newest active assignment is the tenant's plan.
        for tenant_id, name, code in (
            db.query(TenantPlanAssignment.tenant_id, PlanDefinition.name, PlanDefinition.code)
            .join(PlanDefinition, PlanDefinition.id == TenantPlanAssignment.plan_id)
            .filter(TenantPlanAssignment.tenant_id.in_(tenant_ids), TenantPlanAssignment.status == "ACTIVE")
            .order_by(TenantPlanAssignment.effective_from.desc())
            .all()
        ):
            plans.setdefault(tenant_id, name or code)
        admins = dict(
            db.query(AuthUser.tenant_id, func.count(AuthUser.id))
            .filter(
                AuthUser.tenant_id.in_(tenant_ids),
                func.upper(AuthUser.role) == ROLE,
                func.upper(AuthUser.status) == "ACTIVE",
            )
            .group_by(AuthUser.tenant_id)
            .all()
        )
    by_customer: dict = {}
    for tenant in tenants:
        by_customer.setdefault(tenant.customer_id, []).append(
            {
                "id": str(tenant.id),
                "tenant_key": tenant.tenant_key,
                "tenant_identifier": tenant.tenant_identifier,
                "display_name": tenant.display_name or tenant.name,
                "status": tenant.status,
                "data_region": tenant.residency_region,
                "plan_name": plans.get(tenant.id),
                "active_admins": admins.get(tenant.id, 0),
            }
        )
    items = []
    for customer in customers:
        owned = by_customer.get(customer.id, [])
        items.append(
            {
                "id": str(customer.id),
                "customer_identifier": customer.customer_identifier,
                "name": customer.display_name or customer.legal_name,
                "legal_name": customer.legal_name,
                "country": customer.country,
                "status": customer.lifecycle_status,
                "created_at": customer.created_at.isoformat() if customer.created_at else None,
                "tenant_count": len(owned),
                "active_admins": sum(tenant["active_admins"] for tenant in owned),
                "tenants": owned,
            }
        )
    return {
        "items": items,
        "page": page,
        "page_size": page_size,
        "total": total,
        "pages": max(1, (total + page_size - 1) // page_size),
    }


@router.post("/platform-admin/customer-records/{customer_id}/tenants")
def add_tenant_to_customer(
    customer_id: uuid.UUID, payload: TenantAddRequest, request: Request, db: Session = Depends(get_db)
):
    """Add a tenant to an existing customer, with its plan, first environment and first Customer Administrator.

    The tenant is a separate data boundary: it starts with no users other than its own administrator, who is
    invited by email. Everything is created in one transaction, so a refusal leaves nothing behind.
    """
    platform_admin = _require_platform_admin(request, db)
    customer = db.query(Customer).filter(Customer.id == customer_id).first()
    if customer is None:
        raise HTTPException(404, detail={"code": "CUSTOMER_NOT_FOUND", "message": "Customer is not available"})
    if (customer.lifecycle_status or "").upper() not in CUSTOMER_STATES_ACCEPTING_TENANTS:
        raise HTTPException(
            409,
            detail={
                "code": "CUSTOMER_NOT_ACTIVE",
                "message": "A tenant can be added only to an active customer",
            },
        )
    key = payload.tenant_code.strip().upper()
    name = payload.tenant_name.strip()
    if db.query(Tenant.id).filter(Tenant.tenant_key == key).first() is not None:
        raise HTTPException(409, detail={"code": "TENANT_EXISTS", "message": "Tenant code already exists"})
    if (
        db.query(Tenant.id).filter(Tenant.customer_id == customer.id, func.lower(Tenant.name) == name.lower()).first()
        is not None
    ):
        raise HTTPException(
            409, detail={"code": "TENANT_NAME_EXISTS", "message": "This customer already has a tenant with this name"}
        )
    email = payload.admin_email.strip().lower()
    # A new tenant has no accounts yet; the same person may already administer another tenant (a separate account).
    plan = (
        db.query(PlanDefinition)
        .filter(PlanDefinition.id == payload.plan_id, func.upper(PlanDefinition.status) == "ACTIVE")
        .first()
    )
    if plan is None:
        raise HTTPException(422, detail={"code": "PLAN_NOT_PUBLISHED", "message": "Choose a published, active plan"})
    now = datetime.now(timezone.utc)
    region = payload.data_region.strip()
    tenant = build_tenant_for_customer(
        db=db,
        customer=customer,
        tenant_key=key,
        name=name,
        status="ACTIVE",
        now=now,
        region=region,
        residency_region=region,
    )
    tenant.provisioning_status = "ACTIVE"
    db.add(tenant)
    db.flush()
    db.add(shared_data_plane(tenant, now))
    # The plan belongs to this tenant only; the plan's shared limits are not changed.
    db.add(
        TenantPlanAssignment(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            plan_id=plan.id,
            status="ACTIVE",
            effective_from=now,
            effective_to=None,
            reason=payload.reason,
            created_at=now,
            updated_at=now,
        )
    )
    db.add(
        TenantEnvironment(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            environment_identifier=f"{payload.environment_type.lower()}-{key.lower()}",
            environment_type=payload.environment_type,
            region=region,
            residency_region=region,
            status="ACTIVE",
            provisioned_at=now,
            activated_at=now,
            created_at=now,
            updated_at=now,
        )
    )
    db.add(
        AuditEvent(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            actor_ref=str(platform_admin.id),
            action="TENANT_ADDED",
            entity_type="Tenant",
            entity_id=tenant.id,
            details={
                "reason": payload.reason,
                "source": "PLATFORM_ADMIN",
                "customer_identifier": customer.customer_identifier,
                "tenant_key": key,
                "plan_code": plan.code,
                "environment_type": payload.environment_type,
                "data_region": region,
            },
            created_at=now,
        )
    )
    db.flush()
    user, token, delivery = create_customer_admin(
        db,
        tenant=tenant,
        customer=customer,
        email=email,
        display_name=payload.admin_display_name,
        reason=payload.reason,
        platform_admin=platform_admin,
        now=now,
    )
    db.commit()
    return {
        "tenant": {
            "id": str(tenant.id),
            "customer_id": str(customer.id),
            "tenant_key": tenant.tenant_key,
            "tenant_identifier": tenant.tenant_identifier,
            "display_name": tenant.display_name,
            "status": tenant.status,
            "data_region": tenant.residency_region,
            "plan_code": plan.code,
            "environment_type": payload.environment_type,
        },
        "administrator": _row(user, tenant, customer, 0),
        "email_delivery": delivery,
        "development_token": _development_token(token) if delivery == "NOT_CONFIGURED" else None,
    }
