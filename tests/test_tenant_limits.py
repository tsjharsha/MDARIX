"""Each customer keeps the limits it was given; another customer on the same plan cannot change them."""

import uuid

from fastapi.testclient import TestClient

from backend.app.access.common import _active_plan_limits
from backend.app.db.models.foundation import FeatureEntitlement, PlanDefinition
from backend.app.db.session import SessionLocal
from backend.app.db.tenant_scope import bind_system
from backend.app.main import app
from tests.conftest import authenticated_client

PASSWORD = "Limits-Test-Password-2026!"


def _customer(platform, users: int, connectors: int) -> dict:
    code = f"LIM{uuid.uuid4().hex[:6].upper()}"
    made = platform.post(
        "/api/v1/platform-admin/customers",
        json={
            "company_name": f"Limits {code}",
            "tenant_code": code,
            "plan_code": "STARTER",
            "licensed_users_limit": users,
            "customer_admin_limit": 2,
            "connector_limit": connectors,
        },
    )
    assert made.status_code == 200, made.text
    return made.json()


def _limits(tenant_id: str) -> dict:
    with SessionLocal() as db:
        bind_system(db, "test: read limits")
        return _active_plan_limits(db, uuid.UUID(tenant_id))


def test_a_new_customer_does_not_change_another_customers_limits():
    platform = authenticated_client()
    with SessionLocal() as db:
        bind_system(db, "test: plan limits before")
        plan = db.query(PlanDefinition).filter(PlanDefinition.code == "STARTER").first()
        before = (
            {
                row.feature_code: row.limits
                for row in db.query(FeatureEntitlement).filter(FeatureEntitlement.plan_id == plan.id)
            }
            if plan
            else {}
        )
    first = _customer(platform, users=3, connectors=1)
    second = _customer(platform, users=50, connectors=9)
    assert _limits(first["id"])["licensed_users_limit"] == 3
    assert _limits(first["id"])["connector_limit"] == 1
    assert _limits(second["id"])["licensed_users_limit"] == 50
    with SessionLocal() as db:
        bind_system(db, "test: plan limits after")
        plan = db.query(PlanDefinition).filter(PlanDefinition.code == "STARTER").first()
        after = {
            row.feature_code: row.limits
            for row in db.query(FeatureEntitlement).filter(FeatureEntitlement.plan_id == plan.id)
        }
    if before:
        assert after == before  # the shared plan was not rewritten by either customer


def _customer_admin(platform, tenant_id: str) -> TestClient:
    email = f"limits-admin-{uuid.uuid4().hex[:8]}@example.invalid"
    made = platform.post(
        f"/api/v1/platform-admin/tenants/{tenant_id}/customer-admins",
        json={"email": email, "display_name": "Limits admin", "reason": "Limits test"},
    )
    assert made.status_code == 200, made.text
    client = TestClient(app)
    assert (
        client.post(
            "/api/v1/auth/activate-account", json={"token": made.json()["development_token"], "password": PASSWORD}
        ).status_code
        == 200
    )
    assert client.post("/api/v1/auth/signin", json={"email": email, "password": PASSWORD}).status_code == 200
    return client


def test_the_connector_limit_is_enforced_per_customer():
    platform = authenticated_client()
    tenant = _customer(platform, users=5, connectors=1)
    admin = _customer_admin(platform, tenant["id"])
    first = admin.post(
        "/api/v1/admin/configuration/connectors",
        json={"code": "ONLY_ONE", "connector_type": "TEST", "configuration": {}},
    )
    assert first.status_code == 200, first.text
    second = admin.post(
        "/api/v1/admin/configuration/connectors",
        json={"code": "ONE_TOO_MANY", "connector_type": "TEST", "configuration": {}},
    )
    assert second.status_code == 409 and second.json()["detail"]["code"] == "CONNECTOR_LIMIT_REACHED"


def test_a_customers_limits_can_be_changed_later_but_not_below_what_it_uses():
    platform = authenticated_client()
    tenant = _customer(platform, users=5, connectors=1)
    admin = _customer_admin(platform, tenant["id"])
    assert (
        admin.post(
            "/api/v1/admin/configuration/connectors",
            json={"code": "ONE", "connector_type": "TEST", "configuration": {}},
        ).status_code
        == 200
    )
    path = f"/api/v1/platform-admin/customers/{tenant['id']}/limits"
    reason = "Customer upgraded their contract"
    raised = platform.put(path, json={"connector_limit": 3, "licensed_users_limit": 12, "reason": reason})
    assert raised.status_code == 200, raised.text
    assert raised.json()["limits"]["connector_limit"] == 3 and raised.json()["limits"]["licensed_users_limit"] == 12
    assert (
        admin.post(
            "/api/v1/admin/configuration/connectors",
            json={"code": "TWO", "connector_type": "TEST", "configuration": {}},
        ).status_code
        == 200
    )
    too_low = platform.put(path, json={"connector_limit": 1, "reason": reason})
    assert too_low.status_code == 409 and too_low.json()["detail"]["code"] == "LIMIT_BELOW_USAGE"
    assert platform.put(path, json={"reason": reason}).status_code == 422
    assert platform.put(path, json={"connector_limit": 3, "reason": "short"}).status_code == 422
    assert admin.put(path, json={"connector_limit": 50, "reason": reason}).status_code == 403
    usage = platform.get(f"/api/v1/platform-admin/customers/{tenant['id']}/usage").json()
    assert usage["usage"]["connectors"] == 2 and usage["limits"]["connector_limit"] == 3
