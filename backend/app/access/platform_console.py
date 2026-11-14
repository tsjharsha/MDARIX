"""Platform-wide views for the platform administrator's console: renewals, reminders, integration runs, AI
activity, the audit trail, security posture and operations.

Each view spans every tenant (system scope, platform administrator only) but returns operational metadata only:
tenant, status, counts, timings, actions and actors. Customer business content is never returned (no AI inputs
or outputs, no record payloads, no audit old/new values).
"""

from __future__ import annotations

import uuid
from collections import Counter
from datetime import date, datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import String, cast, func, or_, select, text
from sqlalchemy.orm import Session

from auth.emailer import smtp_configuration_status
from backend.app import support_access
from backend.app.access.authz import _require_platform_admin
from backend.app.access.platform_subscriptions import DEFAULT_REMINDER_THRESHOLDS
from backend.app.access.schemas import MailLogCheck, QueueItemsAction
from backend.app.access.trends import daily as _daily, per_day as _per_day, run_outcome, window
from backend.app.business_ids import wanted_ids
from backend.app.db.models.customer_lifecycle import Customer, ProvisioningJob, SupportAccessGrant
from backend.app.db.models.enterprise import ConnectorRun
from backend.app.db.models.foundation import (
    AIExecution,
    AuditEvent,
    AuthUser,
    PlanDefinition,
    Tenant,
    TenantPlanAssignment,
)
from backend.app.db.models.stage2 import EmailTemplate, OutboxEvent, ReminderPolicy, SubscriptionLifecycle
from backend.app.db.session import get_db
from backend.app.enterprise_audit import make_audit_event
from backend.app.sorting import order_query
from backend.app.worker_status import worker_status

router = APIRouter(prefix="/api/v1", tags=["Platform console"])

# Merge variables a reminder template may use (the server refuses any other).
TEMPLATE_VARIABLES = ["customer_name", "expiry_date", "days_remaining", "activation_link"]
# Platform tables that deliberately carry no row-level security policy (see migration md05_rls_system_scope).
RLS_EXCLUDED_TABLES = [
    "auth_users",
    "auth_sessions",
    "onboarding_requests",
    "provisioning_jobs",
    "provisioning_job_steps",
    "platform_incidents",
    "tenant_data_planes",
]


def _tenant_names(db: Session, tenant_ids) -> dict:
    """Tenant id -> {tenant_key, tenant_name, customer_name and both business identifiers} for the given tenants,
    in one query."""
    ids = {tenant_id for tenant_id in tenant_ids if tenant_id}
    if not ids:
        return {}
    rows = (
        db.query(
            Tenant.id,
            Tenant.tenant_key,
            Tenant.display_name,
            Tenant.name,
            Customer.display_name,
            Tenant.business_id,
            Customer.business_id,
        )
        .outerjoin(Customer, Customer.id == Tenant.customer_id)
        .filter(Tenant.id.in_(ids))
        .all()
    )
    return {
        row[0]: {
            "tenant_key": row[1],
            "tenant_name": row[2] or row[3],
            "customer_name": row[4],
            "tenant_business_id": row[5],
            "customer_business_id": row[6],
        }
        for row in rows
    }


def _with_tenant(item: dict, names: dict, tenant_id) -> dict:
    found = names.get(tenant_id, {})
    return {
        **item,
        "tenant_id": str(tenant_id) if tenant_id else None,
        "tenant_business_id": found.get("tenant_business_id"),
        "tenant_key": found.get("tenant_key"),
        "tenant_name": found.get("tenant_name"),
        "customer_name": found.get("customer_name"),
        "customer_business_id": found.get("customer_business_id"),
    }


def _iso(value) -> str | None:
    return value.isoformat() if value else None


def _page(page: int, page_size: int) -> tuple[int, int]:
    return max(1, page), min(100, max(1, page_size))


def _tenant_name_of(model):
    """The name a list shows for the tenant of each ``model`` row, as a sortable SQL expression."""
    return (
        select(func.coalesce(Tenant.display_name, Tenant.name))
        .where(Tenant.id == model.tenant_id)
        .correlate(model)
        .scalar_subquery()
    )


# Plans & Licensing ---------------------------------------------------------------------------------------------


@router.get("/platform-admin/console/renewals")
def subscription_renewals(request: Request, db: Session = Depends(get_db)):
    """Every licence with an end date, soonest first, with its tenant, plan and the reminders queued for it."""
    from backend.app.trial.scope import not_trial_clause

    _require_platform_admin(request, db)
    now = datetime.now(timezone.utc)
    # Free trials end on Trial organizations (TO-1), not among the renewals.
    rows = (
        db.query(SubscriptionLifecycle)
        .filter(not_trial_clause(SubscriptionLifecycle.tenant_id))
        .order_by(SubscriptionLifecycle.expires_at.asc())
        .all()
    )
    names = _tenant_names(db, [row.tenant_id for row in rows])
    plans = dict(db.query(PlanDefinition.id, PlanDefinition.name).all())
    queued = Counter(
        str(subscription_id)
        for (subscription_id,) in db.query(OutboxEvent.aggregate_id).filter(
            OutboxEvent.event_name == "SUBSCRIPTION_REMINDER"
        )
    )
    items = []
    for row in rows:
        days = (row.expires_at - now).days if row.expires_at else None
        items.append(
            _with_tenant(
                {
                    "subscription_id": str(row.id),
                    "subscription_business_id": row.business_id,
                    "plan_name": plans.get(row.plan_id),
                    "status": row.status,
                    "starts_at": _iso(row.starts_at),
                    "expires_at": _iso(row.expires_at),
                    "grace_ends_at": _iso(row.grace_ends_at),
                    "days_remaining": days,
                    "renewal_state": row.renewal_state,
                    "reminders_queued": queued.get(str(row.id), 0),
                },
                names,
                row.tenant_id,
            )
        )
    return {"items": items, "total": len(items)}


@router.get("/platform-admin/tenants/{tenant_id}/reminder-settings")
def tenant_reminder_settings(tenant_id: uuid.UUID, request: Request, db: Session = Depends(get_db)):
    """The reminder policy a tenant uses (its newest active one, or the default) and its email templates."""
    _require_platform_admin(request, db)
    if db.query(Tenant.id).filter(Tenant.id == tenant_id).first() is None:
        raise HTTPException(404, detail={"code": "TENANT_NOT_FOUND", "message": "Tenant is not available"})
    policy = (
        db.query(ReminderPolicy)
        .filter(ReminderPolicy.tenant_id == tenant_id, func.upper(ReminderPolicy.status) == "ACTIVE")
        .order_by(ReminderPolicy.created_at.desc())
        .first()
    )
    templates = (
        db.query(EmailTemplate)
        .filter(EmailTemplate.tenant_id == tenant_id)
        .order_by(EmailTemplate.stage, EmailTemplate.created_at.desc())
        .all()
    )
    return {
        "policy": {
            "id": str(policy.id),
            "name": policy.name,
            "thresholds": list(policy.thresholds or []),
            "timezone": policy.timezone,
            "recipient_types": list(policy.recipient_types or []),
            "version": policy.version,
            "created_at": _iso(policy.created_at),
        }
        if policy
        else None,
        "default_thresholds": DEFAULT_REMINDER_THRESHOLDS,
        "templates": [
            {
                "id": str(row.id),
                "stage": row.stage,
                "version": row.version,
                "subject": row.subject,
                "body": row.body,
                "status": row.status,
                "created_at": _iso(row.created_at),
            }
            for row in templates
        ],
        "template_variables": TEMPLATE_VARIABLES,
    }


# Integrations --------------------------------------------------------------------------------------------------


@router.get("/platform-admin/console/integration-runs")
def integration_runs(
    request: Request,
    status: str = "",
    tenant_id: uuid.UUID | None = None,
    q: str = "",
    reconciled: bool = False,
    page: int = 1,
    page_size: int = 25,
    sort: str = "",
    order: str = "",
    db: Session = Depends(get_db),
):
    """Connector runs across every tenant, newest first, with a 30-day summary by outcome.

    ``reconciled`` keeps only runs that were reconciled against their source (any result). ``sort``/``order`` order
    every page by a column instead (backend/app/sorting.py).
    """
    _require_platform_admin(request, db)
    page, page_size = _page(page, page_size)
    query = db.query(ConnectorRun)
    if status.strip():
        if status.strip().upper() == "PROBLEMS":
            query = query.filter(
                or_(
                    func.upper(ConnectorRun.status).in_(["FAILED", "PARTIAL", "ERROR"]),
                    ConnectorRun.failure_category.is_not(None),
                    ConnectorRun.records_rejected > 0,
                )
            )
        else:
            query = query.filter(func.upper(ConnectorRun.status) == status.strip().upper())
    if tenant_id:
        query = query.filter(ConnectorRun.tenant_id == tenant_id)
    if reconciled:
        query = query.filter(ConnectorRun.reconciliation_status.is_not(None))
    if q.strip():
        like = f"%{q.strip().lower()}%"
        query = query.filter(
            or_(func.lower(ConnectorRun.source_system).like(like), func.lower(ConnectorRun.connection_id).like(like))
        )
    total = query.count()
    query = order_query(
        query,
        sort,
        order,
        columns={
            "when": [ConnectorRun.started_at],
            "started_at": [ConnectorRun.started_at],
            "completed_at": [ConnectorRun.completed_at],
            "tenant": [_tenant_name_of(ConnectorRun)],
            "tenant_name": [_tenant_name_of(ConnectorRun)],
            "source": [ConnectorRun.source_system, ConnectorRun.connection_id],
            "source_system": [ConnectorRun.source_system],
            "connection_id": [ConnectorRun.connection_id],
            "run_type": [ConnectorRun.run_type],
            "records": [ConnectorRun.records_received],
            "records_received": [ConnectorRun.records_received],
            "records_accepted": [ConnectorRun.records_accepted],
            "records_rejected": [ConnectorRun.records_rejected],
            "records_quarantined": [ConnectorRun.records_quarantined],
            "records_duplicate": [ConnectorRun.records_duplicate],
            "retry_attempt": [ConnectorRun.retry_attempt],
            "status": [ConnectorRun.status],
            "reconciliation": [ConnectorRun.reconciliation_status],
            "reconciliation_status": [ConnectorRun.reconciliation_status],
            "schema_drift_status": [ConnectorRun.schema_drift_status],
            "failure_category": [ConnectorRun.failure_category],
            "problem": [ConnectorRun.failure_category, ConnectorRun.schema_drift_status, ConnectorRun.records_rejected],
        },
        default=[ConnectorRun.started_at.desc()],
        tiebreak=[ConnectorRun.id],
    )
    rows = query.offset((page - 1) * page_size).limit(page_size).all()
    names = _tenant_names(db, [row.tenant_id for row in rows])
    since = datetime.now(timezone.utc) - timedelta(days=30)
    summary = dict(
        db.query(func.upper(ConnectorRun.status), func.count(ConnectorRun.id))
        .filter(ConnectorRun.started_at >= since)
        .group_by(func.upper(ConnectorRun.status))
        .all()
    )
    reconciliation = dict(
        db.query(func.upper(ConnectorRun.reconciliation_status), func.count(ConnectorRun.id))
        .filter(ConnectorRun.started_at >= since, ConnectorRun.reconciliation_status.is_not(None))
        .group_by(func.upper(ConnectorRun.reconciliation_status))
        .all()
    )
    items = [
        _with_tenant(
            {
                "id": str(row.id),
                "source_system": row.source_system,
                "connection_id": row.connection_id,
                "run_type": row.run_type,
                "status": row.status,
                "records_received": row.records_received,
                "records_accepted": row.records_accepted,
                "records_rejected": row.records_rejected,
                "records_quarantined": row.records_quarantined,
                "records_duplicate": row.records_duplicate,
                "retry_attempt": row.retry_attempt,
                "reconciliation_status": row.reconciliation_status,
                "schema_drift_status": row.schema_drift_status,
                "failure_category": row.failure_category,
                "started_at": _iso(row.started_at),
                "completed_at": _iso(row.completed_at),
            },
            names,
            row.tenant_id,
        )
        for row in rows
    ]
    return {
        "items": items,
        "total": total,
        "page": page,
        "pages": max(1, (total + page_size - 1) // page_size),
        "last_30_days": {"by_status": summary, "by_reconciliation": reconciliation},
    }


# AI Control Center ---------------------------------------------------------------------------------------------


@router.get("/platform-admin/console/ai-activity")
def ai_activity(request: Request, days: int = 30, db: Session = Depends(get_db)):
    """AI executions across every tenant: totals, failures, latency, by tenant and model, and the latest runs.

    Metadata only: what ran, where, when, how long and whether it validated. Inputs and outputs stay with the tenant.
    """
    _require_platform_admin(request, db)
    days = min(365, max(1, days))
    since = datetime.now(timezone.utc) - timedelta(days=days)
    window = db.query(AIExecution).filter(AIExecution.execution_timestamp >= since)
    total = window.count()
    failed = window.filter(AIExecution.error_state.is_not(None)).count()
    latencies = sorted(
        value
        for (value,) in db.query(AIExecution.latency_ms).filter(
            AIExecution.execution_timestamp >= since, AIExecution.latency_ms.is_not(None)
        )
    )
    p95 = latencies[min(len(latencies) - 1, int(len(latencies) * 0.95))] if latencies else None
    by_tenant_rows = (
        db.query(AIExecution.tenant_id, func.count(AIExecution.id))
        .filter(AIExecution.execution_timestamp >= since)
        .group_by(AIExecution.tenant_id)
        .order_by(func.count(AIExecution.id).desc())
        .limit(10)
        .all()
    )
    by_model = [
        {"provider": row[0], "model": row[1], "count": row[2]}
        for row in db.query(AIExecution.provider, AIExecution.model_name, func.count(AIExecution.id))
        .filter(AIExecution.execution_timestamp >= since)
        .group_by(AIExecution.provider, AIExecution.model_name)
        .order_by(func.count(AIExecution.id).desc())
        .all()
    ]
    by_validation: dict = {}
    for status, count in (
        db.query(func.upper(AIExecution.validation_status), func.count(AIExecution.id))
        .filter(AIExecution.execution_timestamp >= since)
        .group_by(func.upper(AIExecution.validation_status))
        .all()
    ):
        key = status or "NOT_RECORDED"
        by_validation[key] = by_validation.get(key, 0) + count
    latest = db.query(AIExecution).order_by(AIExecution.execution_timestamp.desc()).limit(50).all()
    names = _tenant_names(db, [row[0] for row in by_tenant_rows] + [row.tenant_id for row in latest])
    return {
        "window_days": days,
        "total": total,
        "failed": failed,
        "p95_latency_ms": p95,
        "by_tenant": [_with_tenant({"count": row[1]}, names, row[0]) for row in by_tenant_rows],
        "by_model": by_model,
        "by_validation": by_validation,
        "latest": [
            _with_tenant(
                {
                    "id": str(row.id),
                    "business_id": row.business_id,
                    "at": _iso(row.execution_timestamp),
                    "provider": row.provider,
                    "model": row.model_name,
                    "model_version": row.model_version,
                    "prompt_version": row.prompt_template_version,
                    "validation_status": row.validation_status,
                    "confidence": row.confidence_label,
                    "latency_ms": row.latency_ms,
                    "failed": row.error_state is not None,
                },
                names,
                row.tenant_id,
            )
            for row in latest
        ],
    }


# Security ------------------------------------------------------------------------------------------------------


def _actor_names(db: Session, refs) -> dict:
    """User id -> {name, business_id} for the references that are user ids, in one query."""
    ids = wanted_ids(refs)
    if not ids:
        return {}
    return {
        str(row[0]): {"name": row[1] or row[2], "business_id": row[3]}
        for row in db.query(AuthUser.id, AuthUser.display_name, AuthUser.username, AuthUser.business_id).filter(
            AuthUser.id.in_(ids)
        )
    }


@router.get("/platform-admin/console/audit")
def platform_audit(
    request: Request,
    q: str = "",
    tenant_id: uuid.UUID | None = None,
    attention: bool = False,
    page: int = 1,
    page_size: int = 50,
    sort: str = "",
    order: str = "",
    db: Session = Depends(get_db),
):
    """The audit trail across organizations, newest first: who did what, where and why (never old/new values).
    It shows the platform's own events, what MDARIX staff did anywhere, and the rest of an organization's trail only
    where its administrators approved Audit access (backend/app/support_access.py); ``complete`` says whether a
    filtered organization's trail is shown in full. ``sort``/``order`` order every page by a column instead
    (backend/app/sorting.py)."""
    admin = _require_platform_admin(request, db)
    page, page_size = _page(page, page_size)
    opened = support_access.open_tenants(
        db, admin, support_access.AUDIT, within={tenant_id} if tenant_id else None, request=request
    )
    query = db.query(AuditEvent).filter(support_access.visible_audit_clause(opened))
    if tenant_id:
        query = query.filter(AuditEvent.tenant_id == tenant_id)
    if attention:
        query = query.filter(
            or_(
                AuditEvent.action.like("%DENIED%"),
                AuditEvent.action.like("%FAILED%"),
                AuditEvent.action.like("%SUSPEND%"),
                AuditEvent.action.like("%REVOKE%"),
            )
        )
    if q.strip():
        like = f"%{q.strip().lower()}%"
        query = query.filter(
            or_(func.lower(AuditEvent.action).like(like), func.lower(AuditEvent.entity_type).like(like))
        )
    total = query.count()
    actor_name = func.coalesce(
        select(func.coalesce(AuthUser.display_name, AuthUser.username))
        .where(cast(AuthUser.id, String) == AuditEvent.actor_ref)
        .correlate(AuditEvent)
        .scalar_subquery(),
        AuditEvent.actor_ref,
    )
    reason = func.coalesce(AuditEvent.reason, AuditEvent.details["reason"].astext)
    query = order_query(
        query,
        sort,
        order,
        columns={
            "when": [AuditEvent.created_at],
            "at": [AuditEvent.created_at],
            "tenant": [_tenant_name_of(AuditEvent)],
            "tenant_name": [_tenant_name_of(AuditEvent)],
            "who": [actor_name],
            "actor": [actor_name],
            "what": [AuditEvent.action, AuditEvent.entity_type],
            "action": [AuditEvent.action],
            "entity_type": [AuditEvent.entity_type],
            "why": [reason],
            "reason": [reason],
            "source_ip": [AuditEvent.source_ip],
        },
        default=[AuditEvent.created_at.desc()],
        tiebreak=[AuditEvent.id],
    )
    rows = query.offset((page - 1) * page_size).limit(page_size).all()
    names = _tenant_names(db, [row.tenant_id for row in rows])
    actors = _actor_names(db, [row.actor_ref for row in rows])
    items = []
    for row in rows:
        details = row.details if isinstance(row.details, dict) else {}
        actor = actors.get(str(row.actor_ref), {})
        items.append(
            _with_tenant(
                {
                    "id": str(row.id),
                    "at": _iso(row.created_at),
                    "action": row.action,
                    "entity_type": row.entity_type,
                    "actor": actor.get("name") or (row.actor_ref if row.actor_ref else None),
                    "actor_business_id": actor.get("business_id"),
                    "reason": row.reason or details.get("reason"),
                    "source": details.get("source"),
                    "source_ip": row.source_ip,
                },
                names,
                row.tenant_id,
            )
        )
    return {
        "items": items,
        "total": total,
        "page": page,
        "pages": max(1, (total + page_size - 1) // page_size),
        "complete": bool(tenant_id) and tenant_id in opened,
    }


@router.get("/platform-admin/console/security")
def security_posture(request: Request, db: Session = Depends(get_db)):
    """Tenant isolation, sign-in protection, support access, data residency and retention, from live records."""
    _require_platform_admin(request, db)
    now = datetime.now(timezone.utc)
    tenant_tables = db.execute(
        text(
            "SELECT c.relname, c.relrowsecurity FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE n.nspname = current_schema() AND c.relkind IN ('r', 'p') AND EXISTS ("
            "SELECT 1 FROM information_schema.columns k WHERE k.table_schema = n.nspname "
            "AND k.table_name = c.relname AND k.column_name = 'tenant_id')"
        )
    ).all()
    protected = sorted(name for name, enabled in tenant_tables if enabled)
    unprotected = sorted(name for name, enabled in tenant_tables if not enabled)
    active_accounts = db.query(AuthUser).filter(func.upper(AuthUser.status) == "ACTIVE")
    grants = dict(
        db.query(func.upper(SupportAccessGrant.status), func.count(SupportAccessGrant.id))
        .group_by(func.upper(SupportAccessGrant.status))
        .all()
    )
    residency = [
        {"region": row[0] or "UNSPECIFIED", "tenants": row[1]}
        for row in db.query(Tenant.residency_region, func.count(Tenant.id))
        .group_by(Tenant.residency_region)
        .order_by(func.count(Tenant.id).desc())
        .all()
    ]
    since = now - timedelta(days=30)
    denied = (
        db.query(AuditEvent.action, func.count(AuditEvent.id))
        .filter(
            AuditEvent.created_at >= since,
            or_(AuditEvent.action.like("%DENIED%"), AuditEvent.action.like("%FAILED%")),
        )
        .group_by(AuditEvent.action)
        .order_by(func.count(AuditEvent.id).desc())
        .limit(8)
        .all()
    )
    audit_total = db.query(func.count(AuditEvent.id)).scalar() or 0
    oldest, earliest_release = db.query(func.min(AuditEvent.created_at), func.min(AuditEvent.retention_until)).one()
    return {
        "isolation": {
            "tenant_tables": len(tenant_tables),
            "protected": len(protected),
            "unprotected": unprotected,
            "excluded_by_design": [name for name in unprotected if name in RLS_EXCLUDED_TABLES],
            "unexpected": [name for name in unprotected if name not in RLS_EXCLUDED_TABLES],
        },
        "sign_in": {
            "active_accounts": active_accounts.count(),
            "mfa_required": active_accounts.filter(AuthUser.mfa_required.is_(True)).count(),
            "mfa_enrolled": active_accounts.filter(AuthUser.mfa_enrolled_at.is_not(None)).count(),
        },
        "support_access": grants,
        "residency": residency,
        "denied_or_failed_30_days": [{"action": row[0], "count": row[1]} for row in denied],
        "retention": {
            "audit_events": audit_total,
            "oldest_event_at": _iso(oldest),
            "earliest_release_at": _iso(earliest_release),
            "policy": "Audit events are append-only and kept for at least 7 years.",
        },
    }


@router.get("/platform-admin/console/support-access")
def support_access_overview(request: Request, db: Session = Depends(get_db)):
    """Support access grants with readable tenant and person names, newest first: where each stands (waiting for
    MDARIX's approval, waiting for the customer, active, denied, revoked, expired), what it covers and who decided."""
    _require_platform_admin(request, db)
    support_access.expire(db)
    db.commit()
    rows = db.query(SupportAccessGrant).order_by(SupportAccessGrant.created_at.desc()).limit(200).all()
    names = _tenant_names(db, [row.tenant_id for row in rows])
    people = _actor_names(
        db,
        [row.platform_user_id for row in rows]
        + [row.requested_by for row in rows]
        + [row.approved_by for row in rows]
        + [row.customer_decided_by for row in rows],
    )
    now = datetime.now(timezone.utc)
    items = []
    for row in rows:
        status = (row.status or "").upper()
        scope = support_access.SupportScope.stored(row.scope)
        open_ = status in support_access.OPEN and bool(row.expires_at and row.expires_at > now)
        person = people.get(str(row.platform_user_id), {})
        approver = people.get(str(row.approved_by), {}) if row.approved_by else {}
        customer = people.get(str(row.customer_decided_by), {}) if row.customer_decided_by else {}
        items.append(
            _with_tenant(
                {
                    "id": str(row.id),
                    "person": person.get("name"),
                    "platform_user_id": str(row.platform_user_id),
                    "platform_user_business_id": person.get("business_id"),
                    "requested_by": people.get(str(row.requested_by), {}).get("name") if row.requested_by else None,
                    "scope": scope.as_dict(),
                    "areas": scope.describe(),
                    "write": scope.write,
                    "reason": row.reason,
                    "status": status if open_ or status not in support_access.OPEN else support_access.EXPIRED,
                    "starts_at": _iso(row.starts_at),
                    "expires_at": _iso(row.expires_at),
                    "approved_by": approver.get("name"),
                    "approved_by_business_id": approver.get("business_id"),
                    "customer_decided_by": customer.get("name"),
                    "customer_decided_at": _iso(row.customer_decided_at),
                    "customer_decision_reason": row.customer_decision_reason,
                    "can_approve": status == support_access.PENDING and open_,
                    "can_revoke": open_,
                },
                names,
                row.tenant_id,
            )
        )
    return {"items": items, "areas": [{"code": code, "label": label} for code, label in support_access.AREAS.items()]}


# Operations ----------------------------------------------------------------------------------------------------


@router.get("/platform-admin/console/operations")
def operations_overview(request: Request, db: Session = Depends(get_db)):
    """Queues, background jobs and email delivery across the platform."""
    _require_platform_admin(request, db)
    database_ok = True
    try:
        db.execute(text("SELECT 1"))
    except Exception:  # pragma: no cover - reported, not raised
        database_ok = False
    outbox = db.query(OutboxEvent)
    pending = outbox.filter(OutboxEvent.published_at.is_(None), OutboxEvent.dead_lettered_at.is_(None))
    by_event = [
        {"event": row[0], "pending": row[1]}
        for row in pending.with_entities(OutboxEvent.event_name, func.count(OutboxEvent.id))
        .group_by(OutboxEvent.event_name)
        .order_by(func.count(OutboxEvent.id).desc())
        .limit(10)
        .all()
    ]
    oldest_pending = pending.with_entities(func.min(OutboxEvent.occurred_at)).scalar()
    jobs = dict(
        db.query(func.upper(ProvisioningJob.status), func.count(ProvisioningJob.id))
        .group_by(func.upper(ProvisioningJob.status))
        .all()
    )
    recent_jobs = db.query(ProvisioningJob).order_by(ProvisioningJob.created_at.desc()).limit(10).all()
    names = _tenant_names(db, [row.tenant_id for row in recent_jobs])
    smtp = smtp_configuration_status()
    worker = worker_status(db, with_metrics=True)
    return {
        "database": "OK" if database_ok else "UNAVAILABLE",
        "worker_heartbeat": worker["state"],
        "worker": worker,
        "queue": {
            "pending": pending.count(),
            "retrying": pending.filter(OutboxEvent.attempts > 0).count(),
            "dead_lettered": outbox.filter(OutboxEvent.dead_lettered_at.is_not(None)).count(),
            "published": outbox.filter(OutboxEvent.published_at.is_not(None)).count(),
            "oldest_pending_at": _iso(oldest_pending),
            "pending_by_event": by_event,
        },
        "provisioning_jobs": {
            "by_status": jobs,
            "recent": [
                _with_tenant(
                    {
                        "id": str(row.id),
                        "job_identifier": row.job_identifier,
                        "status": row.status,
                        "retry_count": row.retry_count,
                        "created_at": _iso(row.created_at),
                        "completed_at": _iso(row.completed_at),
                    },
                    names,
                    row.tenant_id,
                )
                for row in recent_jobs
            ],
        },
        "email": {
            "configured": bool(smtp.get("configured")),
            "present": smtp.get("present", {}),
            "sender_domain_verified": bool(smtp.get("sender_domain_verified")),
            "reminders_pending": pending.filter(OutboxEvent.event_name == "SUBSCRIPTION_REMINDER").count(),
            "reminders_dead_lettered": outbox.filter(
                OutboxEvent.event_name == "SUBSCRIPTION_REMINDER", OutboxEvent.dead_lettered_at.is_not(None)
            ).count(),
            # The outbox worker emails queued reminders (backend/app/notifications.py); without SMTP it acknowledges
            # them without sending, so delivery is only CONNECTED when email is configured.
            "reminder_delivery": "CONNECTED" if smtp.get("configured") else "EMAIL_NOT_CONFIGURED",
        },
    }


# Work that gave up after its retries ---------------------------------------------------------------------------

DEAD_LETTER_LIMIT = 500
# The marker scripts/recovery_check.py (B6b Part D, D1 step 6) leaves on every event a restored copy had not sent:
# dead-lettered with this last_error and an OUTBOX_EVENTS_HELD_AFTER_RESTORE audit record. Production may already have
# sent it, so it is retried only when the mail provider's log, checked and recorded here, shows it was not delivered.
HELD_AFTER_RESTORE = "held after restore"
MAIL_LOG_CHECKED = "OUTBOX_MAIL_LOG_CHECKED"
NOT_DELIVERED = "NOT_DELIVERED"


def _dead_letter_summary(row: OutboxEvent) -> dict:
    """What was queued and why it gave up; never the payload, which can hold customer business data."""
    return {
        "id": str(row.id),
        "event_name": row.event_name,
        "aggregate_type": row.aggregate_type,
        "attempts": row.attempts,
        "last_error": row.last_error,
        "occurred_at": _iso(row.occurred_at),
        "dead_lettered_at": _iso(row.dead_lettered_at),
    }


@router.get("/platform-admin/console/dead-letters")
def dead_letters(request: Request, db: Session = Depends(get_db)):
    """Background work that gave up after its retries, newest first, with the tenant it belongs to."""
    _require_platform_admin(request, db)
    query = db.query(OutboxEvent).filter(OutboxEvent.dead_lettered_at.is_not(None))
    rows = query.order_by(OutboxEvent.dead_lettered_at.desc()).limit(DEAD_LETTER_LIMIT).all()
    names = _tenant_names(db, [row.tenant_id for row in rows])
    return {
        "total": query.count(),
        "items": [_with_tenant(_dead_letter_summary(row), names, row.tenant_id) for row in rows],
    }


def _act_on_dead_letters(request: Request, body: QueueItemsAction, db: Session, *, discard: bool) -> dict:
    admin = _require_platform_admin(request, db)
    ids = set(body.ids)
    rows = (
        db.query(OutboxEvent)
        .filter(OutboxEvent.id.in_(ids), OutboxEvent.dead_lettered_at.is_not(None))
        .with_for_update()
        .all()
    )
    if len(rows) != len(ids):
        # Someone else retried or discarded part of the selection: act on all of it or on none of it.
        raise HTTPException(
            409,
            detail={
                "code": "QUEUE_ITEMS_CHANGED",
                "message": "Some of these items are no longer waiting for a decision. Reload and try again.",
            },
        )
    now = datetime.now(timezone.utc)
    by_tenant: dict = {}
    for row in rows:
        by_tenant.setdefault(row.tenant_id, []).append(row)
    if not discard:
        _refuse_held_unless_not_delivered(request, db, admin, rows, body.reason, now)
    action = "OUTBOX_EVENTS_DISCARDED" if discard else "OUTBOX_EVENTS_RETRIED"
    # One audit record per tenant, written before the change, naming every item (without its payload) and the reason.
    for tenant_id, items in by_tenant.items():
        db.add(
            make_audit_event(
                tenant_id=tenant_id,
                actor_ref=str(admin.id),
                action=action,
                entity_type="OutboxEvent",
                details={
                    "source": "PLATFORM_ADMIN",
                    "count": len(items),
                    "items": [_dead_letter_summary(row) for row in items],
                },
                request=request,
                reason=body.reason,
                created_at=now,
            )
        )
    for row in rows:
        if discard:
            db.delete(row)
        else:
            # Back in the queue with a fresh set of retries; the worker picks it up on its next cycle.
            row.dead_lettered_at = None
            row.attempts = 0
            row.next_attempt_at = now
            row.last_error = None
            row.claimed_by = None
            row.claimed_at = None
    db.commit()
    return {"count": len(rows), "action": "DISCARDED" if discard else "RETRIED"}


def mail_log_results(db: Session, held: list[OutboxEvent]) -> dict[str, str]:
    """The latest recorded mail-log check of each held event, made after it was held: event id -> result."""
    if not held:
        return {}
    wanted = {str(row.id) for row in held}
    found: dict[str, str] = {}
    records = (
        db.query(AuditEvent)
        .filter(
            AuditEvent.action == MAIL_LOG_CHECKED,
            AuditEvent.tenant_id.in_({row.tenant_id for row in held}),
            AuditEvent.created_at >= min(row.dead_lettered_at for row in held),
        )
        .order_by(AuditEvent.created_at.desc())
    )
    held_at = {str(row.id): row.dead_lettered_at for row in held}
    for record in records:
        for item in (record.details or {}).get("items", []):
            event_id = item.get("id")
            if event_id in wanted and event_id not in found and record.created_at >= held_at[event_id]:
                found[event_id] = item.get("result")
    return found


def _refuse_held_unless_not_delivered(request: Request, db: Session, admin, rows, reason: str, now) -> None:
    """B6b-D10: an event held after a restore is retried only when its recorded mail-log check says NOT_DELIVERED.
    Otherwise the whole selection is refused (409 HELD_AFTER_RESTORE) and the refusal is audited."""
    held = [row for row in rows if row.last_error == HELD_AFTER_RESTORE]
    results = mail_log_results(db, held)
    blocked = [row for row in held if results.get(str(row.id)) != NOT_DELIVERED]
    if not blocked:
        return
    by_tenant: dict = {}
    for row in blocked:
        by_tenant.setdefault(row.tenant_id, []).append(row)
    for tenant_id, items in by_tenant.items():
        db.add(
            make_audit_event(
                tenant_id=tenant_id,
                actor_ref=str(admin.id),
                action="OUTBOX_RETRY_REFUSED",
                entity_type="OutboxEvent",
                details={
                    "source": "PLATFORM_ADMIN",
                    "code": "HELD_AFTER_RESTORE",
                    "count": len(items),
                    "items": [
                        {**_dead_letter_summary(row), "mail_log": results.get(str(row.id)) or "NOT_CHECKED"}
                        for row in items
                    ],
                },
                request=request,
                reason=reason,
                created_at=now,
            )
        )
    db.commit()
    raise HTTPException(
        409,
        detail={
            "code": "HELD_AFTER_RESTORE",
            "message": f"{len(blocked)} of these items were held after a restore and may already have been sent. "
            "Retry one only after the mail provider's log, recorded here, shows it was not delivered.",
            "ids": [str(row.id) for row in blocked],
        },
    )


@router.post("/platform-admin/console/dead-letters/mail-log-check")
def record_mail_log_check(request: Request, body: MailLogCheck, db: Session = Depends(get_db)):
    """Record what the mail provider's log showed for events held after a restore (B6b-D10), with where it was
    checked. One audit record per tenant; only events held after a restore can be recorded."""
    admin = _require_platform_admin(request, db)
    ids = set(body.ids)
    rows = (
        db.query(OutboxEvent)
        .filter(
            OutboxEvent.id.in_(ids),
            OutboxEvent.dead_lettered_at.is_not(None),
            OutboxEvent.last_error == HELD_AFTER_RESTORE,
        )
        .all()
    )
    if len(rows) != len(ids):
        raise HTTPException(
            409,
            detail={
                "code": "NOT_HELD_AFTER_RESTORE",
                "message": "Only events held after a restore are checked against the mail provider's log.",
            },
        )
    now = datetime.now(timezone.utc)
    by_tenant: dict = {}
    for row in rows:
        by_tenant.setdefault(row.tenant_id, []).append(row)
    for tenant_id, items in by_tenant.items():
        db.add(
            make_audit_event(
                tenant_id=tenant_id,
                actor_ref=str(admin.id),
                action=MAIL_LOG_CHECKED,
                entity_type="OutboxEvent",
                details={
                    "source": "PLATFORM_ADMIN",
                    "count": len(items),
                    "items": [
                        {"id": str(row.id), "event_name": row.event_name, "result": body.result} for row in items
                    ],
                },
                request=request,
                reason=body.reason,
                created_at=now,
            )
        )
    db.commit()
    return {"count": len(rows), "result": body.result}


@router.post("/platform-admin/console/dead-letters/retry")
def retry_dead_letters(request: Request, body: QueueItemsAction, db: Session = Depends(get_db)):
    """Put work that gave up back in the queue (for example after the cause was fixed). Recorded with a reason."""
    return _act_on_dead_letters(request, body, db, discard=False)


@router.post("/platform-admin/console/dead-letters/discard")
def discard_dead_letters(request: Request, body: QueueItemsAction, db: Session = Depends(get_db)):
    """Remove work that gave up and is not needed (for example test leftovers). Recorded with a reason."""
    return _act_on_dead_letters(request, body, db, discard=True)


# Dashboard ------------------------------------------------------------------------------------------------------


@router.get("/platform-admin/console/dashboard")
def dashboard_trends(request: Request, days: int = 30, db: Session = Depends(get_db)):
    """Platform-wide daily activity for the dashboard (AI runs, integration runs, audit events, new tenants) and
    the shape of the customer base (tenants by plan and data region, licences ending by month)."""
    _require_platform_admin(request, db)
    days, today, since = window(days)

    def per_day(column, *conditions, key=None) -> list[tuple]:
        return _per_day(db, since, column, *conditions, key=key)

    # Group on plain column expressions (no bound values, which Postgres would not match in GROUP BY), then label.
    ai_rows = [
        (day, "completed" if ok else "failed", count)
        for day, ok, count in per_day(AIExecution.execution_timestamp, key=AIExecution.error_state.is_(None))
    ]

    run_rows = [
        (day, run_outcome(status), count)
        for day, status, count in per_day(ConnectorRun.started_at, key=func.upper(ConnectorRun.status))
    ]
    refused = or_(AuditEvent.action.like("%DENIED%"), AuditEvent.action.like("%FAILED%"))
    audit_total = per_day(AuditEvent.created_at)
    audit_refused = per_day(AuditEvent.created_at, refused)
    audit_rows = [(day, "events", count) for day, _, count in audit_total] + [
        (day, "refused", count) for day, _, count in audit_refused
    ]
    from backend.app.trial import admin_actions
    from backend.app.trial.scope import not_trial_clause, trial_tenant_clause

    # Customers and free trials are counted apart (TO-1): two series of new organizations per day.
    tenant_rows = [
        (day, "customers", count) for day, _, count in per_day(Tenant.created_at, not_trial_clause(Tenant.id))
    ] + [(day, "trials", count) for day, _, count in per_day(Tenant.created_at, trial_tenant_clause(Tenant.id))]

    plans: Counter = Counter()
    latest: dict = {}
    for tenant_id, name, effective in (
        db.query(TenantPlanAssignment.tenant_id, PlanDefinition.name, TenantPlanAssignment.effective_from)
        .join(PlanDefinition, PlanDefinition.id == TenantPlanAssignment.plan_id)
        .filter(TenantPlanAssignment.status == "ACTIVE", not_trial_clause(TenantPlanAssignment.tenant_id))
    ):
        if tenant_id not in latest or (effective and latest[tenant_id][1] and effective > latest[tenant_id][1]):
            latest[tenant_id] = (name, effective)
    tenant_count = db.query(func.count(Tenant.id)).filter(not_trial_clause(Tenant.id)).scalar() or 0
    for name, _ in latest.values():
        plans[name] += 1
    if tenant_count > len(latest):
        plans["No plan"] += tenant_count - len(latest)
    regions = [
        {"label": row[0] or "Not specified", "count": row[1]}
        for row in db.query(Tenant.residency_region, func.count(Tenant.id))
        .filter(not_trial_clause(Tenant.id))
        .group_by(Tenant.residency_region)
        .order_by(func.count(Tenant.id).desc())
        .all()
    ]
    months = []
    first = today.replace(day=1)
    for offset in range(12):
        year, month = divmod(first.month - 1 + offset, 12)
        months.append(date(first.year + year, month + 1, 1))
    ending = Counter(
        row.expires_at.date().replace(day=1)
        for row in db.query(SubscriptionLifecycle.expires_at).filter(
            SubscriptionLifecycle.expires_at.is_not(None), not_trial_clause(SubscriptionLifecycle.tenant_id)
        )
        if row.expires_at and months[0] <= row.expires_at.date().replace(day=1) <= months[-1]
    )
    return {
        "days": days,
        "ai_runs": _daily(ai_rows, days, today),
        "integration_runs": _daily(run_rows, days, today),
        "audit_events": _daily(audit_rows, days, today),
        "new_tenants": _daily(tenant_rows, days, today),
        "tenants_by_plan": [{"label": label, "count": count} for label, count in plans.most_common()],
        "tenants_by_region": regions,
        "licences_ending": [{"month": month.isoformat(), "count": ending.get(month, 0)} for month in months],
        # Free trials, shown apart from the customer figures (TO-1).
        "trials": admin_actions.summary(db),
    }
