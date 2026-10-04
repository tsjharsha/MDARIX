"""Tenant administration read models: audit history/export, retention, health, dashboards, integrations, AI executions."""

import io
import json
import uuid
import zipfile
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from auth.emailer import (
    smtp_configuration_status,
)
from backend.app import csv_safe
from backend.app.db.models.foundation import (
    AuditEvent,
    AuthUser,
    ConnectorConfiguration,
    Decision,
    Investigation,
    MappingConfiguration,
    Product,
    AIExecution,
)
from backend.app.db.models.enterprise import ConnectorRun, ReconciliationRecord
from backend.app.db.models.stage2 import (
    AuthSession,
    OutboxEvent,
    UserInvitation,
)
from backend.app.db.data_plane import tenant_data_session
from backend.app.db.session import get_db
from backend.app.access.authz import (
    _admin_detail_tenant,
    _admin_tenant,
    _is_platform_admin,
    _require_platform_admin,
    platform_account_clause,
    visible_user_filters,
)
from backend.app.access.trends import daily, per_day, run_outcome, window
from backend.app.runtime_env import environment
from backend.app.worker_status import worker_status

router = APIRouter(prefix="/api/v1", tags=["Access Control"])


@router.get("/admin/smtp-status")
def admin_smtp_status(request: Request, db: Session = Depends(get_db)):
    _require_platform_admin(request, db)
    return smtp_configuration_status()


PLATFORM_ACTOR_LABEL = "MDARIX platform administrator"


def _as_uuid(value):
    try:
        return uuid.UUID(str(value))
    except (TypeError, ValueError):
        return None


@router.get("/admin/audit-history")
def audit_history(
    request: Request, action: str | None = None, entity_type: str | None = None, db: Session = Depends(get_db)
):
    admin = _admin_tenant(request, db)
    query = db.query(AuditEvent).filter(AuditEvent.tenant_id == admin.tenant_id)
    if action:
        query = query.filter(AuditEvent.action == action)
    if entity_type:
        query = query.filter(AuditEvent.entity_type == entity_type)
    rows = query.order_by(AuditEvent.created_at.desc()).limit(200).all()
    # Actions by MDARIX staff stay visible to the customer, attributed to the platform rather than to a person.
    platform_actors = (
        set()
        if _is_platform_admin(admin)
        else {
            str(user_id)
            for (user_id,) in db.query(AuthUser.id).filter(
                AuthUser.id.in_({_as_uuid(row.actor_ref) for row in rows} - {None}), platform_account_clause()
            )
        }
    )
    return [
        {
            "id": str(row.id),
            "tenant_id": str(row.tenant_id),
            "actor_ref": None if str(row.actor_ref) in platform_actors else row.actor_ref,
            "actor_label": PLATFORM_ACTOR_LABEL if str(row.actor_ref) in platform_actors else None,
            "action": row.action,
            "entity_type": row.entity_type,
            "entity_id": str(row.entity_id) if row.entity_id else None,
            "details": row.details,
            "source_ip": row.source_ip,
            "user_agent": row.user_agent,
            "reason": row.reason,
            "old_values": row.old_values,
            "new_values": row.new_values,
            "retention_until": row.retention_until,
            "created_at": row.created_at,
        }
        for row in rows
    ]


# Every exported audit event carries its place in the organization's hash chain (migration md18), so whoever
# receives an export can check that nothing between the first and last event is missing or changed.
AUDIT_EXPORT_FIELDS = [
    "id",
    "tenant_id",
    "chain_seq",
    "previous_hash",
    "event_hash",
    "actor_ref",
    "action",
    "entity_type",
    "entity_id",
    "source_ip",
    "user_agent",
    "reason",
    "old_values",
    "new_values",
    "retention_until",
    "created_at",
]


@router.get("/admin/audit-history/export")
def export_audit_history(
    request: Request,
    output_format: str = "CSV",
    action: str | None = None,
    entity_type: str | None = None,
    db: Session = Depends(get_db),
):
    """Export only the authenticated tenant's audit evidence."""
    admin = _admin_tenant(request, db)
    rows = db.query(AuditEvent).filter(AuditEvent.tenant_id == admin.tenant_id)
    if action:
        rows = rows.filter(AuditEvent.action == action)
    if entity_type:
        rows = rows.filter(AuditEvent.entity_type == entity_type)
    # The whole trail, in chain order: an export is evidence, so it is never cut short.
    events = rows.order_by(AuditEvent.chain_seq.asc()).yield_per(1000)
    fields = AUDIT_EXPORT_FIELDS
    if output_format.upper() == "JSON":
        return [
            {
                field: (
                    str(getattr(row, field))
                    if field in {"id", "tenant_id", "entity_id", "created_at", "retention_until"}
                    and getattr(row, field) is not None
                    else getattr(row, field)
                )
                for field in fields
            }
            for row in events
        ]
    if output_format.upper() != "CSV":
        raise HTTPException(400, detail={"code": "AUDIT_EXPORT_FORMAT_NOT_SUPPORTED", "message": "Use CSV or JSON"})
    stream = io.StringIO()
    writer = csv_safe.writer(stream, fieldnames=fields)
    writer.writeheader()
    for row in events:
        writer.writerow(
            {field: str(getattr(row, field)) if getattr(row, field) is not None else "" for field in fields}
        )
    return Response(
        content=stream.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="mdarix-audit-{admin.tenant_id}.csv"'},
    )


def _chain_summary(db: Session, tenant_id) -> dict:
    from backend.app.audit_chain import verify_tenant_chain

    result = verify_tenant_chain(db, tenant_id)
    return {
        key: result[key] for key in ("valid", "checked", "first_broken_seq", "last_seq", "last_hash", "verified_at")
    }


@router.get("/admin/audit-history/evidence-package")
def download_audit_evidence_package(
    request: Request, action: str | None = None, entity_type: str | None = None, db: Session = Depends(get_db)
):
    """Download a tenant-scoped, redacted compliance evidence package.

    The package is generated in memory, contains no credentials, and includes a
    manifest, audit CSV, and machine-readable audit JSON for traceability.
    """
    admin = _admin_tenant(request, db)
    query = db.query(AuditEvent).filter(AuditEvent.tenant_id == admin.tenant_id)
    if action:
        query = query.filter(AuditEvent.action == action)
    if entity_type:
        query = query.filter(AuditEvent.entity_type == entity_type)
    events = query.order_by(AuditEvent.chain_seq.asc()).yield_per(1000)
    fields = AUDIT_EXPORT_FIELDS
    rows = []
    for row in events:
        item = {field: getattr(row, field) for field in fields}
        for field in ("id", "tenant_id", "entity_id", "retention_until", "created_at"):
            if item[field] is not None:
                item[field] = str(item[field])
        rows.append(item)
    manifest = {
        "package": "MDARIX_COMPLIANCE_EVIDENCE",
        "version": "1",
        "tenant_id": str(admin.tenant_id),
        "event_count": len(rows),
        "complete": True,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "filters": {"action": action, "entity_type": entity_type},
        # The organization's whole chain, verified in the database when the package was made.
        "audit_chain": _chain_summary(db, admin.tenant_id),
        "retention_policy": "7-year minimum",
        "redaction": "secret-bearing fields excluded by audit writer",
    }
    csv_stream = io.StringIO()
    writer = csv_safe.writer(csv_stream, fieldnames=fields)
    writer.writeheader()
    for row in rows:
        writer.writerow(
            {
                key: json.dumps(value, default=str)
                if isinstance(value, (dict, list))
                else ("" if value is None else value)
                for key, value in row.items()
            }
        )
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("manifest.json", json.dumps(manifest, indent=2))
        archive.writestr("audit-events.json", json.dumps(rows, indent=2, default=str))
        archive.writestr("audit-events.csv", csv_stream.getvalue())
    return Response(
        content=output.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="mdarix-compliance-{admin.tenant_id}.zip"'},
    )


@router.get("/admin/retention-status")
def audit_retention_status(request: Request, db: Session = Depends(get_db)):
    """Return operational retention posture without exposing another tenant's events."""
    admin = _admin_tenant(request, db)
    now = datetime.now(timezone.utc)
    horizon = now + timedelta(days=30)
    query = db.query(AuditEvent).filter(AuditEvent.tenant_id == admin.tenant_id)
    expired = query.filter(AuditEvent.retention_until < now).count()
    expiring = query.filter(AuditEvent.retention_until >= now, AuditEvent.retention_until <= horizon).count()
    total = query.count()
    return {
        "tenant_id": str(admin.tenant_id),
        "policy": "7-year minimum",
        "total_events": total,
        "expired": expired,
        "expiring_within_30_days": expiring,
        "archival_required": expired > 0,
        "status": "ATTENTION_REQUIRED" if expired else "HEALTHY",
        "checked_at": now,
    }


@router.get("/admin/health-summary")
def admin_health_summary(request: Request, db: Session = Depends(get_db)):
    """Return operational administrator signals, scoped to the authenticated tenant."""
    admin = _admin_tenant(request, db)
    tenant_id = admin.tenant_id
    recent = (
        db.query(AuditEvent)
        .filter(AuditEvent.tenant_id == tenant_id)
        .order_by(AuditEvent.created_at.desc())
        .limit(100)
        .all()
    )
    connector_failures = sum(
        1
        for row in recent
        if any(token in row.action.upper() for token in ("CONNECTOR", "PROVIDER"))
        and any(token in row.action.upper() for token in ("FAILED", "FAILURE", "ERROR", "UNAVAILABLE"))
    )
    security_events = sum(
        1
        for row in recent
        if any(token in row.action.upper() for token in ("DENIED", "UNAUTHORIZED", "SECURITY", "AUTHENTICATION_FAILED"))
    )
    invitation_failures = sum(
        1
        for row in recent
        if "INVIT" in row.action.upper()
        and any(token in row.action.upper() for token in ("FAILED", "FAILURE", "ERROR"))
    )
    pending_invitations = (
        db.query(UserInvitation).filter(UserInvitation.tenant_id == tenant_id, UserInvitation.used_at.is_(None)).count()
    )
    pending_approvals = (
        db.query(Decision)
        .filter(
            Decision.tenant_id == tenant_id,
            Decision.decision_status.in_(["DRAFT", "PENDING", "PENDING_APPROVAL", "READY_FOR_APPROVAL"]),
        )
        .count()
    )
    mapping_issues = (
        db.query(MappingConfiguration)
        .filter(
            MappingConfiguration.tenant_id == tenant_id,
            MappingConfiguration.status.in_(["DRAFT", "BLOCKED", "FAILED", "REVIEW"]),
        )
        .count()
    )
    alerts = []
    for code, label, count, severity in (
        ("CONNECTOR_FAILURES", "Failed or degraded connectors", connector_failures, "HIGH"),
        ("PENDING_APPROVALS", "Pending approvals", pending_approvals, "MEDIUM"),
        ("INVITATION_FAILURES", "Invitation or activation failures", invitation_failures, "HIGH"),
        ("SECURITY_EVENTS", "Security or authorization events", security_events, "HIGH"),
        ("MAPPING_ISSUES", "Schema or mapping items needing review", mapping_issues, "MEDIUM"),
    ):
        if count:
            alerts.append({"code": code, "label": label, "count": count, "severity": severity})
    return {
        "tenant_id": str(tenant_id),
        "status": "ATTENTION_REQUIRED" if alerts else "HEALTHY",
        "metrics": {
            "connector_failures": connector_failures,
            "pending_approvals": pending_approvals,
            "pending_invitations": pending_invitations,
            "invitation_failures": invitation_failures,
            "security_events": security_events,
            "mapping_issues": mapping_issues,
            "recent_audit_events": len(recent),
        },
        "alerts": alerts,
        "recent_audit": [
            {"action": row.action, "entity_type": row.entity_type, "created_at": row.created_at} for row in recent[:10]
        ],
    }


@router.get("/admin/tenant-dashboard")
def tenant_dashboard(request: Request, db: Session = Depends(get_db)):
    """Return the authenticated tenant's complete dashboard projection.

    The tenant is derived exclusively from the durable authenticated request
    context.  No tenant id, tenant slug, or client-provided filter is accepted.
    This keeps dashboard cards, alerts, and counts consistent with API policy.
    """
    admin = _admin_tenant(request, db)
    tenant_id = admin.tenant_id
    health = admin_health_summary(request, db)
    visible = visible_user_filters(admin)
    users = db.query(AuthUser).filter(AuthUser.tenant_id == tenant_id, *visible).count()
    active_users = (
        db.query(AuthUser).filter(AuthUser.tenant_id == tenant_id, AuthUser.status == "ACTIVE", *visible).count()
    )
    # Business records live in the tenant's data plane (a dedicated database, or the shared one).
    with tenant_data_session(tenant_id) as data:
        products = data.query(Product).filter(Product.tenant_id == tenant_id).count()
        investigations = data.query(Investigation).filter_by(tenant_id=tenant_id).count()
    connectors = db.query(ConnectorConfiguration).filter(ConnectorConfiguration.tenant_id == tenant_id).count()
    return {
        "tenant": {
            "id": str(tenant_id),
            "name": admin.company or admin.display_name or "Authenticated tenant",
            "environment": environment(),
        },
        "metrics": {
            "users": users,
            "active_users": active_users,
            "products": products,
            "investigations": investigations,
            "connectors": connectors,
            **health["metrics"],
        },
        "health": {"status": health["status"], "alerts": health["alerts"], "recent_audit": health["recent_audit"]},
        "scope": {"tenant_scoped": True, "server_derived": True},
    }


@router.get("/admin/dashboard-trends")
def tenant_dashboard_trends(request: Request, days: int = 30, db: Session = Depends(get_db)):
    """The signed-in administrator's own tenant, day by day: sign-ins, new users, integration runs, AI runs and
    audit events, plus investigations by status. The tenant comes from the session only; counts, never content."""
    admin = _admin_tenant(request, db)
    tenant_id = admin.tenant_id
    days, today, since = window(days)
    visible = visible_user_filters(admin)

    sign_in_day = func.date(AuthSession.created_at)
    sign_ins = (
        db.query(sign_in_day, func.count())
        .join(AuthUser, AuthUser.id == AuthSession.user_id)
        .filter(AuthSession.tenant_id == tenant_id, AuthSession.created_at >= since, *visible)
        .group_by(sign_in_day)
        .all()
    )
    new_users = per_day(db, since, AuthUser.created_at, AuthUser.tenant_id == tenant_id, *visible)
    runs = per_day(
        db, since, ConnectorRun.started_at, ConnectorRun.tenant_id == tenant_id, key=func.upper(ConnectorRun.status)
    )
    with tenant_data_session(tenant_id) as data:
        ai = per_day(
            data,
            since,
            AIExecution.execution_timestamp,
            AIExecution.tenant_id == tenant_id,
            key=AIExecution.error_state.is_(None),
        )
        investigations = (
            data.query(func.upper(Investigation.status), func.count(Investigation.id))
            .filter(Investigation.tenant_id == tenant_id)
            .group_by(func.upper(Investigation.status))
            .order_by(func.count(Investigation.id).desc())
            .all()
        )
    in_tenant = AuditEvent.tenant_id == tenant_id
    refused = or_(AuditEvent.action.like("%DENIED%"), AuditEvent.action.like("%FAILED%"))
    audit = [(day, "events", count) for day, _, count in per_day(db, since, AuditEvent.created_at, in_tenant)] + [
        (day, "refused", count) for day, _, count in per_day(db, since, AuditEvent.created_at, in_tenant, refused)
    ]
    return {
        "days": days,
        "sign_ins": daily([(day, "sign_ins", count) for day, count in sign_ins], days, today),
        "new_users": daily([(day, "users", count) for day, _, count in new_users], days, today),
        "integration_runs": daily([(day, run_outcome(status), count) for day, status, count in runs], days, today),
        "ai_runs": daily([(day, "completed" if ok else "failed", count) for day, ok, count in ai], days, today),
        "audit_events": daily(audit, days, today),
        "investigations_by_status": [
            {"label": status or "UNKNOWN", "count": count} for status, count in investigations
        ],
        "scope": {"tenant_scoped": True, "server_derived": True},
    }


@router.get("/admin/ai-summary")
def admin_ai_summary(request: Request, db: Session = Depends(get_db)):
    """Return a safe, tenant-scoped AI control-plane summary without prompt or secret data."""
    admin = _admin_tenant(request, db)
    recent = (
        db.query(AuditEvent)
        .filter(AuditEvent.tenant_id == admin.tenant_id)
        .order_by(AuditEvent.created_at.desc())
        .limit(200)
        .all()
    )
    executions = sum(1 for row in recent if "AI" in row.action.upper() or "GENAI" in row.action.upper())
    failures = sum(
        1
        for row in recent
        if ("AI" in row.action.upper() or "GENAI" in row.action.upper())
        and any(token in row.action.upper() for token in ("FAIL", "ERROR", "UNAVAILABLE"))
    )
    from genai.provider import GenAIProvider

    health = GenAIProvider().health()
    return {
        "tenant_id": str(admin.tenant_id),
        "provider": health.get("provider"),
        "model": health.get("model"),
        "configured": health.get("configured", False),
        "human_review_required": True,
        "hidden_chain_of_thought_persisted": False,
        "metrics": {"recent_executions": executions, "recent_failures": failures, "evaluations": "SERVER_DERIVED"},
        "scope": {"tenant_scoped": True, "secrets_redacted": True},
    }


@router.get("/admin/security-summary")
def admin_security_summary(request: Request, db: Session = Depends(get_db)):
    """Return tenant-isolation and security evidence counts for the admin dashboard."""
    admin = _admin_tenant(request, db)
    recent = (
        db.query(AuditEvent)
        .filter(AuditEvent.tenant_id == admin.tenant_id)
        .order_by(AuditEvent.created_at.desc())
        .limit(200)
        .all()
    )
    security = [
        row
        for row in recent
        if any(
            token in row.action.upper()
            for token in ("DENIED", "UNAUTHORIZED", "SECURITY", "AUTHENTICATION_FAILED", "ISOLATION")
        )
    ]
    return {
        "tenant_id": str(admin.tenant_id),
        "status": "REVIEW" if security else "HEALTHY",
        "metrics": {
            "security_events": len(security),
            "isolation_checks": sum(1 for row in recent if "ISOLATION" in row.action.upper()),
            "policy_denials": sum(1 for row in security if "DENIED" in row.action.upper()),
        },
        "controls": ["API authorization", "Tenant-scoped queries", "Field-policy filtering", "Audit immutability"],
        "scope": {"tenant_scoped": True},
    }


@router.get("/admin/operations-summary")
def admin_operations_summary(request: Request, db: Session = Depends(get_db)):
    """Return operational queue and connector health counts from durable records."""
    admin = _admin_tenant(request, db)
    tenant_id = admin.tenant_id
    pending = (
        db.query(OutboxEvent)
        .filter(
            OutboxEvent.tenant_id == tenant_id,
            OutboxEvent.published_at.is_(None),
            OutboxEvent.dead_lettered_at.is_(None),
        )
        .count()
    )
    dead_lettered = (
        db.query(OutboxEvent)
        .filter(OutboxEvent.tenant_id == tenant_id, OutboxEvent.dead_lettered_at.is_not(None))
        .count()
    )
    retried = db.query(OutboxEvent).filter(OutboxEvent.tenant_id == tenant_id, OutboxEvent.attempts > 0).count()
    connectors = db.query(ConnectorConfiguration).filter(ConnectorConfiguration.tenant_id == tenant_id).count()
    return {
        "tenant_id": str(tenant_id),
        "status": "ATTENTION_REQUIRED" if dead_lettered else "HEALTHY",
        "metrics": {
            "outbox_pending": pending,
            "outbox_retried": retried,
            "outbox_dead_lettered": dead_lettered,
            "configured_connectors": connectors,
        },
        # Only whether the shared worker runs: its counters cover every tenant, so they are not shown here.
        "worker": {"heartbeat": worker_status(db)["state"], "deployment": "ENVIRONMENT_DEPENDENT"},
        "scope": {"tenant_scoped": True},
    }


@router.get("/admin/integrations/runs")
def admin_integration_runs(request: Request, db: Session = Depends(get_db)):
    tenant_id = _admin_detail_tenant(request, db)
    rows = (
        db.query(ConnectorRun)
        .filter(ConnectorRun.tenant_id == tenant_id)
        .order_by(ConnectorRun.created_at.desc())
        .limit(200)
        .all()
    )
    return [
        {
            "id": str(row.id),
            "tenant_id": str(row.tenant_id),
            "connection_id": row.connection_id,
            "source_system": row.source_system,
            "run_type": row.run_type,
            "status": row.status,
            "records_received": row.records_received,
            "records_accepted": row.records_accepted,
            "records_rejected": row.records_rejected,
            "records_duplicate": row.records_duplicate,
            "retry_attempt": row.retry_attempt,
            "reconciliation_status": row.reconciliation_status,
            "schema_drift_status": row.schema_drift_status,
            "failure_category": row.failure_category,
            "correlation_id": row.correlation_id,
            "started_at": row.started_at,
            "completed_at": row.completed_at,
        }
        for row in rows
    ]


@router.get("/admin/integrations/reconciliation")
def admin_integration_reconciliation(request: Request, db: Session = Depends(get_db)):
    tenant_id = _admin_detail_tenant(request, db)
    rows = (
        db.query(ReconciliationRecord)
        .filter(ReconciliationRecord.tenant_id == tenant_id)
        .order_by(ReconciliationRecord.reconciled_at.desc())
        .limit(200)
        .all()
    )
    return [
        {
            "id": str(row.id),
            "tenant_id": str(row.tenant_id),
            "connector_run_id": str(row.connector_run_id),
            "expected_count": row.expected_count,
            "received_count": row.received_count,
            "accepted_count": row.accepted_count,
            "rejected_count": row.rejected_count,
            "quarantined_count": row.quarantined_count,
            "duplicate_count": row.duplicate_count,
            "unresolved_count": row.unresolved_count,
            "status": row.status,
            "details": row.details,
            "reconciled_at": row.reconciled_at,
        }
        for row in rows
    ]


@router.get("/admin/integrations/credentials")
def admin_integration_credentials(request: Request, db: Session = Depends(get_db)):
    tenant_id = _admin_detail_tenant(request, db)
    rows = db.query(ConnectorConfiguration).filter(ConnectorConfiguration.tenant_id == tenant_id).all()
    return [
        {
            "id": str(row.id),
            "tenant_id": str(row.tenant_id),
            "code": row.code,
            "connector_type": row.connector_type,
            "version": row.version,
            "status": row.status,
            "credential_ref": (row.configuration or {}).get("credential_ref"),
            "credential_configured": bool((row.configuration or {}).get("credential_ref")),
            "secret_value": None,
            "scope": {"tenant_scoped": True, "secrets_redacted": True},
        }
        for row in rows
    ]


@router.get("/admin/ai-executions")
def admin_ai_executions(request: Request, db: Session = Depends(get_db)):
    tenant_id = _admin_detail_tenant(request, db)
    with tenant_data_session(tenant_id) as data:
        rows = (
            data.query(AIExecution)
            .filter(AIExecution.tenant_id == tenant_id)
            .order_by(AIExecution.execution_timestamp.desc())
            .limit(200)
            .all()
        )
        data.expunge_all()
    return [
        {
            "id": str(row.id),
            "tenant_id": str(row.tenant_id),
            "investigation_id": str(row.investigation_id) if row.investigation_id else None,
            "provider": row.provider,
            "model_name": row.model_name,
            "model_version": row.model_version,
            "prompt_template_version": row.prompt_template_version,
            "validation_status": row.validation_status,
            "confidence_label": row.confidence_label,
            "execution_timestamp": row.execution_timestamp,
            "latency_ms": row.latency_ms,
            "error_state": row.error_state,
            "structured_output": row.structured_output,
            "secrets_redacted": True,
        }
        for row in rows
    ]
