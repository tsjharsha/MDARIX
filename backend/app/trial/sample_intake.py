"""The sample's first contacts, urgent intake and triage (T-SAM for 0.10.57: T-G32, T-G19, T-G20).

| Reference | Product | What the desk heard | Shows |
|---|---|---|---|
| SAMPLE-CALL-01 | PulseWatch 410 | A clinic asks for a copy of the instructions for use; nothing wrong | Service only, signed; in the QA review |
| SAMPLE-CALL-02 | VentraLink 250 Rev B, lot 4 | The controller switched off on battery during a patient transfer; battery to replace | Both, signed nine days ago, its QMS complaint never linked; with SAMPLE-RT-05 a likely duplicate |
| SAMPLE-CALL-03 | PulseWatch 410 | A loan monitor asked for; theirs taken out of use, reason and harm unknown ("pt") | Pending, flagged at once, a follow-up |
| SAMPLE-CALL-04 | OrbitCare 300 | A caller says the pump works and nothing went wrong; the call ends | Pending: confirm no deficiency |
| SAMPLE-URG-01 | OrbitCare 300 Rev B, lot 3 | Free flow at set-up; the patient moved to ICU; no awareness time yet | Urgent intake: triage at once, awareness unresolved, provisional deadlines from first knowledge |

SAMPLE-CALL-02 and SAMPLE-RT-05 (sample_dispositions.py) are the same occurrence: the hospital's service desk called
nine days ago; its formal complaint reached the QMS a month after the event (awareness one day ago). They share the
product, lot 4, the event day and the country, so the duplicate warning shows; linking them gives the earlier
awareness and recomputes RT-05's deadlines, with "awareness conflict" on the triage list. The quarantined sample row
SAMPLE-RJ-02 (sample_imports.py) reaches the triage list by its harm word.

SAMPLE-CASE-11 (0.10.93, B2 spec 4.8) is the hospital's call behind the flagship SAMPLE-RV-11: the same product,
version, lot, country and event day, received when RV-11's awareness starts. Its check is pre-filled and unsigned
(question 6 Unknown is the one left for the person; the suggestion is "Complaint and service"): Getting started's
steps 1 and 2 are done on it. No task is raised for it, so day 0 stays calm. The calls keep their SAMPLE-CALL
references (spec 9.3's re-seed as SAMPLE-CASE-01..04 was not done: the released tests and the RT-05 example read them).

No complaint, product or lot is added: every count quoted elsewhere stays (the second look, the backlog, the
reportability watch, the dispositions and the signals read complaints only). Every row is marked ``MDARIX_SAMPLE``
(the intake events, checks, triage records), so sample removal takes it, with its tasks. Idempotent; flushes but never
commits (the caller owns the transaction).
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from backend.app.trial.sample_data import SAMPLE_SOURCE

logger = logging.getLogger("mdarix.trial.sample_intake")

MARKER = "SAMPLE-CALL-01"
RT05_EVENT_DAYS = 33  # sample_dispositions.LATE_EVENT_DAYS["SAMPLE-RT-05"]
STORY_CASE = "SAMPLE-CASE-11"
# "More cases to try" on Getting started (spec 4.8), in order; each is shown with its own outcome as the record says.
MORE_CASES = ("SAMPLE-CALL-01", "SAMPLE-CALL-03", "SAMPLE-CALL-04", "SAMPLE-URG-01")
STORY_CASE_WORDS = (
    "Biomedical engineering at a sample hospital called the service desk: they checked a PulseWatch 410 against a "
    "reference oximeter and its SpO2 read 4 to 6 points high on two patients. No harm was reported. The monitor is "
    "out of use and they want it serviced."
)
# Spec 4.8: Q6 Unknown is the one question left for the person.
STORY_CASE_ANSWERS = dict(Q1="YES", Q2="YES", Q3="YES", Q4="NO", Q5="NO", Q6="UNKNOWN", Q7="NO", Q8="YES", Q9="NO")


def _answers(**given) -> dict:
    from backend.app.intake import rules

    return rules.clean_answers({question: {"answer": answer} for question, answer in given.items()})


def _contacts(now: datetime) -> list[dict]:
    """The sample's four contacts and the urgent intake, with their times."""
    return [
        {
            "reference": "SAMPLE-CALL-01",
            "kind": "CONTACT",
            "product": "SAMPLE-PULSE-410",
            "words": "The biomedical engineering lead at a sample clinic asked for a copy of the current PulseWatch 410 "
            "instructions for use, for their training file. Nothing was wrong with their monitors.",
            "reporter_type": "Clinic",
            "site": "Sample City Clinic (Sample)",
            "country": "US",
            "requested": "INFORMATION",
            "environment": "CLINIC",
            "user": "HEALTHCARE_PROFESSIONAL",
            "received": now - timedelta(days=3, hours=2),
            "answers": _answers(Q1="NO", Q2="NO", Q3="NO", Q4="NO", Q5="NO", Q6="NO", Q7="YES", Q8="NO", Q9="NO"),
            "signed": (
                "SERVICE_ONLY",
                "Information request only: a copy of the instructions for use. No fault and no harm alleged.",
            ),
        },
        {
            "reference": "SAMPLE-CALL-02",
            "kind": "CONTACT",
            "product": "SAMPLE-VENTRA-250",
            "lot": "SAMPLE-VENTRA-250-LOT-004",
            "words": "Biomedical engineer at a sample hospital called the service desk: a VentraLink 250 switched itself "
            "off on battery while a patient was being moved, although the battery showed full. Staff ventilated the "
            "patient by hand. They want the battery pack checked and replaced.",
            "reporter_type": "Hospital",
            "site": "Sample Klinikum Nord (Sample)",
            "country": "Germany",
            "requested": "REPAIR",
            "environment": "AMBULANCE",
            "user": "HEALTHCARE_PROFESSIONAL",
            "event": now - timedelta(days=RT05_EVENT_DAYS),
            "received": now - timedelta(days=9),
            "answers": _answers(Q1="YES", Q2="NO", Q3="YES", Q4="YES", Q5="NO", Q6="YES", Q7="NO", Q8="YES", Q9="NO"),
            "signed": ("BOTH", None),
            "ticket": "SVC-DE-0412",
            "triaged": True,
        },
        {
            "reference": "SAMPLE-CALL-03",
            "kind": "CONTACT",
            "product": "SAMPLE-PULSE-410",
            "words": "Ward sister asked for a loan monitor today. Night staff took their PulseWatch 410 out of use; she "
            "does not know why, or whether the pt was affected.",
            "reporter_type": "Hospital",
            "site": "Sample General Hospital (Sample)",
            "country": "GB",
            "requested": "REPAIR",
            "environment": "HOSPITAL_WARD",
            "user": "HEALTHCARE_PROFESSIONAL",
            "received": now - timedelta(hours=2),
            "answers": _answers(
                Q1="UNKNOWN",
                Q2="UNKNOWN",
                Q3="UNKNOWN",
                Q4="UNKNOWN",
                Q5="UNKNOWN",
                Q6="UNKNOWN",
                Q7="NO",
                Q8="UNKNOWN",
                Q9="UNKNOWN",
            ),
            "unknowns": "Why the monitor was taken out of use, and how the patient was.",
        },
        {
            "reference": "SAMPLE-CALL-04",
            "kind": "CONTACT",
            "product": "SAMPLE-ORBIT-300",
            "words": "The ward manager of a sample care home called about an OrbitCare 300 coming back from loan. She "
            "said it works and nothing went wrong; the call ended before she said what she needed.",
            "reporter_type": "Care home",
            "site": "Sample Care Home (Sample)",
            "country": "US",
            "requested": "NONE",
            "environment": "HOME",
            "user": "UNKNOWN",
            "received": now - timedelta(hours=5),
            "answers": _answers(Q1="NO", Q2="NO", Q3="NO", Q4="NO", Q5="NO", Q6="NO", Q7="NO", Q8="NO", Q9="NO"),
        },
        {
            "reference": "SAMPLE-URG-01",
            "kind": "URGENT",
            "product": "SAMPLE-ORBIT-300",
            "lot": "SAMPLE-ORBIT-300-LOT-003",
            "words": "Distributor service engineer on site: the OrbitCare 300 free-flowed during set-up after the door "
            "was opened. The pt was moved to ICU for monitoring. Pump taken out of use and kept for return.",
            "reporter_type": "Distributor",
            "site": "Sample Distributor US (Sample)",
            "country": "US",
            "requested": "REPAIR",
            "environment": "HOSPITAL_WARD",
            "user": "SERVICE_ENGINEER",
            "event": now - timedelta(hours=31),
            "first_knowledge": now - timedelta(hours=30),
            "received": now - timedelta(hours=2),
        },
    ]


def has_sample_intake(db: Session, tenant_id) -> bool:
    from backend.app.db.models.intake import IntakeEvent

    return (
        db.query(IntakeEvent.id).filter(IntakeEvent.tenant_id == tenant_id, IntakeEvent.reference == MARKER).first()
        is not None
    )


def stage_sample_intake(db: Session, tenant_id, now: datetime | None = None) -> dict:
    """Add the sample's contacts, urgent intake, their checks, tasks and one finished triage record (once)."""
    from backend.app.db.models.foundation import LotBatch, Product, SignedApprovalRecord
    from backend.app.db.models.intake import FirstContactCheck, IntakeEvent, TriageRecord
    from backend.app.human_decision.rules import fingerprint, signature_hash
    from backend.app.intake import rules, service
    from backend.app.reportability import markets
    from backend.app.standards import STARTER_MARK
    from backend.app.trial.sample_decision import SAMPLE_AUTHOR_ROLE, sample_author

    now = now or datetime.now(timezone.utc)
    if has_sample_intake(db, tenant_id):
        return {"created": False, "why": "ALREADY_STAGED"}
    products = {
        row.product_identifier: row
        for row in db.query(Product).filter(Product.tenant_id == tenant_id, Product.source_system == SAMPLE_SOURCE)
    }
    if not {"SAMPLE-VENTRA-250", "SAMPLE-PULSE-410", "SAMPLE-ORBIT-300"} <= set(products):
        return {"created": False, "why": "NO_SAMPLE_PRODUCTS"}
    lots = {
        row.lot_identifier: row
        for row in db.query(LotBatch).filter(LotBatch.tenant_id == tenant_id, LotBatch.source_system == SAMPLE_SOURCE)
    }
    savepoint = db.begin_nested()
    try:
        author = str(sample_author(db, tenant_id, now).id)
        counts = {"contacts": 0, "urgent": 0, "signed": 0, "triage_records": 0}
        for item in _contacts(now):
            lot = lots.get(item.get("lot") or "")
            received = item["received"]
            event = IntakeEvent(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                reference=item["reference"],
                kind=item["kind"],
                reporter_words=item["words"],
                reporter_type=item["reporter_type"],
                reporter_site=item["site"],
                country=item["country"],
                product_id=products[item["product"]].id,
                product_version_id=lot.product_version_id if lot else None,
                lot_batch_id=lot.id if lot else None,
                requested=item["requested"],
                use_environment=item["environment"],
                user_type=item["user"],
                event_at=item.get("event"),
                event_zone="Europe/Berlin" if item["country"] == "Germany" else "UTC" if item.get("event") else None,
                first_knowledge_at=item.get("first_knowledge"),
                first_knowledge_zone="America/Chicago" if item.get("first_knowledge") else None,
                first_knowledge_party="DISTRIBUTOR" if item.get("first_knowledge") else None,
                received_at=received,
                received_zone="UTC",
                awareness_at=received if item["kind"] == "CONTACT" else None,
                awareness_zone="UTC" if item["kind"] == "CONTACT" else None,
                service_ticket=item.get("ticket"),
                source_system=SAMPLE_SOURCE,
                created_by=author,
                created_at=received,
                updated_at=received,
            )
            db.add(event)
            db.flush()
            if item["kind"] == "URGENT":
                counts["urgent"] += 1
                service.ensure_qms_task(db, tenant_id, event, author, received)
                _queue(db, tenant_id, event, service.QMS)
                continue
            counts["contacts"] += 1
            answers = item["answers"]
            suggestion = rules.outcome(answers)
            check = FirstContactCheck(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                intake_event_id=event.id,
                version=1,
                guide_version=rules.GUIDE_VERSION,
                answers=answers,
                unknowns=item.get("unknowns"),
                suggestion=suggestion,
                source_system=SAMPLE_SOURCE,
                created_by=author,
                created_at=received,
                updated_at=received,
            )
            db.add(check)
            db.flush()
            signed = item.get("signed")
            if signed is None:
                service.ensure_follow_up(db, tenant_id, event, answers, suggestion, author, received)
                _queue(db, tenant_id, event, service.FOLLOW_UP)
                continue
            classification, reason = signed
            signed_at = received + timedelta(minutes=20)
            material = {
                "event": event.reference,
                "version": 1,
                "guide_version": rules.GUIDE_VERSION,
                "answers": answers,
                "suggestion": suggestion,
                "classification": classification,
                "reason": reason,
                "awareness_at": received.isoformat(),
                "starter_mark": STARTER_MARK,
                "practice_label": markets.PRACTICE_LABEL,
                "sample": True,
            }
            content = fingerprint(material)
            record_id = uuid.uuid4()
            db.add(
                SignedApprovalRecord(
                    id=record_id,
                    tenant_id=tenant_id,
                    object_type="FirstContactCheck",
                    object_id=check.id,
                    object_version="1",
                    decision_type="FIRST_CONTACT_CHECK",
                    decision=classification,
                    remarks="Sample: a finished example signed by the MDARIX sample author",
                    signer_user_id=author,
                    signer_role=SAMPLE_AUTHOR_ROLE,
                    signature_meaning=f"I have checked first contact {event.reference} with guide "
                    f"{rules.GUIDE_VERSION} and classify it: {rules.OUTCOME_LABELS[classification].lower()}.",
                    content_fingerprint=content,
                    signature_hash=signature_hash(content, author, "1"),
                    status="SIGNED",
                    signed_at=signed_at,
                    created_at=signed_at,
                )
            )
            check.classification, check.reason = classification, reason
            check.signed_record_id, check.content_fingerprint = record_id, content
            check.signed_by, check.signed_at, check.updated_at = author, signed_at, signed_at
            counts["signed"] += 1
            if classification == rules.SERVICE_ONLY:
                service.ensure_review_task(db, tenant_id, event, check, author, signed_at)
            else:
                service.ensure_qms_task(db, tenant_id, event, author, signed_at)
                _queue(db, tenant_id, event, service.QMS)
            if item.get("triaged"):
                db.add(
                    TriageRecord(
                        tenant_id=tenant_id,
                        subject_kind=service.INTAKE,
                        subject_id=event.id,
                        opened_at=received,
                        target_hours=rules.TRIAGE_TARGET_HOURS,
                        severity=markets.SERIOUS,
                        event_owner=author,
                        triage_owner=author,
                        immediate_action="Battery pack replaced on site; the removed pack kept for evaluation.",
                        completed_by=author,
                        completed_at=received + timedelta(hours=3),
                        source_system=SAMPLE_SOURCE,
                        created_by=author,
                        created_at=received,
                        updated_at=received + timedelta(hours=3),
                    )
                )
                counts["triage_records"] += 1
        db.flush()
        counts["story_case"] = stage_story_case(db, tenant_id, author)
        savepoint.commit()
    except Exception:
        savepoint.rollback()
        logger.exception("Trial sample intake could not be staged")
        return {"created": False, "why": "ERROR"}
    return {"created": True, **counts}


def has_story_case(db: Session, tenant_id) -> bool:
    from backend.app.db.models.intake import IntakeEvent

    return (
        db.query(IntakeEvent.id).filter(IntakeEvent.tenant_id == tenant_id, IntakeEvent.reference == STORY_CASE).first()
        is not None
    )


def stage_story_case(db: Session, tenant_id, author: str | None = None) -> int:
    """SAMPLE-CASE-11, unsigned, from the flagship's own facts (once; nothing without the flagship). Flushes; returns
    1 when added, else 0."""
    from backend.app.db.models.foundation import Complaint
    from backend.app.db.models.intake import FirstContactCheck, IntakeEvent
    from backend.app.intake import case_rules
    from backend.app.trial.sample_data import FLAGSHIP, FLAGSHIP_SERVICE
    from backend.app.trial.sample_decision import sample_author

    flagship = (
        db.query(Complaint)
        .filter(
            Complaint.tenant_id == tenant_id,
            Complaint.source_system == SAMPLE_SOURCE,
            Complaint.complaint_identifier == FLAGSHIP,
        )
        .first()
    )
    if flagship is None or has_story_case(db, tenant_id):
        return 0
    received = flagship.awareness_timestamp
    author = author or str(sample_author(db, tenant_id, received).id)
    event = IntakeEvent(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        reference=STORY_CASE,
        kind="CONTACT",
        reporter_words=STORY_CASE_WORDS,
        reporter_type="Hospital",
        reporter_site="Sample Lakeside Hospital (Sample)",
        country=flagship.country,
        product_id=flagship.product_id,
        product_version_id=flagship.product_version_id,
        lot_batch_id=flagship.lot_batch_id,
        requested="REPAIR",
        use_environment="HOSPITAL_WARD",
        user_type="HEALTHCARE_PROFESSIONAL",
        channel="PHONE",
        event_at=flagship.event_timestamp,
        event_zone="UTC",
        received_at=received,
        received_zone="UTC",
        awareness_at=received,
        awareness_zone="UTC",
        service_ticket=FLAGSHIP_SERVICE["service_reference"],
        source_system=SAMPLE_SOURCE,
        created_by=author,
        created_at=received,
        updated_at=received,
    )
    db.add(event)
    db.flush()
    answers = case_rules.clean_answers({question: {"answer": value} for question, value in STORY_CASE_ANSWERS.items()})
    db.add(
        FirstContactCheck(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            intake_event_id=event.id,
            version=1,
            guide_version=case_rules.GUIDE_VERSION,
            answers=answers,
            suggestion=case_rules.case_outcome(answers, event.requested),
            source_system=SAMPLE_SOURCE,
            created_by=author,
            created_at=received,
            updated_at=received,
        )
    )
    db.flush()
    return 1


def _queue(db: Session, tenant_id, event, task_type: str) -> None:
    """The sample author's task goes to its role queue, so the trial's own people see it in My Work."""
    from backend.app.db.models.workflow import WorkflowTask
    from backend.app.workflow.labels import task_type as definition

    for task in db.query(WorkflowTask).filter(
        WorkflowTask.tenant_id == tenant_id,
        WorkflowTask.source_entity_id == event.id,
        WorkflowTask.task_type == task_type,
    ):
        task.assigned_user_id, task.assigned_role, task.status = None, definition(task_type).queue_role, "NEW"
