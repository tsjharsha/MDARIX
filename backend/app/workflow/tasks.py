"""Workflow tasks: create, finish and move tasks. Every change writes a task history row (workflow_task_events) and
an audit event (``TASK_<EVENT>``) in the same session, which is the tenant's data plane (where the source records
live). Nothing here commits; callers do (see ``run_hook`` for the never-blocking hooks of existing actions).
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from backend.app.business_ids import as_uuid
from backend.app.db.models.workflow import (
    OPEN_TASK_STATUSES,
    TASK_PRIORITIES,
    TASK_STATUSES,
    WorkflowTask,
    WorkflowTaskEvent,
)
from backend.app.enterprise_audit import make_audit_event
from backend.app.role_codes import role_code
from backend.app.workflow.labels import task_type as task_type_definition

logger = logging.getLogger("mdarix.workflow")

# Statuses that end a task, and the statuses of a task waiting in a role queue for someone to claim it.
FINISHED_STATUSES = ("COMPLETED", "CANCELLED", "SUPERSEDED")
QUEUE_STATUSES = ("NEW", "DECLINED", "ESCALATED")
# Who created or changed a task when no person did (backfill, automatic transitions without a signed-in user).
SYSTEM_ACTOR = "system"
TITLE_LENGTH = 300
OUTCOME_LENGTH = 60


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def shorten(text: Any, length: int) -> str:
    """One line of at most ``length`` characters, cut at a word with an ellipsis when longer."""
    value = " ".join(str(text or "").split())
    if len(value) <= length:
        return value
    cut = value[: max(length - 1, 1)].rsplit(" ", 1)[0] or value[: max(length - 1, 1)]
    return cut.rstrip(" ,;:.") + "…"


def record_event(
    db: Session,
    task: WorkflowTask,
    event_type: str,
    *,
    actor_ref: str | None,
    actor_role: str | None = None,
    from_status: str | None = None,
    to_status: str | None = None,
    reason: str | None = None,
    details: dict | None = None,
    correlation_id: str | None = None,
    now: datetime | None = None,
) -> WorkflowTaskEvent:
    """The task's history row and the matching audit event (action ``TASK_<EVENT>``). Does not commit."""
    now = now or now_utc()
    actor = str(actor_ref) if actor_ref else SYSTEM_ACTOR
    role = (role_code(actor_role) or None) if actor_role else None
    event = WorkflowTaskEvent(
        id=uuid.uuid4(),
        tenant_id=task.tenant_id,
        task_id=task.id,
        event_type=event_type,
        actor_ref=actor,
        actor_role=role,
        from_status=from_status,
        to_status=to_status,
        reason=reason,
        details=dict(details or {}),
        created_at=now,
    )
    db.add(event)
    db.add(
        make_audit_event(
            tenant_id=task.tenant_id,
            actor_ref=actor,
            action=f"TASK_{event_type}",
            entity_type="WorkflowTask",
            entity_id=task.id,
            correlation_id=correlation_id,
            reason=reason,
            details={
                "task_type": task.task_type,
                "source_type": task.source_entity_type,
                "source_id": str(task.source_entity_id),
                "investigation_id": str(task.investigation_id) if task.investigation_id else None,
                "from_status": from_status,
                "to_status": to_status,
                "actor_role": role,
                **dict(details or {}),
            },
            created_at=now,
        )
    )
    return event


def _open_tasks(db: Session, tenant_id, **filters):
    query = db.query(WorkflowTask).filter(
        WorkflowTask.tenant_id == as_uuid(tenant_id), WorkflowTask.status.in_(OPEN_TASK_STATUSES)
    )
    if filters.get("task_types"):
        query = query.filter(WorkflowTask.task_type.in_([str(item).upper() for item in filters["task_types"]]))
    if filters.get("source_type") is not None:
        query = query.filter(WorkflowTask.source_entity_type == filters["source_type"])
    if filters.get("source_id") is not None:
        query = query.filter(WorkflowTask.source_entity_id == as_uuid(filters["source_id"]))
    if filters.get("investigation_id") is not None:
        query = query.filter(WorkflowTask.investigation_id == as_uuid(filters["investigation_id"]))
    return query


def has_open_task(db: Session, tenant_id, *, task_type: str, source_type: str, source_id) -> bool:
    """True when the source already has an open task of this type, whoever it is for."""
    return (
        _open_tasks(db, tenant_id, task_types=[task_type], source_type=source_type, source_id=source_id).first()
        is not None
    )


def create_task(
    db: Session,
    tenant_id,
    *,
    task_type: str,
    title: str,
    source_type: str,
    source_id,
    investigation_id=None,
    assigned_user_id=None,
    assigned_role: str | None = None,
    priority: str = "MEDIUM",
    due_at: datetime | None = None,
    created_by,
    status: str | None = None,
    is_return: bool = False,
    details: dict | None = None,
    actor_role: str | None = None,
    correlation_id: str | None = None,
) -> WorkflowTask:
    """A new task for a person (``assigned_user_id``) or a role queue (``assigned_role``; by default the type's queue
    role when no person is named). Status defaults to ASSIGNED for a person and NEW for a queue.

    Idempotent: an open task of the same type for the same source and the same assignee (the same person, or for a
    queue task the same role) is returned instead of a duplicate. Does not commit."""
    code = str(task_type or "").strip().upper()
    definition = task_type_definition(code)
    tenant = as_uuid(tenant_id)
    source = as_uuid(source_id)
    if tenant is None or source is None:
        raise ValueError("A task needs its organization and its source record")
    user = as_uuid(assigned_user_id)
    role = role_code(assigned_role) if assigned_role else None
    if user is None and not role:
        role = definition.queue_role
    status = str(status or ("ASSIGNED" if user else "NEW")).upper()
    if status not in TASK_STATUSES:
        raise ValueError(f"Unknown task status {status!r}")
    priority = str(priority or "MEDIUM").upper()
    if priority not in TASK_PRIORITIES:
        raise ValueError(f"Unknown task priority {priority!r}")
    existing = _open_tasks(db, tenant, task_types=[code], source_type=source_type, source_id=source)
    if user is not None:
        existing = existing.filter(WorkflowTask.assigned_user_id == user)
    else:
        existing = existing.filter(WorkflowTask.assigned_user_id.is_(None), WorkflowTask.assigned_role == role)
    found = existing.order_by(WorkflowTask.created_at).first()
    if found is not None:
        return found
    now = now_utc()
    task = WorkflowTask(
        id=uuid.uuid4(),
        tenant_id=tenant,
        task_type=code,
        title=shorten(title, TITLE_LENGTH) or definition.label,
        source_entity_type=source_type,
        source_entity_id=source,
        investigation_id=as_uuid(investigation_id),
        assigned_role=role,
        assigned_user_id=user,
        priority=priority,
        due_at=due_at,
        status=status,
        is_return=bool(is_return),
        created_by=str(created_by or SYSTEM_ACTOR),
        created_at=now,
        updated_at=now,
        accepted_at=now if status in ("ACCEPTED", "IN_PROGRESS") else None,
        escalation_level=0,
        details=dict(details or {}),
    )
    db.add(task)
    # The history row references the task (foreign key), so the task is written first.
    db.flush()
    record_event(
        db,
        task,
        "CREATED",
        actor_ref=str(created_by or SYSTEM_ACTOR),
        actor_role=actor_role,
        to_status=status,
        details={"assigned_user_id": str(user) if user else None, "assigned_role": role, "is_return": bool(is_return)},
        correlation_id=correlation_id,
        now=now,
    )
    return task


def _finish(
    db: Session,
    tenant_id,
    *,
    to_status: str,
    event_type: str,
    outcome: str | None,
    actor_ref,
    actor_role: str | None,
    source_type: str | None = None,
    source_id=None,
    task_types=None,
    investigation_id=None,
    reason: str | None = None,
    correlation_id: str | None = None,
) -> list[WorkflowTask]:
    if source_id is None and investigation_id is None:
        raise ValueError("Name the source record or the investigation whose tasks end")
    rows = (
        _open_tasks(
            db,
            tenant_id,
            task_types=task_types,
            source_type=source_type,
            source_id=source_id,
            investigation_id=investigation_id,
        )
        .order_by(WorkflowTask.created_at)
        .with_for_update()
        .all()
    )
    now = now_utc()
    for task in rows:
        previous = task.status
        task.status = to_status
        task.completed_at = now
        task.completion_outcome = (shorten(outcome, OUTCOME_LENGTH) or None) if outcome else None
        task.updated_at = now
        record_event(
            db,
            task,
            event_type,
            actor_ref=actor_ref,
            actor_role=actor_role,
            from_status=previous,
            to_status=to_status,
            reason=reason,
            details={"outcome": task.completion_outcome},
            correlation_id=correlation_id,
            now=now,
        )
    if rows:
        db.flush()
    return rows


def complete_tasks(
    db: Session,
    tenant_id,
    *,
    source_type: str,
    source_id,
    task_types,
    outcome: str,
    actor_ref,
    actor_role: str | None = None,
    reason: str | None = None,
    correlation_id: str | None = None,
) -> list[WorkflowTask]:
    """Mark the source's open tasks of these types COMPLETED with ``outcome``. Does not commit."""
    return _finish(
        db,
        tenant_id,
        to_status="COMPLETED",
        event_type="COMPLETED",
        outcome=outcome,
        actor_ref=actor_ref,
        actor_role=actor_role,
        source_type=source_type,
        source_id=source_id,
        task_types=task_types,
        reason=reason,
        correlation_id=correlation_id,
    )


def cancel_tasks(
    db: Session,
    tenant_id,
    *,
    source_type: str | None = None,
    source_id=None,
    task_types=None,
    investigation_id=None,
    outcome: str,
    actor_ref,
    actor_role: str | None = None,
    reason: str | None = None,
    correlation_id: str | None = None,
) -> list[WorkflowTask]:
    """Cancel open tasks of a source (optionally of some types), or every open task of an investigation
    (``investigation_id``). Does not commit."""
    return _finish(
        db,
        tenant_id,
        to_status="CANCELLED",
        event_type="CANCELLED",
        outcome=outcome,
        actor_ref=actor_ref,
        actor_role=actor_role,
        source_type=source_type,
        source_id=source_id,
        task_types=task_types,
        investigation_id=investigation_id,
        reason=reason,
        correlation_id=correlation_id,
    )


def supersede_tasks(
    db: Session,
    tenant_id,
    *,
    source_type: str,
    source_id,
    task_types,
    outcome: str = "SUPERSEDED",
    actor_ref,
    actor_role: str | None = None,
    reason: str | None = None,
    correlation_id: str | None = None,
) -> list[WorkflowTask]:
    """Mark the source's open tasks of these types SUPERSEDED (a newer task replaces them). Does not commit."""
    return _finish(
        db,
        tenant_id,
        to_status="SUPERSEDED",
        event_type="SUPERSEDED",
        outcome=outcome,
        actor_ref=actor_ref,
        actor_role=actor_role,
        source_type=source_type,
        source_id=source_id,
        task_types=task_types,
        reason=reason,
        correlation_id=correlation_id,
    )


def run_hook(db: Session | None, name: str, step, *args, **kwargs):
    """Run one task hook of an existing action, after that action is saved: inside a SAVEPOINT on the data-plane
    session, then committed. A failure is logged and swallowed (the session is rolled back to a clean state), so a
    task can never block or undo the action itself. Returns the step's result, or None when it failed."""
    if db is None:
        return None
    try:
        with db.begin_nested():
            result = step(db, *args, **kwargs)
        db.commit()
        return result
    except Exception:
        logger.exception("Workflow task hook %s failed; the action itself is saved", name)
        try:
            db.rollback()
        except Exception:
            logger.exception("Workflow task hook %s: the session could not be rolled back", name)
        return None
