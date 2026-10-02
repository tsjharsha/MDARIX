"""MDARIX staff prepare draft mapping sheets for a customer tenant; the customer's administrators release them."""

import uuid

from backend.app.db.models.foundation import AuditEvent, Tenant
from backend.app.db.session import SessionLocal
from backend.app.db.tenant_scope import bind_system
from tests.conftest import authenticated_client
from tests.test_business_permissions import _client_with_role

RULES = {
    "item": {"target_field": "Product.product_id", "transform": "trim"},
    "name": {"target_field": "Product.product_name", "transform": "trim"},
}


def _acme() -> str:
    with SessionLocal() as db:
        bind_system(db, "test: tenant")
        return str(db.query(Tenant.id).filter(Tenant.tenant_key == "ACME_CARE_SYNTHETIC").first()[0])


def test_staff_prepare_a_draft_the_customer_sees_and_releases():
    platform, tenant_id = authenticated_client(), _acme()
    code = f"PREP_{uuid.uuid4().hex[:8].upper()}"
    made = platform.post(
        f"/api/v1/platform-admin/tenants/{tenant_id}/mappings",
        json={"code": code, "source_system": "TEAMCENTER", "target_entity": "Product", "mapping_rules": RULES},
    )
    assert made.status_code == 200, made.text
    assert made.json()["tenant_id"] == tenant_id and made.json()["status"] == "DRAFT"
    listed = platform.get(f"/api/v1/platform-admin/tenants/{tenant_id}/mappings").json()
    assert any(row["code"] == code for row in listed)
    customer_admin = _client_with_role("CUSTOMER_ADMIN")
    assert any(row["code"] == code for row in customer_admin.get("/api/v1/admin/configuration/mappings").json())
    with SessionLocal() as db:
        bind_system(db, "test: audit")
        event = (
            db.query(AuditEvent)
            .filter(
                AuditEvent.tenant_id == uuid.UUID(tenant_id),
                AuditEvent.action == "MAPPING_CONFIGURATION_CREATED",
                AuditEvent.entity_id == uuid.UUID(made.json()["mapping_id"]),
            )
            .first()
        )
        assert event is not None and event.details["source"] == "PLATFORM_ADMIN"


def test_only_staff_may_prepare_and_the_tenant_must_exist():
    tenant_id = _acme()
    body = {"code": "NOPE", "source_system": "X", "target_entity": "Product", "mapping_rules": RULES}
    assert (
        _client_with_role("CUSTOMER_ADMIN")
        .post(f"/api/v1/platform-admin/tenants/{tenant_id}/mappings", json=body)
        .status_code
        == 403
    )
    assert (
        authenticated_client().post(f"/api/v1/platform-admin/tenants/{uuid.uuid4()}/mappings", json=body).status_code
        == 404
    )
