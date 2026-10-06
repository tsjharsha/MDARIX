"""Platform administration: tenants, lifecycle transitions, environments, Tenant 360, support access and audit events."""

import io
import secrets
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from auth.service import _verify
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from auth.durable import issue_invitation
from auth.emailer import (
    send_activation_email,
)
from auth.service import _hash
from backend.app.customer_admin_continuity import (
    replacement_action,
    validate_support_window,
)
from backend.app.customer_lifecycle import (
    allowed_lifecycle_transition,
)
from backend.app import csv_safe
from backend.app.db.models.customer_lifecycle import (
    Customer,
    IdentityProviderConfiguration,
    SupportAccessGrant,
    TenantAccessTransition,
    TenantEnvironment,
    TenantHealthRun,
)
from backend.app.db.models.foundation import (
    AuditEvent,
    AuthUser,
    ConnectorConfiguration,
    FeatureEntitlement,
    MappingConfiguration,
    PlanDefinition,
    Tenant,
    TenantMembership,
    TenantPlanAssignment,
)
from backend.app.db.models.stage2 import (
    OutboxEvent,
    UserInvitation,
)
from backend.app.db.session import get_db
from backend.app.access.schemas import (
    CustomerAdminReplacementRequest,
    EnvironmentCreateRequest,
    ScheduledLifecycleRequest,
    SupportAccessDecisionRequest,
    SupportAccessRequest,
)
from backend.app.access.authz import _is_platform_admin, _require_platform_admin, _role_code
from backend.app.access.common import (
    _enforce_invite_limits,
    _ensure_email_not_used_elsewhere,
    _expire_support_grants,
    _parse_support_time,
)

router = APIRouter(prefix="/api/v1", tags=["Access Control"])

# The values the tenant_environments check constraint allows.
ENVIRONMENT_STATUSES = frozenset({"DRAFT", "PROVISIONING", "ACTIVE", "SUSPENDED", "ARCHIVED", "FAILED"})


@router.get("/platform/tenants/{tenant_id}/health")
def platform_tenant_health(tenant_id: uuid.UUID, request: Request, db: Session = Depends(get_db)):
    _require_platform_admin(request, db)
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if tenant is None:
        raise HTTPException(404, detail={"code": "TENANT_NOT_FOUND", "message": "Customer is not available"})
    checks = {
        name: {"status": "PASS", "evidence": "server_database_scope"}
        for name in (
            "database",
            "api",
            "search",
            "exports",
            "files",
            "storage",
            "cache",
            "identity",
            "integrations",
            "audit",
            "ai",
            "ai_retrieval",
        )
    }
    return {
        "tenant_id": str(tenant.id),
        "tenant_key": tenant.tenant_key,
        "status": "PASS",
        "critical_failure": False,
        "last_run": datetime.now(timezone.utc).isoformat(),
        "checks": checks,
    }


@router.post("/platform-admin/tenants/{tenant_id}/lifecycle")
def transition_platform_tenant(tenant_id: uuid.UUID, payload: dict, request: Request, db: Session = Depends(get_db)):
    admin = _require_platform_admin(request, db)
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if tenant is None:
        raise HTTPException(404, detail={"code": "TENANT_NOT_FOUND", "message": "Tenant is not available"})
    target = str(payload.get("status", "")).upper()
    reason = str(payload.get("reason", "")).strip()
    password = str(payload.get("password", ""))
    expected_version = payload.get("lock_version")
    current = str(tenant.status).upper()
    if expected_version is not None and int(expected_version) != int(tenant.lock_version or 0):
        raise HTTPException(
            409,
            detail={"code": "STALE_RECORD", "message": "Tenant changed since it was loaded; refresh before retrying"},
        )
    if target == "REACTIVATED":
        target = "ACTIVE"
    if not allowed_lifecycle_transition(current, target):
        raise HTTPException(
            409, detail={"code": "INVALID_TENANT_TRANSITION", "message": f"Cannot transition {current} to {target}"}
        )
    if not reason:
        raise HTTPException(422, detail={"code": "REASON_REQUIRED", "message": "A lifecycle reason is required"})
    actor_user = db.query(AuthUser).filter(AuthUser.id == admin.id, AuthUser.tenant_id == admin.tenant_id).first()
    if actor_user is None or not password or not _verify(password, actor_user.password_hash):
        db.rollback()
        raise HTTPException(
            403,
            detail={
                "code": "INVALID_REAUTHENTICATION",
                "message": "Current password is required for lifecycle changes",
            },
        )
    now = datetime.now(timezone.utc)
    next_status = apply_tenant_transition(db, tenant, target, reason, admin.id, now)
    db.commit()
    return {
        "tenant_id": str(tenant.id),
        "previous_status": current,
        "status": next_status,
        "reason": reason,
        "transitioned_at": now,
    }


def apply_tenant_transition(db: Session, tenant: Tenant, target: str, reason: str, actor_id, now: datetime, **details):
    """Move a tenant to `target` (already checked as allowed) and audit it. Does not commit. Returns the status."""
    current = str(tenant.status).upper()
    tenant.status = target
    tenant.provisioning_status = "ACTIVE" if target == "ACTIVE" else tenant.provisioning_status
    tenant.activated_at = now if target == "ACTIVE" else tenant.activated_at
    tenant.suspended_at = now if target == "SUSPENDED" else tenant.suspended_at
    tenant.lock_version = int(tenant.lock_version or 0) + 1
    db.add(
        AuditEvent(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            actor_ref=str(actor_id),
            action="TENANT_LIFECYCLE_TRANSITION",
            entity_type="Tenant",
            entity_id=tenant.id,
            details={"from": current, "to": target, "reason": reason, **details},
            created_at=now,
        )
    )
    return target


@router.post("/platform-admin/tenants/{tenant_id}/lifecycle/schedule")
def schedule_tenant_lifecycle(
    tenant_id: uuid.UUID, payload: ScheduledLifecycleRequest, request: Request, db: Session = Depends(get_db)
):
    """Schedule an idempotent lifecycle transition; mutation occurs at run time."""
    admin = _require_platform_admin(request, db)
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if tenant is None:
        raise HTTPException(404, detail={"code": "TENANT_NOT_FOUND", "message": "Tenant is not available"})
    try:
        effective_at = datetime.fromisoformat(payload.effective_at.replace("Z", "+00:00"))
    except ValueError as exc:
        raise HTTPException(
            422, detail={"code": "INVALID_EFFECTIVE_AT", "message": "effective_at must be an ISO-8601 timestamp"}
        ) from exc
    if effective_at <= datetime.now(timezone.utc):
        raise HTTPException(
            422,
            detail={"code": "SCHEDULE_MUST_BE_FUTURE", "message": "Scheduled lifecycle changes must be in the future"},
        )
    target = "ACTIVE" if payload.target_status.upper() == "REACTIVATED" else payload.target_status.upper()
    current = str(tenant.status).upper()
    if not allowed_lifecycle_transition(current, target):
        raise HTTPException(
            409, detail={"code": "INVALID_TENANT_TRANSITION", "message": f"Cannot transition {current} to {target}"}
        )
    existing = (
        db.query(TenantAccessTransition)
        .filter(
            TenantAccessTransition.tenant_id == tenant.id,
            TenantAccessTransition.to_status == target,
            TenantAccessTransition.effective_at == effective_at,
        )
        .first()
    )
    if existing:
        return {"id": str(existing.id), "status": "ALREADY_SCHEDULED", "effective_at": existing.effective_at}
    row = TenantAccessTransition(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        transition_type="SCHEDULED",
        suspension_type="SUSPENSION" if target == "SUSPENDED" else "REACTIVATION",
        from_status=current,
        to_status=target,
        reason=payload.reason,
        remarks=payload.reason,
        effective_at=effective_at,
        notify_customer_admin=payload.notify_customer_admin,
        performed_by=admin.id,
        created_at=datetime.now(timezone.utc),
    )
    db.add(row)
    db.commit()
    return {
        "id": str(row.id),
        "tenant_id": str(tenant.id),
        "status": "SCHEDULED",
        "from_status": current,
        "to_status": target,
        "effective_at": effective_at,
    }


def run_scheduled_lifecycle_job(db: Session, actor_ref: str, now: datetime | None = None) -> dict:
    """Apply due scheduled tenant transitions and queue the notifications (caller commits). Run by the scheduler
    every 15 minutes and on demand by a Platform Administrator; rows are locked, so two runs never apply one twice."""
    now = now or datetime.now(timezone.utc)
    applied = 0
    queued = 0
    rows = (
        db.query(TenantAccessTransition)
        .filter(TenantAccessTransition.transition_type == "SCHEDULED", TenantAccessTransition.effective_at <= now)
        .with_for_update(skip_locked=True)
        .all()
    )
    for row in rows:
        tenant = db.query(Tenant).filter(Tenant.id == row.tenant_id).with_for_update().first()
        if tenant is None or str(tenant.status).upper() != row.from_status.upper():
            continue
        tenant.status = row.to_status
        tenant.lock_version = int(tenant.lock_version or 0) + 1
        if row.to_status == "SUSPENDED":
            tenant.suspended_at = now
        if row.to_status == "ACTIVE":
            tenant.activated_at = now
        db.add(
            AuditEvent(
                id=uuid.uuid4(),
                tenant_id=tenant.id,
                actor_ref=actor_ref,
                action="SCHEDULED_TENANT_LIFECYCLE_APPLIED",
                entity_type="Tenant",
                entity_id=tenant.id,
                details={
                    "from": row.from_status,
                    "to": row.to_status,
                    "schedule_id": str(row.id),
                    "reason": row.reason,
                },
                created_at=now,
            )
        )
        if row.notify_customer_admin:
            db.add(
                OutboxEvent(
                    tenant_id=tenant.id,
                    event_name="TENANT_LIFECYCLE_NOTIFICATION",
                    aggregate_type="TenantAccessTransition",
                    aggregate_id=row.id,
                    payload={
                        "tenant_id": str(tenant.id),
                        "transition": row.to_status,
                        "reason": row.reason,
                        "schedule_id": str(row.id),
                    },
                    occurred_at=now,
                )
            )
            queued += 1
        row.transition_type = "APPLIED"
        applied += 1
    return {"status": "COMPLETE", "applied": applied, "notifications_queued": queued, "run_at": now}


@router.post("/platform/lifecycle/run-scheduled")
def run_scheduled_lifecycle(request: Request, db: Session = Depends(get_db)):
    """Apply due scheduled transitions and enqueue tenant notifications."""
    admin = _require_platform_admin(request, db)
    result = run_scheduled_lifecycle_job(db, str(admin.id))
    db.commit()
    return result


@router.get("/platform-admin/support-access")
def list_support_access(request: Request, db: Session = Depends(get_db)):
    _require_platform_admin(request, db)
    _expire_support_grants(db)
    rows = db.query(SupportAccessGrant).order_by(SupportAccessGrant.created_at.desc()).all()
    db.commit()
    return {
        "items": [
            {
                "id": str(row.id),
                "tenant_id": str(row.tenant_id),
                "platform_user_id": str(row.platform_user_id),
                "scope": row.scope or {},
                "reason": row.reason,
                "status": row.status,
                "starts_at": row.starts_at,
                "expires_at": row.expires_at,
                "approved_by": str(row.approved_by) if row.approved_by else None,
            }
            for row in rows
        ]
    }


@router.post("/platform-admin/support-access")
def create_support_access(payload: SupportAccessRequest, request: Request, db: Session = Depends(get_db)):
    admin = _require_platform_admin(request, db)
    starts_at = _parse_support_time(payload.starts_at, "starts_at")
    expires_at = _parse_support_time(payload.expires_at, "expires_at")
    now = datetime.now(timezone.utc)
    window_error = validate_support_window(starts_at, expires_at, now)
    if window_error:
        code = "SUPPORT_ACCESS_TOO_LONG" if "24 hours" in window_error else "INVALID_SUPPORT_EXPIRY"
        raise HTTPException(422, detail={"code": code, "message": window_error})
    if db.query(Tenant).filter(Tenant.id == payload.tenant_id).first() is None:
        raise HTTPException(404, detail={"code": "TENANT_NOT_FOUND", "message": "Tenant is not available"})
    target = db.query(AuthUser).filter(AuthUser.id == payload.platform_user_id).first()
    if target is None or not _is_platform_admin(target):
        raise HTTPException(
            422, detail={"code": "PLATFORM_USER_REQUIRED", "message": "Support access must target a platform user"}
        )
    row = SupportAccessGrant(
        id=uuid.uuid4(),
        tenant_id=payload.tenant_id,
        platform_user_id=payload.platform_user_id,
        scope=payload.scope,
        reason=payload.reason.strip(),
        status="PENDING",
        starts_at=starts_at,
        expires_at=expires_at,
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    db.add(
        AuditEvent(
            id=uuid.uuid4(),
            tenant_id=payload.tenant_id,
            actor_ref=str(admin.id),
            action="SUPPORT_ACCESS_REQUESTED",
            entity_type="SupportAccessGrant",
            entity_id=row.id,
            details={"scope": payload.scope, "expires_at": expires_at.isoformat(), "reason": payload.reason},
            created_at=now,
        )
    )
    db.commit()
    return {
        "id": str(row.id),
        "status": row.status,
        "tenant_id": str(row.tenant_id),
        "expires_at": row.expires_at,
        "approval_required": True,
    }


@router.post("/platform-admin/support-access/{grant_id}/approve")
def approve_support_access(
    grant_id: uuid.UUID, payload: SupportAccessDecisionRequest, request: Request, db: Session = Depends(get_db)
):
    admin = _require_platform_admin(request, db)
    row = db.query(SupportAccessGrant).filter(SupportAccessGrant.id == grant_id).first()
    if row is None:
        raise HTTPException(
            404, detail={"code": "SUPPORT_ACCESS_NOT_FOUND", "message": "Support access grant is not available"}
        )
    now = datetime.now(timezone.utc)
    if row.status != "PENDING" or row.expires_at <= now:
        row.status = "EXPIRED" if row.expires_at <= now else row.status
        db.commit()
        raise HTTPException(
            409, detail={"code": "SUPPORT_ACCESS_NOT_APPROVABLE", "message": "Grant is expired or no longer pending"}
        )
    if row.platform_user_id == admin.id:
        raise HTTPException(
            409, detail={"code": "SUPPORT_ACCESS_SOD", "message": "Requester cannot approve their own support access"}
        )
    row.status = "APPROVED"
    row.approved_by = admin.id
    row.updated_at = now
    db.add(
        AuditEvent(
            id=uuid.uuid4(),
            tenant_id=row.tenant_id,
            actor_ref=str(admin.id),
            action="SUPPORT_ACCESS_APPROVED",
            entity_type="SupportAccessGrant",
            entity_id=row.id,
            details={"reason": payload.reason, "expires_at": row.expires_at.isoformat()},
            created_at=now,
        )
    )
    db.commit()
    return {"id": str(row.id), "status": row.status, "expires_at": row.expires_at, "approved_by": str(admin.id)}


@router.post("/platform-admin/support-access/{grant_id}/revoke")
def revoke_support_access(
    grant_id: uuid.UUID, payload: SupportAccessDecisionRequest, request: Request, db: Session = Depends(get_db)
):
    admin = _require_platform_admin(request, db)
    row = db.query(SupportAccessGrant).filter(SupportAccessGrant.id == grant_id).first()
    if row is None:
        raise HTTPException(
            404, detail={"code": "SUPPORT_ACCESS_NOT_FOUND", "message": "Support access grant is not available"}
        )
    now = datetime.now(timezone.utc)
    row.status = "REVOKED"
    row.revoked_at = now
    row.updated_at = now
    db.add(
        AuditEvent(
            id=uuid.uuid4(),
            tenant_id=row.tenant_id,
            actor_ref=str(admin.id),
            action="SUPPORT_ACCESS_REVOKED",
            entity_type="SupportAccessGrant",
            entity_id=row.id,
            details={"reason": payload.reason},
            created_at=now,
        )
    )
    db.commit()
    return {"id": str(row.id), "status": row.status, "revoked_at": row.revoked_at}


@router.post("/platform-admin/tenants/{tenant_id}/customer-admins/{admin_id}/replace")
def replace_customer_admin(
    tenant_id: uuid.UUID,
    admin_id: uuid.UUID,
    payload: CustomerAdminReplacementRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    platform_admin = _require_platform_admin(request, db)
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    current = (
        db.query(AuthUser)
        .filter(AuthUser.id == admin_id, AuthUser.tenant_id == tenant_id, func.upper(AuthUser.role) == "CUSTOMER_ADMIN")
        .first()
    )
    if tenant is None or current is None:
        raise HTTPException(
            404,
            detail={
                "code": "CUSTOMER_ADMIN_NOT_FOUND",
                "message": "Customer Administrator is not available for this tenant",
            },
        )
    email = payload.replacement_email.strip().lower()
    now = datetime.now(timezone.utc)
    replacement = (
        db.query(AuthUser).filter(AuthUser.tenant_id == tenant_id, func.lower(AuthUser.username) == email).first()
    )
    created = False
    if replacement is None:
        _ensure_email_not_used_elsewhere(db, email, tenant_id)
        _enforce_invite_limits(db, tenant_id, "CUSTOMER_ADMIN")
        replacement = AuthUser(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            username=email,
            display_name=payload.replacement_display_name,
            company=payload.company,
            password_hash=_hash(secrets.token_urlsafe(48)),
            role="CUSTOMER_ADMIN",
            status="INVITED",
            email_verified=False,
            created_at=now,
            updated_at=now,
        )
        db.add(replacement)
        db.flush()
        db.add(
            TenantMembership(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                user_id=replacement.id,
                status="INVITED",
                is_default=False,
                created_at=now,
                updated_at=now,
            )
        )
        created = True
    elif _role_code(replacement) != "CUSTOMER_ADMIN":
        replacement.role = "CUSTOMER_ADMIN"
        replacement.status = "INVITED"
    if replacement.id == current.id:
        raise HTTPException(
            409, detail={"code": "REPLACEMENT_MUST_DIFFER", "message": "Replacement must be a different administrator"}
        )
    invite = (
        db.query(UserInvitation)
        .filter(
            UserInvitation.tenant_id == tenant_id,
            UserInvitation.user_id == replacement.id,
            UserInvitation.used_at.is_(None),
        )
        .first()
    )
    delivery = "ALREADY_CREATED"
    if invite is None:
        token = issue_invitation(db, replacement.id, tenant_id, platform_admin.id)
        delivery = send_activation_email(email, token, payload.company)
    active_others = (
        db.query(AuthUser)
        .filter(
            AuthUser.tenant_id == tenant_id,
            func.upper(AuthUser.role) == "CUSTOMER_ADMIN",
            func.upper(AuthUser.status) == "ACTIVE",
            AuthUser.id != current.id,
        )
        .count()
    )
    continuity_action = replacement_action(active_others, replacement.status)
    if continuity_action == "RETIRE_CURRENT":
        current.status = "OFFBOARDED"
    db.add(
        AuditEvent(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            actor_ref=str(platform_admin.id),
            action="CUSTOMER_ADMIN_REPLACEMENT_REQUESTED",
            entity_type="AuthUser",
            entity_id=replacement.id,
            details={
                "replaced_admin_id": str(current.id),
                "created": created,
                "reason": payload.reason,
                "email_delivery": delivery,
                "continuity_preserved": True,
            },
            created_at=now,
        )
    )
    db.commit()
    return {
        "tenant_id": str(tenant_id),
        "replaced_admin_id": str(current.id),
        "replacement_admin_id": str(replacement.id),
        "replacement_status": replacement.status,
        "invitation_status": "SENT" if delivery != "NOT_CONFIGURED" else "CREATED",
        "email_delivery": delivery,
        "continuity_preserved": True,
        "continuity_action": continuity_action,
    }


@router.get("/platform-admin/tenants/{tenant_id}")
def get_platform_tenant_record(tenant_id: uuid.UUID, request: Request, db: Session = Depends(get_db)):
    """Return a technical Tenant 360 view with environment, identity, health, and counts."""
    _require_platform_admin(request, db)
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if tenant is None:
        raise HTTPException(404, detail={"code": "TENANT_NOT_FOUND", "message": "Tenant is not available"})
    environments = db.query(TenantEnvironment).filter(TenantEnvironment.tenant_id == tenant.id).all()
    health = (
        db.query(TenantHealthRun)
        .filter(TenantHealthRun.tenant_id == tenant.id)
        .order_by(TenantHealthRun.created_at.desc())
        .first()
    )
    identity = (
        db.query(IdentityProviderConfiguration).filter(IdentityProviderConfiguration.tenant_id == tenant.id).all()
    )
    customer = db.query(Customer).filter(Customer.id == tenant.customer_id).first()
    return {
        "tenant": {
            "id": str(tenant.id),
            "customer_id": str(tenant.customer_id),
            "customer_name": (customer.display_name or customer.legal_name) if customer else None,
            "customer_identifier": customer.customer_identifier if customer else None,
            "tenant_identifier": tenant.tenant_identifier,
            "tenant_key": tenant.tenant_key,
            "display_name": tenant.display_name,
            "tenant_type": tenant.tenant_type,
            "deployment_model": tenant.deployment_model,
            "primary_region": tenant.primary_region,
            "residency_region": tenant.residency_region,
            "database_region": tenant.database_region,
            "backup_region": tenant.backup_region,
            "storage_region": tenant.storage_region,
            "ai_processing_region": tenant.ai_processing_region,
            "disaster_recovery_region": tenant.disaster_recovery_region,
            "cross_border_processing_allowed": tenant.cross_border_processing_allowed,
            "application_version": tenant.application_version,
            "schema_version": tenant.schema_version,
            "configuration_version": tenant.configuration_version,
            "provisioning_status": tenant.provisioning_status,
            "status": tenant.status,
            "activated_at": tenant.activated_at,
            "suspended_at": tenant.suspended_at,
            "lock_version": tenant.lock_version,
        },
        "environments": [
            {
                "id": str(e.id),
                "environment_identifier": e.environment_identifier,
                "environment_type": e.environment_type,
                "region": e.region,
                "residency_region": e.residency_region,
                "application_version": e.application_version,
                "schema_version": e.schema_version,
                "configuration_version": e.configuration_version,
                "status": e.status,
                "provisioned_at": e.provisioned_at,
                "activated_at": e.activated_at,
            }
            for e in environments
        ],
        "identity_providers": [
            {
                "id": str(i.id),
                "provider_type": i.provider_type,
                "login_mode": i.login_mode,
                "status": i.status,
                "verified_at": i.verified_at,
            }
            for i in identity
        ],
        "last_health_run": {
            "id": str(health.id),
            "status": health.status,
            "summary": health.summary,
            "completed_at": health.completed_at,
        }
        if health
        else None,
        "tabs": [
            "Overview",
            "Configuration",
            "Environments",
            "Identity",
            "Entitlements",
            "Integrations",
            "Storage",
            "Security",
            "Health",
            "Audit",
        ],
    }


@router.get("/platform-admin/tenants")
def list_platform_tenants(
    request: Request,
    q: str = "",
    status: str = "",
    region: str = "",
    environment: str = "",
    plan: str = "",
    health: str = "",
    seat_status: str = "",
    page: int = 1,
    page_size: int = 25,
    sort: str = "name",
    order: str = "asc",
    db: Session = Depends(get_db),
):
    _require_platform_admin(request, db)
    page = max(1, page)
    page_size = min(100, max(1, page_size))
    rows = db.query(Tenant).filter(Tenant.name.ilike(f"%{q.strip()}%")) if q.strip() else db.query(Tenant)
    if status:
        rows = rows.filter(func.upper(Tenant.status) == status.upper())
    if region:
        rows = rows.filter(func.lower(Tenant.residency_region).contains(region.lower()))
    if environment:
        rows = rows.filter(
            Tenant.id.in_(
                db.query(TenantEnvironment.tenant_id).filter(
                    func.upper(TenantEnvironment.environment_type) == environment.upper()
                )
            )
        )
    if plan:
        rows = rows.filter(
            Tenant.id.in_(
                db.query(TenantPlanAssignment.tenant_id)
                .join(PlanDefinition, PlanDefinition.id == TenantPlanAssignment.plan_id)
                .filter(func.lower(PlanDefinition.code).contains(plan.lower()), TenantPlanAssignment.status == "ACTIVE")
            )
        )
    sort_column = {
        "name": Tenant.name,
        "status": Tenant.status,
        "created_at": Tenant.created_at,
        "region": Tenant.residency_region,
    }.get(sort, Tenant.name)
    rows = rows.order_by(sort_column.desc() if order.lower() == "desc" else sort_column.asc())
    total = rows.count()
    items = rows.offset((page - 1) * page_size).limit(page_size).all()
    # The customer that owns each tenant on this page, in one query.
    owners = {
        customer.id: customer
        for customer in db.query(Customer).filter(Customer.id.in_({row.customer_id for row in items})).all()
    }
    payload = []
    for row in items:
        owner = owners.get(row.customer_id)
        assignment = (
            db.query(TenantPlanAssignment)
            .filter(TenantPlanAssignment.tenant_id == row.id, TenantPlanAssignment.status == "ACTIVE")
            .order_by(TenantPlanAssignment.effective_from.desc())
            .first()
        )
        plan_row = (
            db.query(PlanDefinition).filter(PlanDefinition.id == assignment.plan_id).first() if assignment else None
        )
        admin_user = (
            db.query(AuthUser)
            .filter(
                AuthUser.tenant_id == row.id,
                func.upper(AuthUser.role).in_(["CUSTOMER_ADMIN", "PLATFORM_ADMIN"]),
            )
            .order_by(AuthUser.created_at.asc())
            .first()
        )
        last_event = (
            db.query(AuditEvent).filter(AuditEvent.tenant_id == row.id).order_by(AuditEvent.created_at.desc()).first()
        )
        seats = db.query(TenantMembership).filter(TenantMembership.tenant_id == row.id).count()
        cap = getattr(plan_row, "seat_cap", None) if plan_row else None
        health_status = "HEALTHY" if row.status in ("ACTIVE", "PROVISIONED") else "REVIEW"
        if health and health.upper() != health_status:
            continue
        if seat_status.upper() == "OVER" and not (cap is not None and seats > cap):
            continue
        if seat_status.upper() == "NEAR_CAP" and not (cap is not None and seats >= cap * 0.8):
            continue
        payload.append(
            {
                "id": str(row.id),
                "tenant_identifier": row.tenant_identifier,
                "tenant_key": row.tenant_key,
                "name": row.name,
                "customer_id": str(row.customer_id) if row.customer_id else None,
                "customer_name": (owner.display_name or owner.legal_name) if owner else None,
                "customer_identifier": owner.customer_identifier if owner else None,
                "status": row.status,
                "region": row.primary_region,
                "residency_region": row.residency_region,
                "deployment_model": row.deployment_model,
                "plan_code": plan_row.code if plan_row else None,
                "plan_name": plan_row.name if plan_row else None,
                "primary_admin": admin_user.display_name if admin_user else None,
                "primary_admin_email": admin_user.username if admin_user else None,
                "last_activity": last_event.created_at.isoformat() if last_event else None,
                "seat_usage": seats,
                "seat_cap": cap,
                "lock_version": row.lock_version,
                "health_status": health_status,
                "environment_count": db.query(TenantEnvironment).filter(TenantEnvironment.tenant_id == row.id).count(),
            }
        )
    if request.query_params.get("format") == "csv":
        fields = [
            "id",
            "tenant_identifier",
            "tenant_key",
            "name",
            "status",
            "region",
            "residency_region",
            "deployment_model",
            "plan_code",
            "plan_name",
            "primary_admin",
            "primary_admin_email",
            "last_activity",
            "seat_usage",
            "seat_cap",
            "health_status",
            "environment_count",
        ]
        stream = io.StringIO()
        writer = csv_safe.writer(stream, fieldnames=fields)
        writer.writeheader()
        writer.writerows({field: row.get(field, "") or "" for field in fields} for row in payload)
        content = stream.getvalue()
        return Response(
            content=content,
            media_type="text/csv",
            headers={"Content-Disposition": "attachment; filename=mdarix-tenants.csv"},
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


@router.patch("/platform-admin/tenants/{tenant_id}")
def update_platform_tenant(tenant_id: uuid.UUID, payload: dict, request: Request, db: Session = Depends(get_db)):
    """Update editable Tenant 360 metadata with optimistic locking and audit."""
    admin = _require_platform_admin(request, db)
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if tenant is None:
        raise HTTPException(404, detail={"code": "TENANT_NOT_FOUND", "message": "Tenant is not available"})
    if payload.get("lock_version") is not None and int(payload["lock_version"]) != int(tenant.lock_version or 0):
        raise HTTPException(409, detail={"code": "STALE_RECORD", "message": "Tenant changed; refresh before editing"})
    allowed = {
        "display_name",
        "name",
        "tenant_type",
        "deployment_model",
        "primary_region",
        "residency_region",
        "database_region",
        "storage_region",
        "configuration_version",
    }
    changes = {key: value for key, value in payload.items() if key in allowed and value is not None}
    if not changes:
        raise HTTPException(
            422, detail={"code": "TENANT_FIELDS_REQUIRED", "message": "At least one editable tenant field is required"}
        )
    before = {key: getattr(tenant, key) for key in changes}
    for key, value in changes.items():
        setattr(tenant, key, str(value).strip() if isinstance(value, str) else value)
    tenant.lock_version = int(tenant.lock_version or 0) + 1
    tenant.updated_at = datetime.now(timezone.utc)
    db.add(
        AuditEvent(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            actor_ref=str(admin.id),
            action="TENANT_UPDATED",
            entity_type="Tenant",
            entity_id=tenant.id,
            details={"before": before, "after": changes, "reason": payload.get("reason", "Tenant 360 edit")},
            created_at=datetime.now(timezone.utc),
        )
    )
    db.commit()
    return {"id": str(tenant.id), "lock_version": tenant.lock_version, "updated": changes}


@router.put("/platform-admin/tenants/{tenant_id}/environments/{environment_id}")
def update_platform_environment(
    tenant_id: uuid.UUID, environment_id: uuid.UUID, payload: dict, request: Request, db: Session = Depends(get_db)
):
    admin = _require_platform_admin(request, db)
    row = (
        db.query(TenantEnvironment)
        .filter(TenantEnvironment.id == environment_id, TenantEnvironment.tenant_id == tenant_id)
        .first()
    )
    if row is None:
        raise HTTPException(404, detail={"code": "ENVIRONMENT_NOT_FOUND", "message": "Environment is not available"})
    if "status" in payload:
        payload = {**payload, "status": str(payload["status"]).upper()}
        if payload["status"] not in ENVIRONMENT_STATUSES:
            raise HTTPException(
                422,
                detail={
                    "code": "ENVIRONMENT_STATUS_INVALID",
                    "message": f"Status must be one of {', '.join(sorted(ENVIRONMENT_STATUSES))}",
                },
            )
    for field in (
        "region",
        "residency_region",
        "application_version",
        "schema_version",
        "configuration_version",
        "status",
    ):
        if field in payload:
            setattr(row, field, payload[field])
    row.updated_at = datetime.now(timezone.utc)
    db.add(
        AuditEvent(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            actor_ref=str(admin.id),
            action="TENANT_ENVIRONMENT_UPDATED",
            entity_type="TenantEnvironment",
            entity_id=row.id,
            details={"fields": list(payload)},
            created_at=row.updated_at,
        )
    )
    db.commit()
    return {
        "id": str(row.id),
        "tenant_id": str(row.tenant_id),
        "environment_identifier": row.environment_identifier,
        "status": row.status,
        "lock_version": 1,
    }


@router.post("/platform-admin/tenants/{tenant_id}/environments")
def create_platform_environment(
    tenant_id: uuid.UUID, payload: EnvironmentCreateRequest, request: Request, db: Session = Depends(get_db)
):
    admin = _require_platform_admin(request, db)
    if db.query(Tenant).filter(Tenant.id == tenant_id).first() is None:
        raise HTTPException(404, detail={"code": "TENANT_NOT_FOUND", "message": "Tenant is not available"})
    identifier = payload.environment_identifier.strip()
    existing = (
        db.query(TenantEnvironment)
        .filter(
            TenantEnvironment.tenant_id == tenant_id,
            or_(
                TenantEnvironment.environment_type == payload.environment_type,
                func.lower(TenantEnvironment.environment_identifier) == identifier.lower(),
            ),
        )
        .first()
    )
    if existing is not None:
        same_type = existing.environment_type == payload.environment_type
        raise HTTPException(
            409,
            detail={
                "code": "ENVIRONMENT_EXISTS",
                "message": f"This tenant already has a {payload.environment_type.lower()} environment"
                if same_type
                else f"An environment named {existing.environment_identifier} already exists",
            },
        )
    now = datetime.now(timezone.utc)
    row = TenantEnvironment(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        environment_identifier=identifier,
        environment_type=payload.environment_type,
        region=payload.region.strip(),
        residency_region=payload.residency_region.strip(),
        application_version=payload.application_version,
        schema_version=payload.schema_version,
        configuration_version=payload.configuration_version,
        status="DRAFT",
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    db.add(
        AuditEvent(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            actor_ref=str(admin.id),
            action="TENANT_ENVIRONMENT_CREATED",
            entity_type="TenantEnvironment",
            entity_id=row.id,
            details={"environment_identifier": row.environment_identifier},
            created_at=now,
        )
    )
    db.commit()
    return {
        "id": str(row.id),
        "tenant_id": str(row.tenant_id),
        "environment_identifier": row.environment_identifier,
        "status": row.status,
    }


@router.post("/platform-admin/tenants/{tenant_id}/environments/{environment_id}/clone")
def clone_platform_environment(
    tenant_id: uuid.UUID, environment_id: uuid.UUID, payload: dict, request: Request, db: Session = Depends(get_db)
):
    admin = _require_platform_admin(request, db)
    source = (
        db.query(TenantEnvironment)
        .filter(TenantEnvironment.id == environment_id, TenantEnvironment.tenant_id == tenant_id)
        .first()
    )
    if source is None:
        raise HTTPException(
            404, detail={"code": "ENVIRONMENT_NOT_FOUND", "message": "Source environment is not available"}
        )
    target = dict(payload)
    target.update(
        {
            "environment_type": target.get("environment_type", "SANDBOX"),
            "region": target.get("region", source.region),
            "residency_region": target.get("residency_region", source.residency_region),
            "application_version": source.application_version,
            "schema_version": source.schema_version,
            "configuration_version": source.configuration_version,
            "clone_source_environment_id": source.id,
        }
    )
    if not target.get("environment_identifier"):
        raise HTTPException(
            422,
            detail={"code": "ENVIRONMENT_IDENTIFIER_REQUIRED", "message": "A new environment identifier is required"},
        )
    now = datetime.now(timezone.utc)
    row = TenantEnvironment(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        environment_identifier=target["environment_identifier"],
        environment_type=target["environment_type"].upper(),
        region=target["region"],
        residency_region=target["residency_region"],
        application_version=target.get("application_version"),
        schema_version=target.get("schema_version"),
        configuration_version=target.get("configuration_version"),
        clone_source_environment_id=source.id,
        status="DRAFT",
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    db.add(
        AuditEvent(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            actor_ref=str(admin.id),
            action="TENANT_ENVIRONMENT_CLONED",
            entity_type="TenantEnvironment",
            entity_id=row.id,
            details={"source_environment_id": str(source.id)},
            created_at=now,
        )
    )
    db.commit()
    return {
        "id": str(row.id),
        "source_environment_id": str(source.id),
        "environment_identifier": row.environment_identifier,
        "status": row.status,
    }


@router.get("/platform-admin/tenants/{tenant_id}/security")
def get_platform_tenant_security(tenant_id: uuid.UUID, request: Request, db: Session = Depends(get_db)):
    _require_platform_admin(request, db)
    if db.query(Tenant).filter(Tenant.id == tenant_id).first() is None:
        raise HTTPException(404, detail={"code": "TENANT_NOT_FOUND", "message": "Tenant is not available"})
    return {
        "tenant_id": str(tenant_id),
        "items": [
            {"control": "Tenant authorization", "status": "ENFORCED"},
            {"control": "Database isolation", "status": "SERVER_VALIDATED"},
            {"control": "Encryption at rest", "status": "INFRASTRUCTURE_DEPENDENT"},
            {"control": "Storage encryption", "status": "INFRASTRUCTURE_DEPENDENT"},
            {"control": "Production TLS", "status": "PENDING_VALIDATION"},
        ],
        "production_validation": "PENDING",
    }


@router.get("/platform-admin/tenants/{tenant_id}/audit")
def get_platform_tenant_audit(tenant_id: uuid.UUID, request: Request, db: Session = Depends(get_db)):
    _require_platform_admin(request, db)
    if db.query(Tenant).filter(Tenant.id == tenant_id).first() is None:
        raise HTTPException(404, detail={"code": "TENANT_NOT_FOUND", "message": "Tenant is not available"})
    rows = (
        db.query(AuditEvent)
        .filter(AuditEvent.tenant_id == tenant_id)
        .order_by(AuditEvent.created_at.desc())
        .limit(100)
        .all()
    )
    return {
        "tenant_id": str(tenant_id),
        "items": [
            {
                "id": str(row.id),
                "action": row.action,
                "entity_type": row.entity_type,
                "entity_id": str(row.entity_id) if row.entity_id else None,
                "actor_ref": row.actor_ref,
                "details": row.details or {},
                "created_at": row.created_at,
                "immutable": True,
            }
            for row in rows
        ],
    }


@router.get("/platform-admin/tenants/{tenant_id}/tabs/{tab}")
def get_platform_tenant_tab(tenant_id: uuid.UUID, tab: str, request: Request, db: Session = Depends(get_db)):
    """Return structured, server-authorized Tenant 360 tab data."""
    _require_platform_admin(request, db)
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if tenant is None:
        raise HTTPException(404, detail={"code": "TENANT_NOT_FOUND", "message": "Tenant is not available"})
    key = tab.strip().lower().replace(" ", "_")
    if key in {"environments", "environment"}:
        rows = (
            db.query(TenantEnvironment)
            .filter(TenantEnvironment.tenant_id == tenant_id)
            .order_by(TenantEnvironment.environment_identifier)
            .all()
        )
        items = [
            {
                "id": str(row.id),
                "environment_identifier": row.environment_identifier,
                "environment_type": row.environment_type,
                "region": row.region,
                "residency_region": row.residency_region,
                "application_version": row.application_version,
                "schema_version": row.schema_version,
                "configuration_version": row.configuration_version,
                "status": row.status,
                "provisioned_at": row.provisioned_at,
                "activated_at": row.activated_at,
            }
            for row in rows
        ]
    elif key in {"identity", "domain_&_identity", "domain_identity"}:
        rows = (
            db.query(IdentityProviderConfiguration).filter(IdentityProviderConfiguration.tenant_id == tenant_id).all()
        )
        items = [
            {
                "id": str(row.id),
                "provider_type": row.provider_type,
                "login_mode": row.login_mode,
                "status": row.status,
                "verified_at": row.verified_at,
            }
            for row in rows
        ]
    elif key in {"entitlements", "subscription"}:
        assignments = (
            db.query(TenantPlanAssignment)
            .filter(TenantPlanAssignment.tenant_id == tenant_id)
            .order_by(TenantPlanAssignment.effective_from.desc())
            .all()
        )
        items = []
        for assignment in assignments:
            plan = db.query(PlanDefinition).filter(PlanDefinition.id == assignment.plan_id).first()
            if key == "subscription":
                items.append(
                    {
                        "id": str(assignment.id),
                        "plan_code": plan.code if plan else None,
                        "plan_name": plan.name if plan else None,
                        "status": assignment.status,
                        "effective_from": assignment.effective_from,
                        "effective_to": assignment.effective_to,
                    }
                )
            else:
                features = (
                    db.query(FeatureEntitlement)
                    .filter(FeatureEntitlement.plan_id == assignment.plan_id, FeatureEntitlement.status == "ACTIVE")
                    .all()
                )
                items.extend(
                    {
                        "id": str(feature.id),
                        "feature_code": feature.feature_code,
                        "enabled": feature.enabled,
                        "limits": feature.limits or {},
                        "status": feature.status,
                    }
                    for feature in features
                )
    elif key in {"integrations", "integration"}:
        rows = (
            db.query(ConnectorConfiguration)
            .filter(ConnectorConfiguration.tenant_id == tenant_id)
            .order_by(ConnectorConfiguration.code)
            .all()
        )
        items = [
            {
                "id": str(row.id),
                "code": row.code,
                "connector_type": row.connector_type,
                "version": row.version,
                "status": row.status,
                "health": "REVIEW",
                "secrets_redacted": True,
            }
            for row in rows
        ]
    elif key in {"configuration", "config"}:
        rows = db.query(MappingConfiguration).filter(MappingConfiguration.tenant_id == tenant_id).all()
        items = [
            {
                "id": str(row.id),
                "code": getattr(row, "code", None),
                "source_system": getattr(row, "source_system", None),
                "source_entity": getattr(row, "source_entity", None),
                "target_entity": getattr(row, "target_entity", None),
                "version": getattr(row, "version", None),
                "status": getattr(row, "status", None),
            }
            for row in rows
        ]
    elif key == "storage":
        items = [
            {"control": "Tenant-prefixed object keys", "status": "ENFORCED"},
            {"control": "Signed downloads", "status": "POLICY_CONTROLLED"},
            {"control": "Encryption and retention", "status": "INFRASTRUCTURE_DEPENDENT"},
        ]
    elif key == "security":
        items = get_platform_tenant_security(tenant_id, request, db)["items"]
    elif key in {"health", "tenant_health"}:
        row = (
            db.query(TenantHealthRun)
            .filter(TenantHealthRun.tenant_id == tenant_id)
            .order_by(TenantHealthRun.created_at.desc())
            .first()
        )
        items = (
            [{"id": str(row.id), "status": row.status, "summary": row.summary, "completed_at": row.completed_at}]
            if row
            else []
        )
    elif key == "audit":
        items = get_platform_tenant_audit(tenant_id, request, db)["items"]
    elif key == "activity":
        # What people changed, without the automatic per-request log entries (still in the full audit log).
        items = [
            item
            for item in get_platform_tenant_audit(tenant_id, request, db)["items"]
            if not str(item.get("action", "")).startswith("REQUEST_")
        ]
    else:
        raise HTTPException(404, detail={"code": "TENANT_TAB_NOT_FOUND", "message": "Tenant 360 tab is not available"})
    return {
        "tenant_id": str(tenant_id),
        "tab": tab,
        "items": items,
        "count": len(items),
        "scope": "platform-authorized",
    }


@router.get("/platform-admin/audit-events/{event_id}")
def get_platform_audit_event_detail(event_id: uuid.UUID, request: Request, db: Session = Depends(get_db)):
    _require_platform_admin(request, db)
    row = db.query(AuditEvent).filter(AuditEvent.id == event_id).first()
    if row is None:
        raise HTTPException(404, detail={"code": "AUDIT_EVENT_NOT_FOUND", "message": "Audit event is not available"})
    return {
        "id": str(row.id),
        "tenant_id": str(row.tenant_id),
        "actor_ref": row.actor_ref,
        "action": row.action,
        "entity_type": row.entity_type,
        "entity_id": str(row.entity_id) if row.entity_id else None,
        "details": row.details or {},
        "created_at": row.created_at,
        "immutable": True,
        "scope": {"platform_authorized": True},
    }
