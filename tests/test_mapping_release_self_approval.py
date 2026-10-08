"""Mapping release in an organization with one administrator: self-approval with a typed reason, audited; the
two-person rule applies again as soon as a second administrator is active."""

import secrets
import uuid
from datetime import datetime, timezone

from fastapi.testclient import TestClient

from auth.durable import persist_session
from auth.service import _hash
from backend.app.db.models.foundation import AuditEvent, AuthUser, TenantMembership
from backend.app.db.session import SessionLocal
from backend.app.db.tenant_scope import bind_system
from backend.app.main import app
from tests.conftest import authenticated_client

RULES = {
    "complaint_number": {"target_field": "Complaint.complaint_id", "transform": "trim"},
    "device_code": {"target_field": "Complaint.product_id", "transform": "trim"},
    "narrative": {"target_field": "Complaint.description", "transform": "trim"},
}


def _organization() -> str:
    code = f"MRS{uuid.uuid4().hex[:6].upper()}"
    created = authenticated_client().post(
        "/api/v1/platform-admin/customers",
        json={"company_name": f"Release Test {code}", "tenant_code": code, "plan_code": "STARTER"},
    )
    assert created.status_code == 200, created.text
    return created.json()["id"]


def _admin(tenant_id: str) -> tuple[TestClient, uuid.UUID]:
    db = SessionLocal()
    try:
        bind_system(db, "test: add a customer administrator")
        now = datetime.now(timezone.utc)
        user = AuthUser(
            id=uuid.uuid4(),
            tenant_id=uuid.UUID(tenant_id),
            username=f"release-admin-{uuid.uuid4().hex[:8]}@example.invalid",
            display_name="Release Admin",
            company="Test",
            password_hash=_hash("Release test 2026!"),
            role="CUSTOMER_ADMIN",
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
                tenant_id=user.tenant_id,
                user_id=user.id,
                status="ACTIVE",
                is_default=True,
                created_at=now,
                updated_at=now,
            )
        )
        db.commit()
        token = secrets.token_urlsafe(32)
        persist_session(db, token, user.id, user.tenant_id)
        user_id = user.id
    finally:
        db.close()
    client = TestClient(app)
    client.cookies.set("mdarix_session", token)
    return client, user_id


def _mapping(client: TestClient) -> str:
    made = client.post(
        "/api/v1/admin/configuration/mappings",
        json={
            "code": f"SELF-{uuid.uuid4().hex[:6]}",
            "source_system": "TRACKWISE",
            "target_entity": "Complaint",
            "mapping_rules": RULES,
        },
    )
    assert made.status_code == 200, made.text
    return made.json().get("mapping_id") or made.json()["id"]


def _action(client: TestClient, mapping_id: str, action: str, reason: str = "Reviewed every field of the sheet"):
    return client.post(
        f"/api/v1/admin/configuration/mappings/{mapping_id}/release-action", json={"action": action, "reason": reason}
    )


def _audit_actions(mapping_id: str) -> list[str]:
    db = SessionLocal()
    try:
        bind_system(db, "test: read the release audit")
        return [
            row.action
            for row in db.query(AuditEvent)
            .filter(AuditEvent.entity_type == "MappingConfiguration", AuditEvent.entity_id == uuid.UUID(mapping_id))
            .order_by(AuditEvent.created_at)
        ]
    finally:
        db.close()


def test_the_only_administrator_approves_their_own_release_with_a_reason():
    tenant_id = _organization()
    admin, admin_id = _admin(tenant_id)
    mapping_id = _mapping(admin)
    assert _action(admin, mapping_id, "REQUEST_APPROVAL").status_code == 200
    # A reason is required, of at least 10 characters.
    assert _action(admin, mapping_id, "APPROVE", reason="ok").status_code == 422
    approved = _action(admin, mapping_id, "APPROVE")
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == "APPROVED" and approved.json()["self_approved"] is True
    assert _audit_actions(mapping_id)[-1] == "MAPPING_RELEASE_SELF_APPROVED"
    db = SessionLocal()
    try:
        bind_system(db, "test")
        event = db.get(AuditEvent, uuid.UUID(approved.json()["audit_event_id"]))
        assert event.actor_ref == str(admin_id)
        assert event.details["reason"] == "Reviewed every field of the sheet" and event.details["self_approved"]
    finally:
        db.close()
    assert _action(admin, mapping_id, "PROMOTE").status_code == 200


def test_with_a_second_administrator_the_two_person_rule_applies_again():
    tenant_id = _organization()
    first, _ = _admin(tenant_id)
    second, _ = _admin(tenant_id)
    mapping_id = _mapping(first)
    assert _action(first, mapping_id, "REQUEST_APPROVAL").status_code == 200
    refused = _action(first, mapping_id, "APPROVE")
    assert refused.status_code == 403 and refused.json()["detail"]["code"] == "SOD_DENIED"
    approved = _action(second, mapping_id, "APPROVE")
    assert approved.status_code == 200 and approved.json()["self_approved"] is False
    assert _audit_actions(mapping_id)[-1] == "MAPPING_RELEASE_APPROVE"
