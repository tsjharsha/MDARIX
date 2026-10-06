"""Impact assessments (IMP000001): evidence that reaches a case after its decision was signed never changes that
decision. Instead a person assesses whether it changes the conclusion.

- ``on_late_evidence``: when a DECIDED or CLOSED case with a current signed brief decision gets evidence (linked,
  reviewed, accepted from a request answer, or ingested for the case), one OPEN assessment per decision and piece of
  evidence, with an IMPACT_ASSESSMENT task for the case owner (else the investigators' queue), audited
  LATE_EVIDENCE_RECEIVED. ``after_late_evidence`` is its never-blocking hook for the evidence endpoints;
  ``run_sweep_for_all_tenants`` is the hourly scheduler job that catches evidence ingested for such a case.
- ``GET  /api/v1/investigations/{id}/impact-assessments`` and ``GET /api/v1/impact-assessments/{id}``;
- ``POST /api/v1/impact-assessments/{id}/complete`` (``investigation.work``) with the conclusion (NO_IMPACT or
  MATERIAL_IMPACT) and its rationale: COMPLETED, and its task completes. A material impact on the current decision
  moves the case back to IN_PROGRESS (from DECIDED or CLOSED, audited) and records that the decision is under
  reconsideration (audit only: the decision row is never changed); the next decision supersedes it.

Completing the IMPACT_ASSESSMENT task through My Work is refused (409 USE_IMPACT_ASSESSMENT): the assessment needs
its conclusion. Everything is limited to the signed-in organization.
"""

from __future__ import annotations

import logging
import uuid
from collections import defaultdict

from fastapi import APIRouter, Depends
from sqlalchemy import and_, exists, func
from sqlalchemy.orm import Session

from backend.app.access.permissions import INVESTIGATION_WORK, require_permission
from backend.app.business_ids import as_uuid, wanted_ids
from backend.app.case_workflow import states
from backend.app.db.data_plane import get_data_plane_db
from backend.app.db.models.decision_outcomes import ImpactAssessment
from backend.app.db.models.foundation import Decision, Evidence, Investigation
from backend.app.db.session import get_db
from backend.app.decision_followups import common, rules
from backend.app.evidence_workflow.people import Person, current_person
from backend.app.request_context import AuthenticatedRequestContext, get_request_context
from backend.app.workflow import tasks as task_service
from backend.app.workflow.labels import TASK_TYPES

logger = logging.getLogger("mdarix.decision_followups")

router = APIRouter(tags=["Impact Assessments"])
BASE = "/api/v1/impact-assessments"
SCHEDULER_ACTOR = "system:scheduler"
# Pieces of late evidence one organization's sweep handles per run (the rest are handled on the next run).
SWEEP_LIMIT = 500


# ---------------------------------------------------------------------------------------------- late evidence


def _owner_id(control_db, case):
    """The case owner's account id (``owner_ref`` holds a sign-in name); None when unowned, not an active colleague
    or not readable, so the task goes to the investigators' queue."""
    if not case.owner_ref or control_db is None:
        return None
    from backend.app.workflow.people import find_user

    try:
        user = find_user(control_db, case.tenant_id, case.owner_ref)
    except Exception:
        logger.warning("The owner of case %s could not be read", case.id, exc_info=True)
        return None
    return user.id if user is not None else None


def on_late_evidence(
    db: Session,
    control_db,
    case: Investigation,
    evidence_id,
    *,
    trigger: str,
    actor_ref: str,
    correlation_id: str | None = None,
) -> ImpactAssessment | None:
    """An OPEN impact assessment of ``evidence_id`` and its IMPACT_ASSESSMENT task, when ``case`` (locked by the
    caller) is DECIDED or CLOSED and has a current signed brief decision. Idempotent per decision and evidence
    (``rules.late_evidence_key``): None when one exists already or nothing is needed. Does not commit."""
    if case is None or states.case_state(case) not in rules.DECIDED_STATES:
        return None
    decision = common.current_decision(db, case.tenant_id, case.id)
    if decision is None:
        return None
    evidence = (
        db.query(Evidence.id, Evidence.business_id)
        .filter(Evidence.tenant_id == case.tenant_id, Evidence.id == as_uuid(evidence_id))
        .first()
    )
    if evidence is None:
        return None
    known = (
        db.query(ImpactAssessment.id)
        .filter(
            ImpactAssessment.tenant_id == case.tenant_id,
            ImpactAssessment.decision_id == decision.id,
            ImpactAssessment.evidence_id == evidence.id,
        )
        .first()
    )
    if known is not None:
        return None
    now = rules.now_utc()
    row = ImpactAssessment(
        id=uuid.uuid4(),
        tenant_id=case.tenant_id,
        investigation_id=case.id,
        decision_id=decision.id,
        trigger=str(trigger or "EVIDENCE_INGESTED").upper()[:40],
        evidence_id=evidence.id,
        status="OPEN",
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    db.flush()
    from backend.app.workflow.people import acting_role

    role = acting_role(control_db, case.tenant_id, actor_ref, rules.INVESTIGATION_WORK)
    task = task_service.create_task(
        db,
        case.tenant_id,
        task_type=rules.IMPACT_TASK,
        title=(
            f"Assess late evidence {evidence.business_id} on {case.business_id}: does it change decision "
            f"{decision.business_id}?"
        ),
        source_type=rules.IMPACT_SOURCE_TYPE,
        source_id=row.id,
        investigation_id=case.id,
        assigned_user_id=_owner_id(control_db, case),
        # Declining or releasing the owner's task hands it to the investigators' queue.
        assigned_role=TASK_TYPES[rules.IMPACT_TASK].queue_role,
        priority=case.priority or "MEDIUM",
        created_by=str(actor_ref),
        actor_role=role,
        correlation_id=correlation_id,
        details={
            "impact_assessment_id": str(row.id),
            "decision_id": str(decision.id),
            "evidence_id": str(evidence.id),
            "trigger": row.trigger,
        },
    )
    row.task_id = task.id
    common.audit(
        db,
        tenant_id=case.tenant_id,
        actor_ref=str(actor_ref),
        action="LATE_EVIDENCE_RECEIVED",
        entity_type=rules.IMPACT_ENTITY,
        entity_id=row.id,
        correlation_id=correlation_id,
        details={
            "investigation_id": str(case.id),
            "decision_id": str(decision.id),
            "decision_business_id": decision.business_id,
            "evidence_id": str(evidence.id),
            "evidence_business_id": evidence.business_id,
            "trigger": row.trigger,
            "workflow_state": states.case_state(case),
            "task_id": str(task.id),
            "actor_role": role,
        },
        now=now,
    )
    return row


def after_late_evidence(
    db: Session | None,
    control_db,
    tenant_id,
    investigation_id,
    evidence_ids,
    *,
    trigger: str,
    actor_ref: str,
    correlation_id: str | None = None,
) -> int:
    """``on_late_evidence`` for each piece of evidence, after the evidence action is saved: inside a SAVEPOINT,
    committed; a failure is logged and never blocks or undoes the action. Returns how many assessments were made."""
    ids = [as_uuid(item) for item in evidence_ids or () if as_uuid(item) is not None]
    if db is None or not ids or as_uuid(investigation_id) is None:
        return 0

    def step(session: Session) -> int:
        case = (
            session.query(Investigation)
            .filter(Investigation.tenant_id == as_uuid(tenant_id), Investigation.id == as_uuid(investigation_id))
            .with_for_update()
            .first()
        )
        if case is None or states.case_state(case) not in rules.DECIDED_STATES:
            return 0
        made = 0
        for evidence_id in dict.fromkeys(ids):
            if (
                on_late_evidence(
                    session,
                    control_db,
                    case,
                    evidence_id,
                    trigger=trigger,
                    actor_ref=actor_ref,
                    correlation_id=correlation_id,
                )
                is not None
            ):
                made += 1
        return made

    return task_service.run_hook(db, f"late evidence ({trigger})", step) or 0


def late_evidence(db: Session, tenant_id, *, limit: int = SWEEP_LIMIT) -> list[tuple]:
    """``(evidence id, investigation id)`` of evidence recorded for a DECIDED or CLOSED case after its current signed
    brief decision (ingested, else created, after ``decided_at``) that has no impact assessment for that decision."""
    tenant = as_uuid(tenant_id)
    received = func.coalesce(Evidence.ingestion_timestamp, Evidence.created_at)
    return (
        db.query(Evidence.id, Evidence.investigation_id)
        .join(
            Investigation,
            and_(Investigation.tenant_id == Evidence.tenant_id, Investigation.id == Evidence.investigation_id),
        )
        .join(Decision, and_(Decision.tenant_id == Evidence.tenant_id, Decision.investigation_id == Investigation.id))
        .filter(
            Evidence.tenant_id == tenant,
            Investigation.workflow_state.in_(rules.DECIDED_STATES),
            Decision.decision_kind == rules.BRIEF_KIND,
            Decision.decision_status == rules.SIGNED_STATUS,
            Decision.superseded_by_decision_id.is_(None),
            Decision.decided_at.isnot(None),
            received > Decision.decided_at,
            ~exists().where(
                ImpactAssessment.tenant_id == Evidence.tenant_id,
                ImpactAssessment.decision_id == Decision.id,
                ImpactAssessment.evidence_id == Evidence.id,
            ),
        )
        .order_by(Evidence.investigation_id, received, Evidence.id)
        .limit(limit)
        .all()
    )


def sweep_tenant(db: Session, control_db, tenant_id, *, limit: int = SWEEP_LIMIT) -> int:
    """Impact assessments for one organization's late evidence (``late_evidence``), each case locked and handled in
    a SAVEPOINT of its own (a case that fails is logged and tried again on the next run; the others are kept).
    Idempotent. Does not commit."""
    by_case: dict = defaultdict(list)
    for evidence_id, investigation_id in late_evidence(db, tenant_id, limit=limit):
        by_case[investigation_id].append(evidence_id)
    made = 0
    for investigation_id, evidence_ids in by_case.items():
        try:
            with db.begin_nested():
                case = (
                    db.query(Investigation)
                    .filter(Investigation.tenant_id == as_uuid(tenant_id), Investigation.id == investigation_id)
                    .with_for_update()
                    .first()
                )
                created = [
                    evidence_id
                    for evidence_id in evidence_ids
                    if on_late_evidence(
                        db, control_db, case, evidence_id, trigger="EVIDENCE_INGESTED", actor_ref=SCHEDULER_ACTOR
                    )
                    is not None
                ]
        except Exception:
            logger.exception(
                "Late evidence of case %s could not be handled; it is tried again next run", investigation_id
            )
            continue
        made += len(created)
    return made


def run_for_all_tenants(control_db: Session) -> dict:
    """The scheduler job: the late-evidence sweep for every active organization, on the shared plane or its own
    database, each committed on its own. A failing organization is logged and reported and the others still run; the
    job then fails so the scheduler alerts after repeated failures."""
    from backend.app.db.data_plane import open_tenant_data_session
    from backend.app.db.models.customer_lifecycle import TenantDataPlane
    from backend.app.db.models.foundation import Tenant

    totals = {"tenants": 0, "created": 0, "failed": []}
    tenant_ids = [
        row.id
        for row in control_db.query(Tenant.id)
        .join(TenantDataPlane, TenantDataPlane.tenant_id == Tenant.id)
        .filter(Tenant.status.in_(["ACTIVE", "active"]), TenantDataPlane.status == "ACTIVE")
        .order_by(Tenant.id)
        .all()
    ]
    for tenant_id in tenant_ids:
        try:
            with open_tenant_data_session(tenant_id) as data:
                try:
                    made = sweep_tenant(data, control_db, tenant_id)
                    data.commit()
                except Exception:
                    data.rollback()
                    raise
        except Exception as exc:
            logger.exception("The late-evidence sweep failed for organization %s", tenant_id)
            totals["failed"].append({"tenant_id": str(tenant_id), "error": type(exc).__name__})
            continue
        totals["tenants"] += 1
        totals["created"] += made
    if totals["failed"]:
        raise RuntimeError(
            f"Late-evidence sweep failed for {len(totals['failed'])} organization(s): {totals['failed']}"
        )
    return totals


# -------------------------------------------------------------------------------------------------------- reading


def _not_found():
    return common.error(404, "IMPACT_ASSESSMENT_NOT_FOUND", "Impact assessment not found")


def load(db: Session, tenant_id, assessment_id, *, lock: bool = False) -> ImpactAssessment:
    query = db.query(ImpactAssessment).filter(
        ImpactAssessment.id == as_uuid(assessment_id), ImpactAssessment.tenant_id == as_uuid(tenant_id)
    )
    if lock:
        query = query.with_for_update()
    row = query.first()
    if row is None:
        raise _not_found()
    return row


def serialize(db: Session, control_db: Session | None, person: Person, rows: list[ImpactAssessment]) -> list[dict]:
    if not rows:
        return []
    tenant_id = rows[0].tenant_id
    evidence_ids = wanted_ids(row.evidence_id for row in rows)
    evidence = (
        {
            str(found.id): found
            for found in db.query(Evidence.id, Evidence.business_id, Evidence.title).filter(
                Evidence.tenant_id == tenant_id, Evidence.id.in_(list(evidence_ids))
            )
        }
        if evidence_ids
        else {}
    )
    decision_ids = wanted_ids(row.decision_id for row in rows)
    decisions = (
        {
            str(found.id): found.business_id
            for found in db.query(Decision.id, Decision.business_id).filter(
                Decision.tenant_id == tenant_id, Decision.id.in_(list(decision_ids))
            )
        }
        if decision_ids
        else {}
    )
    people = common.names(control_db, tenant_id, (row.assessed_by for row in rows))
    can_work = person.holds(INVESTIGATION_WORK)
    items = []
    for row in rows:
        ev = evidence.get(str(row.evidence_id)) if row.evidence_id else None
        items.append(
            {
                "id": str(row.id),
                "business_id": row.business_id,
                "trigger": row.trigger,
                "trigger_label": rules.trigger_label(row.trigger),
                "evidence": (
                    {"id": str(ev.id), "business_id": ev.business_id, "title": ev.title} if ev is not None else None
                ),
                "decision": {"id": str(row.decision_id), "business_id": decisions.get(str(row.decision_id))},
                "status": row.status,
                "status_label": rules.IMPACT_STATUS_LABELS.get(row.status, row.status),
                "conclusion": row.conclusion,
                "conclusion_label": rules.conclusion_label(row.conclusion),
                "rationale": row.rationale,
                "assessed_by_name": common.name(people, row.assessed_by) if row.assessed_by else None,
                "assessed_role": row.assessed_role,
                "assessed_at": common.iso(row.assessed_at),
                "created_at": common.iso(row.created_at),
                "actions": rules.impact_actions(status=row.status, can_work=can_work),
            }
        )
    return items


@router.get("/api/v1/investigations/{investigation_id}/impact-assessments")
def list_case_impact_assessments(
    investigation_id: uuid.UUID,
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """Every impact assessment of the case, newest first."""
    tenant_id = common.tenant_of(ctx)
    case = common.load_case(db, tenant_id, investigation_id)
    person = current_person(control_db, ctx)
    rows = (
        db.query(ImpactAssessment)
        .filter(ImpactAssessment.tenant_id == tenant_id, ImpactAssessment.investigation_id == case.id)
        .order_by(ImpactAssessment.created_at.desc(), ImpactAssessment.business_id.desc())
        .all()
    )
    return {"items": serialize(db, control_db, person, rows)}


@router.get(BASE + "/{assessment_id}")
def get_impact_assessment(
    assessment_id: uuid.UUID,
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    person = current_person(control_db, ctx)
    return serialize(db, control_db, person, [load(db, common.tenant_of(ctx), assessment_id)])[0]


# ------------------------------------------------------------------------------------------------------ changing


@router.post(BASE + "/{assessment_id}/complete", dependencies=[Depends(require_permission(INVESTIGATION_WORK))])
def complete_impact_assessment(
    assessment_id: uuid.UUID,
    payload: rules.ImpactCompletePayload,
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """Conclude an open impact assessment: NO_IMPACT or MATERIAL_IMPACT, with the rationale. Its task completes. A
    material impact on the case's current decision moves a DECIDED or CLOSED case back to IN_PROGRESS and records
    that the decision is under reconsideration; the signed decision itself is never changed."""
    tenant_id = common.tenant_of(ctx)
    person = current_person(control_db, ctx)
    row = load(db, tenant_id, assessment_id, lock=True)
    if row.status != "OPEN":
        raise common.error(409, "IMPACT_ASSESSMENT_COMPLETED", "This impact assessment is already completed")
    case = common.load_case(db, tenant_id, row.investigation_id, lock=True)
    now = rules.now_utc()
    role = person.role_for(INVESTIGATION_WORK)
    row.status = "COMPLETED"
    row.conclusion = payload.conclusion
    row.rationale = payload.rationale
    row.assessed_by = person.user_id
    row.assessed_role = role
    row.assessed_at = now
    row.updated_at = now
    material = payload.conclusion == "MATERIAL_IMPACT"
    current = common.current_decision(db, tenant_id, case.id)
    decision_current = current is not None and current.id == row.decision_id
    before_state = states.case_state(case)
    before = {"workflow_state": case.workflow_state, "status": case.status}
    reopened = False
    common.audit(
        db,
        tenant_id=tenant_id,
        actor_ref=person.user_id,
        action="IMPACT_ASSESSMENT_COMPLETED",
        entity_type=rules.IMPACT_ENTITY,
        entity_id=row.id,
        correlation_id=ctx.correlation_id,
        reason=payload.rationale,
        old_values={"status": "OPEN"},
        new_values={"status": "COMPLETED", "conclusion": payload.conclusion},
        details={
            "investigation_id": str(case.id),
            "decision_id": str(row.decision_id),
            "evidence_id": str(row.evidence_id) if row.evidence_id else None,
            "conclusion": payload.conclusion,
            "decision_current": decision_current,
            "actor_role": role,
        },
        now=now,
    )
    if material and decision_current:
        common.audit(
            db,
            tenant_id=tenant_id,
            actor_ref=person.user_id,
            action="DECISION_UNDER_RECONSIDERATION",
            entity_type="Decision",
            entity_id=current.id,
            correlation_id=ctx.correlation_id,
            reason=payload.rationale,
            details={
                "investigation_id": str(case.id),
                "decision_business_id": current.business_id,
                "impact_assessment_id": str(row.id),
                "impact_assessment_business_id": row.business_id,
                "evidence_id": str(row.evidence_id) if row.evidence_id else None,
                "actor_role": role,
            },
            now=now,
        )
        if before_state in rules.DECIDED_STATES:
            states.set_state(case, "IN_PROGRESS", now)
            states.audit_state_change(
                db,
                case,
                actor_ref=person.user_id,
                before=before,
                reason=(
                    f"Impact assessment {row.business_id}: late evidence has a material impact on decision "
                    f"{current.business_id}"
                ),
                correlation_id=ctx.correlation_id,
                details={"impact_assessment_id": str(row.id), "decision_id": str(current.id), "from": before_state},
                now=now,
            )
            reopened = True
    db.commit()
    task_id = row.task_id
    if task_id is not None:
        task_service.run_hook(
            db,
            "impact assessment completed",
            lambda session: common.finish_task(
                session,
                tenant_id,
                task_id,
                to_status="COMPLETED",
                outcome=payload.conclusion,
                actor_ref=person.user_id,
                actor_role=role,
                correlation_id=ctx.correlation_id,
            ),
        )
    if reopened:
        # The case's tasks and signals follow it as reopening does: a task for its owner (or the queue), and its
        # closed or decided signals are open again. Never blocks or undoes the assessment.
        from backend.app.workflow.hooks import on_investigation_managed

        on_investigation_managed(
            db, control_db, case, actor_user_id=person.user_id, before_owner=case.owner_ref, before_status="closed"
        )
        from backend.app.signals.hooks import on_investigation_status_changed

        on_investigation_status_changed(db, control_db, case, actor_user_id=person.user_id, before_status="closed")
    result = serialize(db, control_db, person, [load(db, tenant_id, row.id)])[0]
    case = common.load_case(db, tenant_id, row.investigation_id)
    return {
        **result,
        "case_reopened": reopened,
        "decision_under_reconsideration": bool(material and decision_current),
        "workflow_state": states.case_state(case),
    }


__all__ = [
    "router",
    "on_late_evidence",
    "after_late_evidence",
    "late_evidence",
    "sweep_tenant",
    "run_for_all_tenants",
    "serialize",
    "load",
]
