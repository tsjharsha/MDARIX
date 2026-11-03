"""The ready-to-use documents through the API (T-G35, T-G35.1-.5), on a free trial's sample data: each of the five
generates with every figure linked to its records and matching Readiness (TA-35.1), its judgement sections empty until
a person writes them (TA-35.2), signed with the password, never edited once signed, a new generation version 2 with
both listed (TA-35.3), the signed PDF kept with its SHA-256 in the signature record and the DOCX marked as an export
(TA-35.4), the clauses printed "pending approval" (TA-35.5); the risk-control answers in the risk-review extract and
the governed RISK_IMPACT report; another organization reads nothing; sample removal takes the versions with it.

No migration: versions are report_jobs rows, signatures signed_approval_records rows."""

from __future__ import annotations

import hashlib
import io
import uuid
from datetime import date, datetime, timedelta, timezone

import pytest

from backend.app.db.models.foundation import Complaint, Investigation, Risk, SignedApprovalRecord
from backend.app.db.models.reporting import ReportJob
from backend.app.db.models.reviews import CaseReview
from backend.app.db.session import RuntimeSessionLocal, SessionLocal, runtime_role_active
from backend.app.db.tenant_scope import bind_tenant
from backend.app.readiness_home.summary import PMS_FRAMING
from reports.pdf import text_of
from tests.test_free_trial import PASSWORD, _approved_trial_client

pytestmark = pytest.mark.db

DOCS = "/api/v1/documents"
PRACTICE = "Practice record: made in a free trial with sample or de-identified data. Not your regulatory record."
ACTIONS = (
    "Open a product investigation into PulseWatch 410 cable wear if a third occurs; owner Rahul; review in 30 days."
)


@pytest.fixture(scope="module")
def trial():
    from backend.app.trial.retention import purge_trial

    user, approval, _ = _approved_trial_client()
    tenant_id = uuid.UUID(approval["tenant_id"])
    types = user.get(f"{DOCS}/types").json()
    try:
        yield {"user": user, "tenant_id": tenant_id, "types": types}
    finally:
        with SessionLocal() as db:
            purge_trial(db, tenant_id, "test:documents-cleanup")


def pdf_text(content: bytes) -> str:
    """The text a PDF written by reports/pdf.py shows, its lines joined (wrapped lines read as one)."""
    return " ".join(text_of(content).split())


def _section(view: dict, key: str) -> dict:
    return next(section for section in view["sections"] if section["key"] == key)


def _texts(section: dict) -> list[str]:
    return [row["text"] for row in section["rows"]]


def _case(trial, identifier: str) -> dict:
    return next(case for case in trial["types"]["cases"] if case["identifier"] == identifier)


def _generate(client, code: str, **extra):
    return client.post(DOCS, json={"code": code, **extra})


def _write_all(client, view: dict) -> dict:
    for item in (section for section in view["sections"] if section["kind"] == "judgement"):
        text = (
            ACTIONS if item["key"] == "ACTIONS_DECIDED" else f"{item['title']}: written by the trial user for review."
        )
        done = client.put(f"{DOCS}/{view['id']}/judgement/{item['key']}", json={"text": text})
        assert done.status_code == 200, done.text
        view = done.json()
    return view


def test_the_five_templates_print_their_clauses_pending_approval(trial):
    found = {item["code"]: item for item in trial["types"]["templates"]}
    assert list(found) == [
        "MANAGEMENT_REVIEW",
        "CAPA_LOG",
        "INVESTIGATION_REPORT",
        "RISK_REVIEW_EXTRACT",
        "CHANGE_IMPACT",
    ]
    clauses = {code: [(clause["short"], clause["state"]) for clause in item["clauses"]] for code, item in found.items()}
    assert clauses["MANAGEMENT_REVIEW"] == [
        ("ISO 13485 5.6.2", "pending approval"),
        ("ISO 13485 8.2.1", "pending approval"),
    ]
    assert clauses["INVESTIGATION_REPORT"] == [
        ("ISO 13485 8.2.2", "pending approval"),
        ("ISO 14971 clause 10", "pending approval"),
    ]
    assert clauses["RISK_REVIEW_EXTRACT"] == [("ISO 14971 clause 10", "pending approval")]
    assert found["MANAGEMENT_REVIEW"]["template_version"] == "mrr-starter-1"
    assert [item["key"] for item in found["MANAGEMENT_REVIEW"]["judgements"]] == ["PMS_CONCLUSION", "ACTIONS_DECIDED"]
    assert trial["types"]["practice_label"] == PRACTICE
    assert "SAMPLE-CHG-014" in {change["ref"] for change in trial["types"]["changes"]}
    assert "SAMPLE-INV-001" in {case["identifier"] for case in trial["types"]["cases"]}


def test_the_management_review_report_matches_readiness_and_links_every_figure(trial):
    user = trial["user"]
    made = _generate(user, "MANAGEMENT_REVIEW", period_days=90)
    assert made.status_code == 200, made.text
    view = made.json()
    assert view["version"] == 1 and view["status"] == "DRAFT" and view["period"]["days"] == 90
    assert view["practice_label"] == PRACTICE and view["template_version"] == "mrr-starter-1"
    assert [section["key"] for section in view["sections"]] == [
        "COMPLAINTS",
        "SECOND_LOOK",
        "DISPOSITIONS",
        "VIGILANCE",
        "TRENDS",
        "RISK_FILE",
        "CAPA",
        "PMS",
        "PMS_CONCLUSION",
        "ACTIONS_DECIDED",
        "LIMITATIONS",
    ]
    # TA-35.1: the figures are the readiness summary's for the same period, each with the records it counts.
    summary = user.get("/api/v1/readiness/summary", params={"period_days": 90}).json()
    complaints = _section(view, "COMPLAINTS")["rows"][0]
    assert complaints["text"].startswith(f"{summary['complaints']['received']} complaints received")
    assert len(complaints["sources"]) + complaints.get("more", 0) == summary["complaints"]["received"]
    assert all(source["type"] == "Complaint" and source["id"] for source in complaints["sources"])
    dispositions = _section(view, "DISPOSITIONS")
    service_level = next(row for row in dispositions["rows"] if row["text"].startswith("Resolved at service level"))
    assert (
        service_level["text"] == f"Resolved at service level: {summary['dispositions']['by_branch']['SERVICE_LEVEL']}."
    )
    assert len(service_level["sources"]) == summary["dispositions"]["by_branch"]["SERVICE_LEVEL"] >= 1  # RT-03
    assert any(text.startswith("By use environment: ") for text in _texts(_section(view, "COMPLAINTS")))
    assert any(text.startswith("By user type: ") for text in _texts(_section(view, "COMPLAINTS")))
    vigilance = _texts(_section(view, "VIGILANCE"))
    assert any(text.startswith("EU and Northern Ireland (EU MDR): 1 conclusion reportable") for text in vigilance)
    assert any(text.startswith("United States (FDA)") and "1 pending now" in text for text in vigilance)  # RV-08
    # The PMS section: T-MSG's framing, the reactive sources, the loop; no proactive source is recorded before 0.10.55.
    pms = _texts(_section(view, "PMS"))
    assert pms[0] == PMS_FRAMING
    assert [text.split(":")[0] for text in pms[1:4]] == [
        "Reactive source, complaints",
        "Reactive source, service records",
        "Reactive source, reportable events",
    ]
    assert any(text.startswith("Into risk management") for text in pms)
    assert any("back to the PMS plan" in text for text in pms)
    # TA-35.2: the judgement sections are empty until a person writes them.
    assert view["judgement"] == {}
    assert _section(view, "ACTIONS_DECIDED")["kind"] == "judgement"
    # Every row stating a figure from records links to them (statements of method and the framing carry none).
    for section in view["sections"]:
        for row in section.get("rows") or []:
            if section["key"] in ("COMPLAINTS", "DISPOSITIONS") and not row["text"].endswith(": 0."):
                assert row["sources"], row["text"]


def test_a_signed_version_is_never_edited_and_a_new_generation_is_version_two(trial):
    user = trial["user"]
    view = _generate(user, "MANAGEMENT_REVIEW", period_days=90).json()
    # A data section cannot be edited; the signature waits for every judgement section.
    data = user.put(f"{DOCS}/{view['id']}/judgement/COMPLAINTS", json={"text": "Five hundred complaints instead."})
    assert data.status_code == 422 and data.json()["detail"]["code"] == "DATA_SECTION_NOT_EDITABLE"
    assert (
        data.json()["detail"]["message"] == "A data section cannot be edited. Correct the record, then generate again."
    )
    early = user.post(f"{DOCS}/{view['id']}/sign", json={"password": PASSWORD})
    assert early.status_code == 422 and early.json()["detail"]["code"] == "JUDGEMENT_NOT_WRITTEN"
    view = _write_all(user, view)
    assert view["judgement"]["ACTIONS_DECIDED"]["text"] == ACTIONS
    wrong = user.post(f"{DOCS}/{view['id']}/sign", json={"password": "not-the-password"})
    assert wrong.status_code == 403
    signed = user.post(f"{DOCS}/{view['id']}/sign", json={"password": PASSWORD})
    assert signed.status_code == 200, signed.text
    body = signed.json()
    signature = body["signature"]
    assert body["status"] == "SIGNED" and body["editable"] is False
    assert signature["meaning"].startswith(f"I approve version {body['version']} of the management review report")
    assert body["writer_note"] == (
        "Writer of the judgement sections and signer: same person (allowed in a trial; a pilot separates them)."
    )
    # TA-35.4: the PDF downloaded is the one signed; its SHA-256 is in the signature record.
    pdf = user.get(f"{DOCS}/{body['id']}/pdf")
    assert pdf.status_code == 200 and pdf.headers["content-type"] == "application/pdf"
    assert hashlib.sha256(pdf.content).hexdigest() == signature["pdf_sha256"]
    with SessionLocal() as db:
        record = (
            db.query(SignedApprovalRecord).filter(SignedApprovalRecord.id == uuid.UUID(signature["record_id"])).one()
        )
    assert record.content_fingerprint == signature["pdf_sha256"] and record.object_type == "QmsDocumentVersion"
    assert record.object_id == uuid.UUID(body["id"]) and record.decision_type == "QMS_DOCUMENT"
    text = pdf_text(pdf.content)
    for expected in (
        f"version {body['version']} (signed)",
        "Template version: mrr-starter-1",
        "ISO 13485 5.6.2 Management review input (pending approval)",
        PRACTICE,
        "Starter, for your consultant to confirm",
        signature["content_fingerprint"],
        "Actions decided",
        "Written by the manufacturer",
    ):
        assert expected in text, expected
    docx = user.get(f"{DOCS}/{body['id']}/docx")
    assert docx.status_code == 200 and docx.content[:2] == b"PK"
    from docx import Document

    paragraphs = "\n".join(paragraph.text for paragraph in Document(io.BytesIO(docx.content)).paragraphs)
    assert f"Exported from signed version {body['version']}" in paragraphs and signature["pdf_sha256"] in paragraphs
    assert "edits outside MDARIX are not part of this record" in paragraphs and PRACTICE in paragraphs
    assert "pending approval" in paragraphs and ACTIONS in paragraphs
    # No patient or reporter data: complaint free text never appears in a document.
    with SessionLocal() as db:
        bind_tenant(db, trial["tenant_id"])
        descriptions = [d for (d,) in db.query(Complaint.description).filter(Complaint.tenant_id == trial["tenant_id"])]
    assert descriptions and not any(item[:40] in text or item[:40] in paragraphs for item in descriptions)

    # TA-35.3: a signed version is never edited; a new generation is the next version, and both are listed.
    again = user.put(f"{DOCS}/{body['id']}/judgement/ACTIONS_DECIDED", json={"text": "Changed after signing, again."})
    assert again.status_code == 409 and again.json()["detail"]["code"] == "SIGNED_VERSION_NOT_EDITABLE"
    assert user.post(f"{DOCS}/{body['id']}/sign", json={"password": PASSWORD}).status_code == 409
    second = _generate(user, "MANAGEMENT_REVIEW", period_days=90).json()
    assert second["version"] == body["version"] + 1 and second["judgement"] == {}
    listed = user.get(DOCS, params={"code": "MANAGEMENT_REVIEW"}).json()["items"]
    assert [item["version"] for item in listed][:2] == [second["version"], body["version"]]
    assert user.get(f"{DOCS}/{body['id']}").json()["judgement"]["ACTIONS_DECIDED"]["text"] == ACTIONS
    second = _write_all(user, second)
    assert user.post(f"{DOCS}/{second['id']}/sign", json={"password": PASSWORD}).status_code == 200
    assert user.get(f"{DOCS}/{body['id']}").json()["superseded_by"] == second["version"]

    # The filing reference and the minutes spent sit beside the signed version.
    assert user.put(f"{DOCS}/{second['id']}/filing", json={"qms_reference": "x"}).status_code == 200
    filed = user.put(f"{DOCS}/{body['id']}/filing", json={"qms_reference": "QMS-MR-2026-04", "minutes_spent": 12})
    assert filed.status_code == 200 and filed.json()["filing"]["qms_reference"] == "QMS-MR-2026-04"
    draft = _generate(user, "CAPA_LOG").json()
    assert user.put(f"{DOCS}/{draft['id']}/filing", json={"qms_reference": "x"}).status_code == 409

    # Chapter 9 counts a signed document.
    chapters = {item["code"]: item for item in user.get("/api/v1/trial/story").json()["chapters"]}
    chapter = chapters["SHOW_THE_INSPECTOR"]
    assert chapter["title"] == "File ready-to-use documents" and chapter["acted"]["count"] >= 2
    assert chapter["opens"].items() >= {"section": "Records", "tab": "Reports"}.items()


def test_the_capa_log_lists_every_imported_capa_with_its_source_and_effectiveness(trial):
    view = _generate(trial["user"], "CAPA_LOG").json()
    rows = _section(view, "CAPAS")["rows"]
    capa = next(row for row in rows if row["text"].startswith("SAMPLE-CAPA-01"))
    assert "effectiveness:" in capa["text"] and "Status " in capa["text"] and capa["sources"][0]["type"] == "Capa"
    assert view["period"]["days"] == 90 and view["sections"][0]["rows"][0]["text"].endswith("with no check planned.")
    assert [section["kind"] for section in view["sections"]] == ["data", "data"]  # no judgement section
    signed = trial["user"].post(f"{DOCS}/{view['id']}/sign", json={"password": PASSWORD})
    assert signed.status_code == 200, signed.text


def test_the_investigation_report_carries_scope_hypotheses_and_the_decision(trial):
    case = _case(trial, "SAMPLE-INV-001")
    missing = _generate(trial["user"], "INVESTIGATION_REPORT")
    assert missing.status_code == 422 and missing.json()["detail"]["code"] == "CASE_REQUIRED"
    view = _generate(trial["user"], "INVESTIGATION_REPORT", case_id=case["id"]).json()
    assert view["scope_ref"] == f"case SAMPLE-INV-001 ({case['ref']})" and view["period"] is None
    assert [clause["state"] for clause in view["clauses"]] == ["pending approval", "pending approval"]
    scope = _texts(_section(view, "SCOPE"))
    assert scope[0].startswith(f"Case SAMPLE-INV-001 ({case['ref']}) on OrbitCare 300") and any(
        t.startswith("Scope version 1") for t in scope
    )
    assert _section(view, "HYPOTHESES")["rows"] and _section(view, "EVIDENCE")["rows"][0]["sources"]
    assert _section(view, "ROOT_CAUSE")["rows"][0]["sources"]
    assert _section(view, "ROOT_CAUSE_CATEGORY") == {
        "key": "ROOT_CAUSE_CATEGORY",
        "title": "Root-cause category",
        "kind": "judgement",
        "prompt": "The root-cause category under your own coding (until MDARIX codes it).",
    }
    listed = trial["user"].get(DOCS, params={"code": "INVESTIGATION_REPORT", "scope_id": case["id"]}).json()["items"]
    assert [item["id"] for item in listed] == [view["id"]]


def test_the_risk_review_extract_and_the_risk_impact_report_show_the_risk_control_answers(trial):
    user, tenant_id = trial["user"], trial["tenant_id"]
    case = _case(trial, "SAMPLE-INV-001")
    owner = user.get("/api/v1/auth/session").json().get("user_id") or str(uuid.uuid4())
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        risk = (
            db.query(Risk)
            .join(
                Investigation,
                (Investigation.tenant_id == Risk.tenant_id) & (Investigation.product_id == Risk.product_id),
            )
            .filter(Risk.tenant_id == tenant_id, Investigation.id == uuid.UUID(case["id"]))
            .order_by(Risk.risk_identifier)
            .first()
        )
        named = f"{risk.risk_identifier} ({risk.description})"
        due = (date.today() + timedelta(days=30)).isoformat()
        now = datetime.now(timezone.utc)
        db.add(
            CaseReview(
                tenant_id=tenant_id,
                investigation_id=uuid.UUID(case["id"]),
                review_type="RISK",
                status="COMPLETED",
                requested_by=owner,
                reviewer_user_id=uuid.UUID(owner) if len(owner) == 36 else None,
                outcome="RISK_FILE_REASSESSMENT_REQUIRED",
                rationale="Post-market data reviewed against the risk file.",
                assessed={
                    "risk_ids": [str(risk.id)],
                    "findings": {
                        str(risk.id): {
                            "kind": "IN_RISK_FILE",
                            "risk_id": str(risk.id),
                            "control_worked": "NO",
                            "reason": "The pressure alarm did not sound, against its specification.",
                            "risk_file_update": {"owner_user_id": owner, "due_on": due, "qms_reference": None},
                        },
                        "NEW-1": {
                            "kind": "NOT_IN_RISK_FILE",
                            "description": "Controller switched off on battery during transport.",
                            "reason": None,
                            "risk_file_update": {"owner_user_id": owner, "due_on": due, "qms_reference": "RM-17"},
                        },
                    },
                },
                completed_at=now,
                created_at=now,
                updated_at=now,
            )
        )
        db.commit()
    view = _generate(user, "RISK_REVIEW_EXTRACT", case_id=case["id"]).json()
    answers = _texts(_section(view, "CONTROL_ANSWERS"))
    assert answers == [
        f"{named}: did its risk control work? No, it did not work. "
        "Reason: The pressure alarm did not sound, against its specification."
    ]
    updates = _texts(_section(view, "RISK_FILE_UPDATES"))
    assert len(updates) == 2 and all("owner " in text and f"due {due}" in text for text in updates)
    assert any(
        "not in the risk file: Controller switched off on battery" in text and "RM-17" in text for text in updates
    )
    assert _section(view, "CLOSURE")["rows"][0]["text"].startswith("Risk review ")
    assert [clause["short"] for clause in view["clauses"]] == ["ISO 14971 clause 10"]
    # The management review report's PMS loop carries the same answers.
    review = _generate(user, "MANAGEMENT_REVIEW", period_days=90).json()
    assert answers[0] in _texts(_section(review, "PMS"))
    # The governed RISK_IMPACT report shows them too.
    report = user.post("/api/v1/stage3/reports/RISK_IMPACT", params={"output_format": "JSON"})
    assert report.status_code == 200, report.text
    context = report.json()["context"]
    assert context["summary"]["risk_control_answers"] == 1 and context["summary"]["risk_file_updates_required"] == 2
    assert context["risk_control_answers"][0]["statement"] == answers[0]


def test_the_change_impact_input_names_the_affected_products_lots_and_assessments(trial):
    change = next(item for item in trial["types"]["changes"] if item["ref"] == "SAMPLE-CHG-014")
    view = _generate(trial["user"], "CHANGE_IMPACT", change_id=change["id"]).json()
    assert view["scope_ref"] == "change record SAMPLE-CHG-014"
    assert _section(view, "CHANGE")["note"].startswith("The change itself is run in your QMS.")
    assert _texts(_section(view, "AFFECTED")) == ["OrbitCare 300 Infusion Pump (Sample) Rev B."]
    lots = _texts(_section(view, "LOTS"))
    assert [text.split(":")[0] for text in lots] == [
        "SAMPLE-ORBIT-300-LOT-003",
        "SAMPLE-ORBIT-300-LOT-004",
        "SAMPLE-ORBIT-300-LOT-005",
        # Rev B lots without complaints, added to the sample by 0.10.61 (lot impact): built after the change too.
        "SAMPLE-ORBIT-300-LOT-006",
        "SAMPLE-ORBIT-300-LOT-007",
        "SAMPLE-ORBIT-300-LOT-008",
    ]
    assert all(row["sources"][0]["type"] == "Lot" for row in _section(view, "LOTS")["rows"])
    # The complaints whose market assessments may need review: RV-08 (US pending) and RV-06 (harm, not assessed yet).
    with SessionLocal() as db:
        bind_tenant(db, trial["tenant_id"])
        refs = dict(
            db.query(Complaint.complaint_identifier, Complaint.business_id).filter(
                Complaint.tenant_id == trial["tenant_id"],
                Complaint.complaint_identifier.in_(["SAMPLE-RV-06", "SAMPLE-RV-08"]),
            )
        )
    assert sorted(_texts(_section(view, "REASSESS"))) == sorted(
        [f"{refs['SAMPLE-RV-06']}: harm reported, no market assessment yet.", f"{refs['SAMPLE-RV-08']}: US pending."]
    )


def test_another_organization_reads_no_document_and_sample_removal_takes_them(trial):
    from tests.test_reporting_capa_api import _client, _organization

    user, tenant_id = trial["user"], trial["tenant_id"]
    mine = user.get(DOCS).json()["items"]
    assert mine
    other = _client(_organization("DOC"), "LEADER")
    assert other.get(f"{DOCS}/{mine[0]['id']}").status_code == 404
    assert other.get(f"{DOCS}/{mine[0]['id']}/pdf").status_code == 404
    assert (
        other.put(f"{DOCS}/{mine[0]['id']}/judgement/ACTIONS_DECIDED", json={"text": "Not mine to write."}).status_code
        == 404
    )
    assert other.get(DOCS).json()["items"] == []
    if runtime_role_active():
        for tenant, expected in ((uuid.uuid4(), False), (tenant_id, True)):
            runtime = RuntimeSessionLocal()
            try:
                bind_tenant(runtime, tenant)
                count = runtime.query(ReportJob).filter(ReportJob.tenant_id == tenant_id).count()
                assert (count > 0) == expected
            finally:
                runtime.close()

    removed = user.post("/api/v1/trial/sample-data/removal", json={"confirm": True})
    assert removed.status_code == 200, removed.text
    assert user.get(DOCS).json()["items"] == []
    with SessionLocal() as db:
        left = (
            db.query(SignedApprovalRecord)
            .filter(
                SignedApprovalRecord.tenant_id == tenant_id, SignedApprovalRecord.object_type == "QmsDocumentVersion"
            )
            .count()
        )
    assert left == 0


def test_a_document_signed_before_the_unicode_pdf_writer_still_verifies(trial, monkeypatch):
    """0.10.62 changed the PDF writer (embedded fonts). A version signed earlier keeps the PDF that was signed: the
    download is the stored file, its SHA-256 is still the signed one, and the signature hash still recomputes."""
    from backend.app.human_decision.rules import signature_hash
    from reports import pdf as writer

    user = trial["user"]
    view = _write_all(user, _generate(user, "MANAGEMENT_REVIEW", period_days=90).json())
    legacy = b"%PDF-1.4\n% a file written by the writer before 0.10.62\n%%EOF\n"
    monkeypatch.setattr(writer, "render", lambda *args, **kwargs: legacy)
    signed = user.post(f"{DOCS}/{view['id']}/sign", json={"password": PASSWORD})
    assert signed.status_code == 200, signed.text
    monkeypatch.undo()  # today's writer from here on
    body = signed.json()
    signature = body["signature"]
    assert signature["pdf_sha256"] == hashlib.sha256(legacy).hexdigest()
    download = user.get(f"{DOCS}/{body['id']}/pdf")
    assert download.status_code == 200 and download.content == legacy
    with SessionLocal() as db:
        record = (
            db.query(SignedApprovalRecord).filter(SignedApprovalRecord.id == uuid.UUID(signature["record_id"])).one()
        )
    assert record.content_fingerprint == hashlib.sha256(download.content).hexdigest()
    assert record.signature_hash == signature_hash(
        record.content_fingerprint, record.signer_user_id, record.object_version
    )
