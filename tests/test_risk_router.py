"""Risk & Traceability reads the organization's real risks, failure modes, controls and requirements."""

import re
import uuid

import pytest
from sqlalchemy import text

from backend.app.db.session import engine
from tests.reports_seed import cleanup, role_client, seed_case


@pytest.fixture(scope="module")
def seeded():
    seed = seed_case()
    yield seed
    cleanup(seed)


def test_the_register_lists_a_risk_with_its_links(seeded):
    client = role_client("VIEWER")[0]
    response = client.get("/api/v1/risk/register", params={"product_id": seeded["product_id"]})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["total"] == 1 and response.headers["X-Total-Count"] == "1" and body["next_offset"] is None
    risk = body["items"][0]
    tag = seeded["tag"]
    assert risk["risk_identifier"] == f"R-{tag}" and risk["product"]["product_identifier"] == f"P-{tag}"
    assert [row["failure_mode_identifier"] for row in risk["failure_modes"]] == [f"FM-{tag}"]
    assert [row["control_identifier"] for row in risk["controls"]] == [f"CTL-{tag}"]
    assert risk["controls"][0]["verification_evidence"][0]["evidence_identifier"] == f"EV-{tag}-V"
    assert [row["requirement_identifier"] for row in risk["requirements"]] == [f"REQ-{tag}"]
    assert risk["residual_risk"]["state"] == "CONTROLLED_WITH_VERIFICATION_EVIDENCE"
    for field in ("hazard", "harm", "severity", "probability", "risk_level"):
        assert risk[field] is None and field in body["fields_not_captured"]


def test_the_register_pages(seeded):
    client = role_client("VIEWER")[0]
    first = client.get("/api/v1/risk/register", params={"limit": 1})
    body = first.json()
    assert len(body["items"]) == 1 and body["total"] >= 2 and body["next_offset"] == 1
    second = client.get("/api/v1/risk/register", params={"limit": 1, "offset": 1}).json()
    assert second["items"][0]["id"] != body["items"][0]["id"]


def test_traceability_shows_chains_and_unlinked_records(seeded):
    body = role_client("VIEWER")[0].get("/api/v1/risk/traceability").json()
    tag = seeded["tag"]
    chain = next(item for item in body["chains"] if item["risk_identifier"] == f"R-{tag}")
    assert chain["complete"] is True and chain["verification_evidence"] == [f"EV-{tag}-V"]
    assert f"CTL-{tag}-U" in body["unlinked"]["controls_without_risk"]
    assert body["counts"]["unlinked"]["controls_without_risk"] == len(body["unlinked"]["controls_without_risk"])
    assert body["counts"]["complete_chains"] >= 1


def test_review_requests_are_permissioned_validated_and_audited(seeded):
    path = f"/api/v1/risk/{seeded['risk_id']}/review-request"
    assert role_client("VIEWER")[0].post(path, json={"reason": "Field data changed"}).status_code == 403
    investigator = role_client("INVESTIGATOR")[0]
    assert investigator.post(path, json={"reason": "too short"}).status_code == 422
    missing = investigator.post(f"/api/v1/risk/{uuid.uuid4()}/review-request", json={"reason": "Field data changed"})
    assert missing.status_code == 404
    made = investigator.post(path, json={"reason": "New complaints suggest the control is insufficient"})
    assert made.status_code == 200, made.text
    body = made.json()
    assert body["status"] == "REVIEW_REQUESTED" and body["risk_identifier"] == f"R-{seeded['tag']}"
    with engine.connect() as connection:
        reason = connection.execute(
            text("SELECT reason FROM audit_events WHERE id = :id AND action = 'RISK_REVIEW_REQUESTED'"),
            {"id": body["audit_event_id"]},
        ).scalar()
    assert reason == "New complaints suggest the control is insufficient"


def test_the_csv_export_is_formula_safe_and_needs_export_permission(seeded):
    assert role_client("VIEWER")[0].get("/api/v1/risk/export.csv").status_code == 403
    response = role_client("INVESTIGATOR")[0].get(
        "/api/v1/risk/export.csv", params={"product_id": seeded["product_id"]}
    )
    assert response.status_code == 200 and response.headers["content-type"].startswith("text/csv")
    lines = response.text.strip().splitlines()
    assert lines[0].startswith("business_id,risk_identifier,description")
    assert re.match(rf"RSK\d{{6}},R-{seeded['tag']},", lines[1])
    # The seeded description is a spreadsheet command; it is exported as text.
    assert "'=cmd" in lines[1] and ",=cmd" not in lines[1]
    assert f"CTL-{seeded['tag']}" in lines[1] and "not captured" in lines[1]


def test_the_register_and_traceability_carry_business_ids(seeded):
    client = role_client("VIEWER")[0]
    risk = client.get("/api/v1/risk/register", params={"product_id": seeded["product_id"]}).json()["items"][0]
    assert re.fullmatch(r"RSK\d{6}", risk["business_id"])
    assert re.fullmatch(r"PROD\d{6}", risk["product"]["business_id"])
    assert re.fullmatch(r"FM\d{6}", risk["failure_modes"][0]["business_id"])
    assert re.fullmatch(r"CTL\d{6}", risk["controls"][0]["business_id"])
    assert re.fullmatch(r"EVD\d{6}", risk["controls"][0]["verification_evidence"][0]["business_id"])
    assert re.fullmatch(r"REQ\d{6}", risk["requirements"][0]["business_id"])
    body = client.get("/api/v1/risk/traceability").json()
    chain = next(item for item in body["chains"] if item["risk_id"] == risk["id"])
    assert chain["risk_business_id"] == risk["business_id"]
    assert chain["control_business_ids"] == [risk["controls"][0]["business_id"]]
    assert len(chain["verification_evidence_business_ids"]) == len(chain["verification_evidence"])
    for key, identifiers in body["unlinked"].items():
        assert len(body["unlinked_business_ids"][key]) == len(identifiers)
