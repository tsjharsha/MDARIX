"""Administrator roles never hold approval authority, by any route (separation of duties; access/governance.py)."""

import pytest

from backend.app.db.session import SessionLocal
from backend.app.db.tenant_scope import bind_system
from tests.test_customer_admin_account_security import _client_for, _tenant, _user

AUTHORITY = {"object_type": "Decision", "decision_type": "INVESTIGATION_REVIEW", "authority": "AUTHORIZED"}


@pytest.fixture(scope="module")
def admin():
    with SessionLocal() as db:
        bind_system(db, "test: a customer administrator managing approval authorities")
        user = _user(db, _tenant(db, "AUTH"), "CUSTOMER_ADMIN", "authority-admin")
        db.commit()
        return _client_for(db, user)


@pytest.mark.parametrize("role", ["CUSTOMER_ADMIN", "Customer Administrator", "PLATFORM_ADMIN", "ADMINISTRATOR"])
def test_creating_an_authority_for_an_administrator_role_is_refused(admin, role):
    response = admin.post(
        "/api/v1/admin/governance/approval-authorities", json={**AUTHORITY, "role_name": role, "version": "t1"}
    )
    assert response.status_code == 422, response.text
    assert response.json()["detail"]["code"] == "ROLE_CANNOT_APPROVE"


def test_an_approver_authority_can_be_made_but_not_turned_into_an_administrator_one(admin):
    created = admin.post(
        "/api/v1/admin/governance/approval-authorities", json={**AUTHORITY, "role_name": "APPROVER", "version": "t2"}
    )
    assert created.status_code == 200, created.text
    authority_id = created.json()["authority_id"]
    edited = admin.patch(
        f"/api/v1/admin/control-plane/approval-authorities/{authority_id}",
        json={"values": {"role_name": "CUSTOMER_ADMIN"}, "reason": "attempt to approve as an administrator"},
    )
    assert edited.status_code == 422 and edited.json()["detail"]["code"] == "ROLE_CANNOT_APPROVE"
    activated = admin.patch(
        f"/api/v1/admin/governance/policies/authority/{authority_id}/status",
        json={"status": "ACTIVE", "reason": "approvers can approve investigation reviews"},
    )
    assert activated.status_code == 200, activated.text
