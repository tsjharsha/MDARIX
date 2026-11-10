"""The closure criteria of a case.

A case in the Decision Brief flow (it has a Decision Brief version or a brief decision) closes only when: its current
signed decision accepts the conclusion (ACCEPT_CONCLUSION, ACCEPT_WITH_CONDITIONS or CLOSE_NO_FURTHER_ACTION), no
impact assessment is open, no risk or regulatory review is requested or in progress, no evidence request of high or
critical priority is open, every follow-up chosen in the decision has its record and task (they may still be open),
and a reason is given. Any other case closes as it always did (only a decision awaiting its human review stops it).

- ``GET /api/v1/investigations/{id}/closure-check``: ``{can_close, applies, criteria}``;
- ``refuse_unmet_closure``: called by ``PATCH /api/v1/investigations/{id}`` when closing (409
  CLOSURE_CRITERIA_NOT_MET with the blocked criteria).
"""

from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from backend.app.db.data_plane import get_data_plane_db
from backend.app.db.models.decision_outcomes import DecisionFollowUp, ImpactAssessment
from backend.app.db.models.foundation import Decision, Investigation
from backend.app.db.models.workflow import WorkflowTask
from backend.app.decision_followups import common, rules
from backend.app.request_context import AuthenticatedRequestContext, get_request_context

logger = logging.getLogger("mdarix.decision_followups")

router = APIRouter(tags=["Case Closure"])


def in_brief_flow(db: Session, case: Investigation) -> bool:
    """True when the case has any Decision Brief version or any brief decision. Read in a SAVEPOINT: when it cannot
    be read (an organization database without these tables) the case keeps today's closing rules."""
    from backend.app.db.models.reviews import DecisionBriefVersion

    try:
        with db.begin_nested():
            if (
                db.query(DecisionBriefVersion.id)
                .filter(
                    DecisionBriefVersion.tenant_id == case.tenant_id, DecisionBriefVersion.investigation_id == case.id
                )
                .first()
                is not None
            ):
                return True
            return (
                db.query(Decision.id)
                .filter(
                    Decision.tenant_id == case.tenant_id,
                    Decision.investigation_id == case.id,
                    Decision.decision_kind == rules.BRIEF_KIND,
                )
                .first()
                is not None
            )
    except Exception:
        logger.warning("Whether case %s is in the Decision Brief flow could not be read", case.id, exc_info=True)
        return False


def _awaiting_review(db: Session, case: Investigation) -> bool:
    from backend.app.investigation_open_router import DECISIONS_AWAITING_REVIEW

    return (
        db.query(Decision.id)
        .filter(
            Decision.tenant_id == case.tenant_id,
            Decision.investigation_id == case.id,
            Decision.decision_status.in_(DECISIONS_AWAITING_REVIEW),
        )
        .first()
        is not None
    )


def _brief_facts(db: Session, case: Investigation) -> dict:
    from backend.app.db.models.reviews import CaseReview
    from backend.app.db.models.stage3 import SupplierEvidenceRequest
    from backend.app.evidence_workflow.rules import FINISHED_STATUSES

    tenant_id = case.tenant_id
    decision = common.current_decision(db, tenant_id, case.id)
    recorded: list[dict] = []
    if decision is not None:
        rows = (
            db.query(DecisionFollowUp.action_type, DecisionFollowUp.task_id)
            .filter(DecisionFollowUp.tenant_id == tenant_id, DecisionFollowUp.decision_id == decision.id)
            .all()
        )
        task_ids = [task_id for _, task_id in rows if task_id is not None]
        existing = (
            {
                found
                for (found,) in db.query(WorkflowTask.id).filter(
                    WorkflowTask.tenant_id == tenant_id, WorkflowTask.id.in_(task_ids)
                )
            }
            if task_ids
            else set()
        )
        recorded = [
            {"action_type": action_type, "has_task": task_id is not None and task_id in existing}
            for action_type, task_id in rows
        ]
    return {
        "decision": (
            {"id": str(decision.id), "business_id": decision.business_id, "outcome": decision.outcome}
            if decision is not None
            else None
        ),
        "open_assessments": db.query(ImpactAssessment.id)
        .filter(
            ImpactAssessment.tenant_id == tenant_id,
            ImpactAssessment.investigation_id == case.id,
            ImpactAssessment.status == "OPEN",
        )
        .count(),
        "open_reviews": db.query(CaseReview.id)
        .filter(
            CaseReview.tenant_id == tenant_id,
            CaseReview.investigation_id == case.id,
            CaseReview.status.in_(rules.OPEN_REVIEW_STATUSES),
        )
        .count(),
        "urgent_requests": db.query(SupplierEvidenceRequest.id)
        .filter(
            SupplierEvidenceRequest.tenant_id == tenant_id,
            SupplierEvidenceRequest.investigation_id == case.id,
            SupplierEvidenceRequest.priority.in_(rules.URGENT_PRIORITIES),
            SupplierEvidenceRequest.status.notin_(sorted(FINISHED_STATUSES)),
        )
        .count(),
        "chosen": rules.chosen_actions(decision.follow_up_actions) if decision is not None else [],
        "recorded": recorded,
    }


def closure_facts(db: Session, case: Investigation, *, reason: str | None = None) -> dict:
    """What the closure criteria read about the case (``rules.closure_criteria``)."""
    from backend.app.case_workflow import states

    applies = in_brief_flow(db, case)
    facts = {
        "closed": states.case_state(case) in states.CLOSED_STATES,
        "awaiting_review": _awaiting_review(db, case),
        "applies": applies,
        "reason": reason,
    }
    if applies:
        facts.update(_brief_facts(db, case))
    return facts


def closure_check(db: Session, case: Investigation, *, reason: str | None = None) -> dict:
    return rules.closure_result(closure_facts(db, case, reason=reason))


def refuse_unmet_closure(db: Session, case: Investigation, *, reason: str | None) -> None:
    """Called while closing the (locked) case: a case in the Decision Brief flow whose closure criteria are not met is
    refused (409 CLOSURE_CRITERIA_NOT_MET, with the blocked criteria). Any other case is left to today's rules."""
    if not in_brief_flow(db, case):
        return
    criteria = rules.closure_criteria(closure_facts(db, case, reason=reason))
    blocked = [item for item in rules.blocked(criteria) if item["key"] != "CASE_OPEN"]
    if blocked:
        raise common.error(
            409,
            "CLOSURE_CRITERIA_NOT_MET",
            "This investigation cannot be closed yet: " + "; ".join(item["rationale"] for item in blocked),
            criteria=blocked,
        )


@router.get("/api/v1/investigations/{investigation_id}/closure-check")
def investigation_closure_check(
    investigation_id: uuid.UUID,
    db: Session = Depends(get_data_plane_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """Whether the case can be closed now, and each criterion with its result (PASS, BLOCKED or NOT_REQUIRED) and
    why. ``applies`` says whether the Decision Brief criteria apply to the case."""
    case = common.load_case(db, common.tenant_of(ctx), investigation_id)
    return closure_check(db, case)


__all__ = ["router", "in_brief_flow", "closure_facts", "closure_check", "refuse_unmet_closure"]
