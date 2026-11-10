"""Reportability watch API: the complaints whose reportability needs a decision, against the organization's reporting
windows; a person's decision on each; and the windows themselves.

Reading is open to every signed-in member of the organization, like the complaint list. Recording a decision needs
regulatory.review or regulatory.approve; changing the windows needs regulatory.approve (they come from the
organization's procedure). Every change carries a rationale or reason and is in the audit trail. MDARIX never decides
reportability and never submits a report.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.access.permissions import REGULATORY_APPROVE, REGULATORY_REVIEW, require_permission
from backend.app.complaint_review.service import people
from backend.app.db.data_plane import get_data_plane_db
from backend.app.db.models.reportability import REPORTABILITY_DECISIONS, ComplaintReportability, ReportabilitySettings
from backend.app.db.session import get_db
from backend.app.enterprise_audit import make_audit_event
from backend.app.evidence_workflow.people import require_any_permission
from backend.app.reportability import rules, service
from backend.app.request_context import AuthenticatedRequestContext, get_request_context

router = APIRouter(prefix="/api/v1/complaints", tags=["Reportability watch"])

REMINDER_TASK = "REPORTABILITY_DECISION"
COMPLAINT_SOURCE = "Complaint"


def _error(status: int, code: str, message: str) -> HTTPException:
    return HTTPException(status, detail={"code": code, "message": message})


def _text(value: str, minimum: int, what: str) -> str:
    text = " ".join(str(value or "").split())
    if len(text) < minimum:
        raise ValueError(f"Say in at least {minimum} characters {what}")
    return text


class DecisionRequest(BaseModel):
    decision: str = Field(max_length=20)
    rationale: str = Field(max_length=4000)
    report_reference: str | None = Field(default=None, max_length=rules.REFERENCE_MAX)
    reported_on: date | None = None

    @field_validator("decision")
    @classmethod
    def _known(cls, value: str) -> str:
        decision = str(value or "").strip().upper()
        if decision not in REPORTABILITY_DECISIONS:
            raise ValueError("decision must be REPORTED or NOT_REPORTABLE")
        return decision

    @field_validator("rationale")
    @classmethod
    def _why(cls, value: str) -> str:
        return _text(value, rules.REASON_MIN, "why")

    @field_validator("report_reference")
    @classmethod
    def _reference(cls, value: str | None) -> str | None:
        text = " ".join(str(value or "").split())
        return text or None


class WindowRequest(BaseModel):
    name: str = Field(max_length=rules.NAME_MAX * 2)
    markets: list[str] = Field(default_factory=list, max_length=rules.MARKETS_MAX * 2)
    triggers: list[str] = Field(default_factory=list, max_length=len(rules.TRIGGERS) * 2)
    days: int
    day_basis: str = Field(default=rules.CALENDAR, max_length=20)
    note: str | None = Field(default=None, max_length=rules.NOTE_MAX * 2)
    # Catalog ids (backend/app/standards.py), kept from the template; unknown ids are dropped. Absent: the template's.
    basis: list[str] | None = Field(default=None, max_length=50)


class SettingsRequest(BaseModel):
    windows: list[WindowRequest] = Field(default_factory=list, max_length=rules.WINDOWS_MAX * 2)
    lookback_days: int = Field(ge=rules.LOOKBACK_MIN, le=rules.LOOKBACK_MAX)
    reason: str = Field(max_length=2000)

    @field_validator("reason")
    @classmethod
    def _why(cls, value: str) -> str:
        return _text(value, rules.REASON_MIN, "why")


@router.get("/reportability")
def reportability_watch(
    show: str = Query("open", pattern="^(open|overdue|due_soon|follow_up|decided|all)$"),
    product_id: uuid.UUID | None = None,
    page: int = Query(1, ge=1, le=10000),
    page_size: int = Query(25, ge=1, le=200),
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """Complaints that report a death, a serious injury or a malfunction, or a patient whose outcome is unknown, most
    urgent first, each with its reporting clocks and missing answers."""
    return service.watch(
        db, control_db, uuid.UUID(ctx.tenant_id), show=show, product_id=product_id, page=page, page_size=page_size
    )


@router.post(
    "/{complaint_id}/reportability",
    dependencies=[Depends(require_any_permission(REGULATORY_REVIEW, REGULATORY_APPROVE))],
)
def decide_reportability(
    complaint_id: uuid.UUID,
    payload: DecisionRequest,
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """The single decision recorded before per-market assessment (0.10.52): it still records that a report was filed
    (REPORTED, with the report's reference and the day it was filed, and the rationale). A revision replaces it; both
    are in the audit trail. "Not reportable" is concluded only by a signed market assessment (code audit 9): rows
    recorded here before are still read."""
    tenant_id = uuid.UUID(ctx.tenant_id)
    if payload.decision == rules.NOT_REPORTABLE:
        raise _error(
            409,
            "SIGNED_ASSESSMENT_REQUIRED",
            "Not reportable is concluded by a signed market assessment: open the complaint's market assessment and "
            "sign each market's conclusion",
        )
    today = service.today_utc()
    found = service.one(db, tenant_id, complaint_id, today)
    if found is None:
        raise _error(404, "COMPLAINT_NOT_FOUND", "No such complaint in your organization")
    complaint, record, seen, second_look = found
    if not payload.report_reference or payload.reported_on is None:
        raise _error(422, "REPORT_DETAILS_REQUIRED", "Give the report's reference and the day it was filed")
    if payload.reported_on > today:
        raise _error(422, "REPORTED_IN_FUTURE", "The day the report was filed cannot be in the future")
    aware = date.fromisoformat(seen["aware_date"]) if seen["aware_date"] else None
    if aware is not None and payload.reported_on < aware:
        raise _error(
            422, "REPORTED_BEFORE_AWARENESS", "The report cannot be filed before the organization became aware"
        )
    reference, reported_on = payload.report_reference, payload.reported_on
    existing = (
        db.query(ComplaintReportability)
        .filter(ComplaintReportability.tenant_id == tenant_id, ComplaintReportability.complaint_id == complaint_id)
        .with_for_update()
        .first()
    )
    on_watch = rules.watched(record) and service.counts_as_complaint(
        complaint.status, complaint.complaint_type, second_look
    )
    if existing is None and not on_watch:
        raise _error(
            409,
            "NOT_ON_WATCH",
            "This complaint is not on the reportability watch: it reports no death, serious injury or malfunction, "
            "and no patient with an unknown outcome",
        )
    if existing is not None and (
        existing.decision,
        existing.rationale,
        existing.report_reference,
        existing.reported_on,
    ) == (payload.decision, payload.rationale, reference, reported_on):
        raise _error(422, "NOTHING_TO_CHANGE", "This is already the decision on this complaint")
    binding = seen["binding"]
    now = datetime.now(timezone.utc)
    action = "COMPLAINT_REPORTABILITY_DECIDED"
    old_values = None
    if existing is None:
        existing = ComplaintReportability(
            tenant_id=tenant_id,
            complaint_id=complaint_id,
            window_name=binding["window"] if binding else None,
            due_on=date.fromisoformat(binding["due_date"]) if binding else None,
        )
        db.add(existing)
    else:
        action = "COMPLAINT_REPORTABILITY_REVISED"
        old_values = {
            "decision": existing.decision,
            "report_reference": existing.report_reference,
            "reported_on": existing.reported_on.isoformat() if existing.reported_on else None,
        }
        # The window that bound the first decision stays: changing the windows later never rewrites timeliness.
    existing.decision, existing.rationale = payload.decision, payload.rationale
    existing.report_reference, existing.reported_on = reference, reported_on
    existing.decided_by, existing.decided_at = ctx.user_id, now
    db.add(
        make_audit_event(
            tenant_id=tenant_id,
            actor_ref=ctx.user_id,
            action=action,
            entity_type="Complaint",
            entity_id=complaint_id,
            correlation_id=ctx.correlation_id,
            reason=payload.rationale,
            details={
                "complaint": record["business_id"] or record["complaint_identifier"],
                "window": existing.window_name,
                "due_on": existing.due_on.isoformat() if existing.due_on else None,
                "aware_date": seen["aware_date"],
                "triggers": seen["triggers"],
            },
            old_values=old_values,
            new_values={
                "decision": payload.decision,
                "report_reference": reference,
                "reported_on": reported_on.isoformat() if reported_on else None,
            },
            created_at=now,
        )
    )
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise _error(
            409, "DECIDED_MEANWHILE", "Someone decided on this complaint a moment ago; reload to see it"
        ) from exc
    _finish_reminders(db, tenant_id, complaint_id, payload.decision, ctx)
    names = people(control_db, tenant_id, [existing.decided_by])
    return {**record, **seen, "state": rules.DECIDED, "decision": service.decision_view(existing, names)}


def _finish_reminders(db: Session, tenant_id: uuid.UUID, complaint_id: uuid.UUID, decision: str, ctx) -> None:
    """The decision ends the complaint's reminder task; a failure never undoes the decision."""
    from backend.app.workflow import tasks as task_service

    task_service.run_hook(
        db,
        "reportability decided",
        lambda session: task_service.complete_tasks(
            session,
            tenant_id,
            source_type=COMPLAINT_SOURCE,
            source_id=complaint_id,
            task_types=[REMINDER_TASK],
            outcome=decision,
            actor_ref=ctx.user_id,
            correlation_id=ctx.correlation_id,
        ),
    )


@router.get("/reportability-settings")
def reportability_settings(
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    return service.settings_of(db, uuid.UUID(ctx.tenant_id), control_db)


@router.put("/reportability-settings", dependencies=[Depends(require_permission(REGULATORY_APPROVE))])
def update_reportability_settings(
    payload: SettingsRequest,
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """Replace the organization's reporting windows and look-back. A new version, in the audit trail."""
    tenant_id = uuid.UUID(ctx.tenant_id)
    windows = [rules.clean_window(item.model_dump()) for item in payload.windows]
    problem = rules.windows_problem(windows)
    if problem:
        raise _error(422, "WINDOWS_INVALID", problem)
    before = service.settings_of(db, tenant_id)
    old = {"windows": before["windows"], "lookback_days": before["lookback_days"]}
    new = {"windows": windows, "lookback_days": payload.lookback_days}
    if old == new:
        raise _error(422, "NOTHING_TO_CHANGE", "These are already the settings")
    row = db.query(ReportabilitySettings).filter(ReportabilitySettings.tenant_id == tenant_id).with_for_update().first()
    now = datetime.now(timezone.utc)
    if row is None:
        row = ReportabilitySettings(tenant_id=tenant_id, version=1)
        db.add(row)
        version = 1
    else:
        version = int(row.version or 1) + 1
    row.windows, row.lookback_days, row.version = windows, payload.lookback_days, version
    row.updated_by, row.updated_at = ctx.user_id, now
    db.flush()
    db.add(
        make_audit_event(
            tenant_id=tenant_id,
            actor_ref=ctx.user_id,
            action="REPORTABILITY_SETTINGS_UPDATED",
            entity_type="ReportabilitySettings",
            entity_id=row.id,
            correlation_id=ctx.correlation_id,
            reason=payload.reason,
            details={"version": version, "windows": [window["name"] for window in windows]},
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
