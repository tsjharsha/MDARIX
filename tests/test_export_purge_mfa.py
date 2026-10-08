"""Taking or deleting all of an organization's data needs a current authenticator code, not only a session.

A full export (by the organization's administrator or by a platform administrator) and a purge are refused without a
current code from an account that has an authenticator, and the refusal is audited; an administrator whose role must
use MFA but has not set it up is sent to set it up. Local development without an MFA policy is not blocked.
"""

import time
import uuid
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from auth import totp
from auth.service import _hash
from backend.app.db.models.foundation import AuditEvent, AuthUser, Tenant, TenantMembership
from backend.app.db.session import SessionLocal
from backend.app.db.tenant_scope import bind_system
from backend.app.main import app
from tests.conftest import authenticated_client
from tests.test_tenant_data import _set_status, make_organization, use_local_storage

PASSWORD = "Export-Mfa-Password-2026!"


@pytest.fixture(autouse=True)
def storage_root(monkeypatch, tmp_path):
    return use_local_storage(monkeypatch, tmp_path)


def _account(role: str, tenant_id=None) -> str:
    email = f"export-mfa-{uuid.uuid4().hex[:10]}@example.invalid"
    with SessionLocal() as db:
        bind_system(db, "test: an administrator with an authenticator")
        tenant = (
            db.get(Tenant, tenant_id)
            if tenant_id
            else db.query(Tenant).filter(Tenant.tenant_key == "ACME_CARE_SYNTHETIC").first()
        )
        now = datetime.now(timezone.utc)
        user = AuthUser(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            username=email,
            display_name="Export MFA admin",
            company="Test",
            password_hash=_hash(PASSWORD),
            role=role,
            status="ACTIVE",
            email_verified=True,
            created_at=now,
            updated_at=now,
        )
        db.add(user)
        db.flush()
        db.add(
            TenantMembership(
                id=uuid.uuid4(),
                tenant_id=tenant.id,
                user_id=user.id,
                status="ACTIVE",
                is_default=True,
                created_at=now,
                updated_at=now,
            )
        )
        db.commit()
    return email


def _enrolled_client(role: str, tenant_id=None) -> tuple[TestClient, str]:
    """Signed in, with an authenticator set up through the real enrollment; returns the client and its secret."""
    client = TestClient(app)
    signed_in = client.post("/api/v1/auth/signin", json={"email": _account(role, tenant_id), "password": PASSWORD})
    assert signed_in.status_code == 200, signed_in.text
    secret = client.post("/api/v1/auth/mfa/enroll").json()["secret"]
    done = client.post("/api/v1/auth/mfa/verify-enrollment", json={"code": totp.current_code(secret)})
    assert done.status_code == 200, done.text
    return client, secret


def _next_code(secret: str) -> str:
    # The next 30-second step: inside the drift window and newer than the code used to enroll.
    return totp.code_at(secret, int(time.time() // 30) + 1)


def _refusals(tenant_id, action: str) -> int:
    with SessionLocal() as db:
        bind_system(db, "test: refusal audit")
        return db.query(AuditEvent).filter(AuditEvent.tenant_id == tenant_id, AuditEvent.action == action).count()


def test_a_platform_export_needs_the_current_code():
    admin, secret = _enrolled_client("PLATFORM_ADMIN")
    organization = make_organization(admin)
    url = f"/api/v1/platform-admin/tenants/{organization['tenant_id']}/exports"
    body = {"reason": "Hand the data back to the customer"}

    missing = admin.post(url, json=body)
    assert missing.status_code == 403 and missing.json()["detail"]["code"] == "AUTHENTICATOR_CODE_REQUIRED"
    wrong = admin.post(url, json={**body, "mfa_code": "000000"})
    assert wrong.status_code == 403 and wrong.json()["detail"]["code"] == "AUTHENTICATOR_CODE_REQUIRED"
    assert _refusals(organization["tenant_id"], "TENANT_EXPORT_REFUSED_MFA") == 2

    queued = admin.post(url, json={**body, "mfa_code": _next_code(secret)})
    assert queued.status_code == 202, queued.text


def test_a_customer_administrators_own_export_needs_the_current_code():
    platform = authenticated_client()
    organization = make_organization(platform)
    admin, secret = _enrolled_client("CUSTOMER_ADMIN", organization["tenant_id"])
    body = {"reason": "Annual records retention copy"}
    refused = admin.post("/api/v1/admin/exports", json=body)
    assert refused.status_code == 403 and refused.json()["detail"]["code"] == "AUTHENTICATOR_CODE_REQUIRED"
    queued = admin.post("/api/v1/admin/exports", json={**body, "mfa_code": _next_code(secret)})
    assert queued.status_code == 202, queued.text


def test_a_purge_needs_the_password_and_then_the_current_code():
    admin, secret = _enrolled_client("PLATFORM_ADMIN")
    organization = make_organization(admin)
    _set_status(organization["tenant_id"], "SUSPENDED")
    url = f"/api/v1/platform-admin/tenants/{organization['tenant_id']}/purge"
    body = {
        "reason": "Pilot ended; customer asked us to delete everything",
        "password": PASSWORD,
        "confirm_tenant_key": organization["tenant_key"],
        "export_waiver_reason": "Customer declined the hand-back in writing",
    }

    refused = admin.post(url, json=body)
    assert refused.status_code == 403 and refused.json()["detail"]["code"] == "AUTHENTICATOR_CODE_REQUIRED"
    assert _refusals(organization["tenant_id"], "TENANT_PURGE_REFUSED_MFA") == 1
    with SessionLocal() as db:
        bind_system(db, "test: nothing deleted")
        assert db.get(Tenant, organization["tenant_id"]).status == "SUSPENDED"

    # A wrong password is still refused first, whatever the code.
    wrong_password = admin.post(url, json={**body, "password": "not the password", "mfa_code": _next_code(secret)})
    assert wrong_password.status_code == 403
    assert wrong_password.json()["detail"]["code"] == "INVALID_REAUTHENTICATION"

    purged = admin.post(url, json={**body, "mfa_code": _next_code(secret)})
    assert purged.status_code == 200, purged.text


def test_an_administrator_who_must_use_mfa_but_has_none_is_sent_to_set_it_up(monkeypatch):
    platform = authenticated_client()  # the shared test administrator has no authenticator
    organization = make_organization(platform)
    monkeypatch.setenv("MDARIX_REQUIRE_MFA_ROLES", "PLATFORM_ADMIN,CUSTOMER_ADMIN")
    refused = platform.post(
        f"/api/v1/platform-admin/tenants/{organization['tenant_id']}/exports", json={"reason": "Hand the data back"}
    )
    assert refused.status_code == 403 and refused.json()["detail"]["code"] == "MFA_ENROLLMENT_REQUIRED"


def test_without_an_mfa_policy_an_account_without_an_authenticator_is_not_blocked(monkeypatch):
    monkeypatch.setenv("MDARIX_REQUIRE_MFA_ROLES", "")
    platform = authenticated_client()
    organization = make_organization(platform)
    queued = platform.post(
        f"/api/v1/platform-admin/tenants/{organization['tenant_id']}/exports", json={"reason": "Hand the data back"}
    )
    assert queued.status_code == 202, queued.text
