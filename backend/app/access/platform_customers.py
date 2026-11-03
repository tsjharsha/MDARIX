"""Platform administration: customer directory, customer records and Customer 360 tabs."""

import io
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import and_, false, func, or_, select
from sqlalchemy.orm import Session

from backend.app.downloads import attachment
from backend.app.customer_lifecycle import (
    CUSTOMER_STATUS_SOURCES,
    build_customer_tenant,
    effective_access,
    is_operator_customer,
    shared_data_plane,
)
from backend.app import csv_safe, support_access
from backend.app.db.models.customer_lifecycle import (
    Customer,
    IdentityProviderConfiguration,
    SupportAccessGrant,
    TenantEnvironment,
)
from backend.app.db.models.foundation import (
    AuditEvent,
    AuthUser,
    ConnectorConfiguration,
    FeatureEntitlement,
    PlanDefinition,
    Tenant,
    TenantMappingVersion,
    TenantMembership,
    TenantPlanAssignment,
)
from backend.app.db.models.stage2 import (
    SubscriptionLifecycle,
)
from backend.app.db.session import get_db
from backend.app.sorting import order_query
from backend.app.access.schemas import (
    CustomerCreateRequest,
    CustomerImportRequest,
    CustomerLifecycleRequest,
    CustomerUpdateRequest,
)
from backend.app.access.authz import _require_platform_admin

router = APIRouter(prefix="/api/v1", tags=["Access Control"])


@router.post("/platform-admin/customers")
def create_customer(payload: CustomerCreateRequest, request: Request, db: Session = Depends(get_db)):
    admin = _require_platform_admin(request, db)
    key = payload.tenant_code.strip().upper()
    if db.query(Tenant).filter(Tenant.tenant_key == key).first():
        raise HTTPException(409, detail={"code": "TENANT_EXISTS", "message": "Tenant code already exists"})
    now = datetime.now(timezone.utc)
    customer, tenant = build_customer_tenant(
        db=db, tenant_key=key, name=payload.company_name, status=payload.status, now=now
    )
    db.add(customer)
    db.add(tenant)
    db.flush()
    db.add(shared_data_plane(tenant, now))
    plan = (
        db.query(PlanDefinition)
        .filter(PlanDefinition.code == payload.plan_code, PlanDefinition.status == "ACTIVE")
        .first()
    )
    if plan is None:
        plan = PlanDefinition(
            id=uuid.uuid4(),
            code=payload.plan_code,
            name=payload.plan_code.replace("_", " ").title(),
            description="Day 35 platform-created test plan",
            version="v1",
            status="ACTIVE",
            effective_from=now,
            effective_to=None,
            created_at=now,
            updated_at=now,
        )
        db.add(plan)
        db.flush()
    db.add(
        TenantPlanAssignment(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            plan_id=plan.id,
            status="ACTIVE",
            effective_from=now,
            effective_to=None,
            reason=payload.notes or "Platform Admin customer provisioning",
            # The limits set for this customer belong to its tenant, not to the plan other customers share.
            limits={
                "licensed_users_limit": payload.licensed_users_limit,
                "customer_admin_limit": payload.customer_admin_limit,
                "connector_limit": payload.connector_limit,
            },
            created_at=now,
            updated_at=now,
        )
    )
    # A plan that has no limits yet starts with this customer's as its defaults; an existing plan's limits are
    # shared by its other customers and are never changed here.
    for feature_code, limits in {
        "ADMIN_CONTROL_PLANE": {
            "licensed_users_limit": payload.licensed_users_limit,
            "customer_admin_limit": payload.customer_admin_limit,
            "connector_limit": payload.connector_limit,
        },
        "CONNECTOR_CONFIGURATION": {"connector_limit": payload.connector_limit},
    }.items():
        existing = (
            db.query(FeatureEntitlement)
            .filter(FeatureEntitlement.plan_id == plan.id, FeatureEntitlement.feature_code == feature_code)
            .first()
        )
        if existing is None:
            db.add(
                FeatureEntitlement(
                    id=uuid.uuid4(),
                    plan_id=plan.id,
                    feature_code=feature_code,
                    enabled=True,
                    limits=limits,
                    status="ACTIVE",
                    created_at=now,
                    updated_at=now,
                )
            )
    db.add(
        AuditEvent(
            id=uuid.uuid4(),
            tenant_id=admin.tenant_id,
            actor_ref=str(admin.id),
            action="CUSTOMER_CREATED",
            entity_type="Tenant",
            entity_id=tenant.id,
            details={
                "tenant_key": key,
                "plan_code": payload.plan_code,
                "licensed_users_limit": payload.licensed_users_limit,
                "customer_admin_limit": payload.customer_admin_limit,
            },
            created_at=now,
        )
    )
    db.commit()
    return {
        "id": str(tenant.id),
        "business_id": tenant.business_id,
        "customer_id": str(customer.id),
        "customer_business_id": customer.business_id,
        "customer_identifier": customer.customer_identifier,
        "tenant_key": tenant.tenant_key,
        "tenant_identifier": tenant.tenant_identifier,
        "name": tenant.name,
        "status": tenant.status,
        "plan_code": payload.plan_code,
        "limits": {
            "licensed_users_limit": payload.licensed_users_limit,
            "customer_admin_limit": payload.customer_admin_limit,
            "connector_limit": payload.connector_limit,
        },
    }


@router.post("/platform-admin/customers/import")
def import_customers(payload: CustomerImportRequest, request: Request, db: Session = Depends(get_db)):
    """Validate or import a bounded customer CSV batch through the normal provisioning rules."""
    _require_platform_admin(request, db)
    seen: set[str] = set()
    results = []
    for row in payload.rows:
        key = row.tenant_code.strip().upper()
        if key in seen:
            results.append({"tenant_code": key, "status": "REJECTED", "error": "Duplicate tenant code in import"})
            continue
        seen.add(key)
        if db.query(Tenant).filter(Tenant.tenant_key == key).first():
            results.append({"tenant_code": key, "status": "REJECTED", "error": "Tenant code already exists"})
            continue
        results.append({"tenant_code": key, "status": "VALIDATED", "company_name": row.company_name})
    if payload.dry_run or any(item["status"] == "REJECTED" for item in results):
        return {"dry_run": payload.dry_run, "imported": 0, "results": results}
    imported = 0
    for row in payload.rows:
        result = create_customer(row, request, db)
        imported += 1
        for item in results:
            if item["tenant_code"] == row.tenant_code.strip().upper():
                item.update({"status": "IMPORTED", "id": result["id"], "business_id": result["business_id"]})
                break
    return {"dry_run": False, "imported": imported, "results": results}


@router.get("/platform/customers")
def platform_customer_directory(request: Request, db: Session = Depends(get_db)):
    return list_platform_customers(request, db)


@router.get("/platform/customers/{tenant_id}")
def platform_customer_detail(tenant_id: uuid.UUID, request: Request, db: Session = Depends(get_db)):
    return get_platform_customer(tenant_id, request, db)


def _subscription_sort_columns(seat_count) -> dict:
    """What each column of the tenant subscription list sorts on (``sort``; backend/app/sorting.py). ``name``,
    ``status``, ``created_at`` and ``tenant_key`` keep the meaning they always had."""

    def current_plan(column):
        return (
            select(column)
            .join(TenantPlanAssignment, TenantPlanAssignment.plan_id == PlanDefinition.id)
            .where(TenantPlanAssignment.tenant_id == Tenant.id, TenantPlanAssignment.status == "ACTIVE")
            # The id breaks ties, so sorting and the row shown pick the same assignment (the page lookup below).
            .order_by(TenantPlanAssignment.effective_from.desc(), TenantPlanAssignment.id.desc())
            .limit(1)
            .correlate(Tenant)
            .scalar_subquery()
        )

    def current_subscription(column):
        return (
            select(column)
            .where(SubscriptionLifecycle.tenant_id == Tenant.id)
            # The id breaks ties, so sorting and the row shown pick the same subscription (the page lookup below).
            .order_by(SubscriptionLifecycle.created_at.desc(), SubscriptionLifecycle.id.desc())
            .limit(1)
            .correlate(Tenant)
            .scalar_subquery()
        )

    last_activity = (
        select(func.max(AuditEvent.created_at))
        .where(AuditEvent.tenant_id == Tenant.id)
        .correlate(Tenant)
        .scalar_subquery()
    )
    shown_name = func.coalesce(Customer.display_name, Tenant.name)
    return {
        "name": [Tenant.name],
        "status": [Tenant.status],
        "created_at": [Tenant.created_at],
        "tenant_key": [Tenant.tenant_key],
        "business_id": [Tenant.business_id, Tenant.tenant_key],
        "tenant": [shown_name, Tenant.tenant_key],
        "legal_name": [Customer.legal_name],
        "customer_identifier": [Customer.customer_identifier],
        "customer_type": [Customer.customer_type],
        "country": [Customer.country],
        "industry": [Customer.industry],
        "data_region": [Tenant.residency_region],
        "plan": [current_plan(PlanDefinition.name), current_plan(PlanDefinition.code)],
        "plan_name": [current_plan(PlanDefinition.name)],
        "plan_code": [current_plan(PlanDefinition.code)],
        "period": [current_subscription(SubscriptionLifecycle.expires_at)],
        "expires_at": [current_subscription(SubscriptionLifecycle.expires_at)],
        "license_start": [current_subscription(SubscriptionLifecycle.starts_at)],
        "seats": [seat_count],
        "seat_usage": [seat_count],
        "last_activity": [last_activity],
    }


@router.get("/platform-admin/customers")
def list_platform_customers(request: Request, db: Session = Depends(get_db)):
    """Return tenant administration metadata only; never customer business data."""
    _require_platform_admin(request, db)
    params = request.query_params
    query = (params.get("q") or "").strip().lower()
    status = (params.get("status") or "").strip().upper()
    country = (params.get("country") or "").strip().lower()
    industry = (params.get("industry") or "").strip().lower()
    environment = (params.get("environment") or "").strip().upper()
    data_region = (params.get("data_region") or "").strip().lower()
    plan = (params.get("plan") or "").strip()
    license_status = (params.get("license") or params.get("license_status") or "").strip().upper()
    expiry_before = (params.get("expiry_before") or "").strip()
    expiry_after = (params.get("expiry_after") or "").strip()
    seat_status = (params.get("seat_status") or "").strip().upper()
    seat_min = (params.get("seat_min") or "").strip()
    seat_max = (params.get("seat_max") or "").strip()
    saved_view = (params.get("view") or "").strip().upper().replace(" ", "_")
    sort = params.get("sort", "name")
    order = params.get("order", "asc").lower()
    page = max(1, int(params.get("page", "1")))
    page_size = min(100, max(1, int(params.get("page_size", "25"))))
    rows = db.query(Tenant, Customer).outerjoin(Customer, Customer.id == Tenant.customer_id)
    if query:
        rows = rows.filter(
            func.lower(Tenant.name).contains(query)
            | func.lower(Tenant.tenant_key).contains(query)
            | func.lower(Customer.display_name).contains(query)
            | func.lower(Customer.customer_identifier).contains(query)
            | func.lower(Tenant.business_id).contains(query)
            | func.lower(Customer.business_id).contains(query)
        )
    if status:
        rows = rows.filter(func.upper(Tenant.status) == status)
    if country:
        rows = rows.filter(func.lower(Customer.country).contains(country))
    if industry:
        rows = rows.filter(func.lower(Customer.industry).contains(industry))
    if data_region:
        rows = rows.filter(func.lower(Tenant.residency_region).contains(data_region))
    if environment:
        matching_tenants = db.query(TenantEnvironment.tenant_id).filter(
            func.upper(TenantEnvironment.environment_type) == environment
        )
        rows = rows.filter(Tenant.id.in_(matching_tenants))
    if plan:
        matching_tenants = (
            db.query(TenantPlanAssignment.tenant_id)
            .join(PlanDefinition, PlanDefinition.id == TenantPlanAssignment.plan_id)
            .filter(func.lower(PlanDefinition.code).contains(plan.lower()), TenantPlanAssignment.status == "ACTIVE")
        )
        rows = rows.filter(Tenant.id.in_(matching_tenants))
    if expiry_before:
        try:
            expiry_date = datetime.fromisoformat(expiry_before).date()
            rows = rows.filter(
                Tenant.id.in_(
                    db.query(SubscriptionLifecycle.tenant_id).filter(SubscriptionLifecycle.expires_at <= expiry_date)
                )
            )
        except ValueError:
            raise HTTPException(
                422, detail={"code": "INVALID_EXPIRY_FILTER", "message": "expiry_before must be an ISO date"}
            )
    if expiry_after:
        try:
            expiry_date = datetime.fromisoformat(expiry_after).date()
            rows = rows.filter(
                Tenant.id.in_(
                    db.query(SubscriptionLifecycle.tenant_id).filter(SubscriptionLifecycle.expires_at >= expiry_date)
                )
            )
        except ValueError:
            raise HTTPException(
                422, detail={"code": "INVALID_EXPIRY_FILTER", "message": "expiry_after must be an ISO date"}
            )
    if license_status:
        rows = rows.filter(
            Tenant.id.in_(
                db.query(SubscriptionLifecycle.tenant_id).filter(
                    func.upper(SubscriptionLifecycle.status) == license_status
                )
            )
        )
    if saved_view == "ACTIVE":
        rows = rows.filter(func.upper(Tenant.status).in_(["ACTIVE", "PROVISIONED"]))
    elif saved_view == "SUSPENDED":
        rows = rows.filter(func.upper(Tenant.status) == "SUSPENDED")
    elif saved_view == "EXPIRED":
        rows = rows.filter(
            Tenant.id.in_(
                db.query(SubscriptionLifecycle.tenant_id).filter(func.upper(SubscriptionLifecycle.status) == "EXPIRED")
            )
        )
    elif saved_view == "EXPIRING_SOON":
        today = datetime.now(timezone.utc).date()
        rows = rows.filter(
            Tenant.id.in_(
                db.query(SubscriptionLifecycle.tenant_id).filter(
                    SubscriptionLifecycle.expires_at >= today,
                    SubscriptionLifecycle.expires_at <= today + timedelta(days=90),
                )
            )
        )
    elif saved_view == "TRIAL":
        rows = rows.filter(
            Tenant.id.in_(
                db.query(TenantPlanAssignment.tenant_id)
                .join(PlanDefinition, PlanDefinition.id == TenantPlanAssignment.plan_id)
                .filter(func.lower(PlanDefinition.code).contains("trial"), TenantPlanAssignment.status == "ACTIVE")
            )
        )
    elif saved_view == "DESIGN_PARTNERS":
        rows = rows.filter(func.lower(Customer.customer_type).contains("design"))
    # Seat filters are applied before counting and paging, so the total matches the rows sent.
    seat_count = (
        select(func.count(TenantMembership.id))
        .where(TenantMembership.tenant_id == Tenant.id)
        .correlate(Tenant)
        .scalar_subquery()
    )
    if seat_status in ("OVER", "NEAR_CAP"):
        # Plans carry no seat cap, so no tenant is over or near one (the rule these rows have always followed);
        # AVAILABLE therefore keeps every tenant.
        rows = rows.filter(false())
    try:
        if seat_min:
            rows = rows.filter(seat_count >= int(seat_min))
        if seat_max:
            rows = rows.filter(seat_count <= int(seat_max))
    except ValueError:
        raise HTTPException(
            422, detail={"code": "INVALID_SEAT_FILTER", "message": "seat_min and seat_max must be whole numbers"}
        )
    rows = order_query(
        rows, sort, order, columns=_subscription_sort_columns(seat_count), default=[Tenant.name], tiebreak=[Tenant.id]
    )
    total = rows.count()
    items = rows.offset((page - 1) * page_size).limit(page_size).all()
    # One query per kind of detail for the whole page (previously six queries per tenant). Each lookup keeps the
    # ordering the per-tenant query used, and the first row per tenant wins, so the output is unchanged.
    page_ids = [row.id for row, _ in items]

    def first_per_tenant(results) -> dict:
        found: dict = {}
        for item in results:
            found.setdefault(item.tenant_id, item)
        return found

    assignments = first_per_tenant(
        db.query(TenantPlanAssignment)
        .filter(TenantPlanAssignment.tenant_id.in_(page_ids), TenantPlanAssignment.status == "ACTIVE")
        .order_by(TenantPlanAssignment.effective_from.desc(), TenantPlanAssignment.id.desc())
        .all()
        if page_ids
        else []
    )
    plan_ids = {assignment.plan_id for assignment in assignments.values()}
    plans = (
        {plan.id: plan for plan in db.query(PlanDefinition).filter(PlanDefinition.id.in_(plan_ids)).all()}
        if plan_ids
        else {}
    )
    subscriptions = first_per_tenant(
        db.query(SubscriptionLifecycle)
        .filter(SubscriptionLifecycle.tenant_id.in_(page_ids))
        .order_by(SubscriptionLifecycle.created_at.desc(), SubscriptionLifecycle.id.desc())
        .all()
        if page_ids
        else []
    )
    admins = first_per_tenant(
        db.query(AuthUser)
        .filter(
            AuthUser.tenant_id.in_(page_ids),
            func.upper(AuthUser.role).in_(["CUSTOMER_ADMIN", "PLATFORM_ADMIN"]),
        )
        .order_by(AuthUser.created_at.asc())
        .all()
        if page_ids
        else []
    )
    last_activities = (
        dict(
            db.query(AuditEvent.tenant_id, func.max(AuditEvent.created_at))
            .filter(AuditEvent.tenant_id.in_(page_ids))
            .group_by(AuditEvent.tenant_id)
            .all()
        )
        if page_ids
        else {}
    )
    seat_counts = (
        dict(
            db.query(TenantMembership.tenant_id, func.count(TenantMembership.id))
            .filter(TenantMembership.tenant_id.in_(page_ids))
            .group_by(TenantMembership.tenant_id)
            .all()
        )
        if page_ids
        else {}
    )
    payload = []
    for row, customer in items:
        assignment = assignments.get(row.id)
        plan_row = plans.get(assignment.plan_id) if assignment else None
        subscription = subscriptions.get(row.id)
        primary_admin = admins.get(row.id)
        last_activity_at = last_activities.get(row.id)
        seat_usage = seat_counts.get(row.id, 0)
        seat_cap = getattr(plan_row, "seat_cap", None) or getattr(plan_row, "max_seats", None)
        health_status = "HEALTHY" if row.status in ("ACTIVE", "PROVISIONED") else "ATTENTION_REQUIRED"
        payload.append(
            {
                "id": str(row.id),
                "business_id": row.business_id,
                "customer_id": str(row.customer_id) if row.customer_id else None,
                "customer_business_id": customer.business_id if customer else None,
                "customer_identifier": customer.customer_identifier if customer else None,
                "tenant_key": row.tenant_key,
                "name": customer.display_name if customer else row.name,
                "legal_name": customer.legal_name if customer else None,
                "customer_type": customer.customer_type if customer else None,
                "country": customer.country if customer else None,
                "industry": customer.industry if customer else None,
                "data_region": row.residency_region,
                "status": row.status,
                "plan_code": plan_row.code if plan_row else None,
                "plan_name": plan_row.name if plan_row else None,
                "seat_usage": seat_usage,
                "seat_cap": seat_cap,
                "license_start": subscription.starts_at.isoformat()
                if subscription and getattr(subscription, "starts_at", None)
                else None,
                "expires_at": subscription.expires_at.isoformat() if subscription and subscription.expires_at else None,
                "primary_admin": primary_admin.display_name if primary_admin else None,
                "primary_admin_email": primary_admin.username if primary_admin else None,
                "last_activity": last_activity_at.isoformat() if last_activity_at else None,
                "created_by": customer.created_by if customer and getattr(customer, "created_by", None) else None,
                "health_status": health_status,
                "created_at": row.created_at.isoformat() if row.created_at else None,
                "actions": ["VIEW", "EDIT", "SUSPEND", "REACTIVATE"],
            }
        )
    if params.get("format") == "csv":
        fields = [
            "id",
            "business_id",
            "customer_id",
            "customer_business_id",
            "customer_identifier",
            "tenant_key",
            "name",
            "legal_name",
            "customer_type",
            "country",
            "industry",
            "data_region",
            "status",
            "plan_code",
            "plan_name",
            "seat_usage",
            "seat_cap",
            "license_start",
            "expires_at",
            "primary_admin",
            "primary_admin_email",
            "last_activity",
            "created_by",
            "health_status",
            "created_at",
        ]
        stream = io.StringIO()
        writer = csv_safe.writer(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows(
            {field: item.get(field, "") if item.get(field) is not None else "" for field in fields} for item in payload
        )
        return Response(
            content=stream.getvalue(),
            media_type="text/csv",
            headers={"Content-Disposition": attachment("mdarix-customers.csv")},
        )
    return {
        "items": payload,
        "page": page,
        "page_size": page_size,
        "total": total,
        "pages": (total + page_size - 1) // page_size,
        "sort": sort,
        "order": order,
    }


@router.get("/platform-admin/customers/{tenant_id}")
def get_platform_customer(tenant_id: uuid.UUID, request: Request, db: Session = Depends(get_db)):
    """Return Customer 360 administration metadata, never regulated records."""
    _require_platform_admin(request, db)
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if tenant is None:
        raise HTTPException(404, detail={"code": "TENANT_NOT_FOUND", "message": "Customer is not available"})
    membership_count = db.query(TenantMembership).filter(TenantMembership.tenant_id == tenant.id).count()
    admin_count = (
        db.query(AuthUser)
        .filter(
            AuthUser.tenant_id == tenant.id,
            func.upper(AuthUser.role).in_(["PLATFORM_ADMIN", "CUSTOMER_ADMIN"]),
        )
        .count()
    )
    connector_count = db.query(ConnectorConfiguration).filter(ConnectorConfiguration.tenant_id == tenant.id).count()
    mapping_count = db.query(TenantMappingVersion).filter(TenantMappingVersion.tenant_id == tenant.id).count()
    audit_count = db.query(AuditEvent).filter(AuditEvent.tenant_id == tenant.id).count()
    assignment = (
        db.query(TenantPlanAssignment)
        .filter(TenantPlanAssignment.tenant_id == tenant.id, TenantPlanAssignment.status == "ACTIVE")
        .order_by(TenantPlanAssignment.effective_from.desc())
        .first()
    )
    return {
        "id": str(tenant.id),
        "business_id": tenant.business_id,
        "tenant_key": tenant.tenant_key,
        "name": tenant.name,
        "status": tenant.status,
        "created_at": tenant.created_at.isoformat() if tenant.created_at else None,
        "plan_id": str(assignment.plan_id) if assignment else None,
        "counts": {
            "users": membership_count,
            "administrators": admin_count,
            "connectors": connector_count,
            "mappings": mapping_count,
            "audit_events": audit_count,
        },
    }


@router.get("/platform-admin/customer-records/{customer_id}")
def get_platform_customer_record(customer_id: uuid.UUID, request: Request, db: Session = Depends(get_db)):
    """Return the complete platform Customer 360 shell without customer business records."""
    _require_platform_admin(request, db)
    return customer_record(db, _customer_or_404(db, customer_id))


def _customer_or_404(db: Session, customer_id) -> Customer:
    customer = db.query(Customer).filter(Customer.id == customer_id).first()
    if customer is None:
        raise HTTPException(404, detail={"code": "CUSTOMER_NOT_FOUND", "message": "Customer is not available"})
    return customer


def customer_record(db: Session, customer: Customer) -> dict:
    """The customer record as GET customer-records/{id} returns it (also returned by the edit and status routes)."""
    tenants = db.query(Tenant).filter(Tenant.customer_id == customer.id).order_by(Tenant.name).all()
    return {
        "customer": {
            "id": str(customer.id),
            "business_id": customer.business_id,
            "customer_identifier": customer.customer_identifier,
            "legal_name": customer.legal_name,
            "display_name": customer.display_name,
            "trading_name": customer.trading_name,
            "customer_type": customer.customer_type,
            "industry": customer.industry,
            "company_size": customer.company_size,
            "country": customer.country,
            "state_province": customer.state_province,
            "headquarters": customer.headquarters,
            "website": customer.website,
            "crm_reference": customer.crm_reference,
            "primary_business_contact": customer.primary_business_contact,
            "billing_contact": customer.billing_contact,
            "internal_account_owner": customer.internal_account_owner,
            "implementation_manager": customer.implementation_manager,
            "lifecycle_status": customer.lifecycle_status,
            "lock_version": customer.lock_version,
            "is_operator": is_operator_customer(db, customer.id),
            "created_at": customer.created_at,
            "updated_at": customer.updated_at,
            "updated_by": str(customer.updated_by) if customer.updated_by else None,
        },
        "tenants": [
            {
                "id": str(t.id),
                "business_id": t.business_id,
                "tenant_identifier": t.tenant_identifier,
                "tenant_key": t.tenant_key,
                "name": t.name,
                "display_name": t.display_name,
                "tenant_type": t.tenant_type,
                "deployment_model": t.deployment_model,
                "primary_region": t.primary_region,
                "residency_region": t.residency_region,
                "status": t.status,
                "provisioning_status": t.provisioning_status,
                "lock_version": t.lock_version,
                "effective_access": effective_access(t.status, customer.lifecycle_status),
            }
            for t in tenants
        ],
        # Sections of the customer page; each is served by the tabs endpoint below.
        "tabs": ["Overview", "Administrators", "Subscription", "Usage", "Activity"],
    }


# Editable customer details (column names); identifiers (customer_identifier, business_id) never change.
CUSTOMER_EDITABLE_FIELDS = (
    "legal_name",
    "display_name",
    "trading_name",
    "customer_type",
    "industry",
    "company_size",
    "country",
    "state_province",
    "headquarters",
    "website",
    "crm_reference",
    "primary_business_contact",
    "billing_contact",
    "internal_account_owner",
    "implementation_manager",
)
# Columns that cannot be emptied.
CUSTOMER_REQUIRED_FIELDS = frozenset({"legal_name", "display_name", "customer_type", "country"})


def _stale(kind: str) -> HTTPException:
    return HTTPException(
        409,
        detail={"code": "STALE_RECORD", "message": f"{kind} changed since it was loaded; refresh before retrying"},
    )


def _no_changes() -> HTTPException:
    return HTTPException(422, detail={"code": "NO_CHANGES", "message": "Nothing was changed"})


@router.patch("/platform-admin/customer-records/{customer_id}")
def update_platform_customer(
    customer_id: uuid.UUID, payload: CustomerUpdateRequest, request: Request, db: Session = Depends(get_db)
):
    """Edit a customer's details (Platform Administrators only), with optimistic locking and an audited reason."""
    admin = _require_platform_admin(request, db)
    customer = _customer_or_404(db, customer_id)
    if int(payload.lock_version) != int(customer.lock_version or 0):
        raise _stale("Customer")
    sent = payload.model_dump(include=set(CUSTOMER_EDITABLE_FIELDS), exclude_unset=True)
    changes: dict = {}
    for field, value in sent.items():
        if isinstance(value, str):
            value = value.strip() or None
        if isinstance(value, dict):
            # A contact is stored whole, {name, email, phone}; an empty one is no contact.
            value = {key: value.get(key) for key in ("name", "email", "phone")}
            value = value if any(value.values()) else None
        if value is None and field in CUSTOMER_REQUIRED_FIELDS:
            raise HTTPException(
                422, detail={"code": "FIELD_REQUIRED", "message": f"{field.replace('_', ' ')} cannot be empty"}
            )
        if value != getattr(customer, field):
            changes[field] = value
    if not changes:
        raise _no_changes()
    before = {field: getattr(customer, field) for field in changes}
    now = datetime.now(timezone.utc)
    for field, value in changes.items():
        setattr(customer, field, value)
    customer.lock_version = int(customer.lock_version or 0) + 1
    customer.updated_by = admin.id
    customer.updated_at = now
    db.add(
        AuditEvent(
            id=uuid.uuid4(),
            tenant_id=admin.tenant_id,
            actor_ref=str(admin.id),
            action="CUSTOMER_UPDATED",
            entity_type="Customer",
            entity_id=customer.id,
            details={
                "reason": payload.reason.strip(),
                "customer_identifier": customer.customer_identifier,
                "changed_fields": sorted(changes),
                "before": before,
                "after": changes,
            },
            created_at=now,
        )
    )
    db.commit()
    return customer_record(db, customer)


@router.post("/platform-admin/customer-records/{customer_id}/lifecycle")
def transition_platform_customer(
    customer_id: uuid.UUID, payload: CustomerLifecycleRequest, request: Request, db: Session = Depends(get_db)
):
    """Activate or suspend a customer. Only the customer's own status changes: its tenants keep theirs.

    A suspended customer blocks sign-in, the API and background jobs for every tenant it owns (request_context.py);
    reactivating it restores exactly the tenants that are themselves active. Re-authentication is required, and the
    platform operator's own customer can never be suspended.
    """
    from auth.service import _verify

    admin = _require_platform_admin(request, db)
    customer = _customer_or_404(db, customer_id)
    if payload.lock_version is not None and int(payload.lock_version) != int(customer.lock_version or 0):
        raise _stale("Customer")
    current = str(customer.lifecycle_status or "").upper()
    target = payload.status
    if target == "SUSPENDED" and is_operator_customer(db, customer.id):
        raise HTTPException(
            409,
            detail={
                "code": "OPERATOR_PROTECTED",
                "message": "The MDARIX operator organization cannot be suspended",
            },
        )
    if current not in CUSTOMER_STATUS_SOURCES.get(target, frozenset()):
        raise HTTPException(
            409,
            detail={
                "code": "INVALID_CUSTOMER_TRANSITION",
                "message": f"A {current.lower()} customer cannot become {target.lower()}",
                "from": current,
                "to": target,
            },
        )
    actor = db.query(AuthUser).filter(AuthUser.id == admin.id, AuthUser.tenant_id == admin.tenant_id).first()
    if actor is None or not _verify(payload.password, actor.password_hash):
        db.rollback()
        raise HTTPException(
            403,
            detail={
                "code": "INVALID_REAUTHENTICATION",
                "message": "Current password is required to change a customer's status",
            },
        )
    now = datetime.now(timezone.utc)
    tenants = db.query(Tenant).filter(Tenant.customer_id == customer.id).order_by(Tenant.tenant_key).all()
    before = {tenant.id: effective_access(tenant.status, current) for tenant in tenants}
    customer.lifecycle_status = target
    customer.lock_version = int(customer.lock_version or 0) + 1
    customer.updated_by = admin.id
    customer.updated_at = now
    affected = [
        {
            "tenant_id": str(tenant.id),
            "business_id": tenant.business_id,
            "name": tenant.display_name or tenant.name,
            "effective_access": effective_access(tenant.status, target),
        }
        for tenant in tenants
        if effective_access(tenant.status, target) != before[tenant.id]
    ]
    db.add(
        AuditEvent(
            id=uuid.uuid4(),
            tenant_id=admin.tenant_id,
            actor_ref=str(admin.id),
            action="CUSTOMER_LIFECYCLE_TRANSITION",
            entity_type="Customer",
            entity_id=customer.id,
            details={
                "from": current,
                "to": target,
                "reason": payload.reason.strip(),
                "customer_identifier": customer.customer_identifier,
                "tenants_access_blocked": [
                    item["business_id"] for item in affected if item["effective_access"] != "ACTIVE"
                ],
                "tenants_access_restored": [
                    item["business_id"] for item in affected if item["effective_access"] == "ACTIVE"
                ],
            },
            created_at=now,
        )
    )
    db.commit()
    return {
        **customer_record(db, customer),
        "customer_id": str(customer.id),
        "customer_business_id": customer.business_id,
        "previous_status": current,
        "status": target,
        "tenants_affected": affected,
        # Earlier response fields, kept for existing callers: tenants no longer change status with the customer.
        "tenants_changed": [],
        "tenants_unchanged": [tenant.tenant_key for tenant in tenants],
        "tenants_refused": [],
    }


@router.get("/platform-admin/customer-records/{customer_id}/tabs/{tab}")
def get_platform_customer_tab(customer_id: uuid.UUID, tab: str, request: Request, db: Session = Depends(get_db)):
    """Return structured, server-authorized Customer 360 tab data. The customer's own data (its integrations, its
    organizations' audit trail) shows only for organizations whose administrators approved support access; the rest
    are counted in ``withheld`` (backend/app/support_access.py)."""
    admin = _require_platform_admin(request, db)
    customer = db.query(Customer).filter(Customer.id == customer_id).first()
    if customer is None:
        raise HTTPException(404, detail={"code": "CUSTOMER_NOT_FOUND", "message": "Customer is not available"})
    tenants = db.query(Tenant).filter(Tenant.customer_id == customer.id).all()
    tenant_ids = [tenant.id for tenant in tenants]
    # Rows name their tenant; the screen shows the tenant's business identifier, not its UUID.
    tenant_business_ids = {tenant.id: tenant.business_id for tenant in tenants}
    key = tab.strip().lower().replace(" ", "_")
    withheld = 0
    if key in {"administrators", "users"}:
        rows = (
            db.query(AuthUser)
            .filter(AuthUser.tenant_id.in_(tenant_ids), func.upper(AuthUser.role) == "CUSTOMER_ADMIN")
            .order_by(AuthUser.username)
            .all()
        )
        items = [
            {
                "id": str(row.id),
                "business_id": row.business_id,
                "display_name": row.display_name,
                "email": row.username,
                "role": row.role,
                "status": row.status,
                "tenant_id": str(row.tenant_id),
                "tenant_business_id": tenant_business_ids.get(row.tenant_id),
            }
            for row in rows
        ]
    elif key in {"environments", "environment"}:
        rows = db.query(TenantEnvironment).filter(TenantEnvironment.tenant_id.in_(tenant_ids)).all()
        items = [
            {
                "id": str(row.id),
                "tenant_id": str(row.tenant_id),
                "tenant_business_id": tenant_business_ids.get(row.tenant_id),
                "environment_identifier": row.environment_identifier,
                "environment_type": row.environment_type,
                "region": row.region,
                "residency_region": row.residency_region,
                "status": row.status,
                "configuration_version": row.configuration_version,
            }
            for row in rows
        ]
    elif key in {"subscription", "entitlements"}:
        assignments = (
            db.query(TenantPlanAssignment)
            .filter(TenantPlanAssignment.tenant_id.in_(tenant_ids), TenantPlanAssignment.status == "ACTIVE")
            .all()
        )
        items = []
        for assignment in assignments:
            plan = db.query(PlanDefinition).filter(PlanDefinition.id == assignment.plan_id).first()
            features = (
                db.query(FeatureEntitlement)
                .filter(FeatureEntitlement.plan_id == assignment.plan_id, FeatureEntitlement.status == "ACTIVE")
                .all()
            )
            if key == "subscription":
                items.append(
                    {
                        "id": str(assignment.id),
                        "tenant_id": str(assignment.tenant_id),
                        "tenant_business_id": tenant_business_ids.get(assignment.tenant_id),
                        "plan_code": plan.code if plan else None,
                        "plan_name": plan.name if plan else None,
                        "status": assignment.status,
                        "effective_from": assignment.effective_from,
                        "effective_to": assignment.effective_to,
                    }
                )
            else:
                items.extend(
                    {
                        "id": str(feature.id),
                        "tenant_id": str(assignment.tenant_id),
                        "tenant_business_id": tenant_business_ids.get(assignment.tenant_id),
                        "feature_code": feature.feature_code,
                        "enabled": feature.enabled,
                        "limits": feature.limits or {},
                        "status": feature.status,
                    }
                    for feature in features
                )
    elif key == "identity":
        rows = (
            db.query(IdentityProviderConfiguration)
            .filter(IdentityProviderConfiguration.tenant_id.in_(tenant_ids))
            .all()
        )
        items = [
            {
                "id": str(row.id),
                "tenant_id": str(row.tenant_id),
                "tenant_business_id": tenant_business_ids.get(row.tenant_id),
                "provider_type": row.provider_type,
                "login_mode": row.login_mode,
                "status": row.status,
                "verified_at": row.verified_at,
            }
            for row in rows
        ]
    elif key == "integrations":
        opened = support_access.open_tenants(
            db, admin, support_access.CONFIGURATION, within=set(tenant_ids), request=request
        )
        withheld = len(set(tenant_ids) - opened)
        rows = (
            db.query(ConnectorConfiguration).filter(ConnectorConfiguration.tenant_id.in_(sorted(opened, key=str))).all()
        )
        items = [
            {
                "id": str(row.id),
                "business_id": row.business_id,
                "tenant_id": str(row.tenant_id),
                "tenant_business_id": tenant_business_ids.get(row.tenant_id),
                "code": row.code,
                "connector_type": row.connector_type,
                "version": row.version,
                "status": row.status,
                "health": "REVIEW",
            }
            for row in rows
        ]
    elif key == "usage":
        items = [
            {
                "tenant_id": str(tenant.id),
                "tenant_business_id": tenant.business_id,
                "users": db.query(TenantMembership).filter(TenantMembership.tenant_id == tenant.id).count(),
                "administrators": db.query(AuthUser)
                .filter(
                    AuthUser.tenant_id == tenant.id,
                    func.upper(AuthUser.role).in_(["PLATFORM_ADMIN", "CUSTOMER_ADMIN"]),
                )
                .count(),
                "connectors": db.query(ConnectorConfiguration)
                .filter(ConnectorConfiguration.tenant_id == tenant.id)
                .count(),
            }
            for tenant in tenants
        ]
    elif key == "support":
        rows = db.query(SupportAccessGrant).filter(SupportAccessGrant.tenant_id.in_(tenant_ids)).all()
        items = [
            {
                "id": str(row.id),
                "tenant_id": str(row.tenant_id),
                "tenant_business_id": tenant_business_ids.get(row.tenant_id),
                "status": row.status,
                "reason": row.reason,
                "expires_at": row.expires_at,
                "scope": row.scope,
            }
            for row in rows
        ]
    elif key in {"security", "audit", "activity"}:
        # The customer's tenants' events, and the events about the customer itself (edits, status changes); of
        # those, an organization's own events only where its administrators approved Audit access, and what MDARIX
        # staff did anywhere.
        opened = support_access.open_tenants(db, admin, support_access.AUDIT, within=set(tenant_ids), request=request)
        withheld = len(set(tenant_ids) - opened)
        query = db.query(AuditEvent).filter(
            or_(
                AuditEvent.tenant_id.in_(tenant_ids),
                and_(AuditEvent.entity_type == "Customer", AuditEvent.entity_id == customer.id),
            ),
            or_(
                support_access.visible_audit_clause(opened),
                and_(AuditEvent.entity_type == "Customer", AuditEvent.entity_id == customer.id),
            ),
        )
        if key == "activity":
            # What people changed, without the automatic per-request log entries (still in the full audit log).
            query = query.filter(~AuditEvent.action.like("REQUEST\\_%"))
        rows = query.order_by(AuditEvent.created_at.desc()).limit(100).all()
        items = [
            {
                "id": str(row.id),
                "tenant_id": str(row.tenant_id),
                "tenant_business_id": tenant_business_ids.get(row.tenant_id),
                "action": row.action,
                "entity_type": row.entity_type,
                "entity_id": str(row.entity_id) if row.entity_id else None,
                "actor_ref": row.actor_ref,
                "details": row.details or {},
                "created_at": row.created_at,
            }
            for row in rows
        ]
    else:
        raise HTTPException(
            404, detail={"code": "CUSTOMER_TAB_NOT_FOUND", "message": "Customer 360 tab is not available"}
        )
    return {
        "customer_id": str(customer.id),
        "tab": tab,
        "items": items,
        "count": len(items),
        "scope": "platform-authorized",
        # Organizations of this customer whose data this tab leaves out until their administrators approve access.
        "withheld": withheld,
    }


@router.get("/platform-admin/customers/{tenant_id}/integrations/{connector_id}")
def get_platform_connector_detail(
    tenant_id: uuid.UUID, connector_id: uuid.UUID, request: Request, db: Session = Depends(get_db)
):
    admin = _require_platform_admin(request, db)
    support_access.require_customer_approved_access(db, admin, tenant_id, support_access.CONFIGURATION, request=request)
    row = (
        db.query(ConnectorConfiguration)
        .filter(ConnectorConfiguration.id == connector_id, ConnectorConfiguration.tenant_id == tenant_id)
        .first()
    )
    if row is None:
        raise HTTPException(
            404, detail={"code": "CONNECTOR_NOT_FOUND", "message": "Integration is not available for this tenant"}
        )
    configuration = row.configuration or {}
    return {
        "id": str(row.id),
        "business_id": row.business_id,
        "tenant_id": str(row.tenant_id),
        "code": row.code,
        "connector_type": row.connector_type,
        "version": row.version,
        "status": row.status,
        "endpoint": configuration.get("endpoint"),
        "health_path": configuration.get("health_path"),
        "schema_path": configuration.get("schema_path"),
        "credential_configured": bool(configuration.get("credential_ref")),
        "last_known_health": "NOT_RUN",
        "scope": {"tenant_scoped": True, "secrets_redacted": True},
    }
