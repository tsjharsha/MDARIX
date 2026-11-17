"""The sample's AI proposals on the guided investigation (WHIF demo, story step 5), pre-recorded: no model is called.

One saved AI result on SAMPLE-INV-001, as an AI run on the case leaves it, written when the sample is seeded and marked
as a sample everywhere it shows: its provider is ``sample-recorded``, its model "pre-recorded sample answer". It
proposes:

- two observations, each read from one of the case's sample evidence documents (shown "AI proposal, not reviewed"
  until a person accepts, edits or rejects each one: ``POST /api/v1/ai-outputs/{id}/review``);
- one competing explanation for the fishbone (category Process: the cut in incoming inspection), with the evidence for
  and against it, beside the sample author's two hypotheses (sample_decision.py). Its status stays "proposed": only a
  person moves it.

Nothing here is usable downstream until a person accepts it (ai_review.usable_output), and it is not AI usage: no AI
call is recorded, so the trial's AI limit is untouched. Every row hangs off the sample case or carries
``MDARIX_SAMPLE``, so sample removal and the sample clock take it with the rest. Idempotent; flushes, never commits.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from backend.app.trial.sample_data import SAMPLE_SOURCE

PROVIDER = "sample-recorded"
MODEL = "pre-recorded sample answer (no model called)"
SAMPLE_CASE = "SAMPLE-INV-001"
RATIONALE = "Sample: an AI proposal recorded with the sample story. No model was called and nothing left MDARIX."
# (evidence, statement): read from that document's own words.
OBSERVATIONS = (
    (
        "SAMPLE-EV-002",
        "Two of 13 sampled sensors in lot 003 (about 15%) and one in lot 004 read 4-6% high at the upper pressure "
        "range; the Precision Sensors lots 001-002 show none. (Sample)",
    ),
    (
        "SAMPLE-EV-003",
        "Pressure-alarm complaints rose about sevenfold after Rev B (0.8 to 5.6 per month), mostly from lots 003 and "
        "004. (Sample)",
    ),
)
HYPOTHESIS = (
    "Cutting incoming inspection from 32 to 13 sensors per lot let out-of-range NovaSense sensors into lots 003 and "
    "004: the inspection change, not only the new supplier, contributed to the alarms. (Sample)"
)
CATEGORY = "PROCESS"
# (evidence, relation, why): for and against.
HYPOTHESIS_EVIDENCE = (
    ("SAMPLE-EV-001", "support", "The change record cut inspection sampling from 32 to 13 units for Rev B."),
    ("SAMPLE-EV-002", "support", "High readings were found only in the lots inspected under the reduced sampling."),
    (
        "SAMPLE-EV-002",
        "contradict",
        "Even 13 units found the high readings, so the sample size alone did not hide them: why were the lots "
        "released?",
    ),
)


def has_sample_ai(db: Session, tenant_id) -> bool:
    from backend.app.db.models.foundation import AIExecution

    return (
        db.query(AIExecution.id).filter(AIExecution.tenant_id == tenant_id, AIExecution.provider == PROVIDER).first()
        is not None
    )


def stage_sample_ai(db: Session, tenant_id, now: datetime | None = None) -> dict:
    """Add the pre-recorded AI proposals (see the module docstring). ``{"created": False, ...}`` without the sample
    case or its evidence, or when they are there already."""
    from backend.app.db.models.evidence_intelligence import EvidenceObservation
    from backend.app.db.models.foundation import AIExecution, Evidence, Hypothesis, HypothesisEvidence, Investigation

    now = now or datetime.now(timezone.utc)
    if has_sample_ai(db, tenant_id):
        return {"created": False, "why": "ALREADY_STAGED"}
    case = (
        db.query(Investigation)
        .filter(Investigation.tenant_id == tenant_id, Investigation.investigation_identifier == SAMPLE_CASE)
        .first()
    )
    evidence = (
        {
            row.evidence_identifier: row
            for row in db.query(Evidence).filter(Evidence.tenant_id == tenant_id, Evidence.investigation_id == case.id)
        }
        if case is not None
        else {}
    )
    if not {"SAMPLE-EV-001", "SAMPLE-EV-002", "SAMPLE-EV-003"} <= set(evidence):
        return {"created": False, "why": "NO_SAMPLE_CASE"}
    moment = now - timedelta(minutes=5)
    execution = AIExecution(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        investigation_id=case.id,
        requestor_ref="system:trial-sample",
        provider=PROVIDER,
        model_name=MODEL,
        model_version="none",
        prompt_template_version="Observations and competing explanations (sample, pre-recorded)",
        orchestration_version="sample",
        evidence_refs={"evidence_identifiers": sorted(evidence)},
        structured_output={
            "sample": True,
            "recorded": True,
            "observations": [{"evidence": code, "statement": text} for code, text in OBSERVATIONS],
            "hypotheses": [{"statement": HYPOTHESIS, "cause_category": CATEGORY}],
        },
        rationale_summary=RATIONALE,
        confidence_label="Sample",
        validation_status="VALIDATED",
        execution_timestamp=moment,
        latency_ms=0,
    )
    db.add(execution)
    db.flush()
    for code, statement in OBSERVATIONS:
        db.add(
            EvidenceObservation(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                evidence_id=evidence[code].id,
                investigation_id=case.id,
                statement=statement,
                observation_type="AI_EXTRACTED_OBSERVATION",
                extraction_method="GENAI",
                epistemic_type="AI_INTERPRETATION",
                origin="AI",
                quality_status="PROPOSED",  # a model proposed it; no person has reviewed it (review G14)
                effective_context={"rationale": RATIONALE, "sample": True},
                ai_execution_id=execution.id,
                created_by="system:trial-sample",
                created_at=moment,
            )
        )
    hypothesis = Hypothesis(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        investigation_id=case.id,
        statement=HYPOTHESIS,
        status="proposed",
        origin="ai",
        cause_category=CATEGORY,
        source_system=SAMPLE_SOURCE,
        source_identifier=str(execution.id),
        created_by="system:trial-sample",
        created_at=moment,
        updated_at=moment,
    )
    db.add(hypothesis)
    db.flush()
    for code, relation, why in HYPOTHESIS_EVIDENCE:
        db.add(
            HypothesisEvidence(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                hypothesis_id=hypothesis.id,
                evidence_id=evidence[code].id,
                relation_type=relation,
                rationale=why,
                created_by_type="ai",
                created_by="system:trial-sample",
                created_at=moment,
            )
        )
    db.flush()
    return {"created": True, "ai_results": 1, "observations": len(OBSERVATIONS), "hypotheses": 1}
