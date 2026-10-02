"""One ingestion path: CSV uploads and mapped connector records both land in Product 360 through the checked import."""

import uuid

import pytest
from sqlalchemy import text

from backend.app.db.session import engine
from tests.conftest import authenticated_client
from tests.test_business_permissions import _client_with_role

SOURCES = ("CSV_IMPORT", "CONNECTOR:%")


def _cleanup():
    with engine.begin() as connection:
        for table in ("complaints", "lot_batches", "product_versions", "products"):
            connection.execute(
                text(f"DELETE FROM {table} WHERE source_system = 'CSV_IMPORT' OR source_system LIKE 'CONNECTOR:%'")
            )


@pytest.fixture(autouse=True, scope="module")
def _clean():
    _cleanup()
    yield
    _cleanup()


def test_a_workspace_csv_import_shows_up_in_product_360():
    investigator = _client_with_role("Investigator")
    product_id = f"IMP-{uuid.uuid4().hex[:6].upper()}"
    products = f"product_id,product_name,version,product_family\n{product_id},Import Pump,Rev A,Infusion\n"
    check = investigator.post("/api/v1/data/import/products/check", content=products).json()
    assert check["ready"] and check["new_records"] == 2 and check["row_limit"] is None
    assert investigator.post("/api/v1/data/import/products", content=products).status_code == 200
    complaints = f"complaint_id,product_id,description,version\nC-{product_id},{product_id},Alarm without cause,Rev A\n"
    assert investigator.post("/api/v1/data/import/complaints", content=complaints).status_code == 200

    listed = {item["product_identifier"]: item for item in investigator.get("/api/v1/products").json()}
    assert product_id in listed
    view = investigator.get(f"/api/v1/products/{listed[product_id]['id']}/product-360").json()
    assert view["product"]["product_identifier"] == product_id


def test_products_without_a_version_import_the_product_only():
    investigator = _client_with_role("Investigator")
    product_id = f"IMP-{uuid.uuid4().hex[:6].upper()}"
    result = investigator.post(
        "/api/v1/data/import/products", content=f"product_id,product_name\n{product_id},Catalog only\n"
    ).json()
    assert result["created"] == 1


def test_import_needs_permission_and_rejects_personal_data():
    viewer = _client_with_role("Viewer")
    refused = viewer.post("/api/v1/data/import/products/check", content="product_id,product_name\nP,Q\n")
    assert refused.status_code == 403 and refused.json()["detail"]["code"] == "PERMISSION_DENIED"
    investigator = _client_with_role("Investigator")
    personal = investigator.post(
        "/api/v1/data/import/products/check",
        content="product_id,product_name\nP-1,Reported by Dr. Smith on 555-123-4567\n",
    ).json()
    assert not personal["ready"] and "personal data" in personal["issues"][0]["message"]


def _complaint_source(identifier: str):
    with engine.connect() as connection:
        return connection.execute(
            text("SELECT source_system FROM complaints WHERE complaint_identifier = :identifier"),
            {"identifier": identifier},
        ).scalar()


def _action(client, mapping_id: str, action: str):
    return client.post(
        f"/api/v1/admin/configuration/mappings/{mapping_id}/release-action",
        json={"action": action, "reason": f"{action.title()} after review of the field mapping"},
    )


def _release(admin, mapping_id: str) -> None:
    """The governed workflow: request approval, approval by a second administrator, release."""
    assert _action(admin, mapping_id, "REQUEST_APPROVAL").status_code == 200
    second_admin = _client_with_role("CUSTOMER_ADMIN")
    approved = _action(second_admin, mapping_id, "APPROVE")
    assert approved.status_code == 200, approved.text
    assert _action(admin, mapping_id, "PROMOTE").status_code == 200


def _released_complaint_connector(admin, product_id: str) -> str:
    mapping = admin.post(
        "/api/v1/admin/configuration/mappings",
        json={
            "code": f"TW-COMPLAINT-{uuid.uuid4().hex[:6]}",
            "source_system": "TRACKWISE",
            "target_entity": "Complaint",
            "mapping_rules": {
                "complaint_number": {"target_field": "Complaint.complaint_id", "transform": "trim"},
                "device_code": {"target_field": "Complaint.product_id", "transform": "trim"},
                "narrative": {"target_field": "Complaint.description", "transform": "trim"},
                "opened_date": {"target_field": "Complaint.received_date", "transform": "date"},
                "status": {"target_field": "Complaint.status", "transform": "lower"},
            },
        },
    )
    assert mapping.status_code == 200, mapping.text
    body = mapping.json()
    mapping_id = body.get("mapping_id") or body.get("id")
    _release(admin, mapping_id)
    code = mapping.json().get("code") or body["code"]
    connector = admin.post(
        "/api/v1/admin/configuration/connectors",
        json={"code": f"tw-{uuid.uuid4().hex[:6]}", "connector_type": "REST", "configuration": {"mapping_code": code}},
    ).json()
    assert admin.patch(
        f"/api/v1/admin/configuration/connectors/{connector['connector_id']}/status", json={"status": "ACTIVE"}
    ).is_success
    return connector["connector_id"]


def test_mapped_connector_records_become_complaints_and_a_bad_batch_writes_nothing():
    admin = authenticated_client()
    product_id = f"IMP-{uuid.uuid4().hex[:6].upper()}"
    assert admin.post(
        "/api/v1/data/import/products", content=f"product_id,product_name\n{product_id},Pump\n"
    ).is_success
    connector_id = _released_complaint_connector(admin, product_id)
    record = {
        "complaint_number": f"TW-{product_id}",
        "device_code": product_id,
        "narrative": "Occlusion alarm with no occlusion",
        "opened_date": "2026-09-01T10:00:00Z",
        "status": "OPEN",
    }
    run = admin.post(
        f"/api/v1/admin/configuration/connectors/{connector_id}/execute",
        json={"records": [record], "source_system": "TRACKWISE"},
    ).json()
    assert run["canonical_import"]["status"] == "IMPORTED" and run["canonical_import"]["created"] == 1
    assert (_complaint_source(f"TW-{product_id}") or "").startswith("CONNECTOR:")

    bad = [dict(record, complaint_number=f"TW2-{product_id}"), dict(record, complaint_number="TW3", device_code="NOPE")]
    blocked = admin.post(
        f"/api/v1/admin/configuration/connectors/{connector_id}/execute",
        json={"records": bad, "source_system": "TRACKWISE"},
    ).json()
    assert blocked["canonical_import"]["status"] == "BLOCKED"
    assert _complaint_source(f"TW2-{product_id}") is None


def _draft_mapping(admin) -> str:
    created = admin.post(
        "/api/v1/admin/configuration/mappings",
        json={
            "code": f"GOV-{uuid.uuid4().hex[:6]}",
            "source_system": "TRACKWISE",
            "target_entity": "Complaint",
            # Complete enough to import (the release gate checks it); the tests here are about the approval flow.
            "mapping_rules": {
                "complaint_number": {"target_field": "Complaint.complaint_id", "transform": "trim"},
                "device_code": {"target_field": "Complaint.product_id", "transform": "trim"},
                "narrative": {"target_field": "Complaint.description", "transform": "trim"},
            },
        },
    ).json()
    return created.get("mapping_id") or created["id"]


def test_mappings_cannot_skip_approval():
    admin = authenticated_client()
    mapping_id = _draft_mapping(admin)
    for status in ("READY_FOR_APPROVAL", "APPROVED", "ACTIVE", "RELEASED"):
        refused = admin.patch(f"/api/v1/admin/configuration/mappings/{mapping_id}/status", json={"status": status})
        assert refused.status_code == 409 and refused.json()["detail"]["code"] == "MAPPING_STATUS_GOVERNED"
    # Promotion needs an approval first, and the requester cannot approve their own request.
    assert _action(admin, mapping_id, "PROMOTE").status_code == 409
    assert _action(admin, mapping_id, "REQUEST_APPROVAL").status_code == 200
    own = _action(admin, mapping_id, "APPROVE")
    assert own.status_code == 403 and own.json()["detail"]["code"] == "SOD_DENIED"
    assert _action(admin, mapping_id, "PROMOTE").status_code == 409


def test_an_approved_but_unreleased_mapping_cannot_import():
    admin = authenticated_client()
    mapping_id = _draft_mapping(admin)
    assert _action(admin, mapping_id, "REQUEST_APPROVAL").status_code == 200
    assert _action(_client_with_role("CUSTOMER_ADMIN"), mapping_id, "APPROVE").status_code == 200
    code = next(
        item["code"]
        for item in admin.get("/api/v1/admin/configuration/mappings").json()
        if (item.get("id") or item.get("mapping_id")) == mapping_id
    )
    connector = admin.post(
        "/api/v1/admin/configuration/connectors",
        json={"code": f"gov-{uuid.uuid4().hex[:6]}", "connector_type": "REST", "configuration": {"mapping_code": code}},
    ).json()
    admin.patch(f"/api/v1/admin/configuration/connectors/{connector['connector_id']}/status", json={"status": "ACTIVE"})
    run = admin.post(
        f"/api/v1/admin/configuration/connectors/{connector['connector_id']}/execute",
        json={"records": [{"complaint_number": "GOV-1"}], "source_system": "TRACKWISE"},
    ).json()
    assert run["canonical_import"]["status"] == "BLOCKED"
