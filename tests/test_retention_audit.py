"""Audit retention and audit payloads: the database dates every event (migration md23), the archive job and the
retention status agree on which events have expired (scripts/archive_expired_audit_events.py,
GET /api/v1/admin/retention-status), and audit rows name people by id."""

import gzip
import json
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from sqlalchemy import text

from backend.app.db.models.foundation import AuditEvent
from backend.app.db.session import SessionLocal
from backend.app.db.tenant_scope import bind_system
from scripts import archive_expired_audit_events as archive_script
from tests.test_person_export import _client_in
from tests.conftest import authenticated_client
from tests.test_tenant_data import make_organization, use_local_storage


@pytest.fixture(autouse=True)
def storage_root(monkeypatch, tmp_path):
    return use_local_storage(monkeypatch, tmp_path)


@pytest.fixture
def platform():
    return authenticated_client()


@pytest.fixture
def organization(platform):
    return make_organization(platform)


def _insert(tenant_id, action: str, **extra) -> uuid.UUID:
    db = SessionLocal()
    bind_system(db, "test")
    try:
        event = AuditEvent(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            actor_ref="test",
            action=action,
            entity_type="Test",
            created_at=datetime.now(timezone.utc),
            **extra,
        )
        db.add(event)
        db.commit()
        return event.id
    finally:
        db.close()


def test_an_event_stored_without_a_retention_date_gets_seven_years_from_the_database(organization):
    event_id = _insert(organization["tenant_id"], "RETENTION_DEFAULT_PROBE")  # retention_until left empty
    db = SessionLocal()
    bind_system(db, "test")
    try:
        retention_until, created_at, expected, now_plus = db.execute(
            text(
                "SELECT retention_until, created_at, created_at + interval '7 years', now() + interval '7 years' "
                "FROM audit_events WHERE id = :id"
            ),
            {"id": event_id},
        ).one()
    finally:
        db.close()
    assert retention_until is not None and retention_until == expected
    # Seven calendar years from the event, which is now.
    assert abs(retention_until - now_plus) < timedelta(minutes=5)
    assert 365 * 7 <= (retention_until - created_at).days <= 365 * 7 + 2


def test_the_archive_job_and_the_retention_status_agree_on_what_has_expired(organization, tmp_path):
    tenant_id = organization["tenant_id"]
    now = datetime.now(timezone.utc)
    expired = _insert(tenant_id, "RETENTION_EXPIRED_PROBE", retention_until=now - timedelta(days=1))
    _insert(tenant_id, "RETENTION_CURRENT_PROBE", retention_until=now + timedelta(days=10))
    admin, _ = _client_in(tenant_id, "CUSTOMER_ADMIN")

    status = admin.get("/api/v1/admin/retention-status")
    assert status.status_code == 200, status.text
    body = status.json()
    assert body["expired"] == 1 and body["expiring_within_30_days"] == 1
    assert body["status"] == "ATTENTION_REQUIRED" and body["archival_required"] is True

    assert archive_script.main(["--archive-dir", str(tmp_path), "--tenant", str(tenant_id)]) == 0
    [archive] = list(tmp_path.glob(f"audit-{tenant_id}-*.jsonl.gz"))
    with gzip.open(archive, "rt", encoding="utf-8") as stream:
        archived = [json.loads(line) for line in stream]
    # Exactly the events the status counts as expired, and the archive never deletes them.
    assert [row["id"] for row in archived] == [str(expired)]
    db = SessionLocal()
    bind_system(db, "test")
    try:
        assert db.get(AuditEvent, expired) is not None
        assert len(archive_script.expired_events(db, datetime.now(timezone.utc), [tenant_id])[str(tenant_id)]) == 1
    finally:
        db.close()


def test_audit_rows_name_a_notification_recipient_by_id_not_by_address(organization):
    """Audit rows outlive an erasure and cannot be changed, so they must not hold the address or the name."""
    tenant_id = organization["tenant_id"]
    admin, _ = _client_in(tenant_id, "CUSTOMER_ADMIN")
    preferences = admin.put(
        "/api/v1/admin/notifications/preferences", json={"reason": "Renewal reminders for the quality lead"}
    )
    assert preferences.status_code == 200, preferences.text
    email = f"quality-lead-{uuid.uuid4().hex[:8]}@example.invalid"
    added = admin.post(
        "/api/v1/admin/notifications/recipients",
        json={
            "recipient_type": "BUSINESS_CONTACT",
            "email": email,
            "name": "Quinn Quality",
            "reason": "Quality lead wants the renewal reminders",
        },
    )
    assert added.status_code == 200, added.text
    db = SessionLocal()
    bind_system(db, "test")
    try:
        [event] = (
            db.query(AuditEvent)
            .filter(AuditEvent.tenant_id == tenant_id, AuditEvent.action == "CUSTOMER_NOTIFICATION_RECIPIENT_ADDED")
            .all()
        )
        payload = json.dumps([event.details, event.old_values, event.new_values])
    finally:
        db.close()
    assert email not in payload and "Quinn" not in payload
    assert event.new_values["contact_id"] == added.json()["contact_id"]
