"""Platform administration of customers: administrators, subscription, standing and environments."""

import time
import uuid

import pytest
from fastapi.testclient import TestClient

from backend.app.db.models.foundation import AuthUser, Tenant, TenantPlanAssignment
from backend.app.db.session import SessionLocal
from backend.app.main import app
from tests.conftest import authenticated_client
from tests.test_business_permissions import _client_with_role

PLATFORM_PASSWORD = "LegacyTestPassword123!"  # the shared Administrator test account (tests/conftest.py)


@pytest.fixture(scope="module")
def platform():
    return authenticated_client()


@pytest.fixture
def customer(platform):
    code = f"PCA{uuid.uuid4().hex[:6].upper()}"
    created = platform.post(
        "/api/v1/platform-admin/customers",
        json={
            "company_name": f"Platform Test {code}",
            "tenant_code": code,
            "plan_code": "STARTER",
            "customer_admin_limit": 5,
        },
    )
    assert created.status_code == 200, created.text
    return created.json()


def _add_admin(platform, tenant_id, name="Ada Admin"):
    email = f"{name.split()[0].lower()}-{uuid.uuid4().hex[:6]}@example.invalid"
    response = platform.post(
        f"/api/v1/platform-admin/tenants/{tenant_id}/customer-admins",
        json={"email": email, "display_name": name, "reason": "New customer administrator"},
    )
    assert response.status_code == 200, response.text
    return response.json()


def _activate(user_id):
    db = SessionLocal()
    try:
        user = db.query(AuthUser).filter(AuthUser.id == uuid.UUID(user_id)).one()
        user.status, user.email_verified = "ACTIVE", True
        db.commit()
    finally:
        db.close()


def _status(platform, user_id, status):
    return platform.post(
        f"/api/v1/platform-admin/customer-admins/{user_id}/status", json={"status": status, "reason": "Access review"}
    )


def test_platform_admin_adds_and_lists_customer_administrators(platform, customer):
    added = _add_admin(platform, customer["id"])
    assert (
        added["status"] == "INVITED"
        and added["can_resend_invitation"]
        and added["customer_id"] == customer["customer_id"]
    )
    listed = platform.get("/api/v1/platform-admin/customer-admins", params={"tenant_id": customer["id"]}).json()[
        "items"
    ]
    assert [item["email"] for item in listed] == [added["email"]]
    # The new administrator is listed as invited (checked on its own tenant: the full list is paged, and how
    # many other administrators fill its first page depends on the data already in the database).
    assert listed[0]["status"] == "INVITED"
    # Retired accounts are hidden unless asked for by status.
    db = SessionLocal()
    try:
        db.query(AuthUser).filter(AuthUser.id == uuid.UUID(added["id"])).one().status = "INACTIVE"
        db.commit()
    finally:
        db.close()
    assert (
        platform.get("/api/v1/platform-admin/customer-admins", params={"tenant_id": customer["id"]}).json()["items"]
        == []
    )
    inactive = platform.get(
        "/api/v1/platform-admin/customer-admins", params={"tenant_id": customer["id"], "status": "INACTIVE"}
    ).json()["items"]
    assert [item["email"] for item in inactive] == [added["email"]]
    # Only Customer Administrators: platform roles never appear.
    everyone = platform.get("/api/v1/platform-admin/customer-admins").json()["items"]
    assert all("legacy-test-auth" not in item["email"] for item in everyone)
    duplicate = platform.post(
        f"/api/v1/platform-admin/tenants/{customer['id']}/customer-admins",
        json={"email": added["email"], "display_name": "Again", "reason": "Duplicate check"},
    )
    assert duplicate.status_code == 409 and duplicate.json()["detail"]["code"] == "ACCOUNT_EXISTS"


def test_the_last_active_administrator_cannot_be_suspended(platform, customer):
    first = _add_admin(platform, customer["id"], "First Admin")
    _activate(first["id"])
    refused = _status(platform, first["id"], "SUSPENDED")
    assert refused.status_code == 409 and refused.json()["detail"]["code"] == "LAST_ACTIVE_CUSTOMER_ADMIN"

    second = _add_admin(platform, customer["id"], "Second Admin")
    _activate(second["id"])
    suspended = _status(platform, first["id"], "SUSPENDED")
    assert suspended.status_code == 200 and suspended.json()["status"] == "SUSPENDED"
    # Now the second is the last active one.
    assert _status(platform, second["id"], "SUSPENDED").status_code == 409
    reactivated = _status(platform, first["id"], "ACTIVE")
    assert reactivated.status_code == 200 and reactivated.json()["status"] == "ACTIVE"
    assert _status(platform, first["id"], "ACTIVE").status_code == 409  # already active


def test_password_reset_and_invitation_emails(platform, customer):
    admin = _add_admin(platform, customer["id"])
    path = f"/api/v1/platform-admin/customer-admins/{admin['id']}"
    reason = {"reason": "Requested by the customer"}
    assert platform.post(f"{path}/password-reset", json=reason).status_code == 409  # not activated yet
    resent = platform.post(f"{path}/resend-invitation", json=reason)
    assert resent.status_code == 200 and resent.json()["status"] == "INVITED"
    _activate(admin["id"])
    reset = platform.post(f"{path}/password-reset", json=reason)
    assert reset.status_code == 200 and reset.json()["status"] in {"RESET_EMAIL_SENT", "RESET_LINK_CREATED"}
    assert platform.post(f"{path}/resend-invitation", json=reason).status_code == 409
    assert platform.post(f"{path}/password-reset", json={"reason": "x"}).status_code == 422  # a reason is required


def test_only_platform_administrators_manage_customer_administrators(customer):
    for client in (_client_with_role("CUSTOMER_ADMIN"), _client_with_role("Investigator")):
        assert client.get("/api/v1/platform-admin/customer-admins").status_code == 403
        assert (
            client.post(
                f"/api/v1/platform-admin/tenants/{customer['id']}/customer-admins",
                json={"email": "x@example.invalid", "display_name": "X", "reason": "Not allowed"},
            ).status_code
            == 403
        )
    assert TestClient(app).get("/api/v1/platform-admin/customer-admins").status_code == 401


def test_a_subscription_change_takes_effect(platform, customer):
    plans = platform.get("/api/v1/platform-admin/plans").json()
    plans = plans.get("items", plans) if isinstance(plans, dict) else plans
    target = next(plan for plan in plans if plan["code"] != "STARTER" and plan.get("status", "ACTIVE") == "ACTIVE")
    changed = platform.post(
        f"/api/v1/platform/customers/{customer['id']}/subscription",
        json={
            "plan_id": target["id"],
            "starts_at": "2026-10-01T00:00:00Z",
            "expires_at": "2027-10-01T00:00:00Z",
            "reason": "Upgrade agreed with the customer",
        },
    )
    assert changed.status_code == 200, changed.text
    current = platform.get(f"/api/v1/platform-admin/customers/{customer['id']}/subscription").json()
    assert current["plan_code"] == target["code"]
    db = SessionLocal()
    try:
        rows = db.query(TenantPlanAssignment).filter(TenantPlanAssignment.tenant_id == uuid.UUID(customer["id"])).all()
        assert sorted(row.status for row in rows) == ["ACTIVE", "SUPERSEDED"]  # history kept
    finally:
        db.close()


def test_environments_are_validated_instead_of_failing(platform, customer):
    path = f"/api/v1/platform-admin/tenants/{customer['id']}/environments"
    body = {"environment_identifier": "acme-uat", "environment_type": "UAT", "region": "EU", "residency_region": "EU"}
    assert platform.post(path, json=body).status_code == 200
    again = platform.post(path, json={**body, "environment_identifier": "acme-uat-2"})
    assert again.status_code == 409 and again.json()["detail"]["code"] == "ENVIRONMENT_EXISTS"
    assert platform.post(path, json={**body, "environment_type": "STAGING"}).status_code == 422


def test_suspending_a_customer_suspends_its_tenants_and_needs_the_password(platform, customer):
    path = f"/api/v1/platform-admin/customer-records/{customer['customer_id']}/lifecycle"
    wrong = platform.post(path, json={"status": "SUSPENDED", "reason": "Contract ended", "password": "wrong-password"})
    assert wrong.status_code == 403
    suspended = platform.post(
        path, json={"status": "SUSPENDED", "reason": "Contract ended", "password": PLATFORM_PASSWORD}
    )
    assert suspended.status_code == 200, suspended.text
    assert suspended.json()["tenants_changed"] == [customer["tenant_key"]]
    db = SessionLocal()
    try:
        assert db.query(Tenant).filter(Tenant.id == uuid.UUID(customer["id"])).one().status == "SUSPENDED"
    finally:
        db.close()
    record = platform.get(f"/api/v1/platform-admin/customer-records/{customer['customer_id']}").json()
    assert record["customer"]["lifecycle_status"] == "SUSPENDED"
    reactivated = platform.post(
        path, json={"status": "ACTIVE", "reason": "Contract renewed", "password": PLATFORM_PASSWORD}
    )
    assert reactivated.status_code == 200 and reactivated.json()["status"] == "ACTIVE"


def test_the_customer_page_has_only_working_sections(platform, customer):
    record = platform.get(f"/api/v1/platform-admin/customer-records/{customer['customer_id']}").json()
    assert record["tabs"] == ["Overview", "Administrators", "Subscription", "Usage", "Activity"]
    for tab in record["tabs"][1:]:
        response = platform.get(f"/api/v1/platform-admin/customer-records/{customer['customer_id']}/tabs/{tab}")
        assert response.status_code == 200, (tab, response.text)
    # Customer details are maintained by the customer, not edited by the platform administrator.
    assert platform.patch(
        f"/api/v1/platform-admin/customer-records/{customer['customer_id']}", json={"display_name": "Renamed"}
    ).status_code in {404, 405}


def test_the_add_administrator_picker_lists_active_tenants_quickly(platform, customer):
    started = time.monotonic()
    options = platform.get("/api/v1/platform-admin/customer-admin-tenants")
    assert options.status_code == 200 and time.monotonic() - started < 2
    items = options.json()["items"]
    assert customer["id"] in {item["id"] for item in items}
    # Light rows: the tenant and the customer that owns it, nothing per-tenant to compute.
    assert all(
        set(item)
        == {"id", "business_id", "tenant_key", "display_name", "tenant_name", "customer_name", "customer_business_id"}
        for item in items
    )
    mine = next(item for item in items if item["id"] == customer["id"])
    assert mine["tenant_name"] == customer["name"] and mine["customer_name"]
    assert _client_with_role("CUSTOMER_ADMIN").get("/api/v1/platform-admin/customer-admin-tenants").status_code == 403
