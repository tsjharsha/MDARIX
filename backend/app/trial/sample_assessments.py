"""The sample answers of a free trial's per-market assessments (T-SAM for 0.10.52, the trial plan's "0.10.51").

- SAMPLE-RV-07 (VentraLink 250, France, zero flow, no harm) has a signed EU/NI assessment by the sample author, as a
  finished example: "might have led to" a life-threatening deterioration answered Yes with its reason, a causal
  relationship reasonably possible, conclusion reportable (the 15-day report). The sample author holds the practice
  training acknowledgements it relies on.
- The same event has a signed Canada assessment (WHIF demo, "the right decision in every market"): a foreign incident
  of a device that is not Class I, so not reportable to Health Canada under s. 59, although the EU/NI answer is
  reportable. The sample author holds the Canada practice training too.
- SAMPLE-RV-08 (OrbitCare 300, US, free flow, outcome not known) has a saved US assessment: the patient's harm is
  Unknown, so the suggestion is pending information and "not reportable" is refused while it remains.
- SAMPLE-RV-06 (OrbitCare 300, US, under-infusion) waits for the trial user.
- The harm complaints carry a severity from the quality system, which the harm-severity scale maps to a level.

Every row is marked ``MDARIX_SAMPLE`` (sample removal takes it and everything done with it). The sample author is the
account of sample_decision.py, which cannot sign in; its signature record says it is a sample. Idempotent; flushes but
never commits (the caller owns the transaction).
"""

from __future__ import annotations

import logging
import uuid
from datetime import date, datetime, timedelta, timezone

from sqlalchemy.orm import Session

from backend.app.trial.sample_data import SAMPLE_SOURCE

logger = logging.getLogger("mdarix.trial.sample_assessments")

# The quality system's severity on the harm complaints (the scale maps each to a level; RV-06 has "Critical").
SAMPLE_SEVERITY = {"SAMPLE-RV-01": "Critical", "SAMPLE-RV-07": "Negligible", "SAMPLE-RV-09": "Serious"}


def _answer(answer: str, rationale: str, *evidence: str) -> dict:
    return {"answer": answer, "rationale": rationale, "evidence": list(evidence)}


EU_EXAMPLE = {
    "EU1": _answer(
        "YES",
        "The flow sensor read zero for 40 seconds: a malfunction of the device's performance.",
        "Complaint description",
    ),
    "EU2": _answer("NO", "No death: staff switched to manual ventilation and the patient was unharmed."),
    "EU3A": _answer(
        "YES",
        "Forty seconds without a valid flow reading on a ventilated patient might have led to life-threatening "
        "hypoventilation had staff not ventilated manually.",
        "Complaint description",
    ),
    "EU3B": _answer("NO", "Nothing suggests a permanent impairment could have followed within 40 seconds."),
    "EU3C": _answer("NO", "No hospitalisation followed; the patient was already in care and unharmed."),
    "EU3D": _answer("NO", "Manual ventilation is the expected response, not an intervention to prevent harm."),
    "EU3E": _answer("NOT_APPLICABLE", "A transient reading loss cannot lead to a chronic disease."),
    "EU3F": _answer("NOT_APPLICABLE", "The patient is an adult; no pregnancy is involved."),
    "EU4": _answer("NO", "One device, one event; nothing suggests an imminent risk to many people."),
    "EU5": _answer(
        "YES", "The zero reading came from the device's flow sensor: a causal relationship is reasonably possible."
    ),
    "EU6": _answer("NO", "A loss of flow reading is a hazard already in the risk file (SAMPLE-RSK-03)."),
}
# The same France event for Canada: sold there and a failure that could seriously harm were it to recur, but it
# happened outside Canada and VentraLink 250 is not a Class I device, so s. 59(1.1) does not apply.
CA_EXAMPLE = {
    "CA1": _answer("YES", "VentraLink 250 is sold in Canada (sample market list)."),
    "CA2": _answer(
        "YES", "The flow sensor read zero for 40 seconds: a failure of the device.", "Complaint description"
    ),
    "CA3": _answer("NO", "No harm: staff switched to manual ventilation and the patient was unharmed."),
    "CA4": _answer(
        "YES",
        "Forty seconds without a valid flow reading on a ventilated patient could lead to a serious deterioration "
        "were it to recur.",
        "Complaint description",
    ),
    "CA5": _answer("NO", "The event happened in France, outside Canada."),
    "CA6": _answer(
        "NO",
        "VentraLink 250 is not a Class I device in Canada; a foreign issue of a Class II to IV device is weighed "
        "under s. 61.2, not this tree.",
    ),
}
US_PENDING = {
    "US1": _answer("NO", "No death reported by the nurse."),
    "US2A": _answer("UNKNOWN", "The patient's outcome is not yet known; the nurse's follow-up is awaited."),
    "US2B": _answer("UNKNOWN", "The patient's outcome is not yet known; the nurse's follow-up is awaited."),
    "US2C": _answer("UNKNOWN", "Whether the patient needed any intervention is not yet known."),
    "US3": _answer("UNKNOWN", "Depends on the outcome: no harm is known yet."),
    "US4": _answer(
        "YES",
        "The pump free-flowed after the door was opened, against its specification.",
        "Complaint description",
    ),
}


def has_sample_assessments(db: Session, tenant_id) -> bool:
    from backend.app.db.models.market_assessment import ComplaintMarketAssessment

    return (
        db.query(ComplaintMarketAssessment.id)
        .filter(
            ComplaintMarketAssessment.tenant_id == tenant_id, ComplaintMarketAssessment.source_system == SAMPLE_SOURCE
        )
        .first()
        is not None
    )


def _complaints(db: Session, tenant_id) -> dict:
    from backend.app.db.models.foundation import Complaint

    return {
        row.complaint_identifier: row
        for row in db.query(Complaint).filter(
            Complaint.tenant_id == tenant_id,
            Complaint.source_system == SAMPLE_SOURCE,
            Complaint.complaint_identifier.in_(
                ["SAMPLE-RV-01", "SAMPLE-RV-06", "SAMPLE-RV-07", "SAMPLE-RV-08", "SAMPLE-RV-09"]
            ),
        )
    }


def _row(db: Session, tenant_id, complaint, market: str, answers: dict, level, term, author_id: str, now, **fields):
    from backend.app.db.models.market_assessment import ComplaintMarketAssessment
    from backend.app.reportability import assessments, deadlines, markets, service

    windows = service.settings_of(db, tenant_id)["windows"]
    aware, _ = service.awareness(complaint)
    zone = deadlines.org_zone(db, tenant_id)
    floor = assessments.floor_at(market, aware, zone)  # B4: the floor at awareness, as a person's save picks it
    evaluation = markets.evaluate(market, answers, floor)
    state = fields.get("conclusion") or evaluation["suggested"]
    # The rule's own date (code audit 3): a pending draft counts the report a signed "reportable" would start.
    clock = markets.market_clock(
        market,
        state,
        evaluation["report_type"],
        windows,
        aware,
        now,
        zone,
        evaluation["report_type_if_reportable"],
        floor,
    )
    row = ComplaintMarketAssessment(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        complaint_id=complaint.id,
        market=market,
        version=1,
        question_set=markets.QUESTION_SETS[market].version,
        answers=answers,
        harm_level=level,
        harm_code=term,
        scale_version=markets.SCALE_VERSION,
        suggested_conclusion=evaluation["suggested"],
        report_type=evaluation["report_type"],
        window_name=clock["window"] if clock else None,
        due_on=date.fromisoformat(clock["due_date"]) if clock else None,
        source_system=SAMPLE_SOURCE,
        created_by=author_id,
        created_at=now,
        updated_at=now,
        **fields,
    )
    return row, evaluation, clock


def _sign(db: Session, tenant_id, complaint, market: str, answers: dict, conclusion: str, author_id: str, signed_at):
    """One finished example: the assessment of ``complaint`` for ``market``, signed by the sample author."""
    from backend.app.db.models.foundation import SignedApprovalRecord
    from backend.app.human_decision.rules import fingerprint, signature_hash
    from backend.app.reportability import markets
    from backend.app.reportability.assessment_router import DECISION_TYPE, OBJECT_TYPE, SIGNATURE_CODES
    from backend.app.standards import STARTER_MARK
    from backend.app.trial.sample_decision import SAMPLE_AUTHOR_ROLE

    row, evaluation, clock = _row(
        db, tenant_id, complaint, market, answers, markets.NEGLIGIBLE, "NO_HEALTH_CONSEQUENCE", author_id, signed_at
    )
    ref = complaint.business_id or complaint.complaint_identifier
    material = {
        "complaint_id": str(row.complaint_id),
        "complaint": ref,
        "market": row.market,
        "version": 1,
        "question_set": row.question_set,
        "answers": answers,
        "harm_level": row.harm_level,
        "harm_code": row.harm_code,
        "scale_version": row.scale_version,
        "suggested": evaluation["suggested"],
        "conclusion": conclusion,
        "report_type": evaluation["report_type"],
        "due_on": clock["due_date"] if clock else None,
        "starter_mark": STARTER_MARK,
        "practice_label": markets.PRACTICE_LABEL,
        "sample": True,
    }
    content_fingerprint = fingerprint(material)
    record = SignedApprovalRecord(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        object_type=OBJECT_TYPE,
        object_id=row.id,
        object_version="1",
        decision_type=DECISION_TYPE,
        decision=SIGNATURE_CODES[conclusion],
        remarks="Sample: a finished example signed by the MDARIX sample author",
        signer_user_id=author_id,
        signer_role=SAMPLE_AUTHOR_ROLE,
        signature_meaning=markets.signature_meaning(ref, market, row.question_set, conclusion),
        content_fingerprint=content_fingerprint,
        signature_hash=signature_hash(content_fingerprint, author_id, "1"),
        status="SIGNED",
        signed_at=signed_at,
        created_at=signed_at,
    )
    db.add(record)
    row.conclusion = conclusion
    row.signed_record_id, row.content_fingerprint = record.id, content_fingerprint
    row.signed_by, row.signed_at = author_id, signed_at
    db.add(row)


def stage_sample_assessments(db: Session, tenant_id, now: datetime | None = None) -> dict:
    """Add the sample answers (see the module docstring). ``{"created": False, ...}`` when the sample story's
    complaints are missing or the sample answers are there already."""
    from backend.app.reportability import markets
    from backend.app.signer_training import service as training
    from backend.app.trial.sample_decision import sample_author

    now = now or datetime.now(timezone.utc)
    if has_sample_assessments(db, tenant_id):
        return {"created": False, "why": "ALREADY_STAGED"}
    found = _complaints(db, tenant_id)
    if not {"SAMPLE-RV-07", "SAMPLE-RV-08"} <= set(found):
        return {"created": False, "why": "NO_STORY_COMPLAINTS"}
    severities = 0
    for identifier, severity in SAMPLE_SEVERITY.items():
        complaint = found.get(identifier)
        if complaint is not None and not complaint.severity:
            complaint.severity = severity
            severities += 1
    savepoint = db.begin_nested()
    try:
        author = sample_author(db, tenant_id, now)
        author_id = str(author.id)
        signed_at = now - timedelta(minutes=20)
        for document in (*training.for_market(markets.EU_NI), *training.for_market(markets.CA)):
            training.acknowledge(
                db,
                tenant_id,
                author_id,
                document,
                signed_at - timedelta(minutes=5),
                trial=True,
                source_system=SAMPLE_SOURCE,
            )
        for market, answers, conclusion in (
            (markets.EU_NI, EU_EXAMPLE, markets.REPORTABLE),
            (markets.CA, CA_EXAMPLE, markets.NOT_REPORTABLE),
        ):
            _sign(db, tenant_id, found["SAMPLE-RV-07"], market, answers, conclusion, author_id, signed_at)
        us, _, _ = _row(db, tenant_id, found["SAMPLE-RV-08"], markets.US, US_PENDING, None, None, author_id, now)
        db.add(us)
        db.flush()
        savepoint.commit()
    except Exception:
        savepoint.rollback()
        logger.exception("Trial sample assessments could not be staged")
        return {"created": False, "why": "ERROR", "severities": severities}
    return {"created": True, "signed": 2, "saved": 1, "severities": severities}


def has_canada_example(db: Session, tenant_id) -> bool:
    from backend.app.db.models.market_assessment import ComplaintMarketAssessment
    from backend.app.reportability import markets

    return (
        db.query(ComplaintMarketAssessment.id)
        .filter(
            ComplaintMarketAssessment.tenant_id == tenant_id,
            ComplaintMarketAssessment.source_system == SAMPLE_SOURCE,
            ComplaintMarketAssessment.market == markets.CA,
        )
        .first()
        is not None
    )


def stage_canada_example(db: Session, tenant_id, now: datetime | None = None) -> dict:
    """The signed Canada example on SAMPLE-RV-07 alone, for a trial whose sample answers were staged before it existed
    (review B, G6): the sample author's Canada practice training and the assessment, as ``stage_sample_assessments``
    writes them. ``{"created": False, ...}`` when it is there already or RV-07 is missing; a trial user's own Canada
    assessment of RV-07 is left as it is."""
    from backend.app.db.models.market_assessment import ComplaintMarketAssessment
    from backend.app.reportability import markets
    from backend.app.signer_training import service as training
    from backend.app.trial.sample_decision import sample_author

    now = now or datetime.now(timezone.utc)
    if has_canada_example(db, tenant_id):
        return {"created": False, "why": "ALREADY_STAGED"}
    complaint = _complaints(db, tenant_id).get("SAMPLE-RV-07")
    if complaint is None:
        return {"created": False, "why": "NO_STORY_COMPLAINTS"}
    taken = (
        db.query(ComplaintMarketAssessment.id)
        .filter(
            ComplaintMarketAssessment.tenant_id == tenant_id,
            ComplaintMarketAssessment.complaint_id == complaint.id,
            ComplaintMarketAssessment.market == markets.CA,
        )
        .first()
    )
    if taken is not None:
        return {"created": False, "why": "ASSESSED_BY_A_PERSON"}
    savepoint = db.begin_nested()
    try:
        author_id = str(sample_author(db, tenant_id, now).id)
        signed_at = now - timedelta(minutes=20)
        for document in training.for_market(markets.CA):
            training.acknowledge(
                db,
                tenant_id,
                author_id,
                document,
                signed_at - timedelta(minutes=5),
                trial=True,
                source_system=SAMPLE_SOURCE,
            )
        _sign(db, tenant_id, complaint, markets.CA, CA_EXAMPLE, markets.NOT_REPORTABLE, author_id, signed_at)
        db.flush()
        savepoint.commit()
    except Exception:
        savepoint.rollback()
        logger.exception("Trial sample Canada example could not be staged")
        return {"created": False, "why": "ERROR"}
    return {"created": True, "signed": 1}
