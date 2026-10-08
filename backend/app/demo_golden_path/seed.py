"""The whole path: running the story, its summary and the idempotent entry point. (Part of the demo golden path; see __init__.py.)"""

from __future__ import annotations
from datetime import datetime
from sqlalchemy.orm import Session
from backend.app import demo_story as story

from backend.app.demo_golden_path.brief import (
    ACCEPT_COMMENT,
    BRIEF_V1,
    BRIEF_V2,
    RETURN_COMMENT,
    create_brief_version,
    quality_review,
)
from backend.app.demo_golden_path.case import add_later_complaints, open_case, rescope_case
from backend.app.demo_golden_path.context import GoldenPathSkipped, SEEDED_ACTION, SEED_ACTOR, Story, _context, logger
from backend.app.demo_golden_path.decision import (
    link_late_evidence,
    open_capa,
    record_decision_on_signal,
    sign_decision,
)
from backend.app.demo_golden_path.evidence import review_case_evidence
from backend.app.demo_golden_path.intelligence import (
    judge_hypothesis,
    seed_ai_hypothesis,
    seed_human_intelligence,
    settle_unknown,
)
from backend.app.demo_golden_path.requests import answer_evidence_request
from backend.app.demo_golden_path.reviews import CASE_REVIEWS, complete_case_review
from backend.app.demo_golden_path.triage import seed_signal, triage_signal


# ------------------------------------------------------------------------------------------------ the whole path


def run_story(s: Story) -> dict:
    """Every step, in the order of the story (each brief is composed from what the case holds at its moment)."""
    signal = seed_signal(s)
    triage_signal(s, signal)
    open_case(s, signal)
    add_later_complaints(s, signal)
    review_case_evidence(s)
    seed_ai_hypothesis(s)
    seed_human_intelligence(s)
    rescope_case(s)
    for spec in CASE_REVIEWS:
        complete_case_review(s, spec)

    first = create_brief_version(s, 1, BRIEF_V1, s.at(24), s.at(24, 60))
    quality_review(s, first, "RETURN_FOR_EVIDENCE", RETURN_COMMENT, s.at(23))
    unknowns = s.made["unknowns"]
    answer_evidence_request(s, unknowns["lots"])
    settle_unknown(
        s,
        unknowns["lots"],
        "resolved",
        "Answered by the incoming inspection records (ACD-EV-4016): membranes above tolerance were accepted.",
        s.at(18),
    )
    judge_hypothesis(
        s,
        s.made["human_hypothesis"],
        "RETIRED",
        "Bench tests reproduce the alarm with correct loading; only the excluded report shows a closed clamp.",
        s.at(17),
    )
    judge_hypothesis(
        s,
        s.made["ai_hypothesis"],
        "PARTIALLY_SUPPORTED",
        "Supported by the change notice, the lot trend, RMA-9127 and the inspection records; DV-305 did not test "
        "T-4 cassettes and only one returned cassette reproduced the alarm.",
        s.at(17, 20),
    )
    settle_unknown(
        s,
        unknowns["rev1"],
        "accepted_limitation",
        "No Rev 1 cassettes from the old tool are left to test; the decision accepts this limitation.",
        s.at(17, 40),
    )
    second = create_brief_version(s, 2, BRIEF_V2, s.at(14), s.at(14, 60))
    quality_review(s, second, "ACCEPT_FOR_DECISION", ACCEPT_COMMENT, s.at(12))

    decision = sign_decision(s, second, s.at(6))
    record_decision_on_signal(s, signal, decision, s.at(6, 5))
    open_capa(s, s.made["follow_ups"][0], decision, s.at(5))
    link_late_evidence(s, s.at(1))
    return summary(s)


def summary(s: Story) -> dict:
    """The business ids of what the golden path made."""
    made = s.made
    return {
        "investigation": s.case.business_id,
        "investigation_identifier": s.case.investigation_identifier,
        "signal": made["signal"].business_id,
        "scope_version": made.get("scope_version"),
        "evidence_request": made["evidence_request"].business_id,
        "hypotheses": [made["ai_hypothesis"].business_id, made["human_hypothesis"].business_id],
        "unknowns": [row.business_id for row in made["unknowns"].values()],
        "failure_chain": made["failure_chain"].business_id,
        "reviews": [row.business_id for row in made.get("reviews", [])],
        "decision_briefs": [row.business_id for row in made.get("briefs", [])],
        "decision": made["decision"].business_id,
        "signature": made["signature"].business_id,
        "follow_ups": [row.business_id for row in made["follow_ups"]],
        "capa": made["capa"].capa_identifier,
        "impact_assessment": made["impact_assessment"].business_id,
    }


def _already_seeded(db: Session, tenant_id) -> bool:
    """True when the golden case was already opened from a signal (the path is written in one transaction)."""
    from backend.app.db.models.foundation import Investigation
    from backend.app.db.models.signals import InvestigationSignal

    return (
        db.query(InvestigationSignal.id)
        .join(
            Investigation,
            (Investigation.tenant_id == InvestigationSignal.tenant_id)
            & (Investigation.id == InvestigationSignal.investigation_id),
        )
        .filter(
            InvestigationSignal.tenant_id == tenant_id,
            Investigation.investigation_identifier == story.GOLDEN_CASE,
        )
        .first()
        is not None
    )


def seed_golden_path(db: Session, tenant_id, now: datetime | None = None) -> dict:
    """Write the golden path into the demo workspace (``now``: the story's today, the day the story was loaded; read
    back from the golden case when not given), in a session of its own bound to the demo tenant (same database), in one transaction. Idempotent. Never raises:
    ``{"seeded": False, "reason": ...}`` when it was already there, cannot be written here, or failed (logged)."""
    from backend.app.db.tenant_scope import bind_tenant
    from backend.app.enterprise_audit import make_audit_event

    try:
        with Session(bind=db.get_bind()) as session:
            bind_tenant(session, tenant_id)
            if _already_seeded(session, tenant_id):
                return {"seeded": False, "reason": "The golden path is already in the workspace"}
            story_state = _context(session, tenant_id, now)
            made = run_story(story_state)
            session.add(
                make_audit_event(
                    tenant_id=tenant_id,
                    actor_ref=SEED_ACTOR,
                    action=SEEDED_ACTION,
                    entity_type="Investigation",
                    entity_id=story_state.case.id,
                    reason="Demo workspace golden path written (synthetic records, dated relative to today)",
                    details={"golden_path": made},
                )
            )
            session.commit()
            return {"seeded": True, **made}
    except GoldenPathSkipped as exc:
        logger.warning("The demo workspace's golden path was not written: %s", exc)
        return {"seeded": False, "reason": str(exc)}
    except Exception:
        logger.exception("The demo workspace's golden path was not written")
        return {"seeded": False, "reason": "Writing the golden path failed; see the log"}
