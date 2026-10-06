"""What evidence requests and evidence reviews do to workflow tasks. Each ``on_*`` function runs after its action is
saved, inside a SAVEPOINT on the same data-plane session, and commits its own changes (``tasks.run_hook``); a failure is
logged and swallowed, so a task can never block or undo the action.

- a request to a colleague or a role: an EVIDENCE_RESPONSE task for the person (ASSIGNED) or the role queue (NEW), and
  for the requester the WAITING EVIDENCE_REQUEST task a supplier request also gets;
- acknowledging: the recipient's task is accepted (or taken from the queue);
- an answer: the recipient's task and the requester's waiting task complete; the requester gets EVIDENCE_REVIEW;
- cannot provide: the same tasks complete; the requester gets a FOLLOW_UP task (``is_return``);
- cancelling: every open task of the request is cancelled;
- reviewing the answer (or later the evidence it became): the requester's EVIDENCE_REVIEW task completes.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from backend.app.business_ids import as_uuid
from backend.app.db.models.workflow import WorkflowTask
from backend.app.evidence_workflow.rules import KIND_INTERNAL, task_source_type
from backend.app.workflow import tasks as service
from backend.app.workflow.labels import TASK_TYPES
from backend.app.workflow.people import acting_role, find_user

RESPONSE_TASK = "EVIDENCE_RESPONSE"
WAITING_TASK = "EVIDENCE_REQUEST"
REVIEW_TASK = "EVIDENCE_REVIEW"


def _permission(task_type: str) -> str:
    return TASK_TYPES[task_type].permission


def _requester(control_db, row):
    if control_db is None:
        return None
    user = find_user(control_db, row.tenant_id, row.requested_by)
    return user.id if user is not None else None


def _role(control_db, row, actor: str, task_type: str):
    return acting_role(control_db, row.tenant_id, actor, _permission(task_type))


def _waiting_task(session, control_db, row, *, actor: str, role):
    requester = _requester(control_db, row)
    return service.create_task(
        session,
        row.tenant_id,
        task_type=WAITING_TASK,
        title=f"Waiting for evidence {row.business_id}: {service.shorten(row.title, 160)}",
        source_type=task_source_type(row.request_kind),
        source_id=row.id,
        investigation_id=row.investigation_id,
        assigned_user_id=requester,
        status="WAITING" if requester is not None else None,
        priority=row.priority or "MEDIUM",
        due_at=row.due_at,
        created_by=actor,
        actor_role=role,
    )


def on_internal_request_created(db: Session, control_db, row, *, actor_user_id) -> None:
    def step(session):
        actor = str(actor_user_id)
        role = _role(control_db, row, actor, WAITING_TASK)
        service.create_task(
            session,
            row.tenant_id,
            task_type=RESPONSE_TASK,
            title=f"Provide evidence {row.business_id}: {service.shorten(row.title, 160)}",
            source_type=task_source_type(row.request_kind),
            source_id=row.id,
            investigation_id=row.investigation_id,
            assigned_user_id=row.recipient_user_id,
            # A role named on the request is the task's queue (declining a person's task hands it back to it).
            assigned_role=row.recipient_role or None,
            priority=row.priority or "MEDIUM",
            due_at=row.due_at,
            created_by=actor,
            actor_role=role,
            details={"request_kind": KIND_INTERNAL},
        )
        _waiting_task(session, control_db, row, actor=actor, role=role)

    service.run_hook(db, "internal evidence request created", step)


def on_supplier_request_scheduled(db: Session, row) -> None:
    """A supplier request made from a case carries a priority and a due date: the requester's waiting task (created
    by the supplier flow's own hook) takes them too."""

    def step(session):
        if row.due_at is None and (row.priority or "MEDIUM") == "MEDIUM":
            return
        for task in service._open_tasks(
            session,
            row.tenant_id,
            task_types=[WAITING_TASK],
            source_type=task_source_type(row.request_kind),
            source_id=row.id,
        ).with_for_update():
            task.priority = row.priority or task.priority
            task.due_at = row.due_at
            task.updated_at = service.now_utc()

    service.run_hook(db, "supplier evidence request scheduled", step)


def on_request_acknowledged(db: Session, control_db, row, *, actor_user_id) -> None:
    def step(session):
        actor = str(actor_user_id)
        me = as_uuid(actor)
        if me is None:
            return
        role = _role(control_db, row, actor, RESPONSE_TASK)
        rows = (
            service._open_tasks(
                session,
                row.tenant_id,
                task_types=[RESPONSE_TASK],
                source_type=task_source_type(row.request_kind),
                source_id=row.id,
            )
            .order_by(WorkflowTask.created_at)
            .with_for_update()
            .all()
        )
        now = service.now_utc()
        for task in rows:
            if task.assigned_user_id == me and task.status == "ASSIGNED":
                event = "ACCEPTED"
            elif task.assigned_user_id is None and task.status in service.QUEUE_STATUSES:
                event = "CLAIMED"
                task.assigned_user_id = me
            else:
                continue
            previous = task.status
            task.status = "ACCEPTED"
            task.accepted_at = now
            task.updated_at = now
            service.record_event(
                session,
                task,
                event,
                actor_ref=actor,
                actor_role=role,
                from_status=previous,
                to_status="ACCEPTED",
                details={"evidence_request_acknowledged": True},
                now=now,
            )
            return

    service.run_hook(db, "evidence request acknowledged", step)


def _finish_answer_tasks(session, control_db, row, *, actor: str, outcome: str) -> None:
    source_type = task_source_type(row.request_kind)
    service.complete_tasks(
        session,
        row.tenant_id,
        source_type=source_type,
        source_id=row.id,
        task_types=[RESPONSE_TASK],
        outcome=outcome,
        actor_ref=actor,
        actor_role=_role(control_db, row, actor, RESPONSE_TASK),
    )
    service.complete_tasks(
        session,
        row.tenant_id,
        source_type=source_type,
        source_id=row.id,
        task_types=[WAITING_TASK],
        outcome=outcome,
        actor_ref=actor,
        actor_role=_role(control_db, row, actor, RESPONSE_TASK),
    )


def on_request_responded(db: Session, control_db, row, *, actor_user_id) -> None:
    def step(session):
        actor = str(actor_user_id)
        _finish_answer_tasks(session, control_db, row, actor=actor, outcome="REPLY_RECEIVED")
        service.create_task(
            session,
            row.tenant_id,
            task_type=REVIEW_TASK,
            title=f"Review evidence response {row.business_id}",
            source_type=task_source_type(row.request_kind),
            source_id=row.id,
            investigation_id=row.investigation_id,
            assigned_user_id=_requester(control_db, row),
            priority=row.priority or "MEDIUM",
            created_by=actor,
            actor_role=_role(control_db, row, actor, RESPONSE_TASK),
        )

    service.run_hook(db, "evidence request answered", step)


def on_request_cannot_provide(db: Session, control_db, row, *, actor_user_id) -> None:
    def step(session):
        actor = str(actor_user_id)
        _finish_answer_tasks(session, control_db, row, actor=actor, outcome="CANNOT_PROVIDE")
        service.create_task(
            session,
            row.tenant_id,
            task_type="FOLLOW_UP",
            title=f"{row.business_id} cannot be provided: {service.shorten(row.title, 160)}",
            source_type=task_source_type(row.request_kind),
            source_id=row.id,
            investigation_id=row.investigation_id,
            assigned_user_id=_requester(control_db, row),
            priority=row.priority or "MEDIUM",
            created_by=actor,
            is_return=True,
            actor_role=_role(control_db, row, actor, RESPONSE_TASK),
            details={"cannot_provide": True},
        )

    service.run_hook(db, "evidence request cannot be provided", step)


def on_request_cancelled(db: Session, control_db, row, *, actor_user_id, reason: str | None = None) -> None:
    def step(session):
        actor = str(actor_user_id)
        service.cancel_tasks(
            session,
            row.tenant_id,
            source_type=task_source_type(row.request_kind),
            source_id=row.id,
            outcome="REQUEST_CANCELLED",
            actor_ref=actor,
            actor_role=_role(control_db, row, actor, WAITING_TASK),
            reason=reason,
        )

    service.run_hook(db, "evidence request cancelled", step)


def _complete_reviews(session, control_db, row, *, actor: str, outcome: str) -> None:
    service.complete_tasks(
        session,
        row.tenant_id,
        source_type=task_source_type(row.request_kind),
        source_id=row.id,
        task_types=[REVIEW_TASK],
        outcome=outcome,
        actor_ref=actor,
        actor_role=_role(control_db, row, actor, REVIEW_TASK),
    )


def on_request_reviewed(db: Session, control_db, row, *, actor_user_id, accepted: bool) -> None:
    def step(session):
        _complete_reviews(
            session,
            control_db,
            row,
            actor=str(actor_user_id),
            outcome="EVIDENCE_ACCEPTED" if accepted else "RESPONSE_REJECTED",
        )

    service.run_hook(db, "evidence request reviewed", step)


def on_evidence_reviewed(db: Session, control_db, tenant_id, evidence_id, *, actor_user_id) -> None:
    """Reviewing evidence that came from a request completes that request's open EVIDENCE_REVIEW task, if any."""

    def step(session):
        from backend.app.db.models.stage3 import SupplierEvidenceRequest

        rows = (
            session.query(SupplierEvidenceRequest)
            .filter(
                SupplierEvidenceRequest.tenant_id == as_uuid(tenant_id),
                SupplierEvidenceRequest.resolved_evidence_id == as_uuid(evidence_id),
            )
            .all()
        )
        for row in rows:
            _complete_reviews(session, control_db, row, actor=str(actor_user_id), outcome="EVIDENCE_REVIEWED")

    service.run_hook(db, "evidence reviewed", step)


__all__ = [
    "on_internal_request_created",
    "on_supplier_request_scheduled",
    "on_request_acknowledged",
    "on_request_responded",
    "on_request_cannot_provide",
    "on_request_cancelled",
    "on_request_reviewed",
    "on_evidence_reviewed",
]
