"""Next steps of a case: the old decision options as actions that do something (``/api/v1/investigations/{id}``).

- ``GET  /next-steps/options``: every action with its label, description and whether the signed-in person may take
  it on the case now (and why not);
- ``POST /next-steps`` (``investigation.work``) ``{action, reason, details?}``:
  - CONTINUE_INVESTIGATION, NO_DECISION_YET: recorded with the reason;
  - REQUEST_RISK_REVIEW, REQUEST_REGULATORY_REVIEW: a review request (as ``POST .../reviews``), ``details: {due_at?}``;
  - REQUEST_ADDITIONAL_EVIDENCE, REQUEST_ADDITIONAL_TESTING: a request to a colleague or a role through the evidence
    request flow (also needs ``evidence.request``), ``details: {title, requested_items, recipient_user_id? |
    recipient_role?, due_at?, priority?, unknown_id?}``; a testing request's title starts "Testing: ";
  - REVIEW_SUPPLIER_CHANGE, REVIEW_PRODUCT_CHANGE: a FOLLOW_UP task, by default for the case owner,
    ``details: {assignee_user_id? | assigned_role?, title?}``;
  - ESCALATE_FOR_QUALITY_REVIEW: nothing is written (409 USE_DECISION_BRIEF): quality review happens on the Decision
    Brief.

Every action taken is audited (NEXT_STEP_RECORDED, with what it created) and shown in the case's intelligence history.
The decision endpoints (``POST /api/v1/investigations/{id}/decisions``) are unchanged.
"""

from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends
from pydantic import ValidationError
from sqlalchemy.orm import Session

from backend.app.access.permissions import EVIDENCE_REQUEST, INVESTIGATION_WORK, require_permission
from backend.app.case_reviews import rules, service
from backend.app.case_reviews.router import _case, request_review_and_task
from backend.app.db.data_plane import get_data_plane_db
from backend.app.db.models.foundation import Investigation
from backend.app.db.session import get_db
from backend.app.enterprise_audit import make_audit_event
from backend.app.evidence_workflow.people import Person, current_person
from backend.app.request_context import AuthenticatedRequestContext, get_request_context

logger = logging.getLogger("mdarix.case_reviews")
router = APIRouter(prefix="/api/v1/investigations", tags=["Case Reviews"])

LABELS = {code: label for code, label, _ in rules.NEXT_STEPS}
HISTORY_OBJECT = "NEXT_STEP"
HISTORY_EVENT = "NEXT_STEP_RECORDED"


def _invalid(exc: ValidationError):
    problems = exc.errors()
    message = str(problems[0].get("msg")) if problems else "The details of this next step are not valid"
    field = ".".join(str(part) for part in problems[0].get("loc") or ()) if problems else None
    return service.error(
        422, "INVALID_NEXT_STEP_DETAILS", message.removeprefix("Value error, "), **({"field": field} if field else {})
    )


def _record(
    db: Session,
    ctx: AuthenticatedRequestContext,
    person: Person,
    case: Investigation,
    action: str,
    reason: str,
    result: dict,
) -> None:
    """The next step in the audit trail (NEXT_STEP_RECORDED) and, when it can be written, the case's intelligence
    history. Does not commit."""
    from backend.app.db.models.intelligence import IntelligenceEvent

    now = service.now_utc()
    role = person.role_for(INVESTIGATION_WORK)
    details = {"action": action, "action_label": LABELS.get(action), **result}
    db.add(
        make_audit_event(
            tenant_id=case.tenant_id,
            actor_ref=person.user_id,
            action="NEXT_STEP_RECORDED",
            entity_type="Investigation",
            entity_id=case.id,
            correlation_id=ctx.correlation_id,
            reason=reason,
            details={**details, "actor_role": role},
            created_at=now,
        )
    )
    try:
        with db.begin_nested():
            db.add(
                IntelligenceEvent(
                    id=uuid.uuid4(),
                    tenant_id=case.tenant_id,
                    investigation_id=case.id,
                    object_type=HISTORY_OBJECT,
                    object_id=case.id,
                    event_type=HISTORY_EVENT,
                    to_value=action,
                    reason=reason,
                    actor_ref=person.user_id,
                    actor_role=role,
                    details={key: value for key, value in details.items() if value is not None},
                    created_at=now,
                )
            )
            db.flush()
    except Exception:
        logger.warning("The next step on case %s could not be added to its history", case.id, exc_info=True)


@router.get("/{investigation_id}/next-steps/options")
def next_step_options(
    investigation_id: uuid.UUID,
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """The next steps of the case, each with whether the signed-in person may take it now and why not."""
    case = _case(db, uuid.UUID(str(ctx.tenant_id)), investigation_id)
    person = current_person(control_db, ctx)
    open_types = service.open_review_types(db, case)
    options = []
    for code, label, description in rules.NEXT_STEPS:
        available, why_not = rules.next_step_availability(
            code,
            can_work=person.holds(INVESTIGATION_WORK),
            can_request_evidence=person.holds(EVIDENCE_REQUEST),
            case_open=service.case_is_open(case),
            open_review_types=open_types,
        )
        options.append(
            {
                "action": code,
                "label": label,
                "description": description,
                "available": available,
                "unavailable_reason": why_not,
            }
        )
    return {
        "investigation": {"id": str(case.id), "business_id": case.business_id},
        "options": options,
    }


def _evidence_request(db, control_db, ctx, person: Person, case: Investigation, action: str, details, reason: str):
    from backend.app.evidence_workflow.requests import create_evidence_request
    from backend.app.evidence_workflow.rules import KIND_INTERNAL, EvidenceRequestPayload

    if not person.holds(EVIDENCE_REQUEST):
        raise service.error(
            403, "PERMISSION_DENIED", "Your role does not allow requesting evidence", permission=EVIDENCE_REQUEST
        )
    title = rules.testing_title(details.title) if action == rules.REQUEST_ADDITIONAL_TESTING else details.title
    try:
        payload = EvidenceRequestPayload(
            kind=KIND_INTERNAL,
            title=title,
            requested_items=details.requested_items,
            rationale=reason,
            unknown_id=details.unknown_id,
            due_at=details.due_at,
            priority=details.priority,
            recipient_user_id=details.recipient_user_id,
            recipient_role=details.recipient_role,
        )
    except ValidationError as exc:
        raise _invalid(exc) from exc
    created = create_evidence_request(investigation_id=case.id, payload=payload, db=db, control_db=control_db, ctx=ctx)
    return {
        "business_id": created.get("business_id"),
        "evidence_request": {"id": created.get("id"), "business_id": created.get("business_id")},
        "evidence_request_id": created.get("id"),
        "evidence_request_business_id": created.get("business_id"),
    }


def _follow_up(db: Session, control_db: Session, ctx, person: Person, case: Investigation, action: str, details):
    """A FOLLOW_UP task about the case for the person or role named, else the case owner (else the investigators'
    queue). An open follow-up of the same next step for the same person or role is returned instead of a second one.
    Does not commit."""
    from backend.app.access.permissions import permissions_for_roles
    from backend.app.db.models.workflow import OPEN_TASK_STATUSES, WorkflowTask
    from backend.app.role_codes import role_code
    from backend.app.workflow import tasks
    from backend.app.workflow.labels import TASK_TYPES, known_role
    from backend.app.workflow.people import find_user, may_hold_tasks

    definition = TASK_TYPES["FOLLOW_UP"]
    user = None
    role = None
    if details.assignee_user_id is not None:
        user = find_user(control_db, case.tenant_id, details.assignee_user_id)
        if user is None or not may_hold_tasks(control_db, user, definition.permission):
            raise service.error(
                422, "ASSIGNEE_NOT_ELIGIBLE", "Choose an active colleague whose roles allow working on investigations"
            )
    if details.assigned_role:
        role = role_code(details.assigned_role)
        if not known_role(role) or definition.permission not in (permissions_for_roles([role]) or ()):
            raise service.error(422, "ROLE_NOT_ELIGIBLE", "That role does not work on investigations")
    if user is None and role is None and case.owner_ref:
        owner = find_user(control_db, case.tenant_id, case.owner_ref)
        user = owner if owner is not None and may_hold_tasks(control_db, owner, definition.permission) else None
    if user is None and role is None:
        role = definition.queue_role
    existing = db.query(WorkflowTask).filter(
        WorkflowTask.tenant_id == case.tenant_id,
        WorkflowTask.task_type == "FOLLOW_UP",
        WorkflowTask.source_entity_type == "Investigation",
        WorkflowTask.source_entity_id == case.id,
        WorkflowTask.status.in_(OPEN_TASK_STATUSES),
        WorkflowTask.details["next_step"].astext == action,
    )
    if user is not None:
        existing = existing.filter(WorkflowTask.assigned_user_id == user.id)
    else:
        existing = existing.filter(WorkflowTask.assigned_user_id.is_(None), WorkflowTask.assigned_role == role)
    found = existing.order_by(WorkflowTask.created_at).first()
    if found is not None:
        return found, False
    now = tasks.now_utc()
    status = "ASSIGNED" if user is not None else "NEW"
    task = WorkflowTask(
        id=uuid.uuid4(),
        tenant_id=case.tenant_id,
        task_type="FOLLOW_UP",
        title=tasks.shorten(details.title or rules.change_title(action, case.business_id), tasks.TITLE_LENGTH),
        source_entity_type="Investigation",
        source_entity_id=case.id,
        investigation_id=case.id,
        assigned_role=role,
        assigned_user_id=user.id if user is not None else None,
        priority=str(case.priority or "MEDIUM").upper()
        if str(case.priority or "").upper() in ("LOW", "MEDIUM", "HIGH", "CRITICAL")
        else "MEDIUM",
        status=status,
        is_return=False,
        created_by=person.user_id,
        created_at=now,
        updated_at=now,
        escalation_level=0,
        details={"next_step": action, "next_step_label": LABELS.get(action)},
    )
    db.add(task)
    db.flush()
    tasks.record_event(
        db,
        task,
        "CREATED",
        actor_ref=person.user_id,
        actor_role=person.role_for(INVESTIGATION_WORK),
        to_status=status,
        details={
            "assigned_user_id": str(task.assigned_user_id) if task.assigned_user_id else None,
            "assigned_role": role,
            "is_return": False,
            "next_step": action,
        },
        correlation_id=ctx.correlation_id,
        now=now,
    )
    return task, True


@router.post(
    "/{investigation_id}/next-steps",
    status_code=201,
    dependencies=[Depends(require_permission(INVESTIGATION_WORK))],
)
def take_next_step(
    investigation_id: uuid.UUID,
    payload: rules.NextStepPayload,
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """Take a next step on the case (see the module docstring): ``{action, action_label, result}`` where ``result``
    names what was created: ``business_id`` of the created record (None for a recorded note), the record itself
    (``review``, ``evidence_request`` or ``task``: ``{id, business_id}``) and the same ids as flat fields."""
    tenant_id = uuid.UUID(str(ctx.tenant_id))
    action = payload.action
    case = _case(db, tenant_id, investigation_id)
    if action == rules.ESCALATE_FOR_QUALITY_REVIEW:
        raise service.error(409, "USE_DECISION_BRIEF", rules.USE_DECISION_BRIEF)
    if not service.case_is_open(case):
        raise service.error(409, "INVESTIGATION_CLOSED", "This investigation is closed; reopen it first")
    try:
        details = rules.next_step_details(action, payload.details)
    except ValidationError as exc:
        raise _invalid(exc) from exc
    person = current_person(control_db, ctx)
    reason = payload.reason

    if action in rules.NOTE_ACTIONS:
        case = _case(db, tenant_id, investigation_id, lock=True)
        # Nothing is created but the record itself (audit trail and the case's history).
        result = {"recorded": True, "business_id": None}
        _record(db, ctx, person, case, action, reason, result)
        db.commit()
    elif action in rules.REVIEW_ACTIONS:
        case = _case(db, tenant_id, investigation_id, lock=True)
        result = {}

        def record(row):
            result.update(
                {
                    "business_id": row.business_id,
                    "review": {"id": str(row.id), "business_id": row.business_id},
                    "review_id": str(row.id),
                    "review_business_id": row.business_id,
                }
            )
            _record(db, ctx, person, case, action, reason, dict(result))

        request_review_and_task(
            db,
            ctx,
            person,
            case,
            review_type=rules.REVIEW_ACTIONS[action],
            reason=reason,
            due_at=details.due_at,
            before_commit=record,
        )
    elif action in rules.EVIDENCE_ACTIONS:
        result = _evidence_request(db, control_db, ctx, person, case, action, details, reason)
        case = _case(db, tenant_id, investigation_id)
        _record(db, ctx, person, case, action, reason, result)
        db.commit()
    else:
        case = _case(db, tenant_id, investigation_id, lock=True)
        task, created = _follow_up(db, control_db, ctx, person, case, action, details)
        result = {
            "business_id": task.business_id,
            "task": {"id": str(task.id), "business_id": task.business_id, "title": task.title},
            "task_id": str(task.id),
            "task_business_id": task.business_id,
            "task_created": created,
        }
        _record(db, ctx, person, case, action, reason, result)
        db.commit()
    return {"action": action, "action_label": LABELS.get(action), "result": result}
