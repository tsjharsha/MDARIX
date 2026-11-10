"""The case AI run API: start the case's AI analysis in one pass, and follow it.

- ``POST /api/v1/investigations/{id}/ai-run`` (ai.run): queues a run and starts it in the background (202).
  ``trigger=AUTO`` (the case page, the first time it opens) starts one only when the case has neither a run nor a
  saved analysis, and only when AI really answers for the organization (a provider configured and allowed, AI switched
  on, allowance left); otherwise it answers with what exists (200), so opening a case page never repeats the AI's work
  and never writes rule results in the AI's name when AI is off.
  A run already queued or running is answered as it is (409 for a person's MANUAL request).
- ``GET /api/v1/investigations/{id}/ai-run``: the latest run with each step's outcome (``run`` is null without one).

The steps are those of the case's AI buttons, in one pass (backend/app/case_ai/runner.py); AI never decides.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.app.access.permissions import AI_RUN, require_permission
from backend.app.case_ai import runner
from backend.app.db.data_plane import get_data_plane_db
from backend.app.db.models.case_ai import CaseAiRun
from backend.app.db.models.foundation import Investigation
from backend.app.db.session import get_db
from backend.app.enterprise_audit import make_audit_event
from backend.app.request_context import AuthenticatedRequestContext, get_request_context

router = APIRouter(prefix="/api/v1/investigations", tags=["Case AI run"])


class RunRequest(BaseModel):
    trigger: str = Field(default="MANUAL", pattern="^(AUTO|MANUAL)$")


def _case(db: Session, tenant_id: uuid.UUID, investigation_id: uuid.UUID) -> Investigation:
    case = (
        db.query(Investigation)
        .filter(Investigation.tenant_id == tenant_id, Investigation.id == investigation_id)
        .first()
    )
    if case is None:
        raise HTTPException(
            404, detail={"code": "INVESTIGATION_NOT_FOUND", "message": "Not found in your organization"}
        )
    return case


def _has_analysis(db: Session, tenant_id: uuid.UUID, investigation_id: uuid.UUID) -> bool:
    from investigator.service import EvidenceGroundedInvestigatorService

    try:
        return EvidenceGroundedInvestigatorService().latest(db, tenant_id, investigation_id) is not None
    except Exception:
        return False


@router.get("/{investigation_id}/ai-run")
def latest_run(
    investigation_id: uuid.UUID,
    db: Session = Depends(get_data_plane_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    tenant_id = uuid.UUID(str(ctx.tenant_id))
    _case(db, tenant_id, investigation_id)
    return {"run": runner.view(runner.latest(db, tenant_id, investigation_id)), "steps": list(runner.STEP_LABELS)}


@router.post("/{investigation_id}/ai-run", dependencies=[Depends(require_permission(AI_RUN))])
def start_run(
    investigation_id: uuid.UUID,
    payload: RunRequest,
    background: BackgroundTasks,
    db: Session = Depends(get_data_plane_db),
    control: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    from backend.app.ai_settings import ai_ready

    tenant_id = uuid.UUID(str(ctx.tenant_id))
    case = (
        db.query(Investigation)
        .filter(Investigation.tenant_id == tenant_id, Investigation.id == investigation_id)
        .with_for_update()
        .first()
    )
    if case is None:
        raise HTTPException(
            404, detail={"code": "INVESTIGATION_NOT_FOUND", "message": "Not found in your organization"}
        )
    current = runner.latest(db, tenant_id, investigation_id)
    if current is not None and current.status in runner.ACTIVE and not runner.is_stale(current):
        if payload.trigger == "AUTO":
            return {"started": False, "run": runner.view(current)}
        raise HTTPException(
            409,
            detail={
                "code": "AI_RUN_IN_PROGRESS",
                "message": "The AI analysis of this investigation is already running",
            },
        )
    if payload.trigger == "AUTO" and (current is not None or _has_analysis(db, tenant_id, investigation_id)):
        # The case's AI work exists already: opening its page never repeats it.
        return {"started": False, "run": runner.view(current)}
    if payload.trigger == "AUTO" and not ai_ready(control, tenant_id):
        # AI is off, not available or used up: opening the case page starts nothing (the steps work by hand).
        return {"started": False, "run": runner.view(current), "reason": "AI_NOT_READY"}
    if current is not None and runner.is_stale(current):
        current.status, current.error = "FAILED", "The run stopped before it finished"
        current.finished_at = runner.now_utc()
    now = datetime.now(timezone.utc)
    run = CaseAiRun(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        investigation_id=investigation_id,
        status="QUEUED",
        trigger=payload.trigger,
        as_of=now,
        steps=[],
        requested_by=str(ctx.user_id),
        requested_at=now,
    )
    db.add(run)
    db.add(
        make_audit_event(
            tenant_id=tenant_id,
            actor_ref=ctx.user_id,
            action="CASE_AI_RUN_REQUESTED",
            entity_type="Investigation",
            entity_id=investigation_id,
            correlation_id=ctx.correlation_id,
            details={"run_id": str(run.id), "trigger": payload.trigger, "case": case.business_id},
            created_at=now,
        )
    )
    db.commit()
    background.add_task(runner.run_in_background, tenant_id, run.id)
    return JSONResponse(status_code=202, content={"started": True, "run": runner.view(run)})
