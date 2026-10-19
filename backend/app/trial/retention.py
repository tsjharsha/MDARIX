"""Free-trial data retention: a closed trial keeps its data for 30 days so it can be converted, then it is deleted.

Only workspaces still on the Free Trial plan whose data lives in the shared trial store are touched; a trial that
was extended or converted no longer qualifies. Everything the trial stored is deleted and its people pseudonymized
(backend/app/tenant_purge.py); the workspace is archived. A trial under a legal hold is left alone, with an audit
record of the skipped run. ``delete_tenant_records`` (business records only) is what the demo workspace reset uses.

Trial requests that never became a trial are kept no longer than needed either: ``REQUEST_RETENTION_DAYS`` (90) after
a request was declined, or after the invitation of an approved one expired unused, the requester's name, email, job
title, phone and free-text goal are erased (``tenant_purge.erase_trial_request``; the organization's name and its
answers about the organization stay as the record of the request), and the account made for them, never activated,
is erased with it. The same scheduled job does it. A request whose trial is under a legal hold is left alone.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from backend.app.db.data_plane import TRIAL_SHARED_DATA_PLANE
from backend.app.db.models.customer_lifecycle import TenantDataPlane
from backend.app.db.models.foundation import AuditEvent, PlanDefinition, Tenant
from backend.app.db.models.stage2 import SubscriptionLifecycle
from backend.app.trial.service import FREE_TRIAL_PLAN

RETENTION_DAYS = 30
# Days a declined request, or an approved one whose invitation expired unused, keeps the requester's personal data.
REQUEST_RETENTION_DAYS = 90

# Records the trial created or uploaded. Identity, plan, subscription and audit tables are deliberately absent.
TRIAL_DATA_TABLES = (
    # Workflow tasks (md27) and their history: about cases, decisions, risks and supplier requests listed below.
    "workflow_task_events",
    "workflow_tasks",
    # Signals (md28): their history, complaints and cases first, then the signals and the rule settings.
    "signal_events",
    "signal_complaints",
    "investigation_signals",
    "signals",
    "signal_rules",
    # Complaint review (md40): decisions on complaints listed below, and the organization's settings.
    "complaint_second_looks",
    "complaint_settings",
    # Reporting and CAPA (md41): reportability decisions on complaints and CAPA effectiveness checks listed below,
    # and the organization's reporting windows.
    "complaint_reportability",
    "reportability_settings",
    "capa_effectiveness_checks",
    # The case AI run (md42): about the cases listed below.
    "case_ai_runs",
    # Case scope versions and evidence review history (md29): about the cases and evidence listed below.
    "evidence_review_events",
    "investigation_scope_versions",
    # Reviews and Decision Brief versions (md32) with their quality-review actions: about the cases listed below.
    "brief_review_actions",
    "decision_brief_versions",
    "case_reviews",
    # The history of people's intelligence judgements (md30), about the cases listed below.
    "intelligence_events",
    # Decision follow-ups and late-evidence impact assessments (md33): about the decisions and cases listed below.
    "decision_follow_ups",
    "impact_assessments",
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
    "capas",
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
    """Closed Free Trial workspaces whose 30-day retention period has passed and whose data is still present.
    ``legal_hold`` marks the ones retention must leave alone."""
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
                    "tenant_business_id": tenant.business_id,
                    "tenant_key": tenant.tenant_key,
                    "name": tenant.name,
                    "trial_ended_at": ended.isoformat(),
                    "delete_after": delete_after.isoformat(),
                    "legal_hold": bool(tenant.legal_hold),
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


def purge_trial(db: Session, tenant_id: uuid.UUID, actor_ref: str, now: datetime | None = None, storage=None) -> dict:
    """Delete one closed trial's data completely and archive it (backend/app/tenant_purge.py). Commits; raises
    PurgeFailed with nothing changed when anything would remain or the trial is under a legal hold."""
    from backend.app.tenant_purge import purge_tenant

    return purge_tenant(
        db,
        tenant_id,
        actor_ref,
        reason=f"Free trial ended more than {RETENTION_DAYS} days ago; its data is deleted as the trial terms state.",
        storage=storage,
        now=now,
    )


def _note_legal_hold(db: Session, trial: dict, actor_ref: str, now: datetime) -> None:
    """The skipped run is recorded in the trial's own trail, so the hold's effect is visible to a reviewer."""
    from backend.app.db.tenant_scope import bind_system

    bind_system(db, "trial retention: record a legal hold")
    tenant = db.get(Tenant, uuid.UUID(trial["tenant_id"]))
    db.add(
        AuditEvent(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            actor_ref=actor_ref,
            action="TRIAL_RETENTION_SKIPPED_LEGAL_HOLD",
            entity_type="Tenant",
            entity_id=tenant.id,
            reason=tenant.legal_hold_reason,
            details={
                "delete_after": trial["delete_after"],
                "legal_hold_set_at": tenant.legal_hold_set_at.isoformat() if tenant.legal_hold_set_at else None,
            },
            created_at=now,
        )
    )
    db.commit()


def _unused_invitation_expired(db: Session, request, owner, now: datetime) -> datetime | None:
    """When the last invitation of a never-activated trial owner expired (None while one is still open)."""
    from sqlalchemy import func

    from backend.app.db.models.stage2 import UserInvitation
    from backend.app.trial.service import TRIAL_INVITATION_TTL_SECONDS

    latest = (
        db.query(func.max(UserInvitation.expires_at))
        .filter(UserInvitation.user_id == owner.id, UserInvitation.tenant_id == owner.tenant_id)
        .scalar()
    )
    if latest is None:
        sent = request.invitation_attempted_at or request.reviewed_at
        latest = sent + timedelta(seconds=TRIAL_INVITATION_TTL_SECONDS) if sent else None
    return latest if latest is not None and latest <= now else None


def requests_due(db: Session, now: datetime | None = None) -> list[dict]:
    """Trial requests whose requester's personal data is due for erasure: declined, or approved with an invitation
    that expired unused, ``REQUEST_RETENTION_DAYS`` ago or more, and not erased yet. ``legal_hold`` marks the ones
    whose trial is under a legal hold."""
    from backend.app.db.models.foundation import AuthUser
    from backend.app.db.models.stage2 import OnboardingRequest
    from backend.app.tenant_purge import REMOVED_DOMAIN

    now = now or datetime.now(timezone.utc)
    cutoff = now - timedelta(days=REQUEST_RETENTION_DAYS)
    due: list[dict] = []
    kept = db.query(OnboardingRequest).filter(~OnboardingRequest.email.like(f"%{REMOVED_DOMAIN}"))
    for row in kept.filter(OnboardingRequest.status == "DECLINED", OnboardingRequest.reviewed_at <= cutoff):
        due.append({"request": row, "why": "DECLINED", "owner": None, "legal_hold": False})
    approved = kept.filter(
        OnboardingRequest.status == "APPROVED",
        OnboardingRequest.tenant_id.is_not(None),
        OnboardingRequest.reviewed_at <= cutoff,
    )
    for row in approved:
        owner = (
            db.query(AuthUser)
            .filter(AuthUser.tenant_id == row.tenant_id, AuthUser.username == row.email.strip().lower())
            .first()
        )
        if owner is None or owner.status != "INVITED":
            continue  # activated: the trial's own retention (above) erases it with the workspace
        expired = _unused_invitation_expired(db, row, owner, now)
        if expired is None or expired > cutoff:
            continue
        tenant = db.get(Tenant, row.tenant_id)
        legal_hold = bool(tenant is not None and tenant.legal_hold)
        due.append({"request": row, "why": "INVITATION_UNUSED", "owner": owner, "legal_hold": legal_hold})
    return due


def _decider_tenant(db: Session, row):
    """The organization whose people decided the request (the platform's): its erasure is logged there."""
    from backend.app.db.models.foundation import AuthUser
    from backend.app.support_access import platform_tenant_id

    decider = db.query(AuthUser.tenant_id).filter(AuthUser.id == row.reviewed_by).scalar() if row.reviewed_by else None
    return decider or platform_tenant_id(db) or row.tenant_id


def erase_stale_requests(db: Session, actor_ref: str, now: datetime | None = None) -> dict:
    """Erase the requester's personal data from every request ``requests_due`` lists (see the module docstring), one
    request per transaction. Returns how many were erased and the MDARIX IDs of those left alone under a legal hold."""
    from backend.app.db.tenant_scope import bind_system
    from backend.app.tenant_purge import erase_person, erase_trial_request

    now = now or datetime.now(timezone.utc)
    scope = "trial retention: erase requests that never became a trial"
    bind_system(db, scope)
    erased, held = [], []
    for item in requests_due(db, now):
        row = item["request"]
        if item["legal_hold"]:
            held.append(row.business_id)
            continue
        if item["why"] == "DECLINED":
            reason = f"Trial request declined more than {REQUEST_RETENTION_DAYS} days ago (privacy policy period)."
        else:
            reason = (
                f"Trial invitation expired unused more than {REQUEST_RETENTION_DAYS} days ago (privacy policy period)."
            )
        erase_trial_request(db, row, _decider_tenant(db, row), actor_ref, reason, now)
        owner = item["owner"]
        if owner is not None:
            # The account made for the requester was never activated: it is erased with the request.
            owner.status = "OFFBOARDED"
            erase_person(db, owner, actor_ref, reason, now)
        db.commit()
        bind_system(db, scope)
        erased.append(row.business_id)
    return {"erased": len(erased), "requests": erased, "legal_hold": held}


def run_retention(db: Session, actor_ref: str, now: datetime | None = None) -> dict:
    """Purge every trial that is due. A trial under a legal hold is skipped with an audit note. A trial that cannot
    be purged completely is left untouched and reported, and one whose files or plane could not be removed stays
    PURGING and is reported too (the next run resumes it); the scheduled job then fails (and alerts) so an operator
    looks at it."""
    from backend.app.tenant_purge import PurgeFailed

    now = now or datetime.now(timezone.utc)
    due = trials_due(db, now)
    results, failed, skipped = [], [], []
    for trial in due:
        if trial["legal_hold"]:
            _note_legal_hold(db, trial, actor_ref, now)
            skipped.append({**trial, "why": "LEGAL_HOLD"})
            continue
        try:
            outcome = purge_trial(db, uuid.UUID(trial["tenant_id"]), actor_ref, now)
        except PurgeFailed as exc:
            failed.append({**trial, "error": str(exc)})
            continue
        if outcome.get("status") == "PURGING":
            failed.append({**trial, "error": "INCOMPLETE:" + ",".join(sorted(outcome.get("incomplete") or {}))})
            continue
        results.append({**trial, **outcome})
    requests = erase_stale_requests(db, actor_ref, now)
    return {"purged": len(results), "trials": results, "failed": failed, "skipped": skipped, "requests": requests}
