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

A trial whose organization asked for its data to be moved into the MVP (an open request, NEW or CONTACTED, with
``move_trial_data``, from Next steps; backend/app/trial/mvp_request.py) is held: while the request is open and the
data may still be moved (sample removed, own data in), the purge skips it with an audit record, for at most
``MVP_HOLD_MAX_DAYS`` after the trial ends. Once the request is closed, the data is deleted ``MVP_HOLD_GRACE_DAYS``
later at the earliest (never the same night), and never after the hold's end. The MDARIX team is alerted
``MVP_HOLD_ALERT_DAYS`` before the date the data would otherwise have been deleted and before the hold ends, once
each. A legal hold works as before, whatever the request.

The same daily run deletes the browser error reports that were sent before sign-in, 90 days after they arrived
(``client_errors.delete_anonymous_reports``): they belong to no organization, so no purge would ever reach them.
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
# A request to move the trial data into the MVP holds it (see the module docstring): for at most this many days after
# the trial ends; this many days after the request is closed at the earliest; alerts this many days before each date.
MVP_HOLD_MAX_DAYS = 90
MVP_HOLD_GRACE_DAYS = 14
MVP_HOLD_ALERT_DAYS = 7

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
    # Per-market assessments, classifications (both on complaints listed below) and signer training records (tr01).
    "complaint_market_assessments",
    "complaint_classifications",
    "signer_training_records",
    # Complaint dispositions (tr02): on the complaints listed below.
    "complaint_dispositions",
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


def move_requests(db: Session, tenant_ids) -> dict:
    """``{tenant id: {"open": its open request asking to move the trial data, or None, "closed_at": when its last such
    request was closed, or None}}`` for the tenants (ids, or a subquery of them) that ever asked to move their data."""
    from backend.app.db.models.stage2 import TrialMvpRequest
    from backend.app.trial.mvp_request import OPEN

    found: dict = {}
    if isinstance(tenant_ids, (list, set, tuple)):
        if not tenant_ids:
            return found
        tenant_ids = list(tenant_ids)
    rows = db.query(TrialMvpRequest).filter(
        TrialMvpRequest.tenant_id.in_(tenant_ids), TrialMvpRequest.move_trial_data.is_(True)
    )
    for row in rows:
        entry = found.setdefault(row.tenant_id, {"open": None, "closed_at": None})
        if row.status in OPEN:
            entry["open"] = row
            continue
        closed = row.handled_at or row.updated_at
        if closed is not None and (entry["closed_at"] is None or closed > entry["closed_at"]):
            entry["closed_at"] = closed
    return found


def retention_plan(ended: datetime, requests: dict | None, movable: bool, now: datetime) -> dict:
    """When one closed trial's data is deleted: 30 days after it ended; while an open request asks to move the data and
    the data may still be moved, not before the hold ends (``MVP_HOLD_MAX_DAYS`` after the trial); after such a request
    was closed, ``MVP_HOLD_GRACE_DAYS`` after it closed at the earliest, and never after the hold's end."""
    original = ended + timedelta(days=RETENTION_DAYS)
    hold_until = ended + timedelta(days=MVP_HOLD_MAX_DAYS)
    request = (requests or {}).get("open")
    held = request is not None and movable and now < hold_until
    delete_after = original
    if held:
        delete_after = max(original, hold_until)
    elif (requests or {}).get("closed_at") is not None:
        resumed = min(requests["closed_at"] + timedelta(days=MVP_HOLD_GRACE_DAYS), hold_until)
        delete_after = max(original, resumed)
    return {
        "trial_ended_at": ended,
        "original_delete_after": original,
        "delete_after": delete_after,
        "hold_until": hold_until,
        "mvp_request": request if held else None,
    }


def deletion_date(db: Session, data: Session, subscription, now: datetime | None = None) -> datetime:
    """The day one trial's data is deleted at the earliest, as people are told it (trial emails, Getting started): 30
    days after the trial ends, counting any grace extension, or later while an open request to move the data into the
    MVP holds it (``retention_plan``). The scheduled job runs daily, and the date can still move later (a grace
    extension, a new request, a legal hold), so it is always worded "at the earliest". ``data`` reads the trial's
    records (whether its data may move)."""
    from backend.app.trial.mvp_request import data_move

    now = now or datetime.now(timezone.utc)
    ended = max(subscription.expires_at, subscription.grace_ends_at or subscription.expires_at)
    asked = move_requests(db, [subscription.tenant_id]).get(subscription.tenant_id)
    movable = bool(asked and asked["open"] is not None and data_move(data, subscription.tenant_id)["allowed"])
    return retention_plan(ended, asked, movable, now)["delete_after"]


def plans(db: Session, now: datetime | None = None, tenant_ids=None) -> list[dict]:
    """The deletion plan (``retention_plan``) of every Free Trial workspace still holding data in the shared trial
    store (or of those among ``tenant_ids``), with its tenant. ``db`` reads every tenant (system scope)."""
    from backend.app.trial.mvp_request import data_move

    now = now or datetime.now(timezone.utc)
    query = (
        db.query(SubscriptionLifecycle, Tenant)
        .join(PlanDefinition, PlanDefinition.id == SubscriptionLifecycle.plan_id)
        .join(Tenant, Tenant.id == SubscriptionLifecycle.tenant_id)
        .join(TenantDataPlane, TenantDataPlane.tenant_id == Tenant.id)
        .filter(
            PlanDefinition.code == FREE_TRIAL_PLAN,
            TenantDataPlane.connection_secret_ref == TRIAL_SHARED_DATA_PLANE,
            Tenant.status != "ARCHIVED",
        )
    )
    if tenant_ids is not None:
        query = query.filter(Tenant.id.in_(list(tenant_ids)))
    # Oldest subscription first, so a workspace's latest one has the last word where they are read per workspace.
    rows = query.order_by(SubscriptionLifecycle.created_at).all()
    requests = move_requests(db, {tenant.id for _subscription, tenant in rows})
    movable: dict = {}
    found = []
    for subscription, tenant in rows:
        asked = requests.get(tenant.id)
        if asked and asked["open"] is not None and tenant.id not in movable:
            # The data may still be moved only while the sample stays removed and the own data is there.
            movable[tenant.id] = bool(data_move(db, tenant.id)["allowed"])
        ended = max(subscription.expires_at, subscription.grace_ends_at or subscription.expires_at)
        found.append({"tenant": tenant, **retention_plan(ended, asked, movable.get(tenant.id, False), now)})
    return found


def plan_view(plan: dict) -> dict:
    """A plan as the Platform Administrator sees it (trials overview, MVP requests, the retention preview)."""
    request = plan["mvp_request"]
    return {
        "delete_after": plan["delete_after"].isoformat(),
        "original_delete_after": plan["original_delete_after"].isoformat(),
        "held_for_mvp_request": request is not None,
        "hold_until": plan["hold_until"].isoformat(),
        "mvp_request": {"id": str(request.id), "status": request.status} if request is not None else None,
    }


def trials_due(db: Session, now: datetime | None = None) -> list[dict]:
    """Closed Free Trial workspaces whose 30-day retention period has passed and whose data is still present.
    ``legal_hold`` marks the ones retention must leave alone, ``held_for_mvp_request`` those an open request to move
    the data into the MVP holds (``delete_after`` is then the end of the hold); a trial whose request was closed lately
    is listed once its grace period has passed."""
    now = now or datetime.now(timezone.utc)
    due = []
    for plan in plans(db, now):
        if plan["original_delete_after"] > now:
            continue
        if plan["mvp_request"] is None and plan["delete_after"] > now:
            continue
        tenant = plan["tenant"]
        due.append(
            {
                "tenant_id": str(tenant.id),
                "tenant_business_id": tenant.business_id,
                "tenant_key": tenant.tenant_key,
                "name": tenant.name,
                "trial_ended_at": plan["trial_ended_at"].isoformat(),
                **plan_view(plan),
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


def _note_mvp_hold(db: Session, trial: dict, actor_ref: str, now: datetime) -> None:
    """The run skipped a trial an open MVP request holds: recorded in the trial's own trail, like a legal hold."""
    from backend.app.db.tenant_scope import bind_system

    bind_system(db, "trial retention: record an MVP request hold")
    tenant_id = uuid.UUID(trial["tenant_id"])
    db.add(
        AuditEvent(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            actor_ref=actor_ref,
            action="TRIAL_RETENTION_SKIPPED_MVP_REQUEST",
            entity_type="Tenant",
            entity_id=tenant_id,
            reason="The organization asked for its trial data to be moved into the pilot; the request is open.",
            details={
                "original_delete_after": trial["original_delete_after"],
                "hold_until": trial["hold_until"],
                "mvp_request": trial["mvp_request"],
            },
            created_at=now,
        )
    )
    db.commit()


HOLD_ALERTED = "TRIAL_RETENTION_MVP_HOLD_ALERTED"
# The two moments the MDARIX team is told about a held trial: before the 30-day date, and before the hold ends.
ALERT_BEFORE_DELETION, ALERT_BEFORE_HOLD_ENDS = "BEFORE_ORIGINAL_DATE", "BEFORE_HOLD_ENDS"


def holds_to_alert(db: Session, now: datetime | None = None) -> list[dict]:
    """Held trials whose 30-day date, or whose hold's end, is ``MVP_HOLD_ALERT_DAYS`` away or less and whose alert for
    it (per request) has not been sent yet: ``{"plan", "stage"}``."""
    now = now or datetime.now(timezone.utc)
    lead = timedelta(days=MVP_HOLD_ALERT_DAYS)
    wanted = []
    for plan in plans(db, now):
        request = plan["mvp_request"]
        if request is None:
            continue
        for stage, day in (
            (ALERT_BEFORE_DELETION, plan["original_delete_after"]),
            (ALERT_BEFORE_HOLD_ENDS, plan["hold_until"]),
        ):
            if now < day - lead:
                continue
            sent = (
                db.query(AuditEvent.id)
                .filter(
                    AuditEvent.tenant_id == plan["tenant"].id,
                    AuditEvent.action == HOLD_ALERTED,
                    AuditEvent.details["stage"].astext == stage,
                    AuditEvent.details["request_id"].astext == str(request.id),
                )
                .first()
            )
            if sent is None:
                wanted.append({"plan": plan, "stage": stage})
    return wanted


def alert_holds(db: Session, actor_ref: str, now: datetime | None = None) -> int:
    """Tell the MDARIX team (backend/app/alerts.py) about every held trial ``holds_to_alert`` lists, in one alert, and
    record each in the trial's trail so it is told once. Names the workspaces by MDARIX ID and key only. Returns how
    many were alerted."""
    from backend.app import alerts
    from backend.app.db.tenant_scope import bind_system

    now = now or datetime.now(timezone.utc)
    bind_system(db, "trial retention: alert on trials held for an MVP request")
    wanted = holds_to_alert(db, now)
    if not wanted:
        return 0
    lines = []
    for item in wanted:
        plan, tenant = item["plan"], item["plan"]["tenant"]
        name = f"{tenant.business_id or tenant.id} ({tenant.tenant_key})"
        if item["stage"] == ALERT_BEFORE_DELETION:
            lines.append(
                f"- {name}: its trial data would be deleted on {plan['original_delete_after']:%d %b %Y}. It is kept "
                f"because its pilot request asks to move the data. Close the request (Platform Admin, Pilot requests) once "
                f"the data is moved or will not be; deletion then follows {MVP_HOLD_GRACE_DAYS} days later. The hold "
                f"ends on {plan['hold_until']:%d %b %Y} at the latest."
            )
        else:
            lines.append(
                f"- {name}: the hold for its pilot request ends on {plan['hold_until']:%d %b %Y}, {MVP_HOLD_MAX_DAYS} "
                "days after the trial ended, and the trial data is deleted then, unless the organization has moved to "
                "a paid plan by that day."
            )
        db.add(
            AuditEvent(
                id=uuid.uuid4(),
                tenant_id=tenant.id,
                actor_ref=actor_ref,
                action=HOLD_ALERTED,
                entity_type="Tenant",
                entity_id=tenant.id,
                details={
                    "stage": item["stage"],
                    "request_id": str(plan["mvp_request"].id),
                    "original_delete_after": plan["original_delete_after"].isoformat(),
                    "hold_until": plan["hold_until"].isoformat(),
                },
                created_at=now,
            )
        )
    db.commit()
    alerts.send_alert(
        "Trial data held for a pilot request",
        f"{len(wanted)} trial(s) keep their data because the organization asked to move it into the pilot:\n"
        + "\n".join(lines),
    )
    return len(wanted)


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
    """Purge every trial that is due. A trial under a legal hold, or held by an open request to move its data into the
    MVP, is skipped with an audit note; the MDARIX team is alerted before a held trial's dates (``alert_holds``). A
    trial that cannot be purged completely is left untouched and reported, and one whose files or plane could not be
    removed stays PURGING and is reported too (the next run resumes it); the scheduled job then fails (and alerts) so
    an operator looks at it."""
    from backend.app.tenant_purge import PurgeFailed

    now = now or datetime.now(timezone.utc)
    due = trials_due(db, now)
    results, failed, skipped = [], [], []
    for trial in due:
        if trial["legal_hold"]:
            _note_legal_hold(db, trial, actor_ref, now)
            skipped.append({**trial, "why": "LEGAL_HOLD"})
            continue
        if trial.get("held_for_mvp_request"):
            _note_mvp_hold(db, trial, actor_ref, now)
            skipped.append({**trial, "why": "MVP_REQUEST"})
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
    alerted = alert_holds(db, actor_ref, now)
    # Error reports sent before sign-in belong to no organization, so no purge reaches them: deleted after 90 days
    # (backend/app/client_errors.py; privacy policy; NEW-3).
    from backend.app.client_errors import delete_anonymous_reports

    error_reports = delete_anonymous_reports(db, now)
    return {
        "purged": len(results),
        "trials": results,
        "failed": failed,
        "skipped": skipped,
        "requests": requests,
        "hold_alerts": alerted,
        "error_reports_deleted": error_reports,
    }
