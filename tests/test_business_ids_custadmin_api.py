"""Customer administration and the signed-in user's context carry business identifiers (md26).

The session and /me answers name the user, their organization and its customer by business identifier
(USR000001, TEN000001, CUST000001); the customer administrator's users, connectors and product catalog answer with
``business_id`` next to their UUIDs (a version also with its product's); the data-plane search finds products by
business identifier and its CSV export carries a ``business_id`` column after ``id``.

The ``test_unit_*`` tests need no database. The others call the API against the test database, each in a fresh
organization of its own (never the golden one).
"""

import csv
import io
import re
import uuid
from types import SimpleNamespace

import pytest

from backend.app.access.common import _safe_connector_summary
from backend.app.auth_router import _signin_response
from backend.app.db.models.customer_lifecycle import Customer
from backend.app.db.models.foundation import AuthUser
from backend.app.db.session import SessionLocal
from backend.app.db.tenant_scope import bind_system
from tests.test_customer_admin_account_security import _client_for, _tenant, _user

CUSTOMER_ID = re.compile(r"CUST\d{6}")
TENANT_ID = re.compile(r"TEN\d{6}")
USER_ID = re.compile(r"USR\d{6}")
CONNECTOR_ID = re.compile(r"CNX\d{6}")
PRODUCT_ID = re.compile(r"PROD\d{6}")
VERSION_ID = re.compile(r"PV\d{6}")


# No database ----------------------------------------------------------------------------------------------------


def test_unit_the_sign_in_answer_names_the_user_by_business_id():
    user = AuthUser(
        id=uuid.uuid4(),
        business_id="USR000042",
        tenant_id=uuid.uuid4(),
        username="ada@example.invalid",
        display_name="Ada",
        role="VIEWER",
    )
    body = _signin_response(user)
    assert body["user_id"] == str(user.id) and body["business_id"] == "USR000042"
    assert body["tenant_id"] == str(user.tenant_id)


def test_unit_a_connector_summary_carries_its_business_id():
    row = SimpleNamespace(
        id=uuid.uuid4(),
        business_id="CNX000003",
        code="QMS",
        connector_type="REST",
        version="v1",
        status="ACTIVE",
        configuration={},
    )
    summary = _safe_connector_summary(row)
    assert summary["id"] == str(row.id) and summary["business_id"] == "CNX000003"


# Database-backed ------------------------------------------------------------------------------------------------


@pytest.fixture(scope="module")
def organization():
    """A fresh organization (registered on the shared data plane at commit) and its customer administrator."""
    with SessionLocal() as db:
        bind_system(db, "test: a customer administrator of a fresh organization")
        tenant = _tenant(db, "BIDCA")
        admin = _user(db, tenant, "CUSTOMER_ADMIN", "bid-ca-admin")
        db.commit()
        customer = db.query(Customer).filter(Customer.id == tenant.customer_id).one()
        return {
            "client": _client_for(db, admin),
            "tenant_id": str(tenant.id),
            "tenant_business_id": tenant.business_id,
            "customer_business_id": customer.business_id,
            "admin_id": str(admin.id),
            "admin_business_id": admin.business_id,
        }


def test_the_signed_in_context_names_the_user_organization_and_customer(organization):
    client = organization["client"]
    assert USER_ID.fullmatch(organization["admin_business_id"])
    assert TENANT_ID.fullmatch(organization["tenant_business_id"])
    assert CUSTOMER_ID.fullmatch(organization["customer_business_id"])
    expected = {
        "business_id": organization["admin_business_id"],
        "tenant_business_id": organization["tenant_business_id"],
        "customer_business_id": organization["customer_business_id"],
    }
    for path in ("/api/v1/me/context", "/api/v1/session/context", "/api/v1/auth/session"):
        response = client.get(path)
        assert response.status_code == 200, (path, response.text)
        body = response.json()
        assert {key: body.get(key) for key in expected} == expected, path
        # The UUIDs stay.
        assert body["user_id"] == organization["admin_id"] and body["tenant_id"] == organization["tenant_id"]
    session = client.get("/api/v1/session/context").json()
    assert session["current_tenant"]["tenant_business_id"] == organization["tenant_business_id"]
    membership = next(item for item in session["memberships"] if item["tenant_id"] == organization["tenant_id"])
    assert membership["tenant_business_id"] == organization["tenant_business_id"]


def test_users_carry_their_business_id(organization):
    client = organization["client"]
    created = client.post(
        "/api/v1/admin/identity/users",
        json={
            "email": f"bid-user-{uuid.uuid4().hex[:8]}@synthetic.invalid",
            "display_name": "Bo Business",
            "company": "Business Id Test",
            "role": "VIEWER",
        },
    )
    assert created.status_code in {200, 201}, created.text
    user = created.json()
    assert USER_ID.fullmatch(user["business_id"])
    with SessionLocal() as db:
        bind_system(db, "test: read the new user's business id")
        stored = db.query(AuthUser.business_id).filter(AuthUser.id == uuid.UUID(user["id"])).scalar()
    assert stored == user["business_id"]

    listed = client.get("/api/v1/admin/identity/users").json()
    assert next(item for item in listed if item["id"] == user["id"])["business_id"] == user["business_id"]
    detail = client.get(f"/api/v1/admin/identity/users/{user['id']}").json()
    assert detail["user_id"] == user["id"] and detail["business_id"] == user["business_id"]
    access = client.get(f"/api/v1/admin/identity/users/{user['id']}/effective-access").json()
    assert access["business_id"] == user["business_id"]
    suspended = client.patch(f"/api/v1/admin/identity/users/{user['id']}/status", json={"status": "SUSPENDED"})
    assert suspended.status_code == 200, suspended.text
    assert suspended.json()["business_id"] == user["business_id"]
    renamed = client.patch(
        f"/api/v1/admin/control-plane/users/{user['id']}", json={"values": {"display_name": "Bo Renamed"}}
    )
    assert renamed.status_code == 200, renamed.text
    assert renamed.json()["business_id"] == user["business_id"]


def test_connectors_carry_their_business_id(organization):
    client = organization["client"]
    code = f"BIDCNX{uuid.uuid4().hex[:6].upper()}"
    created = client.post("/api/v1/admin/configuration/connectors", json={"code": code, "connector_type": "FILE"})
    assert created.status_code == 200, created.text
    connector = created.json()
    assert CONNECTOR_ID.fullmatch(connector["business_id"])
    listed = client.get("/api/v1/admin/configuration/connectors").json()
    mine = next(item for item in listed if item["id"] == connector["connector_id"])
    assert mine["business_id"] == connector["business_id"]
    versions = client.get(f"/api/v1/admin/configuration/connectors/{code}/versions").json()
    assert [item["business_id"] for item in versions] == [connector["business_id"]]
    activated = client.patch(
        f"/api/v1/admin/configuration/connectors/{connector['connector_id']}/status", json={"status": "ACTIVE"}
    )
    assert activated.status_code == 200, activated.text
    assert activated.json()["business_id"] == connector["business_id"]


def test_the_product_catalog_carries_product_and_version_business_ids(organization):
    client = organization["client"]
    created = client.post(
        "/api/v1/admin/catalog/products",
        json={"product_identifier": f"BID-PRD-{uuid.uuid4().hex[:6]}", "name": "Business Id Pump"},
    )
    assert created.status_code == 200, created.text
    product = created.json()
    assert PRODUCT_ID.fullmatch(product["business_id"])
    listed = client.get("/api/v1/admin/catalog/products").json()
    assert next(item for item in listed if item["id"] == product["id"])["business_id"] == product["business_id"]

    version = client.post(
        "/api/v1/admin/catalog/product-versions", json={"product_id": product["id"], "version_identifier": "1.0"}
    )
    assert version.status_code == 200, version.text
    version = version.json()
    assert VERSION_ID.fullmatch(version["business_id"])
    assert version["product_business_id"] == product["business_id"]
    versions = client.get("/api/v1/admin/catalog/product-versions", params={"product_id": product["id"]}).json()
    assert [(item["business_id"], item["product_business_id"]) for item in versions] == [
        (version["business_id"], product["business_id"])
    ]
    updated = client.patch(f"/api/v1/admin/catalog/products/{product['id']}", json={"values": {"name": "Pump 2"}})
    assert updated.status_code == 200, updated.text
    assert updated.json()["business_id"] == product["business_id"]


def test_the_data_plane_finds_and_exports_products_by_business_id(organization):
    client = organization["client"]
    created = client.post(
        "/api/v1/admin/catalog/products",
        json={"product_identifier": f"BID-DP-{uuid.uuid4().hex[:6]}", "name": "Business Id Valve"},
    )
    assert created.status_code == 200, created.text
    product = created.json()
    listed = client.get("/api/v1/data-plane/products").json()["records"]
    assert next(item for item in listed if item["id"] == product["id"])["business_id"] == product["business_id"]

    found = client.get("/api/v1/data-plane/search", params={"q": product["business_id"].lower()})
    assert found.status_code == 200, found.text
    products = [item for item in found.json()["records"] if item["record_type"] == "product"]
    assert [item["id"] for item in products] == [product["id"]]

    exported = client.get("/api/v1/data-plane/export.csv")
    assert exported.status_code == 200, exported.text
    header = next(csv.reader(io.StringIO(exported.text)))
    assert header[:2] == ["id", "business_id"]
    rows = {row["id"]: row for row in csv.DictReader(io.StringIO(exported.text))}
    assert rows[product["id"]]["business_id"] == product["business_id"]


def test_the_lifecycle_names_the_organization_by_business_id(organization):
    response = organization["client"].get("/api/v1/admin/tenant/lifecycle")
    assert response.status_code == 200, response.text
    assert response.json()["tenant_business_id"] == organization["tenant_business_id"]
