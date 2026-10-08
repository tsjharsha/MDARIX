"""Platform administration lists accounts by who they belong to: platform users (platform administrators only) apart
from customer accounts (Customer Administrators, and the read-only list of every other customer user)."""

import uuid

import pytest

from tests.conftest import authenticated_client
from tests.test_business_permissions import _client_with_role


@pytest.fixture(scope="module")
def platform():
    return authenticated_client()


@pytest.fixture(scope="module")
def customer(platform):
    code = f"PAC{uuid.uuid4().hex[:6].upper()}"
    created = platform.post(
        "/api/v1/platform-admin/customers",
        json={
            "company_name": f"Accounts Test {code}",
            "tenant_code": code,
            "plan_code": "STARTER",
            "customer_admin_limit": 5,
        },
    )
    assert created.status_code == 200, created.text
    return created.json()


def test_platform_users_lists_platform_administrators_only(platform):
    response = platform.get("/api/v1/platform-admin/platform-users")
    assert response.status_code == 200, response.text
    items = response.json()["items"]
    assert items, "the shared test administrator is a platform user"
    assert {item["role_label"] for item in items} == {"Platform Administrator"}
    # Each row says which organization the account signs in to.
    assert all(item["tenant_name"] for item in items)


def test_customer_users_never_lists_platform_or_customer_administrators(platform):
    response = platform.get("/api/v1/platform-admin/customer-users", params={"page_size": 200})
    assert response.status_code == 200, response.text
    body = response.json()
    labels = {item["role_label"] for item in body["items"]}
    assert "Platform Administrator" not in labels and "Customer Administrator" not in labels
    assert body["page"] == 1 and body["pages"] >= 1 and body["total"] >= len(body["items"])


def test_customer_users_filters_by_tenant_role_and_search(platform, customer):
    tenant_id = customer["id"]
    invited = platform.post(
        f"/api/v1/platform-admin/tenants/{tenant_id}/customer-admins",
        json={
            "email": f"ada-{uuid.uuid4().hex[:6]}@example.invalid",
            "display_name": "Ada Admin",
            "reason": "New customer administrator",
        },
    )
    assert invited.status_code == 200, invited.text
    # The new tenant has only its administrator, who belongs in the Customer administrators list, not here.
    only_tenant = platform.get(
        "/api/v1/platform-admin/customer-users", params={"tenant_id": tenant_id, "status": "INVITED"}
    ).json()
    assert only_tenant["items"] == [] and only_tenant["total"] == 0
    viewers = platform.get("/api/v1/platform-admin/customer-users", params={"role": "VIEWER", "page_size": 50}).json()
    assert all(item["role_label"] == "Viewer" for item in viewers["items"])
    nobody = platform.get("/api/v1/platform-admin/customer-users", params={"q": f"no-such-{uuid.uuid4().hex}"}).json()
    assert nobody["items"] == [] and nobody["total"] == 0


def test_customer_users_pages_and_limits_page_size(platform):
    first = platform.get("/api/v1/platform-admin/customer-users", params={"page_size": 1}).json()
    assert len(first["items"]) <= 1 and first["page_size"] == 1
    huge = platform.get("/api/v1/platform-admin/customer-users", params={"page_size": 10_000}).json()
    assert huge["page_size"] == 200
    beyond = platform.get("/api/v1/platform-admin/customer-users", params={"page": 10_000}).json()
    assert beyond["page"] == beyond["pages"]


@pytest.mark.parametrize("role", ["CUSTOMER_ADMIN", "LEADER", "VIEWER"])
def test_only_platform_administrators_see_the_account_lists(role):
    client = _client_with_role(role)
    for path in ("/api/v1/platform-admin/platform-users", "/api/v1/platform-admin/customer-users"):
        response = client.get(path)
        assert response.status_code == 403, (path, response.text)
        assert response.json()["detail"]["code"] == "PLATFORM_ADMIN_REQUIRED"


def test_role_catalog_describes_every_built_in_role_and_permission(platform):
    response = platform.get("/api/v1/platform-admin/role-catalog")
    assert response.status_code == 200, response.text
    body = response.json()
    codes = [role["code"] for role in body["roles"]]
    assert codes[:2] == ["PLATFORM_ADMIN", "CUSTOMER_ADMIN"] and codes[-1] == "VIEWER"
    assert {
        "TRIAGE_LEAD",
        "INVESTIGATOR",
        "RISK_REVIEWER",
        "REGULATORY_REVIEWER",
        "REVIEWER",
        "APPROVER",
        "LEADER",
    } <= set(codes)
    roles = {role["code"]: role for role in body["roles"]}
    assert roles["VIEWER"]["permissions"] == []
    assert "decision.sign" not in roles["CUSTOMER_ADMIN"]["permissions"]
    assert all(role["description"] and role["label"] for role in body["roles"])
    # Every permission a role grants is described, and each lists exactly the roles that grant it.
    described = {permission["code"]: permission for permission in body["permissions"]}
    for role in body["roles"]:
        for code in role["permissions"]:
            assert role["code"] in described[code]["roles"]
    assert set(described["decision.sign"]["roles"]) == {"PLATFORM_ADMIN", "APPROVER", "LEADER"}
    assert roles["PLATFORM_ADMIN"]["account_holders"] >= 1


@pytest.mark.parametrize("role", ["CUSTOMER_ADMIN", "LEADER"])
def test_only_platform_administrators_read_the_role_catalog(role):
    response = _client_with_role(role).get("/api/v1/platform-admin/role-catalog")
    assert response.status_code == 403 and response.json()["detail"]["code"] == "PLATFORM_ADMIN_REQUIRED"
