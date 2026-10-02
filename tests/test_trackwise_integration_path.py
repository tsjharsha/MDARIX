"""A customer's TrackWise Digital integration, end to end: the guided mapping format imports, the release gate needs
real field rules, every sync is recorded as a run, and every new tenant has a data plane."""

import uuid

import pytest
from sqlalchemy import text

from backend.app.access.connector_mapping import check_mapping
from backend.app.db.models.customer_lifecycle import TenantDataPlane
from backend.app.db.models.enterprise import ConnectorRun
from backend.app.db.session import SessionLocal, engine
from tests.conftest import authenticated_client
from tests.test_business_permissions import _client_with_role
from tests.test_data_import_path import _action, _complaint_source, _release

# What the shared mapping wizard saves for TrackWise complaints (frontend/src/features/mapping/mappingModel.ts).
WIZARD_RULES = {
    "complaint_id": {"target_field": "Complaint.complaint_id", "transform": "trim"},
    "product_code": {"target_field": "Complaint.product_id", "transform": "trim"},
    "problem_description": {"target_field": "Complaint.description", "transform": "trim"},
    "received_date": {"target_field": "Complaint.received_date", "transform": "date"},
}


def _cleanup():
    with engine.begin() as connection:
        for table in ("complaints", "products"):
            connection.execute(text(f"DELETE FROM {table} WHERE source_system LIKE 'CONNECTOR:twi-%'"))
            connection.execute(text(f"DELETE FROM {table} WHERE source_system = 'CSV_IMPORT'"))


@pytest.fixture(autouse=True, scope="module")
def _clean():
    _cleanup()
    yield
    _cleanup()


@pytest.fixture(scope="module")
def admin():
    return authenticated_client()


def test_the_import_targets_and_conversions_are_listed_in_words(admin):
    targets = admin.get("/api/v1/admin/configuration/mapping-targets").json()
    complaint = next(item for item in targets["targets"] if item["entity"] == "Complaint")
    assert complaint["required"] == ["complaint_id", "product_id", "description"]
    assert {item["code"] for item in targets["transforms"]} >= {"identity", "trim", "date", "boolean"}
    assert all(item["label"] for item in targets["transforms"])


def test_a_mapping_is_checked_before_it_is_saved(admin):
    ready = admin.post(
        "/api/v1/admin/configuration/mappings/check",
        json={"target_entity": "Complaint", "mapping_rules": WIZARD_RULES},
    ).json()
    assert ready == {"status": "READY", "problems": [], "missing_required": [], "rule_count": 4}
    partial = check_mapping("Complaint", {"complaint_id": {"target_field": "Complaint.complaint_id"}})
    assert partial["status"] == "NEEDS_CHANGES" and partial["missing_required"] == ["product_id", "description"]
    wrong = check_mapping(
        "Complaint",
        {
            "a": {"target_field": "Complaint.severity", "transform": "trim"},
            "b": {"target_field": "Complaint.complaint_id", "transform": "ENUM_MAP"},
            "c": {"target_field": "Complaint.complaint_id", "transform": "trim"},
        },
    )
    assert any("severity" in problem for problem in wrong["problems"])
    assert any("ENUM_MAP" in problem for problem in wrong["problems"])
    assert any("more than one" in problem for problem in wrong["problems"])
    # The canonical data-model code (what the first wizard saved) is not an importable record.
    assert check_mapping("COMPLAINT", WIZARD_RULES)["status"] == "NEEDS_CHANGES"


def test_a_mapping_without_field_rules_cannot_be_released(admin):
    created = admin.post(
        "/api/v1/admin/configuration/mappings",
        json={"code": f"EMPTY-{uuid.uuid4().hex[:6]}", "source_system": "TRACKWISE", "target_entity": "Complaint"},
    ).json()
    mapping_id = created.get("mapping_id") or created["id"]
    # Saving always stores a "_configuration" settings key; it is not a rule.
    refused = _action(admin, mapping_id, "REQUEST_APPROVAL")
    assert refused.status_code == 409 and refused.json()["detail"]["code"] == "RELEASE_GATE_BLOCKED"
    check = admin.get(f"/api/v1/admin/configuration/mappings/{mapping_id}/check").json()
    assert check["status"] == "NEEDS_CHANGES" and check["rule_count"] == 0


def test_trackwise_complaints_arrive_through_a_wizard_mapping_and_each_sync_is_a_run(admin):
    product_id = f"TWI-{uuid.uuid4().hex[:6].upper()}"
    assert admin.post(
        "/api/v1/data/import/products", content=f"product_id,product_name\n{product_id},Pump\n"
    ).is_success
    code = f"TRACKWISE_COMPLAINTS_{uuid.uuid4().hex[:6].upper()}"
    created = admin.post(
        "/api/v1/admin/configuration/mappings",
        json={
            "code": code,
            "source_system": "TRACKWISE",
            "source_table": "Complaint",
            "target_entity": "Complaint",
            "target_table": "Complaint",
            "version": "v1",
            "mapping_rules": WIZARD_RULES,
        },
    ).json()
    mapping_id = created.get("mapping_id") or created["id"]
    assert admin.get(f"/api/v1/admin/configuration/mappings/{mapping_id}/check").json()["status"] == "READY"
    _release(admin, mapping_id)
    connection_code = f"twi-{uuid.uuid4().hex[:6]}"
    connector = admin.post(
        "/api/v1/admin/configuration/connectors",
        json={
            "code": connection_code,
            "connector_type": "TRACKWISE",
            "configuration": {"mapping_code": code, "source_object": "Complaint"},
        },
    ).json()
    connector_id = connector["connector_id"]
    assert admin.patch(
        f"/api/v1/admin/configuration/connectors/{connector_id}/status", json={"status": "ACTIVE"}
    ).is_success
    # TrackWise Digital complaint fields, as the catalog names them.
    record = {
        "complaint_id": f"TW-{product_id}",
        "complaint_number": "CMP-1",
        "product_code": product_id,
        "problem_description": "Occlusion alarm with no occlusion",
        "received_date": "2026-09-01T10:00:00Z",
        "severity": "MAJ",
    }
    run = admin.post(
        f"/api/v1/admin/configuration/connectors/{connector_id}/execute",
        json={"records": [record], "source_system": "TRACKWISE"},
    ).json()
    assert run["canonical_import"]["status"] == "IMPORTED", run["canonical_import"]
    assert (_complaint_source(f"TW-{product_id}") or "").startswith("CONNECTOR:")
    db = SessionLocal()
    try:
        recorded = db.query(ConnectorRun).filter(ConnectorRun.id == uuid.UUID(run["run_id"])).one()
        assert (recorded.connection_id, recorded.status, recorded.records_received, recorded.records_accepted) == (
            connection_code,
            "COMPLETED",
            1,
            1,
        )
        assert recorded.reconciliation_status == "MATCH" and recorded.source_system == "Complaint"
    finally:
        db.close()
    # A batch the import refuses is recorded as a failed run that reconciles as a mismatch.
    blocked = admin.post(
        f"/api/v1/admin/configuration/connectors/{connector_id}/execute",
        json={"records": [dict(record, complaint_id="TW-X", product_code="NO-SUCH-PRODUCT")], "source_system": "X"},
    ).json()
    assert blocked["canonical_import"]["status"] == "BLOCKED"
    db = SessionLocal()
    try:
        failed = db.query(ConnectorRun).filter(ConnectorRun.id == uuid.UUID(blocked["run_id"])).one()
        assert (failed.status, failed.records_rejected, failed.reconciliation_status) == ("FAILED", 1, "MISMATCH")
        assert failed.failure_category == "IMPORT_BLOCKED"
    finally:
        db.close()
    runs = admin.get("/api/v1/admin/integrations/runs").json()
    assert {run["run_id"], blocked["run_id"]} <= {str(item.get("id")) for item in runs}


def test_a_mapping_the_import_cannot_read_is_reported_not_a_server_error(admin):
    code = f"OLD_FORMAT_{uuid.uuid4().hex[:6].upper()}"
    created = admin.post(
        "/api/v1/admin/configuration/mappings",
        json={
            "code": code,
            "source_system": "TRACKWISE",
            "target_entity": "Complaint",
            # A rule without "<Entity>.<column>": the import cannot use it.
            "mapping_rules": {"complaint_id": {"target_field": "complaint_id", "transform": "trim"}},
        },
    ).json()
    _release(admin, created.get("mapping_id") or created["id"])
    connector = admin.post(
        "/api/v1/admin/configuration/connectors",
        json={
            "code": f"twi-{uuid.uuid4().hex[:6]}",
            "connector_type": "TRACKWISE",
            "configuration": {"mapping_code": code},
        },
    ).json()
    admin.patch(f"/api/v1/admin/configuration/connectors/{connector['connector_id']}/status", json={"status": "ACTIVE"})
    response = admin.post(
        f"/api/v1/admin/configuration/connectors/{connector['connector_id']}/execute",
        json={"records": [{"complaint_id": "X-1"}], "source_system": "TRACKWISE"},
    )
    assert response.status_code == 200
    assert response.json()["canonical_import"]["status"] == "BLOCKED"


def test_customer_administrators_can_read_the_source_catalog_but_not_change_it():
    customer_admin = _client_with_role("CUSTOMER_ADMIN")
    assert customer_admin.get("/api/v1/admin/mapping/applications").status_code == 200
    assert customer_admin.get("/api/v1/admin/mapping/applications/TRACKWISE/objects").status_code == 200
    fields = customer_admin.get("/api/v1/admin/mapping/objects/TRACKWISE:COMPLAINT/fields")
    assert fields.status_code == 200 and any(field["field_name"] == "complaint_id" for field in fields.json())
    assert customer_admin.get("/api/v1/admin/configuration/mapping-targets").status_code == 200
    # Checks and catalog changes stay platform-only.
    assert customer_admin.post("/api/v1/admin/mapping/validate", json={"entity_id": "COMPLAINT"}).status_code == 403
    assert _client_with_role("Investigator").get("/api/v1/admin/mapping/applications").status_code == 403


@pytest.mark.parametrize("how", ["customer", "onboarding", "add_tenant"])
def test_every_new_tenant_gets_a_data_plane(admin, how):
    suffix = uuid.uuid4().hex[:6].upper()
    if how == "customer":
        tenant_id = admin.post(
            "/api/v1/platform-admin/customers",
            json={"company_name": f"Plane {suffix}", "tenant_code": f"PLN{suffix}", "plan_code": "STARTER"},
        ).json()["id"]
    elif how == "onboarding":
        provisioned = admin.post(
            "/api/v1/platform/tenants/provision",
            json={
                "company_name": f"Plane {suffix}",
                "tenant_code": f"PLO{suffix}",
                "plan_code": "STARTER",
                "customer_admin_email": f"plane-{suffix.lower()}@example.invalid",
                "customer_admin_display_name": "Plane Admin",
                "invitation_required": False,
            },
        )
        assert provisioned.status_code == 200, provisioned.text
        tenant_id = provisioned.json()["tenant_id"]
    else:
        customer = admin.post(
            "/api/v1/platform-admin/customers",
            json={"company_name": f"Plane {suffix}", "tenant_code": f"PLA{suffix}", "plan_code": "STARTER"},
        ).json()
        db = SessionLocal()
        try:
            from backend.app.db.models.foundation import PlanDefinition

            plan_id = str(db.query(PlanDefinition.id).filter(PlanDefinition.code == "STARTER").scalar())
        finally:
            db.close()
        added = admin.post(
            f"/api/v1/platform-admin/customer-records/{customer['customer_id']}/tenants",
            json={
                "tenant_name": f"Second {suffix}",
                "tenant_code": f"PLB{suffix}",
                "environment_type": "PRODUCTION",
                "data_region": "eu-central-1",
                "plan_id": plan_id,
                "admin_email": f"second-{suffix.lower()}@example.invalid",
                "admin_display_name": "Second Admin",
                "reason": "Second tenant for the data plane test",
            },
        )
        assert added.status_code == 200, added.text
        tenant_id = added.json()["tenant"]["id"]
    db = SessionLocal()
    try:
        plane = db.query(TenantDataPlane).filter(TenantDataPlane.tenant_id == uuid.UUID(tenant_id)).one()
        assert plane.status == "ACTIVE" and plane.database_ref.startswith("shared-control:")
    finally:
        db.close()
