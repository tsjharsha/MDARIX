"""Running the case's AI steps in one pass.

The steps are the ones the four separate buttons ran, in order, each reusing the result of the step before (so no
step runs the earlier ones again): the analysis, the competing explanations, the challenges, the unknowns, the failure
chains and the investigation brief, all for one point in time (the run's ``as_of``). Each step keeps working exactly as
before: written by the language model when AI is on and available, by the rules otherwise (AI off, over budget, no
provider, no evidence yet), and checked as before. The run records each step's outcome; the steps' results are stored
where they always were, so the case page, the readiness checks and the Decision Brief read them as before.

Runs in the background after the request that queued it (FastAPI background task), in its own session on the
organization's data plane and in the organization's AI scope (genai.governance.tenant_scope).
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from backend.app.db.models.case_ai import CaseAiRun
from backend.app.enterprise_audit import make_audit_event

logger = logging.getLogger("mdarix.case_ai")

STEPS = (
    ("ANALYSIS", "Analysis of the evidence"),
    ("HYPOTHESES", "Competing explanations"),
    ("CHALLENGES", "Challenges to the explanations"),
    ("UNKNOWNS", "What is still unknown"),
    ("FAILURE_CHAINS", "Possible failure chains"),
    ("BRIEF", "Investigation brief"),
)
STEP_LABELS = dict(STEPS)
ACTIVE = ("QUEUED", "RUNNING")
# A run still QUEUED or RUNNING after this long is taken to have stopped (a restarted server); a new one may start.
STALE_AFTER = timedelta(minutes=30)


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def is_stale(run: CaseAiRun, now: datetime | None = None) -> bool:
    moment = run.started_at or run.requested_at
    return run.status in ACTIVE and moment is not None and (now or now_utc()) - moment > STALE_AFTER


def latest(db: Session, tenant_id: uuid.UUID, investigation_id: uuid.UUID) -> CaseAiRun | None:
    return (
        db.query(CaseAiRun)
        .filter(CaseAiRun.tenant_id == tenant_id, CaseAiRun.investigation_id == investigation_id)
        .order_by(CaseAiRun.requested_at.desc(), CaseAiRun.id.desc())
        .first()
    )


def view(run: CaseAiRun | None) -> dict | None:
    if run is None:
        return None
    done = {item.get("step"): item for item in run.steps or []}
    status = "FAILED" if is_stale(run) else run.status
    return {
        "id": str(run.id),
        "status": status,
        "trigger": run.trigger,
        "as_of": run.as_of.isoformat() if run.as_of else None,
        "requested_at": run.requested_at.isoformat() if run.requested_at else None,
        "started_at": run.started_at.isoformat() if run.started_at else None,
        "finished_at": run.finished_at.isoformat() if run.finished_at else None,
        "error": "The run stopped before it finished; start it again" if is_stale(run) else run.error,
        "steps": [
            {"step": code, "label": label, **({"status": "PENDING"} | done.get(code, {}))} for code, label in STEPS
        ],
    }


def _outcome(response, *, result_id) -> dict:
    """What a step's response says: who wrote it, its AI run, why AI did not contribute (if so)."""
    notice = getattr(response, "ai_notice", None)
    return {
        "status": "DONE",
        "author": "RULES" if notice is not None else "AI",
        "notice": getattr(notice, "message", None) if notice is not None else None,
        "reason_code": getattr(notice, "reason_code", None) if notice is not None else None,
        "ai_execution_id": str(response.ai_execution_id) if getattr(response, "ai_execution_id", None) else None,
        "result_id": str(result_id) if result_id else None,
    }


def _steps(db: Session, tenant_id: uuid.UUID, investigation_id: uuid.UUID, as_of: datetime, actor: str):
    """The steps, as (code, callable returning the step's outcome); each callable uses the results before it."""
    from briefs.schemas import BriefCreateRequest, BriefResponse
    from briefs.service import BriefService
    from challenger.schemas import ChallengeRequest
    from challenger.service import ChallengerService
    from failure_chain.schemas import FailureChainRequest
    from failure_chain.service import UnknownsFailureChainService
    from hypothesis_engine.schemas import HypothesisSetRequest
    from hypothesis_engine.service import CompetingHypothesisService
    from investigator.schemas import InvestigationAnalysisRequest
    from investigator.service import EvidenceGroundedInvestigatorService
    from unknowns.schemas import UnknownRequest

    common = {"tenant_id": tenant_id, "investigation_id": investigation_id, "temporal_mode": "current", "as_of": as_of}
    found: dict = {}

    def analysis():
        response = EvidenceGroundedInvestigatorService().analyze(
            db, InvestigationAnalysisRequest(**common, persist=True)
        )
        found["analysis"] = response.analysis.analysis_id
        outcome = _outcome(response, result_id=response.analysis.analysis_id)
        # The analysis says who wrote it: the language model, or the rules (AI off, unavailable or no evidence).
        outcome["author"] = "AI" if response.analysis.analysis_author == "LANGUAGE_MODEL" else "RULES"
        return outcome

    def hypotheses():
        response = CompetingHypothesisService().generate(
            db, HypothesisSetRequest(**common, source_analysis_id=found.get("analysis"), persist=True)
        )
        found["hypotheses"] = response.hypothesis_set.hypothesis_set_id
        return _outcome(response, result_id=found["hypotheses"])

    def challenges():
        response = ChallengerService().generate(
            db, ChallengeRequest(**common, hypothesis_set_id=found.get("hypotheses"), persist=True)
        )
        found["challenges"] = response.challenge_set.challenge_set_id
        return _outcome(response, result_id=found["challenges"])

    def unknowns():
        response = UnknownsFailureChainService().unknowns(
            db,
            UnknownRequest(
                **common,
                hypothesis_set_id=found.get("hypotheses"),
                challenge_set_id=found.get("challenges"),
                persist=True,
            ),
        )
        found["unknowns"] = response.unknown_set.unknown_set_id
        return _outcome(response, result_id=found["unknowns"])

    def chains():
        response = UnknownsFailureChainService().chains(
            db,
            FailureChainRequest(
                **common,
                hypothesis_set_id=found.get("hypotheses"),
                unknown_set_id=found.get("unknowns"),
                persist=True,
            ),
        )
        return _outcome(response, result_id=response.failure_chain_set.failure_chain_set_id)

    def brief():
        # The service answers with the brief as a dict; read it as the brief route does (its AI notice included).
        response = BriefResponse.model_validate(
            BriefService().generate(
                db,
                tenant_id,
                investigation_id,
                BriefCreateRequest(temporal_mode="current", as_of=as_of, generated_by=actor),
            )
        )
        return _outcome(response, result_id=response.id)

    return (
        ("ANALYSIS", analysis),
        ("HYPOTHESES", hypotheses),
        ("CHALLENGES", challenges),
        ("UNKNOWNS", unknowns),
        ("FAILURE_CHAINS", chains),
        ("BRIEF", brief),
    )


def _error_code(exc: Exception) -> str:
    return str(getattr(exc, "code", None) or getattr(exc, "reason", None) or type(exc).__name__)[:120]


def execute(db: Session, run_id: uuid.UUID) -> CaseAiRun | None:
    """Run the steps of a queued run, saving each step's outcome as it finishes. A failing step stops the run (the
    steps after it need its result); what was done stays. Never raises."""
    run = db.query(CaseAiRun).filter(CaseAiRun.id == run_id).with_for_update().first()
    if run is None or run.status != "QUEUED":
        return run
    tenant_id, investigation_id = run.tenant_id, run.investigation_id
    run.status, run.started_at = "RUNNING", now_utc()
    db.commit()
    outcomes: list[dict] = []
    failed = None
    for code, step in _steps(db, tenant_id, investigation_id, run.as_of, run.requested_by):
        started = now_utc()
        try:
            outcome = step()
            db.commit()
        except Exception as exc:  # a step's own refusal or failure: recorded, never raised
            db.rollback()
            logger.exception("Case AI run %s: step %s failed", run_id, code)
            outcome = {"status": "FAILED", "error": _error_code(exc)}
            failed = code
        outcome = {"step": code, **outcome, "seconds": round((now_utc() - started).total_seconds(), 1)}
        outcomes.append(outcome)
        run = db.query(CaseAiRun).filter(CaseAiRun.id == run_id).first()
        run.steps = list(outcomes)
        db.commit()
        if failed:
            break
    done = sum(1 for item in outcomes if item["status"] == "DONE")
    run.status = "COMPLETED" if not failed else ("PARTIAL" if done else "FAILED")
    run.error = f"{STEP_LABELS[failed]} failed: {outcomes[-1]['error']}" if failed else None
    run.finished_at = now_utc()
    db.add(
        make_audit_event(
            tenant_id=tenant_id,
            actor_ref=run.requested_by,
            action="CASE_AI_RUN_FINISHED",
            entity_type="Investigation",
            entity_id=investigation_id,
            details={
                "run_id": str(run.id),
                "status": run.status,
                "trigger": run.trigger,
                "steps": [
                    {"step": item["step"], "status": item["status"], "author": item.get("author")} for item in outcomes
                ],
            },
            created_at=run.finished_at,
        )
    )
    db.commit()
    return run


def run_in_background(tenant_id: uuid.UUID, run_id: uuid.UUID) -> None:
    """The background task: the run in its own session on the organization's data plane, in its AI scope."""
    from backend.app.db.data_plane import open_tenant_data_session
    from genai.governance import tenant_scope

    try:
        with tenant_scope(tenant_id), open_tenant_data_session(tenant_id) as db:
            execute(db, run_id)
    except Exception:
        logger.exception("Case AI run %s could not run", run_id)
