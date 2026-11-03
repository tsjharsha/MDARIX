"""The sample's own decision guide versions and communications log (T-G15, T-G30; T-SAM for 0.10.59).

- **A customer version of the US guide:** US-v2 (fictional, clearly sample), prepared by the sample author from the
  starter: the three serious-injury parts keep MDARIX's locked wording and carry the organization's own explanation
  beside it (part (c) also its examples), and an extra question asks whether the organization takes part in FDA's VMSR
  program (21 CFR 803.19), with its clause and basis. Its test cases
  (the starter's) pass; the sample approver (the second sample account of 0.10.58) approved it, so it is the US guide
  in use. Assessments started from then on use it; the RV-08 draft, started before, keeps US-starter-1.
- **A draft US-v3** whose test matrix has one worked complaint of the organization's own that fails ("outcome
  unknown: expected not reportable", while Unknown is never No): it cannot be sent for approval.
- **The communications log:** on SAMPLE-RV-08 (outcome not known) a request to the reporter for the patient's outcome,
  raised by its Unknown answers, with two unanswered attempts and its reply overdue; on SAMPLE-RV-03 a distributor's
  question answered (the reply recorded, its QMS record linked by ID); on SAMPLE-RV-01 a request to the hospital's
  biomedical team that went unanswered after three attempts to each contact: "unresolved after attempts".

The open request is owned by the trial's first user when there is one (so it shows in their My Work), else by the
sample author. Every row is marked ``MDARIX_SAMPLE``; sample removal takes it and everything done with it (the tasks,
the signature). No complaint is added: the sample's counts stay. Idempotent; flushes but never commits.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from backend.app.trial.sample_data import SAMPLE_SOURCE

logger = logging.getLogger("mdarix.trial.sample_guides")

INJURY_HELP = (
    "Our procedure (sample QP-08): permanent means it does not heal by itself or with treatment. An injury that "
    "needed treatment to prevent permanent damage is part (c), even if the patient recovered."
)
VMSR_QUESTION = {
    "id": "",
    "text": "Does our organization take part in FDA's Voluntary Malfunction Summary Reporting (VMSR) program for this "
    "device's product code?",
    "definition": "Under VMSR, eligible malfunction reports may be sent quarterly in summary form. Record the answer "
    "and the product code: the reporting route is chosen when the report is prepared. This answer never changes the "
    "conclusion.",
    "note": "Sample: check the product code against FDA's VMSR list.",
    "clause": "21 CFR 803.19 (VMSR program)",
    "basis": ["CFR803_19"],
}
# Shown after "Your examples:" (0.10.72: it read "Your examples: Sample examples: …"); the guide is the sample's.
INJURY_EXAMPLES = (
    "A cut closed with sutures to prevent permanent scarring is part (c); a bruise that healed without treatment is "
    "not."
)
V2_REASON = (
    "Sample: our own help text on the three serious-injury parts (procedure QP-08), and the VMSR question our "
    "reporting procedure asks."
)
FAILING_TEST = {
    "name": "Our test: outcome unknown, malfunction not likely to harm: expected not reportable",
    "answers": {
        "US1": "NO",
        "US2A": "NO",
        "US2B": "UNKNOWN",
        "US2C": "NO",
        "US3": "YES",
        "US4": "YES",
        "US5": "NO",
        "US6": "NO",
    },
    "expected": "NOT_REPORTABLE",
    "expected_report_type": None,
}


# The sample's open request to RV-08's reporter, in words (0.10.66, J18: it named the US questions by code).
RV08_REQUEST = (
    "Ask the reporter: the patient's outcome after the free flow (four US questions on harm are Unknown in the US "
    "assessment)"
)
RV08_REQUEST_BEFORE = (
    "Ask the reporter: the patient's outcome after the free flow (US2A, US2B, US2C and US3 are Unknown in the US "
    "assessment)"
)


def has_sample_guides(db: Session, tenant_id) -> bool:
    from backend.app.db.models.guides_communications import DecisionGuideVersion

    return (
        db.query(DecisionGuideVersion.id)
        .filter(DecisionGuideVersion.tenant_id == tenant_id, DecisionGuideVersion.source_system == SAMPLE_SOURCE)
        .first()
        is not None
    )


def trial_owner(db: Session, tenant_id) -> str | None:
    """The trial's first person (not a sample account), who owns the sample's open request."""
    from backend.app.db.models.foundation import AuthUser
    from backend.app.trial.sample_decision import is_sample_author

    for user in (
        db.query(AuthUser)
        .filter(AuthUser.tenant_id == tenant_id, AuthUser.status.in_(("ACTIVE", "INVITED")))
        .order_by(AuthUser.created_at)
    ):
        if not is_sample_author(user):
            return str(user.id)
    return None


def _guides(db, tenant_id, author: str, approver: str, now: datetime) -> dict:
    from backend.app.db.models.foundation import SignedApprovalRecord
    from backend.app.decision_guides import router, rules
    from backend.app.human_decision.rules import signature_hash
    from backend.app.reportability import markets

    us = markets.US
    made = now - timedelta(days=5)
    v2 = router.start_draft(db, tenant_id, us, author, made, SAMPLE_SOURCE)
    questions = [
        {**item, "explanation": INJURY_HELP, "examples": INJURY_EXAMPLES if item["id"] == "US2C" else ""}
        if item["id"] in ("US2A", "US2B", "US2C")
        else item
        for item in v2.questions
    ]
    questions, problem = rules.clean_questions(us, [*questions, VMSR_QUESTION])
    assert problem is None, problem
    router.save(db, v2, questions, v2.test_cases, author, made + timedelta(hours=1))
    router.run_tests(db, v2, author, made + timedelta(hours=2))
    router.request_approval(db, v2, V2_REASON, author, made + timedelta(hours=3))
    approved = made + timedelta(days=1)
    title = rules.build(us, v2.code, v2.questions).title
    record = SignedApprovalRecord(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        object_type=router.OBJECT_TYPE,
        object_id=v2.id,
        object_version=v2.code,
        decision_type=router.DECISION_TYPE,
        decision="APPROVED",
        remarks="Sample: approved by the MDARIX sample approver",
        signer_user_id=approver,
        signer_role="Sample approver",
        signature_meaning=rules.signature_meaning(v2.code, title),
        content_fingerprint=v2.content_fingerprint,
        signature_hash=signature_hash(v2.content_fingerprint, approver, v2.code),
        status="SIGNED",
        signed_at=approved,
        created_at=approved,
    )
    db.add(record)
    db.flush()
    router.publish(db, v2, approver, record.id, approved)
    started = now - timedelta(days=1)
    v3 = router.start_draft(db, tenant_id, us, author, started, SAMPLE_SOURCE)
    tests, problem = rules.clean_tests(us, [*v3.test_cases, FAILING_TEST])
    assert problem is None, problem
    router.save(db, v3, v3.questions, tests, author, started + timedelta(hours=1))
    results = router.run_tests(db, v3, author, started + timedelta(hours=2))
    return {"published": v2.code, "draft": v3.code, "draft_failing": results["failed"]}


def relock_sample_drafts(db: Session, tenant_id, apply: bool) -> int:
    """0.10.64: a sample guide version being prepared, seeded before the core wording was locked, takes MDARIX's wording
    back (its help text becomes its explanation) and MDARIX's starter worked complaints, and its matrix is run again,
    so it fails only on its own worked complaint as in a new trial. Returns how many changed (or would); idempotent."""
    from backend.app.db.models.guides_communications import DecisionGuideVersion
    from backend.app.decision_guides import router, rules

    changed = 0
    for row in db.query(DecisionGuideVersion).filter(
        DecisionGuideVersion.tenant_id == tenant_id,
        DecisionGuideVersion.source_system == SAMPLE_SOURCE,
        DecisionGuideVersion.state.in_(rules.OPEN_STATES),
    ):
        questions = rules.relocked(row.market, row.questions or [])
        tests, problem = rules.clean_tests(row.market, row.test_cases or [])
        if problem or (questions == row.questions and tests == row.test_cases):
            continue
        changed += 1
        if apply:
            router.save(db, row, questions, tests, row.updated_by or "system:trial-sample", row.updated_at)
            router.run_tests(db, row, row.updated_by or "system:trial-sample", row.updated_at)
    return changed


def _party(
    db, tenant_id, kind: str, name: str, author: str, at, complaint=None, primary=(None, None), second=(None, None)
):
    from backend.app.db.models.guides_communications import ExternalParty

    party = ExternalParty(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        party_type=kind,
        name=name,
        complaint_id=complaint.id if complaint is not None else None,
        primary_name=primary[0],
        primary_details=primary[1],
        second_name=second[0],
        second_details=second[1],
        source_system=SAMPLE_SOURCE,
        created_by=author,
        created_at=at,
        updated_by=author,
        updated_at=at,
    )
    db.add(party)
    db.flush()
    return party


def _communications(db, tenant_id, complaints: dict, author: str, owner: str, now: datetime) -> dict:
    from backend.app.communications import rules, service

    limit = service.attempts_limit(db, tenant_id)
    found = {}
    rv08 = complaints.get("SAMPLE-RV-08")
    if rv08 is not None:
        start = now - timedelta(days=6)
        reporter = _party(
            db,
            tenant_id,
            rules.REPORTER,
            "Reporter of SAMPLE-RV-08 (ward nurse, fictional)",
            author,
            start,
            rv08,
            ("Ward nurse (fictional)", "nurse.sample@hospital.invalid; +1 555 0100 (sample)"),
        )
        entry = service.record(
            db,
            tenant_id,
            complaint=rv08,
            party=reporter,
            direction=rules.SENT,
            purpose=rules.REQUEST,
            subject=RV08_REQUEST,
            channel="EMAIL",
            occurred_at=start,
            actor=author,
            now=start + timedelta(minutes=10),
            owner_id=owner,
            reply_due_on=(now - timedelta(days=3)).date(),
            origin={"type": service.ASSESSMENT, "market": "US", "questions": ["US2A", "US2B", "US2C", "US3"]},
            source_system=SAMPLE_SOURCE,
        )
        service.add_attempt(
            db,
            entry,
            reporter,
            at=now - timedelta(days=4),
            channel="PHONE",
            outcome="NO_ANSWER",
            note="Sample: called the ward; the nurse was off shift.",
            actor=author,
            now=now - timedelta(days=4) + timedelta(minutes=20),
            limit=limit,
        )
        found["reporter"] = entry.status
    rv03 = complaints.get("SAMPLE-RV-03")
    if rv03 is not None:
        asked = now - timedelta(days=10)
        distributor = _party(
            db,
            tenant_id,
            rules.DISTRIBUTOR,
            "MedSupply Partners (sample distributor)",
            author,
            asked,
            primary=("Asha Rao, quality contact (sample)", "quality@medsupply.invalid"),
            second=("Vikram Das, operations (sample)", "operations@medsupply.invalid"),
        )
        request = service.record(
            db,
            tenant_id,
            complaint=rv03,
            party=distributor,
            direction=rules.SENT,
            purpose=rules.REQUEST,
            subject="Ask the distributor whether other sites reported pressure alarms on OrbitCare 300 Rev B pumps",
            channel="EMAIL",
            occurred_at=asked,
            actor=author,
            now=asked - timedelta(minutes=5),
            owner_id=author,
            reply_due_on=(asked + timedelta(days=3)).date(),
            source_system=SAMPLE_SOURCE,
        )
        answered = asked + timedelta(days=2)
        reply = service.record(
            db,
            tenant_id,
            complaint=rv03,
            party=distributor,
            direction=rules.RECEIVED,
            purpose=rules.RESPONSE,
            subject="Two other sites reported intermittent pressure alarms on Rev B; 14 units of lot 3 held and "
            "quarantined",
            channel="EMAIL",
            occurred_at=answered,
            actor=author,
            now=answered + timedelta(minutes=30),
            evidence=["Distributor's e-mail (sample)", "Site list (sample spreadsheet)"],
            qms_reference="SAMPLE-QMS-COMM-0042",
            in_reply_to=request.id,
            source_system=SAMPLE_SOURCE,
        )
        service.close(db, request, rules.ANSWERED, reply.subject, author, answered + timedelta(minutes=30))
        found["distributor"] = request.status
    rv01 = complaints.get("SAMPLE-RV-01")
    if rv01 is not None:
        asked = now - timedelta(days=20)
        hospital = _party(
            db,
            tenant_id,
            rules.HOSPITAL,
            "St. Sample General Hospital, biomedical engineering (sample)",
            author,
            asked,
            primary=("Biomedical engineering desk (sample)", "biomed@stsample.invalid"),
            second=("Head of biomedical engineering (sample)", "biomed.head@stsample.invalid; +1 555 0199 (sample)"),
        )
        entry = service.record(
            db,
            tenant_id,
            complaint=rv01,
            party=hospital,
            direction=rules.SENT,
            purpose=rules.REQUEST,
            subject="Ask the hospital for the monitor and its alarm log from the night of the event",
            channel="EMAIL",
            occurred_at=asked,
            actor=author,
            now=asked + timedelta(minutes=15),
            owner_id=author,
            reply_due_on=(asked + timedelta(days=5)).date(),
            source_system=SAMPLE_SOURCE,
        )
        # Two more to the desk (three in all), then three to the head of department: unresolved after attempts. One
        # call was logged the next day: it counts as done outside MDARIX (S4).
        for days, channel, outcome, late in (
            (3, "EMAIL", "SENT", False),
            (6, "PHONE", "NO_ANSWER", False),
            (8, "EMAIL", "SENT", False),
            (10, "PHONE", "NO_ANSWER", True),
            (12, "PHONE", "MESSAGE_LEFT", False),
        ):
            at = asked + timedelta(days=days)
            service.add_attempt(
                db,
                entry,
                hospital,
                at=at,
                channel=channel,
                outcome=outcome,
                note=None,
                actor=author,
                now=at + (timedelta(days=1) if late else timedelta(minutes=30)),
                limit=limit,
            )
            if entry.status != rules.OPEN:
                break
        found["hospital"] = entry.status
    return found


def stage_sample_guides(db: Session, tenant_id, now: datetime | None = None, owner_id: str | None = None) -> dict:
    """Add the sample's guide versions and communications log (see the module docstring). ``{"created": False, ...}``
    when the sample story's complaints are missing or the examples are there already."""
    from backend.app.db.models.foundation import Complaint
    from backend.app.trial.sample_decision import sample_author
    from backend.app.trial.sample_reports import sample_approver

    now = now or datetime.now(timezone.utc)
    if has_sample_guides(db, tenant_id):
        return {"created": False, "why": "ALREADY_STAGED"}
    complaints = {
        row.complaint_identifier: row
        for row in db.query(Complaint).filter(
            Complaint.tenant_id == tenant_id,
            Complaint.source_system == SAMPLE_SOURCE,
            Complaint.complaint_identifier.in_(["SAMPLE-RV-01", "SAMPLE-RV-03", "SAMPLE-RV-08"]),
        )
    }
    if not complaints:
        return {"created": False, "why": "NO_STORY_COMPLAINTS"}
    savepoint = db.begin_nested()
    try:
        author = str(sample_author(db, tenant_id, now).id)
        approver = str(sample_approver(db, tenant_id, now).id)
        owner = owner_id or trial_owner(db, tenant_id) or author
        guides = _guides(db, tenant_id, author, approver, now)
        communications = _communications(db, tenant_id, complaints, author, owner, now)
        savepoint.commit()
    except Exception:
        savepoint.rollback()
        logger.exception("Trial sample guides and communications could not be staged")
        return {"created": False, "why": "ERROR"}
    return {"created": True, "guides": guides, "communications": communications}
