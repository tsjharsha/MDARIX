"""The twelve governed reports carry the organization's real records, in JSON, formula-safe CSV and PDF."""

import pytest

from reports.pdf import page_count
from reports.service import REPORT_VERSION, REPORTS
from tests.reports_seed import cleanup, role_client, seed_case


@pytest.fixture(scope="module")
def seeded():
    seed = seed_case()
    yield seed
    cleanup(seed)


@pytest.fixture(scope="module")
def investigator():
    return role_client("INVESTIGATOR")[0]


def _report(client, code, fmt="JSON"):
    response = client.post(f"/api/v1/stage3/reports/{code}", params={"output_format": fmt})
    assert response.status_code == 200, response.text
    return response


def _row(rows, key, value):
    return next(row for row in rows if row.get(key) == value)


def test_every_report_is_tenant_scoped_dated_and_needs_human_review(seeded, investigator):
    for code in REPORTS:
        body = _report(investigator, code).json()
        assert body["report_type"] == code and body["report_version"] == REPORT_VERSION
        assert body["tenant"]["id"] == seeded["tenant_id"] and body["tenant"]["name"]
        assert body["generated_at"] and body["data_cut_off"]
        assert body["human_review_required"] is True
        assert body["context"]["limitations"] or body["context"].get("scope"), code


def test_product_reports_count_the_seeded_records(seeded, investigator):
    tag = seeded["tag"]
    products = _report(investigator, "PRODUCT_INTELLIGENCE").json()["context"]["products"]
    product = _row(products, "product_identifier", f"P-{tag}")
    assert (product["complaints_total"], product["investigations_total"], product["risks"]) == (1, 1, 1)
    versions = _report(investigator, "PRODUCT_VERSION_IMPACT").json()["context"]["versions"]
    version = _row(versions, "version_identifier", f"V-{tag}")
    assert (version["complaints_open"], version["investigations_via_complaints"]) == (1, 1)


def test_complaint_and_signal_reports(seeded, investigator):
    tag = seeded["tag"]
    trend = _report(investigator, "COMPLAINT_TREND").json()["context"]
    assert _row(trend["by_product"], "label", f"P-{tag}")["count"] == 1
    signals = _report(investigator, "SIGNAL_ASSESSMENT").json()["context"]["signals"]
    signal = _row(signals, "complaint_identifier", f"C-{tag}")
    assert signal["serious_injury"] is True and signal["linked_to_investigation"] is True
    assert signal["awareness_lag_days"] == 38


def test_investigation_evidence_and_decision_reports(seeded, investigator):
    tag = seeded["tag"]
    cases = _report(investigator, "INVESTIGATION").json()["context"]["investigations"]
    case = _row(cases, "investigation_identifier", f"INV-{tag}")
    assert (case["linked_complaints"], case["evidence"], case["hypotheses"], case["open_unknowns"]) == (1, 2, 1, 1)
    assert case["valid_signatures"] == 1
    evidence = _report(investigator, "EVIDENCE_PROVENANCE").json()["context"]["evidence"]
    item = _row(evidence, "evidence_identifier", f"EV-{tag}-1")
    assert item["source_system"] == "QMS" and item["source_reference"] == f"qms://reports/{tag}"
    assert item["investigation_identifier"] == f"INV-{tag}"
    decisions = _report(investigator, "DECISION_BRIEF").json()["context"]["decisions"]
    signed = _row(decisions, "decision_identifier", f"D-{tag}-S")
    assert [sig["valid"] for sig in signed["signatures"]] == [True]


def test_risk_report_follows_the_traceability_links(seeded, investigator):
    tag = seeded["tag"]
    content = _report(investigator, "RISK_IMPACT").json()["context"]
    risk = _row(content["risks"], "risk_identifier", f"R-{tag}")
    assert risk["controls"] == [f"CTL-{tag}"] and risk["failure_modes"] == [f"FM-{tag}"]
    assert risk["requirements"] == [f"REQ-{tag}"] and risk["verification_evidence"] == [f"EV-{tag}-V"]
    assert risk["residual_risk_state"] == "CONTROLLED_WITH_VERIFICATION_EVIDENCE"
    assert f"CTL-{tag}-U" in content["unlinked"]["controls_without_risk"]
    # Hazard, harm, severity and probability are not in the imported records: said so, never estimated.
    assert "severity" in content["fields_not_captured"]


def test_scenario_comparison_says_what_it_is_based_on(seeded, investigator):
    content = _report(investigator, "SCENARIO_COMPARISON").json()["context"]
    assert content["basis"] in {"SCENARIO_RECORDS", "COMPETING_HYPOTHESES"}
    if content["basis"] == "COMPETING_HYPOTHESES":
        statements = [row["statement"] for row in content["hypotheses"]]
        assert any(seeded["tag"] in statement for statement in statements)
        assert "no scenario records" in content["limitations"][0]


def test_ai_audit_and_executive_reports(seeded, investigator):
    ai = _report(investigator, "AI_ASSURANCE").json()["context"]
    assert ai["summary"]["ai_executions"] >= 1 and any(row["label"] == "PASS" for row in ai["assurance_by_status"])
    audit = _report(investigator, "AUDIT_APPROVAL").json()["context"]
    assert seeded["audit_event_id"] in {event["id"] for event in audit["audit_events"]}
    assert seeded["signature_id"] in {item["signature_id"] for item in audit["signature_verification"]}
    kpis = _report(investigator, "EXECUTIVE_QUALITY_REVIEW").json()["context"]["kpis"]
    assert kpis["products"] >= 1 and kpis["signed_approvals"] >= 1 and kpis["complaints_serious_injury_or_death"] >= 1


def test_csv_is_formula_safe_and_pdf_lists_the_records(seeded, investigator):
    tag = seeded["tag"]
    csv_response = _report(investigator, "SIGNAL_ASSESSMENT", "CSV")
    assert csv_response.headers["content-type"].startswith("text/csv")
    assert "attachment" in csv_response.headers["content-disposition"]
    text = csv_response.text
    assert f"C-{tag}" in text and "human_review_required" in text
    assert "'=HYPERLINK" in text and ",=HYPERLINK" not in text
    pdf = _report(investigator, "INVESTIGATION", "PDF").content
    assert pdf.startswith(b"%PDF") and f"INV-{tag}".encode() in pdf and page_count(pdf) >= 1
    assert b"Human review required" in pdf


def test_report_jobs_render_the_same_content(seeded, investigator):
    job = investigator.post("/api/v1/stage3/reports/RISK_IMPACT/jobs", params={"output_format": "CSV"})
    assert job.status_code == 200, job.text
    assert job.json()["status"] == "READY"
    download = investigator.get(f"/api/v1/stage3/reports/jobs/{job.json()['id']}/download")
    assert download.status_code == 200 and f"R-{seeded['tag']}".encode() in download.content


def test_unknown_reports_and_viewers_are_refused(investigator):
    unknown = investigator.post("/api/v1/stage3/reports/NOT_A_REPORT")
    assert unknown.status_code == 400 and unknown.json()["detail"]["code"] == "REPORT_TYPE_NOT_SUPPORTED"
    viewer = role_client("VIEWER")[0]
    assert viewer.post("/api/v1/stage3/reports/COMPLAINT_TREND").status_code == 403
