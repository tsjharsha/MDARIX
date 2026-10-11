"""Erasing a person's data in an organization under a legal hold is refused as a legal hold (409 LEGAL_HOLD), by the
customer administrator's and the platform administrator's erase alike; nothing is erased."""

import pytest

from backend.app.db.models.foundation import AuthUser, Tenant
from backend.app.db.session import SessionLocal
from backend.app.db.tenant_scope import bind_system
from tests.conftest import authenticated_client
from tests.test_customer_admin_account_security import _client_for, _tenant, _user

REASON = {"reason": "The person asked in writing for their data to be erased (ticket 4711)."}


@pytest.fixture
def held():
    """An organization under a legal hold, its administrator, and an offboarded person in it."""
    with SessionLocal() as db:
        bind_system(db, "test: an organization under a legal hold")
        tenant = _tenant(db, "HOLD")
        admin = _user(db, tenant, "CUSTOMER_ADMIN", "hold-admin")
        person = _user(db, tenant, "Investigator", "hold-person")
        person.status = "OFFBOARDED"
        tenant.legal_hold = True
        tenant.legal_hold_reason = "Litigation hold for test"
        db.commit()
        client = _client_for(db, admin)
        return client, person.id, person.username


def _unchanged(person_id, email):
    with SessionLocal() as db:
        bind_system(db, "test: the person is untouched")
        row = db.get(AuthUser, person_id)
        assert row is not None and row.username == email and row.status == "OFFBOARDED"


@pytest.mark.parametrize("who", ["customer_admin", "platform_admin"])
def test_an_erasure_under_a_legal_hold_is_refused_as_such(held, who):
    client, person_id, email = held
    if who == "customer_admin":
        response = client.post(f"/api/v1/admin/identity/users/{person_id}/erase", json=REASON)
    else:
        from tests.support_grants import grant_support_access

        with SessionLocal() as db:
            bind_system(db, "test: the person's organization")
            tenant_id = db.get(AuthUser, person_id).tenant_id
        grant_support_access(tenant_id, areas=("PEOPLE",))
        response = authenticated_client().post(f"/api/v1/platform-admin/users/{person_id}/erase", json=REASON)
    assert response.status_code == 409, response.text
    detail = response.json()["detail"]
    assert detail["code"] == "LEGAL_HOLD"
    assert detail["message"] == (
        "This organization is under a legal hold; personal data cannot be erased until the hold is lifted."
    )
    _unchanged(person_id, email)


def test_an_active_person_is_still_told_to_offboard_first(held):
    client, person_id, _email = held
    with SessionLocal() as db:
        bind_system(db, "test: lift the hold, keep an active person")
        person = db.query(AuthUser).filter(AuthUser.id == person_id).one()
        db.get(Tenant, person.tenant_id).legal_hold = False
        person.status = "ACTIVE"
        db.commit()
    response = client.post(f"/api/v1/admin/identity/users/{person_id}/erase", json=REASON)
    assert response.status_code == 409 and response.json()["detail"]["code"] == "USER_NOT_OFFBOARDED"
