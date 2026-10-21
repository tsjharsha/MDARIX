"""Golden evaluation runs: the real analysis pipeline scored on the synthetic golden scenarios.

``POST /runs`` never grades canned output. It records a RUNNING evaluation for the caller's organization and runs
``evaluation.real_pipeline.run_real_golden_suite`` in the background (the investigator and hypothesis engine as a user
gets them: the configured language model, or the rules in controlled mode when no provider is configured). The run
reads the synthetic golden organization in a short-lived system-scope session; nothing about it is saved there. Only
a computed result is stored: PASS when every scenario passed, FAIL otherwise, ERROR when the run could not complete.

Only a Platform Administrator starts a run (pre-launch review SEC-08): it reads another organization (the synthetic
golden one) in system scope and keeps a CPU busy for minutes, so it is MDARIX's own release check (Platform Admin >
AI > Evaluations), never something a customer or a free trial starts. Reading the published result stays open.
"""

import hashlib
import json
import logging
import time
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.app.db.models.foundation import EvaluationRun, ReleaseAssuranceResult
from backend.app.db.data_plane import get_data_plane_db
from backend.app.db.session import get_db
from backend.app.request_context import AuthenticatedRequestContext, get_request_context
from backend.app.access.authz import _require_platform_admin
from backend.app.access.permissions import AI_RUN, require_permission
from evaluation.harness import SCENARIO_IDS

router = APIRouter(prefix="/api/v1/evaluations", tags=["Golden Evaluation"])
logger = logging.getLogger("mdarix.evaluation")
# A run that has not finished after this long is treated as abandoned (the process ended), so a new one may start.
RUN_STALE_AFTER = timedelta(hours=2)


class EvaluationRequest(BaseModel):
    release_version: str = Field(default="MDARIX-R1", max_length=120)
    # Recorded with the run for reference; the run itself uses the configured provider (or the rules).
    model_version: str = Field(default="1.0", max_length=120)
    prompt_version: str = Field(default="R1-controlled-v1", max_length=120)
    # Limit the run to these scenarios (for example ["VS001"]); all of them when omitted.
    scenario_ids: list[str] | None = Field(default=None, max_length=len(SCENARIO_IDS))


def _scenario_ids(requested: list[str] | None) -> set[str] | None:
    if not requested:
        return None
    ids = {item.strip().upper() for item in requested}
    unknown = sorted(ids - set(SCENARIO_IDS))
    if unknown:
        raise HTTPException(
            422, detail={"code": "UNKNOWN_EVALUATION_SCENARIO", "message": "Unknown scenario: " + ", ".join(unknown)}
        )
    return ids


def _suite_outcome(report: dict) -> str:
    """PASS only when the pipeline ran on at least one scenario and every scenario passed."""
    total, passed = int(report.get("total") or 0), int(report.get("passed") or 0)
    return "PASS" if total and passed == total else "FAIL"


def run_golden_evaluation(scenario_ids: set[str] | None) -> dict:
    """The real pipeline on the golden scenarios, read in a system-scope session of the synthetic golden tenant."""
    from backend.app.db.session import RuntimeSessionLocal
    from backend.app.db.tenant_scope import bind_system
    from evaluation.real_pipeline import run_real_golden_suite

    session = RuntimeSessionLocal()
    try:
        bind_system(session, "golden evaluation run on the synthetic golden tenant")
        report = run_real_golden_suite(session, tenant_key=GOLDEN_TENANT_KEY, scenario_ids=scenario_ids)
        session.rollback()  # the pipeline saves nothing; leave no transaction open
        return report
    finally:
        session.close()


def _complete_run(run_id: uuid.UUID, tenant_id: str, release_version: str, scenario_ids: set[str] | None) -> None:
    """Run the evaluation and store what it computed (never a result that was not computed)."""
    from backend.app.db.data_plane import open_tenant_data_session
    from evaluation.real_pipeline import EVALUATION_VERSION

    try:
        report = json.loads(json.dumps(run_golden_evaluation(scenario_ids), default=str))
        outcome = _suite_outcome(report)
        failures = [
            {"scenario_id": item.get("scenario_id"), "status": item.get("status"), "error": item.get("error")}
            for item in report.get("results", [])
            if item.get("status") != "PASS"
        ]
        if not report.get("total"):
            failures.append({"error": "NO_SCENARIO_EVALUATED"})
    except Exception as exc:  # the run could not complete: record that, never a pass
        logger.exception("golden evaluation run %s failed", run_id)
        report = {"evaluation_version": EVALUATION_VERSION, "error": type(exc).__name__, "results": []}
        outcome, failures = "ERROR", [{"error": type(exc).__name__}]
    configuration = {
        "model": report.get("model"),
        "evaluation_version": report.get("evaluation_version"),
        "thresholds": report.get("thresholds"),
    }
    now = datetime.now(timezone.utc)
    # The result is computed; storing it must not be lost to a passing database hiccup. If every attempt fails the
    # run stays RUNNING and is reported as abandoned (ERROR) after RUN_STALE_AFTER: never as a pass.
    for attempt in range(1, 4):
        try:
            with open_tenant_data_session(uuid.UUID(str(tenant_id))) as db:
                row = (
                    db.query(EvaluationRun)
                    .filter(EvaluationRun.id == run_id, EvaluationRun.tenant_id == tenant_id)
                    .one()
                )
                row.status = outcome
                row.results = {**report, "outcome": outcome}
                row.configuration_hash = hashlib.sha256(json.dumps(configuration, sort_keys=True).encode()).hexdigest()
                row.completed_at = now
                db.add(
                    ReleaseAssuranceResult(
                        id=uuid.uuid4(),
                        tenant_id=row.tenant_id,
                        evaluation_run_id=row.id,
                        release_version=release_version,
                        suite_version=row.suite_version,
                        dataset_version=row.dataset_version,
                        configuration_hash=row.configuration_hash,
                        status="PASS" if outcome == "PASS" else "BLOCKED",
                        critical_failures={"items": failures},
                        limitations={
                            "items": [
                                "Internal assurance only; not regulatory certification.",
                                "Synthetic golden scenarios; a pass shows the pipeline met these scenarios' expectations only.",
                            ]
                        },
                        generated_at=now,
                        created_at=now,
                    )
                )
                db.commit()
            return
        except Exception:
            logger.exception("golden evaluation run %s: result not stored (attempt %s)", run_id, attempt)
            time.sleep(5 * attempt)


@router.post("/runs", status_code=202, dependencies=[Depends(require_permission(AI_RUN))])
def run_evaluation(
    request: EvaluationRequest,
    http_request: Request,
    background: BackgroundTasks,
    control_db: Session = Depends(get_db),
    db: Session = Depends(get_data_plane_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """Start an honest golden evaluation; 202 with the run id. Poll ``GET /runs/{id}`` until the status is PASS,
    FAIL or ERROR (RUNNING until then). One run at a time per organization. A Platform Administrator only, who holds
    every permission (403 ``PLATFORM_ADMIN_REQUIRED`` for anyone else who may run AI, SEC-08)."""
    from evaluation.harness import DATASET_VERSION
    from evaluation.real_pipeline import EVALUATION_VERSION

    _require_platform_admin(http_request, control_db)

    scenario_ids = _scenario_ids(request.scenario_ids)
    now = datetime.now(timezone.utc)
    running = (
        db.query(EvaluationRun.id)
        .filter(
            EvaluationRun.tenant_id == ctx.tenant_id,
            EvaluationRun.status == "RUNNING",
            EvaluationRun.started_at >= now - RUN_STALE_AFTER,
        )
        .first()
    )
    if running is not None:
        raise HTTPException(
            409,
            detail={
                "code": "EVALUATION_ALREADY_RUNNING",
                "message": "An evaluation is already running for your organization",
                "evaluation_run_id": str(running.id),
            },
        )
    requested = {
        "model_version": request.model_version,
        "prompt_version": request.prompt_version,
        "scenario_ids": sorted(scenario_ids) if scenario_ids else None,
    }
    row = EvaluationRun(
        id=uuid.uuid4(),
        tenant_id=ctx.tenant_id,
        suite_version=EVALUATION_VERSION,
        dataset_version=DATASET_VERSION,
        release_version=request.release_version,
        configuration_hash=hashlib.sha256(json.dumps(requested, sort_keys=True).encode()).hexdigest(),
        status="RUNNING",
        results={"outcome": "RUNNING", "requested": requested},
        started_at=now,
        created_at=now,
    )
    db.add(row)
    db.commit()
    background.add_task(_complete_run, row.id, str(ctx.tenant_id), request.release_version, scenario_ids)
    return {
        "evaluation_run_id": str(row.id),
        "business_id": row.business_id,
        "status": "RUNNING",
        "suite_version": row.suite_version,
        "dataset_version": row.dataset_version,
        "status_url": f"/api/v1/evaluations/runs/{row.id}",
        "human_review_required": True,
    }


GOLDEN_TENANT_KEY = "ACME_CARE_SYNTHETIC"


@router.get("/golden/latest")
def latest_golden_evaluation(ctx: AuthenticatedRequestContext = Depends(get_request_context)):
    """The latest honest evaluation of the real AI pipeline on the synthetic golden scenarios (Trust page).

    The run belongs to the synthetic golden tenant, so it is read in a separate, short-lived system-scope session
    limited to that one record; the caller's own session and tenant scope are untouched.
    """
    from backend.app.db.models.foundation import Tenant
    from backend.app.db.session import RuntimeSessionLocal
    from backend.app.db.tenant_scope import bind_system
    from evaluation.real_pipeline import EVALUATION_VERSION, trust_summary

    session = RuntimeSessionLocal()
    try:
        bind_system(session, "read the published golden evaluation (synthetic data)")
        row = (
            session.query(EvaluationRun)
            .join(Tenant, Tenant.id == EvaluationRun.tenant_id)
            # The published run (scripts/run_real_evaluation.py --record stores it COMPLETED). Runs started through
            # POST /runs (PASS / FAIL / ERROR, possibly of a few scenarios, or still RUNNING) are not published.
            .filter(
                Tenant.tenant_key == GOLDEN_TENANT_KEY,
                EvaluationRun.suite_version == EVALUATION_VERSION,
                EvaluationRun.status == "COMPLETED",
                EvaluationRun.completed_at.is_not(None),
            )
            .order_by(EvaluationRun.completed_at.desc())
            .first()
        )
        if row is None:
            return {"status": "NOT_RUN_YET", "evaluation": None}
        return {"status": "AVAILABLE", "evaluation": trust_summary(row.results, row.completed_at)}
    finally:
        session.close()


@router.get("/runs/{run_id}")
def get_evaluation(
    run_id: uuid.UUID,
    db: Session = Depends(get_data_plane_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    tenant = ctx.tenant_id
    row = db.query(EvaluationRun).filter(EvaluationRun.tenant_id == tenant, EvaluationRun.id == run_id).first()
    if not row:
        raise HTTPException(
            404, detail={"code": "EVALUATION_NOT_FOUND", "message": "Evaluation run is not available for this tenant"}
        )
    if row.status == "RUNNING" and row.started_at and row.started_at < datetime.now(timezone.utc) - RUN_STALE_AFTER:
        # The process that ran it ended before it finished: nothing was computed, so it can never count as a pass.
        row.status = "ERROR"
        row.results = {**(row.results or {}), "outcome": "ERROR", "error": "RUN_ABANDONED"}
        row.completed_at = datetime.now(timezone.utc)
        db.commit()
    return {
        "evaluation_run_id": row.id,
        "business_id": row.business_id,
        "started_at": row.started_at,
        "completed_at": row.completed_at,
        "suite_version": row.suite_version,
        "dataset_version": row.dataset_version,
        "release_version": row.release_version,
        "configuration_hash": row.configuration_hash,
        "status": row.status,
        "results": row.results,
    }
