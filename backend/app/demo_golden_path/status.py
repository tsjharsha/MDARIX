"""The golden path's status, as the demo workspace screens show it. (Part of the demo golden path; see __init__.py.)"""

from __future__ import annotations
from sqlalchemy.orm import Session
from backend.app import demo_story as story

from backend.app.demo_golden_path.context import logger


# ---------------------------------------------------------------------------------------------------- status

LIVE_CASE = "ACD-INV-101"


def _status_of(db: Session, tenant_id) -> dict:
    from backend.app.case_workflow import states
    from backend.app.db.models.decision_outcomes import DecisionFollowUp, ImpactAssessment
    from backend.app.db.models.foundation import Capa, Investigation
    from backend.app.db.models.reviews import CaseReview, DecisionBriefVersion
    from backend.app.db.models.signals import InvestigationSignal, Signal
    from backend.app.human_decision import service

    cases = {
        row.investigation_identifier: row
        for row in db.query(Investigation).filter(
            Investigation.tenant_id == tenant_id,
            Investigation.investigation_identifier.in_([story.GOLDEN_CASE, LIVE_CASE]),
        )
    }
    waiting = [
        row.business_id
        for row in db.query(Signal)
        .filter(Signal.tenant_id == tenant_id, Signal.status == "NEW")
        .order_by(Signal.business_id)
    ]
    live = cases.get(LIVE_CASE)
    result = {
        "seeded": False,
        "live_case": (
            {"business_id": live.business_id, "identifier": LIVE_CASE, "workflow_state": states.case_state(live)}
            if live is not None
            else None
        ),
        "signals_awaiting_triage": waiting,
    }
    case = cases.get(story.GOLDEN_CASE)
    if case is None:
        return result

    def of_case(model, *order):
        return db.query(model).filter(model.tenant_id == tenant_id, model.investigation_id == case.id).order_by(*order)

    signals = [
        {"business_id": row.business_id, "status": row.status}
        for row in db.query(Signal)
        .join(
            InvestigationSignal,
            (InvestigationSignal.tenant_id == Signal.tenant_id) & (InvestigationSignal.signal_id == Signal.id),
        )
        .filter(InvestigationSignal.tenant_id == tenant_id, InvestigationSignal.investigation_id == case.id)
        .order_by(Signal.business_id)
    ]
    decision = service.current_decision(db, case)
    record = service.signature_record(db, decision) if decision is not None else None
    result.update(
        seeded=bool(signals) and decision is not None,
        investigation={
            "business_id": case.business_id,
            "identifier": case.investigation_identifier,
            "workflow_state": states.case_state(case),
        },
        signals=signals,
        decision_briefs=[
            {"business_id": row.business_id, "version": row.version, "status": row.status}
            for row in of_case(DecisionBriefVersion, DecisionBriefVersion.version)
        ],
        reviews=[
            {"business_id": row.business_id, "type": row.review_type, "outcome": row.outcome}
            for row in of_case(CaseReview, CaseReview.created_at)
        ],
        decision=(
            {
                "business_id": decision.business_id,
                "identifier": decision.decision_identifier,
                "outcome": decision.outcome,
                "signature": record.business_id if record is not None else None,
                "verification": service.verify_signature(db, record, decision)["status"],
            }
            if decision is not None
            else None
        ),
        follow_ups=[
            {"business_id": row.business_id, "action_type": row.action_type, "status": row.status}
            for row in of_case(DecisionFollowUp, DecisionFollowUp.business_id)
        ],
        capas=[row.capa_identifier for row in of_case(Capa, Capa.capa_identifier)],
        impact_assessments=[
            {"business_id": row.business_id, "status": row.status}
            for row in of_case(ImpactAssessment, ImpactAssessment.business_id)
        ],
    )
    return result


def golden_path_status(db: Session, tenant_id) -> dict:
    """What the demo shows on the golden path, by business id (case, signal, briefs, reviews, the signed decision
    with its verification, follow-ups, CAPA, impact assessments), the case left mid-investigation for live demos and
    the signals awaiting triage. Read in a session bound to the demo tenant; never raises."""
    from backend.app.db.tenant_scope import bind_tenant

    try:
        with Session(bind=db.get_bind()) as session:
            bind_tenant(session, tenant_id)
            return _status_of(session, tenant_id)
    except Exception:
        logger.exception("The demo workspace's golden path could not be read")
        return {"seeded": False, "error": "The golden path could not be read; see the log"}
