"""Platform administration of customers and tenants as two workflows: edit details, activate and suspend.

A customer and its tenants each keep their own status. A suspended customer blocks every tenant it owns without
changing the tenants' status; reactivating it restores exactly the tenants that are themselves active.
"""

import uuid
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from backend.app.access import authz
from backend.app.customer_lifecycle import (
    build_tenant_for_customer,
    customer_allows_access_clause,
    effective_access,
    operator_customer_ids,
)
from backend.app.db.models.customer_lifecycle import Customer
from backend.app.db.models.foundation import AuditEvent, AuthUser, Tenant
from backend.app.db.session import SessionLocal
from backend.app.db.tenant_scope import bind_system
from backend.app.main import app
from backend.app.role_codes import is_strict_platform_admin_role
from tests.conftest import GOLDEN_TENANT_KEY, authenticated_client
from tests.test_business_permissions import _client_with_role
from tests.test_customer_admin_account_security import PASSWORD, _user

PLATFORM_PASSWORD = "LegacyTestPassword123!"  # the shared Platform Administrator test account (tests/conftest.py)
REASON = "Requested by the customer in writing"


@pytest.fixture(scope="module")
def platform():
    return authenticated_client()


@pytest.fixture
def customer(platform):
    code = f"CTW{uuid.uuid4().hex[:6].upper()}"
    created = platform.post(
        "/api/v1/platform-admin/customers",
        json={"company_name": f"Workflow Test {code}", "tenant_code": code, "plan_code": "STARTER"},
    )
    assert created.status_code == 200, created.text
    return created.json()


def _record(platform, customer_id):
    response = platform.get(f"/api/v1/platform-admin/customer-records/{customer_id}")
    assert response.status_code == 200, response.text
    return response.json()


def _customer_status(platform, customer_id, status, **extra):
    return platform.post(
        f"/api/v1/platform-admin/customer-records/{customer_id}/lifecycle",
        json={"status": status, "reason": REASON, "password": PLATFORM_PASSWORD, **extra},
    )


def _tenant_status(platform, tenant_id, status, **extra):
    return platform.post(
        f"/api/v1/platform-admin/tenants/{tenant_id}/lifecycle",
        json={"status": status, "reason": REASON, "password": PLATFORM_PASSWORD, **extra},
    )


def _second_tenant(customer_id) -> str:
    """Another ACTIVE tenant of the same customer, added directly."""
    db = SessionLocal()
    try:
        bind_system(db, "test: second tenant")
        owner = db.query(Customer).filter(Customer.id == uuid.UUID(customer_id)).one()
        tenant = build_tenant_for_customer(
            db=db,
            customer=owner,
            tenant_key=f"CTW2{uuid.uuid4().hex[:6].upper()}",
            name=f"Second tenant {uuid.uuid4().hex[:4]}",
            status="ACTIVE",
            now=datetime.now(timezone.utc),
        )
        db.add(tenant)
        db.commit()
        return str(tenant.id)
    finally:
        db.close()


def _viewer_in(tenant_id) -> str:
    """An active Viewer account in the tenant; returns its email (password PASSWORD)."""
    db = SessionLocal()
    try:
        tenant = db.query(Tenant).filter(Tenant.id == uuid.UUID(tenant_id)).one()
        user = _user(db, tenant, "Viewer", "ctw-viewer")
        db.commit()
        return user.username
    finally:
        db.close()


def _sign_in(email):
    return TestClient(app).post("/api/v1/auth/signin", json={"email": email, "password": PASSWORD})


def _tenant_row(tenant_id) -> Tenant:
    db = SessionLocal()
    try:
        return db.query(Tenant).filter(Tenant.id == uuid.UUID(tenant_id)).one()
    finally:
        db.close()


# --- Customer details ---------------------------------------------------------------------------------------------


def test_platform_admin_edits_customer_details_with_reason_and_version(platform, customer):
    path = f"/api/v1/platform-admin/customer-records/{customer['customer_id']}"
    before = _record(platform, customer["customer_id"])["customer"]
    assert before["lock_version"] == 1 and before["lifecycle_status"] == "ACTIVE"
    body = {
        "display_name": "Acme Devices",
        "industry": "Medical devices",
        "website": "https://acme.example",
        "primary_business_contact": {"name": "Ann Lee", "email": "Ann@Acme.example", "phone": "+1 555 0100"},
        "reason": REASON,
        "lock_version": 1,
    }
    updated = platform.patch(path, json=body)
    assert updated.status_code == 200, updated.text
    record = updated.json()
    # The same shape as GET, so the page refreshes from it.
    assert set(record) == set(_record(platform, customer["customer_id"]))
    assert record["customer"]["display_name"] == "Acme Devices"
    assert record["customer"]["primary_business_contact"]["email"] == "ann@acme.example"
    assert record["customer"]["lock_version"] == 2
    assert record["customer"]["customer_identifier"] == customer["customer_identifier"]
    db = SessionLocal()
    try:
        bind_system(db, "test: read audit")
        event = (
            db.query(AuditEvent)
            .filter(AuditEvent.action == "CUSTOMER_UPDATED", AuditEvent.entity_id == uuid.UUID(customer["customer_id"]))
            .one()
        )
        assert event.entity_type == "Customer"
        assert event.details["reason"] == REASON
        assert event.details["changed_fields"] == sorted(
            ["display_name", "industry", "website", "primary_business_contact"]
        )
        assert event.details["after"]["display_name"] == "Acme Devices"
        assert "password" not in str(event.details).lower()
    finally:
        db.close()
    # The change appears in the customer's activity.
    activity = platform.get(f"{path}/tabs/Activity").json()["items"]
    assert any(item["action"] == "CUSTOMER_UPDATED" for item in activity)


def test_customer_edit_validation_conflicts_and_no_changes(platform, customer):
    path = f"/api/v1/platform-admin/customer-records/{customer['customer_id']}"
    assert platform.patch(path, json={"display_name": "X Corp", "lock_version": 1}).status_code == 422  # no reason
    assert (
        platform.patch(path, json={"display_name": "X Corp", "reason": "short", "lock_version": 1}).status_code == 422
    )
    assert platform.patch(path, json={"display_name": "X Corp", "reason": REASON}).status_code == 422  # no version
    bad_email = {"billing_contact": {"email": "not-an-email"}, "reason": REASON, "lock_version": 1}
    assert platform.patch(path, json=bad_email).status_code == 422
    assert platform.patch(path, json={"legal_name": "", "reason": REASON, "lock_version": 1}).status_code == 422
    stale = platform.patch(path, json={"display_name": "X Corp", "reason": REASON, "lock_version": 99})
    assert stale.status_code == 409 and stale.json()["detail"]["code"] == "STALE_RECORD"
    current = _record(platform, customer["customer_id"])["customer"]
    same = platform.patch(
        path, json={"display_name": current["display_name"], "reason": REASON, "lock_version": current["lock_version"]}
    )
    assert same.status_code == 422 and same.json()["detail"]["code"] == "NO_CHANGES"
    nothing = platform.patch(path, json={"reason": REASON, "lock_version": current["lock_version"]})
    assert nothing.status_code == 422 and nothing.json()["detail"]["code"] == "NO_CHANGES"
    # Identifiers are not editable fields: sending one changes nothing.
    ignored = platform.patch(
        path, json={"customer_identifier": "HACKED", "reason": REASON, "lock_version": current["lock_version"]}
    )
    assert ignored.status_code == 422 and ignored.json()["detail"]["code"] == "NO_CHANGES"


def test_only_platform_administrators_edit_or_change_customers_and_tenants(customer):
    body = {"display_name": "Nope Inc", "reason": REASON, "lock_version": 1}
    for client in (_client_with_role("CUSTOMER_ADMIN"), _client_with_role("Investigator")):
        assert (
            client.patch(f"/api/v1/platform-admin/customer-records/{customer['customer_id']}", json=body).status_code
            == 403
        )
        assert (
            client.post(
                f"/api/v1/platform-admin/customer-records/{customer['customer_id']}/lifecycle",
                json={"status": "SUSPENDED", "reason": REASON, "password": PASSWORD},
            ).status_code
            == 403
        )
        assert client.patch(f"/api/v1/platform-admin/tenants/{customer['id']}", json=body).status_code == 403
        assert (
            client.post(
                f"/api/v1/platform-admin/tenants/{customer['id']}/lifecycle",
                json={"status": "SUSPENDED", "reason": REASON, "password": PASSWORD},
            ).status_code
            == 403
        )


# --- Customer status ----------------------------------------------------------------------------------------------


def test_suspended_customer_blocks_its_tenants_without_changing_their_status(platform, customer):
    second = _second_tenant(customer["customer_id"])
    email = _viewer_in(customer["id"])
    assert _sign_in(email).status_code == 200
    # The second tenant is suspended on its own before the customer is.
    assert _tenant_status(platform, second, "SUSPENDED").status_code == 200

    suspended = _customer_status(platform, customer["customer_id"], "SUSPENDED", lock_version=1)
    assert suspended.status_code == 200, suspended.text
    body = suspended.json()
    assert body["customer"]["lifecycle_status"] == "SUSPENDED" and body["customer"]["lock_version"] == 2
    # Only the tenant that was itself open is affected; the separately suspended one was already blocked.
    assert [item["tenant_id"] for item in body["tenants_affected"]] == [customer["id"]]
    assert _tenant_row(customer["id"]).status == "ACTIVE"
    assert _tenant_row(second).status == "SUSPENDED"
    access = {item["id"]: item["effective_access"] for item in body["tenants"]}
    assert access == {customer["id"]: "BLOCKED_BY_CUSTOMER", second: "BLOCKED"}

    refused = _sign_in(email)
    assert refused.status_code == 403
    assert refused.json()["detail"]["code"] == "TENANT_ACCESS_SUSPENDED"
    assert "suspended" in refused.json()["detail"]["message"].lower()

    tenant_view = platform.get(f"/api/v1/platform-admin/tenants/{customer['id']}").json()["tenant"]
    assert tenant_view["customer_lifecycle_status"] == "SUSPENDED"
    assert tenant_view["effective_access"] == "BLOCKED_BY_CUSTOMER"
    listed = platform.get("/api/v1/platform-admin/tenants", params={"q": customer["business_id"]}).json()["items"]
    assert next(row for row in listed if row["id"] == customer["id"])["effective_access"] == "BLOCKED_BY_CUSTOMER"
    accounts = platform.get("/api/v1/platform-admin/customer-accounts", params={"q": customer["customer_identifier"]})
    assert (
        next(row for row in accounts.json()["items"] if row["id"] == customer["customer_id"])["status"] == "SUSPENDED"
    )

    db = SessionLocal()
    try:
        bind_system(db, "test: read audit")
        event = (
            db.query(AuditEvent)
            .filter(
                AuditEvent.action == "CUSTOMER_LIFECYCLE_TRANSITION",
                AuditEvent.entity_id == uuid.UUID(customer["customer_id"]),
            )
            .one()
        )
        assert event.entity_type == "Customer"
        assert event.details["from"] == "ACTIVE" and event.details["to"] == "SUSPENDED"
        assert event.details["tenants_access_blocked"] == [customer["business_id"]]
    finally:
        db.close()

    # Reactivation restores exactly the tenants that are themselves active.
    restored = _customer_status(platform, customer["customer_id"], "ACTIVE")
    assert restored.status_code == 200, restored.text
    assert [item["effective_access"] for item in restored.json()["tenants_affected"]] == ["ACTIVE"]
    assert _tenant_row(second).status == "SUSPENDED"
    assert _sign_in(email).status_code == 200


def test_customer_status_transitions(platform, customer):
    again = _customer_status(platform, customer["customer_id"], "ACTIVE")
    assert again.status_code == 409 and again.json()["detail"]["code"] == "INVALID_CUSTOMER_TRANSITION"
    assert _customer_status(platform, customer["customer_id"], "TERMINATED").status_code == 422
    stale = _customer_status(platform, customer["customer_id"], "SUSPENDED", lock_version=42)
    assert stale.status_code == 409 and stale.json()["detail"]["code"] == "STALE_RECORD"
    short = platform.post(
        f"/api/v1/platform-admin/customer-records/{customer['customer_id']}/lifecycle",
        json={"status": "SUSPENDED", "reason": "too short", "password": PLATFORM_PASSWORD},
    )
    assert short.status_code == 422


def test_a_new_customer_is_activated_from_provisioning(platform, customer):
    db = SessionLocal()
    try:
        db.query(Customer).filter(Customer.id == uuid.UUID(customer["customer_id"])).update(
            {"lifecycle_status": "PROVISIONING"}
        )
        db.commit()
    finally:
        db.close()
    refused = _customer_status(platform, customer["customer_id"], "SUSPENDED")
    assert refused.status_code == 409 and refused.json()["detail"]["code"] == "INVALID_CUSTOMER_TRANSITION"
    activated = _customer_status(platform, customer["customer_id"], "ACTIVE")
    assert activated.status_code == 200, activated.text
    assert activated.json()["customer"]["lifecycle_status"] == "ACTIVE"
    # A provisioning customer never blocked its tenants, so no tenant's access changes.
    assert activated.json()["tenants_affected"] == []


def test_the_operator_organization_cannot_be_suspended(platform):
    db = SessionLocal()
    try:
        bind_system(db, "test: operator")
        golden = db.query(Tenant).filter(Tenant.tenant_key == GOLDEN_TENANT_KEY).first()
        if golden is None:
            golden = (
                db.query(Tenant)
                .join(AuthUser, AuthUser.tenant_id == Tenant.id)
                .filter(AuthUser.username == "legacy-test-auth@synthetic.invalid")
                .first()
            )
        assert golden is not None
        tenant_id, customer_id = str(golden.id), golden.customer_id
        # The shared Platform Administrator lives in this tenant, so its customer is the operator's.
        assert customer_id in operator_customer_ids(db)
    finally:
        db.close()
    refused = _customer_status(platform, str(customer_id), "SUSPENDED")
    assert refused.status_code == 409 and refused.json()["detail"]["code"] == "OPERATOR_PROTECTED"
    for status in ("SUSPENDED", "TERMINATED"):
        tenant = _tenant_status(platform, tenant_id, status)
        assert tenant.status_code == 409
        assert tenant.json()["detail"]["code"] in {"OPERATOR_PROTECTED", "INVALID_TENANT_TRANSITION"}
    assert _tenant_status(platform, tenant_id, "SUSPENDED").json()["detail"]["code"] == "OPERATOR_PROTECTED"


# --- Tenants ------------------------------------------------------------------------------------------------------


def test_tenant_edit_is_typed_versioned_and_audited(platform, customer):
    path = f"/api/v1/platform-admin/tenants/{customer['id']}"
    version = platform.get(path).json()["tenant"]["lock_version"]
    assert (
        platform.patch(path, json={"tenant_type": "HUGE", "reason": REASON, "lock_version": version}).status_code == 422
    )
    assert platform.patch(path, json={"display_name": "Renamed", "lock_version": version}).status_code == 422
    assert platform.patch(path, json={"display_name": "Renamed", "reason": REASON}).status_code == 422
    stale = platform.patch(path, json={"display_name": "Renamed", "reason": REASON, "lock_version": version + 5})
    assert stale.status_code == 409 and stale.json()["detail"]["code"] == "STALE_RECORD"
    updated = platform.patch(
        path,
        json={"display_name": "Renamed tenant", "tenant_type": "ENTERPRISE", "reason": REASON, "lock_version": version},
    )
    assert updated.status_code == 200, updated.text
    body = updated.json()
    assert body["lock_version"] == version + 1
    assert body["updated"] == {"display_name": "Renamed tenant", "tenant_type": "ENTERPRISE"}
    assert body["tenant"]["effective_access"] == "ACTIVE"
    same = platform.patch(path, json={"display_name": "Renamed tenant", "reason": REASON, "lock_version": version + 1})
    assert same.status_code == 422 and same.json()["detail"]["code"] == "NO_CHANGES"
    db = SessionLocal()
    try:
        bind_system(db, "test: read audit")
        event = (
            db.query(AuditEvent)
            .filter(AuditEvent.action == "TENANT_UPDATED", AuditEvent.entity_id == uuid.UUID(customer["id"]))
            .one()
        )
        assert event.details["reason"] == REASON
        assert event.details["before"]["tenant_type"] == "STANDARD"
    finally:
        db.close()


def test_a_tenant_cannot_be_activated_under_a_suspended_customer(platform, customer):
    suspended = _tenant_status(platform, customer["id"], "SUSPENDED")
    assert suspended.status_code == 200, suspended.text
    assert suspended.json()["effective_access"] == "BLOCKED"
    assert _customer_status(platform, customer["customer_id"], "SUSPENDED").status_code == 200
    refused = _tenant_status(platform, customer["id"], "ACTIVE")
    assert refused.status_code == 409 and refused.json()["detail"]["code"] == "CUSTOMER_NOT_ACTIVE"
    legacy = _tenant_status(platform, customer["id"], "REACTIVATED")  # the older spelling is still accepted
    assert legacy.status_code == 409 and legacy.json()["detail"]["code"] == "CUSTOMER_NOT_ACTIVE"
    # Reactivating the customer leaves the separately suspended tenant suspended.
    assert _customer_status(platform, customer["customer_id"], "ACTIVE").status_code == 200
    assert _tenant_row(customer["id"]).status == "SUSPENDED"
    reactivated = _tenant_status(platform, customer["id"], "ACTIVE")
    assert reactivated.status_code == 200, reactivated.text
    assert reactivated.json()["status"] == "ACTIVE" and reactivated.json()["effective_access"] == "ACTIVE"


def _set_tenant_status(tenant_id, status):
    db = SessionLocal()
    try:
        db.query(Tenant).filter(Tenant.id == uuid.UUID(tenant_id)).update({"status": status})
        db.commit()
    finally:
        db.close()


@pytest.mark.parametrize("status", ["DRAFT", "PENDING_APPROVAL", "PROVISIONING"])
def test_a_tenant_still_provisioning_cannot_be_activated(platform, customer, status):
    _set_tenant_status(customer["id"], status)
    refused = _tenant_status(platform, customer["id"], "ACTIVE")
    assert refused.status_code == 409 and refused.json()["detail"]["code"] == "INVALID_TENANT_TRANSITION"
    assert "provisioning" in refused.json()["detail"]["message"].lower()


@pytest.mark.parametrize("status", ["PROVISIONED", "PENDING_CUSTOMER_ACTIVATION"])
def test_a_provisioned_tenant_is_activated(platform, customer, status):
    _set_tenant_status(customer["id"], status)
    activated = _tenant_status(platform, customer["id"], "ACTIVE")
    assert activated.status_code == 200, activated.text
    assert activated.json()["effective_access"] == "ACTIVE"


def test_wrong_password_on_status_changes_is_403_not_401(platform, customer):
    for path, status in (
        (f"/api/v1/platform-admin/customer-records/{customer['customer_id']}/lifecycle", "SUSPENDED"),
        (f"/api/v1/platform-admin/tenants/{customer['id']}/lifecycle", "SUSPENDED"),
    ):
        refused = platform.post(path, json={"status": status, "reason": REASON, "password": "not-the-password"})
        assert refused.status_code == 403 and refused.json()["detail"]["code"] == "INVALID_REAUTHENTICATION"


def test_optional_details_are_cleared_with_null(platform, customer):
    path = f"/api/v1/platform-admin/customer-records/{customer['customer_id']}"
    contact = {"name": "Bo Billing", "email": "billing@acme.example", "phone": None}
    set_ = platform.patch(
        path, json={"billing_contact": contact, "industry": "Devices", "reason": REASON, "lock_version": 1}
    )
    assert set_.status_code == 200, set_.text
    assert set_.json()["customer"]["billing_contact"] == contact
    cleared = platform.patch(
        path, json={"billing_contact": None, "industry": None, "reason": REASON, "lock_version": 2}
    )
    assert cleared.status_code == 200, cleared.text
    assert cleared.json()["customer"]["billing_contact"] is None and cleared.json()["customer"]["industry"] is None
    # Every editable field is returned, even when empty.
    for field in (
        "trading_name",
        "company_size",
        "state_province",
        "headquarters",
        "crm_reference",
        "primary_business_contact",
        "internal_account_owner",
        "implementation_manager",
    ):
        assert field in cleared.json()["customer"]


def test_terminating_a_tenant_records_when(platform, customer):
    terminated = _tenant_status(platform, customer["id"], "TERMINATED")
    assert terminated.status_code == 200, terminated.text
    assert _tenant_row(customer["id"]).terminated_at is not None


# --- Background jobs and helpers ----------------------------------------------------------------------------------


def test_background_jobs_skip_tenants_of_a_suspended_customer(platform, customer):
    def eligible() -> bool:
        db = SessionLocal()
        try:
            bind_system(db, "test: job filter")
            return (
                db.query(Tenant.id)
                .filter(Tenant.id == uuid.UUID(customer["id"]), customer_allows_access_clause())
                .first()
                is not None
            )
        finally:
            db.close()

    assert eligible()
    assert _customer_status(platform, customer["customer_id"], "SUSPENDED").status_code == 200
    assert not eligible()
    assert _customer_status(platform, customer["customer_id"], "ACTIVE").status_code == 200
    assert eligible()


@pytest.mark.parametrize(
    "tenant_status,customer_status,expected",
    [
        ("ACTIVE", "ACTIVE", "ACTIVE"),
        ("EXPIRING_SOON", "EXPIRING_SOON", "ACTIVE"),
        ("ACTIVE", "PROVISIONING", "ACTIVE"),
        ("ACTIVE", "SUSPENDED", "BLOCKED_BY_CUSTOMER"),
        ("ACTIVE", "TERMINATED", "BLOCKED_BY_CUSTOMER"),
        ("SUSPENDED", "ACTIVE", "BLOCKED"),
        ("SUSPENDED", "SUSPENDED", "BLOCKED"),
        ("PROVISIONING", "ACTIVE", "BLOCKED"),
    ],
)
def test_effective_access(tenant_status, customer_status, expected):
    assert effective_access(tenant_status, customer_status) == expected


# --- Platform administrator role ----------------------------------------------------------------------------------


@pytest.mark.parametrize("role", ["PLATFORM_ADMIN", "platform admin", "MDARIX_ADMINISTRATOR"])
def test_platform_admin_guard_accepts_platform_roles(role):
    assert is_strict_platform_admin_role(role)


@pytest.mark.parametrize("role", ["ADMIN", "Admin", "ADMINISTRATOR", "Administrator", "CUSTOMER_ADMIN", "Viewer", ""])
def test_platform_admin_guard_refuses_generic_administrator_roles(role, monkeypatch):
    assert not is_strict_platform_admin_role(role)
    monkeypatch.setattr(authz, "_authenticated_user", lambda request, db: SimpleNamespace(role=role))
    with pytest.raises(HTTPException) as refused:
        authz._require_platform_admin(None, SimpleNamespace(info={}))
    assert refused.value.status_code == 403
    assert refused.value.detail["code"] == "PLATFORM_ADMIN_REQUIRED"


def test_wizard_provisioning_records_every_step_and_keeps_the_reason(platform):
    """The new-customer wizard: every provisioning step is recorded as completed (the customer step used to be
    recorded as failed), the CRM reference is kept on the customer and the reason in the audit trail."""
    code = f"WIZ{uuid.uuid4().hex[:6].upper()}"
    payload = {
        "company_name": f"Wizard Customer {code}",
        "tenant_code": code,
        "region": "UK",
        "residency": "UK",
        "plan_code": "STARTER",
        "licensed_users_limit": 10,
        "customer_admin_email": f"wiz-{uuid.uuid4().hex[:6]}@example.invalid",
        "customer_admin_display_name": "Wanda Wizard",
        "customer_admin_company": f"Wizard Customer {code}",
        "invitation_required": True,
        "reason": "Signed contract for the wizard test",
        "customer_reference": "CRM-WIZ-1",
    }
    assert platform.post("/api/v1/platform-admin/onboarding/validate", json=payload).status_code == 200
    response = platform.post("/api/v1/platform/tenants/provision", json=payload)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["status"] == "ACTIVE" and all(body["prerequisites"].values())
    job = platform.get(f"/api/v1/platform-admin/provisioning-jobs/{body['job_id']}").json()
    assert job["status"] == "COMPLETED"
    assert [step["status"] for step in job["step_details"]] == ["COMPLETED"] * 7
    db = SessionLocal()
    try:
        bind_system(db, "test: wizard provisioning")
        customer = db.query(Customer).filter(Customer.id == uuid.UUID(body["customer_id"])).one()
        assert customer.crm_reference == "CRM-WIZ-1" and customer.lifecycle_status == "ACTIVE"
        event = (
            db.query(AuditEvent)
            .filter(AuditEvent.action == "TENANT_PROVISIONED", AuditEvent.entity_id == uuid.UUID(body["tenant_id"]))
            .one()
        )
        assert event.details["reason"] == "Signed contract for the wizard test"
    finally:
        db.close()
