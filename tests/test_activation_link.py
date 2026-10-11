"""Activation links issued by MDARIX support: platform administrators with a verified second factor only, for accounts
still waiting to be activated, single use, replacing earlier links, audited without the link or the address."""

import uuid
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qs, urlparse

import pytest
from fastapi.testclient import TestClient

from auth.durable import issue_invitation, new_session, peek
from backend.app.db.models.foundation import AuditEvent, AuthUser, Tenant
from backend.app.db.session import SessionLocal
from backend.app.db.tenant_scope import bind_system
from backend.app.main import app
from tests.test_customer_admin_account_security import _tenant, _user

URL = "/api/v1/platform-admin/users/{}/activation-link"


def _account(db, tenant, role, label, *, status="ACTIVE", mfa=False):
    user = _user(db, tenant, role, label)
    user.status = status
    user.email_verified = status == "ACTIVE"
    if mfa:
        # Enrolled: a session of this account exists only after its second factor was checked.
        user.mfa_secret_encrypted = "sealed-for-test"
        user.mfa_enrolled_at = datetime.now(timezone.utc)
    db.flush()
    return user


def _client(user_id, tenant_id, mfa_state=None):
    with SessionLocal() as db:
        token = new_session(db, user_id, tenant_id, mfa_state=mfa_state)
    client = TestClient(app)
    client.cookies.set("mdarix_session", token)
    return client


@pytest.fixture(scope="module")
def world():
    with SessionLocal() as db:
        bind_system(db, "test: activation link accounts")
        tenant = _tenant(db, "LINK")
        operator = _tenant(db, "OPS")
        made = {
            "platform": _account(db, operator, "PLATFORM_ADMIN", "link-platform", mfa=True),
            "platform_no_mfa": _account(db, operator, "PLATFORM_ADMIN", "link-platform-nomfa"),
            "customer_admin": _account(db, tenant, "CUSTOMER_ADMIN", "link-ca", mfa=True),
            "active": _account(db, tenant, "Investigator", "link-active"),
            "offboarded": _account(db, tenant, "Investigator", "link-offboarded", status="OFFBOARDED"),
        }
        db.commit()
        ids = {key: (user.id, user.tenant_id, user.username) for key, user in made.items()}
    from tests.support_grants import grant_support_access

    # MDARIX support issues links to the organization's people under the People access its administrators approved.
    grant_support_access(ids["customer_admin"][1], ids["platform"][0])
    return ids


def _invited(world):
    """A fresh invited account (each test gets its own, so links do not interfere)."""
    with SessionLocal() as db:
        bind_system(db, "test: invited account")
        tenant = db.get(Tenant, world["active"][1])
        user = _account(db, tenant, "Investigator", "link-invited", status="INVITED")
        db.commit()
        return user.id, user.tenant_id, user.username


def _as(world, key, mfa_state=None):
    user_id, tenant_id, _ = world[key]
    return _client(user_id, tenant_id, mfa_state)


def test_a_platform_administrator_gets_a_fresh_single_use_link(world):
    user_id, tenant_id, email = _invited(world)
    with SessionLocal() as db:
        bind_system(db, "test: the invitation that was emailed")
        emailed = issue_invitation(db, user_id, tenant_id)
    response = _as(world, "platform").post(URL.format(user_id))
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    body = response.json()
    assert set(body) == {"url", "expires_at"}
    link = urlparse(body["url"])
    assert link.path == "/activate-account"
    token = parse_qs(link.query)["token"][0]
    expires_at = datetime.fromisoformat(body["expires_at"])
    assert timedelta(hours=47) < expires_at - datetime.now(timezone.utc) <= timedelta(hours=48)
    with SessionLocal() as db:
        bind_system(db, "test: which links work")
        assert peek(db, token, "activation") == str(user_id)
        with pytest.raises(ValueError):
            peek(db, emailed, "activation")  # the new link replaces the one that was emailed
    # The person activates with it, once.
    activated = TestClient(app).post(
        "/api/v1/auth/activate-account", json={"token": token, "password": "A passphrase only I know 2026"}
    )
    assert activated.status_code == 200, activated.text
    again = TestClient(app).post(
        "/api/v1/auth/activate-account", json={"token": token, "password": "Another passphrase of mine 2026"}
    )
    assert again.status_code == 400
    with SessionLocal() as db:
        bind_system(db, "test: audit of the link")
        event = (
            db.query(AuditEvent)
            .filter(AuditEvent.action == "ACTIVATION_LINK_ISSUED", AuditEvent.entity_id == user_id)
            .one()
        )
        assert event.tenant_id == tenant_id and event.actor_ref == str(world["platform"][0])
        assert event.details == {"user_id": str(user_id), "source": "PLATFORM_ADMIN"}
        recorded = str(event.details) + str(event.reason) + str(event.new_values)
        assert token not in recorded and email not in recorded


def test_customer_administrators_and_business_users_are_refused(world):
    user_id, *_ = _invited(world)
    refused = _as(world, "customer_admin").post(URL.format(user_id))
    assert refused.status_code == 403 and refused.json()["detail"]["code"] == "PLATFORM_ADMIN_REQUIRED"
    assert _as(world, "active").post(URL.format(user_id)).status_code == 403
    assert TestClient(app).post(URL.format(user_id)).status_code == 401


def test_the_platform_administrator_must_have_passed_mfa(world):
    user_id, *_ = _invited(world)
    no_authenticator = _as(world, "platform_no_mfa").post(URL.format(user_id))
    assert no_authenticator.status_code == 403 and no_authenticator.json()["detail"]["code"] == "MFA_REQUIRED"
    code_still_due = _as(world, "platform", mfa_state="VERIFY").post(URL.format(user_id))
    assert code_still_due.status_code == 403 and code_still_due.json()["detail"]["code"] == "MFA_REQUIRED"
    with SessionLocal() as db:
        bind_system(db, "test: nothing was issued")
        assert (
            db.query(AuditEvent)
            .filter(AuditEvent.action == "ACTIVATION_LINK_ISSUED", AuditEvent.entity_id == user_id)
            .count()
            == 0
        )


def test_only_accounts_waiting_for_activation_get_a_link(world):
    platform = _as(world, "platform")
    active = platform.post(URL.format(world["active"][0]))
    assert active.status_code == 409 and active.json()["detail"]["code"] == "ACCOUNT_ALREADY_ACTIVE"
    offboarded = platform.post(URL.format(world["offboarded"][0]))
    assert offboarded.status_code == 409 and offboarded.json()["detail"]["code"] == "ACCOUNT_NOT_INVITED"
    unknown = platform.post(URL.format(uuid.uuid4()))
    assert unknown.status_code == 404
    with SessionLocal() as db:
        bind_system(db, "test: the active account is unchanged")
        assert db.get(AuthUser, world["active"][0]).status == "ACTIVE"
