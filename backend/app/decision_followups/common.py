"""What follow-ups, impact assessments and the closure check share: errors, loading a case of the signed-in
organization, the case's current signed decision, people's names, and moving one workflow task by its id (with its
history row and ``TASK_<EVENT>`` audit event). Nothing here commits.
"""

from __future__ import annotations

import logging
import uuid

from fastapi import HTTPException
from sqlalchemy.orm import Session

from backend.app.business_ids import as_uuid
from backend.app.db.models.foundation import Decision, Investigation
from backend.app.db.models.workflow import OPEN_TASK_STATUSES, WorkflowTask
from backend.app.decision_followups import rules
from backend.app.enterprise_audit import make_audit_event
from backend.app.workflow import tasks as task_service

logger = logging.getLogger("mdarix.decision_followups")


def error(status: int, code: str, message: str, **extra) -> HTTPException:
    return HTTPException(status, detail={"code": code, "message": message, **extra})


def iso(value) -> str | None:
    return value.isoformat() if value is not None else None


def tenant_of(ctx) -> uuid.UUID:
    return uuid.UUID(str(ctx.tenant_id))


def load_case(db: Session, tenant_id, investigation_id, *, lock: bool = False) -> Investigation:
    query = db.query(Investigation).filter(
        Investigation.id == as_uuid(investigation_id), Investigation.tenant_id == as_uuid(tenant_id)
    )
    if lock:
        query = query.with_for_update()
    case = query.first()
    if case is None:
        raise error(404, "INVESTIGATION_NOT_FOUND", "Investigation not found")
    return case


def current_decision(db: Session, tenant_id, investigation_id) -> Decision | None:
    """The case's current signed human decision on its Decision Brief: kind BRIEF, signed, not superseded (the
    latest when there were ever more than one)."""
    return (
        db.query(Decision)
        .filter(
            Decision.tenant_id == as_uuid(tenant_id),
            Decision.investigation_id == as_uuid(investigation_id),
            Decision.decision_kind == rules.BRIEF_KIND,
            Decision.decision_status == rules.SIGNED_STATUS,
            Decision.superseded_by_decision_id.is_(None),
        )
        .order_by(Decision.decided_at.desc().nulls_last(), Decision.created_at.desc())
        .first()
    )


def names(control_db: Session | None, tenant_id, refs) -> dict[str, str]:
    """``{str(user id): name}`` for the organization's accounts among ``refs``; empty when they cannot be read."""
    if control_db is None:
        return {}
    from backend.app.workflow.people import names_by_id

    try:
        return names_by_id(control_db, tenant_id, refs)
    except Exception:
        logger.warning("Names could not be read", exc_info=True)
        return {}


def name(found: dict[str, str], ref) -> str | None:
    key = as_uuid(ref)
    if key is not None:
        return found.get(str(key))
    # Changes MDARIX made itself (the scheduler, automatic steps); any other text reference is not shown.
    return "MDARIX" if str(ref or "").startswith(task_service.SYSTEM_ACTOR) else None


def audit(
    db: Session,
    *,
    tenant_id,
    actor_ref: str,
    action: str,
    entity_type: str,
    entity_id,
    reason: str | None = None,
    correlation_id: str | None = None,
    old_values: dict | None = None,
    new_values: dict | None = None,
    details: dict | None = None,
    now=None,
) -> None:
    db.add(
        make_audit_event(
            tenant_id=tenant_id,
            actor_ref=str(actor_ref),
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            correlation_id=correlation_id,
            reason=reason,
            old_values=old_values,
            new_values=new_values,
            details=dict(details or {}),
            created_at=now,
        )
    )


# ------------------------------------------------------------------------------------------------------- tasks


def _locked_task(db: Session, tenant_id, task_id) -> WorkflowTask | None:
    if as_uuid(task_id) is None:
        return None
    return (
        db.query(WorkflowTask)
        .filter(WorkflowTask.tenant_id == as_uuid(tenant_id), WorkflowTask.id == as_uuid(task_id))
        .with_for_update()
        .first()
    )


def finish_task(
    db: Session,
    tenant_id,
    task_id,
    *,
    to_status: str,
    outcome: str,
    actor_ref: str,
    actor_role: str | None = None,
    reason: str | None = None,
    correlation_id: str | None = None,
) -> WorkflowTask | None:
    """COMPLETED or CANCELLED for one open task, with its history row and audit event; None when the task is
    unknown or already finished. Does not commit."""
    task = _locked_task(db, tenant_id, task_id)
    if task is None or task.status not in OPEN_TASK_STATUSES:
        return None
    now = task_service.now_utc()
    previous = task.status
    task.status = to_status
    task.completed_at = now
    task.completion_outcome = task_service.shorten(outcome, task_service.OUTCOME_LENGTH) or None
    task.updated_at = now
    task_service.record_event(
        db,
        task,
        to_status,
        actor_ref=actor_ref,
        actor_role=actor_role,
        from_status=previous,
        to_status=to_status,
        reason=reason,
        details={"outcome": task.completion_outcome},
        correlation_id=correlation_id,
        now=now,
    )
    db.flush()
    return task


def take_task(
    db: Session,
    tenant_id,
    task_id,
    *,
    user_uuid,
    actor_role: str | None = None,
    correlation_id: str | None = None,
) -> WorkflowTask | None:
    """The person starting the work accepts their task (ASSIGNED to them) or takes it from its queue; a task already
    accepted, finished or someone else's is left as it is. Does not commit."""
    me = as_uuid(user_uuid)
    task = _locked_task(db, tenant_id, task_id)
    if task is None or me is None or task.status not in OPEN_TASK_STATUSES:
        return None
    if task.assigned_user_id == me and task.status == "ASSIGNED":
        event = "ACCEPTED"
    elif task.assigned_user_id is None and task.status in task_service.QUEUE_STATUSES:
        event = "CLAIMED"
        task.assigned_user_id = me
    else:
        return task
    now = task_service.now_utc()
    previous = task.status
    task.status = "ACCEPTED"
    task.accepted_at = now
    task.updated_at = now
    task_service.record_event(
        db,
        task,
        event,
        actor_ref=str(me),
        actor_role=actor_role,
        from_status=previous,
        to_status="ACCEPTED",
        details={"follow_up_started": True},
        correlation_id=correlation_id,
        now=now,
    )
    db.flush()
    return task
