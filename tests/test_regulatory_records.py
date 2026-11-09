"""DEV-09 (0.10.87): controlled records, end to end on a free trial's flagship US complaint (SAMPLE-RV-11).

- Provenance runs from the source to the conclusion, the report and the PDF: the complaint's record value is the
  answer's source, the signed conclusion is bound to its checksum, the report is created from that signed version and
  each field names its source, and the approved snapshot's PDF prints the sources, the form version and the approval.
- The approved report's PDF (FDA's own Form 3500A, filled, then MDARIX's record page) matches its snapshot
  (tests/snapshots/worksheet_us_3500a.txt), with only what changes per run (dates, times, checksums, generated
  references) replaced by placeholders.
- An amendment is a new version: the prior signed version stays as it was signed, with its rationale, signer, time and
  checksum, and its signature record still verifies.

Rows AM-1, PV-1 and PV-2 of docs/compliance/REGULATORY_DECISION_TABLES.md. Tests of the starter rules, not regulatory
qualification.
"""

from __future__ import annotations

import io
import os
import re
import uuid
from pathlib import Path

import pytest

from backend.app.db.models.foundation import AuditEvent, SignedApprovalRecord
from backend.app.db.models.market_assessment import ComplaintMarketAssessment
from backend.app.db.session import SessionLocal
from backend.app.db.tenant_scope import bind_system, bind_tenant
from pypdf import PdfReader
from tests.report_fill import fill
from tests.test_free_trial import PASSWORD, _approved_trial_client
from tests.test_release_c3_0_10_75 import REPORTS, _flagship, _ok, _purge, _reports, _sign_us

pytestmark = pytest.mark.db

SNAPSHOT = Path(__file__).parent / "snapshots" / "worksheet_us_3500a.txt"


@pytest.fixture(scope="module")
def trial():
    user, approval, _ = _approved_trial_client()
    tenant_id = uuid.UUID(approval["tenant_id"])
    complaint = _flagship(user)
    try:
        yield {"user": user, "tenant_id": tenant_id, "complaint": complaint, "state": {}}
    finally:
        _purge(tenant_id)


def _versions(tenant_id, complaint) -> list[ComplaintMarketAssessment]:
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        rows = (
            db.query(ComplaintMarketAssessment)
            .filter(
                ComplaintMarketAssessment.tenant_id == tenant_id,
                ComplaintMarketAssessment.complaint_id == uuid.UUID(complaint),
                ComplaintMarketAssessment.market == "US",
            )
            .order_by(ComplaintMarketAssessment.version)
            .all()
        )
        db.expunge_all()
        return rows


def _normalized(text: str) -> str:
    """The PDF's text with what changes per run replaced: checksums, generated references, dates and times (the
    sample's dates are relative to the day it is staged)."""
    rules = (
        (r"\b[0-9a-f]{64}\b", "<SHA256>"),
        (r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b", "<UUID>"),
        (r"\b(?:Mon|Tue|Wed|Thu|Fri|Sat|Sun) \d{1,2} [A-Z][a-z]{2} \d{4}, \d{2}:\d{2} [A-Z+0-9]+", "<MOMENT>"),
        (r"\b\d{1,2} [A-Z][a-z]{2} \d{4}, \d{2}:\d{2} UTC", "<MOMENT>"),
        (r"\b\d{4}-\d{2}-\d{2}\b", "<DATE>"),
        (r"\b\d{2}-[A-Z][a-z]{2}-\d{4}\b", "<DATE>"),  # as FDA's form writes a date (01-Jan-1900)
        # Business IDs come from counters (CMP000038, ESIG000012).
        (r"\b[A-Z]{2,5}\d{6}\b", "<BUSINESS-ID>"),
    )
    for pattern, mark in rules:
        text = re.sub(pattern, mark, text)
    return "\n".join(line.rstrip() for line in text.splitlines()).strip() + "\n"


def test_provenance_runs_from_the_complaint_to_the_conclusion_the_report_and_its_pdf(trial):
    user, complaint, tenant_id = trial["user"], trial["complaint"], trial["tenant_id"]
    signed = _ok(_sign_us(user, complaint, "REPORTABLE"))
    us = next(item for item in signed["markets"] if item["market"] == "US")
    current = us["current"]
    # Source -> conclusion: each answer the record gave keeps where it came from; the conclusion is bound to its
    # checksum and to the question set and scale versions it was signed with.
    sourced = {key: item for key, item in current["answers"].items() if item.get("source")}
    assert sourced and all(item["source"].startswith("From the complaint record") for item in sourced.values())
    # The sample organization's published US guide, version 2 (decision_guides), and the starter scale.
    assert current["question_set"] == "US-v2" and current["scale_version"] == "scale-starter-1"
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        record = db.get(SignedApprovalRecord, uuid.UUID(current["signed_record_id"]))
        assert record.content_fingerprint == current["content_fingerprint"] and record.object_version == "1"
        assert "harm-severity scale, MDARIX starter, version 1" in record.signature_meaning
    # Conclusion -> report: the report is created from the signed version, and every filled field names its source.
    (report,) = _reports(user, complaint)
    detail = _ok(user.get(f"{REPORTS}/{report['id']}"))
    assert detail["form"]["version"] == "Form FDA 3500A (09/2025)"
    filled = [item for section in detail["sections"] for item in section["fields"] if item["value"]]
    from_conclusion = [item for item in filled if (item.get("source") or {}).get("type") == "MarketAssessment"]
    assert from_conclusion and all(
        item["source"]["ref"].endswith("United States (FDA) v1 (signed)") for item in from_conclusion
    )
    assert all(item["source"] or item["status"] != "FROM_RECORD" for item in filled)
    # Report -> approved snapshot -> PDF.
    fill(user, REPORTS, report["id"], detail["mandatory"]["missing"])
    pending = _ok(user.post(f"{REPORTS}/{report['id']}/snapshots"))["pending_snapshot"]["id"]
    done = _ok(user.post(f"{REPORTS}/{report['id']}/snapshots/{pending}/approve", json={"password": PASSWORD}))
    snapshot = done["approved_snapshot"]
    pdf = user.get(f"{REPORTS}/{report['id']}/worksheet.pdf", params={"snapshot": snapshot["id"]})
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
    # An approved US report's PDF is FDA's own Form 3500A, filled, then MDARIX's record page.
    text = _form_text(pdf.content)
    assert "mfr: Test value (sample)" in text and "Form: Form FDA 3500A (09/2025)" in text
    # B1 (0.10.89): a patient connected with no harm recorded is no adverse event; the malfunction is a product problem.
    assert "prodProblem: /1" in text and "adverse: /1" not in text
    assert "United States (FDA) v1 (signed)" in text  # the conclusion as the source of its fields
    assert "Source records" in text and "Approval" in text
    assert "PRACTICE RECORD" in text or "Practice record" in text
    trial["state"].update(report=report["id"], snapshot=snapshot["id"], pdf=text)
    print("\n----PDF----\n" + text + "\n----END----")


def _form_text(pdf: bytes) -> str:
    """The filled form's fields in page order ("field: value"), then the record page's text."""
    reader = PdfReader(io.BytesIO(pdf))
    filled = [
        f"{str(widget['/T'])[:-3]}: {widget['/V']}"
        for page in reader.pages[:-1]
        for widget in (annotation.get_object() for annotation in page.get("/Annots") or [])
        if widget.get("/T") and widget.get("/V") not in (None, "", "/Off", "--")
    ]
    return "\n".join([*filled, reader.pages[-1].extract_text()])


def test_the_worksheet_pdf_matches_its_snapshot(trial):
    state = trial["state"]
    assert state.get("pdf"), "runs after the provenance test"
    found = _normalized(state["pdf"])
    if os.environ.get("MDARIX_UPDATE_SNAPSHOTS") == "1":
        SNAPSHOT.parent.mkdir(exist_ok=True)
        SNAPSHOT.write_text(found, encoding="utf-8")
    assert found == SNAPSHOT.read_text(encoding="utf-8")


def _fda_mapped_code(annex: str) -> str:
    """A selectable IMDRF code of the annex that FDA's published FDA-IMDRF mapping gives an FDA code."""
    from backend.app import regulatory_reference as reference
    from backend.app.db.models.regulatory_reference import ImdrfCode, ReferenceCode

    with SessionLocal() as db:
        release = reference.newest_release(db)
        mapped = {row.imdrf_code for row in db.query(ReferenceCode).filter(ReferenceCode.list == "FDA_CDRH")}
        rows = (
            db.query(ImdrfCode).filter(ImdrfCode.release == release, ImdrfCode.annex == annex).order_by(ImdrfCode.code)
        )
        return next(row.code for row in rows if row.code in mapped and reference.selectable(row.status))


def test_the_emdr_file_waits_for_what_fda_requires_then_validates(trial):  # eMDR, 0.10.89
    from backend.app.authority_reports import emdr

    user, state = trial["user"], trial["state"]
    report = state["report"]
    detail = _ok(user.get(f"{REPORTS}/{report}"))
    refused = user.get(f"{REPORTS}/{report}/emdr.xml", params={"snapshot": state["snapshot"]})
    assert refused.status_code == 409 and refused.json()["detail"]["code"] == "EMDR_MISSING"
    # The screen and the refusal name the same blocks: the report number's format and the H6 codes still owed. G1 is
    # not among them: since 0.10.92 (A5) the contact office with its e-mail is asked for before approval.
    missing = refused.json()["detail"]["missing"]
    assert missing == detail["emdr"]["missing"]
    assert [item.split(":")[0] for item in missing] == [
        "G8 Manufacturer report number",
        "H6 Component code",
        "H6 Type of investigation code",
        "H6 Investigation findings code",
    ]
    # The organization's US contact office in Settings, the report reopened, completed and approved again.
    party = {
        "market": "US",
        "role": "MANUFACTURER",
        "organisation": "Trial Devices Inc",
        "address": "1 Sample Way, Springfield, MA 01101, US",
        "contact_name": "Taylor Quality",
        "contact_email": "mdr@example.invalid",
        "contact_phone": "+1(240)276-0001",
    }
    _ok(user.put("/api/v1/regulatory-reference/responsible-parties", json=party))
    _ok(user.post(f"{REPORTS}/{report}/reopen", json={"reason": "Complete the blocks the eMDR file needs"}))
    _ok(user.put(f"{REPORTS}/{report}/fields/MFR_REPORT", json={"value": "1234567-2026-00001"}))
    for field in ("G1", "D3"):
        _ok(user.put(f"{REPORTS}/{report}/fields/{field}", json={"clear": True}))
    for field, annex in (("H6_COMPONENT", "G"), ("H6_TYPE", "B"), ("H6_FINDINGS", "C")):
        _ok(user.put(f"{REPORTS}/{report}/fields/{field}", json={"codes": [_fda_mapped_code(annex)]}))
    detail = _ok(user.get(f"{REPORTS}/{report}"))
    assert detail["emdr"]["missing"] == [] and detail["mandatory"]["missing"] == []
    pending = _ok(user.post(f"{REPORTS}/{report}/snapshots"))["pending_snapshot"]["id"]
    done = _ok(user.post(f"{REPORTS}/{report}/snapshots/{pending}/approve", json={"password": PASSWORD}))
    snapshot = done["approved_snapshot"]["id"]
    state["snapshot"] = snapshot
    found = user.get(f"{REPORTS}/{report}/emdr.xml", params={"snapshot": snapshot})
    assert found.status_code == 200, found.text
    assert found.headers["content-type"].startswith("application/xml")
    assert "mdarix-emdr-SAMPLE-RV-11-snapshot-2.xml" in found.headers["content-disposition"]
    assert emdr.validate(found.content) == []
    assert b'extension="1234567-2026-00001"' in found.content and b"mailto:mdr@example.invalid" in found.content
    assert b"Practice record: free trial" in found.content  # a trial's file is a practice record
    # The PDF's G1 boxes come from the same contact office.
    fields = _form_text(user.get(f"{REPORTS}/{report}/worksheet.pdf", params={"snapshot": snapshot}).content)
    assert "manuEmail: mdr@example.invalid" in fields and "manuPhone: +1(240)276-0001" in fields


def test_an_amended_conclusion_keeps_the_prior_version_with_its_rationale_actor_and_time(trial):
    user, complaint, tenant_id = trial["user"], trial["complaint"], trial["tenant_id"]
    (before,) = [row for row in _versions(tenant_id, complaint) if row.conclusion]
    kept = {
        "answers": before.answers,
        "conclusion": before.conclusion,
        "report_type": before.report_type,
        "override_reason": before.override_reason,
        "signed_by": before.signed_by,
        "signed_at": before.signed_at,
        "content_fingerprint": before.content_fingerprint,
        "signed_record_id": before.signed_record_id,
    }
    # New evidence: a recurrence would not harm. The amendment is version 2, not reportable.
    amended = _ok(_sign_us(user, complaint, "NOT_REPORTABLE", recurs=False))
    us = next(item for item in amended["markets"] if item["market"] == "US")
    assert us["current"]["version"] == 2 and us["current"]["conclusion"] == "NOT_REPORTABLE"
    (history,) = us["history"]
    assert history["version"] == 1 and history["superseded"] and history["conclusion"] == "REPORTABLE"
    assert history["signed_by"] and history["signed_at"] and history["answers"]["US5"]["rationale"]
    first, second = _versions(tenant_id, complaint)
    assert {key: getattr(first, key) for key in kept} == kept  # nothing of version 1 changed
    assert first.superseded_by == second.id and second.superseded_by is None
    assert first.answers["US5"]["answer"] == "YES" and second.answers["US5"]["answer"] == "NO"
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        record = db.get(SignedApprovalRecord, first.signed_record_id)
        assert record.status == "SIGNED" and record.content_fingerprint == first.content_fingerprint
        assert record.signer_user_id == first.signed_by and record.signed_at == first.signed_at
        bind_system(db, "test: read the audit trail")
        signed = (
            db.query(AuditEvent)
            .filter(
                AuditEvent.entity_id == uuid.UUID(complaint), AuditEvent.action == "COMPLAINT_MARKET_CONCLUSION_SIGNED"
            )
            .order_by(AuditEvent.created_at)
            .all()
        )
    assert [(event.details["version"], event.details["conclusion"]) for event in signed] == [
        (1, "REPORTABLE"),
        (2, "NOT_REPORTABLE"),
    ]
    assert all(event.actor_ref == first.signed_by for event in signed)
    assert signed[0].details["fingerprint"] == first.content_fingerprint
    # The report it created is cancelled with its reason; the approved snapshot stays, superseded, with its approval.
    detail = _ok(user.get(f"{REPORTS}/{trial['state']['report']}"))
    assert detail["state"] == "CANCELLED" and "version 2" in detail["cancelled_reason"]
    snapshot = next(row for row in detail["snapshots"] if row["id"] == trial["state"]["snapshot"])
    assert snapshot["state"] == "SUPERSEDED" and snapshot["approved_by"]


def test_a_superseded_snapshot_gives_no_emdr_file_and_no_pdf(trial):  # code audit 9 Nov 2026, fix 5
    user, state = trial["user"], trial["state"]
    for path in ("emdr.xml", "worksheet.pdf"):
        refused = user.get(f"{REPORTS}/{state['report']}/{path}", params={"snapshot": state["snapshot"]})
        assert refused.status_code == 409, (path, refused.text)
        assert refused.json()["detail"]["code"] == "SNAPSHOT_NOT_APPROVED"
