"""Case workflow API: moving a case between workflow states, its versioned scope, its readiness for a decision, and
the investigator's own open cases.

- ``POST /api/v1/investigations/{id}/transition``: start, hold, cancel or take up again a case, with a reason;
- ``GET|PUT /api/v1/investigations/{id}/scope`` and ``GET .../scope/versions/{n}``: the scope and its history;
- ``GET /api/v1/investigations/{id}/readiness``: the case's steps and the checks a decision depends on;
- ``GET /api/v1/investigations/mine/summary``: the signed-in investigator's open cases and what waits on them.

Reading needs only a signed-in session; every lookup is limited to the signed-in organization (another
organization's case is "not found"). Changing a scope needs ``investigation.work``; a manual move needs
``investigation.work`` (start, hold) or ``investigation.assign`` (cancel). Every change is audited with its reason.
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Path
from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy import case as sql_case
from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.app.access.permissions import INVESTIGATION_WORK, effective_permissions, require_permission
from backend.app.case_workflow import readiness, scope, states
from backend.app.db.data_plane import get_data_plane_db
from backend.app.db.models.case_scope import INVESTIGATION_STATES, OPEN_INVESTIGATION_STATES
from backend.app.db.models.foundation import AuthUser, Decision, Investigation, Product
from backend.app.db.session import get_db
from backend.app.enterprise_audit import make_audit_event
from backend.app.request_context import AuthenticatedRequestContext, get_request_context

router = APIRouter(prefix="/api/v1/investigations", tags=["Investigations"])

STATE_PATTERN = "^(" + "|".join(INVESTIGATION_STATES) + ")$"
DUE_SOON_DAYS = 7
MINE_LIMIT = 200
# A decision still waiting for its human review keeps the case from being cancelled, as it keeps it from closing.
DECISIONS_AWAITING_REVIEW = ("REQUIRES_REVIEW",)
_PRIORITY_ORDER = sql_case(states.PRIORITY_RANK, value=Investigation.priority, else_=len(states.PRIORITY_RANK))


def _error(status: int, code: str, message: str) -> HTTPException:
    return HTTPException(status, detail={"code": code, "message": message})


def _not_found() -> HTTPException:
    return _error(404, "INVESTIGATION_NOT_FOUND", "Investigation not found")


def _case(db: Session, tenant_id: uuid.UUID, investigation_id: uuid.UUID, *, lock: bool = False) -> Investigation:
    query = db.query(Investigation).filter(Investigation.id == investigation_id, Investigation.tenant_id == tenant_id)
    if lock:
        query = query.with_for_update()
    found = query.first()
    if found is None:
        raise _not_found()
    return found


def _iso(value) -> str | None:
    return value.isoformat() if value is not None else None


def case_view(case: Investigation) -> dict:
    """Where a case stands: its workflow state (with its label), open/closed status, priority and due date."""
    state = states.case_state(case)
    return {
        "id": str(case.id),
        "business_id": case.business_id,
        "workflow_state": state,
        "workflow_state_label": states.state_label(state),
        "status": case.status,
        "closed_at": _iso(case.closed_at),
        "priority": case.priority,
        "due_at": _iso(case.due_at),
        "state_changed_at": _iso(case.state_changed_at),
    }


def _reason(value: str) -> str:
    text = " ".join(str(value or "").split())
    if len(text) < 10:
        raise ValueError("Say in at least 10 characters why")
    return text


# ------------------------------------------------------------------------------------------- the investigator's


@router.get("/mine/summary")
def my_cases_summary(
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """The signed-in person's open cases (they own them), most urgent first (priority, then due date), with what waits
    on each, and the counts of the investigator's dashboard."""
    from backend.app.db.models.stage3 import SupplierEvidenceRequest as Request

    tenant_id = uuid.UUID(str(ctx.tenant_id))
    now = states.now_utc()
    counts = {
        "open": 0,
        "in_progress": 0,
        "on_hold": 0,
        "due_soon": 0,
        "overdue": 0,
        "unreviewed_evidence": 0,
        "requests_waiting": 0,
        "requests_to_review": 0,
    }
    user = None
    try:
        user = (
            control_db.query(AuthUser.username)
            .filter(AuthUser.id == uuid.UUID(str(ctx.user_id)), AuthUser.tenant_id == tenant_id)
            .first()
        )
    except (TypeError, ValueError):
        user = None
    username = str(user[0] or "").strip() if user else ""
    rows: list[Investigation] = []
    if username:
        rows = (
            db.query(Investigation)
            .filter(
                Investigation.tenant_id == tenant_id,
                func.lower(Investigation.owner_ref) == username.lower(),
                func.lower(func.coalesce(Investigation.status, "")) != "closed",
                Investigation.workflow_state.in_(OPEN_INVESTIGATION_STATES),
            )
            .order_by(_PRIORITY_ORDER, Investigation.due_at.asc().nulls_last(), Investigation.opened_at.desc())
            .limit(MINE_LIMIT)
            .all()
        )
    ids = [row.id for row in rows]
    products = {}
    if rows:
        products = {
            str(product.id): product
            for product in db.query(Product).filter(
                Product.tenant_id == tenant_id, Product.id.in_(list({row.product_id for row in rows}))
            )
        }
    evidence = readiness.safely(db, "evidence", lambda session: readiness.evidence_by_case(session, tenant_id, ids))
    requests = readiness.safely(db, "requests", lambda session: readiness.requests_by_case(session, tenant_id, ids))
    unknowns = readiness.safely(db, "unknowns", lambda session: readiness.unknowns_by_case(session, tenant_id, ids))
    names = states.owner_names(control_db, tenant_id, (row.owner_ref for row in rows))
    items = []
    for row in rows:
        key = str(row.id)
        state = states.case_state(row)
        product = products.get(str(row.product_id))
        unreviewed = (evidence or {}).get(key, (0, 0))[1]
        late = states.overdue(row.due_at, state, now)
        items.append(
            {
                "id": key,
                "business_id": row.business_id,
                "question": row.investigation_question,
                "workflow_state": state,
                "workflow_state_label": states.state_label(state),
                "priority": row.priority,
                "due_at": _iso(row.due_at),
                "overdue": late,
                "owner_name": states.owner_name(names, row.owner_ref),
                "product": (
                    {"id": str(product.id), "business_id": product.business_id, "name": product.name}
                    if product is not None
                    else None
                ),
                "unreviewed_evidence": unreviewed,
                "open_requests": (requests or {}).get(key, (0, 0))[0],
                "open_unknowns": (unknowns or {}).get(key, (0, 0))[1],
            }
        )
        if state in ("OPEN", "IN_PROGRESS", "ON_HOLD"):
            counts[state.lower()] += 1
        if late:
            counts["overdue"] += 1
        elif row.due_at is not None and row.due_at <= now + timedelta(days=DUE_SOON_DAYS):
            counts["due_soon"] += 1
        counts["unreviewed_evidence"] += unreviewed

    def mine(session):
        return (
            session.query(Request.status, Request.responded_at, Request.reviewed_at)
            .filter(Request.tenant_id == tenant_id, Request.requested_by == str(ctx.user_id))
            .all()
        )

    for status, responded_at, reviewed_at in readiness.safely(db, "my requests", mine, default=[]) or []:
        if not readiness.request_is_open(status, reviewed_at):
            continue
        if readiness.request_is_answered(status, responded_at):
            counts["requests_to_review"] += 1
        else:
            counts["requests_waiting"] += 1
    return {"cases": items, "counts": counts}


# ---------------------------------------------------------------------------------------------------- states


class TransitionRequest(BaseModel):
    to_state: str = Field(pattern=STATE_PATTERN)
    reason: str = Field(min_length=10, max_length=1000)

    @field_validator("reason")
    @classmethod
    def _reason(cls, value: str) -> str:
        return _reason(value)


@router.post("/{investigation_id}/transition")
def transition_investigation(
    investigation_id: uuid.UUID,
    payload: TransitionRequest,
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """Start (IN_PROGRESS), hold (ON_HOLD) or cancel (CANCELLED) a case, or take a cancelled case up again, with a
    reason. Closing and reopening stay with managing the case; the review and decision states are set by those steps.

    Cancelling closes the case for everything that reads its status, cancels its open tasks and closes the signals it
    was opened for (as closing does); taking it up again gives it a task and reopens those signals (as reopening
    does)."""
    tenant_id = uuid.UUID(str(ctx.tenant_id))
    target = payload.to_state
    permission = states.required_permission(target)
    if permission is not None and permission not in effective_permissions(control_db, ctx):
        raise HTTPException(
            403,
            detail={
                "code": "PERMISSION_DENIED",
                "message": "Your role does not allow this action",
                "permission": permission,
            },
        )
    case = _case(db, tenant_id, investigation_id, lock=True)
    current = states.case_state(case)
    refusal = states.transition_refusal(current, target)
    if refusal:
        raise _error(409, "INVALID_TRANSITION", refusal)
    if target == "CANCELLED":
        waiting = (
            db.query(Decision.id)
            .filter(
                Decision.tenant_id == tenant_id,
                Decision.investigation_id == case.id,
                Decision.decision_status.in_(DECISIONS_AWAITING_REVIEW),
            )
            .first()
        )
        if waiting is not None:
            raise _error(
                409,
                "DECISIONS_AWAITING_REVIEW",
                "A decision on this case still awaits its human review; finish it before cancelling the case",
            )
    before = {"workflow_state": current, "status": case.status}
    now = states.now_utc()
    states.set_state(case, target, now)
    states.audit_state_change(
        db,
        case,
        actor_ref=str(ctx.user_id),
        before=before,
        reason=payload.reason,
        correlation_id=ctx.correlation_id,
        now=now,
    )
    db.commit()
    result = case_view(case)
    # Tasks and signals follow the case. Saved after the move; a failure is logged and never undoes it.
    states.after_state_change(
        db, control_db, case, actor_user_id=ctx.user_id, before_state=current, before_status=before["status"]
    )
    return result


# ----------------------------------------------------------------------------------------------------- scope


class ExcludedComplaintRequest(BaseModel):
    complaint_id: uuid.UUID
    reason: str = Field(min_length=5, max_length=500)

    @field_validator("reason")
    @classmethod
    def _reason(cls, value: str) -> str:
        text = " ".join(str(value or "").split())
        if len(text) < 5:
            raise ValueError("Say in at least 5 characters why the complaint is excluded")
        return text


class ScopeRequest(BaseModel):
    question: str = Field(min_length=10, max_length=2000)
    product_version_ids: list[uuid.UUID] = Field(default_factory=list, max_length=200)
    included_complaint_ids: list[uuid.UUID] = Field(default_factory=list, max_length=1000)
    excluded_complaints: list[ExcludedComplaintRequest] = Field(default_factory=list, max_length=1000)
    lot_ids: list[uuid.UUID] = Field(default_factory=list, max_length=500)
    markets: list[str] = Field(default_factory=list, max_length=100)
    failure_mode_ids: list[uuid.UUID] = Field(default_factory=list, max_length=200)
    date_from: date | None = None
    date_to: date | None = None
    objectives: str | None = Field(default=None, max_length=4000)
    change_reason: str | None = Field(default=None, min_length=10, max_length=2000)
    reviews_must_restart: bool = False
    conclusions_invalidated: bool = False

    @field_validator("question")
    @classmethod
    def _question(cls, value: str) -> str:
        text = str(value or "").strip()
        if len(" ".join(text.split())) < 10:
            raise ValueError("Write the question in at least 10 characters")
        return text

    @field_validator("markets")
    @classmethod
    def _markets(cls, value: list[str]) -> list[str]:
        if any(len(str(item or "").strip()) > 120 for item in value):
            raise ValueError("A market is named in at most 120 characters")
        return scope.text_list(value)

    @field_validator("change_reason")
    @classmethod
    def _change_reason(cls, value: str | None) -> str | None:
        return None if value is None else _reason(value)

    @model_validator(mode="after")
    def _dates(self):
        if self.date_from is not None and self.date_to is not None and self.date_from > self.date_to:
            raise ValueError("The scope must start before it ends")
        return self


def _scope_payload(db: Session, control_db: Session, case: Investigation, rows) -> dict:
    current = scope.as_data(rows[0]) if rows else scope.derived_scope(db, case)
    refs = scope.references(db, case.tenant_id, [current])
    names = scope.names_for(control_db, case.tenant_id, (row.created_by for row in rows))
    return {
        "investigation": {
            "id": str(case.id),
            "business_id": case.business_id,
            "workflow_state": states.case_state(case),
        },
        "current": scope.serialize(current, refs, names),
        "versions": [scope.summary(scope.as_data(row), names) for row in rows],
    }


@router.get("/{investigation_id}/scope")
def get_scope(
    investigation_id: uuid.UUID,
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """The case's current scope and its version history (newest first). A case without a stored scope shows its
    question and linked complaints as version 0."""
    case = _case(db, uuid.UUID(str(ctx.tenant_id)), investigation_id)
    return _scope_payload(db, control_db, case, scope.versions_of(db, case.tenant_id, case.id))


@router.get("/{investigation_id}/scope/versions/{version}")
def get_scope_version(
    investigation_id: uuid.UUID,
    version: int = Path(ge=1, le=100000),
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    from backend.app.db.models.case_scope import InvestigationScopeVersion

    case = _case(db, uuid.UUID(str(ctx.tenant_id)), investigation_id)
    row = (
        db.query(InvestigationScopeVersion)
        .filter(
            InvestigationScopeVersion.tenant_id == case.tenant_id,
            InvestigationScopeVersion.investigation_id == case.id,
            InvestigationScopeVersion.version == version,
        )
        .first()
    )
    if row is None:
        raise _error(404, "SCOPE_VERSION_NOT_FOUND", "This version of the scope does not exist")
    data = scope.as_data(row)
    return scope.serialize(
        data,
        scope.references(db, case.tenant_id, [data]),
        scope.names_for(control_db, case.tenant_id, [row.created_by]),
    )


@router.put("/{investigation_id}/scope", dependencies=[Depends(require_permission(INVESTIGATION_WORK))])
def save_scope(
    investigation_id: uuid.UUID,
    payload: ScopeRequest,
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """Record a new version of the case's scope. Once a version exists, a change needs its reason. Every id must be
    the organization's own, complaints and versions of the case's product, and no complaint both included and
    excluded. Included complaints outside the chosen versions or dates are warnings, not errors.

    The case's question becomes the scope's question and its complaint links the included complaints; the first
    scope saved on an OPEN case starts it (IN_PROGRESS)."""
    from backend.app.workflow.people import acting_role

    tenant_id = uuid.UUID(str(ctx.tenant_id))
    case = _case(db, tenant_id, investigation_id, lock=True)
    if states.case_state(case) in states.CLOSED_STATES:
        raise _error(409, "INVESTIGATION_CLOSED", "This investigation is closed; reopen it first")
    data = payload.model_dump()
    data["product_version_ids"] = scope.id_list(data["product_version_ids"])
    data["included_complaint_ids"] = scope.id_list(data["included_complaint_ids"])
    data["excluded_complaints"] = scope.excluded_list(data["excluded_complaints"])
    data["lot_ids"] = scope.id_list(data["lot_ids"])
    data["failure_mode_ids"] = scope.id_list(data["failure_mode_ids"])
    if scope.conflicting_complaints(data["included_complaint_ids"], data["excluded_complaints"]):
        raise _error(
            422, "COMPLAINT_INCLUDED_AND_EXCLUDED", "A complaint is either included in the scope or excluded, not both"
        )
    previous_row = scope.latest_version(db, tenant_id, case.id)
    if previous_row is not None and not data.get("change_reason"):
        raise _error(422, "CHANGE_REASON_REQUIRED", "Say in at least 10 characters why the scope changes")
    previous = scope.as_data(previous_row) if previous_row is not None else scope.derived_scope(db, case)
    # The lot impact list (tr08) stays with every later version: its factor, its signed snapshot and the lots left out
    # (a lot put back in the scope here is no longer left out).
    data["excluded_lots"] = [item for item in previous["excluded_lots"] if item["lot_id"] not in data["lot_ids"]]
    data["lot_impact"] = previous["lot_impact"]
    included = scope.check_references(db, case, data)
    warnings = scope.scope_warnings(included, data["product_version_ids"], data["date_from"], data["date_to"])
    diff = scope.scope_diff(previous, data)
    now = states.now_utc()
    role = acting_role(control_db, tenant_id, ctx.user_id, INVESTIGATION_WORK)
    row = scope.write_version(db, case, data, actor_ref=str(ctx.user_id), actor_role=role, now=now)
    question_before = case.investigation_question
    if case.investigation_question != row.question:
        case.investigation_question = row.question
    linked, unlinked = scope.sync_complaint_links(db, case, row.included_complaint_ids, now)
    case.updated_at = now
    question_changed = question_before != case.investigation_question
    db.add(
        make_audit_event(
            tenant_id=tenant_id,
            actor_ref=str(ctx.user_id),
            action="INVESTIGATION_SCOPE_CHANGED",
            entity_type="Investigation",
            entity_id=case.id,
            correlation_id=ctx.correlation_id,
            reason=row.change_reason or "Scope recorded",
            old_values={"question": question_before} if question_changed else None,
            new_values={"question": case.investigation_question} if question_changed else None,
            details={
                "version": row.version,
                **scope.diff_counts(diff),
                "complaint_links_added": len(linked),
                "complaint_links_removed": len(unlinked),
                "reviews_must_restart": bool(row.reviews_must_restart),
                "conclusions_invalidated": bool(row.conclusions_invalidated),
                "warnings": len(warnings),
                "actor_role": role,
            },
            created_at=now,
        )
    )
    states.start_case(
        db,
        case,
        actor_ref=str(ctx.user_id),
        reason=f"Scope version {row.version} recorded",
        correlation_id=ctx.correlation_id,
    )
    db.commit()
    saved = scope.as_data(row)
    refs = scope.references(db, tenant_id, [saved, previous])
    names = scope.names_for(control_db, tenant_id, [row.created_by])
    return {
        "scope": scope.serialize(saved, refs, names),
        "diff": scope.labelled_diff(diff, refs),
        "warnings": warnings,
    }


# ------------------------------------------------------------------------------------------------- readiness


@router.get("/{investigation_id}/readiness")
def get_readiness(
    investigation_id: uuid.UUID,
    db: Session = Depends(get_data_plane_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """How far the case is from a decision: its steps and the checks a decision depends on. Read only."""
    case = _case(db, uuid.UUID(str(ctx.tenant_id)), investigation_id)
    return readiness.evaluate(readiness.case_facts(db, case))
