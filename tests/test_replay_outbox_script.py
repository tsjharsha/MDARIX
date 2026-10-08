"""scripts/replay_outbox.py: re-queues only dead letters, with fresh retries and an audit record."""

import importlib.util
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest
from sqlalchemy import text

from backend.app.db.models.foundation import AuditEvent
from backend.app.db.models.stage2 import OutboxEvent
from backend.app.db.session import SessionLocal
from backend.app.db.tenant_scope import bind_system

_SPEC = importlib.util.spec_from_file_location(
    "replay_outbox", Path(__file__).resolve().parents[1] / "scripts" / "replay_outbox.py"
)
replay_outbox = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(replay_outbox)


@pytest.fixture
def db():
    session = SessionLocal()
    bind_system(session, "test")
    yield session
    session.rollback()
    session.close()


def _event(db, *, dead: bool) -> OutboxEvent:
    tenant = db.execute(text("select id from tenants order by created_at limit 1")).scalar_one()
    now = datetime.now(timezone.utc)
    row = OutboxEvent(
        tenant_id=tenant,
        event_name="REPLAY_SCRIPT_TEST",
        aggregate_type="Test",
        payload={"secret": "never in the audit"},
        occurred_at=now,
        attempts=12,
        dead_lettered_at=now if dead else None,
        last_error="delivery failed",
    )
    db.add(row)
    db.commit()
    return row


def _cleanup(db, row_id) -> None:
    bind_system(db, "test cleanup")
    db.query(OutboxEvent).filter(OutboxEvent.id == row_id).delete()
    db.commit()


def test_a_dead_letter_gets_fresh_retries_and_an_audit_record(db):
    row = _event(db, dead=True)
    try:
        replayed = replay_outbox.replay(db, row.id, "SMTP credentials fixed")
        assert replayed.dead_lettered_at is None and replayed.attempts == 0 and replayed.last_error is None
        bind_system(db, "test")
        audit = (
            db.query(AuditEvent)
            .filter(AuditEvent.entity_id == row.id, AuditEvent.action == "OUTBOX_EVENTS_RETRIED")
            .one()
        )
        assert audit.reason == "SMTP credentials fixed"
        assert audit.details["event_name"] == "REPLAY_SCRIPT_TEST" and "never in the audit" not in str(audit.details)
    finally:
        _cleanup(db, row.id)


def test_an_event_that_is_not_dead_lettered_is_refused(db):
    row = _event(db, dead=False)
    try:
        with pytest.raises(ValueError, match="OUTBOX_EVENT_NOT_DEAD_LETTERED"):
            replay_outbox.replay(db, row.id, "should not replay")
    finally:
        db.rollback()
        _cleanup(db, row.id)


def test_an_unknown_event_and_a_short_reason_are_refused(db):
    with pytest.raises(ValueError, match="OUTBOX_EVENT_NOT_FOUND"):
        replay_outbox.replay(db, uuid.uuid4(), "reason long enough")
    with pytest.raises(SystemExit):
        replay_outbox.main([str(uuid.uuid4()), "--reason", "short"])
