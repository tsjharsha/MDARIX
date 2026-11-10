"""The sample's report worksheets and submission records (T-G2c, T-G2b; T-SAM for 0.10.58).

- **A finished US example:** SAMPLE-RV-09 (PulseWatch 410, US, alarm too quiet, oxygen therapy needed) gets a signed
  US conclusion (reportable, the 30-day report) by the sample author, and its Form FDA 3500A worksheet goes the whole
  way: prepared by the sample author, the snapshot approved by the sample approver (a second sample account), the
  eMDR submission recorded on day 27 with the eSubmitter copy, and FDA's four acknowledgements as sample files (Ack3
  passed): accepted. Its filing settles the market on the reportability watch.
- **An India example with a rejected attempt:** a new complaint, SAMPLE-RV-10 (PulseWatch 410 Rev A, India, a probe
  that overheated and burned a finger, reported four weeks after the event), with a signed India conclusion (reportable, a serious adverse event) by the
  sample author, and its MvPI worksheet (MDAE form, Version 1.2): approved, sent by e-mail, bounced. The obligation is
  back in draft, "correction required", with its original deadline, waiting for a correction and a new approval.
- SAMPLE-RV-06 keeps waiting for the trial user: after its US conclusion is signed, its 3500A worksheet is drafted
  from the case; a colleague approves it or, working alone in the trial, the trial user (practice approval, 0.10.64).
- India is enabled in the sample's reporting windows (the India MDR 2017 window, starter text) when the windows are
  still the sample's; an organization's own windows are never changed.

The sample's patient and reporter fields are fictional (authority_reports/worksheet.py SAMPLE_PERSONAL). The sample
author and approver cannot sign in; their sample signatures rely on no practice acknowledgement, so neither is ever
offered as a trained colleague. Every row is marked ``MDARIX_SAMPLE``; sample removal takes it and everything done with
it. RV-10 is added after the sample's import run, so the run's counts stay as they were. Idempotent; flushes but never
commits (the caller owns the transaction).
"""

from __future__ import annotations

import hashlib
import logging
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from backend.app.trial.sample_data import SAMPLE_SOURCE, STORY_WINDOWS_BY, _stamp

logger = logging.getLogger("mdarix.trial.sample_reports")

INDIA_COMPLAINT = "SAMPLE-RV-10"
INDIA_DAYS = 8
INDIA_EVENT_DAYS = 35
INDIA_WINDOW = "India MDR 2017: serious adverse event (15 days)"
APPROVER_NAME = "MDARIX sample approver"


def _answer(answer: str, rationale: str) -> dict:
    return {"answer": answer, "rationale": rationale, "evidence": ["Complaint description"]}


US_EXAMPLE = {
    "US1": _answer("NO", "No death: the patient recovered on oxygen therapy."),
    "US2A": _answer("NO", "The desaturation was treated on the ward; not life-threatening per the ward's report."),
    "US2B": _answer("NO", "No lasting impairment reported after oxygen therapy."),
    "US2C": _answer("YES", "Oxygen therapy was needed to treat the desaturation found late."),
    "US3": _answer("YES", "The alarm was too quiet to hear, so the desaturation was found late."),
    "US4": _answer(
        "YES", "The alarm output was below what a busy ward needs to hear it: it did not perform as intended."
    ),
    "US5": _answer("YES", "Recurrence presumed: an alarm nobody hears can delay treatment again."),
    "US6": _answer("NO", "No remedial action decided to prevent an unreasonable risk to public health."),
}
IN_EXAMPLE = {
    "IN1": _answer(
        "YES", "The probe overheated at the finger sensor: the device is suspected to have caused the burn."
    ),
    "IN2A": _answer("NO", "No death."),
    "IN2B": _answer("NO", "A finger burn; not life-threatening."),
    "IN2C": _answer("NO", "The patient was already in hospital; the stay was not prolonged."),
    "IN2D": _answer("NO", "No persistent disability reported so far."),
    "IN2E": _answer("NOT_APPLICABLE", "An adult patient; no pregnancy involved."),
    "IN2F": _answer("YES", "The burn needed treatment by the ward doctor to prevent permanent skin damage."),
    "IN3": _answer("YES", "Overheating at the sensor is not among the risks in the labelling."),
}
# The fields the sample author entered by hand (values marked as samples). From 0.10.96 the US example is FDA-valid,
# so its approval freezes an eMDR file (XML, eSubmitter-layout PDF, official form): a practice report number (FDA's
# test sequences start with 7; CFN 0000000 is no real firm's), and B4 and G8 filled as Send for approval fills them.
US_ENTRIES = {
    "MFR_REPORT": "0000000-{year}-70001",
    # An FDA product code from the published list (0.10.81: a code field takes only a code; DQA: Oximeter).
    "D2A": "DQA",
    "G2": "Health professional",
    "G4": "SAMPLE-510K-0001 (sample)",
    # Without the IMDRF release and FDA's mapping loaded, the codes read as entered in eSubmitter (as before 0.10.96).
    "H6_CONCLUSIONS": "Entered in eSubmitter from the IMDRF Annex D release (sample)",
    # 0.10.77: an initial 3500A needs both health effect codes on the new navigation (forms.CODES_REQUIRED).
    "H6_CLINICAL": "Entered in eSubmitter from the IMDRF Annex E release (sample)",
    "H6_IMPACT": "Entered in eSubmitter from the IMDRF Annex F release (sample)",
}
# The IMDRF codes the sample author chose in the code picker (0.10.96), each with its FDA code from FDA's mapping:
# low oxygen saturation, an unexpected medical intervention (oxygen therapy), the audible alarm, the returned device
# tested, an alarm system problem found, a design inadequate for its purpose. H6_PROBLEM is the mapping's suggestion.
US_CODES = {
    "H6_CLINICAL": "E2203",
    "H6_IMPACT": "F23",
    "H6_COMPONENT": "G0600101",
    "H6_TYPE": "B01",
    "H6_FINDINGS": "C1202",
    "H6_CONCLUSIONS": "D0101",
}
# The US manufacturer the eMDR file names (G1 contact office, D3), with the e-mail FDA requires. It exists only while
# the sample's report is frozen (the file and its party parts stay in the approved snapshot), so the organization's own
# US responsible party, and the trial's "give the contact office's e-mail" step, stay the person's own.
US_PARTY = {
    "market": "US",
    "role": "MANUFACTURER",
    "organisation": "Orbit Medical Devices (Sample)",
    "address": "1 Sample Way, Springfield, US",
    "contact_email": "vigilance@orbit-sample.invalid",
}
IN_ENTRIES = {
    "P1": "{submitted}",
    "P4": "SAMPLE-MAH-2026-001 (sample)",
    "R1": "Manufacturer",
    "R3": "Orbit Medical Devices India (Sample), 1 Sample Road, Pune; vigilance office (sample)",
    "A_MANUFACTURER": "Orbit Medical Devices (Sample), Springfield, US",
    "A1": "Class B (sample)",
    "A3": "SAMPLE-MD-LICENCE-0001 (sample)",
    "E3": "Possible (sample)",
}


def _file(name: str, text: str) -> dict:
    data = text.encode()
    return {
        "file_name": name,
        "content_type": "text/plain",
        "size": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "content": data,
    }


def has_sample_reports(db: Session, tenant_id) -> bool:
    from backend.app.db.models.authority_reports import ReportObligation

    return (
        db.query(ReportObligation.id)
        .filter(ReportObligation.tenant_id == tenant_id, ReportObligation.source_system == SAMPLE_SOURCE)
        .first()
        is not None
    )


def sample_approver(db: Session, tenant_id: uuid.UUID, now: datetime):
    """The second sample account, which approves the sample's snapshots: it cannot sign in and holds no seat (its
    username starts as the sample author's does, so every list that leaves out the sample author leaves it out)."""
    import secrets

    from backend.app.db.models.foundation import AuthUser
    from backend.app.trial.sample_decision import SAMPLE_AUTHOR_ROLE
    from backend.app.trial.service import _hash

    email = f"sample-author+approver-{tenant_id.hex[:12]}@sample.invalid"
    user = db.query(AuthUser).filter(AuthUser.tenant_id == tenant_id, AuthUser.username == email).first()
    if user is not None:
        return user
    user = AuthUser(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        username=email,
        display_name=APPROVER_NAME,
        company="MDARIX sample data",
        password_hash=_hash(secrets.token_urlsafe(32)),
        role=SAMPLE_AUTHOR_ROLE,
        status="DISABLED",
        email_verified=False,
        created_at=now,
        updated_at=now,
    )
    db.add(user)
    db.flush()
    return user


def _india_window(db: Session, tenant_id, now: datetime) -> bool:
    """Enable India in the sample's reporting windows (only while the windows are the sample's own)."""
    from backend.app.db.models.reportability import ReportabilitySettings
    from backend.app.reportability.rules import TEMPLATES, clean_window

    settings = db.query(ReportabilitySettings).filter(ReportabilitySettings.tenant_id == tenant_id).first()
    if settings is None or settings.updated_by != STORY_WINDOWS_BY:
        return False
    if any(window.get("name") == INDIA_WINDOW for window in settings.windows or []):
        return False
    template = next(item for item in TEMPLATES if item["name"] == INDIA_WINDOW)
    settings.windows = [*(settings.windows or []), clean_window(template)]
    settings.version = (settings.version or 1) + 1
    settings.updated_at = now
    db.flush()
    return True


def _india_complaint(db: Session, tenant_id, now: datetime):
    from backend.app.db.models.foundation import Complaint, LotBatch, Product, ProductVersion

    found = (
        db.query(Complaint)
        .filter(Complaint.tenant_id == tenant_id, Complaint.complaint_identifier == INDIA_COMPLAINT)
        .first()
    )
    if found is not None:
        return found
    product = (
        db.query(Product)
        .filter(
            Product.tenant_id == tenant_id,
            Product.source_system == SAMPLE_SOURCE,
            Product.product_identifier == "SAMPLE-PULSE-410",
        )
        .first()
    )
    if product is None:
        return None
    version = (
        db.query(ProductVersion)
        .filter(
            ProductVersion.tenant_id == tenant_id,
            ProductVersion.product_id == product.id,
            ProductVersion.version_identifier == "Rev A",
        )
        .first()
    )
    lot = (
        db.query(LotBatch)
        .filter(LotBatch.tenant_id == tenant_id, LotBatch.product_version_id == version.id)
        .order_by(LotBatch.lot_identifier)
        .first()
        if version
        else None
    )
    aware = now - timedelta(days=INDIA_DAYS)
    complaint = Complaint(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        complaint_identifier=INDIA_COMPLAINT,
        product_id=product.id,
        product_version_id=version.id if version else None,
        lot_batch_id=lot.id if lot else None,
        # The hospital reported it weeks after the event: an old event, so PulseWatch Rev A gains no recent complaint
        # in the trend check's 30 days (OrbitCare stays the only rise).
        event_timestamp=now - timedelta(days=INDIA_EVENT_DAYS),
        complaint_timestamp=aware,
        awareness_timestamp=aware,
        description=(
            "SpO2 probe overheated at the finger sensor during overnight monitoring; the patient's finger had a burn "
            "that the ward doctor treated. The hospital reported it four weeks later and returned the probe."
        ),
        source_identifier=INDIA_COMPLAINT,
        status="open",
        problem_code="PROBE_OVERHEAT",
        country="India",
        patient_involved=True,
        serious_injury=True,
        death=False,
        malfunction=True,
        device_returned=True,
        severity="Serious",
        **_stamp(now, INDIA_DAYS),
    )
    db.add(complaint)
    db.flush()
    return complaint


def _signed(db, tenant_id, complaint, market, answers, level, term, author_id, signed_at):
    """A market conclusion signed by the sample author (as sample_assessments.py signs the EU example)."""
    from backend.app.db.models.foundation import SignedApprovalRecord
    from backend.app.human_decision.rules import fingerprint, signature_hash
    from backend.app.reportability import markets
    from backend.app.reportability.assessment_router import DECISION_TYPE, OBJECT_TYPE, SIGNATURE_CODES
    from backend.app.standards import STARTER_MARK
    from backend.app.trial.sample_assessments import _row
    from backend.app.trial.sample_decision import SAMPLE_AUTHOR_ROLE

    row, evaluation, clock = _row(db, tenant_id, complaint, market, answers, level, term, author_id, signed_at)
    ref = complaint.business_id or complaint.complaint_identifier
    material = {
        "complaint_id": str(complaint.id),
        "complaint": ref,
        "market": market,
        "version": 1,
        "question_set": row.question_set,
        "answers": answers,
        "harm_level": level,
        "harm_code": term,
        "scale_version": row.scale_version,
        "suggested": evaluation["suggested"],
        "conclusion": markets.REPORTABLE,
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
        decision=SIGNATURE_CODES[markets.REPORTABLE],
        remarks="Sample: a finished example signed by the MDARIX sample author",
        signer_user_id=author_id,
        signer_role=SAMPLE_AUTHOR_ROLE,
        signature_meaning=markets.signature_meaning(ref, market, row.question_set, markets.REPORTABLE),
        content_fingerprint=content_fingerprint,
        signature_hash=signature_hash(content_fingerprint, author_id, "1"),
        status="SIGNED",
        signed_at=signed_at,
        created_at=signed_at,
    )
    db.add(record)
    row.conclusion, row.signed_record_id, row.content_fingerprint = markets.REPORTABLE, record.id, content_fingerprint
    row.signed_by, row.signed_at = author_id, signed_at
    db.add(row)
    db.flush()
    return row


def _approve(db, obligation, snapshot, approver_id: str, at: datetime) -> None:
    from backend.app.authority_reports import router, rules
    from backend.app.db.models.foundation import SignedApprovalRecord
    from backend.app.human_decision.rules import signature_hash

    record = SignedApprovalRecord(
        id=uuid.uuid4(),
        tenant_id=obligation.tenant_id,
        object_type=router.OBJECT_TYPE,
        object_id=snapshot.id,
        object_version=str(snapshot.version),
        decision_type=router.DECISION_TYPE,
        decision="APPROVED",
        remarks="Sample: approved by the MDARIX sample approver",
        signer_user_id=approver_id,
        signer_role="Sample approver",
        signature_meaning=router.signature_meaning(
            router.forms.FORMS[obligation.form_code].title, snapshot.version, snapshot.fields["complaint"]
        ),
        content_fingerprint=snapshot.content_fingerprint,
        signature_hash=signature_hash(snapshot.content_fingerprint, approver_id, str(snapshot.version)),
        status="SIGNED",
        signed_at=at,
        created_at=at,
    )
    db.add(record)
    snapshot.state, snapshot.approved_by, snapshot.approved_at, snapshot.signed_record_id = (
        "APPROVED",
        approver_id,
        at,
        record.id,
    )
    obligation.state = rules.APPROVED
    db.flush()


def _entries(values: dict, author_id: str, at: datetime) -> dict:
    stamp = at.isoformat()
    return {
        key: {
            "value": value.replace("{submitted}", at.date().isoformat()).replace("{year}", str(at.year)),
            "by": author_id,
            "at": stamp,
        }
        for key, value in values.items()
    }


# The sample's G1 and D3 as typed before 0.10.96: used when the organization has its own US responsible party, which
# the sample never reads (its report then keeps no eMDR file; its PDF is the filled official form).
US_TYPED_PARTY = {
    "D3": "Orbit Medical Devices (Sample), Springfield, US",
    "G1": "Orbit Medical Devices (Sample), 1 Sample Way, Springfield, US; vigilance office (sample)",
}


def _coded(db, control_db, obligation, author_id: str, at: datetime) -> dict:
    """The US example's IMDRF codes as the code picker writes them (term and FDA code); none without the release."""
    from fastapi import HTTPException

    from backend.app.authority_reports import router

    fields = {field.id: field for field in router._form(obligation).fields()}
    try:
        return {
            key: {
                **router._code_entry(
                    db, control_db, obligation, fields[key], router.FieldRequest(codes=[code]), author_id
                ),
                "at": at.isoformat(),
            }
            for key, code in US_CODES.items()
        }
    except HTTPException:
        return {}


def _freeze_us(db, control_db, obligation, author_id: str, at: datetime):
    """Freeze the US example for approval, its eMDR file built from the sample's US manufacturer (``US_PARTY``),
    which is there only for this; the organization's own party, when it has one, is never read or changed."""
    from backend.app.authority_reports import router
    from backend.app.db.models.regulatory_reference import MarketResponsibleParty

    own = (
        db.query(MarketResponsibleParty.id)
        .filter(MarketResponsibleParty.tenant_id == obligation.tenant_id, MarketResponsibleParty.market == "US")
        .first()
    )
    if own is not None:
        obligation.entries = {**(obligation.entries or {}), **_entries(US_TYPED_PARTY, author_id, at)}
        return router.request_snapshot(db, control_db, obligation, author_id, at, SAMPLE_SOURCE)
    party = MarketResponsibleParty(tenant_id=obligation.tenant_id, created_at=at, updated_at=at, **US_PARTY)
    db.add(party)
    db.flush()
    try:
        return router.request_snapshot(db, control_db, obligation, author_id, at, SAMPLE_SOURCE)
    finally:
        db.delete(party)
        db.flush()


def stage_sample_reports(
    db: Session, tenant_id, now: datetime | None = None, control_db: Session | None = None
) -> dict:
    """Add the sample's report examples (see the module docstring). ``{"created": False, ...}`` when the sample
    story's complaints are missing or the examples are there already."""
    from backend.app.authority_reports import forms, router, worksheet
    from backend.app.db.models.foundation import Complaint
    from backend.app.reportability import markets
    from backend.app.trial.sample_decision import sample_author

    now = now or datetime.now(timezone.utc)
    if has_sample_reports(db, tenant_id):
        return {"created": False, "why": "ALREADY_STAGED"}
    us_complaint = (
        db.query(Complaint)
        .filter(
            Complaint.tenant_id == tenant_id,
            Complaint.source_system == SAMPLE_SOURCE,
            Complaint.complaint_identifier == "SAMPLE-RV-09",
        )
        .first()
    )
    if us_complaint is None:
        return {"created": False, "why": "NO_STORY_COMPLAINTS"}
    control_db = control_db or db
    savepoint = db.begin_nested()
    try:
        window = _india_window(db, tenant_id, now)
        india = _india_complaint(db, tenant_id, now)
        author_id = str(sample_author(db, tenant_id, now).id)
        approver_id = str(sample_approver(db, tenant_id, now).id)
        # The US example: signed on day 26 after awareness, submitted on day 27, accepted minutes later.
        aware = us_complaint.awareness_timestamp
        signed_at = aware + timedelta(days=26)
        submitted = aware + timedelta(days=27, hours=2)
        _signed(
            db,
            tenant_id,
            us_complaint,
            markets.US,
            US_EXAMPLE,
            markets.SERIOUS,
            "MEDICAL_INTERVENTION",
            author_id,
            signed_at,
        )
        us = router.start(db, tenant_id, us_complaint.id, markets.US, author_id, signed_at, SAMPLE_SOURCE)
        us.entries = _entries(US_ENTRIES, author_id, submitted - timedelta(hours=3))
        us.entries = {**us.entries, **_coded(db, control_db, us, author_id, submitted - timedelta(hours=3))}
        # The sample author confirmed the device problem code the approved mapping suggests (0.10.77).
        us.entries = worksheet.confirm_suggestions(
            forms.FDA_3500A,
            router._context(db, control_db, us),
            us.entries,
            author_id,
            (submitted - timedelta(hours=3)).isoformat(),
        )
        snapshot = _freeze_us(db, control_db, us, author_id, submitted - timedelta(hours=2))
        _approve(db, us, snapshot, approver_id, submitted - timedelta(hours=1))
        attempt = router.record_submission(
            db,
            us,
            author_id,
            "EMDR",
            submitted,
            note="Sample: the eSubmitter copy of the 3500A as submitted; it matches the approved snapshot.",
            file=_file("sample-esubmitter-copy.txt", "Form FDA 3500A as submitted in eSubmitter (sample file)."),
            differences=[],
            reference=None,
            now=submitted,
            source_system=SAMPLE_SOURCE,
        )
        for minutes, kind, outcome, text in (
            (5, "ACK1", "RECEIPT", "Ack1: received by FDA's gateway (sample file)."),
            (7, "ACK2", "RECEIPT", "Ack2: sent on to CDRH (sample file)."),
            (12, "ACK3", "ACCEPTED", "Ack3: load passed (sample file)."),
            (12, "ACK4", "RECEIPT", "Ack4: load result, XML (sample file)."),
        ):
            at = submitted + timedelta(minutes=minutes)
            router.record_evidence(
                db,
                us,
                attempt,
                author_id,
                kind,
                outcome,
                at,
                note=f"Sample: {forms_label(kind)}",
                file=_file(f"sample-{kind.lower()}.txt", text),
                reference="SAMPLE-ESG-0001 (sample)" if kind == "ACK1" else None,
                now=at,
                source_system=SAMPLE_SOURCE,
            )
        india_result = None
        if india is not None:
            in_signed = now - timedelta(days=4)
            in_submitted = now - timedelta(days=2)
            _signed(
                db,
                tenant_id,
                india,
                markets.IN,
                IN_EXAMPLE,
                markets.SERIOUS,
                "MEDICAL_INTERVENTION",
                author_id,
                in_signed,
            )
            obligation = router.start(db, tenant_id, india.id, markets.IN, author_id, in_signed, SAMPLE_SOURCE)
            obligation.entries = _entries(IN_ENTRIES, author_id, in_submitted - timedelta(hours=3))
            snapshot = router.request_snapshot(
                db, control_db, obligation, author_id, in_submitted - timedelta(hours=2), SAMPLE_SOURCE
            )
            _approve(db, obligation, snapshot, approver_id, in_submitted - timedelta(hours=1))
            attempt = router.record_submission(
                db,
                obligation,
                author_id,
                "MVPI_EMAIL",
                in_submitted,
                note="Sample: the e-mail sent to MvPI with the filled MDAE form attached.",
                file=_file(
                    "sample-sent-email.txt", "To: MvPI. Subject: MDAE report SAMPLE-MAH-2026-001 (sample file)."
                ),
                differences=[],
                reference=None,
                now=in_submitted,
                source_system=SAMPLE_SOURCE,
            )
            bounced = in_submitted + timedelta(minutes=10)
            router.record_evidence(
                db,
                obligation,
                attempt,
                author_id,
                "BOUNCE",
                "REJECTED",
                bounced,
                note="Sample: delivery failed (the attachment was over the mail server's size limit).",
                file=_file("sample-bounce.txt", "Delivery failed: message too large (sample file)."),
                reference=None,
                now=bounced,
                source_system=SAMPLE_SOURCE,
            )
            india_result = obligation.state
        db.flush()
        savepoint.commit()
    except Exception:
        savepoint.rollback()
        logger.exception("Trial sample reports could not be staged")
        return {"created": False, "why": "ERROR"}
    return {
        "created": True,
        "india_window": window,
        "complaints": 1 if india is not None else 0,
        "signed": 2 if india is not None else 1,
        "us": us.state,
        "india": india_result,
    }


def forms_label(kind: str) -> str:
    from backend.app.authority_reports.forms import EVIDENCE_LABELS

    return EVIDENCE_LABELS.get(kind, kind)
