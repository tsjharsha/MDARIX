"""The outbox worker never hands a handler an event whose payload names another organization than the event row
(RSK-026): such an event is dead-lettered at once with PAYLOAD_TENANT_MISMATCH, without retries, and the log and the
alert name the event and both organizations, never the payload."""

import logging
import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import text

from backend.app.db.models.stage2 import OutboxEvent
from backend.app.db.session import SessionLocal
from backend.app.db.tenant_scope import bind_system
from outbox.worker import OutboxWorker

PAYLOAD_TENANT_MISMATCH = "PAYLOAD_TENANT_MISMATCH"
SECRET = "patient-name-that-must-never-be-logged"


@pytest.fixture
def events():
    tag = uuid.uuid4().hex[:8]
    with SessionLocal() as db:
        bind_system(db, "test: two organizations' events")
        own, other = db.execute(text("select id from tenants order by created_at limit 2")).scalars().all()
        rows = {
            "own": OutboxEvent(tenant_id=own, payload={"tenant_id": str(own), "note": SECRET}),
            "other": OutboxEvent(tenant_id=own, payload={"tenant_id": str(other), "note": SECRET}),
            "upper": OutboxEvent(tenant_id=own, payload={"tenant_id": str(own).upper()}),
            "none": OutboxEvent(tenant_id=own, payload={"subscription_id": str(uuid.uuid4())}),
        }
        for key, row in rows.items():
            row.id = uuid.uuid4()
            row.event_name = f"SCOPE_{key.upper()}_{tag}"
            row.aggregate_type = "Test"
            row.occurred_at = datetime(2000, 1, 1, tzinfo=timezone.utc)
        db.add_all(rows.values())
        db.commit()
        ids = {key: row.id for key, row in rows.items()}
    yield ids, own, other
    with SessionLocal() as db:
        bind_system(db, "test cleanup")
        db.query(OutboxEvent).filter(OutboxEvent.id.in_(list(ids.values()))).delete(synchronize_session=False)
        db.commit()


def _row(event_id):
    with SessionLocal() as db:
        bind_system(db, "test: read outbox row")
        return db.get(OutboxEvent, event_id)


@pytest.mark.db
def test_an_event_whose_payload_names_another_organization_is_dead_lettered_and_never_handled(events, caplog):
    ids, own, other = events
    handled, alerts = [], []
    worker = OutboxWorker(lambda name, payload: handled.append(name), max_attempts=12, alert=alerts.append)
    stats = {"published": 0, "failed": 0, "dead_lettered": 0, "stale_recovered": 0}
    caplog.set_level(logging.INFO, logger="outbox.worker")
    db = SessionLocal()
    try:
        bind_system(db, "test: deliver")
        for key in ("own", "other", "upper", "none"):
            worker._deliver_one(db, ids[key], stats)
    finally:
        db.close()

    assert not any("_OTHER_" in name for name in handled)
    assert len(handled) == 3  # same organization (any case) and a payload without one are delivered as before
    for key in ("own", "upper", "none"):
        assert _row(ids[key]).published_at is not None
    refused = _row(ids["other"])
    assert refused.published_at is None and refused.dead_lettered_at is not None  # at once, no retry
    assert refused.last_error == PAYLOAD_TENANT_MISMATCH and refused.attempts == 1 and refused.next_attempt_at is None
    assert stats["dead_lettered"] == 1 and stats["published"] == 3
    assert [alert["event_id"] for alert in alerts] == [str(ids["other"])]
    assert alerts[0]["error"] == PAYLOAD_TENANT_MISMATCH
    logged = caplog.text
    assert str(ids["other"]) in logged and str(own) in logged and str(other) in logged
    assert SECRET not in logged and SECRET not in str(alerts)


@pytest.mark.db
def test_a_refused_event_stays_out_of_every_later_cycle(events):
    ids, _own, _other = events
    worker = OutboxWorker(lambda *_: None)
    stats = {"published": 0, "failed": 0, "dead_lettered": 0, "stale_recovered": 0}
    db = SessionLocal()
    try:
        bind_system(db, "test: deliver twice")
        worker._deliver_one(db, ids["other"], stats)
        worker._deliver_one(db, ids["other"], stats)  # no longer due: skipped
    finally:
        db.close()
    assert stats["dead_lettered"] == 1 and _row(ids["other"]).attempts == 1
