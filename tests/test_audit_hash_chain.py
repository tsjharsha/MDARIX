"""The database chains every audit event per organization and detects any change (migration md18)."""

import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import text

from backend.app.audit_chain import verify_all, verify_tenant_chain
from backend.app.db.models.foundation import AuditEvent, Tenant
from backend.app.db.session import SessionLocal
from backend.app.db.tenant_scope import bind_system
from backend.app.enterprise_audit import make_audit_event
from tests.conftest import authenticated_client


@pytest.fixture
def db():
    session = SessionLocal()
    bind_system(session, "test")
    yield session
    session.rollback()
    session.close()


def _tenant(db) -> uuid.UUID:
    row = db.query(Tenant).filter(Tenant.tenant_key == "ACME_CARE_SYNTHETIC").first() or db.query(Tenant).first()
    return row.id


def _add(db, tenant_id, action, **extra):
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
    db.flush()
    db.refresh(event)
    return event


def test_every_new_event_is_linked_to_the_one_before_it(db):
    tenant_id = _tenant(db)
    first = _add(db, tenant_id, "CHAIN_TEST_ONE")
    second = make_audit_event(tenant_id=tenant_id, actor_ref="test", action="CHAIN_TEST_TWO", entity_type="Test")
    db.add(second)
    db.flush()
    db.refresh(second)
    assert second.chain_seq == first.chain_seq + 1
    assert second.previous_hash == first.event_hash and len(second.event_hash) == 64
    assert verify_tenant_chain(db, tenant_id)["valid"] is True


def test_hashes_supplied_by_the_application_are_replaced(db):
    tenant_id = _tenant(db)
    before = _add(db, tenant_id, "CHAIN_TEST_BEFORE")
    event = _add(db, tenant_id, "CHAIN_TEST_FORGED", previous_hash="0" * 64, event_hash="f" * 64, chain_seq=1)
    assert event.event_hash != "f" * 64 and event.previous_hash == before.event_hash
    assert event.chain_seq == before.chain_seq + 1


def test_a_changed_event_breaks_the_chain(db):
    tenant_id = _tenant(db)
    event = _add(db, tenant_id, "CHAIN_TEST_TAMPER")
    # Simulate someone with database-owner access editing history (the immutability trigger normally refuses).
    db.execute(text("ALTER TABLE audit_events DISABLE TRIGGER audit_events_immutable"))
    db.execute(text("UPDATE audit_events SET reason = 'edited later' WHERE id = :id"), {"id": event.id})
    result = verify_tenant_chain(db, tenant_id)
    assert result["valid"] is False and result["first_broken_seq"] == event.chain_seq


def test_events_cannot_be_changed_or_deleted(db):
    event = _add(db, _tenant(db), "CHAIN_TEST_IMMUTABLE")
    with pytest.raises(Exception, match="immutable"):
        db.execute(text("UPDATE audit_events SET reason = 'x' WHERE id = :id"), {"id": event.id})


def test_a_rewritten_history_is_caught_by_the_last_verified_anchor(db):
    tenant_id = _tenant(db)
    _add(db, tenant_id, "CHAIN_TEST_ANCHOR")
    state: dict = {}
    first = verify_all(db, state)
    assert first["broken"] == [] and str(tenant_id) in state["anchors"]
    anchor = state["anchors"][str(tenant_id)]
    # Someone rewrites the anchored event and re-hashes it: the stored hash no longer matches the anchor.
    db.execute(text("ALTER TABLE audit_events DISABLE TRIGGER audit_events_immutable"))
    db.execute(
        text("UPDATE audit_events SET event_hash = :fake WHERE tenant_id = :tenant AND chain_seq = :seq"),
        {"fake": "a" * 64, "tenant": tenant_id, "seq": anchor["seq"]},
    )
    second = verify_all(db, state)
    assert {"tenant_id": str(tenant_id), "reason": "ANCHOR_CHANGED", "seq": anchor["seq"]} in second["broken"]


def test_an_administrator_can_verify_the_trail(db):
    _add(db, _tenant(db), "CHAIN_TEST_VERIFY")  # the organization's trail is never empty, even on a fresh database
    db.commit()
    response = authenticated_client().get("/api/v1/admin/audit-chain")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["valid"] is True and body["checked"] == body["last_seq"] and len(body["last_hash"]) == 64


def test_exports_carry_the_chain_and_its_verification(db):
    import csv
    import io
    import json
    import zipfile

    _add(db, _tenant(db), "CHAIN_TEST_EXPORT")
    db.commit()
    client = authenticated_client()
    exported = client.get("/api/v1/admin/audit-history/export?output_format=CSV")
    assert exported.status_code == 200
    rows = list(csv.DictReader(io.StringIO(exported.text)))
    assert rows and {"chain_seq", "previous_hash", "event_hash"} <= set(rows[0])
    sequence = [int(row["chain_seq"]) for row in rows]
    assert sequence == sorted(sequence) and sequence[0] == 1  # the whole trail, from its first event

    package = client.get("/api/v1/admin/audit-history/evidence-package")
    manifest = json.loads(zipfile.ZipFile(io.BytesIO(package.content)).read("manifest.json"))
    assert manifest["complete"] is True and manifest["audit_chain"]["valid"] is True
    assert manifest["event_count"] == len(rows)
