"""A customer owns one or more tenants; each tenant has its own plan, environment and Customer Administrators."""

import uuid

import pytest

from backend.app.db.models.customer_lifecycle import Customer, TenantEnvironment
from backend.app.db.models.foundation import (
    AuditEvent,
    AuthUser,
    FeatureEntitlement,
    PlanDefinition,
    Tenant,
    TenantPlanAssignment,
)
from backend.app.db.session import SessionLocal
from tests.conftest import authenticated_client
from tests.test_business_permissions import _client_with_role


@pytest.fixture(scope="module")
def platform():
    return authenticated_client()


@pytest.fixture
def customer(platform):
    code = f"PCT{uuid.uuid4().hex[:6].upper()}"
    created = platform.post(
        "/api/v1/platform-admin/customers",
        json={"company_name": f"Tenant Test {code}", "tenant_code": code, "plan_code": "STARTER"},
    )
    assert created.status_code == 200, created.text
    return created.json()


def _plan_id(code="STARTER") -> str:
    db = SessionLocal()
    try:
        return str(db.query(PlanDefinition.id).filter(PlanDefinition.code == code).scalar())
    finally:
        db.close()


def _tenant_request(**overrides):
    suffix = uuid.uuid4().hex[:6].upper()
    body = {
        "tenant_name": f"Europe Production {suffix}",
        "tenant_code": f"EU{suffix}",
        "environment_type": "PRODUCTION",
        "data_region": "eu-central-1",
        "plan_id": _plan_id(),
        "admin_email": f"eu-admin-{suffix.lower()}@example.invalid",
        "admin_display_name": "Eva Europe",
        "reason": "Customer opened a European operation",
    }
    return {**body, **overrides}


def _add_tenant(platform, customer_id, **overrides):
    return platform.post(
        f"/api/v1/platform-admin/customer-records/{customer_id}/tenants", json=_tenant_request(**overrides)
    )


def test_a_customer_gets_a_second_tenant_with_its_own_plan_environment_and_administrator(platform, customer):
    body = _tenant_request()
    added = platform.post(f"/api/v1/platform-admin/customer-records/{customer['customer_id']}/tenants", json=body)
    assert added.status_code == 200, added.text
    result = added.json()
    tenant = result["tenant"]
    assert tenant["customer_id"] == customer["customer_id"] and tenant["tenant_key"] == body["tenant_code"]
    assert tenant["status"] == "ACTIVE" and tenant["tenant_identifier"].startswith("TEN")
    # The administrator belongs to the new tenant, not to the customer's first tenant.
    admin = result["administrator"]
    assert admin["tenant_id"] == tenant["id"] and admin["status"] == "INVITED" and admin["email"] == body["admin_email"]

    record = platform.get(f"/api/v1/platform-admin/customer-records/{customer['customer_id']}").json()
    assert {item["id"] for item in record["tenants"]} == {customer["id"], tenant["id"]}

    db = SessionLocal()
    try:
        assert db.query(TenantPlanAssignment).filter_by(tenant_id=uuid.UUID(tenant["id"]), status="ACTIVE").count() == 1
        environment = db.query(TenantEnvironment).filter_by(tenant_id=uuid.UUID(tenant["id"])).one()
        assert environment.environment_type == "PRODUCTION" and environment.residency_region == "eu-central-1"
        assert db.query(AuditEvent).filter_by(tenant_id=uuid.UUID(tenant["id"]), action="TENANT_ADDED").count() == 1
        user = db.query(AuthUser).filter_by(id=uuid.UUID(admin["id"])).one()
        assert user.tenant_id == uuid.UUID(tenant["id"]) and user.role == "CUSTOMER_ADMIN"
    finally:
        db.close()

    # Each tenant lists only its own administrators.
    first = platform.get("/api/v1/platform-admin/customer-admins", params={"tenant_id": customer["id"]}).json()
    second = platform.get("/api/v1/platform-admin/customer-admins", params={"tenant_id": tenant["id"]}).json()
    assert body["admin_email"] not in {item["email"] for item in first["items"]}
    assert [item["email"] for item in second["items"]] == [body["admin_email"]]
    assert second["items"][0]["tenant_name"] == body["tenant_name"]
    # The customer view lists both tenants' administrators, each with its tenant.
    both = platform.get("/api/v1/platform-admin/customer-admins", params={"customer_id": customer["customer_id"]})
    assert {item["tenant_id"] for item in both.json()["items"]} >= {tenant["id"]}


def test_the_customer_directory_shows_each_customer_once_with_its_tenants(platform, customer):
    second = _add_tenant(platform, customer["customer_id"])
    assert second.status_code == 200, second.text
    listed = platform.get("/api/v1/platform-admin/customer-accounts", params={"q": customer["tenant_key"]}).json()
    rows = [row for row in listed["items"] if row["id"] == customer["customer_id"]]
    assert len(rows) == 1
    row = rows[0]
    assert row["tenant_count"] == 2 and row["status"] == "ACTIVE"
    assert {item["tenant_key"] for item in row["tenants"]} == {
        customer["tenant_key"],
        second.json()["tenant"]["tenant_key"],
    }
    # Searching by the second tenant's code finds the same customer.
    by_tenant = platform.get(
        "/api/v1/platform-admin/customer-accounts", params={"q": second.json()["tenant"]["tenant_key"]}
    ).json()
    assert [item["id"] for item in by_tenant["items"]] == [customer["customer_id"]]
    # The tenant directory names the owning customer.
    tenants = platform.get(
        "/api/v1/platform-admin/tenants", params={"q": second.json()["tenant"]["display_name"]}
    ).json()["items"]
    owned = [item for item in tenants if item["id"] == second.json()["tenant"]["id"]]
    assert owned and owned[0]["customer_identifier"] == customer["customer_identifier"]
    detail = platform.get(f"/api/v1/platform-admin/tenants/{second.json()['tenant']['id']}").json()["tenant"]
    assert detail["customer_identifier"] == customer["customer_identifier"]


def test_the_last_active_administrator_rule_applies_to_each_tenant(platform, customer):
    added = _add_tenant(platform, customer["customer_id"]).json()
    first_admin = platform.post(
        f"/api/v1/platform-admin/tenants/{customer['id']}/customer-admins",
        json={
            "email": f"first-{uuid.uuid4().hex[:6]}@example.invalid",
            "display_name": "Fay First",
            "reason": "First admin",
        },
    ).json()
    db = SessionLocal()
    try:
        for user_id in (first_admin["id"], added["administrator"]["id"]):
            user = db.query(AuthUser).filter_by(id=uuid.UUID(user_id)).one()
            user.status, user.email_verified = "ACTIVE", True
        db.commit()
    finally:
        db.close()
    # Both tenants have one active administrator each: neither can be suspended, though the customer has two.
    for user_id in (first_admin["id"], added["administrator"]["id"]):
        refused = platform.post(
            f"/api/v1/platform-admin/customer-admins/{user_id}/status", json={"status": "SUSPENDED", "reason": "Review"}
        )
        assert refused.status_code == 409 and refused.json()["detail"]["code"] == "LAST_ACTIVE_CUSTOMER_ADMIN"
        assert "tenant" in refused.json()["detail"]["message"]


def test_a_refused_tenant_leaves_nothing_behind(platform, customer):
    def tenant_count():
        db = SessionLocal()
        try:
            return db.query(Tenant).filter(Tenant.customer_id == uuid.UUID(customer["customer_id"])).count()
        finally:
            db.close()

    before = tenant_count()
    duplicate_code = _add_tenant(platform, customer["customer_id"], tenant_code=customer["tenant_key"])
    assert duplicate_code.status_code == 409 and duplicate_code.json()["detail"]["code"] == "TENANT_EXISTS"
    taken = _add_tenant(platform, customer["customer_id"]).json()["administrator"]["email"]
    before = tenant_count()
    # The same person may administer a second tenant: a separate account there; sign-in asks which tenant.
    second_tenant = _add_tenant(platform, customer["customer_id"], admin_email=taken)
    assert second_tenant.status_code == 200, second_tenant.text
    before = tenant_count()
    same_name = _add_tenant(platform, customer["customer_id"], tenant_name=customer["name"].upper())
    assert same_name.status_code == 409 and same_name.json()["detail"]["code"] == "TENANT_NAME_EXISTS"
    no_plan = _add_tenant(platform, customer["customer_id"], plan_id=str(uuid.uuid4()))
    assert no_plan.status_code == 422 and no_plan.json()["detail"]["code"] == "PLAN_NOT_PUBLISHED"
    bad_environment = _add_tenant(platform, customer["customer_id"], environment_type="PROD")
    assert bad_environment.status_code == 422
    missing = _add_tenant(platform, str(uuid.uuid4()))
    assert missing.status_code == 404
    assert tenant_count() == before


def test_a_suspended_customer_gets_no_new_tenant(platform, customer):
    db = SessionLocal()
    try:
        record = db.query(Customer).filter_by(id=uuid.UUID(customer["customer_id"])).one()
        record.lifecycle_status = "SUSPENDED"
        db.commit()
    finally:
        db.close()
    refused = _add_tenant(platform, customer["customer_id"])
    assert refused.status_code == 409 and refused.json()["detail"]["code"] == "CUSTOMER_NOT_ACTIVE"


def test_adding_a_tenant_does_not_change_the_shared_plan_limits(platform, customer):
    def limits():
        db = SessionLocal()
        try:
            return {
                row.feature_code: dict(row.limits or {})
                for row in db.query(FeatureEntitlement)
                .filter(FeatureEntitlement.plan_id == uuid.UUID(_plan_id()))
                .all()
            }
        finally:
            db.close()

    before = limits()
    assert _add_tenant(platform, customer["customer_id"]).status_code == 200
    assert limits() == before


def test_only_a_platform_administrator_manages_customer_tenants(customer):
    customer_admin = _client_with_role("CUSTOMER_ADMIN")
    assert customer_admin.get("/api/v1/platform-admin/customer-accounts").status_code == 403
    response = customer_admin.post(
        f"/api/v1/platform-admin/customer-records/{customer['customer_id']}/tenants", json=_tenant_request()
    )
    assert response.status_code == 403
