"""The investigation record export: the whole case, tenant-scoped and audited; and the evidence-package endpoint."""

import re
import uuid

import pytest
from sqlalchemy import text

from backend.app.db.session import engine
from reports.pdf import text_of
from tests.reports_seed import cleanup, role_client, seed_case

PATH = "/api/v1/stage3/investigations/{}/record"


@pytest.fixture(scope="module")
def seeded():
    seed = seed_case()
    yield seed
    cleanup(seed)


def _audited(action, entity_id) -> int:
    with engine.connect() as connection:
        return connection.execute(
            text("SELECT count(*) FROM audit_events WHERE action = :action AND entity_id = :id"),
            {"action": action, "id": entity_id},
        ).scalar()


def test_the_record_holds_the_whole_case(seeded):
    client = role_client("INVESTIGATOR")[0]
    tag = seeded["tag"]
    before = _audited("INVESTIGATION_RECORD_EXPORTED", seeded["investigation_id"])
    response = client.get(PATH.format(seeded["investigation_id"]))
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["report_type"] == "INVESTIGATION_RECORD" and body["human_review_required"] is True
    record = body["context"]
    assert record["investigation"]["investigation_identifier"] == f"INV-{tag}"
    assert record["counts"]["complaints"] == 1 and record["counts"]["evidence"] == 2
    assert record["counts"]["hypotheses"] == 1 and record["counts"]["decisions"] == 2
    assert record["counts"]["signatures"] == 1
    evidence = {item["evidence_identifier"]: item for item in record["evidence"]}
    assert evidence[f"EV-{tag}-1"]["source_reference"] == f"qms://reports/{tag}"
    assert evidence[f"EV-{tag}-1"]["effective_timestamp"]
    assert record["hypotheses"][0]["evidence"][0]["relation_type"] == "support"
    signed = next(item for item in record["decisions"] if item["decision_identifier"] == f"D-{tag}-S")
    assert signed["signatures"][0]["signature_id"] == seeded["signature_id"] and signed["signatures"][0]["valid"]
    assert seeded["audit_event_id"] in {event["id"] for event in record["audit_events"]}
    assert _audited("INVESTIGATION_RECORD_EXPORTED", seeded["investigation_id"]) == before + 1


def test_csv_and_pdf_formats(seeded):
    client = role_client("INVESTIGATOR")[0]
    tag = seeded["tag"]
    csv_response = client.get(PATH.format(seeded["investigation_id"]), params={"format": "csv"})
    assert csv_response.status_code == 200 and csv_response.headers["content-type"].startswith("text/csv")
    assert f"EV-{tag}-2" in csv_response.text and "[decisions]" in csv_response.text
    # The complaint's problem code would run as a formula; the CSV keeps it as text.
    assert "'=HYPERLINK" in csv_response.text and ",=HYPERLINK" not in csv_response.text
    pdf = client.get(PATH.format(seeded["investigation_id"]), params={"format": "pdf"})
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
    shown = text_of(pdf.content)
    assert f"INV-{tag}" in shown and seeded["signature_id"] in shown
    assert client.get(PATH.format(seeded["investigation_id"]), params={"format": "xml"}).status_code == 422


def test_unknown_cases_and_viewers_are_refused(seeded):
    client = role_client("INVESTIGATOR")[0]
    missing = client.get(PATH.format(uuid.uuid4()))
    assert missing.status_code == 404 and missing.json()["detail"]["code"] == "INVESTIGATION_NOT_FOUND"
    viewer = role_client("VIEWER")[0]
    assert viewer.get(PATH.format(seeded["investigation_id"])).status_code == 403


def test_the_compliance_pdf_lists_the_audit_events_and_signatures(seeded):
    admin = role_client("CUSTOMER_ADMIN")[0]
    response = admin.get("/api/v1/stage3/compliance-report", params={"output_format": "PDF"})
    assert response.status_code == 200 and response.content.startswith(b"%PDF")
    from reports.pdf import page_count

    assert page_count(response.content) > 1
    shown = text_of(response.content)
    assert seeded["audit_event_id"] in shown and seeded["signature_id"] in shown
    as_json = admin.get("/api/v1/stage3/compliance-report", params={"output_format": "JSON"}).json()
    assert seeded["audit_event_id"] in {event["id"] for event in as_json["context"]["audit_events"]}


def test_the_record_lists_each_record_by_business_id(seeded):
    body = role_client("INVESTIGATOR")[0].get(PATH.format(seeded["investigation_id"])).json()
    record = body["context"]
    assert re.fullmatch(r"INV\d{6}", record["investigation"]["business_id"])
    assert body["title"] == f"Investigation Record {record['investigation']['business_id']}"
    assert re.fullmatch(r"PROD\d{6}", record["investigation"]["product"]["business_id"])
    assert all(re.fullmatch(r"CMP\d{6}", item["business_id"]) for item in record["complaints"])
    assert all(re.fullmatch(r"EVD\d{6}", item["business_id"]) for item in record["evidence"])
    assert all(re.fullmatch(r"HYP\d{6}", item["business_id"]) for item in record["hypotheses"])
    assert all(re.fullmatch(r"UNK\d{6}", item["business_id"]) for item in record["unknowns"])
    signed = next(item for item in record["decisions"] if item["signatures"])
    assert re.fullmatch(r"DEC\d{6}", signed["business_id"])
    assert signed["signatures"][0]["decision_business_id"] == signed["business_id"]
    assert re.fullmatch(r"ESIG\d{6}", signed["signatures"][0]["business_id"])
