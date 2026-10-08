"""Product 360, regulatory documents and the product graph return each record's business identifier (md26)."""

import re
import uuid

from fastapi.testclient import TestClient
from sqlalchemy import text

from backend.app.db.session import engine
from backend.app.main import app
from tests.test_business_permissions import _client_with_role

# Signed in by conftest (LEGACY_PROTECTED) when each test runs, once the golden organization exists: a session made
# at import would put the shared test account in whichever organization exists first on a fresh database.
client = TestClient(app)


def _primary_product() -> str:
    with engine.connect() as conn:
        return str(conn.execute(text("SELECT id FROM products WHERE product_identifier='PRD-ASTER-100'")).scalar_one())


def test_the_product_list_carries_business_ids():
    response = client.get("/api/v1/products")
    assert response.status_code == 200, response.text
    product = next(item for item in response.json() if item["product_identifier"] == "PRD-ASTER-100")
    assert re.fullmatch(r"PROD\d{6}", product["business_id"])


def test_product360_lists_every_record_with_its_business_id():
    payload = client.get(f"/api/v1/products/{_primary_product()}/product-360", params={"version_id": "D"}).json()
    assert re.fullmatch(r"PROD\d{6}", payload["product"]["business_id"])
    assert re.fullmatch(r"PV\d{6}", payload["selected_version"]["business_id"])
    expected = {
        "complaints": r"CMP\d{6}",
        "investigations": r"INV\d{6}",
        "risks": r"RSK\d{6}",
        "failure_modes": r"FM\d{6}",
        "controls": r"CTL\d{6}",
        "changes": r"CHG\d{6}",
        "evidence": r"EVD\d{6}",
    }
    for section, pattern in expected.items():
        assert all(re.fullmatch(pattern, row["business_id"]) for row in payload[section]), section
    assert all(re.fullmatch(r"COMP\d{6}", row["business_id"]) for row in payload["configuration"]["components"])
    assert all(re.fullmatch(r"SUP\d{6}", row["business_id"]) for row in payload["configuration"]["suppliers"])
    assert all(re.fullmatch(r"LOT\d{6}", row["business_id"]) for row in payload["manufacturing"]["lots"])
    assert all(re.fullmatch(r"SITE\d{6}", row["business_id"]) for row in payload["manufacturing"]["sites"])
    complaints = {row["id"]: row["business_id"] for row in payload["complaints"]}
    for event in payload["timeline"]:
        if event["related_entity_type"] == "complaint":
            assert event["related_entity_business_id"] == complaints[event["related_entity_id"]]


def test_product_investigations_carry_business_ids():
    rows = client.get(f"/api/v1/products/{_primary_product()}/investigations").json()
    assert rows and all(re.fullmatch(r"INV\d{6}", row["business_id"]) for row in rows)


def test_regulatory_documents_carry_their_business_id():
    author = _client_with_role("INVESTIGATOR")
    identifier = f"REG-TEST-{uuid.uuid4().hex[:8]}"
    made = author.post("/api/v1/regulatory/draft", json={"document_type": "IFU", "document_identifier": identifier})
    assert made.status_code == 200, made.text
    business_id = made.json()["document_business_id"]
    assert re.fullmatch(r"RDOC\d{6}", business_id)
    document_id = made.json()["document_id"]
    assert author.get(f"/api/v1/regulatory/documents/{document_id}").json()["business_id"] == business_id
    listed = next(row for row in author.get("/api/v1/regulatory/documents").json() if row["id"] == document_id)
    assert listed["business_id"] == business_id
