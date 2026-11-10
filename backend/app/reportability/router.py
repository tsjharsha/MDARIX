"""Reportability watch API: the complaints whose reportability needs a decision, against the organization's reporting
windows, and the windows themselves (the decision itself is the signed market assessment: assessment_router).

Reading is open to every signed-in member of the organization, like the complaint list. Recording a decision needs
regulatory.review or regulatory.approve; changing the windows needs regulatory.approve (they come from the
organization's procedure). Every change carries a rationale or reason and is in the audit trail. MDARIX never decides
reportability and never submits a report.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.access.permissions import REGULATORY_APPROVE, REGULATORY_REVIEW, require_permission
from backend.app.db.data_plane import get_data_plane_db
from backend.app.db.models.reportability import ReportabilitySettings
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
def decide_reportability(complaint_id: uuid.UUID):
    """The single decision recorded before per-market assessment (0.10.52) is closed (code audit 9 and owner decision
    10 Nov): "not reportable" is concluded by a signed market assessment, and a filed report is recorded on its signed
    reportable conclusion. Decisions recorded here before are still read (the watch, the complaint)."""
    raise _error(
        409,
        "SIGNED_ASSESSMENT_REQUIRED",
        "Reportability is decided on the complaint's market assessment: sign each market's conclusion, and record a "
        "filed report on the signed reportable conclusion (Record the filing)",
    )


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
