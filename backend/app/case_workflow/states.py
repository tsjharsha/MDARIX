"""Case workflow states, priorities and due dates.

``workflow_state`` says where a case is in the workflow; ``status`` keeps meaning open/closed for everything that
reads it: CLOSED and CANCELLED keep it "closed" (with ``closed_at``), every other state "open". Every change of state
goes through ``set_state`` so the two never drift apart.

People move a case by hand between OPEN, IN_PROGRESS, ON_HOLD and CANCELLED (``POST .../transition``); closing and
reopening stay with managing the case (``PATCH /api/v1/investigations/{id}``). BRIEF_IN_REVIEW, READY_FOR_DECISION and
DECIDED are set by the brief and decision steps, never by hand here.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from backend.app.db.models.case_scope import INVESTIGATION_STATES

logger = logging.getLogger("mdarix.case_workflow")

INVESTIGATION_WORK = "investigation.work"
INVESTIGATION_ASSIGN = "investigation.assign"

STATE_LABELS: dict[str, str] = {
    "OPEN": "Open",
    "IN_PROGRESS": "In progress",
    "ON_HOLD": "On hold",
    "BRIEF_IN_REVIEW": "Brief in review",
    "READY_FOR_DECISION": "Ready for decision",
    "DECIDED": "Decided",
    "CLOSED": "Closed",
    "CANCELLED": "Cancelled",
}
CLOSED_STATES = ("CLOSED", "CANCELLED")
# Set by the brief and decision steps, never by hand.
RESERVED_STATES = ("BRIEF_IN_REVIEW", "READY_FOR_DECISION", "DECIDED")
# The moves people make by hand, from each state.
TRANSITIONS: dict[str, tuple[str, ...]] = {
    "OPEN": ("IN_PROGRESS", "ON_HOLD", "CANCELLED"),
    "IN_PROGRESS": ("ON_HOLD", "CANCELLED"),
    "ON_HOLD": ("IN_PROGRESS", "CANCELLED"),
    "CANCELLED": ("IN_PROGRESS",),
}
# Working on a case moves it; cancelling it is for whoever assigns work.
TARGET_PERMISSIONS: dict[str, str] = {
    "IN_PROGRESS": INVESTIGATION_WORK,
    "ON_HOLD": INVESTIGATION_WORK,
    "CANCELLED": INVESTIGATION_ASSIGN,
}

PRIORITIES = ("LOW", "MEDIUM", "HIGH", "CRITICAL")
PRIORITY_RANK: dict[str, int] = {"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}
DEFAULT_PRIORITY = "MEDIUM"
# Days a case has from opening, by priority.
DUE_DAYS: dict[str, int] = {"CRITICAL": 15, "HIGH": 30, "MEDIUM": 60, "LOW": 90}


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def state_label(state: str | None) -> str | None:
    return STATE_LABELS.get(str(state or "").upper()) if state else None


def is_closed_status(status: str | None) -> bool:
    return str(status or "").strip().lower() == "closed"


def effective_state(workflow_state: str | None, status: str | None) -> str:
    """The state a case is in, read defensively: a case whose ``status`` says closed is CLOSED (or CANCELLED) even
    when its workflow state was never set (an imported closed case), and an open case is never CLOSED or CANCELLED."""
    state = str(workflow_state or "").strip().upper()
    if state not in INVESTIGATION_STATES:
        state = "OPEN"
    if is_closed_status(status):
        return state if state in CLOSED_STATES else "CLOSED"
    return "OPEN" if state in CLOSED_STATES else state


def case_state(case) -> str:
    return effective_state(getattr(case, "workflow_state", None), getattr(case, "status", None))


def status_for(state: str) -> str:
    """The open/closed ``status`` that goes with a workflow state."""
    return "closed" if str(state or "").upper() in CLOSED_STATES else "open"


def normalize_priority(priority: str | None) -> str:
    value = str(priority or "").strip().upper()
    return value if value in PRIORITIES else DEFAULT_PRIORITY


def due_at_for(priority: str | None, start: datetime) -> datetime:
    """When a case of this priority is due, counted from ``start`` (when it was opened)."""
    return start + timedelta(days=DUE_DAYS[normalize_priority(priority)])


def required_permission(to_state: str) -> str | None:
    """The permission a manual move to ``to_state`` needs; None when no manual move goes there."""
    return TARGET_PERMISSIONS.get(str(to_state or "").upper())


def transition_refusal(current: str, to_state: str) -> str | None:
    """Why a case in ``current`` cannot be moved to ``to_state`` by hand, in words people read; None when it can."""
    current = str(current or "").upper()
    target = str(to_state or "").upper()
    if target not in INVESTIGATION_STATES:
        return "That is not a state a case can be in"
    if target in RESERVED_STATES:
        return f"A case becomes {STATE_LABELS[target].lower()} through its brief and decision, not by hand"
    if target == "CLOSED":
        return "Close a case from its management, with a reason"
    if target == current:
        return f"The case is already {STATE_LABELS.get(current, current).lower()}"
    if target not in TRANSITIONS.get(current, ()):
        return (
            f"A case that is {STATE_LABELS.get(current, current).lower()} cannot be moved to "
            f"{STATE_LABELS[target].lower()}"
        )
    return None


def overdue(due_at: datetime | None, state: str, now: datetime) -> bool:
    return bool(due_at is not None and state not in CLOSED_STATES and due_at < now)


# ---------------------------------------------------------------------------------------------------- changing


def set_state(case, state: str, now: datetime | None = None) -> None:
    """Put the case in ``state`` and keep ``status`` (and ``closed_at``) in step. Does not audit or commit."""
    now = now or now_utc()
    state = str(state).upper()
    if state not in INVESTIGATION_STATES:
        raise ValueError(f"Unknown investigation state {state!r}")
    status = status_for(state)
    if status == "closed":
        if not is_closed_status(case.status) or case.closed_at is None:
            case.closed_at = now
    else:
        case.closed_at = None
    case.status = status
    case.workflow_state = state
    case.state_changed_at = now
    case.updated_at = now


def audit_state_change(
    db: Session,
    case,
    *,
    actor_ref: str,
    before: dict,
    reason: str | None,
    correlation_id: str | None = None,
    details: dict | None = None,
    now: datetime | None = None,
) -> None:
    """The INVESTIGATION_STATE_CHANGED audit event: ``before`` holds the previous ``workflow_state`` and ``status``;
    only what changed is recorded."""
    from backend.app.enterprise_audit import make_audit_event

    after = {"workflow_state": case.workflow_state, "status": case.status}
    db.add(
        make_audit_event(
            tenant_id=case.tenant_id,
            actor_ref=str(actor_ref),
            action="INVESTIGATION_STATE_CHANGED",
            entity_type="Investigation",
            entity_id=case.id,
            correlation_id=correlation_id,
            reason=reason,
            old_values={key: before.get(key) for key in after if before.get(key) != after[key]},
            new_values={key: after[key] for key in after if before.get(key) != after[key]},
            details=dict(details or {}),
            created_at=now,
        )
    )


def start_case(
    db: Session, case, *, actor_ref: str, reason: str, correlation_id: str | None = None, details: dict | None = None
) -> bool:
    """Move an OPEN case to IN_PROGRESS (someone has started working on it), audited. Any other state is left
    alone. Returns True when the case moved. Does not commit."""
    if case is None or case_state(case) != "OPEN":
        return False
    before = {"workflow_state": case.workflow_state, "status": case.status}
    now = now_utc()
    set_state(case, "IN_PROGRESS", now)
    audit_state_change(
        db,
        case,
        actor_ref=actor_ref,
        before=before,
        reason=reason,
        correlation_id=correlation_id,
        details=details,
        now=now,
    )
    return True


def on_task_taken(db: Session, task, *, actor_ref: str, how: str, correlation_id: str | None = None) -> None:
    """Accepting or claiming a case's INVESTIGATION task starts work on an OPEN case. Runs in a SAVEPOINT of the task
    change and is committed with it; a failure is logged and never blocks taking the task."""
    if str(getattr(task, "task_type", "") or "").upper() != "INVESTIGATION" or task.investigation_id is None:
        return
    from backend.app.db.models.foundation import Investigation

    try:
        with db.begin_nested():
            case = (
                db.query(Investigation)
                .filter(Investigation.tenant_id == task.tenant_id, Investigation.id == task.investigation_id)
                .with_for_update()
                .first()
            )
            start_case(
                db,
                case,
                actor_ref=actor_ref,
                reason=f"Investigation task {task.business_id or task.id} {how}",
                correlation_id=correlation_id,
                details={"task_id": str(task.id)},
            )
    except Exception:
        logger.exception("Starting the case of task %s failed; the task change itself is saved", task.id)


def after_state_change(db: Session, control_db, case, *, actor_user_id, before_state: str, before_status) -> None:
    """What a manual move does to the case's tasks and signals, after it is saved (each step never blocks or undoes
    the move): cancelling cancels every open task of the case (CASE_CANCELLED) and closes its signals as closing does;
    taking a cancelled case up again gives it a task and reopens its signals as reopening does."""
    from backend.app.signals.hooks import on_investigation_status_changed
    from backend.app.workflow import tasks as task_service
    from backend.app.workflow.hooks import on_investigation_managed
    from backend.app.workflow.people import acting_role

    state = case_state(case)
    actor = str(actor_user_id)
    if state == "CANCELLED" and before_state != "CANCELLED":

        def step(session):
            task_service.cancel_tasks(
                session,
                case.tenant_id,
                investigation_id=case.id,
                outcome="CASE_CANCELLED",
                actor_ref=actor,
                actor_role=acting_role(control_db, case.tenant_id, actor, INVESTIGATION_ASSIGN),
            )

        task_service.run_hook(db, "investigation cancelled", step)
    elif before_state == "CANCELLED" and state != "CANCELLED":
        on_investigation_managed(
            db, control_db, case, actor_user_id=actor, before_owner=case.owner_ref, before_status="closed"
        )
    on_investigation_status_changed(db, control_db, case, actor_user_id=actor, before_status=before_status)


# ------------------------------------------------------------------------------------------------------ owners


def owner_names(control_db, tenant_id, refs) -> dict[str, str]:
    """``{sign-in name (lower case): name people read}`` for the case owners among ``refs`` (``owner_ref`` holds a
    sign-in name): the display name, else the sign-in name. One query on the control database; empty when it cannot
    be read, so a list never fails because of a name."""
    wanted = sorted({str(ref).strip().lower() for ref in refs or () if ref and str(ref).strip()})
    if control_db is None or not wanted:
        return {}
    from sqlalchemy import func

    from backend.app.business_ids import as_uuid
    from backend.app.db.models.foundation import AuthUser

    try:
        rows = (
            control_db.query(AuthUser.username, AuthUser.display_name)
            .filter(AuthUser.tenant_id == as_uuid(tenant_id), func.lower(AuthUser.username).in_(wanted))
            .all()
        )
    except Exception:
        logger.warning("The names of case owners could not be read", exc_info=True)
        return {}
    return {str(username).lower(): (str(name or "").strip() or str(username)) for username, name in rows}


def owner_name(names: dict[str, str], owner_ref: str | None) -> str | None:
    key = str(owner_ref or "").strip().lower()
    return names.get(key) if key else None


def with_owner_names(control_db, tenant_id, rows: list[dict]) -> list[dict]:
    """Add ``owner_name`` to each case row that carries ``owner_ref`` (None when nobody owns it or the owner is not
    one of the organization's accounts)."""
    names = owner_names(control_db, tenant_id, (row.get("owner_ref") for row in rows))
    for row in rows:
        row["owner_name"] = owner_name(names, row.get("owner_ref"))
    return rows
