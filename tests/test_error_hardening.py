"""Inputs that used to crash the server (HTTP 500) now get a clear answer."""

import pytest
import uuid
from types import SimpleNamespace

from backend.app.access.connector_mapping import import_connector_records
from tests.test_business_permissions import _client_with_role
from tests.test_supplier_evidence_requests import own_supplier


@pytest.mark.db
def test_a_duplicate_connector_or_mapping_code_is_refused_clearly():
    admin = _client_with_role("CUSTOMER_ADMIN")
    code = f"DUP_{uuid.uuid4().hex[:8].upper()}"
    connector = {"code": code, "connector_type": "TEST", "configuration": {}}
    assert admin.post("/api/v1/admin/configuration/connectors", json=connector).status_code == 200
    again = admin.post("/api/v1/admin/configuration/connectors", json=connector)
    assert again.status_code == 409 and again.json()["detail"]["code"] == "CONNECTOR_CODE_EXISTS"
    mapping = {
        "code": code,
        "source_system": "X",
        "target_entity": "Product",
        "mapping_rules": {"id": {"target_field": "Product.product_id", "transform": "trim"}},
    }
    assert admin.post("/api/v1/admin/configuration/mappings", json=mapping).status_code == 200
    again = admin.post("/api/v1/admin/configuration/mappings", json=mapping)
    assert again.status_code == 409 and again.json()["detail"]["code"] == "MAPPING_CODE_EXISTS"


def test_a_value_that_cannot_be_converted_blocks_the_batch_with_a_report():
    mapping = SimpleNamespace(
        code="M1",
        target_entity="Complaint",
        mapping_rules={
            "id": {"target_field": "Complaint.complaint_id", "transform": "trim"},
            "opened": {"target_field": "Complaint.event_date", "transform": "date"},
        },
    )
    result = import_connector_records(None, uuid.uuid4(), "C1", mapping, [{"id": "A", "opened": "not-a-date"}])
    assert result["status"] == "BLOCKED"
    issue = result["report"]["issues"][0]
    assert issue["row"] == 1 and issue["column"] == "opened" and "not-a-date" in issue["message"]


@pytest.mark.db
def test_ask_refuses_bad_or_foreign_references_cleanly():
    user = _client_with_role("INVESTIGATOR")
    long_context = user.post("/api/v1/stage3/interactions", json={"prompt": "Hi", "page_context": "x" * 121})
    assert long_context.status_code == 422
    odd_mode = user.post("/api/v1/stage3/interactions", json={"prompt": "Hi", "temporal_mode": "'; DROP TABLE x;--"})
    assert odd_mode.status_code == 422
    for field in ("investigation_id", "product_id", "product_version_id"):
        foreign = user.post("/api/v1/stage3/interactions", json={"prompt": "Hi", field: str(uuid.uuid4())})
        assert foreign.status_code == 404, (field, foreign.text)


@pytest.mark.db
def test_uploads_keep_only_a_safe_name_and_must_be_what_they_claim():
    user = _client_with_role("INVESTIGATOR")
    made = user.post(
        "/api/v1/stage3/supplier-evidence-requests",
        json={
            "recipient": "supplier@example.invalid",
            "title": "CoC",
            "requested_items": ["CoC"],
            "supplier_id": own_supplier(user),
        },
    )
    assert made.status_code == 200, made.text
    path = f"/api/v1/stage3/supplier-evidence-requests/{made.json()['id']}/attachments"
    traversal = user.post(path, files={"file": ("../../../../windows/win.ini", b"hello", "text/plain")})
    assert traversal.status_code == 200 and traversal.json()["filename"] == "win.ini"
    disguised = user.post(path, files={"file": ("photo.png", b"not really a png", "image/png")})
    assert disguised.status_code == 415 and disguised.json()["detail"]["code"] == "ATTACHMENT_CONTENT_MISMATCH"


@pytest.mark.db
def test_decisions_made_in_the_same_second_get_distinct_identifiers():
    from backend.app.db.models.foundation import Investigation, Tenant
    from backend.app.db.session import SessionLocal
    from backend.app.db.tenant_scope import bind_system

    with SessionLocal() as db:
        bind_system(db, "test: pick a case")
        tenant = db.query(Tenant).filter(Tenant.tenant_key == "ACME_CARE_SYNTHETIC").first()
        case = db.query(Investigation.id).filter(Investigation.tenant_id == tenant.id).first()[0]
    user = _client_with_role("INVESTIGATOR")
    body = {"selected_action": "CONTINUE_INVESTIGATION", "rationale": "Same second", "decision_type": "DISPOSITION"}
    made = [user.post(f"/api/v1/investigations/{case}/decisions", json=body) for _ in range(3)]
    assert all(response.status_code == 200 for response in made), [r.text for r in made]
    assert len({response.json()["decision_identifier"] for response in made}) == 3
