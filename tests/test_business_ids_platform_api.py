"""Platform administration answers carry business identifiers (md26): customers, tenants, users, subscriptions,
connectors, products and AI executions show CUST000001-style identifiers next to their UUIDs, their displayed
references carry ``<role>_business_id``, searches find records by business identifier and CSV exports include it.

The ``test_unit_*`` tests need no database. The others call the API against the test database.
"""

import csv
import io
import re
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from backend.app.access.platform_console import _tenant_names, _with_tenant
from backend.app.access.platform_customer_admins import _row
from backend.app.db.models.customer_lifecycle import Customer
from backend.app.db.models.foundation import AuthUser, PlanDefinition, Tenant
from backend.app.db.session import SessionLocal
from tests.conftest import authenticated_client

CUSTOMER_ID = re.compile(r"CUST\d{6}")
TENANT_ID = re.compile(r"TEN\d{6}")
USER_ID = re.compile(r"USR\d{6}")


# No database ----------------------------------------------------------------------------------------------------


def test_unit_console_rows_name_the_tenant_and_customer_by_business_id():
    tenant_id = uuid.uuid4()
    names = {
        tenant_id: {
            "tenant_key": "ACME",
            "tenant_name": "Acme Production",
            "customer_name": "Acme",
            "tenant_business_id": "TEN000007",
            "customer_business_id": "CUST000003",
        }
    }
    item = _with_tenant({"id": "x"}, names, tenant_id)
    assert item["tenant_id"] == str(tenant_id) and item["tenant_business_id"] == "TEN000007"
    assert item["customer_business_id"] == "CUST000003" and item["tenant_key"] == "ACME"
    # A row without a (known) tenant keeps the same keys, empty.
    unknown = _with_tenant({"id": "y"}, names, None)
    assert unknown["tenant_id"] is None and unknown["tenant_business_id"] is None
    assert unknown["customer_business_id"] is None


def test_unit_tenant_names_without_tenants_reads_nothing():
    # No tenant ids: answered without touching the session.
    assert _tenant_names(None, [None, None]) == {}


def test_unit_customer_admin_rows_carry_their_business_ids():
    customer = Customer(id=uuid.uuid4(), business_id="CUST000002", display_name="Acme", legal_name="Acme Ltd")
    tenant = Tenant(
        id=uuid.uuid4(), business_id="TEN000004", tenant_key="ACME", name="Acme", display_name="Acme", status="ACTIVE"
    )
    user = AuthUser(
        id=uuid.uuid4(),
        business_id="USR000010",
        tenant_id=tenant.id,
        username="ada@example.invalid",
        display_name="Ada",
        status="ACTIVE",
        email_verified=True,
    )
    row = _row(user, tenant, customer, 2)
    assert (row["business_id"], row["tenant_business_id"], row["customer_business_id"]) == (
        "USR000010",
        "TEN000004",
        "CUST000002",
    )
    assert row["id"] == str(user.id) and row["can_suspend"]
    orphan = _row(user, None, None, 1)
    assert orphan["business_id"] == "USR000010"
    assert orphan["tenant_business_id"] is None and orphan["customer_business_id"] is None


# Database-backed ------------------------------------------------------------------------------------------------


@pytest.fixture(scope="module")
def platform():
    return authenticated_client()


@pytest.fixture
def customer(platform):
    code = f"BID{uuid.uuid4().hex[:6].upper()}"
    created = platform.post(
        "/api/v1/platform-admin/customers",
        json={"company_name": f"Business Id Test {code}", "tenant_code": code, "plan_code": "STARTER"},
    )
    assert created.status_code == 200, created.text
    return created.json()


def _plan_id(code="STARTER") -> str:
    db = SessionLocal()
    try:
        return str(db.query(PlanDefinition.id).filter(PlanDefinition.code == code).scalar())
    finally:
        db.close()


def _csv(response) -> list[dict]:
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("text/csv")
    return list(csv.DictReader(io.StringIO(response.text)))


def test_a_new_customer_answers_with_its_tenant_and_customer_business_ids(platform, customer):
    assert TENANT_ID.fullmatch(customer["business_id"]) and CUSTOMER_ID.fullmatch(customer["customer_business_id"])
    # The older identifiers are still returned.
    assert customer["customer_identifier"] and customer["tenant_identifier"]
    db = SessionLocal()
    try:
        tenant = db.query(Tenant).filter(Tenant.id == uuid.UUID(customer["id"])).one()
        owner = db.query(Customer).filter(Customer.id == uuid.UUID(customer["customer_id"])).one()
        assert (tenant.business_id, owner.business_id) == (customer["business_id"], customer["customer_business_id"])
    finally:
        db.close()


def test_the_customer_list_shows_and_finds_business_ids_and_exports_them(platform, customer):
    for term in (customer["business_id"].lower(), customer["customer_business_id"].lower()):
        listed = platform.get("/api/v1/platform-admin/customers", params={"q": term}).json()["items"]
        mine = [item for item in listed if item["id"] == customer["id"]]
        assert len(mine) == 1, term
        assert mine[0]["business_id"] == customer["business_id"]
        assert mine[0]["customer_business_id"] == customer["customer_business_id"]
    exported = platform.get("/api/v1/platform-admin/customers", params={"q": customer["business_id"], "format": "csv"})
    header = next(csv.reader(io.StringIO(exported.text)))
    assert header[:5] == ["id", "business_id", "customer_id", "customer_business_id", "customer_identifier"]
    rows = _csv(exported)
    assert [(row["id"], row["business_id"]) for row in rows] == [(customer["id"], customer["business_id"])]
    assert rows[0]["customer_business_id"] == customer["customer_business_id"]
    detail = platform.get(f"/api/v1/platform-admin/customers/{customer['id']}").json()
    assert detail["business_id"] == customer["business_id"]


def test_the_customer_directory_shows_and_finds_customer_and_tenant_business_ids(platform, customer):
    for term in (customer["customer_business_id"].lower(), customer["business_id"].lower()):
        listed = platform.get("/api/v1/platform-admin/customer-accounts", params={"q": term}).json()["items"]
        assert [item["id"] for item in listed] == [customer["customer_id"]], term
        row = listed[0]
        assert row["business_id"] == customer["customer_business_id"]
        assert [tenant["business_id"] for tenant in row["tenants"]] == [customer["business_id"]]
        assert row["customer_identifier"] == customer["customer_identifier"]


def test_the_customer_record_and_its_tabs_name_tenants_and_people_by_business_id(platform, customer):
    record = platform.get(f"/api/v1/platform-admin/customer-records/{customer['customer_id']}").json()
    assert record["customer"]["business_id"] == customer["customer_business_id"]
    assert [tenant["business_id"] for tenant in record["tenants"]] == [customer["business_id"]]
    added = platform.post(
        f"/api/v1/platform-admin/tenants/{customer['id']}/customer-admins",
        json={
            "email": f"bid-{uuid.uuid4().hex[:6]}@example.invalid",
            "display_name": "Bea Business",
            "reason": "New customer administrator",
        },
    )
    assert added.status_code == 200, added.text
    tab = platform.get(f"/api/v1/platform-admin/customer-records/{customer['customer_id']}/tabs/Administrators").json()
    admin = next(item for item in tab["items"] if item["id"] == added.json()["id"])
    assert USER_ID.fullmatch(admin["business_id"]) and admin["tenant_business_id"] == customer["business_id"]
    usage = platform.get(f"/api/v1/platform-admin/customer-records/{customer['customer_id']}/tabs/Usage").json()
    assert [item["tenant_business_id"] for item in usage["items"]] == [customer["business_id"]]


def test_the_tenant_list_shows_and_finds_business_ids_and_exports_them(platform, customer):
    for term in (customer["business_id"].lower(), customer["customer_business_id"].lower()):
        listed = platform.get("/api/v1/platform-admin/tenants", params={"q": term}).json()["items"]
        mine = [item for item in listed if item["id"] == customer["id"]]
        assert len(mine) == 1, term
        assert mine[0]["business_id"] == customer["business_id"]
        assert mine[0]["customer_business_id"] == customer["customer_business_id"]
    exported = platform.get("/api/v1/platform-admin/tenants", params={"q": customer["business_id"], "format": "csv"})
    header = next(csv.reader(io.StringIO(exported.text)))
    assert header[:3] == ["id", "business_id", "tenant_identifier"]
    assert [(row["id"], row["business_id"]) for row in _csv(exported)] == [(customer["id"], customer["business_id"])]
    record = platform.get(f"/api/v1/platform-admin/tenants/{customer['id']}").json()["tenant"]
    assert record["business_id"] == customer["business_id"]
    assert record["customer_business_id"] == customer["customer_business_id"]
    assert record["tenant_identifier"] == customer["tenant_identifier"]


def test_customer_administrators_carry_and_are_found_by_business_ids(platform, customer):
    added = platform.post(
        f"/api/v1/platform-admin/tenants/{customer['id']}/customer-admins",
        json={
            "email": f"bid-{uuid.uuid4().hex[:6]}@example.invalid",
            "display_name": "Cal Customer",
            "reason": "New customer administrator",
        },
    )
    assert added.status_code == 200, added.text
    admin = added.json()
    assert USER_ID.fullmatch(admin["business_id"])
    assert admin["tenant_business_id"] == customer["business_id"]
    assert admin["customer_business_id"] == customer["customer_business_id"]
    for term in (admin["business_id"].lower(), customer["business_id"].lower(), customer["customer_business_id"]):
        found = platform.get("/api/v1/platform-admin/customer-admins", params={"q": term}).json()["items"]
        assert admin["id"] in {item["id"] for item in found}, term
    options = platform.get("/api/v1/platform-admin/customer-admin-tenants").json()["items"]
    mine = next(item for item in options if item["id"] == customer["id"])
    assert mine["business_id"] == customer["business_id"]
    assert mine["customer_business_id"] == customer["customer_business_id"]


def test_console_views_name_subscriptions_tenants_and_customers_by_business_id(platform, customer):
    now = datetime.now(timezone.utc)
    changed = platform.post(
        f"/api/v1/platform/customers/{customer['id']}/subscription",
        json={
            "plan_id": _plan_id(),
            "starts_at": now.isoformat(),
            "expires_at": (now + timedelta(days=30)).isoformat(),
            "reason": "Annual licence",
        },
    )
    assert changed.status_code == 200, changed.text
    renewals = platform.get("/api/v1/platform-admin/console/renewals").json()["items"]
    mine = next(item for item in renewals if item["tenant_id"] == customer["id"])
    assert re.fullmatch(r"SUB\d{6}", mine["subscription_business_id"])
    assert mine["tenant_business_id"] == customer["business_id"]
    assert mine["customer_business_id"] == customer["customer_business_id"]
    # Customer creation is audited in the platform administrator's own tenant, by that administrator.
    audit = platform.get("/api/v1/platform-admin/console/audit", params={"q": "customer_created", "page_size": 5})
    created = next(item for item in audit.json()["items"] if item["action"] == "CUSTOMER_CREATED")
    assert TENANT_ID.fullmatch(created["tenant_business_id"]) and USER_ID.fullmatch(created["actor_business_id"])
    assert created["actor"] and not USER_ID.fullmatch(created["actor"])
    for item in platform.get("/api/v1/platform-admin/console/support-access").json()["items"]:
        assert "platform_user_business_id" in item and "approved_by_business_id" in item


def test_product_configuration_names_products_and_versions_by_business_id(platform, customer):
    code = uuid.uuid4().hex[:6].upper()
    product = platform.post(
        "/api/v1/platform/product-configuration/products",
        json={"tenant_id": customer["id"], "product_identifier": f"P-{code}", "name": "Infusion Pump"},
    )
    assert product.status_code == 200, product.text
    product = product.json()
    assert re.fullmatch(r"PROD\d{6}", product["business_id"])
    edited = platform.patch(
        f"/api/v1/platform/product-configuration/{customer['id']}/products/{product['id']}", json={"name": "Pump 2"}
    )
    assert edited.status_code == 200 and edited.json()["business_id"] == product["business_id"]
    version = platform.post(
        "/api/v1/platform/product-configuration/product-versions",
        json={"tenant_id": customer["id"], "product_id": product["id"], "version_identifier": "1.0"},
    )
    assert version.status_code == 200, version.text
    version = version.json()
    assert re.fullmatch(r"PV\d{6}", version["business_id"])
    assert version["product_business_id"] == product["business_id"]
    config = platform.get(f"/api/v1/platform/product-configuration/{customer['id']}").json()
    assert config["tenant"]["business_id"] == customer["business_id"]
    assert [item["business_id"] for item in config["products"]] == [product["business_id"]]
    listed = next(item for item in config["versions"] if item["id"] == version["id"])
    assert (listed["business_id"], listed["product_business_id"]) == (version["business_id"], product["business_id"])
