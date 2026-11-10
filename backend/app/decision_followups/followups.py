"""The follow-up actions of a signed decision (FUP000001): what the decision maker chose while signing (a CAPA, a
product change, a field action review, a risk reassessment, a regulatory action), with its owner, task and status.
The signing step creates them (backend/app/human_decision); this module lets people work on them.

- ``GET  /api/v1/investigations/{id}/follow-ups``: the case's follow-ups;
- ``GET  /api/v1/follow-ups`` (``box`` mine | all, ``status``, paging) and ``GET /api/v1/follow-ups/{id}``;
- ``POST /api/v1/follow-ups/{id}/start`` (the assignee; when nobody is named, anyone holding its role): IN_PROGRESS,
  and the person accepts its task (or takes it from the queue);
- ``POST /api/v1/follow-ups/{id}/complete`` (the same people) with a note: DONE, its FOLLOW_UP task completes;
- ``POST /api/v1/follow-ups/{id}/cancel`` (``investigation.assign``) with a reason: CANCELLED, its task is cancelled;
- ``POST /api/v1/follow-ups/{id}/capa`` (``investigation.work``; CAPA_REQUIRED follow-ups, once): records the CAPA to
  raise in the QMS (``capas``, with its QMS reference when known) for the case and links it;
- ``POST /api/v1/follow-ups/{id}/capa/qms-reference`` (``investigation.work``): the number the QMS gave that CAPA
  (J22), set, changed or cleared.

Completing the FOLLOW_UP task through My Work completes the follow-up too (``on_follow_up_task_completed``). Reading
needs a signed-in session; everything is limited to the signed-in organization (another organization's follow-up is
"not found"). Every change locks the follow-up row, is audited (FOLLOW_UP_<EVENT>) with the role it was done under,
and moves its task through a never-blocking hook.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy import and_, false, or_
from sqlalchemy.orm import Session

from backend.app.access.permissions import INVESTIGATION_ASSIGN, INVESTIGATION_WORK, require_permission
from backend.app.business_ids import as_uuid, wanted_ids
from backend.app.db.data_plane import get_data_plane_db
from backend.app.db.models.decision_outcomes import DecisionFollowUp
from backend.app.db.models.foundation import Capa, Decision, Investigation
from backend.app.db.session import get_db
from backend.app.decision_followups import common, rules
from backend.app.evidence_workflow.people import Person, current_person
from backend.app.request_context import AuthenticatedRequestContext, get_request_context
from backend.app.workflow import tasks as task_service
from backend.app.workflow.labels import role_label

router = APIRouter(tags=["Decision Follow-ups"])
BASE = "/api/v1/follow-ups"
BOXES = ("mine", "all")


def _not_found():
    return common.error(404, "FOLLOW_UP_NOT_FOUND", "Follow-up not found")


def _conflict(message: str):
    return common.error(409, "FOLLOW_UP_STATE_CONFLICT", message)


def load(db: Session, tenant_id, follow_up_id, *, lock: bool = False) -> DecisionFollowUp:
    query = db.query(DecisionFollowUp).filter(
        DecisionFollowUp.id == as_uuid(follow_up_id), DecisionFollowUp.tenant_id == as_uuid(tenant_id)
    )
    if lock:
        query = query.with_for_update()
    row = query.first()
    if row is None:
        raise _not_found()
    return row


def responsible(person: Person, row: DecisionFollowUp) -> bool:
    return rules.is_responsible(
        assignee_user_id=row.assignee_user_id,
        assigned_role=row.assigned_role,
        user_uuid=person.user_uuid,
        role_codes=person.role_codes,
        holds_work=person.holds(INVESTIGATION_WORK),
    )


def actions_for(person: Person, row: DecisionFollowUp) -> dict[str, bool]:
    return rules.follow_up_actions(
        status=row.status,
        action_type=row.action_type,
        capa_id=row.capa_id,
        responsible=responsible(person, row),
        can_assign=person.holds(INVESTIGATION_ASSIGN),
        can_work=person.holds(INVESTIGATION_WORK),
    )


def serialize(db: Session, control_db: Session | None, person: Person, rows: list[DecisionFollowUp]) -> list[dict]:
    """The FollowUp JSON of each row; decisions, cases, CAPAs and names are read in bulk."""
    if not rows:
        return []
    tenant_id = rows[0].tenant_id
    now = rules.now_utc()

    def lookup(model, columns, ids) -> dict[str, tuple]:
        wanted = wanted_ids(ids)
        if not wanted:
            return {}
        return {
            str(found[0]): found
            for found in db.query(model.id, *columns).filter(model.tenant_id == tenant_id, model.id.in_(list(wanted)))
        }

    decisions = lookup(Decision, (Decision.business_id, Decision.outcome), (row.decision_id for row in rows))
    cases = lookup(Investigation, (Investigation.business_id,), (row.investigation_id for row in rows))
    capas = lookup(Capa, (Capa.business_id, Capa.capa_identifier, Capa.qms_reference), (row.capa_id for row in rows))
    people = common.names(
        control_db, tenant_id, [ref for row in rows for ref in (row.assignee_user_id, row.completed_by)]
    )
    items = []
    for row in rows:
        decision = decisions.get(str(row.decision_id))
        case = cases.get(str(row.investigation_id))
        capa = capas.get(str(row.capa_id)) if row.capa_id else None
        items.append(
            {
                "id": str(row.id),
                "business_id": row.business_id,
                "action_type": row.action_type,
                "action_label": rules.action_label(row.action_type),
                "title": row.title,
                "status": row.status,
                "status_label": rules.status_label(row.status),
                "assignee": (
                    {"id": str(row.assignee_user_id), "name": common.name(people, row.assignee_user_id)}
                    if row.assignee_user_id
                    else None
                ),
                "assigned_role": row.assigned_role,
                "assigned_role_label": role_label(row.assigned_role),
                "due_at": common.iso(row.due_at),
                "overdue": rules.is_overdue(row.status, row.due_at, now),
                "decision": {
                    "id": str(row.decision_id),
                    "business_id": decision[1] if decision else None,
                    "outcome": decision[2] if decision else None,
                },
                "investigation": {"id": str(row.investigation_id), "business_id": case[1] if case else None},
                "capa": (
                    {
                        "id": str(row.capa_id),
                        "business_id": capa[1] if capa else None,
                        "capa_identifier": capa[2] if capa else None,
                        "qms_reference": capa[3] if capa else None,
                    }
                    if row.capa_id
                    else None
                ),
                "completion_note": row.completion_note,
                "completed_by_name": common.name(people, row.completed_by) if row.completed_by else None,
                "completed_at": common.iso(row.completed_at),
                "actions": actions_for(person, row),
            }
        )
    return items


def _one(db: Session, control_db: Session, person: Person, row: DecisionFollowUp) -> dict:
    return serialize(db, control_db, person, [load(db, row.tenant_id, row.id)])[0]


def _ordered(query):
    return query.order_by(DecisionFollowUp.due_at.asc().nulls_last(), DecisionFollowUp.created_at.desc())


# -------------------------------------------------------------------------------------------------------- reading


@router.get("/api/v1/investigations/{investigation_id}/follow-ups")
def list_case_follow_ups(
    investigation_id: uuid.UUID,
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """Every follow-up of the case (of all its decisions), oldest first."""
    tenant_id = common.tenant_of(ctx)
    case = common.load_case(db, tenant_id, investigation_id)
    person = current_person(control_db, ctx)
    rows = (
        db.query(DecisionFollowUp)
        .filter(DecisionFollowUp.tenant_id == tenant_id, DecisionFollowUp.investigation_id == case.id)
        .order_by(DecisionFollowUp.created_at, DecisionFollowUp.business_id)
        .all()
    )
    return {"items": serialize(db, control_db, person, rows)}


def _box_query(db: Session, person: Person, box: str):
    query = db.query(DecisionFollowUp).filter(DecisionFollowUp.tenant_id == person.tenant_id)
    if box == "all":
        return query
    mine = DecisionFollowUp.assignee_user_id == person.user_uuid if person.user_uuid is not None else false()
    roles = sorted(person.role_codes)
    by_role = (
        and_(DecisionFollowUp.assignee_user_id.is_(None), DecisionFollowUp.assigned_role.in_(roles))
        if roles
        else false()
    )
    return query.filter(or_(mine, by_role))


@router.get(BASE)
def list_follow_ups(
    box: str = Query(default="mine", pattern="^(" + "|".join(BOXES) + ")$"),
    status: str | None = Query(default=None, max_length=200),
    page: int = Query(default=1, ge=1, le=100000),
    page_size: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """One page of follow-ups: ``mine`` (assigned to me, or to one of my roles with nobody named) or ``all``;
    optionally in some statuses (comma separated). Soonest due first."""
    person = current_person(control_db, ctx)
    query = _box_query(db, person, box)
    if status:
        wanted = [item.strip().upper() for item in status.split(",") if item.strip()]
        unknown = [item for item in wanted if item not in rules.STATUS_LABELS]
        if unknown:
            raise common.error(422, "UNKNOWN_STATUS", f"Choose from: {', '.join(rules.STATUS_LABELS)}")
        if wanted:
            query = query.filter(DecisionFollowUp.status.in_(wanted))
    total = query.count()
    rows = _ordered(query).offset((page - 1) * page_size).limit(page_size).all()
    return {"items": serialize(db, control_db, person, rows), "total": total, "page": page, "page_size": page_size}


@router.get(BASE + "/{follow_up_id}")
def get_follow_up(
    follow_up_id: uuid.UUID,
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    person = current_person(control_db, ctx)
    return serialize(db, control_db, person, [load(db, common.tenant_of(ctx), follow_up_id)])[0]


# ------------------------------------------------------------------------------------------------------ changing


def _require_responsible(person: Person, row: DecisionFollowUp) -> None:
    if not responsible(person, row):
        raise common.error(
            403, "FOLLOW_UP_NOT_YOURS", "Only the person this follow-up is assigned to, or its role, can do this"
        )


def _task_hook(db: Session, name: str, step) -> None:
    task_service.run_hook(db, name, step)


@router.post(BASE + "/{follow_up_id}/start")
def start_follow_up(
    follow_up_id: uuid.UUID,
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """Start work on an open follow-up: IN_PROGRESS, and it is yours (when it was assigned to your role). Its task is
    accepted (or taken from the queue)."""
    person = current_person(control_db, ctx)
    row = load(db, common.tenant_of(ctx), follow_up_id, lock=True)
    _require_responsible(person, row)
    if row.status != "OPEN":
        raise _conflict("Only an open follow-up can be started")
    now = rules.now_utc()
    role = person.role_for(INVESTIGATION_WORK)
    before = {
        "status": row.status,
        "assignee_user_id": str(row.assignee_user_id) if row.assignee_user_id else None,
    }
    row.status = "IN_PROGRESS"
    if row.assignee_user_id is None and person.user_uuid is not None:
        row.assignee_user_id = person.user_uuid
    row.updated_at = now
    common.audit(
        db,
        tenant_id=row.tenant_id,
        actor_ref=person.user_id,
        action="FOLLOW_UP_STARTED",
        entity_type=rules.FOLLOW_UP_ENTITY,
        entity_id=row.id,
        correlation_id=ctx.correlation_id,
        old_values=before,
        new_values={
            "status": row.status,
            "assignee_user_id": str(row.assignee_user_id) if row.assignee_user_id else None,
        },
        details=_details(row, role),
        now=now,
    )
    db.commit()
    task_id, tenant_id = row.task_id, row.tenant_id
    if task_id is not None:
        _task_hook(
            db,
            "follow-up started",
            lambda session: common.take_task(
                session,
                tenant_id,
                task_id,
                user_uuid=person.user_uuid,
                actor_role=role,
                correlation_id=ctx.correlation_id,
            ),
        )
    return _one(db, control_db, person, row)


def _details(row: DecisionFollowUp, role: str | None, **extra) -> dict:
    return {
        "investigation_id": str(row.investigation_id),
        "decision_id": str(row.decision_id),
        "action_type": row.action_type,
        "actor_role": role,
        **extra,
    }


@router.post(BASE + "/{follow_up_id}/complete")
def complete_follow_up(
    follow_up_id: uuid.UUID,
    payload: rules.FollowUpCompletePayload,
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """Record that the follow-up is done, with a note of what was done: DONE; its FOLLOW_UP task completes."""
    person = current_person(control_db, ctx)
    row = load(db, common.tenant_of(ctx), follow_up_id, lock=True)
    _require_responsible(person, row)
    if row.status not in rules.OPEN_FOLLOW_UP_STATUSES:
        raise _conflict("Only an open follow-up or one in progress can be completed")
    now = rules.now_utc()
    role = person.role_for(INVESTIGATION_WORK)
    before = row.status
    row.status = "DONE"
    row.completion_note = payload.note
    row.completed_by = person.user_id
    row.completed_at = now
    row.updated_at = now
    common.audit(
        db,
        tenant_id=row.tenant_id,
        actor_ref=person.user_id,
        action="FOLLOW_UP_COMPLETED",
        entity_type=rules.FOLLOW_UP_ENTITY,
        entity_id=row.id,
        correlation_id=ctx.correlation_id,
        reason=payload.note,
        old_values={"status": before},
        new_values={"status": "DONE"},
        details=_details(row, role),
        now=now,
    )
    db.commit()
    task_id, tenant_id = row.task_id, row.tenant_id
    if task_id is not None:
        _task_hook(
            db,
            "follow-up completed",
            lambda session: common.finish_task(
                session,
                tenant_id,
                task_id,
                to_status="COMPLETED",
                outcome="FOLLOW_UP_DONE",
                actor_ref=person.user_id,
                actor_role=role,
                correlation_id=ctx.correlation_id,
            ),
        )
    return _one(db, control_db, person, row)


@router.post(BASE + "/{follow_up_id}/cancel", dependencies=[Depends(require_permission(INVESTIGATION_ASSIGN))])
def cancel_follow_up(
    follow_up_id: uuid.UUID,
    payload: rules.ReasonPayload,
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """Cancel a follow-up still to be done, with a reason (kept as its closing note): CANCELLED; its task is
    cancelled."""
    person = current_person(control_db, ctx)
    row = load(db, common.tenant_of(ctx), follow_up_id, lock=True)
    if row.status not in rules.OPEN_FOLLOW_UP_STATUSES:
        raise _conflict("Only an open follow-up or one in progress can be cancelled")
    now = rules.now_utc()
    role = person.role_for(INVESTIGATION_ASSIGN)
    before = row.status
    row.status = "CANCELLED"
    row.completion_note = payload.reason
    row.completed_by = person.user_id
    row.completed_at = now
    row.updated_at = now
    common.audit(
        db,
        tenant_id=row.tenant_id,
        actor_ref=person.user_id,
        action="FOLLOW_UP_CANCELLED",
        entity_type=rules.FOLLOW_UP_ENTITY,
        entity_id=row.id,
        correlation_id=ctx.correlation_id,
        reason=payload.reason,
        old_values={"status": before},
        new_values={"status": "CANCELLED"},
        details=_details(row, role),
        now=now,
    )
    db.commit()
    task_id, tenant_id = row.task_id, row.tenant_id
    if task_id is not None:
        _task_hook(
            db,
            "follow-up cancelled",
            lambda session: common.finish_task(
                session,
                tenant_id,
                task_id,
                to_status="CANCELLED",
                outcome="FOLLOW_UP_CANCELLED",
                actor_ref=person.user_id,
                actor_role=role,
                reason=payload.reason,
                correlation_id=ctx.correlation_id,
            ),
        )
    return _one(db, control_db, person, row)


@router.post(
    BASE + "/{follow_up_id}/capa", status_code=201, dependencies=[Depends(require_permission(INVESTIGATION_WORK))]
)
def create_follow_up_capa(
    follow_up_id: uuid.UUID,
    payload: rules.CapaPayload,
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """Open the CAPA a CAPA_REQUIRED follow-up asks for (once): a ``capas`` record CAPA-<case>-<n> for the case's
    product, sourced from the decision, linked to the follow-up. The follow-up itself stays as it is."""
    tenant_id = common.tenant_of(ctx)
    person = current_person(control_db, ctx)
    row = load(db, tenant_id, follow_up_id, lock=True)
    if str(row.action_type or "").upper() != "CAPA_REQUIRED":
        raise common.error(409, "FOLLOW_UP_NOT_CAPA", "Only a follow-up that requires a CAPA can open one")
    if row.capa_id is not None:
        raise common.error(409, "CAPA_ALREADY_CREATED", "This follow-up already has its CAPA")
    if row.status == "CANCELLED":
        raise _conflict("A cancelled follow-up cannot open a CAPA")
    # The case row is locked so two CAPAs of the same case never take the same number.
    case = common.load_case(db, tenant_id, row.investigation_id, lock=True)
    decision = db.query(Decision).filter(Decision.tenant_id == tenant_id, Decision.id == row.decision_id).first()
    taken = {
        value
        for (value,) in db.query(Capa.capa_identifier).filter(
            Capa.tenant_id == tenant_id, Capa.capa_identifier.like(f"CAPA-{case.business_id}-%")
        )
    }
    identifier = rules.capa_identifier(case.business_id, taken)
    now = rules.now_utc()
    role = person.role_for(INVESTIGATION_WORK)
    capa = Capa(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        capa_identifier=identifier,
        title=payload.title,
        action_type=rules.CAPA_ACTION_TYPE,
        source_type=rules.CAPA_SOURCE_TYPE,
        source_reference=decision.business_id if decision is not None else None,
        source_system=rules.CAPA_SOURCE_SYSTEM,
        source_identifier=identifier,
        product_id=case.product_id,
        investigation_id=case.id,
        status=rules.CAPA_STATUS,
        opened_at=now,
        due_at=payload.due_at,
        qms_reference=payload.qms_reference,
        source_timestamp=now,
        effective_timestamp=now,
        recorded_timestamp=now,
        ingestion_timestamp=now,
        created_at=now,
        updated_at=now,
    )
    db.add(capa)
    db.flush()
    row.capa_id = capa.id
    row.updated_at = now
    common.audit(
        db,
        tenant_id=tenant_id,
        actor_ref=person.user_id,
        action="FOLLOW_UP_CAPA_CREATED",
        entity_type=rules.FOLLOW_UP_ENTITY,
        entity_id=row.id,
        correlation_id=ctx.correlation_id,
        new_values={"capa_id": str(capa.id), "capa_identifier": identifier},
        details=_details(
            row,
            role,
            capa_id=str(capa.id),
            capa_identifier=identifier,
            title=payload.title,
            due_at=common.iso(payload.due_at),
            qms_reference=payload.qms_reference,
        ),
        now=now,
    )
    db.commit()
    return _one(db, control_db, person, row)


@router.post(
    BASE + "/{follow_up_id}/capa/qms-reference",
    dependencies=[Depends(require_permission(INVESTIGATION_WORK))],
)
def set_capa_qms_reference(
    follow_up_id: uuid.UUID,
    payload: rules.QmsReferencePayload,
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """The number the QMS gave the CAPA this follow-up recorded (J22): set, changed, or cleared with a blank. The
    CAPA itself is raised and run in the QMS; MDARIX keeps its reference beside the decision."""
    tenant_id = common.tenant_of(ctx)
    person = current_person(control_db, ctx)
    row = load(db, tenant_id, follow_up_id, lock=True)
    capa = (
        db.query(Capa).filter(Capa.tenant_id == tenant_id, Capa.id == row.capa_id).with_for_update().first()
        if row.capa_id
        else None
    )
    if capa is None:
        raise common.error(409, "FOLLOW_UP_HAS_NO_CAPA", "Record the CAPA to raise in your QMS first")
    before = capa.qms_reference
    if before == payload.qms_reference:
        return _one(db, control_db, person, row)
    now = rules.now_utc()
    capa.qms_reference = payload.qms_reference
    capa.updated_at = now
    common.audit(
        db,
        tenant_id=tenant_id,
        actor_ref=person.user_id,
        action="FOLLOW_UP_CAPA_QMS_REFERENCE_SET",
        entity_type=rules.FOLLOW_UP_ENTITY,
        entity_id=row.id,
        correlation_id=ctx.correlation_id,
        old_values={"qms_reference": before},
        new_values={"qms_reference": payload.qms_reference},
        details=_details(
            row, person.role_for(INVESTIGATION_WORK), capa_id=str(capa.id), capa_identifier=capa.capa_identifier
        ),
        now=now,
    )
    db.commit()
    return _one(db, control_db, person, row)


# ---------------------------------------------------------------------------------------------------------- hooks


def on_follow_up_task_completed(db: Session, task, *, actor_ref: str, actor_role=None, note=None, correlation_id=None):
    """A FOLLOW_UP task of a follow-up (``details.follow_up_id``) completed through My Work completes the follow-up
    too (DONE, with the completion reason as its note). Runs after the task change is saved and never blocks or
    undoes it (``tasks.run_hook``)."""
    details = getattr(task, "details", None) or {}
    follow_up_id = as_uuid(details.get("follow_up_id"))
    if follow_up_id is None:
        return None
    tenant_id = task.tenant_id
    task_ref = task.business_id or str(task.id)
    text = " ".join(str(note or "").split())

    def step(session: Session):
        row = (
            session.query(DecisionFollowUp)
            .filter(DecisionFollowUp.tenant_id == tenant_id, DecisionFollowUp.id == follow_up_id)
            .with_for_update()
            .first()
        )
        if row is None or row.status not in rules.OPEN_FOLLOW_UP_STATUSES:
            return None
        now = rules.now_utc()
        before = row.status
        row.status = "DONE"
        row.completion_note = text if len(text) >= rules.NOTE_MIN else f"Completed through its task {task_ref}"
        row.completed_by = str(actor_ref)
        row.completed_at = now
        row.updated_at = now
        common.audit(
            session,
            tenant_id=tenant_id,
            actor_ref=str(actor_ref),
            action="FOLLOW_UP_COMPLETED",
            entity_type=rules.FOLLOW_UP_ENTITY,
            entity_id=row.id,
            correlation_id=correlation_id,
            reason=row.completion_note,
            old_values={"status": before},
            new_values={"status": "DONE"},
            details=_details(row, actor_role, through_task=task_ref),
            now=now,
        )
        return row

    return task_service.run_hook(db, "follow-up task completed", step)


def on_case_closed(db: Session, control_db, case, *, actor_user_id, correlation_id=None) -> None:
    """Follow-ups outlive their case: closing a case cancels every open task of it (backend/app/workflow/hooks.py),
    so each follow-up still open whose FOLLOW_UP task was cancelled that way gets a new task like it, and the
    follow-up points at it (audited FOLLOW_UP_TASK_RENEWED). Never blocks or undoes the closing."""
    tenant_id, case_id = case.tenant_id, case.id
    actor = str(actor_user_id)

    def step(session: Session):
        from backend.app.db.models.workflow import WorkflowTask
        from backend.app.workflow.people import acting_role

        rows = (
            session.query(DecisionFollowUp)
            .filter(
                DecisionFollowUp.tenant_id == tenant_id,
                DecisionFollowUp.investigation_id == case_id,
                DecisionFollowUp.status.in_(rules.OPEN_FOLLOW_UP_STATUSES),
                DecisionFollowUp.task_id.isnot(None),
            )
            .with_for_update()
            .all()
        )
        if not rows:
            return 0
        tasks = {
            task.id: task
            for task in session.query(WorkflowTask).filter(
                WorkflowTask.tenant_id == tenant_id, WorkflowTask.id.in_([row.task_id for row in rows])
            )
        }
        role = acting_role(control_db, tenant_id, actor, rules.INVESTIGATION_WORK)
        renewed = 0
        for row in rows:
            old = tasks.get(row.task_id)
            if old is None or old.status != "CANCELLED" or old.completion_outcome != "CASE_CLOSED":
                continue
            task = task_service.create_task(
                session,
                tenant_id,
                task_type=rules.FOLLOW_UP_TASK,
                title=old.title,
                source_type=old.source_entity_type,
                source_id=old.source_entity_id,
                investigation_id=old.investigation_id,
                assigned_user_id=old.assigned_user_id,
                assigned_role=old.assigned_role,
                priority=old.priority,
                due_at=old.due_at,
                created_by=actor,
                status="ACCEPTED" if old.assigned_user_id and row.status == "IN_PROGRESS" else None,
                details={**dict(old.details or {}), "follow_up_id": str(row.id), "renewed_from_task_id": str(old.id)},
                actor_role=role,
                correlation_id=correlation_id,
            )
            if task.id == old.id:
                continue
            row.task_id = task.id
            row.updated_at = rules.now_utc()
            common.audit(
                session,
                tenant_id=tenant_id,
                actor_ref=actor,
                action="FOLLOW_UP_TASK_RENEWED",
                entity_type=rules.FOLLOW_UP_ENTITY,
                entity_id=row.id,
                correlation_id=correlation_id,
                old_values={"task_id": str(old.id)},
                new_values={"task_id": str(task.id)},
                details=_details(row, role, reason="The investigation was closed; the follow-up stays open"),
            )
            renewed += 1
        return renewed

    task_service.run_hook(db, "follow-up tasks after the case closed", step)


__all__ = ["router", "on_follow_up_task_completed", "on_case_closed", "serialize", "load"]
