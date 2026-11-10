"""What case reviews do to workflow tasks. Each ``on_*`` function is called by the reviews router after its change is
committed; it runs inside a SAVEPOINT and commits its own changes (``workflow.tasks.run_hook``). A failure is logged
and swallowed: a task can never block or undo the review change that caused it.

- requesting a review: a RISK_REVIEW or REGULATORY_REVIEW task in the reviewers' role queue ("Risk review of
  INV000147");
- starting it: the reviewer claims (or accepts) that task, which is then in progress;
- completing it: the task is completed with the outcome; an outcome that asks for more evidence or escalates gives
  the case owner (else the investigators' queue) a FOLLOW_UP task (``is_return``) describing it;
- recusing: the task goes back to the queue; cancelling: the review's open tasks are cancelled.

Superseding reviews after a scope change is done with the scope save (``service.restart_reviews``).
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from backend.app.case_reviews import rules
from backend.app.workflow import tasks as service
from backend.app.workflow.labels import TASK_TYPES

PRIORITIES = ("LOW", "MEDIUM", "HIGH", "CRITICAL")


def task_title(review, case_reference: str | None) -> str:
    label = rules.TYPE_LABELS.get(review.review_type, "Review")
    return f"{label} of {case_reference}" if case_reference else label


def _priority(value: str | None) -> str:
    code = str(value or "").strip().upper()
    return code if code in PRIORITIES else "MEDIUM"


def _open_review_tasks(session: Session, review):
    from backend.app.db.models.workflow import OPEN_TASK_STATUSES, WorkflowTask

    return (
        session.query(WorkflowTask)
        .filter(
            WorkflowTask.tenant_id == review.tenant_id,
            WorkflowTask.source_entity_type == rules.SOURCE_TYPE,
            WorkflowTask.source_entity_id == review.id,
            WorkflowTask.task_type == rules.TYPE_TASKS[review.review_type],
            WorkflowTask.status.in_(OPEN_TASK_STATUSES),
        )
        .order_by(WorkflowTask.created_at)
        .with_for_update()
        .all()
    )


def _queue_task(session: Session, review, *, case_reference, priority, actor: str, actor_role, **extra):
    task_type = rules.TYPE_TASKS[review.review_type]
    return service.create_task(
        session,
        review.tenant_id,
        task_type=task_type,
        title=task_title(review, case_reference),
        source_type=rules.SOURCE_TYPE,
        source_id=review.id,
        investigation_id=review.investigation_id,
        assigned_role=TASK_TYPES[task_type].queue_role,
        priority=_priority(priority),
        due_at=review.due_at,
        created_by=actor,
        actor_role=actor_role,
        details={"review_business_id": review.business_id, "review_type": review.review_type},
        **extra,
    )


def on_review_requested(
    db: Session, review, *, actor_user_id, actor_role=None, case_reference=None, priority=None, correlation_id=None
) -> None:
    def step(session):
        _queue_task(
            session,
            review,
            case_reference=case_reference,
            priority=priority,
            actor=str(actor_user_id),
            actor_role=actor_role,
            correlation_id=correlation_id,
        )

    service.run_hook(db, "case review requested", step)


def on_review_started(
    db: Session, review, *, actor_user_id, actor_role=None, case_reference=None, priority=None, correlation_id=None
) -> None:
    """The reviewer takes the review's queue task (or accepts it when it was given to them) and works on it. A review
    without an open task (its task could not be created) gets one for the reviewer."""

    def step(session):
        actor = str(actor_user_id)
        reviewer = review.reviewer_user_id
        rows = _open_review_tasks(session, review)
        now = service.now_utc()
        if not rows:
            _queue_task(
                session,
                review,
                case_reference=case_reference,
                priority=priority,
                actor=actor,
                actor_role=actor_role,
                assigned_user_id=reviewer,
                status="IN_PROGRESS",
                correlation_id=correlation_id,
            )
            return
        for task in rows:
            if task.assigned_user_id is not None and task.assigned_user_id != reviewer:
                continue
            previous = task.status
            event = "CLAIMED" if task.assigned_user_id is None else "ACCEPTED"
            task.assigned_user_id = reviewer
            task.status = "IN_PROGRESS"
            task.accepted_at = task.accepted_at or now
            task.updated_at = now
            service.record_event(
                session,
                task,
                event,
                actor_ref=actor,
                actor_role=actor_role,
                from_status=previous,
                to_status="IN_PROGRESS",
                details={"review_business_id": review.business_id},
                correlation_id=correlation_id,
                now=now,
            )
            break
        session.flush()

    service.run_hook(db, "case review started", step)


def on_review_completed(
    db: Session,
    control_db,
    review,
    case,
    *,
    actor_user_id,
    actor_role=None,
    correlation_id=None,
) -> None:
    def step(session):
        actor = str(actor_user_id)
        service.complete_tasks(
            session,
            review.tenant_id,
            source_type=rules.SOURCE_TYPE,
            source_id=review.id,
            task_types=[rules.TYPE_TASKS[review.review_type]],
            outcome=review.outcome,
            actor_ref=actor,
            actor_role=actor_role,
            correlation_id=correlation_id,
        )
        if not rules.is_blocking_outcome(review.outcome):
            return
        owner = None
        if control_db is not None and case.owner_ref:
            from backend.app.workflow.people import find_user

            owner = find_user(control_db, case.tenant_id, case.owner_ref)
        label = rules.TYPE_LABELS.get(review.review_type, "Review")
        outcome = rules.outcome_label(review.outcome)
        service.create_task(
            session,
            review.tenant_id,
            task_type="FOLLOW_UP",
            title=f"{label} of {case.business_id} returned: {outcome}",
            source_type=rules.SOURCE_TYPE,
            source_id=review.id,
            investigation_id=review.investigation_id,
            assigned_user_id=owner.id if owner is not None else None,
            priority=_priority(case.priority),
            created_by=actor,
            is_return=True,
            actor_role=actor_role,
            details={
                "review_business_id": review.business_id,
                "review_type": review.review_type,
                "outcome": review.outcome,
                "outcome_label": outcome,
                "description": (
                    f"{review.business_id} concluded "
                    f'"{outcome}": {service.shorten(review.rationale, 500)} '
                    f"A new {label.lower()} must be completed before the investigation is ready for a decision."
                ),
            },
            correlation_id=correlation_id,
        )

    service.run_hook(db, "case review completed", step)


def on_review_recused(db: Session, review, *, actor_user_id, actor_role=None, reason=None, correlation_id=None) -> None:
    """The reviewer steps back: the review's task goes back to its role queue for someone else to take."""

    def step(session):
        actor = str(actor_user_id)
        now = service.now_utc()
        queue = TASK_TYPES[rules.TYPE_TASKS[review.review_type]].queue_role
        for task in _open_review_tasks(session, review):
            previous = task.status
            task.assigned_user_id = None
            task.assigned_role = task.assigned_role or queue
            task.accepted_at = None
            task.status = "NEW"
            task.updated_at = now
            service.record_event(
                session,
                task,
                "RELEASED",
                actor_ref=actor,
                actor_role=actor_role,
                from_status=previous,
                to_status="NEW",
                reason=reason,
                details={"review_business_id": review.business_id, "recused": True},
                correlation_id=correlation_id,
                now=now,
            )
        session.flush()

    service.run_hook(db, "case review recused", step)


def on_review_cancelled(
    db: Session, review, *, actor_user_id, actor_role=None, reason=None, correlation_id=None
) -> None:
    def step(session):
        service.cancel_tasks(
            session,
            review.tenant_id,
            source_type=rules.SOURCE_TYPE,
            source_id=review.id,
            outcome="REVIEW_CANCELLED",
            actor_ref=str(actor_user_id),
            actor_role=actor_role,
            reason=reason,
            correlation_id=correlation_id,
        )

    service.run_hook(db, "case review cancelled", step)
