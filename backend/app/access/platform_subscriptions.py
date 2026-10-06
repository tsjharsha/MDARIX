"""Platform administration: plans, subscriptions, usage, reminder policies and email templates."""

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.app.db.models.foundation import (
    AuditEvent,
    ConnectorConfiguration,
    FeatureEntitlement,
    PlanDefinition,
    Tenant,
    TenantPlanAssignment,
)
from backend.app.db.models.stage2 import (
    EmailTemplate,
    OutboxEvent,
    ReminderPolicy,
    SubscriptionLifecycle,
)
from backend.app.db.session import get_db
from backend.app.access.schemas import (
    EmailTemplateRequest,
    PlanCreateRequest,
    ReminderPolicyRequest,
    SubscriptionRequest,
)
from backend.app.access.authz import _require_platform_admin
from backend.app.access.schemas import TenantLimitsRequest

router = APIRouter(prefix="/api/v1", tags=["Access Control"])


@router.get("/platform-admin/plans")
def list_platform_plans(request: Request, db: Session = Depends(get_db)):
    """Platform plan catalog with feature and limit provenance."""
    _require_platform_admin(request, db)
    plans = db.query(PlanDefinition).order_by(PlanDefinition.code).all()
    result = []
    for plan in plans:
        features = db.query(FeatureEntitlement).filter(FeatureEntitlement.plan_id == plan.id).all()
        capabilities = {f.feature_code: bool(f.enabled) for f in features}
        limits = {}
        for feature in features:
            if feature.limits:
                limits.update(feature.limits)
        result.append(
            {
                "id": str(plan.id),
                "code": plan.code,
                "name": plan.name,
                "description": plan.description,
                "version": plan.version,
                "status": plan.status,
                "capabilities": capabilities,
                "limits": limits,
                "provenance": "PLAN",
            }
        )
    return result


@router.post("/platform-admin/plans")
def create_platform_plan(payload: PlanCreateRequest, request: Request, db: Session = Depends(get_db)):
    admin = _require_platform_admin(request, db)
    if db.query(PlanDefinition).filter(PlanDefinition.code == payload.code).first():
        raise HTTPException(409, detail={"code": "PLAN_EXISTS", "message": "Plan code already exists"})
    now = datetime.now(timezone.utc)
    plan = PlanDefinition(
        id=uuid.uuid4(),
        code=payload.code,
        name=payload.name,
        description=payload.description,
        version=payload.version,
        status="ACTIVE",
        effective_from=now,
        created_at=now,
        updated_at=now,
    )
    db.add(plan)
    db.flush()
    for code, enabled in payload.capabilities.items():
        db.add(
            FeatureEntitlement(
                id=uuid.uuid4(),
                plan_id=plan.id,
                feature_code=code,
                enabled=bool(enabled),
                limits=payload.limits if code == "ADMIN_CONTROL_PLANE" else {},
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
            action="PLAN_CREATED",
            entity_type="PlanDefinition",
            entity_id=plan.id,
            details={"code": plan.code, "version": plan.version},
            created_at=now,
        )
    )
    db.commit()
    return {"id": str(plan.id), "code": plan.code, "status": plan.status}


@router.get("/platform-admin/customers/{tenant_id}/subscription")
def get_platform_subscription(tenant_id: uuid.UUID, request: Request, db: Session = Depends(get_db)):
    _require_platform_admin(request, db)
    assignment = (
        db.query(TenantPlanAssignment)
        .filter(TenantPlanAssignment.tenant_id == tenant_id, TenantPlanAssignment.status == "ACTIVE")
        .order_by(TenantPlanAssignment.effective_from.desc())
        .first()
    )
    if assignment is None:
        raise HTTPException(
            404, detail={"code": "SUBSCRIPTION_NOT_FOUND", "message": "Active subscription is not available"}
        )
    plan = db.query(PlanDefinition).filter(PlanDefinition.id == assignment.plan_id).first()
    features = (
        db.query(FeatureEntitlement)
        .filter(FeatureEntitlement.plan_id == assignment.plan_id, FeatureEntitlement.status == "ACTIVE")
        .all()
    )
    limits = {}
    for feature in features:
        if feature.limits:
            limits.update(feature.limits)
    return {
        "subscription_id": str(assignment.id),
        "tenant_id": str(tenant_id),
        "plan_id": str(assignment.plan_id),
        "plan_code": plan.code if plan else None,
        "status": assignment.status,
        "effective_from": assignment.effective_from.isoformat() if assignment.effective_from else None,
        "effective_to": assignment.effective_to.isoformat() if assignment.effective_to else None,
        "limits": limits,
        "entitlements": [
            {"feature_code": f.feature_code, "enabled": f.enabled, "limits": f.limits or {}, "provenance": "PLAN"}
            for f in features
        ],
    }


@router.get("/platform-admin/subscriptions/{subscription_id}")
def get_platform_subscription_detail(subscription_id: uuid.UUID, request: Request, db: Session = Depends(get_db)):
    _require_platform_admin(request, db)
    assignment = db.query(TenantPlanAssignment).filter(TenantPlanAssignment.id == subscription_id).first()
    if assignment is None:
        raise HTTPException(404, detail={"code": "SUBSCRIPTION_NOT_FOUND", "message": "Subscription is not available"})
    plan = db.query(PlanDefinition).filter(PlanDefinition.id == assignment.plan_id).first()
    return {
        "subscription_id": str(assignment.id),
        "tenant_id": str(assignment.tenant_id),
        "plan_id": str(assignment.plan_id),
        "plan_code": plan.code if plan else None,
        "status": assignment.status,
        "effective_from": assignment.effective_from.isoformat() if assignment.effective_from else None,
        "effective_to": assignment.effective_to.isoformat() if assignment.effective_to else None,
        "scope": {"platform_authorized": True},
    }


def _usage_counts(db: Session, tenant_id: uuid.UUID) -> tuple[int, int, int]:
    """Seats, customer administrators and connectors counted exactly as the limits are enforced."""
    from backend.app.access.common import _seat_counts
    from backend.app.access.configuration import RETIRED_CONNECTOR_STATUSES

    seats = _seat_counts(db, tenant_id)
    connectors = (
        db.query(ConnectorConfiguration.id)
        .filter(
            ConnectorConfiguration.tenant_id == tenant_id,
            ~func.upper(ConnectorConfiguration.status).in_(RETIRED_CONNECTOR_STATUSES),
        )
        .count()
    )
    return seats["allocated_users"], seats["allocated_customer_admins"], connectors


@router.put("/platform-admin/customers/{tenant_id}/limits")
def set_tenant_limits(
    tenant_id: uuid.UUID, payload: TenantLimitsRequest, request: Request, db: Session = Depends(get_db)
):
    """Change one customer tenant's limits (its plan's other customers are not affected). A limit cannot go below
    what the tenant already uses; the change and its reason are in the tenant's audit trail."""
    admin = _require_platform_admin(request, db)
    if db.query(Tenant).filter(Tenant.id == tenant_id).first() is None:
        raise HTTPException(404, detail={"code": "TENANT_NOT_FOUND", "message": "Customer is not available"})
    assignment = (
        db.query(TenantPlanAssignment)
        .filter(TenantPlanAssignment.tenant_id == tenant_id, TenantPlanAssignment.status == "ACTIVE")
        .with_for_update()
        .first()
    )
    if assignment is None:
        raise HTTPException(
            409, detail={"code": "NO_ACTIVE_PLAN", "message": "Assign a plan to this tenant before setting its limits"}
        )
    requested = {
        key: value
        for key, value in {
            "licensed_users_limit": payload.licensed_users_limit,
            "customer_admin_limit": payload.customer_admin_limit,
            "connector_limit": payload.connector_limit,
        }.items()
        if value is not None
    }
    if not requested:
        raise HTTPException(422, detail={"code": "NOTHING_TO_CHANGE", "message": "Give at least one limit"})
    users, admins, connectors = _usage_counts(db, tenant_id)
    in_use = {"licensed_users_limit": users, "customer_admin_limit": admins, "connector_limit": connectors}
    too_low = {
        key: {"requested": value, "in_use": in_use[key]} for key, value in requested.items() if value < in_use[key]
    }
    if too_low:
        raise HTTPException(
            409,
            detail={
                "code": "LIMIT_BELOW_USAGE",
                "message": "A limit cannot be lower than what the tenant already uses",
                "limits": too_low,
            },
        )
    from backend.app.access.common import _active_plan_limits

    before = _active_plan_limits(db, tenant_id)
    assignment.limits = {**(assignment.limits or {}), **requested}
    now = datetime.now(timezone.utc)
    assignment.updated_at = now
    from backend.app.enterprise_audit import make_audit_event

    db.add(
        make_audit_event(
            tenant_id=tenant_id,
            actor_ref=str(admin.id),
            action="TENANT_LIMITS_CHANGED",
            entity_type="TenantPlanAssignment",
            entity_id=assignment.id,
            details={"source": "PLATFORM_ADMIN"},
            request=request,
            reason=payload.reason,
            old_values={key: before.get(key) for key in requested},
            new_values=requested,
            created_at=now,
        )
    )
    db.commit()
    return {"tenant_id": str(tenant_id), "limits": _active_plan_limits(db, tenant_id), "usage": in_use}


@router.get("/platform-admin/customers/{tenant_id}/usage")
def get_platform_usage(tenant_id: uuid.UUID, request: Request, db: Session = Depends(get_db)):
    _require_platform_admin(request, db)
    if db.query(Tenant).filter(Tenant.id == tenant_id).first() is None:
        raise HTTPException(404, detail={"code": "TENANT_NOT_FOUND", "message": "Customer is not available"})
    users, admins, connectors = _usage_counts(db, tenant_id)
    assignment = (
        db.query(TenantPlanAssignment)
        .filter(TenantPlanAssignment.tenant_id == tenant_id, TenantPlanAssignment.status == "ACTIVE")
        .first()
    )
    from backend.app.access.common import _active_plan_limits

    # The plan's limits with this tenant's own limits taking precedence (the same rule enforcement uses).
    limits = _active_plan_limits(db, tenant_id) if assignment else {}
    usage = {"licensed_users": users, "customer_admins": admins, "connectors": connectors}
    alerts = []
    for key, code in (
        ("customer_admins", "CUSTOMER_ADMIN_LIMIT_REACHED"),
        ("licensed_users", "LICENSED_USER_LIMIT_REACHED"),
        ("connectors", "CONNECTOR_LIMIT_NEAR"),
    ):
        limit_key = {
            "customer_admins": "customer_admin_limit",
            "licensed_users": "licensed_users_limit",
            "connectors": "connector_limit",
        }[key]
        limit = limits.get(limit_key)
        if isinstance(limit, int) and (
            (usage[key] >= limit) or (key == "connectors" and usage[key] >= max(0, limit - 1))
        ):
            alerts.append(code)
    return {
        "tenant_id": str(tenant_id),
        "usage": usage,
        "limits": limits,
        "alerts": alerts,
        "limit_change_authority": "PLATFORM_ADMIN_ONLY",
    }


def _assign_plan(db: Session, tenant_id: uuid.UUID, plan: PlanDefinition, now: datetime, reason: str) -> str | None:
    """Make `plan` the tenant's active plan assignment (the one plan columns, entitlements and limits read).

    The previous active assignment is ended (SUPERSEDED), not deleted, so the plan history stays visible.
    Returns the previous plan code, if any.
    """
    current = (
        db.query(TenantPlanAssignment)
        .filter(TenantPlanAssignment.tenant_id == tenant_id, TenantPlanAssignment.status == "ACTIVE")
        .all()
    )
    previous = None
    for assignment in current:
        if assignment.plan_id == plan.id:
            return plan.code
        old_plan = db.query(PlanDefinition).filter(PlanDefinition.id == assignment.plan_id).first()
        previous = old_plan.code if old_plan else None
        assignment.status, assignment.effective_to, assignment.updated_at = "SUPERSEDED", now, now
    db.add(
        TenantPlanAssignment(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            plan_id=plan.id,
            status="ACTIVE",
            effective_from=now,
            effective_to=None,
            reason=reason[:1000],
            created_at=now,
            updated_at=now,
        )
    )
    return previous


@router.post("/platform/customers/{tenant_id}/subscription")
def set_platform_subscription(
    tenant_id: uuid.UUID, payload: SubscriptionRequest, request: Request, db: Session = Depends(get_db)
):
    admin = _require_platform_admin(request, db)
    now = datetime.now(timezone.utc)
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    plan = (
        db.query(PlanDefinition).filter(PlanDefinition.id == payload.plan_id, PlanDefinition.status == "ACTIVE").first()
    )
    if tenant is None or plan is None:
        raise HTTPException(
            404, detail={"code": "SUBSCRIPTION_TARGET_NOT_FOUND", "message": "Tenant or active plan is not available"}
        )
    starts = datetime.fromisoformat(payload.starts_at.replace("Z", "+00:00"))
    expires = datetime.fromisoformat(payload.expires_at.replace("Z", "+00:00"))
    if expires <= starts:
        raise HTTPException(
            422, detail={"code": "INVALID_SUBSCRIPTION_WINDOW", "message": "Expiry must be after start"}
        )
    from backend.app.trial.service import FREE_TRIAL_PLAN, trial_subscription

    # A Free Trial moving to any other plan is a conversion: decided before the subscription row changes plan.
    converting = plan.code != FREE_TRIAL_PLAN and trial_subscription(db, tenant_id) is not None
    current = (
        db.query(SubscriptionLifecycle)
        .filter(
            SubscriptionLifecycle.tenant_id == tenant_id,
            SubscriptionLifecycle.status.in_(["ACTIVE", "GRACE", "EXPIRED"]),
        )
        .order_by(SubscriptionLifecycle.created_at.desc())
        .first()
    )
    if current:
        current.plan_id = plan.id
        current.plan_version = plan.version
        current.starts_at = starts
        current.expires_at = expires
        current.grace_ends_at = (
            datetime.fromisoformat(payload.grace_ends_at.replace("Z", "+00:00")) if payload.grace_ends_at else None
        )
        current.expiry_version += 1
        current.status = "ACTIVE"
        current.renewal_state = "RENEWED"
        current.updated_at = now
        row = current
    else:
        row = SubscriptionLifecycle(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            plan_id=plan.id,
            plan_version=plan.version,
            starts_at=starts,
            expires_at=expires,
            grace_ends_at=datetime.fromisoformat(payload.grace_ends_at.replace("Z", "+00:00"))
            if payload.grace_ends_at
            else None,
            created_at=now,
            updated_at=now,
        )
        db.add(row)
    previous_plan = _assign_plan(db, tenant_id, plan, now, payload.reason)
    promoted = _promote_trial_owner(db, tenant_id, admin, plan, now) if converting else None
    db.add(
        AuditEvent(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            actor_ref=str(admin.id),
            action="SUBSCRIPTION_CHANGED",
            entity_type="SubscriptionLifecycle",
            entity_id=row.id,
            details={
                "reason": payload.reason,
                "plan_version": plan.version,
                "plan_code": plan.code,
                "previous_plan_code": previous_plan,
            },
            created_at=now,
        )
    )
    db.commit()
    return {
        "subscription_id": str(row.id),
        "tenant_id": str(tenant_id),
        "status": row.status,
        "expiry_version": row.expiry_version,
        "expires_at": row.expires_at.isoformat(),
        "trial_converted": converting,
        "trial_owner_promoted": promoted,
    }


def _promote_trial_owner(db: Session, tenant_id: uuid.UUID, admin, plan: PlanDefinition, now: datetime) -> str | None:
    """Make the person who started a converted trial its Customer Administrator, so the organization can invite
    its users (trial workspaces have no administrator; free-trial colleagues are invited by the owner instead).

    Their sessions are ended: the next sign-in goes through the administrator rules (an authenticator app is
    required), and no session keeps the old role. Audited ``TRIAL_OWNER_PROMOTED`` in the customer's organization
    with the account id only. Returns the promoted user id, or None when there is no owner account to promote.
    """
    from auth.durable import revoke_user_sessions
    from backend.app.db.models.foundation import AuthUser
    from backend.app.enterprise_audit import make_audit_event
    from backend.app.role_codes import CUSTOMER_ADMIN, is_customer_admin_role
    from backend.app.trial.team import trial_request

    request = trial_request(db, tenant_id)
    if request is None:
        return None
    owner = (
        db.query(AuthUser)
        .filter(
            AuthUser.tenant_id == tenant_id,
            AuthUser.username == request.email.strip().lower(),
            func.upper(AuthUser.status).in_(["ACTIVE", "INVITED"]),
        )
        .with_for_update()
        .first()
    )
    if owner is None or is_customer_admin_role(owner.role):
        return None
    previous_role = owner.role
    owner.role = CUSTOMER_ADMIN
    owner.updated_at = now
    revoke_user_sessions(db, owner.id, tenant_id)
    db.add(
        make_audit_event(
            tenant_id=tenant_id,
            actor_ref=str(admin.id),
            action="TRIAL_OWNER_PROMOTED",
            entity_type="AuthUser",
            entity_id=owner.id,
            details={"user_id": str(owner.id), "plan_code": plan.code, "reason": "Free trial converted"},
            old_values={"role": previous_role},
            new_values={"role": CUSTOMER_ADMIN},
            created_at=now,
        )
    )
    return str(owner.id)


@router.get("/platform/subscriptions/expiring")
def expiring_subscriptions(request: Request, db: Session = Depends(get_db)):
    _require_platform_admin(request, db)
    now = datetime.now(timezone.utc)
    rows = (
        db.query(SubscriptionLifecycle).filter(SubscriptionLifecycle.status.in_(["ACTIVE", "GRACE", "EXPIRED"])).all()
    )
    return [
        {
            "subscription_id": str(row.id),
            "tenant_id": str(row.tenant_id),
            "status": row.status,
            "expires_at": row.expires_at.isoformat(),
            "days_remaining": (row.expires_at - now).days,
            "expiry_version": row.expiry_version,
        }
        for row in rows
    ]


DEFAULT_REMINDER_THRESHOLDS = [60, 30, 7]


def reminder_schedules(db: Session) -> dict:
    """Tenant id -> reminder days before expiry, from each tenant's newest active policy.

    A tenant without a policy is absent; the lifecycle run then uses 60, 30 and 7 days.
    """
    schedules: dict = {}
    for policy in (
        db.query(ReminderPolicy)
        .filter(func.upper(ReminderPolicy.status) == "ACTIVE")
        .order_by(ReminderPolicy.created_at.desc())
        .all()
    ):
        schedules.setdefault(policy.tenant_id, [int(value) for value in (policy.thresholds or [])])
    return schedules


def run_subscription_lifecycle_job(db: Session, actor_ref: str, now: datetime | None = None) -> dict:
    """Move expired subscriptions to grace or expiry (suspending the tenant) and queue renewal reminders.

    Idempotent: a reminder is queued once per subscription, stage and expiry version. Every status change is
    audited in the affected tenant. Run by the scheduler every hour and on demand by a Platform Administrator.
    """
    now = now or datetime.now(timezone.utc)
    queued = 0
    transitioned = 0
    rows = db.query(SubscriptionLifecycle).all()
    schedules = reminder_schedules(db)
    for row in rows:
        previous = row.status
        if row.expires_at <= now and row.grace_ends_at and row.grace_ends_at > now and row.status != "GRACE":
            row.status = "GRACE"
            transitioned += 1
        if row.expires_at <= now and (not row.grace_ends_at or row.grace_ends_at <= now) and row.status != "EXPIRED":
            row.status = "EXPIRED"
            transitioned += 1
            db.query(Tenant).filter(Tenant.id == row.tenant_id).update({"status": "SUSPENDED"})
        if row.status != previous:
            db.add(
                AuditEvent(
                    id=uuid.uuid4(),
                    tenant_id=row.tenant_id,
                    actor_ref=actor_ref,
                    action="SUBSCRIPTION_STATUS_CHANGED",
                    entity_type="SubscriptionLifecycle",
                    entity_id=row.id,
                    details={"from": previous, "to": row.status, "tenant_suspended": row.status == "EXPIRED"},
                    created_at=now,
                )
            )
        thresholds = schedules.get(row.tenant_id) or DEFAULT_REMINDER_THRESHOLDS
        for stage, threshold in ((f"{days}_DAY", days) for days in thresholds):
            if 0 <= (row.expires_at - now).days <= threshold:
                existing = (
                    db.query(OutboxEvent)
                    .filter(
                        OutboxEvent.tenant_id == row.tenant_id,
                        OutboxEvent.event_name == "SUBSCRIPTION_REMINDER",
                        OutboxEvent.payload["subscription_id"].as_string() == str(row.id),
                        OutboxEvent.payload["stage"].as_string() == stage,
                        OutboxEvent.payload["expiry_version"].as_integer() == row.expiry_version,
                    )
                    .first()
                )
                if not existing:
                    db.add(
                        OutboxEvent(
                            tenant_id=row.tenant_id,
                            event_name="SUBSCRIPTION_REMINDER",
                            aggregate_type="SubscriptionLifecycle",
                            aggregate_id=row.id,
                            payload={
                                "subscription_id": str(row.id),
                                "stage": stage,
                                "expiry_version": row.expiry_version,
                            },
                            occurred_at=now,
                        )
                    )
                    queued += 1
    return {"status": "COMPLETE", "queued": queued, "transitioned": transitioned, "idempotent": True}


@router.post("/platform/subscriptions/lifecycle/run")
def run_subscription_lifecycle(request: Request, db: Session = Depends(get_db)):
    admin = _require_platform_admin(request, db)
    now = datetime.now(timezone.utc)
    result = run_subscription_lifecycle_job(db, str(admin.id), now)
    db.add(
        AuditEvent(
            id=uuid.uuid4(),
            tenant_id=admin.tenant_id,
            actor_ref=str(admin.id),
            action="SUBSCRIPTION_LIFECYCLE_RUN",
            entity_type="SubscriptionLifecycle",
            details={"queued": result["queued"], "transitioned": result["transitioned"]},
            created_at=now,
        )
    )
    db.commit()
    return result


@router.post("/platform/subscriptions/{tenant_id}/reminder-policies")
def create_reminder_policy(
    tenant_id: uuid.UUID, payload: ReminderPolicyRequest, request: Request, db: Session = Depends(get_db)
):
    admin = _require_platform_admin(request, db)
    if payload.thresholds != sorted(set(payload.thresholds), reverse=True) or any(
        value < 0 for value in payload.thresholds
    ):
        raise HTTPException(
            422, detail={"code": "INVALID_REMINDER_THRESHOLDS", "message": "Thresholds must be unique and descending"}
        )
    now = datetime.now(timezone.utc)
    row = ReminderPolicy(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        name=payload.name,
        thresholds=payload.thresholds,
        timezone=payload.timezone,
        recipient_types=payload.recipient_types,
        version=payload.version,
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    db.add(
        AuditEvent(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            actor_ref=str(admin.id),
            action="REMINDER_POLICY_CREATED",
            entity_type="ReminderPolicy",
            entity_id=row.id,
            details={"version": row.version},
            created_at=now,
        )
    )
    db.commit()
    return {"id": str(row.id), "version": row.version, "status": row.status}


@router.post("/platform/subscriptions/{tenant_id}/email-templates")
def create_email_template(
    tenant_id: uuid.UUID, payload: EmailTemplateRequest, request: Request, db: Session = Depends(get_db)
):
    admin = _require_platform_admin(request, db)
    allowed = {"customer_name", "expiry_date", "days_remaining", "activation_link"}
    if set(payload.allowed_variables) - allowed:
        raise HTTPException(
            422,
            detail={
                "code": "TEMPLATE_VARIABLE_NOT_ALLOWED",
                "message": "Template contains an unsupported merge variable",
            },
        )
    now = datetime.now(timezone.utc)
    # The newest saved email for a stage is the one customers receive (backend/app/notifications.py); the versions
    # before it stay on record as SUPERSEDED.
    for previous in (
        db.query(EmailTemplate)
        .filter(
            EmailTemplate.tenant_id == tenant_id,
            EmailTemplate.stage == payload.stage,
            func.upper(EmailTemplate.status).in_(["ACTIVE", "DRAFT"]),
        )
        .all()
    ):
        previous.status = "SUPERSEDED"
        previous.updated_at = now
    row = EmailTemplate(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        stage=payload.stage,
        version=payload.version,
        subject=payload.subject,
        body=payload.body,
        allowed_variables=payload.allowed_variables,
        status="ACTIVE",
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    db.add(
        AuditEvent(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            actor_ref=str(admin.id),
            action="EMAIL_TEMPLATE_CREATED",
            entity_type="EmailTemplate",
            entity_id=row.id,
            details={"stage": row.stage, "version": row.version},
            created_at=now,
        )
    )
    db.commit()
    return {"id": str(row.id), "stage": row.stage, "version": row.version, "status": row.status}
