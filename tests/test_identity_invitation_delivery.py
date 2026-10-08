"""An invitation whose email cannot be delivered still creates the account: the failure is recorded and answered
(201, ``delivery: "FAILED"``), and MDARIX support can issue an activation link instead."""

import uuid

import pytest

from auth.durable import peek
from auth.emailer import EmailDeliveryError
from backend.app.access import common, identity
from backend.app.db.models.foundation import AuditEvent, AuthUser, Tenant, TenantMembership
from backend.app.db.session import SessionLocal
from backend.app.db.tenant_scope import bind_system
from tests.test_customer_admin_account_security import _client_for, _tenant, _user


@pytest.fixture(scope="module")
def admin_client():
    with SessionLocal() as db:
        bind_system(db, "test: an organization and its administrator")
        tenant = _tenant(db, "MAIL")
        admin = _user(db, tenant, "CUSTOMER_ADMIN", "mail-admin")
        db.commit()
        client = _client_for(db, admin)
        return client, tenant.id


def _smtp_down(monkeypatch):
    def refuse(*_args, **_kwargs):
        raise EmailDeliveryError("The email provider refused the message or could not be reached.")

    monkeypatch.setattr(identity, "send_activation_email", refuse)


def _invite(client):
    email = f"mail-{uuid.uuid4().hex[:8]}@synthetic.invalid"
    response = client.post(
        "/api/v1/admin/identity/users",
        json={"email": email, "display_name": "Invited Person", "company": "Synthetic", "role": "Investigator"},
    )
    return response, email


def _account(tenant_id, email):
    with SessionLocal() as db:
        bind_system(db, "test: the invited account")
        user = db.query(AuthUser).filter(AuthUser.tenant_id == tenant_id, AuthUser.username == email).one_or_none()
        if user is not None:
            db.expunge(user)
        return user


def _last_audit(action, user_id):
    with SessionLocal() as db:
        bind_system(db, "test: audit")
        return (
            db.query(AuditEvent)
            .filter(AuditEvent.action == action, AuditEvent.entity_id == user_id)
            .order_by(AuditEvent.created_at.desc())
            .first()
        )


def test_a_delivery_failure_keeps_the_account_and_says_what_to_do(admin_client, monkeypatch):
    client, tenant_id = admin_client
    _smtp_down(monkeypatch)
    response, email = _invite(client)
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["delivery"] == body["email_delivery"] == "FAILED"
    assert body["invitation_status"] == "NOT_SENT" and "MDARIX support" in body["message"]
    assert "activation link" in body["message"]
    user = _account(tenant_id, email)
    assert user is not None and user.status == "INVITED" and body["id"] == str(user.id)
    with SessionLocal() as db:
        bind_system(db, "test: membership and link")
        membership = db.query(TenantMembership).filter(TenantMembership.user_id == user.id).one()
        assert membership.status == "INVITED"
        # Local development keeps showing the link's token, so the flow can be finished without email.
        assert body["development_token"] and peek(db, body["development_token"], "activation") == str(user.id)
    audit = _last_audit("USER_INVITATION_SENT", user.id)
    assert audit is not None and audit.details["email_delivery"] == "FAILED"


def test_outside_development_no_token_is_returned(admin_client, monkeypatch):
    client, _tenant_id = admin_client
    _smtp_down(monkeypatch)
    monkeypatch.setattr(common, "is_development", lambda: False)
    response, _email = _invite(client)
    assert response.status_code == 201 and response.json()["development_token"] is None


def test_a_delivered_invitation_answers_as_before(admin_client, monkeypatch):
    client, tenant_id = admin_client
    monkeypatch.setattr(identity, "send_activation_email", lambda *_args, **_kwargs: "SENT")
    response, email = _invite(client)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["email_delivery"] == "SENT" and body["invitation_status"] == "SENT"
    assert "delivery" not in body and body["development_token"] is None
    assert _account(tenant_id, email).status == "INVITED"


def test_a_reinvitation_that_cannot_be_emailed_still_reinvites(admin_client, monkeypatch):
    client, tenant_id = admin_client
    with SessionLocal() as db:
        bind_system(db, "test: an offboarded person")
        person = _user(db, db.get(Tenant, tenant_id), "Investigator", "mail-offboarded")
        person.status = "OFFBOARDED"
        db.commit()
        person_id = person.id
    _smtp_down(monkeypatch)
    response = client.post(f"/api/v1/admin/identity/users/{person_id}/reactivate")
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["delivery"] == "FAILED" and body["status"] == "INVITED" and "MDARIX support" in body["message"]
    with SessionLocal() as db:
        bind_system(db, "test: the person is invited again")
        assert db.get(AuthUser, person_id).status == "INVITED"
    audit = _last_audit("USER_REACTIVATED", person_id)
    assert audit is not None and audit.details["email_delivery"] == "FAILED"
