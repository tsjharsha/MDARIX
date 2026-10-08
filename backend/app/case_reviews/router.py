"""Risk and regulatory reviews of a case.

- ``GET  /api/v1/investigations/{id}/reviews/policy``: whether the policy requires each review, and why;
- ``GET  /api/v1/investigations/{id}/reviews``: the case's reviews (newest first) and the policy;
- ``POST /api/v1/investigations/{id}/reviews`` (``investigation.work``): ask for a review; it lands in the reviewers'
  role queue as a task (one open review per type at a time);
- ``GET  /api/v1/case-reviews/summary``: the reviewer's dashboard (queues, own reviews, due and overdue);
- ``GET  /api/v1/case-reviews`` (``box`` mine | queue | all) and ``GET /api/v1/case-reviews/{id}`` (with what the
  reviewer needs to see: ``context``);
- ``POST /api/v1/case-reviews/{id}/start`` (anyone holding the review type's permission), ``/complete`` and
  ``/recuse`` (its reviewer), ``/cancel`` (its requester or ``investigation.assign``).

Reading needs a signed-in session; every lookup is limited to the signed-in organization (another organization's
review or case is "not found"). Every change locks the review row (a request locks the case row), is audited
(CASE_REVIEW_*) with the role it was done under, and moves workflow tasks through never-blocking hooks. MDARIX never
decides an outcome or reportability: the reviewer does.
"""

from __future__ import annotations

import uuid
from datetime import timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import false, func
from sqlalchemy.orm import Session

from backend.app.access.permissions import INVESTIGATION_ASSIGN, INVESTIGATION_WORK, require_permission
from backend.app.case_reviews import hooks, rules, service
from backend.app.db.data_plane import get_data_plane_db
from backend.app.db.models.foundation import Investigation, Risk
from backend.app.db.models.reviews import CaseReview
from backend.app.db.session import get_db
from backend.app.evidence_workflow.people import Person, current_person
from backend.app.request_context import AuthenticatedRequestContext, get_request_context

router = APIRouter(tags=["Case Reviews"])
BASE = "/api/v1/case-reviews"
BOXES = ("mine", "queue", "all")
SUMMARY_LIMIT = 50
COMPLETED_DAYS = 30


def _tenant(ctx: AuthenticatedRequestContext) -> uuid.UUID:
    return uuid.UUID(str(ctx.tenant_id))


def _case(db: Session, tenant_id, investigation_id, *, lock: bool = False) -> Investigation:
    query = db.query(Investigation).filter(Investigation.id == investigation_id, Investigation.tenant_id == tenant_id)
    if lock:
        query = query.with_for_update()
    found = query.first()
    if found is None:
        raise service.error(404, "INVESTIGATION_NOT_FOUND", "Investigation not found")
    return found


def _review(db: Session, tenant_id, review_id, *, lock: bool = False) -> CaseReview:
    query = db.query(CaseReview).filter(CaseReview.id == review_id, CaseReview.tenant_id == tenant_id)
    if lock:
        query = query.with_for_update()
    found = query.first()
    if found is None:
        raise service.error(404, "CASE_REVIEW_NOT_FOUND", "Review not found")
    return found


def _one(db: Session, control_db: Session, person: Person, row: CaseReview) -> dict:
    return service.serialize_reviews(db, control_db, person, [row])[0]


def _denied(permission: str, message: str = "Your role does not allow this action"):
    return service.error(403, "PERMISSION_DENIED", message, permission=permission)


def _conflict(message: str):
    return service.error(409, "REVIEW_STATE_CONFLICT", message)


def _refuse_closed(case: Investigation) -> None:
    if not service.case_is_open(case):
        raise service.error(409, "INVESTIGATION_CLOSED", "This investigation is closed")


def request_review_and_task(
    db: Session,
    ctx: AuthenticatedRequestContext,
    person: Person,
    case: Investigation,
    *,
    review_type: str,
    reason: str | None,
    due_at=None,
    before_commit=None,
) -> CaseReview:
    """Request a review of the locked case, commit, and queue its task (never-blocking). ``before_commit(row)`` may
    add more to the same transaction (the next-step record). Shared by POST .../reviews and the next steps."""
    role = person.role_for(INVESTIGATION_WORK)
    row = service.create_review(
        db,
        case,
        review_type=review_type,
        actor_ref=person.user_id,
        actor_role=role,
        reason=reason,
        due_at=due_at,
        correlation_id=ctx.correlation_id,
    )
    if before_commit is not None:
        before_commit(row)
    db.commit()
    hooks.on_review_requested(
        db,
        row,
        actor_user_id=person.user_id,
        actor_role=role,
        case_reference=case.business_id,
        priority=case.priority,
        correlation_id=ctx.correlation_id,
    )
    return row


# ------------------------------------------------------------------------------------------------- per case


@router.get("/api/v1/investigations/{investigation_id}/reviews/policy")
def review_policy(
    investigation_id: uuid.UUID,
    db: Session = Depends(get_data_plane_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """Whether the risk and the regulatory review are required for the case now, with the reasons in plain words."""
    case = _case(db, _tenant(ctx), investigation_id)
    return service.policy_for_case(db, case)


@router.get("/api/v1/investigations/{investigation_id}/reviews")
def list_case_reviews(
    investigation_id: uuid.UUID,
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """Every review of the case, newest first (superseded and cancelled ones too), and what the policy requires."""
    tenant_id = _tenant(ctx)
    case = _case(db, tenant_id, investigation_id)
    person = current_person(control_db, ctx)
    rows = (
        db.query(CaseReview)
        .filter(CaseReview.tenant_id == tenant_id, CaseReview.investigation_id == case.id)
        .order_by(CaseReview.created_at.desc(), CaseReview.business_id.desc())
        .all()
    )
    return {
        "items": service.serialize_reviews(db, control_db, person, rows),
        "policy": service.policy_for_case(db, case),
    }


@router.post(
    "/api/v1/investigations/{investigation_id}/reviews",
    status_code=201,
    dependencies=[Depends(require_permission(INVESTIGATION_WORK))],
)
def request_case_review(
    investigation_id: uuid.UUID,
    payload: rules.ReviewRequestPayload,
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """Ask for a risk or regulatory review of the case. It records whether the policy requires it (and why) and the
    current scope version, and lands in the reviewers' role queue as a task. 409 REVIEW_ALREADY_OPEN while a review of
    the same type is requested or in progress."""
    tenant_id = _tenant(ctx)
    person = current_person(control_db, ctx)
    case = _case(db, tenant_id, investigation_id, lock=True)
    row = request_review_and_task(
        db, ctx, person, case, review_type=payload.review_type, reason=payload.reason, due_at=payload.due_at
    )
    return _one(db, control_db, person, _review(db, tenant_id, row.id))


# -------------------------------------------------------------------------------------------- reviewer's views


def _box_query(db: Session, person: Person, box: str):
    query = db.query(CaseReview).filter(CaseReview.tenant_id == person.tenant_id)
    if box == "mine":
        if person.user_uuid is None:
            return query.filter(false())
        return query.filter(CaseReview.reviewer_user_id == person.user_uuid)
    if box == "queue":
        types = [code for code, permission in rules.TYPE_PERMISSIONS.items() if person.holds(permission)]
        if not types:
            return query.filter(false())
        return query.filter(
            CaseReview.reviewer_user_id.is_(None),
            CaseReview.status == "REQUESTED",
            CaseReview.review_type.in_(types),
        )
    return query


def _ordered(query):
    return query.order_by(CaseReview.due_at.asc().nulls_last(), CaseReview.created_at.desc())


@router.get(BASE + "/summary")
def review_summary(
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """The reviewer's dashboard: which reviews they may take (``roles``), the queues of their review types, their own
    open reviews, what is due within a week or overdue (among their own open reviews and their queues), and how many
    they completed in the last 30 days."""
    person = current_person(control_db, ctx)
    now = service.now_utc()
    roles = {
        "risk": person.holds(rules.TYPE_PERMISSIONS[rules.RISK]),
        "regulatory": person.holds(rules.TYPE_PERMISSIONS[rules.REGULATORY]),
    }
    queue = _box_query(db, person, "queue")
    queue_counts = dict(
        queue.with_entities(CaseReview.review_type, func.count(CaseReview.id)).group_by(CaseReview.review_type).all()
    )
    mine_open = _box_query(db, person, "mine").filter(CaseReview.status.in_(rules.OPEN_STATUSES))
    actionable = [*mine_open.all(), *queue.all()]
    due_soon = sum(
        1
        for row in actionable
        if row.due_at is not None and now <= rules.as_utc(row.due_at) <= now + timedelta(days=rules.DUE_SOON_DAYS)
    )
    overdue = sum(1 for row in actionable if rules.is_overdue(row.status, row.due_at, now))
    completed = (
        _box_query(db, person, "mine")
        .filter(CaseReview.status == "COMPLETED", CaseReview.completed_at >= now - timedelta(days=COMPLETED_DAYS))
        .count()
    )
    mine_rows = _ordered(mine_open).limit(SUMMARY_LIMIT).all()
    queue_rows = _ordered(queue).limit(SUMMARY_LIMIT).all()
    return {
        "roles": roles,
        "counts": {
            "risk_queue": int(queue_counts.get(rules.RISK, 0)),
            "regulatory_queue": int(queue_counts.get(rules.REGULATORY, 0)),
            "mine_open": mine_open.count(),
            "due_soon": due_soon,
            "overdue": overdue,
            "completed_30d": completed,
        },
        "mine": service.serialize_reviews(db, control_db, person, mine_rows),
        "queue": service.serialize_reviews(db, control_db, person, queue_rows),
    }


@router.get(BASE)
def list_reviews(
    review_type: str | None = Query(default=None, alias="type", pattern="^(RISK|REGULATORY|risk|regulatory)$"),
    box: str = Query(default="mine", pattern="^(" + "|".join(BOXES) + ")$"),
    status: str | None = Query(default=None, max_length=200),
    page: int = Query(default=1, ge=1, le=100000),
    page_size: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """One page of reviews: ``mine`` (I am the reviewer), ``queue`` (requested, nobody took them yet, of a type whose
    permission I hold) or ``all``; optionally of one type and in some statuses (comma separated). Most urgent first."""
    person = current_person(control_db, ctx)
    query = _box_query(db, person, box)
    if review_type:
        query = query.filter(CaseReview.review_type == review_type.upper())
    if status:
        wanted = [item.strip().upper() for item in status.split(",") if item.strip()]
        unknown = [item for item in wanted if item not in rules.STATUS_LABELS]
        if unknown:
            raise service.error(422, "UNKNOWN_STATUS", f"Choose from: {', '.join(rules.STATUS_LABELS)}")
        if wanted:
            query = query.filter(CaseReview.status.in_(wanted))
    total = query.count()
    rows = _ordered(query).offset((page - 1) * page_size).limit(page_size).all()
    return {
        "items": service.serialize_reviews(db, control_db, person, rows),
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get(BASE + "/{review_id}")
def get_review(
    review_id: uuid.UUID,
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """A review with what its reviewer needs to see (``context``, read only)."""
    person = current_person(control_db, ctx)
    row = _review(db, _tenant(ctx), review_id)
    return {**_one(db, control_db, person, row), "context": service.review_context(db, row)}


# ---------------------------------------------------------------------------------------------------- changing


def _case_of(db: Session, row: CaseReview, *, lock: bool = False) -> Investigation:
    return _case(db, row.tenant_id, row.investigation_id, lock=lock)


@router.post(BASE + "/{review_id}/start")
def start_review(
    review_id: uuid.UUID,
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """Take a requested review: the signed-in person becomes its reviewer (they must hold the review type's
    permission; whoever asked for it may review it too) and its task is theirs, in progress."""
    person = current_person(control_db, ctx)
    row = _review(db, _tenant(ctx), review_id, lock=True)
    permission = rules.TYPE_PERMISSIONS[row.review_type]
    if not person.holds(permission):
        raise _denied(permission, f"Your roles do not allow you to do a {rules.TYPE_LABELS[row.review_type].lower()}")
    if row.status != "REQUESTED":
        raise _conflict("Only a requested review can be started")
    if person.user_uuid is None:
        raise _denied(permission)
    case = _case_of(db, row)
    _refuse_closed(case)
    task = service.review_task(service.open_tasks_by_review(db, row.tenant_id, [row.id]).get(str(row.id), []), row)
    if service.task_taken_by_other(task, person):
        raise service.error(409, "REVIEW_TASK_TAKEN", "Another reviewer has taken this review's task")
    now = service.now_utc()
    role = person.role_for(permission)
    row.status = "IN_PROGRESS"
    row.reviewer_user_id = person.user_uuid
    row.reviewer_role = role
    row.updated_at = now
    service.audit(
        db,
        row,
        "CASE_REVIEW_STARTED",
        actor_ref=person.user_id,
        actor_role=role,
        now=now,
        correlation_id=ctx.correlation_id,
        old_values={"status": "REQUESTED"},
        new_values={"status": "IN_PROGRESS", "reviewer_user_id": person.user_id},
    )
    db.commit()
    hooks.on_review_started(
        db,
        row,
        actor_user_id=person.user_id,
        actor_role=role,
        case_reference=case.business_id,
        priority=case.priority,
        correlation_id=ctx.correlation_id,
    )
    return _one(db, control_db, person, _review(db, row.tenant_id, row.id))


def _check_risks(db: Session, case: Investigation, risk_ids) -> None:
    if not risk_ids:
        return
    found = {
        row[0]
        for row in db.query(Risk.id).filter(
            Risk.tenant_id == case.tenant_id, Risk.product_id == case.product_id, Risk.id.in_(list(risk_ids))
        )
    }
    if len(found) != len(set(risk_ids)):
        raise service.error(422, "RISK_NOT_FOR_PRODUCT", "Every assessed risk must be a risk of this case's product")


@router.post(BASE + "/{review_id}/complete")
def complete_review(
    review_id: uuid.UUID,
    payload: rules.CompletePayload,
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """Conclude a review in progress: its reviewer records the outcome (one that fits the review type), the rationale
    and what was assessed (risks of the case's product, markets, notes). The review cannot change afterwards. An
    outcome that asks for more evidence or escalates gives the case owner a follow-up and keeps the case from being
    ready until a new review of the type is completed."""
    person = current_person(control_db, ctx)
    row = _review(db, _tenant(ctx), review_id, lock=True)
    if row.status != "IN_PROGRESS":
        raise _conflict("Only a review in progress can be completed")
    if row.reviewer_user_id is None or not person.is_user(row.reviewer_user_id):
        raise service.error(403, "REVIEW_NOT_YOURS", "Only the reviewer of this review can complete it")
    permission = rules.TYPE_PERMISSIONS[row.review_type]
    if not person.holds(permission):
        raise _denied(permission)
    problem = rules.outcome_problem(row.review_type, payload.outcome)
    if problem:
        raise service.error(422, "OUTCOME_NOT_FOR_REVIEW_TYPE", problem)
    case = _case_of(db, row)
    _refuse_closed(case)
    _check_risks(db, case, payload.assessed.risk_ids)
    now = service.now_utc()
    role = row.reviewer_role or person.role_for(permission)
    row.status = "COMPLETED"
    row.outcome = payload.outcome
    row.rationale = payload.rationale
    row.assessed = {
        "risk_ids": [str(item) for item in payload.assessed.risk_ids],
        "markets": list(payload.assessed.markets),
        "notes": payload.assessed.notes,
    }
    row.completed_at = now
    row.updated_at = now
    service.audit(
        db,
        row,
        "CASE_REVIEW_COMPLETED",
        actor_ref=person.user_id,
        actor_role=role,
        now=now,
        correlation_id=ctx.correlation_id,
        reason=payload.rationale,
        old_values={"status": "IN_PROGRESS"},
        new_values={"status": "COMPLETED", "outcome": row.outcome},
        details={
            "outcome": row.outcome,
            "assessed_risks": len(payload.assessed.risk_ids),
            "assessed_markets": len(payload.assessed.markets),
            "scope_version": row.scope_version,
        },
    )
    db.commit()
    hooks.on_review_completed(
        db, control_db, row, case, actor_user_id=person.user_id, actor_role=role, correlation_id=ctx.correlation_id
    )
    return _one(db, control_db, person, _review(db, row.tenant_id, row.id))


@router.post(BASE + "/{review_id}/recuse")
def recuse_from_review(
    review_id: uuid.UUID,
    payload: rules.ReasonPayload,
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """The reviewer steps back, with a reason: the review is requested again, with nobody reviewing it, and its task
    goes back to the reviewers' queue."""
    person = current_person(control_db, ctx)
    row = _review(db, _tenant(ctx), review_id, lock=True)
    if row.status != "IN_PROGRESS":
        raise _conflict("Only a review in progress can be handed back")
    if row.reviewer_user_id is None or not person.is_user(row.reviewer_user_id):
        raise service.error(403, "REVIEW_NOT_YOURS", "Only the reviewer of this review can recuse")
    now = service.now_utc()
    role = row.reviewer_role or person.role_for(rules.TYPE_PERMISSIONS[row.review_type])
    before = str(row.reviewer_user_id)
    row.status = "REQUESTED"
    row.reviewer_user_id = None
    row.reviewer_role = None
    row.updated_at = now
    service.audit(
        db,
        row,
        "CASE_REVIEW_RECUSED",
        actor_ref=person.user_id,
        actor_role=role,
        now=now,
        correlation_id=ctx.correlation_id,
        reason=payload.reason,
        old_values={"status": "IN_PROGRESS", "reviewer_user_id": before},
        new_values={"status": "REQUESTED", "reviewer_user_id": None},
    )
    db.commit()
    hooks.on_review_recused(
        db, row, actor_user_id=person.user_id, actor_role=role, reason=payload.reason, correlation_id=ctx.correlation_id
    )
    return _one(db, control_db, person, _review(db, row.tenant_id, row.id))


@router.post(BASE + "/{review_id}/cancel")
def cancel_review(
    review_id: uuid.UUID,
    payload: rules.ReasonPayload,
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """Cancel a review that is still to be done, with a reason: its requester or whoever assigns work. Its open tasks
    are cancelled."""
    person = current_person(control_db, ctx)
    row = _review(db, _tenant(ctx), review_id, lock=True)
    if not (person.is_user(row.requested_by) or person.holds(INVESTIGATION_ASSIGN)):
        raise _denied(INVESTIGATION_ASSIGN, "Only whoever asked for the review, or assigns work, can cancel it")
    if row.status not in rules.OPEN_STATUSES:
        raise _conflict("Only a requested review or a review in progress can be cancelled")
    now = service.now_utc()
    role = person.role_for(INVESTIGATION_ASSIGN if person.holds(INVESTIGATION_ASSIGN) else INVESTIGATION_WORK)
    before = row.status
    row.status = "CANCELLED"
    row.updated_at = now
    service.audit(
        db,
        row,
        "CASE_REVIEW_CANCELLED",
        actor_ref=person.user_id,
        actor_role=role,
        now=now,
        correlation_id=ctx.correlation_id,
        reason=payload.reason,
        old_values={"status": before},
        new_values={"status": "CANCELLED"},
    )
    db.commit()
    hooks.on_review_cancelled(
        db, row, actor_user_id=person.user_id, actor_role=role, reason=payload.reason, correlation_id=ctx.correlation_id
    )
    return _one(db, control_db, person, _review(db, row.tenant_id, row.id))
