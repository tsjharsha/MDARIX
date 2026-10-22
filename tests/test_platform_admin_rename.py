"""Platform Admin changes a platform account's name (Identity & Access > Platform users > Change name, 0.10.47).

The screen sends PATCH /api/v1/admin/control-plane/users/{id} with only display_name: the name is trimmed and checked
(1 to 120 characters, as every form that sets a name), and the audit event keeps the name before and after.
"""

from __future__ import annotations

import uuid

import pytest

from backend.app.db.models.foundation import AuditEvent, AuthUser, Tenant
from backend.app.db.session import SessionLocal
from tests.conftest import authenticated_client
from tests.test_customer_admin_account_security import _client_for, _tenant, _user


@pytest.fixture(scope="module")
def accounts():
    platform = authenticated_client()
    me = platform.get("/api/v1/auth/session").json()
    db = SessionLocal()
    try:
        tenant = db.get(Tenant, uuid.UUID(me["tenant_id"]))
        colleague = _user(db, tenant, "PLATFORM_ADMIN", "rename-colleague")
        elsewhere = _user(db, _tenant(db, "RENAME"), "PLATFORM_ADMIN", "rename-elsewhere")
        customer_tenant = _tenant(db, "RENAME-CA")
        customer_admin = _user(db, customer_tenant, "CUSTOMER_ADMIN", "rename-customer-admin")
        platform_in_customer = _user(db, customer_tenant, "PLATFORM_ADMIN", "rename-platform-in-customer")
        db.commit()
        customer = _client_for(db, customer_admin)
        db.commit()
        ids = {
            "me": me["user_id"],
            "colleague": str(colleague.id),
            "elsewhere": str(elsewhere.id),
            "platform_in_customer": str(platform_in_customer.id),
        }
    finally:
        db.close()
    return platform, customer, ids


def _rename(client, user_id, value):
    return client.patch(f"/api/v1/admin/control-plane/users/{user_id}", json={"values": {"display_name": value}})


def _stored(user_id) -> str:
    with SessionLocal() as db:
        return db.get(AuthUser, uuid.UUID(user_id)).display_name


def test_platform_admin_renames_a_platform_account_trimmed_and_audited(accounts):
    platform, _, ids = accounts
    response = _rename(platform, ids["colleague"], "  Asha   Rao  ")
    assert response.status_code == 200, response.text
    assert _stored(ids["colleague"]) == "Asha Rao"
    listed = platform.get("/api/v1/platform-admin/platform-users", params={"q": "Asha Rao"}).json()["items"]
    assert [item["display_name"] for item in listed if item["id"] == ids["colleague"]] == ["Asha Rao"]
    with SessionLocal() as db:
        event = (
            db.query(AuditEvent)
            .filter(AuditEvent.entity_id == ids["colleague"], AuditEvent.action == "USER_UPDATED")
            .order_by(AuditEvent.created_at.desc())
            .first()
        )
        assert event is not None and event.actor_ref == ids["me"]
        assert event.old_values == {"display_name": "rename-colleague"}
        assert event.new_values == {"display_name": "Asha Rao"}
    # One's own name too: a name is not access.
    assert _rename(platform, ids["me"], "Platform Admin (renamed)").status_code == 200
    assert _rename(platform, ids["me"], "Platform Admin").status_code == 200


@pytest.mark.parametrize("value", ["", "   ", "x" * 121, 42, None, "Asha\x00Rao", ["Asha"]])
def test_a_name_that_is_empty_too_long_or_not_text_is_refused(accounts, value):
    platform, _, ids = accounts
    before = _stored(ids["colleague"])
    response = _rename(platform, ids["colleague"], value)
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "DISPLAY_NAME_INVALID"
    assert _stored(ids["colleague"]) == before


def test_the_longest_name_is_accepted(accounts):
    platform, _, ids = accounts
    assert _rename(platform, ids["colleague"], "A" * 120).status_code == 200
    assert _stored(ids["colleague"]) == "A" * 120


def test_only_accounts_of_the_administrators_own_organization_and_never_by_a_customer(accounts):
    platform, customer, ids = accounts
    # The route is scoped to the administrator's organization (the screen offers Change name only there).
    assert _rename(platform, ids["elsewhere"], "Not Renamed").status_code == 404
    assert _stored(ids["elsewhere"]) == "rename-elsewhere"
    # A customer administrator cannot rename a platform account in their own organization.
    refused = _rename(customer, ids["platform_in_customer"], "Not Renamed")
    assert refused.status_code == 403 and refused.json()["detail"]["code"] == "PLATFORM_USER_PROTECTED"
    assert _stored(ids["platform_in_customer"]) == "rename-platform-in-customer"
