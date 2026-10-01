"""Free-trial data retention: a closed trial keeps its data for 30 days so it can be converted, then it is deleted.

Only workspaces still on the Free Trial plan whose data lives in the shared trial store are touched; a trial that
was extended or converted no longer qualifies. Business and AI records are deleted; the audit trail, the customer
and workspace identity, and the review history are kept. Users can no longer sign in and the workspace is archived.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from backend.app.db.data_plane import TRIAL_SHARED_DATA_PLANE
from backend.app.db.models.customer_lifecycle import TenantDataPlane
from backend.app.db.models.foundation import AuditEvent, AuthUser, PlanDefinition, Tenant, TenantMembership
from backend.app.db.models.stage2 import AuthSession, SubscriptionLifecycle
from backend.app.trial.service import FREE_TRIAL_PLAN

RETENTION_DAYS = 30

# Records the trial created or uploaded. Identity, plan, subscription and audit tables are deliberately absent.
TRIAL_DATA_TABLES = (
    "ai_interaction_feedback",
    "ai_interactions",
    "ai_interaction_sessions",
    "ai_executions",
    "assurance_results",
    "assurance_checks",
    "release_assurance_results",
    "signed_approval_records",
    "human_reviews",
    "decisions",
    "investigation_briefs",
    "hypothesis_evidence",
    "hypotheses",
    "unknowns",
    "failure_chain_edges",
    "failure_chain_nodes",
    "failure_chains",
    "failure_modes",
    "evidence_proposition_relations",
    "evidence_observations",
    "evidence_entity_links",
    "evidence_chunk_embeddings",
    "evidence_chunks",
    "evidence_embeddings",
    "evidence_attachments",
    "investigation_evidence",
    "investigation_complaints",
    "investigation_sessions",
    "case_contexts",
    "context_snapshots",
    "retrieval_queries",
    "report_jobs",
    "scenarios",
    "supplier_evidence_requests",
    "evidence",
    "investigations",
    "risks",
    "controls",
    "requirements",
    "regulatory_document_versions",
    "regulatory_documents",
    "reality_relationships",
    "canonical_relationships",
    "source_canonical_links",
    "complaints",
    "lot_components",
    "lot_batches",
    "product_components",
    "product_suppliers",
    "component_suppliers",
    "components",
    "product_versions",
    "products",
    "suppliers",
    "changes",
    "manufacturing_sites",
    "data_quality_issues",
    "normalization_issues",
    "normalization_runs",
    "staged_source_records",
    "ingestion_runs",
    "connector_source_records",
    "connector_reconciliations",
    "connector_runs",
    "inbound_email_events",
    "source_records",
)


def _existing_tables(db: Session) -> list[str]:
    present = {
        name
        for (name,) in db.execute(
            text(
                "SELECT table_name FROM information_schema.columns "
                "WHERE table_schema = 'public' AND column_name = 'tenant_id'"
            )
        )
    }
    return [table for table in TRIAL_DATA_TABLES if table in present]


def trials_due(db: Session, now: datetime | None = None) -> list[dict]:
    """Closed Free Trial workspaces whose 30-day retention period has passed and whose data is still present."""
    now = now or datetime.now(timezone.utc)
    rows = (
        db.query(SubscriptionLifecycle, Tenant)
        .join(PlanDefinition, PlanDefinition.id == SubscriptionLifecycle.plan_id)
        .join(Tenant, Tenant.id == SubscriptionLifecycle.tenant_id)
        .join(TenantDataPlane, TenantDataPlane.tenant_id == Tenant.id)
        .filter(
            PlanDefinition.code == FREE_TRIAL_PLAN,
            TenantDataPlane.connection_secret_ref == TRIAL_SHARED_DATA_PLANE,
            Tenant.status != "ARCHIVED",
        )
        .all()
    )
    due = []
    for subscription, tenant in rows:
        ended = max(subscription.expires_at, subscription.grace_ends_at or subscription.expires_at)
        delete_after = ended + timedelta(days=RETENTION_DAYS)
        if delete_after <= now:
            due.append(
                {
                    "tenant_id": str(tenant.id),
                    "tenant_key": tenant.tenant_key,
                    "name": tenant.name,
                    "trial_ended_at": ended.isoformat(),
                    "delete_after": delete_after.isoformat(),
                }
            )
    return due


def delete_tenant_records(db: Session, tenant_id: uuid.UUID) -> tuple[dict[str, int], list[str]]:
    """Delete one tenant's business and AI records (not identity, plan or audit). Returns deleted counts per table
    and any tables whose rows could not be deleted. Does not commit."""
    remaining = _existing_tables(db)
    deleted: dict[str, int] = {}
    # Child tables are listed first; the passes cover any foreign key this ordering misses.
    for _ in range(len(remaining)):
        progress = False
        for table in list(remaining):
            savepoint = db.begin_nested()
            try:
                count = db.execute(text(f"DELETE FROM {table} WHERE tenant_id = :tenant_id"), {"tenant_id": tenant_id})
                savepoint.commit()
            except DBAPIError:
                savepoint.rollback()
                continue
            if count.rowcount:
                deleted[table] = count.rowcount
            remaining.remove(table)
            progress = True
        if not remaining or not progress:
            break
    return deleted, remaining


def purge_trial(db: Session, tenant_id: uuid.UUID, actor_ref: str, now: datetime | None = None) -> dict:
    """Delete one closed trial's records, close its accounts and archive it. Commits; returns what was removed."""
    now = now or datetime.now(timezone.utc)
    deleted, remaining = delete_tenant_records(db, tenant_id)

    user_ids = [user_id for (user_id,) in db.query(AuthUser.id).filter(AuthUser.tenant_id == tenant_id)]
    db.query(AuthUser).filter(AuthUser.tenant_id == tenant_id).update(
        {"status": "REMOVED", "updated_at": now}, synchronize_session=False
    )
    db.query(TenantMembership).filter(TenantMembership.tenant_id == tenant_id).update(
        {"status": "REMOVED", "updated_at": now}, synchronize_session=False
    )
    if user_ids:
        db.query(AuthSession).filter(AuthSession.user_id.in_(user_ids), AuthSession.revoked_at.is_(None)).update(
            {"revoked_at": now}, synchronize_session=False
        )
    db.query(TenantDataPlane).filter(TenantDataPlane.tenant_id == tenant_id).update(
        {"status": "RETIRED", "updated_at": now}, synchronize_session=False
    )
    db.query(Tenant).filter(Tenant.id == tenant_id).update(
        {"status": "ARCHIVED", "updated_at": now}, synchronize_session=False
    )
    result = {"deleted_records": deleted, "not_deleted_tables": remaining, "users_closed": len(user_ids)}
    db.add(
        AuditEvent(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            actor_ref=actor_ref,
            action="TRIAL_DATA_DELETED",
            entity_type="Tenant",
            entity_id=tenant_id,
            details={**result, "retention_days": RETENTION_DAYS},
            created_at=now,
        )
    )
    db.commit()
    return result


def run_retention(db: Session, actor_ref: str, now: datetime | None = None) -> dict:
    due = trials_due(db, now)
    results = []
    for trial in due:
        outcome = purge_trial(db, uuid.UUID(trial["tenant_id"]), actor_ref, now)
        results.append({**trial, **outcome})
    return {"purged": len(results), "trials": results}
