"""0.10.58 through the API, as two trial users, with migration tr05's tables: the US 3500A and India MDAE worksheets
(T-G2c: TA-2c.1-4) and the obligation lifecycle with its submission record (T-G2b: TA-2b.1-5), the second-person
approval (D-T19), "MDARIX never submits" (no outbound call), tenant isolation under the runtime role, and sample
removal."""

from __future__ import annotations

import io
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from backend.app.db.models.authority_reports import ReportEvidence, ReportObligation, ReportSnapshot, ReportSubmission
from backend.app.db.models.foundation import Complaint
from backend.app.db.session import RuntimeSessionLocal, SessionLocal, runtime_role_active
from backend.app.db.tenant_scope import bind_tenant
from tests.test_free_trial import PASSWORD, _approved_trial_client
from tests.test_reporting_capa_api import PASSWORD as COLLEAGUE_PASSWORD
from tests.test_reporting_capa_api import _client

pytestmark = pytest.mark.db

REPORTS = "/api/v1/reports"
TRAINING = "/api/v1/signer-training"
WHY = "Read from the complaint record and the nurse's report"
US_SERIOUS = dict(US1="NO", US2A="UNKNOWN", US2B="NO", US2C="YES", US3="YES", US4="YES", US5="YES", US6="NO")


def _ok(response):
    assert response.status_code == 200, response.text
    return response.json()


@pytest.fixture(scope="module")
def trial():
    from backend.app.trial.retention import purge_trial

    from tests.code_lists import ensure_loaded
    from tests.test_release_c3_0_10_75 import _classic

    ensure_loaded()  # the IMDRF terms and FDA's codes (0.10.77)

    user, approval, _ = _approved_trial_client()
    tenant_id = uuid.UUID(approval["tenant_id"])
    # The lifecycle as built in 0.10.58, which the classic navigation keeps (every pilot today). The new navigation's
    # rules (0.10.75: a report made on signing, approval after every mandatory field, the PDF after approval) are
    # tested in test_release_c3_0_10_75.py.
    _classic(tenant_id)
    colleague = _client(tenant_id, "LEADER", "Rahul Colleague")
    try:
        yield {"user": user, "colleague": colleague, "tenant_id": tenant_id}
    finally:
        with SessionLocal() as db:
            purge_trial(db, tenant_id, "test:authority-reports-cleanup")


def _items(client, **params) -> dict:
    return {
        (item["complaint_identifier"], item["market"], item["kind"]): item
        for item in _ok(client.get(REPORTS, params=params))["items"]
    }


def _fields(detail: dict) -> dict:
    return {item["id"]: item for section in detail["sections"] for item in section["fields"]}


def _complaint_id(tenant_id, identifier: str) -> str:
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        return str(
            db.query(Complaint.id)
            .filter(Complaint.tenant_id == tenant_id, Complaint.complaint_identifier == identifier)
            .scalar()
        )


def _sign_rv06(trial) -> str:
    """The trial user signs SAMPLE-RV-06's US conclusion (the story's step 2.4), once."""
    user = trial["user"]
    complaint = _complaint_id(trial["tenant_id"], "SAMPLE-RV-06")
    base = f"/api/v1/complaints/{complaint}/market-assessments"
    detail = _ok(user.get(base))
    us = next(item for item in detail["markets"] if item["market"] == "US")
    if us["current"]:
        return complaint
    for document in _ok(user.get(f"{TRAINING}?documents=QUESTION_SET_US,HARM_SCALE"))["documents"]:
        _ok(
            user.post(
                f"{TRAINING}/{document['code']}/acknowledge",
                json={"version": document["version"], "statement": document["statement"]},
            )
        )
    answers = {key: {"answer": value, "rationale": WHY, "evidence": []} for key, value in US_SERIOUS.items()}
    saved = _ok(user.put(f"{base}/US", json={"answers": answers, "harm_level": "CRITICAL"}))
    draft = next(item for item in saved["markets"] if item["market"] == "US")["draft"]
    _ok(
        user.post(
            f"{base}/US/sign",
            json={
                "conclusion": "REPORTABLE",
                "version": draft["version"],
                "saved_at": draft["saved_at"],
                "password": PASSWORD,
            },
        )
    )
    return complaint


def _start_rv06(trial) -> dict:
    complaint = _sign_rv06(trial)
    found = _items(trial["user"], complaint_id=complaint).get(("SAMPLE-RV-06", "US", "INITIAL"))
    if found and found["id"]:
        return _ok(trial["user"].get(f"{REPORTS}/{found['id']}"))
    return _ok(trial["user"].post(REPORTS, json={"complaint_id": complaint, "market": "US"}))


def _ready_us(client, report_id: str, number: str | None = "1234567-2026-00001") -> dict:
    """A US draft its eMDR file can be made from (0.10.96: Send for approval checks the file): the report number
    when given, FDA's required blocks filled as a person does."""
    from tests.report_fill import US_EMDR, fill

    if number:
        _ok(client.put(f"{REPORTS}/{report_id}/fields/MFR_REPORT", json={"value": number}))
    return fill(client, REPORTS, report_id, US_EMDR)


def test_rv06_drafts_a_3500a_worksheet_in_field_order_with_a_status_on_every_field(trial):  # TA-2c.1
    # Before the conclusion is signed, the obligation is listed with its provisional deadline (pending information).
    before = _items(trial["user"])
    assert ("SAMPLE-RV-08", "US", "INITIAL") in before and before[("SAMPLE-RV-08", "US", "INITIAL")]["provisional"]
    detail = _start_rv06(trial)
    assert detail["form"]["version"] == "Form FDA 3500A (09/2025)" and detail["state"] == "DRAFT"
    assert [section["code"] for section in detail["sections"]] == ["FRONT", "A", "B", "C", "D", "E", "F", "G", "H"]
    fields = _fields(detail)
    assert list(fields)[:8] == ["MFR_REPORT", "A1", "A2", "A3", "A4", "A5", "B1", "B2"]
    assert all(item["status"] and item["status_label"] for item in fields.values())
    assert fields["B5"]["status"] == "FROM_RECORD" and fields["B5"]["source"]["type"] == "Complaint"
    assert fields["B2"]["value"] == "Required intervention to prevent permanent impairment/damage"
    assert fields["G6"]["value"] == "30-day; Initial" and fields["G6"]["source"]["type"] == "MarketAssessment"
    assert fields["MFR_REPORT"]["status"] == "MUST_HAVE"
    # The sample's patient fields keep their place, filled with fictional values.
    assert fields["A1"]["value"] == "PT-0006 (fictional)" and fields["A1"]["status"] == "FICTIONAL"
    assert detail["practice_label"] and detail["starter_mark"] and "never submits" in detail["never_submits"]


def test_the_worksheets_use_the_mapped_imdrf_codes(trial):  # TA-2c.4
    fields = _fields(_start_rv06(trial))
    problem = fields["H6_PROBLEM"]
    assert problem["status"] == "FROM_RECORD" and problem["source"]["type"] == "ImdrfMapping"
    # UNDER_INFUSION_NO_ALARM -> A1407, A160102 (0.10.77), each with its FDA code from FDA's IMDRF mapping.
    assert problem["value"].startswith("A1407") and "A160102" in problem["value"] and "(FDA " in problem["value"]


def test_the_india_sample_drafts_an_mdae_v12_worksheet_in_field_order(trial):  # TA-2c.2, TA-2b.3
    item = _items(trial["user"])[("SAMPLE-RV-10", "IN", "INITIAL")]
    detail = _ok(trial["user"].get(f"{REPORTS}/{item['id']}"))
    assert detail["form"]["version"] == "MDAE Reporting Form, Version 1.2"
    assert [section["code"] for section in detail["sections"]] == [
        "PRIMARY",
        "REPORTER",
        "CATEGORY",
        "A",
        "B",
        "C",
        "D",
        "E",
        "F",
    ]
    fields = _fields(detail)
    assert fields["B8"]["value"].startswith("Yes: f) Required intervention")
    assert fields["C2"]["value"] == "R.K. (fictional)"
    # The sample's rejected attempt: back to draft with its original deadline, needing a new approval.
    assert detail["state"] == "CORRECTION_REQUIRED"
    (attempt,) = detail["submissions"]
    assert attempt["result"] == "REJECTED" and [row["kind"] for row in attempt["evidence"]][-1] == "BOUNCE"
    from backend.app.oversight.rules import zone_info
    from backend.app.reportability.deadlines import org_zone

    with SessionLocal() as db:
        bind_tenant(db, trial["tenant_id"])
        obligation = db.get(ReportObligation, uuid.UUID(item["id"]))
        stamp = db.get(Complaint, obligation.complaint_id).awareness_timestamp
        # The awareness day is the earlier of its day in IST and in the organization's zone (deadlines.py), not its
        # UTC day: a sample seeded before 05:00 UTC falls on the day before in New York, the trial's zone.
        zones = ("Asia/Kolkata", org_zone(db, trial["tenant_id"]))
        aware = min(stamp.astimezone(zone_info(zone)).date() for zone in zones)
        # India counts the awareness day as day 1 (0.10.63, the MVP's conservative rule): day 15 is awareness + 14.
        assert obligation.due_on == aware + timedelta(days=14)
    assert detail["deadline"]["due_on"] == (aware + timedelta(days=14)).isoformat()
    # 0.10.84: the label is in the organization's time zone, whichever market's deadline it is.
    from backend.app.reportability import deadlines

    with SessionLocal() as db:
        bind_tenant(db, trial["tenant_id"])
        assert detail["deadline"]["due_label"] == deadlines.moment_label(
            datetime.fromisoformat(detail["deadline"]["due_at"]), org_zone(db, trial["tenant_id"])
        )
    refused = trial["user"].post(
        f"{REPORTS}/{item['id']}/submissions",
        json={
            "route": "MVPI_EMAIL",
            "submitted_at": datetime.now(timezone.utc).isoformat(),
            "no_differences": True,
            "content_note": "Resent.",
        },
    )
    assert refused.status_code == 409 and refused.json()["detail"]["code"] == "SNAPSHOT_NOT_APPROVED"


def test_uploaded_data_leaves_patient_fields_blank_and_refuses_them(trial):  # T-B9
    detail = _start_rv06(trial)
    refused = trial["user"].put(f"{REPORTS}/{detail['id']}/fields/A1", json={"value": "John Smith"})
    assert refused.status_code == 422 and refused.json()["detail"]["code"] == "PERSONAL_FIELD"
    from backend.app.authority_reports import forms, worksheet

    context = {"complaint": type("C", (), {"complaint_identifier": "OWN-1"})(), "sample": False}
    row = next(
        item
        for section in worksheet.build(forms.FDA_3500A, {**context, **_empty_context()}, {}, {})
        for item in section["fields"]
        if item["id"] == "A1"
    )
    assert (
        row["value"] is None and row["status"] == "OUTSIDE" and row["status_label"] == "Enter in the authority's route"
    )


def _empty_context() -> dict:
    complaint = type(
        "C",
        (),
        {
            "complaint_identifier": "OWN-1",
            "description": "Own",
            "event_timestamp": None,
            "death": None,
            "serious_injury": None,
            "patient_involved": None,
            "malfunction": None,
            "serial_number": None,
            "udi": None,
            "device_returned": None,
            "problem_code": None,
            "id": uuid.uuid4(),
        },
    )()
    return {
        "complaint": complaint,
        "record": {"business_id": "C-1", "complaint_identifier": "OWN-1", "version": None},
        "seen": {},
        "product": None,
        "lot": None,
        "current": None,
        "draft": None,
        "classification": None,
        "case": None,
        "capas": [],
        "triage": None,
        "registrations": [],
        "parties": [],
        "imdrf": [],
        "sample": False,
    }


def test_the_preparer_and_the_conclusion_signer_cannot_approve_and_a_colleague_can(trial):  # TA-2b.1, D-T19
    user, colleague = trial["user"], trial["colleague"]
    detail = _start_rv06(trial)
    if detail["state"] == "DRAFT":
        _ready_us(user, detail["id"])
        detail = _ok(user.post(f"{REPORTS}/{detail['id']}/snapshots"))
        snapshot = detail["pending_snapshot"]
        assert snapshot and detail["state"] == "DRAFT"
        # The same person (the preparer, who also signed the US conclusion) is refused, before any password check.
        same = user.post(f"{REPORTS}/{detail['id']}/snapshots/{snapshot['id']}/approve", json={"password": PASSWORD})
        assert same.status_code == 403 and same.json()["detail"]["code"] == "SECOND_PERSON_REQUIRED"
        approved = _ok(
            colleague.post(
                f"{REPORTS}/{detail['id']}/snapshots/{snapshot['id']}/approve", json={"password": COLLEAGUE_PASSWORD}
            )
        )
        assert approved["state"] == "APPROVED" and approved["snapshots"][0]["approved_by"] == "Rahul Colleague"


def test_the_conclusion_signer_alone_is_refused_too():
    from backend.app.authority_reports import rules

    assert rules.approver_problem("a", "LEADER", {"b"}, "a").startswith("You signed the market conclusion")
    assert rules.approver_problem("a", "CUSTOMER_ADMIN", set(), None).startswith("An administrator")
    assert rules.approver_problem("c", "LEADER", {"b"}, "a") is None


def test_a_receipt_is_not_acceptance(trial, monkeypatch):  # TA-2b.2, MDARIX never submits
    import smtplib
    import socket
    import urllib.request

    import httpx

    def no_outbound(*args, **kwargs):
        raise AssertionError("MDARIX never submits: no outbound call")

    # The test client talks to the app in process; any real network call (HTTP, sockets, mail) fails the test.
    monkeypatch.setattr(httpx.HTTPTransport, "handle_request", no_outbound)
    monkeypatch.setattr(socket, "create_connection", no_outbound)
    monkeypatch.setattr(urllib.request, "urlopen", no_outbound)
    monkeypatch.setattr(smtplib, "SMTP", no_outbound)
    test_the_preparer_and_the_conclusion_signer_cannot_approve_and_a_colleague_can(trial)
    user = trial["user"]
    detail = _start_rv06(trial)
    assert detail["state"] == "APPROVED"
    material = user.post(
        f"{REPORTS}/{detail['id']}/submissions",
        json={
            "route": "EMDR",
            "submitted_at": datetime.now(timezone.utc).isoformat(),
            "content_note": "Copy",
            "differences": [{"field": "B5", "classification": "MATERIAL", "reason": "Narrative rewritten"}],
        },
    )
    assert material.status_code == 409 and "re-approval" in material.json()["detail"]["message"]
    submitted = _ok(
        user.post(
            f"{REPORTS}/{detail['id']}/submissions",
            json={
                "route": "EMDR",
                "submitted_at": (datetime.now(timezone.utc) - timedelta(minutes=30)).isoformat(),
                "content_note": "The eSubmitter copy as submitted.",
                "no_differences": True,
                "file": {"name": "copy.txt", "content_type": "text/plain", "data": "Y29weQ=="},
            },
        )
    )
    attempt = submitted["submissions"][0]
    assert submitted["state"] == "SUBMITTED_PENDING" and attempt["follow_up"]["row"] in (1, 2, 3, 4)
    now = datetime.now(timezone.utc)
    for kind in ("ACK1", "ACK2"):
        receipt = _ok(
            user.post(
                f"{REPORTS}/{detail['id']}/submissions/{attempt['id']}/evidence",
                json={"kind": kind, "outcome": "RECEIPT", "received_at": now.isoformat(), "note": f"{kind} file"},
            )
        )
        assert receipt["state"] == "SUBMITTED_PENDING" and receipt["submissions"][0]["receipt_only"]
    watch = _ok(user.get("/api/v1/complaints/reportability", params={"show": "all"}))
    rv06 = next(item for item in watch["items"] if item["complaint_identifier"] == "SAMPLE-RV-06")
    assert not next(m for m in rv06["markets"] if m["market"] == "US")["filed"]  # not shown as met
    accepted = _ok(
        user.post(
            f"{REPORTS}/{detail['id']}/submissions/{attempt['id']}/evidence",
            json={"kind": "ACK3", "outcome": "ACCEPTED", "received_at": now.isoformat(), "note": "Ack3 passed"},
        )
    )
    assert accepted["state"] == "ACCEPTED" and accepted["submissions"][0]["result"] == "ACCEPTED"
    watch = _ok(user.get("/api/v1/complaints/reportability", params={"show": "all"}))
    rv06 = next(item for item in watch["items"] if item["complaint_identifier"] == "SAMPLE-RV-06")
    assert next(m for m in rv06["markets"] if m["market"] == "US")["filed"]


def test_a_request_for_information_creates_a_separate_response_obligation(trial):  # TA-2b.4
    user = trial["user"]
    finished = _items(user)[("SAMPLE-RV-09", "US", "INITIAL")]
    assert finished["state"] == "ACCEPTED"
    today = datetime.now(timezone.utc).date()
    response = _ok(
        user.post(
            f"{REPORTS}/{finished['id']}/requests",
            json={
                "request_text": "FDA asks for the device evaluation results.",
                "received_on": today.isoformat(),
                "due_on": (today + timedelta(days=10)).isoformat(),
            },
        )
    )
    assert response["kind"] == "RESPONSE" and response["parent_id"] == finished["id"] and response["state"] == "DRAFT"
    # 0.10.96 (B3): FDA's request is answered by a follow-up on Form 3500A, H2 "Response to FDA request".
    assert response["follow_up"] == 1 and _fields(response)["H2"]["value"] == "Response to FDA request"
    assert response["request"]["text"] == "FDA asks for the device evaluation results."
    parent = _ok(user.get(f"{REPORTS}/{finished['id']}"))
    assert parent["state"] == "ACCEPTED" and parent["responses"][0]["id"] == response["id"]


def test_an_export_carries_the_form_version_the_starter_mark_and_the_practice_label(trial):  # TA-2c.3
    from docx import Document

    user = trial["user"]
    finished = _items(user)[("SAMPLE-RV-09", "US", "INITIAL")]
    detail = _ok(user.get(f"{REPORTS}/{finished['id']}"))
    snapshot = next(row for row in detail["snapshots"] if row["state"] == "APPROVED")
    pdf = user.get(f"{REPORTS}/{finished['id']}/worksheet.pdf", params={"snapshot": snapshot["id"]})
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
    docx = user.get(f"{REPORTS}/{finished['id']}/worksheet.docx")
    assert docx.status_code == 200
    text = "\n".join(paragraph.text for paragraph in Document(io.BytesIO(docx.content)).paragraphs)
    assert (
        "Form FDA 3500A (09/2025)" in text
        and "Starter, for your consultant to confirm" in text
        and "Practice record" in text
    )
    assert "MDARIX NEVER SUBMITS" in text


def test_another_organization_reads_none_of_it(trial):  # TA-2b.5
    other, _, _ = _approved_trial_client()
    mine = _items(trial["user"])[("SAMPLE-RV-09", "US", "INITIAL")]
    assert other.get(f"{REPORTS}/{mine['id']}").status_code == 404
    assert mine["id"] not in {item["id"] for item in _items(other).values()}
    if runtime_role_active():
        for model in (ReportObligation, ReportSnapshot, ReportSubmission, ReportEvidence):
            for tenant, expected in ((uuid.uuid4(), False), (trial["tenant_id"], True)):
                runtime = RuntimeSessionLocal()
                try:
                    bind_tenant(runtime, tenant)
                    count = runtime.query(model).filter(model.tenant_id == trial["tenant_id"]).count()
                    assert (count > 0) == expected, model.__tablename__
                finally:
                    runtime.close()


def test_export_purge_and_sample_removal_cover_the_records():  # TA-2b.5
    from backend.app.db.tenant_scope import bind_system
    from backend.app.tenant_export import _tables
    from backend.app.trial.retention import TRIAL_DATA_TABLES, purge_trial

    tables = {"report_obligations", "report_snapshots", "report_submissions", "report_evidence"}
    user, approval, _ = _approved_trial_client()
    tenant_id = uuid.UUID(approval["tenant_id"])
    with SessionLocal() as db:
        bind_system(db, "test: tables an export and the purge cover")
        assert tables <= {table for _, table in _tables(db)} and tables <= set(TRIAL_DATA_TABLES)
    _ok(user.post("/api/v1/trial/sample-data/removal", json={"confirm": True}))
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        for model in (ReportObligation, ReportSnapshot, ReportSubmission, ReportEvidence):
            assert db.query(model).filter(model.tenant_id == tenant_id).count() == 0, model.__tablename__
        purge_trial(db, tenant_id, "test:authority-reports-removal")
