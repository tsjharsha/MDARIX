"""One person's data export (GET /api/v1/admin/people/{id}/export, docs/runbooks/DATA_REQUESTS.md section 1)."""

import secrets
import uuid
from datetime import datetime, timezone

import pytest

from fastapi.testclient import TestClient

from auth.durable import persist_session
from auth.service import _hash
from backend.app.db.models.foundation import AuditEvent, AuthUser, TenantMembership
from backend.app.db.session import SessionLocal
from backend.app.db.tenant_scope import bind_system
from backend.app.main import app
from tests.conftest import authenticated_client
from tests.test_tenant_data import _count, make_organization, use_local_storage


@pytest.fixture(autouse=True)
def storage_root(monkeypatch, tmp_path):
    return use_local_storage(monkeypatch, tmp_path)


@pytest.fixture
def platform():
    return authenticated_client()


@pytest.fixture
def organization(platform):
    return make_organization(platform)


def _client_in(tenant_id, role: str) -> tuple[TestClient, uuid.UUID]:
    """A signed-in user with ``role`` in the given organization."""
    now = datetime.now(timezone.utc)
    db = SessionLocal()
    bind_system(db, "test")
    try:
        user = AuthUser(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            username=f"{role.lower()}-{uuid.uuid4().hex[:8]}@example.invalid",
            display_name=f"{role} user",
            company="Purge Test",
            password_hash=_hash("Export test password 2026!"),
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
                tenant_id=tenant_id,
                user_id=user.id,
                status="ACTIVE",
                is_default=True,
                created_at=now,
                updated_at=now,
            )
        )
        db.commit()
        token = secrets.token_urlsafe(32)
        persist_session(db, token, user.id, tenant_id)
        user_id = user.id
    finally:
        db.close()
    client = TestClient(app)
    client.cookies.set("mdarix_session", token)
    return client, user_id


def test_an_administrator_exports_everything_held_about_one_person_without_credentials(organization):
    tenant_id, person_id = organization["tenant_id"], organization["user_id"]
    admin, admin_id = _client_in(tenant_id, "CUSTOMER_ADMIN")
    response = admin.get(f"/api/v1/admin/people/{person_id}/export")
    assert response.status_code == 200, response.text
    assert response.headers["cache-control"] == "no-store"
    assert f"mdarix-person-{str(person_id)[:8]}.json" in response.headers["content-disposition"]
    document = response.json()
    assert document["account"]["id"] == str(person_id) and document["account"]["display_name"] == "Pat Person"
    assert document["account"]["email"].startswith("person-")
    # The audit events the person caused (the fixture's TEST_EVENT) are included, with the totals.
    assert [event["action"] for event in document["audit_events"]] == ["TEST_EVENT"]
    assert document["audit_events_total"] == 1 and document["audit_events_truncated"] is False
    assert [membership["status"] for membership in document["memberships"]] == ["ACTIVE"]
    # Credentials and authenticator material are never part of it.
    text = response.text
    for secret in ("password_hash", "mfa_secret", "recovery", "session_hash"):
        assert secret not in text
    # The export is audited against the person, by id.
    db = SessionLocal()
    bind_system(db, "test")
    try:
        [event] = (
            db.query(AuditEvent)
            .filter(AuditEvent.tenant_id == tenant_id, AuditEvent.action == "PERSONAL_DATA_EXPORTED")
            .all()
        )
        assert event.entity_id == person_id and event.actor_ref == str(admin_id)
        assert "Pat" not in str(event.details) and "@" not in str(event.details)
    finally:
        db.close()


def test_a_person_export_stays_inside_the_administrators_organization(platform, organization):
    tenant_id, person_id = organization["tenant_id"], organization["user_id"]
    # An administrator of another organization gets "not found", exactly as for an id that does not exist.
    other = platform.post(
        "/api/v1/platform-admin/customers",
        json={
            "company_name": f"Other {uuid.uuid4().hex[:6]}",
            "tenant_code": f"OTH{uuid.uuid4().hex[:6].upper()}",
            "plan_code": "STARTER",
        },
    )
    assert other.status_code == 200, other.text
    outsider, _ = _client_in(uuid.UUID(other.json()["id"]), "CUSTOMER_ADMIN")
    assert outsider.get(f"/api/v1/admin/people/{person_id}/export").status_code == 404
    assert outsider.get(f"/api/v1/admin/people/{uuid.uuid4()}/export").status_code == 404
    # Inside the organization, only administrators may export a person.
    investigator, _ = _client_in(tenant_id, "Investigator")
    assert investigator.get(f"/api/v1/admin/people/{person_id}/export").status_code in (401, 403)
    assert _count(AuditEvent, tenant_id=tenant_id, action="PERSONAL_DATA_EXPORTED") == 0
