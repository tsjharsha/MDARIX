"""DEV-09 (0.10.87): controlled records, end to end on a free trial's flagship US complaint (SAMPLE-RV-11).

- Provenance runs from the source to the conclusion, the report and the PDF: the complaint's record value is the
  answer's source, the signed conclusion is bound to its checksum, the report is created from that signed version and
  each field names its source, and the approved snapshot's PDF prints the sources, the form version and the approval.
- The worksheet PDF matches its snapshot (tests/snapshots/worksheet_us_3500a.txt), with only what changes per run
  (dates, times, checksums, generated references) replaced by placeholders.
- An amendment is a new version: the prior signed version stays as it was signed, with its rationale, signer, time and
  checksum, and its signature record still verifies.

Rows AM-1, PV-1 and PV-2 of docs/compliance/REGULATORY_DECISION_TABLES.md. Tests of the starter rules, not regulatory
qualification.
"""

from __future__ import annotations

import os
import re
import uuid
from pathlib import Path

import pytest

from backend.app.db.models.foundation import AuditEvent, SignedApprovalRecord
from backend.app.db.models.market_assessment import ComplaintMarketAssessment
from backend.app.db.session import SessionLocal
from backend.app.db.tenant_scope import bind_system, bind_tenant
from reports.pdf import text_of
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
    text = text_of(pdf.content)
    assert "Form version: Form FDA 3500A (09/2025)" in text
    assert "United States (FDA) v1 (signed)" in text  # the conclusion as the source of its fields
    assert "Source records" in text and "Approval" in text
    assert "PRACTICE RECORD" in text or "Practice record" in text
    trial["state"].update(report=report["id"], snapshot=snapshot["id"], pdf=pdf.content)
    print("\n----PDF----\n" + text + "\n----END----")


def test_the_worksheet_pdf_matches_its_snapshot(trial):
    state = trial["state"]
    assert state.get("pdf"), "runs after the provenance test"
    found = _normalized(text_of(state["pdf"]))
    if os.environ.get("MDARIX_UPDATE_SNAPSHOTS") == "1":
        SNAPSHOT.parent.mkdir(exist_ok=True)
        SNAPSHOT.write_text(found, encoding="utf-8")
    assert found == SNAPSHOT.read_text(encoding="utf-8")


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
