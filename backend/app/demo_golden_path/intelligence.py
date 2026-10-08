"""The case's intelligence: the AI's hypothesis and the investigators' own judgements. (Part of the demo golden path; see __init__.py.)"""

from __future__ import annotations
import uuid
from datetime import datetime
from backend.app import demo_story as story

from backend.app.demo_golden_path.context import Story
from backend.app.demo_golden_path.evidence import _ctx


# ------------------------------------------------------------------------------------------------ intelligence

AI_HYPOTHESIS = (
    "Cassette valves moulded on the new tool T-4 have a thicker membrane at the gate that can stay closed after the "
    "cassette is loaded, so the pump detects no flow and stops the infusion."
)
HUMAN_HYPOTHESIS = (
    "The interruptions are use errors (cassette not fully seated or the extension-set clamp left closed), not a "
    "device fault."
)
HUMAN_HYPOTHESIS_RATIONALE = "One report describes a closed clamp; loading errors are a known cause of no-flow alarms."
UNKNOWN_LOTS = "Were the valve membranes of cassette lots C-301 to C-303 within the drawing tolerance at incoming?"
UNKNOWN_REV1 = "Do cassettes from the previous tool (Rev 1 pumps) show the same sticking under the same test?"
CHAIN_NAME = "Thick membrane to interrupted therapy"
CHAIN_NODES = (
    "Valve moulding moved to tool T-4",
    "Membrane thicker than drawing at the gate",
    "Membrane stays closed after cassette loading",
    "Pump detects no flow and stops the infusion",
    "Therapy delayed",
)
# (from, to, state, evidence or None, rationale)
CHAIN_LINKS = (
    (0, 1, "PARTIALLY_SUPPORTED", "ACD-EV-4011", "The change notice gives no membrane data; RMA-9127 measured thick."),
    (1, 2, "HYPOTHESIZED", None, "Plausible mechanism; not yet shown on more than one cassette."),
    (2, 3, "SUPPORTED", "ACD-EV-4013", "RMA-9127 reproduced the no-flow alarm when its membrane stayed closed."),
    (3, 4, "SUPPORTED", "ACD-EV-4012", "Complaints report delayed doses after the interruptions."),
)
# (evidence, epistemic type, statement, rationale)
OBSERVATIONS = (
    (
        "ACD-EV-4013",
        "FACT",
        "One of two returned cassettes gave a no-flow alarm on three of twenty loads at 23 C.",
        "Read from the bench test report.",
    ),
    (
        "ACD-EV-4014",
        "SOURCE_ASSERTION",
        "DV-305 tested flow continuity with cassettes from the previous tool only.",
        "The verification report says so; tool T-4 parts were never verified.",
    ),
    (
        "ACD-EV-4012",
        "DERIVED_OBSERVATION",
        "Every flow interruption complaint since Rev 2 comes from pump lots built with tool T-4 cassettes.",
        "Lot comparison of the complaint trend.",
    ),
)


def seed_ai_hypothesis(s: Story):
    """Day 31: an AI-origin hypothesis with the AI's own evidence links, as the hypothesis engine materializes them.
    The AI run behind it is a synthetic demo record (no model was called), labelled so in its provider and kind."""
    from backend.app.db.models.foundation import AIExecution, Hypothesis, HypothesisEvidence

    moment = s.at(31)
    execution = AIExecution(
        id=uuid.uuid4(),
        tenant_id=s.tenant_id,
        investigation_id=s.case.id,
        requestor_ref=s.person("INVESTIGATOR").user_id,
        provider="demo-seed",
        model_name="synthetic-demo",
        model_version="none",
        prompt_template_version="Hypotheses (synthetic demo run, no model called)",
        orchestration_version="demo-seed",
        evidence_refs={"evidence_identifiers": ["ACD-EV-4011", "ACD-EV-4012", "ACD-EV-4014"]},
        structured_output={"synthetic": True, "hypotheses": [AI_HYPOTHESIS]},
        rationale_summary=f"{story.SYNTHETIC}: stands in for an AI hypothesis run in the demo story.",
        validation_status="DEMO_SEEDED",
        execution_timestamp=moment,
        latency_ms=0,
    )
    s.db.add(execution)
    s.db.flush()
    row = Hypothesis(
        id=uuid.uuid4(),
        tenant_id=s.tenant_id,
        investigation_id=s.case.id,
        statement=AI_HYPOTHESIS,
        status="mixed_evidence",
        origin="ai",
        reviewer_disposition=None,
        source_system="demo-seed",
        created_at=moment,
        updated_at=moment,
    )
    s.db.add(row)
    s.db.flush()
    for code, relation, rationale in (
        ("ACD-EV-4011", "support", "The change notice dates the new tool before the complaints began."),
        ("ACD-EV-4012", "support", "All complaints come from lots with tool T-4 cassettes."),
        ("ACD-EV-4014", "contradict", "Design verification found no flow interruption."),
    ):
        s.db.add(
            HypothesisEvidence(
                id=uuid.uuid4(),
                tenant_id=s.tenant_id,
                hypothesis_id=row.id,
                evidence_id=s.evidence[code].id,
                relation_type=relation,
                rationale=rationale,
                created_by_type="system",
                created_at=moment,
            )
        )
    s.db.flush()
    s.made["ai_execution"] = execution
    s.made["ai_hypothesis"] = row
    return row


def seed_human_intelligence(s: Story):
    """Days 44-28: Ines adds a hypothesis, two unknowns, an evidence link, a failure chain and observations, each
    with its history row and audit event, as the case intelligence endpoints write them."""
    from backend.app.access.permissions import INVESTIGATION_WORK
    from backend.app.case_intelligence import rules
    from backend.app.case_intelligence.router import _record, _store_chain
    from backend.app.db.models.evidence_intelligence import EvidenceObservation
    from backend.app.db.models.foundation import Hypothesis, HypothesisEvidence, Unknown

    ines = s.person("INVESTIGATOR")
    ctx = _ctx()

    def record(moment, **kwargs):
        _record(s.db, ctx=ctx, person=ines, permission=INVESTIGATION_WORK, case=s.case, now=moment, **kwargs)

    moment = s.at(44)
    human = Hypothesis(
        id=uuid.uuid4(),
        tenant_id=s.tenant_id,
        investigation_id=s.case.id,
        statement=HUMAN_HYPOTHESIS,
        status=rules.PROPOSED.lower(),
        origin=rules.ORIGIN_HUMAN,
        human_status=rules.PROPOSED,
        status_reason=HUMAN_HYPOTHESIS_RATIONALE,
        status_changed_by=ines.user_id,
        status_changed_at=moment,
        created_by=ines.user_id,
        created_at=moment,
        updated_at=moment,
    )
    s.db.add(human)
    s.db.flush()
    record(
        moment,
        object_type=rules.OBJECT_HYPOTHESIS,
        object_id=human.id,
        entity_type="Hypothesis",
        event_type=rules.EVENT_CREATED,
        to_value=rules.PROPOSED,
        reason=HUMAN_HYPOTHESIS_RATIONALE,
        details={"business_id": human.business_id, "statement": HUMAN_HYPOTHESIS, "origin": "HUMAN"},
        new_values={"statement": HUMAN_HYPOTHESIS, "human_status": rules.PROPOSED},
    )

    unknowns = {}
    for key, description, needed, hypothesis in (
        ("lots", UNKNOWN_LOTS, "Incoming inspection records of the cassette lots.", s.made["ai_hypothesis"]),
        ("rev1", UNKNOWN_REV1, "Rev 1 cassettes from the old tool loaded under the same bench test.", None),
    ):
        moment = s.at(30, 10 if key == "lots" else 20)
        row = Unknown(
            id=uuid.uuid4(),
            tenant_id=s.tenant_id,
            investigation_id=s.case.id,
            hypothesis_id=hypothesis.id if hypothesis is not None else None,
            category="evidence_gap",
            description=description,
            evidence_needed=needed,
            status=rules.UNKNOWN_OPEN,
            origin=rules.ORIGIN_HUMAN,
            created_by=ines.user_id,
            created_at=moment,
            updated_at=moment,
        )
        s.db.add(row)
        s.db.flush()
        record(
            moment,
            object_type=rules.OBJECT_UNKNOWN,
            object_id=row.id,
            entity_type="Unknown",
            event_type=rules.EVENT_CREATED,
            to_value=rules.UNKNOWN_OPEN,
            details={
                "business_id": row.business_id,
                "description": description,
                "hypothesis_business_id": hypothesis.business_id if hypothesis is not None else None,
            },
            new_values={"description": description, "category": "evidence_gap", "evidence_needed": needed},
        )
        unknowns[key] = row

    moment = s.at(29, 30)
    ai = s.made["ai_hypothesis"]
    link = HypothesisEvidence(
        id=uuid.uuid4(),
        tenant_id=s.tenant_id,
        hypothesis_id=ai.id,
        evidence_id=s.evidence["ACD-EV-4013"].id,
        relation_type=rules.relation_type("SUPPORTING"),
        rationale="RMA-9127 reproduced the alarm and its membrane measured above the drawing tolerance.",
        created_by_type=rules.CREATED_BY_HUMAN,
        created_by=ines.user_id,
        created_at=moment,
    )
    s.db.add(link)
    s.db.flush()
    ai.updated_at = moment
    record(
        moment,
        object_type=rules.OBJECT_HYPOTHESIS_EVIDENCE,
        object_id=link.id,
        entity_type="HypothesisEvidence",
        event_type=rules.EVENT_EVIDENCE_LINKED,
        to_value="SUPPORTING",
        reason=link.rationale,
        details={
            "business_id": ai.business_id,
            "hypothesis_id": str(ai.id),
            "evidence_id": str(link.evidence_id),
            "evidence_business_id": s.evidence["ACD-EV-4013"].business_id,
            "relation": "SUPPORTING",
        },
        new_values={"relation_type": link.relation_type, "rationale": link.rationale},
    )

    moment = s.at(28)
    links = [
        {
            "from_index": start,
            "to_index": end,
            "state": state,
            "evidence_id": s.evidence[code].id if code else None,
            "rationale": rationale,
        }
        for start, end, state, code, rationale in CHAIN_LINKS
    ]
    chain = _store_chain(
        s.db,
        tenant_id=s.tenant_id,
        case=s.case,
        person=ines,
        name=CHAIN_NAME,
        origin=rules.CHAIN_ORIGIN_HUMAN,
        labels=list(CHAIN_NODES),
        links=links,
        now=moment,
    )
    record(
        moment,
        object_type=rules.OBJECT_FAILURE_CHAIN,
        object_id=chain.id,
        entity_type="FailureChain",
        event_type=rules.EVENT_CREATED,
        to_value=rules.CHAIN_STATUS_DRAFT,
        details={
            "business_id": chain.business_id,
            "name": chain.name,
            "origin": "HUMAN",
            "nodes": len(CHAIN_NODES),
            "links": len(links),
        },
        new_values={
            "name": chain.name,
            "nodes": list(CHAIN_NODES),
            "links": [{"from_index": a, "to_index": b, "state": state} for a, b, state, *_ in CHAIN_LINKS],
        },
    )

    for index, (code, kind, statement, rationale) in enumerate(OBSERVATIONS):
        moment = s.at(27, index * 10)
        ev = s.evidence[code]
        row = EvidenceObservation(
            id=uuid.uuid4(),
            tenant_id=s.tenant_id,
            evidence_id=ev.id,
            statement=statement,
            observation_type=rules.HUMAN_OBSERVATION_TYPE,
            extraction_method=rules.HUMAN_EXTRACTION_METHOD,
            quality_status=rules.HUMAN_QUALITY_STATUS,
            effective_context={"rationale": rationale},
            epistemic_type=kind,
            origin=rules.OBSERVATION_ORIGIN_HUMAN,
            created_by=ines.user_id,
            investigation_id=s.case.id,
            created_at=moment,
        )
        s.db.add(row)
        s.db.flush()
        record(
            moment,
            object_type=rules.OBJECT_OBSERVATION,
            object_id=row.id,
            entity_type="EvidenceObservation",
            event_type=rules.EVENT_CREATED,
            to_value=kind,
            reason=rationale,
            details={
                "evidence_id": str(ev.id),
                "evidence_business_id": ev.business_id,
                "statement": statement,
                "epistemic_type": kind,
            },
            new_values={"statement": statement, "epistemic_type": kind},
        )
    s.db.flush()
    s.made.update(human_hypothesis=human, unknowns=unknowns, failure_chain=chain)


def judge_hypothesis(s: Story, row, status: str, reason: str, moment: datetime) -> None:
    """Ines's judgement of a hypothesis, as ``POST .../hypotheses/{id}/status`` records it."""
    from backend.app.access.permissions import INVESTIGATION_WORK
    from backend.app.case_intelligence import rules
    from backend.app.case_intelligence.router import _record

    ines = s.person("INVESTIGATOR")
    before = {
        "human_status": row.human_status,
        "status_reason": row.status_reason,
        "reviewer_disposition": row.reviewer_disposition,
    }
    row.human_status = status
    row.status_reason = reason
    row.status_changed_by = ines.user_id
    row.status_changed_at = moment
    if row.reviewer_disposition is None:
        row.reviewer_disposition = rules.HUMAN_JUDGED
    row.updated_at = moment
    _record(
        s.db,
        ctx=_ctx(),
        person=ines,
        permission=INVESTIGATION_WORK,
        case=s.case,
        object_type=rules.OBJECT_HYPOTHESIS,
        object_id=row.id,
        entity_type="Hypothesis",
        event_type=rules.EVENT_STATUS_CHANGED,
        from_value=before["human_status"],
        to_value=status,
        reason=reason,
        details={"business_id": row.business_id, "origin": rules.origin_code(row.origin), "ai_status": row.status},
        old_values=before,
        new_values={"human_status": status, "status_reason": reason, "reviewer_disposition": row.reviewer_disposition},
        now=moment,
    )
    s.db.flush()


def settle_unknown(s: Story, row, status: str, reason: str, moment: datetime) -> None:
    """Ines resolves an unknown or accepts it as a limitation, as ``POST .../unknowns/{id}/status`` records it."""
    from backend.app.access.permissions import INVESTIGATION_WORK
    from backend.app.case_intelligence import rules
    from backend.app.case_intelligence.router import _record

    if not rules.unknown_transition_allowed(row.status, status):
        raise ValueError(f"{row.business_id}: {row.status} cannot become {status}")
    ines = s.person("INVESTIGATOR")
    before = {"status": row.status, "resolution": row.resolution}
    row.status = status
    row.resolution = reason if status in rules.RESOLUTION_STATUSES else None
    row.status_changed_by = ines.user_id
    row.status_changed_at = moment
    row.updated_at = moment
    _record(
        s.db,
        ctx=_ctx(),
        person=ines,
        permission=INVESTIGATION_WORK,
        case=s.case,
        object_type=rules.OBJECT_UNKNOWN,
        object_id=row.id,
        entity_type="Unknown",
        event_type=rules.EVENT_STATUS_CHANGED,
        from_value=before["status"],
        to_value=status,
        reason=reason,
        details={"business_id": row.business_id, "previous_resolution": before["resolution"]},
        old_values=before,
        new_values={"status": row.status, "resolution": row.resolution},
        now=moment,
    )
    s.db.flush()
