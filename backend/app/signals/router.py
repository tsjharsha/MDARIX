"""Signals and triage (``/api/v1/triage``): the signal list and summary, one signal with its context, the triage
actions, opening a case from a signal, and the detection rule.

Reading needs a signed-in session; every lookup is limited to the signed-in organization (another organization's
signal is "not found"). Triage actions need ``signal.triage``, opening a case ``investigation.create``. Every change
locks the signal rows, writes the signal's history and an audit event (``SIGNAL_<EVENT>``) recording the role that
granted the permission used, and keeps the signal's SIGNAL_TRIAGE task in step. The existing read-only
``GET /api/v1/signals/{id}`` and ``/api/v1/analytics/signals`` (backend/app/stage3_router.py) are unchanged.
"""

from __future__ import annotations

import uuid
from contextlib import contextmanager
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import case, false, func, or_, select
from sqlalchemy.orm import Session

from backend.app.access.permissions import INVESTIGATION_CREATE, SIGNAL_TRIAGE, require_permission
from backend.app.db.data_plane import get_data_plane_db
from backend.app.db.models.foundation import Product, ProductVersion
from backend.app.db.models.signals import (
    OPEN_SIGNAL_STATUSES,
    SIGNAL_ORIGINS,
    SIGNAL_PRIORITIES,
    SIGNAL_STATUSES,
    InvestigationSignal,
    Signal,
)
from backend.app.db.session import get_db
from backend.app.enterprise_audit import make_audit_event
from backend.app.request_context import AuthenticatedRequestContext, get_request_context
from backend.app.signals import logic, service
from backend.app.signals.labels import (
    AWAITING_TRIAGE,
    CASE_FROM,
    DISPOSITION_FROM,
    PRIORITY_RANK,
    RULES,
    SEVERITY_RANK,
    THRESHOLD_DEFAULTS,
    THRESHOLD_RULE,
)
from backend.app.sorting import order_query
from backend.app.sorting_lookup import lookup_order, person_names

router = APIRouter(prefix="/api/v1/triage", tags=["Signals and triage"])

PRIORITY_PATTERN = "^(" + "|".join(SIGNAL_PRIORITIES) + ")$"
SORT_KEYS = ("priority", "due_at", "created_at", "complaint_count", "last_event_at")
# The inbox's column headings sort by these as well (with ``order``); see _column_sorts.
COLUMN_SORT_KEYS = ("business_id", "title", "product", "problem_key", "highest_severity", "status", "owner", "age_days")
SORT_PATTERN = "^-?(" + "|".join((*SORT_KEYS, *COLUMN_SORT_KEYS)) + ")$"
IDENTIFIER_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9._/-]*$"
EFFECTIVE_PRIORITY = func.coalesce(Signal.confirmed_priority, Signal.suggested_priority)
PRIORITY_ORDER = case(PRIORITY_RANK, value=EFFECTIVE_PRIORITY, else_=0)
OPEN_FIRST = case((Signal.status.in_(OPEN_SIGNAL_STATUSES), 0), else_=1)


def _error(status: int, code: str, message: str) -> HTTPException:
    return HTTPException(status, detail={"code": code, "message": message})


@contextmanager
def _refusals():
    """A rule the signals refuse (logic.SignalRuleError) answers with its status and code."""
    try:
        yield
    except logic.SignalRuleError as exc:
        raise _error(exc.status, exc.code, exc.message) from exc


def _actor(control_db: Session, ctx: AuthenticatedRequestContext):
    """The signed-in person: their permissions (all their roles) and the role that grants each one."""
    from backend.app.workflow.router import _actor as task_actor

    return task_actor(control_db, ctx)


def _actions(actor, signal: Signal) -> dict:
    triage = actor.holds(SIGNAL_TRIAGE)
    status = signal.status
    is_open = status in OPEN_SIGNAL_STATUSES
    return {
        "can_start": triage and status == "NEW",
        "can_set_priority": triage and is_open,
        "can_disposition": triage and (status in DISPOSITION_FROM or status == "ESCALATED"),
        "can_merge": triage and is_open,
        "can_add_complaints": triage and is_open,
        "can_create_investigation": actor.holds(INVESTIGATION_CREATE)
        and status in CASE_FROM
        and signal.product_id is not None,
    }


def _detail(db: Session, control_db: Session, actor, signal_id) -> dict:
    signal = service.load(db, actor.tenant_id, signal_id)
    return service.detail(db, control_db, signal, actions=_actions(actor, signal))


def _codes(value: str | None, allowed, name: str) -> list[str]:
    """A comma-separated filter; every value must be one of ``allowed``."""
    codes = [part.strip().upper() for part in str(value or "").split(",") if part.strip()]
    unknown = [code for code in codes if code not in allowed]
    if unknown:
        raise _error(422, f"UNKNOWN_{name.upper()}", f"Unknown {name}: {', '.join(unknown)}")
    return codes


def _clean(text: str | None) -> str | None:
    value = " ".join(str(text or "").split())
    return value or None


# ------------------------------------------------------------------------------------------------------- reading


def _filtered(query, actor, *, statuses, priorities, origins, product_id, owner, q, overdue=False, review_due=False):
    now = service.now_utc()
    if overdue:
        # As the summary counts it and SignalSummary.overdue flags it: still awaiting triage past its due date.
        query = query.filter(Signal.status.in_(AWAITING_TRIAGE), Signal.due_at < now)
    if review_due:
        query = query.filter(Signal.status == "MONITOR", Signal.monitor_review_date <= now.date())
    if statuses:
        wanted = set(code for code in statuses if code != "OPEN")
        if "OPEN" in statuses:
            wanted |= set(OPEN_SIGNAL_STATUSES)
        query = query.filter(Signal.status.in_(sorted(wanted)))
    if priorities:
        query = query.filter(EFFECTIVE_PRIORITY.in_(priorities))
    if origins:
        query = query.filter(Signal.origin.in_(origins))
    if product_id is not None:
        query = query.filter(Signal.product_id == product_id)
    if owner == "me":
        query = query.filter(Signal.owner_user_id == actor.user_uuid) if actor.user_uuid else query.filter(false())
    elif owner == "unassigned":
        query = query.filter(Signal.owner_user_id.is_(None))
    text = _clean(q)
    if text:
        escaped = text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        pattern = f"%{escaped}%"
        query = query.filter(
            or_(
                Signal.title.ilike(pattern, escape="\\"),
                Signal.business_id.ilike(pattern, escape="\\"),
                Signal.problem_key.ilike(pattern, escape="\\"),
            )
        )
    return query


def _column_sorts(query, control_db: Session, tenant_id) -> dict:
    """What each inbox column sorts on when a heading asks for it (``sort`` with ``order``)."""
    product_name = (
        select(Product.name)
        .where(Product.tenant_id == Signal.tenant_id, Product.id == Signal.product_id)
        .scalar_subquery()
    )
    version_name = (
        select(ProductVersion.version_identifier)
        .where(ProductVersion.tenant_id == Signal.tenant_id, ProductVersion.id == Signal.product_version_id)
        .scalar_subquery()
    )
    owners = [row[0] for row in query.with_entities(Signal.owner_user_id).distinct() if row[0] is not None]
    return {
        "business_id": [Signal.business_id],
        "title": [Signal.title],
        "product": [product_name, version_name],
        "problem_key": [Signal.problem_key],
        "complaint_count": [Signal.complaint_count],
        "highest_severity": [
            case(SEVERITY_RANK, value=func.upper(func.trim(Signal.highest_severity)), else_=None),
            Signal.serious_harm,
        ],
        "priority": [PRIORITY_ORDER],
        "status": [Signal.status],
        "owner": [lookup_order(Signal.owner_user_id, person_names(control_db, tenant_id, owners))],
        "due_at": [Signal.due_at],
        "created_at": [Signal.created_at],
        "last_event_at": [Signal.last_event_at],
    }


def _ordered(query, sort: str | None, order: str | None = None, columns: dict | None = None):
    """Default: open signals first, then the most urgent priority, then the earliest due date. A sort key orders by
    that field in its natural direction (highest priority, earliest due, newest, most complaints, latest complaint);
    a leading ``-`` reverses it. With ``order`` (asc or desc), a column heading's sort: the key's column in that
    direction across every page."""
    key = (sort or "").lstrip("-")
    if sort and columns is not None and (order or key not in SORT_KEYS):
        order = order or ("desc" if sort.startswith("-") else "asc")
        if key == "age_days":
            # Ordering by age is ordering by the creation date the other way round (youngest first ascending).
            key, order = "created_at", ("desc" if order == "asc" else "asc")
        if key in columns:
            return order_query(query, key, order, columns, default=[], tiebreak=[Signal.id])
    if key not in SORT_KEYS:
        sort = None
    if not sort:
        return query.order_by(
            OPEN_FIRST, PRIORITY_ORDER.desc(), Signal.due_at.asc().nulls_last(), Signal.created_at.desc(), Signal.id
        )
    reverse = sort.startswith("-")
    key = sort.lstrip("-")
    natural = {
        "priority": (PRIORITY_ORDER, False),
        "due_at": (Signal.due_at, True),
        "created_at": (Signal.created_at, False),
        "complaint_count": (Signal.complaint_count, False),
        "last_event_at": (Signal.last_event_at, False),
    }
    column, ascending = natural[key]
    ascending = ascending != reverse
    first = column.asc().nulls_last() if ascending else column.desc().nulls_last()
    return query.order_by(first, Signal.created_at.desc(), Signal.id)


@router.get("/signals")
def list_signals(
    status: str | None = Query(default=None, max_length=400),
    priority: str | None = Query(default=None, max_length=100),
    product_id: uuid.UUID | None = None,
    origin: str | None = Query(default=None, max_length=100),
    owner: str | None = Query(default=None, pattern="^(me|unassigned)$"),
    q: str | None = Query(default=None, max_length=200),
    overdue: bool = False,
    review_due: bool = False,
    sort: str | None = Query(default=None, pattern=SORT_PATTERN),
    order: str | None = Query(default=None, pattern="^(asc|desc)$"),
    page: int = Query(default=1, ge=1, le=100000),
    page_size: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """One page of the organization's signals with the count per status (for the other filters). ``status`` may
    name several statuses (comma-separated) or OPEN for every open one, ``priority`` several priorities;
    ``overdue=true`` keeps signals awaiting triage (NEW, TRIAGE) past their due date, ``review_due=true`` monitored
    signals whose review date has come. ``sort`` alone keeps its natural direction (``-`` reverses it); with
    ``order`` (asc or desc) it is a column heading's sort, and the inbox's columns (title, product, owner…) can be
    named as well."""
    actor = _actor(control_db, ctx)
    statuses = _codes(status, (*SIGNAL_STATUSES, "OPEN"), "status")
    filters = {
        "priorities": _codes(priority, SIGNAL_PRIORITIES, "priority"),
        "origins": _codes(origin, SIGNAL_ORIGINS, "origin"),
        "product_id": product_id,
        "owner": owner,
        "q": q,
        "overdue": overdue,
        "review_due": review_due,
    }
    base = db.query(Signal).filter(Signal.tenant_id == actor.tenant_id)
    query = _filtered(base, actor, statuses=statuses, **filters)
    total = query.count()
    columns = (
        _column_sorts(query, control_db, actor.tenant_id)
        if sort and (order or sort.lstrip("-") not in SORT_KEYS)
        else None
    )
    rows = _ordered(query, sort, order, columns).offset((page - 1) * page_size).limit(page_size).all()
    counts = {code: 0 for code in SIGNAL_STATUSES}
    unfiltered = _filtered(
        db.query(Signal.status, func.count(Signal.id)).filter(Signal.tenant_id == actor.tenant_id),
        actor,
        statuses=[],
        **filters,
    )
    for code, count in unfiltered.group_by(Signal.status):
        counts[code] = int(count)
    return {
        "items": service.summaries(db, control_db, actor.tenant_id, rows),
        "total": total,
        "page": page,
        "page_size": page_size,
        "counts_by_status": counts,
    }


@router.get("/summary")
def triage_summary(
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """How many signals wait at each triage step, are unowned or overdue, and the open ones by priority."""
    actor = _actor(control_db, ctx)
    now = service.now_utc()
    base = db.query(func.count(Signal.id)).filter(Signal.tenant_id == actor.tenant_id)

    def count(*conditions) -> int:
        return int(base.filter(*conditions).scalar() or 0)

    is_open = Signal.status.in_(OPEN_SIGNAL_STATUSES)
    counts = {
        "new": count(Signal.status == "NEW"),
        "triage": count(Signal.status == "TRIAGE"),
        "escalated": count(Signal.status == "ESCALATED"),
        "investigation_required": count(Signal.status == "INVESTIGATION_REQUIRED"),
        "monitor": count(Signal.status == "MONITOR"),
        "monitor_review_due": count(Signal.status == "MONITOR", Signal.monitor_review_date <= now.date()),
        "unowned": count(is_open, Signal.owner_user_id.is_(None)),
        "overdue": count(Signal.status.in_(AWAITING_TRIAGE), Signal.due_at < now),
    }
    by_priority = {code: 0 for code in SIGNAL_PRIORITIES}
    for code, number in (
        db.query(EFFECTIVE_PRIORITY, func.count(Signal.id))
        .filter(Signal.tenant_id == actor.tenant_id, is_open)
        .group_by(EFFECTIVE_PRIORITY)
    ):
        if code in by_priority:
            by_priority[code] = int(number)
    return {"counts": counts, "by_priority": by_priority}


@router.get("/signals/{signal_id}")
def get_signal(
    signal_id: uuid.UUID,
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    actor = _actor(control_db, ctx)
    with _refusals():
        return _detail(db, control_db, actor, signal_id)


# ------------------------------------------------------------------------------------------------------ changing


def _reason(value: str | None, minimum: int = 10) -> str | None:
    text = " ".join(str(value or "").split())
    if text and len(text) < minimum:
        raise ValueError(f"Say in at least {minimum} characters why")
    return text or None


class CreateSignalRequest(BaseModel):
    title: str = Field(min_length=5, max_length=300)
    description: str | None = Field(default=None, max_length=5000)
    product_id: uuid.UUID
    product_version_id: uuid.UUID | None = None
    complaint_ids: list[uuid.UUID] = Field(default_factory=list, max_length=200)
    priority: str | None = Field(default=None, pattern=PRIORITY_PATTERN)
    reason: str | None = Field(default=None, max_length=1000)

    @field_validator("title")
    @classmethod
    def _title(cls, value: str) -> str:
        value = " ".join(value.split())
        if len(value) < 5:
            raise ValueError("Give the signal a title of at least 5 characters")
        return value

    @field_validator("reason")
    @classmethod
    def _why(cls, value: str | None) -> str | None:
        return _reason(value)


class PriorityRequest(BaseModel):
    priority: str = Field(pattern=PRIORITY_PATTERN)
    reason: str | None = Field(default=None, max_length=1000)

    @field_validator("reason")
    @classmethod
    def _why(cls, value: str | None) -> str | None:
        return _reason(value)


class DispositionRequest(BaseModel):
    disposition: str = Field(pattern="^(MONITOR|NO_ACTION|DUPLICATE|INVESTIGATION_REQUIRED|ESCALATED)$")
    reason: str = Field(min_length=10, max_length=2000)
    canonical_signal_id: uuid.UUID | None = None
    monitor_review_date: date | None = None
    monitor_trigger: str | None = Field(default=None, max_length=1000)

    @field_validator("reason")
    @classmethod
    def _why(cls, value: str) -> str:
        return _reason(value) or ""


class MergeRequest(BaseModel):
    source_signal_ids: list[uuid.UUID] = Field(min_length=1, max_length=50)
    reason: str = Field(min_length=10, max_length=2000)

    @field_validator("reason")
    @classmethod
    def _why(cls, value: str) -> str:
        return _reason(value) or ""


class AddComplaintsRequest(BaseModel):
    complaint_ids: list[uuid.UUID] = Field(min_length=1, max_length=200)
    reason: str = Field(min_length=10, max_length=1000)

    @field_validator("reason")
    @classmethod
    def _why(cls, value: str) -> str:
        return _reason(value) or ""


class CreateInvestigationRequest(BaseModel):
    investigation_question: str = Field(min_length=10, max_length=2000)
    complaint_ids: list[uuid.UUID] | None = Field(default=None, max_length=500)
    assignee_user_id: uuid.UUID | None = None
    also_signal_ids: list[uuid.UUID] = Field(default_factory=list, max_length=20)
    investigation_identifier: str | None = Field(default=None, min_length=3, max_length=60, pattern=IDENTIFIER_PATTERN)


class RuleRequest(BaseModel):
    enabled: bool
    min_complaints: int = Field(ge=2, le=1000)
    window_days: int = Field(ge=1, le=365)
    reason: str = Field(min_length=10, max_length=1000)

    @field_validator("reason")
    @classmethod
    def _why(cls, value: str) -> str:
        return _reason(value) or ""


def _saved(db: Session, control_db: Session, actor, signal_id) -> dict:
    db.commit()
    return _detail(db, control_db, actor, signal_id)


@router.post("/signals", status_code=201, dependencies=[Depends(require_permission(SIGNAL_TRIAGE))])
def create_signal(
    payload: CreateSignalRequest,
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """A signal raised by a person (origin MANUAL, status NEW) for one product, optionally a version and complaints
    of that product, with a SIGNAL_TRIAGE task in the triage leads' queue. A priority that differs from the one the
    complaints suggest needs a reason."""
    actor = _actor(control_db, ctx)
    tenant = actor.tenant_id
    product = db.query(Product).filter(Product.tenant_id == tenant, Product.id == payload.product_id).first()
    if product is None:
        raise _error(404, "PRODUCT_NOT_FOUND", "Not found in your organization")
    if payload.product_version_id is not None:
        version = (
            db.query(ProductVersion.id)
            .filter(
                ProductVersion.tenant_id == tenant,
                ProductVersion.id == payload.product_version_id,
                ProductVersion.product_id == product.id,
            )
            .first()
        )
        if version is None:
            raise _error(422, "VERSION_NOT_FOR_PRODUCT", "The version must be one of this product's versions")
    with _refusals():
        complaint_ids = service.complaints_of_product(db, tenant, product.id, payload.complaint_ids)
        facts = (
            service.complaint_facts(
                service.complaint_facts_query(db, tenant).filter(service.Complaint.id.in_(complaint_ids))
            )
            if complaint_ids
            else []
        )
        minimum = int(service.rule_settings(db, tenant)["min_complaints"])
        suggested = logic.suggested_priority(logic.summarize(facts), minimum)
        if payload.priority and logic.needs_priority_reason(payload.priority, suggested) and not payload.reason:
            raise logic.SignalRuleError(
                422, "REASON_REQUIRED", f"Say why the priority differs from the suggested {suggested}"
            )
        keys = {row.problem_key for row in facts}
        signal = service.create_signal(
            db,
            tenant,
            title=payload.title,
            description=payload.description,
            origin="MANUAL",
            product_id=product.id,
            product_version_id=payload.product_version_id,
            problem_key=keys.pop() if len(keys) == 1 else None,
            complaint_ids=complaint_ids,
            added_how="MANUAL",
            actor_ref=actor.user_id,
            actor_role=actor.role_for(SIGNAL_TRIAGE),
            confirmed_priority=payload.priority,
            priority_reason=payload.reason if payload.priority else None,
            min_complaints=minimum,
            correlation_id=ctx.correlation_id,
        )
        signal_id = signal.id
        return _saved(db, control_db, actor, signal_id)


@router.post("/signals/{signal_id}/start", dependencies=[Depends(require_permission(SIGNAL_TRIAGE))])
def start_triage(
    signal_id: uuid.UUID,
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """Take a NEW signal into triage: it becomes yours (owner) and so does its triage task (ACCEPTED)."""
    actor = _actor(control_db, ctx)
    with _refusals():
        signal = service.load(db, actor.tenant_id, signal_id, lock=True)
        if signal.status != "NEW":
            raise logic.SignalRuleError(409, "SIGNAL_STATE_CONFLICT", "Only a new signal can be taken into triage")
        if actor.user_uuid is None:
            raise logic.SignalRuleError(409, "SIGNAL_STATE_CONFLICT", "Your account cannot own a signal")
        role = actor.role_for(SIGNAL_TRIAGE)
        signal.owner_user_id = actor.user_uuid
        service.set_status(
            db,
            signal,
            "TRIAGE",
            "TRIAGE_STARTED",
            actor_ref=actor.user_id,
            actor_role=role,
            correlation_id=ctx.correlation_id,
        )
        service.take_triage_task(
            db, signal, user_id=actor.user_uuid, actor_role=role, correlation_id=ctx.correlation_id
        )
        return _saved(db, control_db, actor, signal.id)


@router.post("/signals/{signal_id}/priority", dependencies=[Depends(require_permission(SIGNAL_TRIAGE))])
def set_priority(
    signal_id: uuid.UUID,
    payload: PriorityRequest,
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """Confirm the signal's priority. A priority other than the suggested one needs a reason (10 characters or
    more). While the signal awaits triage its due date follows the new priority."""
    actor = _actor(control_db, ctx)
    with _refusals():
        signal = service.load(db, actor.tenant_id, signal_id, lock=True)
        if signal.status not in OPEN_SIGNAL_STATUSES:
            raise logic.SignalRuleError(409, "SIGNAL_STATE_CONFLICT", "The priority of a finished signal is fixed")
        if logic.needs_priority_reason(payload.priority, signal.suggested_priority) and not payload.reason:
            raise logic.SignalRuleError(
                422,
                "REASON_REQUIRED",
                f"Say why the priority differs from the suggested {signal.suggested_priority or 'one'}",
            )
        previous = logic.effective_priority(signal.confirmed_priority, signal.suggested_priority)
        now = service.now_utc()
        signal.confirmed_priority = payload.priority
        signal.priority_reason = payload.reason
        signal.updated_at = now
        if signal.status in AWAITING_TRIAGE:
            signal.due_at = logic.due_at(payload.priority, signal.created_at or now)
        service.update_open_task_schedule(db, signal)
        service.record(
            db,
            signal,
            "PRIORITY_SET",
            actor_ref=actor.user_id,
            actor_role=actor.role_for(SIGNAL_TRIAGE),
            reason=payload.reason,
            details={"from": previous, "to": payload.priority, "suggested": signal.suggested_priority},
            correlation_id=ctx.correlation_id,
            now=now,
        )
        return _saved(db, control_db, actor, signal.id)


@router.post("/signals/{signal_id}/disposition", dependencies=[Depends(require_permission(SIGNAL_TRIAGE))])
def disposition_signal(
    signal_id: uuid.UUID,
    payload: DispositionRequest,
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """Record the triage decision: MONITOR (with a future review date and a trigger), NO_ACTION, DUPLICATE (of
    another signal, which is kept and linked; nothing is deleted), INVESTIGATION_REQUIRED or ESCALATED (priority
    CRITICAL). The triage task is completed with the decision as its outcome."""
    actor = _actor(control_db, ctx)
    with _refusals():
        signal = service.load(db, actor.tenant_id, signal_id, lock=True)
        canonical = None
        if payload.disposition == "DUPLICATE" and payload.canonical_signal_id is not None:
            if payload.canonical_signal_id != signal.id:
                canonical = (
                    db.query(Signal)
                    .filter(Signal.tenant_id == actor.tenant_id, Signal.id == payload.canonical_signal_id)
                    .with_for_update()
                    .first()
                )
        now = service.now_utc()
        logic.check_disposition(
            payload.disposition,
            signal.status,
            signal_id=signal.id,
            canonical={"id": canonical.id, "status": canonical.status} if canonical is not None else None,
            canonical_signal_id=payload.canonical_signal_id,
            monitor_review_date=payload.monitor_review_date,
            monitor_trigger=payload.monitor_trigger,
            today=now.date(),
        )
        role = actor.role_for(SIGNAL_TRIAGE)
        signal.disposition_reason = payload.reason
        signal.dispositioned_by = actor.user_id
        signal.dispositioned_at = now
        if signal.owner_user_id is None and actor.user_uuid is not None:
            signal.owner_user_id = actor.user_uuid
        details = {"disposition": payload.disposition}
        if payload.disposition == "MONITOR":
            signal.monitor_review_date = payload.monitor_review_date
            signal.monitor_trigger = _clean(payload.monitor_trigger)
            details.update(
                monitor_review_date=service.iso(payload.monitor_review_date), monitor_trigger=signal.monitor_trigger
            )
        if payload.disposition == "DUPLICATE":
            signal.canonical_signal_id = canonical.id
            details["canonical_business_id"] = canonical.business_id
        if payload.disposition == "ESCALATED":
            details["priority_from"] = logic.effective_priority(signal.confirmed_priority, signal.suggested_priority)
            signal.confirmed_priority = "CRITICAL"
            signal.priority_reason = payload.reason
        service.set_status(
            db,
            signal,
            payload.disposition,
            "DISPOSITIONED",
            actor_ref=actor.user_id,
            actor_role=role,
            reason=payload.reason,
            details=details,
            correlation_id=ctx.correlation_id,
            now=now,
        )
        if canonical is not None:
            service.record(
                db,
                canonical,
                "DUPLICATE_LINKED",
                actor_ref=actor.user_id,
                actor_role=role,
                reason=payload.reason,
                details={"duplicate_business_id": signal.business_id},
                correlation_id=ctx.correlation_id,
                now=now,
            )
        service.finish_triage_tasks(db, signal, outcome=payload.disposition, actor_ref=actor.user_id, actor_role=role)
        return _saved(db, control_db, actor, signal.id)


@router.post("/signals/{signal_id}/merge", dependencies=[Depends(require_permission(SIGNAL_TRIAGE))])
def merge_signals(
    signal_id: uuid.UUID,
    payload: MergeRequest,
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """Merge other open signals of the same product into this one (the canonical signal). Each source is kept as
    MERGED and points at this signal; its complaints are linked here (MERGE) and its triage task is superseded. A
    signal a case was opened for cannot be merged."""
    actor = _actor(control_db, ctx)
    sources = list(dict.fromkeys(payload.source_signal_ids))
    with _refusals():
        if signal_id in sources:
            raise logic.SignalRuleError(422, "MERGE_INTO_ITSELF", "A signal cannot be merged into itself")
        rows = {row.id: row for row in service.load_many(db, actor.tenant_id, [signal_id, *sources], lock=True)}
        canonical = rows[signal_id]
        if canonical.status not in OPEN_SIGNAL_STATUSES:
            raise logic.SignalRuleError(409, "SIGNAL_STATE_CONFLICT", "Signals can only be merged into an open signal")
        with_cases = {
            row[0]
            for row in db.query(InvestigationSignal.signal_id).filter(
                InvestigationSignal.tenant_id == actor.tenant_id, InvestigationSignal.signal_id.in_(sources)
            )
        }
        for source_id in sources:
            source = rows[source_id]
            if source.status not in OPEN_SIGNAL_STATUSES:
                raise logic.SignalRuleError(
                    409, "SIGNAL_STATE_CONFLICT", f"{source.business_id} is not open and cannot be merged"
                )
            if source_id in with_cases:
                raise logic.SignalRuleError(
                    409, "SIGNAL_HAS_INVESTIGATION", f"{source.business_id} has an investigation and cannot be merged"
                )
            if source.product_id != canonical.product_id:
                raise logic.SignalRuleError(
                    422, "PRODUCT_MISMATCH", f"{source.business_id} is about another product and cannot be merged"
                )
        role = actor.role_for(SIGNAL_TRIAGE)
        now = service.now_utc()
        added_total = 0
        for source_id in sources:
            source = rows[source_id]
            source.canonical_signal_id = canonical.id
            source.disposition_reason = payload.reason
            source.dispositioned_by = actor.user_id
            source.dispositioned_at = now
            service.set_status(
                db,
                source,
                "MERGED",
                "MERGED_INTO",
                actor_ref=actor.user_id,
                actor_role=role,
                reason=payload.reason,
                details={"canonical_business_id": canonical.business_id},
                correlation_id=ctx.correlation_id,
                now=now,
            )
            added_total += len(
                service.link_complaints(
                    db, canonical, service.linked_complaint_ids(db, source), how="MERGE", actor_ref=actor.user_id
                )
            )
            service.finish_triage_tasks(
                db, source, outcome="MERGED", actor_ref=actor.user_id, actor_role=role, supersede=True
            )
        service.recompute(db, canonical, now=now)
        service.update_open_task_schedule(db, canonical)
        service.record(
            db,
            canonical,
            "MERGED_FROM",
            actor_ref=actor.user_id,
            actor_role=role,
            reason=payload.reason,
            details={
                "source_business_ids": [rows[source_id].business_id for source_id in sources],
                "complaints_added": added_total,
            },
            correlation_id=ctx.correlation_id,
            now=now,
        )
        return _saved(db, control_db, actor, canonical.id)


@router.post("/signals/{signal_id}/complaints", dependencies=[Depends(require_permission(SIGNAL_TRIAGE))])
def add_complaints(
    signal_id: uuid.UUID,
    payload: AddComplaintsRequest,
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """Add complaints of the signal's product (MANUAL); the count, time range, severity and suggested priority are
    recomputed."""
    actor = _actor(control_db, ctx)
    with _refusals():
        signal = service.load(db, actor.tenant_id, signal_id, lock=True)
        if signal.status not in OPEN_SIGNAL_STATUSES:
            raise logic.SignalRuleError(409, "SIGNAL_STATE_CONFLICT", "Complaints can only be added to an open signal")
        wanted = service.complaints_of_product(db, actor.tenant_id, signal.product_id, payload.complaint_ids)
        added = service.link_complaints(db, signal, wanted, how="MANUAL", actor_ref=actor.user_id)
        if not added:
            raise logic.SignalRuleError(422, "NOTHING_TO_ADD", "These complaints are already part of the signal")
        now = service.now_utc()
        service.recompute(db, signal, now=now)
        service.update_open_task_schedule(db, signal)
        business_ids = [
            row[0]
            for row in db.query(service.Complaint.business_id).filter(
                service.Complaint.tenant_id == actor.tenant_id, service.Complaint.id.in_(added)
            )
        ]
        service.record(
            db,
            signal,
            "COMPLAINTS_ADDED",
            actor_ref=actor.user_id,
            actor_role=actor.role_for(SIGNAL_TRIAGE),
            reason=payload.reason,
            details={"how": "MANUAL", "complaints": len(added), "complaint_business_ids": sorted(business_ids)[:50]},
            correlation_id=ctx.correlation_id,
            now=now,
        )
        return _saved(db, control_db, actor, signal.id)


def _assignee(control_db: Session, tenant_id, user_id):
    """An active colleague whose role may work on cases (as for assigning a case), else ASSIGNEE_NOT_ELIGIBLE."""
    from backend.app.access.authz import _is_platform_role
    from backend.app.investigation_open_router import _can_work_cases
    from backend.app.workflow.people import find_user

    person = find_user(control_db, tenant_id, user_id)
    if person is None or _is_platform_role(person.role) or not _can_work_cases(control_db, person):
        raise _error(
            422, "ASSIGNEE_NOT_ELIGIBLE", "Assign the case to an active colleague whose role may work on cases"
        )
    return person


@router.post(
    "/signals/{signal_id}/create-investigation",
    status_code=201,
    dependencies=[Depends(require_permission(INVESTIGATION_CREATE))],
)
def create_investigation(
    signal_id: uuid.UUID,
    payload: CreateInvestigationRequest,
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """Open a case from a signal that needs one (INVESTIGATION_REQUIRED, ESCALATED, or INVESTIGATION_OPEN for a
    second case), with the signal's complaints unless others are named, for a colleague or the investigators' queue.
    Other open signals of the same product (``also_signal_ids``) are linked to the case too. The case is opened exactly
    as ``POST /api/v1/investigations`` opens one (backend/app/investigation_open_router.open_case)."""
    from backend.app.investigation_open_router import open_case

    actor = _actor(control_db, ctx)
    also = [item for item in dict.fromkeys(payload.also_signal_ids)]
    with _refusals():
        if signal_id in also:
            raise logic.SignalRuleError(422, "SIGNAL_LISTED_TWICE", "List other signals only in also_signal_ids")
        rows = {row.id: row for row in service.load_many(db, actor.tenant_id, [signal_id, *also], lock=True)}
        signal = rows[signal_id]
        if not logic.can_open_case(signal.status):
            raise logic.SignalRuleError(
                409, "SIGNAL_STATE_CONFLICT", "Triage the signal as needing an investigation before opening one"
            )
        if signal.product_id is None:
            raise logic.SignalRuleError(422, "SIGNAL_HAS_NO_PRODUCT", "The signal names no product to investigate")
        for other_id in also:
            other = rows[other_id]
            if other.product_id != signal.product_id:
                raise logic.SignalRuleError(422, "PRODUCT_MISMATCH", f"{other.business_id} is about another product")
            if other.status not in OPEN_SIGNAL_STATUSES:
                raise logic.SignalRuleError(409, "SIGNAL_STATE_CONFLICT", f"{other.business_id} is not open")
    person = _assignee(control_db, actor.tenant_id, payload.assignee_user_id) if payload.assignee_user_id else None
    complaint_ids = payload.complaint_ids
    if complaint_ids is None:
        complaint_ids = service.linked_complaint_ids(db, signal)
    investigation, product, linked = open_case(
        db,
        actor.tenant_id,
        actor_ref=actor.user_id,
        product_id=signal.product_id,
        investigation_question=payload.investigation_question,
        complaint_ids=complaint_ids,
        investigation_identifier=payload.investigation_identifier,
        owner_ref=person.username if person is not None else None,
        # The case takes the signal's priority; it starts in progress only when the person opening it takes it.
        priority=logic.effective_priority(signal.confirmed_priority, signal.suggested_priority),
        assigned_to_opener=person is not None and str(person.id) == str(ctx.user_id),
        actor_role=actor.role_for(INVESTIGATION_CREATE),
    )
    role = actor.role_for(INVESTIGATION_CREATE)
    now = service.now_utc()
    for row in [signal, *(rows[other_id] for other_id in also)]:
        db.add(
            InvestigationSignal(
                id=uuid.uuid4(),
                tenant_id=actor.tenant_id,
                investigation_id=investigation.id,
                signal_id=row.id,
                created_by=actor.user_id,
                created_at=now,
            )
        )
        details = {"investigation_business_id": investigation.business_id, "primary": row.id == signal.id}
        if row.status == "INVESTIGATION_OPEN":
            service.record(
                db,
                row,
                "INVESTIGATION_CREATED",
                actor_ref=actor.user_id,
                actor_role=role,
                details=details,
                correlation_id=ctx.correlation_id,
                now=now,
            )
        else:
            service.set_status(
                db,
                row,
                "INVESTIGATION_OPEN",
                "INVESTIGATION_CREATED",
                actor_ref=actor.user_id,
                actor_role=role,
                details=details,
                correlation_id=ctx.correlation_id,
                now=now,
            )
        service.finish_triage_tasks(db, row, outcome="INVESTIGATION_OPENED", actor_ref=actor.user_id, actor_role=role)
    db.commit()
    case_result = {
        "id": str(investigation.id),
        "business_id": investigation.business_id,
        "investigation_identifier": investigation.investigation_identifier,
        "product_id": str(product.id),
        "product_business_id": product.business_id,
        "status": investigation.status,
        "owner": {"id": str(person.id), "name": person.display_name} if person is not None else None,
        "complaints_linked": len(linked),
        "signal_business_ids": [signal.business_id, *(rows[other_id].business_id for other_id in also)],
    }
    # The case's first task (the assignee's, else the investigators' queue) and the assignee's notification, as when a
    # case is opened or assigned elsewhere. Saved after the case; a failure is logged and never undoes it.
    from backend.app.workflow.hooks import on_investigation_opened

    on_investigation_opened(
        db, control_db, investigation, actor_user_id=ctx.user_id, owner_user_id=person.id if person else None
    )
    if person is not None:
        from backend.app.governance_router import _notify

        if _notify(
            "notify_assignment",
            control_db,
            tenant_id=actor.tenant_id,
            investigation_id=investigation.id,
            assignee_ref=person.username,
            assigned_by_user_id=str(ctx.user_id),
            reference=case_result["business_id"],
            investigation_business_id=case_result["business_id"],
        ):
            control_db.commit()
    return {"investigation": case_result, "signal": service.summaries(db, control_db, actor.tenant_id, [signal])[0]}


# ---------------------------------------------------------------------------------------------------------- rules


def _rule_item(db: Session, control_db: Session, tenant_id) -> dict:
    settings = service.rule_settings(db, tenant_id)
    row = settings["row"]
    name = None
    if row is not None and row.updated_by:
        name = service.actor_name(service.people_names(control_db, tenant_id, [row.updated_by]), row.updated_by)
    return {
        "rule_code": THRESHOLD_RULE,
        "label": RULES[THRESHOLD_RULE]["label"],
        "description": RULES[THRESHOLD_RULE]["description"],
        "enabled": settings["enabled"],
        "min_complaints": settings["min_complaints"],
        "window_days": settings["window_days"],
        "version": settings["version"],
        "updated_by_name": name,
        "updated_at": service.iso(row.updated_at) if row is not None else None,
        "last_run_at": service.iso(row.last_run_at) if row is not None else None,
        "defaults": dict(THRESHOLD_DEFAULTS),
    }


@router.get("/rules")
def list_rules(
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """The organization's detection rules (the complaint threshold rule) with their current settings."""
    return [_rule_item(db, control_db, uuid.UUID(str(ctx.tenant_id)))]


@router.post("/rules/run", dependencies=[Depends(require_permission(SIGNAL_TRIAGE))])
def run_rules(
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """Run detection for the organization now: the signals it created, updated, and took out of monitoring."""
    from backend.app.signals.detection import detect

    actor = _actor(control_db, ctx)
    role = actor.role_for(SIGNAL_TRIAGE)
    result = detect(
        db, actor.tenant_id, apply=True, actor_ref=actor.user_id, actor_role=role, correlation_id=ctx.correlation_id
    )
    row = service.rule_row(db, actor.tenant_id)
    db.add(
        make_audit_event(
            tenant_id=actor.tenant_id,
            actor_ref=actor.user_id,
            action="SIGNAL_RULE_RUN",
            entity_type="SignalRule",
            entity_id=row.id,
            correlation_id=ctx.correlation_id,
            details={
                "rule_code": THRESHOLD_RULE,
                "rule_version": result["rule_version"],
                "actor_role": role,
                "created": result["created"],
                "updated": result["updated"],
                "monitor_reopened": result["monitor_reopened"],
            },
        )
    )
    db.commit()
    return {key: result[key] for key in ("created", "updated", "monitor_reopened", "enabled")}


@router.put("/rules/{rule_code}", dependencies=[Depends(require_permission(SIGNAL_TRIAGE))])
def update_rule(
    rule_code: str,
    payload: RuleRequest,
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """Change the rule's settings (a new version; signals already raised keep the version that raised them)."""
    if rule_code.upper() != THRESHOLD_RULE:
        raise _error(404, "RULE_NOT_FOUND", "Unknown detection rule")
    actor = _actor(control_db, ctx)
    row = service.rule_row(db, actor.tenant_id, lock=True)
    before = {"enabled": row.enabled, "min_complaints": row.min_complaints, "window_days": row.window_days}
    after = {"enabled": payload.enabled, "min_complaints": payload.min_complaints, "window_days": payload.window_days}
    if before == after:
        raise _error(422, "NOTHING_TO_CHANGE", "These are already the rule's settings")
    now = service.now_utc()
    previous_version = int(row.version or 1)
    row.enabled, row.min_complaints, row.window_days = payload.enabled, payload.min_complaints, payload.window_days
    row.version = previous_version + 1
    row.updated_by = actor.user_id
    row.updated_at = now
    db.add(
        make_audit_event(
            tenant_id=actor.tenant_id,
            actor_ref=actor.user_id,
            action="SIGNAL_RULE_UPDATED",
            entity_type="SignalRule",
            entity_id=row.id,
            correlation_id=ctx.correlation_id,
            reason=payload.reason,
            details={
                "rule_code": THRESHOLD_RULE,
                "version": row.version,
                "previous_version": previous_version,
                "actor_role": actor.role_for(SIGNAL_TRIAGE),
            },
            old_values={key: value for key, value in before.items() if before[key] != after[key]},
            new_values={key: value for key, value in after.items() if before[key] != after[key]},
            created_at=now,
        )
    )
    db.commit()
    return _rule_item(db, control_db, actor.tenant_id)
