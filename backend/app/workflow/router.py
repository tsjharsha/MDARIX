"""My Work: the signed-in person's tasks and the role queues they may take work from (``/api/v1/tasks``).

Reading needs only a signed-in session; every list and lookup is limited to the signed-in organization (another
organization's task is "not found"). Changing a task is checked here, by the task's own rules: only its assignee
accepts, declines, releases or completes it; claiming from a queue needs the task type's permission; reassigning needs
``investigation.assign``. Every change locks the task row, writes the task's history and an audit event
(``TASK_<EVENT>``), recording the role that granted the permission used (else the account role).
"""

from __future__ import annotations

import uuid
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy import case, false, func, or_
from sqlalchemy.orm import Session

from backend.app.business_ids import as_uuid, wanted_ids
from backend.app.db.data_plane import get_data_plane_db
from backend.app.db.models.workflow import OPEN_TASK_STATUSES, WorkflowTask, WorkflowTaskEvent
from backend.app.db.session import get_db
from backend.app.request_context import AuthenticatedRequestContext, get_request_context
from backend.app.role_codes import role_code
from backend.app.workflow import tasks as service
from backend.app.workflow.labels import (
    INVESTIGATION_ASSIGN_PERMISSION,
    MANUAL_COMPLETION_TYPES,
    SOURCE_LABELS,
    TASK_TYPES,
    known_role,
    role_label,
    task_type_label,
)
from backend.app.workflow.people import find_user, may_hold_tasks, names_by_id, role_granting, roles_of

router = APIRouter(prefix="/api/v1/tasks", tags=["My Work"])

VIEWS = ("assigned", "queue", "waiting", "returned", "due_soon", "overdue", "completed", "created")
SUMMARY_VIEWS = ("assigned", "queue", "waiting", "returned", "due_soon", "overdue")
DUE_SOON_DAYS = 3
COMPLETED_DAYS = 90
# A person is working on these (they can decline, release or complete them).
WORKING_STATUSES = ("ASSIGNED", "ACCEPTED", "IN_PROGRESS")
_PRIORITY_RANK = case({"CRITICAL": 0, "HIGH": 1, "MEDIUM": 2, "LOW": 3}, value=WorkflowTask.priority, else_=4)


def _error(status: int, code: str, message: str) -> HTTPException:
    return HTTPException(status, detail={"code": code, "message": message})


def _not_found() -> HTTPException:
    return _error(404, "TASK_NOT_FOUND", "Task not found")


def _conflict(message: str) -> HTTPException:
    return _error(409, "TASK_STATE_CONFLICT", message)


@dataclass
class Actor:
    """The signed-in person as tasks see them: their permissions (all their roles) and roles."""

    user_id: str
    user_uuid: uuid.UUID | None
    tenant_id: uuid.UUID
    permissions: frozenset[str] = field(default_factory=frozenset)
    roles: list[str] = field(default_factory=list)
    account_role: str | None = None

    def holds(self, permission: str | None) -> bool:
        return bool(permission) and permission in self.permissions

    def role_for(self, permission: str | None) -> str | None:
        """The role that grants ``permission``, else the account role (recorded on the task's history)."""
        try:
            return role_granting(self.roles, permission, self.account_role)
        except Exception:
            return role_code(self.account_role) or None

    def owns(self, task: WorkflowTask) -> bool:
        return self.user_uuid is not None and task.assigned_user_id == self.user_uuid


def _actor(control_db: Session, ctx: AuthenticatedRequestContext) -> Actor:
    from backend.app.access.permissions import effective_permissions

    tenant_id = uuid.UUID(str(ctx.tenant_id))
    user = find_user(control_db, tenant_id, ctx.user_id, active_only=False)
    return Actor(
        user_id=str(ctx.user_id),
        user_uuid=as_uuid(ctx.user_id),
        tenant_id=tenant_id,
        permissions=frozenset(effective_permissions(control_db, ctx) or ()),
        roles=roles_of(control_db, user),
        account_role=user.role if user is not None else ctx.active_role_id,
    )


def _permission(task: WorkflowTask) -> str | None:
    definition = TASK_TYPES.get(str(task.task_type or "").upper())
    return definition.permission if definition else None


def _permitted_types(actor: Actor) -> list[str]:
    return [code for code, definition in TASK_TYPES.items() if actor.holds(definition.permission)]


def _own_decision(actor: Actor, task: WorkflowTask) -> bool:
    """Segregation of duties: nobody approves their own decision, so they cannot take its approval task."""
    author = str((task.details or {}).get("decision_author_ref") or "").strip()
    return task.task_type == "DECISION_APPROVAL" and bool(author) and author == actor.user_id


# ------------------------------------------------------------------------------------------------------- reading


def _view_query(db: Session, actor: Actor, view: str, now: datetime):
    query = db.query(WorkflowTask).filter(WorkflowTask.tenant_id == actor.tenant_id)
    mine = WorkflowTask.assigned_user_id == actor.user_uuid if actor.user_uuid is not None else false()
    is_open = WorkflowTask.status.in_(OPEN_TASK_STATUSES)
    if view == "assigned":
        return query.filter(mine, is_open, WorkflowTask.status != "WAITING")
    if view == "queue":
        types = _permitted_types(actor)
        return query.filter(
            WorkflowTask.assigned_user_id.is_(None),
            WorkflowTask.status.in_(service.QUEUE_STATUSES),
            WorkflowTask.task_type.in_(types) if types else false(),
        )
    if view == "waiting":
        return query.filter(mine, WorkflowTask.status == "WAITING")
    if view == "returned":
        return query.filter(mine, is_open, WorkflowTask.is_return.is_(True))
    if view == "due_soon":
        return query.filter(
            mine, is_open, WorkflowTask.due_at >= now, WorkflowTask.due_at <= now + timedelta(days=DUE_SOON_DAYS)
        )
    if view == "overdue":
        return query.filter(mine, is_open, WorkflowTask.due_at < now)
    if view == "completed":
        return query.filter(
            mine,
            WorkflowTask.status.in_(service.FINISHED_STATUSES),
            func.coalesce(WorkflowTask.completed_at, WorkflowTask.updated_at) >= now - timedelta(days=COMPLETED_DAYS),
        )
    if view == "created":
        return query.filter(WorkflowTask.created_by == actor.user_id)
    raise _error(422, "UNKNOWN_VIEW", f"Choose one of: {', '.join(VIEWS)}")


def _search(query, q: str | None):
    text = " ".join(str(q or "").split())
    if not text:
        return query
    escaped = text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    pattern = f"%{escaped}%"
    return query.filter(
        or_(WorkflowTask.title.ilike(pattern, escape="\\"), WorkflowTask.business_id.ilike(pattern, escape="\\"))
    )


def _ordered(query):
    return query.order_by(_PRIORITY_RANK, WorkflowTask.due_at.asc().nulls_last(), WorkflowTask.created_at.desc())


def _source_models() -> dict:
    from backend.app.db.models.foundation import Decision, Investigation, Risk
    from backend.app.db.models.signals import Signal
    from backend.app.db.models.stage3 import SupplierEvidenceRequest

    return {
        "Investigation": Investigation,
        "Decision": Decision,
        "Risk": Risk,
        "SupplierEvidenceRequest": SupplierEvidenceRequest,
        "Signal": Signal,
        # Requests to a colleague or a role (Phase 3) live in the same table as supplier requests.
        "EvidenceRequest": SupplierEvidenceRequest,
    }


def _business_ids(db: Session, model, tenant_id, ids) -> dict[str, str]:
    wanted = wanted_ids(ids)
    if not wanted:
        return {}
    rows = db.query(model.id, model.business_id).filter(model.tenant_id == tenant_id, model.id.in_(list(wanted)))
    return {str(row_id): business_id for row_id, business_id in rows}


def _iso(value) -> str | None:
    return value.isoformat() if value is not None else None


def _actions(actor: Actor, task: WorkflowTask) -> dict:
    mine = actor.owns(task)
    status = task.status
    return {
        "can_accept": mine and status == "ASSIGNED",
        "can_decline": mine and status in WORKING_STATUSES,
        "can_claim": task.assigned_user_id is None
        and status in service.QUEUE_STATUSES
        and actor.holds(_permission(task))
        and not _own_decision(actor, task),
        "can_release": mine and bool(task.assigned_role) and status in WORKING_STATUSES,
        "can_reassign": status in OPEN_TASK_STATUSES and actor.holds(INVESTIGATION_ASSIGN_PERMISSION),
        "can_complete": mine and task.task_type in MANUAL_COMPLETION_TYPES and status in (*WORKING_STATUSES, "WAITING"),
    }


def serialize_tasks(db: Session, control_db: Session, actor: Actor, rows: list[WorkflowTask]) -> list[dict]:
    """The Task JSON of each row, with business ids, the case and assignee names read in bulk."""
    if not rows:
        return []
    now = service.now_utc()
    models = _source_models()
    by_type: dict[str, set] = defaultdict(set)
    for task in rows:
        by_type[task.source_entity_type].add(task.source_entity_id)
    sources: dict[tuple[str, str], str] = {}
    for source_type, ids in by_type.items():
        model = models.get(source_type)
        if model is None:
            continue
        for key, value in _business_ids(db, model, actor.tenant_id, ids).items():
            sources[(source_type, key)] = value
    investigation_ids = wanted_ids(task.investigation_id for task in rows)
    cases = {}
    if investigation_ids:
        model = models["Investigation"]
        for row_id, business_id, product_id in db.query(model.id, model.business_id, model.product_id).filter(
            model.tenant_id == actor.tenant_id, model.id.in_(list(investigation_ids))
        ):
            cases[str(row_id)] = {
                "id": str(row_id),
                "business_id": business_id,
                "product_id": str(product_id) if product_id else None,
            }
    names = names_by_id(control_db, actor.tenant_id, (task.assigned_user_id for task in rows))
    items = []
    for task in rows:
        business_id = sources.get((task.source_entity_type, str(task.source_entity_id)))
        kind = SOURCE_LABELS.get(task.source_entity_type, task.source_entity_type)
        is_open = task.status in OPEN_TASK_STATUSES
        items.append(
            {
                "id": str(task.id),
                "business_id": task.business_id,
                "task_type": task.task_type,
                "task_type_label": task_type_label(task.task_type),
                "title": task.title,
                "status": task.status,
                "priority": task.priority,
                "due_at": _iso(task.due_at),
                "is_return": bool(task.is_return),
                "overdue": bool(is_open and task.due_at is not None and task.due_at < now),
                "source": {
                    "type": task.source_entity_type,
                    "id": str(task.source_entity_id),
                    "business_id": business_id,
                    "label": f"{kind} {business_id}" if business_id else kind,
                },
                "investigation": cases.get(str(task.investigation_id)) if task.investigation_id else None,
                "assigned_role": task.assigned_role,
                "assigned_role_label": role_label(task.assigned_role),
                "assigned_user": (
                    {"id": str(task.assigned_user_id), "name": names.get(str(task.assigned_user_id))}
                    if task.assigned_user_id
                    else None
                ),
                "created_at": _iso(task.created_at),
                "updated_at": _iso(task.updated_at),
                "accepted_at": _iso(task.accepted_at),
                "completed_at": _iso(task.completed_at),
                "completion_outcome": task.completion_outcome,
                "actions": _actions(actor, task),
            }
        )
    return items


@router.get("")
def list_tasks(
    view: str = Query(default="assigned", pattern="^(" + "|".join(VIEWS) + ")$"),
    page: int = Query(default=1, ge=1, le=100000),
    page_size: int = Query(default=50, ge=1, le=200),
    q: str | None = Query(default=None, max_length=200),
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """One page of a view of My Work, most urgent first (priority, then due date, then newest)."""
    actor = _actor(control_db, ctx)
    query = _search(_view_query(db, actor, view, service.now_utc()), q)
    total = query.count()
    rows = _ordered(query).offset((page - 1) * page_size).limit(page_size).all()
    return {
        "view": view,
        "items": serialize_tasks(db, control_db, actor, rows),
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/summary")
def task_summary(
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """How many tasks each view holds, the person's roles, and the role queues they may take work from."""
    actor = _actor(control_db, ctx)
    now = service.now_utc()
    counts = {view: _view_query(db, actor, view, now).count() for view in SUMMARY_VIEWS}
    queues = []
    types = _permitted_types(actor)
    if types:
        rows = (
            db.query(WorkflowTask.assigned_role, WorkflowTask.task_type, func.count(WorkflowTask.id))
            .filter(
                WorkflowTask.tenant_id == actor.tenant_id,
                WorkflowTask.assigned_user_id.is_(None),
                WorkflowTask.status.in_(service.QUEUE_STATUSES),
                WorkflowTask.task_type.in_(types),
            )
            .group_by(WorkflowTask.assigned_role, WorkflowTask.task_type)
            .order_by(WorkflowTask.assigned_role, WorkflowTask.task_type)
            .all()
        )
        queues = [
            {
                "role": role,
                "role_label": role_label(role),
                "task_type": task_type,
                "task_type_label": task_type_label(task_type),
                "count": int(count),
            }
            for role, task_type, count in rows
        ]
    return {
        "counts": counts,
        "roles": [{"code": code, "label": role_label(code)} for code in actor.roles],
        "queues": queues,
    }


def _task(db: Session, actor: Actor, task_id: uuid.UUID, *, lock: bool = False) -> WorkflowTask:
    query = db.query(WorkflowTask).filter(WorkflowTask.id == task_id, WorkflowTask.tenant_id == actor.tenant_id)
    if lock:
        query = query.with_for_update()
    task = query.first()
    if task is None:
        raise _not_found()
    return task


def _events(db: Session, control_db: Session, actor: Actor, task: WorkflowTask) -> list[dict]:
    rows = (
        db.query(WorkflowTaskEvent)
        .filter(WorkflowTaskEvent.tenant_id == actor.tenant_id, WorkflowTaskEvent.task_id == task.id)
        .order_by(WorkflowTaskEvent.created_at, WorkflowTaskEvent.id)
        .all()
    )
    names = names_by_id(control_db, actor.tenant_id, (row.actor_ref for row in rows))

    def name(ref: str | None) -> str | None:
        if as_uuid(ref) is not None:
            return names.get(str(as_uuid(ref)))
        # Changes made by MDARIX itself (backfill, automatic steps); any other text reference is not shown.
        return "MDARIX" if str(ref or "").startswith(service.SYSTEM_ACTOR) else None

    return [
        {
            "event_type": row.event_type,
            "actor_name": name(row.actor_ref),
            "actor_role": row.actor_role,
            "from_status": row.from_status,
            "to_status": row.to_status,
            "reason": row.reason,
            "created_at": _iso(row.created_at),
        }
        for row in rows
    ]


@router.get("/{task_id}")
def get_task(
    task_id: uuid.UUID,
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    actor = _actor(control_db, ctx)
    task = _task(db, actor, task_id)
    return {**serialize_tasks(db, control_db, actor, [task])[0], "events": _events(db, control_db, actor, task)}


# ------------------------------------------------------------------------------------------------------ changing


class ReasonRequest(BaseModel):
    reason: str = Field(min_length=10, max_length=1000)

    @field_validator("reason")
    @classmethod
    def _reason(cls, value: str) -> str:
        if len(value.strip()) < 10:
            raise ValueError("Say in at least 10 characters why")
        return value.strip()


class ReassignRequest(ReasonRequest):
    assignee_user_id: uuid.UUID | None = None
    assigned_role: str | None = Field(default=None, min_length=2, max_length=60)

    @model_validator(mode="after")
    def _someone(self):
        if self.assignee_user_id is None and not (self.assigned_role or "").strip():
            raise ValueError("Name the person or the role the task goes to")
        return self


class CompleteRequest(BaseModel):
    outcome: str | None = Field(default=None, max_length=60)
    reason: str | None = Field(default=None, max_length=1000)


def _change(
    db: Session,
    control_db: Session,
    actor: Actor,
    task: WorkflowTask,
    event_type: str,
    *,
    to_status: str,
    permission: str | None,
    reason: str | None = None,
    details: dict | None = None,
    correlation_id: str | None = None,
) -> dict:
    """Apply the new status, write the history and audit rows, commit, and return the task as the person sees it."""
    now = service.now_utc()
    previous = task.status
    task.status = to_status
    task.updated_at = now
    service.record_event(
        db,
        task,
        event_type,
        actor_ref=actor.user_id,
        actor_role=actor.role_for(permission),
        from_status=previous,
        to_status=to_status,
        reason=reason,
        details=details,
        correlation_id=correlation_id,
        now=now,
    )
    db.commit()
    return serialize_tasks(db, control_db, actor, [_task(db, actor, task.id)])[0]


def _sync_case_owner(
    db: Session, control_db: Session, actor: Actor, task: WorkflowTask, person, reason: str, *, only_if_actor=False
) -> None:
    """Keep an INVESTIGATION task and its case in step: taking, handing over, releasing or declining the task sets or
    clears the case owner, audited like managing the case. ``person`` is the new owner (None clears it); with
    ``only_if_actor`` the owner is cleared only while it is still the person giving the task up. A closed case is
    left alone. Committed with the task change."""
    if task.task_type != "INVESTIGATION" or task.investigation_id is None:
        return
    from backend.app.db.models.foundation import AuditEvent, Investigation

    case = (
        db.query(Investigation)
        .filter(Investigation.tenant_id == task.tenant_id, Investigation.id == task.investigation_id)
        .with_for_update()
        .first()
    )
    if case is None or str(case.status or "").lower() == "closed":
        return
    if only_if_actor:
        me = find_user(control_db, actor.tenant_id, actor.user_id, active_only=False)
        if me is None or str(case.owner_ref or "").strip().lower() != str(me.username or "").strip().lower():
            return
    owner = person.username if person is not None else None
    if case.owner_ref == owner:
        return
    now = service.now_utc()
    before = case.owner_ref
    case.owner_ref = owner
    case.updated_at = now
    db.add(
        AuditEvent(
            id=uuid.uuid4(),
            tenant_id=task.tenant_id,
            actor_ref=actor.user_id,
            action="INVESTIGATION_UPDATED",
            entity_type="Investigation",
            entity_id=case.id,
            reason=f"{reason} (task {task.business_id})",
            old_values={"owner": before},
            new_values={"owner": owner},
            created_at=now,
        )
    )


def _start_case(db: Session, actor: Actor, task: WorkflowTask, how: str, correlation_id: str | None) -> None:
    """Taking a case's INVESTIGATION task starts work on the case when it is still OPEN (IN_PROGRESS, audited).
    Committed with the task change; a failure never blocks it (backend/app/case_workflow/states.py)."""
    from backend.app.case_workflow.states import on_task_taken

    on_task_taken(db, task, actor_ref=actor.user_id, how=how, correlation_id=correlation_id)


def _require_assignee(actor: Actor, task: WorkflowTask) -> None:
    if not actor.owns(task):
        raise _error(403, "TASK_NOT_YOURS", "Only the person this task is assigned to can do this")


@router.post("/{task_id}/accept")
def accept_task(
    task_id: uuid.UUID,
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    actor = _actor(control_db, ctx)
    task = _task(db, actor, task_id, lock=True)
    _require_assignee(actor, task)
    if task.status != "ASSIGNED":
        raise _conflict("Only a task assigned to you and not yet accepted can be accepted")
    task.accepted_at = service.now_utc()
    _start_case(db, actor, task, "accepted", ctx.correlation_id)
    return _change(
        db,
        control_db,
        actor,
        task,
        "ACCEPTED",
        to_status="ACCEPTED",
        permission=_permission(task),
        correlation_id=ctx.correlation_id,
    )


@router.post("/{task_id}/decline")
def decline_task(
    task_id: uuid.UUID,
    payload: ReasonRequest,
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """Decline a task given to you: a task with a role queue goes back to it; any other task stays DECLINED for
    whoever assigns work to hand it to someone else."""
    actor = _actor(control_db, ctx)
    task = _task(db, actor, task_id, lock=True)
    _require_assignee(actor, task)
    if task.status not in WORKING_STATUSES:
        raise _conflict("This task cannot be declined in its current state")
    to_status = "DECLINED"
    if task.assigned_role:
        task.assigned_user_id = None
        task.accepted_at = None
        to_status = "NEW"
        _sync_case_owner(db, control_db, actor, task, None, payload.reason, only_if_actor=True)
    return _change(
        db,
        control_db,
        actor,
        task,
        "DECLINED",
        to_status=to_status,
        permission=_permission(task),
        reason=payload.reason,
        details={"returned_to_queue": to_status == "NEW"},
        correlation_id=ctx.correlation_id,
    )


@router.post("/{task_id}/claim")
def claim_task(
    task_id: uuid.UUID,
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    actor = _actor(control_db, ctx)
    task = _task(db, actor, task_id, lock=True)
    permission = _permission(task)
    if not actor.holds(permission):
        raise _error(403, "PERMISSION_DENIED", "Your roles do not allow you to take this task")
    if _own_decision(actor, task):
        raise _error(403, "PERMISSION_DENIED", "You cannot approve a decision you recorded")
    if actor.user_uuid is None or task.assigned_user_id is not None or task.status not in service.QUEUE_STATUSES:
        raise _conflict("This task is not waiting in a queue")
    task.assigned_user_id = actor.user_uuid
    task.accepted_at = service.now_utc()
    _sync_case_owner(
        db,
        control_db,
        actor,
        task,
        find_user(control_db, actor.tenant_id, actor.user_id),
        "Taken from the investigation queue",
    )
    _start_case(db, actor, task, "taken from the queue", ctx.correlation_id)
    return _change(
        db,
        control_db,
        actor,
        task,
        "CLAIMED",
        to_status="ACCEPTED",
        permission=permission,
        correlation_id=ctx.correlation_id,
    )


@router.post("/{task_id}/release")
def release_task(
    task_id: uuid.UUID,
    payload: ReasonRequest,
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    actor = _actor(control_db, ctx)
    task = _task(db, actor, task_id, lock=True)
    _require_assignee(actor, task)
    if not task.assigned_role:
        raise _conflict("This task has no role queue to return to")
    if task.status not in WORKING_STATUSES:
        raise _conflict("This task cannot be released in its current state")
    task.assigned_user_id = None
    task.accepted_at = None
    _sync_case_owner(db, control_db, actor, task, None, payload.reason, only_if_actor=True)
    return _change(
        db,
        control_db,
        actor,
        task,
        "RELEASED",
        to_status="NEW",
        permission=_permission(task),
        reason=payload.reason,
        correlation_id=ctx.correlation_id,
    )


@router.post("/{task_id}/reassign")
def reassign_task(
    task_id: uuid.UUID,
    payload: ReassignRequest,
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """Give an open task to a person (ASSIGNED) or to a role queue (NEW). The person must be an active colleague
    whose roles allow the task; the role must allow it too."""
    actor = _actor(control_db, ctx)
    task = _task(db, actor, task_id, lock=True)
    if not actor.holds(INVESTIGATION_ASSIGN_PERMISSION):
        raise _error(403, "PERMISSION_DENIED", "Your roles do not allow you to assign work")
    if task.status not in OPEN_TASK_STATUSES:
        raise _conflict("A finished task cannot be reassigned")
    permission = _permission(task)
    role = None
    if (payload.assigned_role or "").strip():
        from backend.app.access.permissions import permissions_for_roles

        role = role_code(payload.assigned_role)
        if not known_role(role) or permission not in (permissions_for_roles([role]) or ()):
            raise _error(422, "ROLE_NOT_ELIGIBLE", "That role does not take this kind of task")
    person = None
    if payload.assignee_user_id is not None:
        person = find_user(control_db, actor.tenant_id, payload.assignee_user_id)
        if person is None or not may_hold_tasks(control_db, person, permission):
            raise _error(
                422,
                "ASSIGNEE_NOT_ELIGIBLE",
                "Assign the task to an active colleague whose roles allow this kind of task",
            )
    before = {
        "assigned_user_id": str(task.assigned_user_id) if task.assigned_user_id else None,
        "assigned_role": task.assigned_role,
    }
    if role:
        task.assigned_role = role
    if person is not None:
        task.assigned_user_id = person.id
        to_status = "ASSIGNED"
    else:
        task.assigned_user_id = None
        to_status = "NEW"
    task.accepted_at = None
    task.reassignment_reason = payload.reason
    _sync_case_owner(db, control_db, actor, task, person, payload.reason)
    return _change(
        db,
        control_db,
        actor,
        task,
        "REASSIGNED",
        to_status=to_status,
        permission=INVESTIGATION_ASSIGN_PERMISSION,
        reason=payload.reason,
        details={
            "from": before,
            "to": {
                "assigned_user_id": str(task.assigned_user_id) if task.assigned_user_id else None,
                "assigned_role": task.assigned_role,
            },
        },
        correlation_id=ctx.correlation_id,
    )


@router.post("/{task_id}/complete")
def complete_task(
    task_id: uuid.UUID,
    payload: CompleteRequest | None = None,
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """Finish a follow-up, impact assessment or evidence review by hand. Other tasks finish with the action they
    ask for (a signature, a supplier's reply ...)."""
    payload = payload or CompleteRequest()
    actor = _actor(control_db, ctx)
    task = _task(db, actor, task_id, lock=True)
    if task.task_type not in MANUAL_COMPLETION_TYPES:
        raise _error(
            409, "TASK_COMPLETES_AUTOMATICALLY", "This task is completed by the action it asks for, not by hand"
        )
    _require_assignee(actor, task)
    if task.status not in (*WORKING_STATUSES, "WAITING"):
        raise _conflict("This task cannot be completed in its current state")
    now = service.now_utc()
    task.completed_at = now
    task.completion_outcome = service.shorten(payload.outcome, service.OUTCOME_LENGTH) or "COMPLETED"
    reason = " ".join(str(payload.reason or "").split()) or None
    return _change(
        db,
        control_db,
        actor,
        task,
        "COMPLETED",
        to_status="COMPLETED",
        permission=_permission(task),
        reason=reason,
        details={"outcome": task.completion_outcome},
        correlation_id=ctx.correlation_id,
    )
