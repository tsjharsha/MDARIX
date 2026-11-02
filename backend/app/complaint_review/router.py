"""Complaint review API: the second look at possible hidden complaints, a person's decision on each, the complaint
backlog board, and the organization's settings for both.

Reading is open to every signed-in member of the organization, like the complaint list. Deciding needs a role that
triages complaints or opens cases (signal.triage, investigation.create or quality.review); changing the settings
needs signal.triage, like the detection rules. Every change carries a reason and is in the audit trail.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.access.permissions import (
    AI_RUN,
    INVESTIGATION_CREATE,
    QUALITY_REVIEW,
    SIGNAL_TRIAGE,
    require_permission,
)
from backend.app.complaint_review import rules, service
from backend.app.db.data_plane import get_data_plane_db
from backend.app.db.models.complaint_review import SECOND_LOOK_DECISIONS, ComplaintSecondLook, ComplaintSettings
from backend.app.db.session import get_db
from backend.app.enterprise_audit import make_audit_event
from backend.app.evidence_workflow.people import require_any_permission
from backend.app.request_context import AuthenticatedRequestContext, get_request_context
from backend.app.business_ids import complaint_ref

router = APIRouter(prefix="/api/v1/complaints", tags=["Complaint review"])


def _error(status: int, code: str, message: str) -> HTTPException:
    return HTTPException(status, detail={"code": code, "message": message})


def _reason(value: str) -> str:
    text = " ".join(str(value or "").split())
    if len(text) < rules.REASON_MIN:
        raise ValueError(f"Say in at least {rules.REASON_MIN} characters why")
    return text


class DecisionRequest(BaseModel):
    decision: str = Field(max_length=20)
    reason: str = Field(max_length=2000)

    @field_validator("decision")
    @classmethod
    def _known(cls, value: str) -> str:
        decision = str(value or "").strip().upper()
        if decision not in SECOND_LOOK_DECISIONS:
            raise ValueError("decision must be CONFIRMED or DISMISSED")
        return decision

    @field_validator("reason")
    @classmethod
    def _why(cls, value: str) -> str:
        return _reason(value)


class SettingsRequest(BaseModel):
    backlog_target_days: int = Field(ge=rules.TARGET_DAYS_MIN, le=rules.TARGET_DAYS_MAX)
    # Null: back to the default list.
    second_look_words: list[str] | None = Field(default=None, max_length=rules.WORDS_MAX * 2)
    reason: str = Field(max_length=2000)

    @field_validator("reason")
    @classmethod
    def _why(cls, value: str) -> str:
        return _reason(value)


@router.get("/second-look")
def second_look(
    state: str = Query("open", pattern="^(open|decided)$"),
    product_id: uuid.UUID | None = None,
    page: int = Query(1, ge=1, le=10000),
    page_size: int = Query(25, ge=1, le=200),
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """Records that may be hidden complaints, most serious first, each with why it was flagged (and the latest AI
    explanation of it, when someone asked for one)."""
    from backend.app.complaint_review import explain

    tenant_id = uuid.UUID(ctx.tenant_id)
    result = service.second_look(
        db,
        control_db,
        tenant_id,
        state=state,
        product_id=product_id,
        page=page,
        page_size=page_size,
    )
    explained = explain.latest(db, tenant_id, [item["id"] for item in result["items"]])
    for item in result["items"]:
        item["explanation"] = explained.get(item["id"])
    return result


@router.post("/{complaint_id}/second-look/explain", dependencies=[Depends(require_permission(AI_RUN))])
def explain_second_look(
    complaint_id: uuid.UUID,
    db: Session = Depends(get_data_plane_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """The AI's explanation of why a flagged record may meet the definition of a complaint: at most three sentences,
    each quoting the record's own fields, checked before it is shown and saved as an AI result with its trust check.
    When AI is off, unavailable or over budget, the rules' reasons stand alone and the answer says why."""
    from backend.app.complaint_review import explain

    tenant_id = uuid.UUID(ctx.tenant_id)
    record, flagged = service.assess(db, tenant_id, complaint_id)
    if record is None:
        raise _error(404, "COMPLAINT_NOT_FOUND", "No such complaint in your organization")
    if flagged is None:
        existing = (
            db.query(ComplaintSecondLook)
            .filter(ComplaintSecondLook.tenant_id == tenant_id, ComplaintSecondLook.complaint_id == complaint_id)
            .first()
        )
        if existing is None:
            raise _error(
                409, "NOT_ON_SECOND_LOOK", "This record is not on the second look, so there is nothing to explain"
            )
        shown = dict(existing.flagged or {})
    else:
        shown = flagged.as_dict()
    result = explain.explain(db, tenant_id, record, shown, actor_ref=ctx.user_id)
    db.commit()
    return {"complaint_id": record["id"], **result}


@router.post(
    "/{complaint_id}/second-look",
    dependencies=[Depends(require_any_permission(SIGNAL_TRIAGE, INVESTIGATION_CREATE, QUALITY_REVIEW))],
)
def decide(
    complaint_id: uuid.UUID,
    payload: DecisionRequest,
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """A person's decision on a flagged record: it is a complaint (CONFIRMED) or not (DISMISSED). A revised decision
    replaces the earlier one; both are in the audit trail. The record itself is never changed."""
    tenant_id = uuid.UUID(ctx.tenant_id)
    record, flagged = service.assess(db, tenant_id, complaint_id)
    if record is None:
        raise _error(404, "COMPLAINT_NOT_FOUND", "No such complaint in your organization")
    existing = (
        db.query(ComplaintSecondLook)
        .filter(ComplaintSecondLook.tenant_id == tenant_id, ComplaintSecondLook.complaint_id == complaint_id)
        .with_for_update()
        .first()
    )
    if flagged is None and existing is None:
        raise _error(
            409,
            "NOT_ON_SECOND_LOOK",
            "This record is not on the second look: it is not cancelled, an inquiry or a recurring No Fault Found "
            "with complaint signs",
        )
    if existing is not None and existing.decision == payload.decision:
        raise _error(422, "NOTHING_TO_CHANGE", "This is already the decision on this record")
    now = datetime.now(timezone.utc)
    shown = flagged.as_dict() if flagged else dict(existing.flagged or {})
    action = "COMPLAINT_SECOND_LOOK_DECIDED"
    old_values = None
    if existing is None:
        existing = ComplaintSecondLook(
            tenant_id=tenant_id,
            complaint_id=complaint_id,
            decision=payload.decision,
            reason=payload.reason,
            flagged=shown,
            decided_by=ctx.user_id,
            decided_at=now,
        )
        db.add(existing)
    else:
        action = "COMPLAINT_SECOND_LOOK_REVISED"
        old_values = {"decision": existing.decision}
        existing.decision, existing.reason, existing.flagged = payload.decision, payload.reason, shown
        existing.decided_by, existing.decided_at = ctx.user_id, now
    db.add(
        make_audit_event(
            tenant_id=tenant_id,
            actor_ref=ctx.user_id,
            action=action,
            entity_type="Complaint",
            entity_id=complaint_id,
            correlation_id=ctx.correlation_id,
            reason=payload.reason,
            details={
                "complaint": complaint_ref(record),
                "reasons": [item["code"] for item in shown.get("reasons", [])],
                "signs": [item["code"] for item in shown.get("signs", [])],
            },
            old_values=old_values,
            new_values={"decision": payload.decision},
            created_at=now,
        )
    )
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise _error(409, "DECIDED_MEANWHILE", "Someone decided on this record a moment ago; reload to see it") from exc
    names = service.people(control_db, tenant_id, [existing.decided_by])
    return {**record, **shown, "decision": service.decision_of(existing, names)}


@router.get("/backlog")
def backlog(
    show: str = Query("all", pattern="^(all|past_target|due_soon)$"),
    product_id: uuid.UUID | None = None,
    page: int = Query(1, ge=1, le=10000),
    page_size: int = Query(25, ge=1, le=200),
    db: Session = Depends(get_data_plane_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """Open complaints in no signal and no case, oldest first, against the organization's target days."""
    return service.backlog(
        db, uuid.UUID(ctx.tenant_id), show=show, product_id=product_id, page=page, page_size=page_size
    )


@router.get("/review-settings")
def review_settings(
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    return service.settings_of(db, uuid.UUID(ctx.tenant_id), control_db)


@router.put("/review-settings", dependencies=[Depends(require_permission(SIGNAL_TRIAGE))])
def update_review_settings(
    payload: SettingsRequest,
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """Change the backlog target days and the second look's words (null: the default words). A new version."""
    tenant_id = uuid.UUID(ctx.tenant_id)
    words = None if payload.second_look_words is None else rules.clean_words(payload.second_look_words)
    if words is not None:
        problem = rules.words_problem(words)
        if problem:
            raise _error(422, "WORDS_INVALID", problem)
        if words == list(rules.DEFAULT_WORDS):
            words = None
    before = service.settings_of(db, tenant_id)
    row = db.query(ComplaintSettings).filter(ComplaintSettings.tenant_id == tenant_id).with_for_update().first()
    old = {"backlog_target_days": before["backlog_target_days"], "second_look_words": before["second_look_words"]}
    new = {
        "backlog_target_days": payload.backlog_target_days,
        "second_look_words": words if words is not None else list(rules.DEFAULT_WORDS),
    }
    if old == new and (row is None or (row.second_look_words is None) == (words is None)):
        raise _error(422, "NOTHING_TO_CHANGE", "These are already the settings")
    now = datetime.now(timezone.utc)
    if row is None:
        row = ComplaintSettings(tenant_id=tenant_id, version=1)
        db.add(row)
        version = 1
    else:
        version = int(row.version or 1) + 1
    row.backlog_target_days = payload.backlog_target_days
    row.second_look_words = words
    row.version = version
    row.updated_by = ctx.user_id
    row.updated_at = now
    db.flush()
    db.add(
        make_audit_event(
            tenant_id=tenant_id,
            actor_ref=ctx.user_id,
            action="COMPLAINT_REVIEW_SETTINGS_UPDATED",
            entity_type="ComplaintSettings",
            entity_id=row.id,
            correlation_id=ctx.correlation_id,
            reason=payload.reason,
            details={"version": version},
            old_values={key: value for key, value in old.items() if old[key] != new[key]},
            new_values={key: value for key, value in new.items() if old[key] != new[key]},
            created_at=now,
        )
    )
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise _error(409, "CHANGED_MEANWHILE", "The settings were changed a moment ago; reload and try again") from exc
    return service.settings_of(db, tenant_id, control_db)
