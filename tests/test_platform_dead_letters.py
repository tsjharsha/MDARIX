"""Work that gave up after its retries: platform administrators retry or discard it, with a reason, on the record."""

import uuid
from datetime import datetime, timezone

import pytest

from backend.app.db.models.foundation import AuditEvent, Tenant
from backend.app.db.models.stage2 import OutboxEvent
from backend.app.db.session import SessionLocal
from backend.app.db.tenant_scope import bind_system
from tests.conftest import authenticated_client
from tests.test_business_permissions import _client_with_role

SECRET = "CONFIDENTIAL-COMPLAINT-PAYLOAD"
BASE = "/api/v1/platform-admin/console/dead-letters"
REASON = "Test leftovers from the worker test, not real work"


@pytest.fixture(scope="module")
def platform():
    return authenticated_client()


@pytest.fixture
def gave_up():
    """Three items that gave up: two in one tenant, one in another."""
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        bind_system(db, "test: dead-lettered items")
        tenants = [row[0] for row in db.query(Tenant.id).order_by(Tenant.created_at).limit(2)]
        rows = [
            OutboxEvent(
                id=uuid.uuid4(),
                tenant_id=tenant,
                event_name="TEST_GAVE_UP",
                aggregate_type="Test",
                payload={"narrative": SECRET},
                occurred_at=now,
                attempts=5,
                last_error="RuntimeError: delivery failed",
                dead_lettered_at=now,
            )
            for tenant in (tenants[0], tenants[0], tenants[1])
        ]
        db.add_all(rows)
        db.commit()
        ids = [str(row.id) for row in rows]
        tenant_ids = [tenants[0], tenants[0], tenants[1]]
    yield ids, tenant_ids
    with SessionLocal() as db:
        bind_system(db, "test cleanup")
        db.query(OutboxEvent).filter(OutboxEvent.id.in_([uuid.UUID(i) for i in ids])).delete(synchronize_session=False)
        db.commit()


def _audit(action, tenant_id):
    with SessionLocal() as db:
        bind_system(db, "test: read audit")
        return (
            db.query(AuditEvent)
            .filter(AuditEvent.action == action, AuditEvent.tenant_id == tenant_id)
            .order_by(AuditEvent.created_at.desc())
            .first()
        )


def _row(item_id):
    with SessionLocal() as db:
        bind_system(db, "test: read outbox")
        return db.get(OutboxEvent, uuid.UUID(item_id))


def test_the_list_names_each_item_and_its_tenant_but_never_its_payload(platform, gave_up):
    ids, _ = gave_up
    response = platform.get(BASE)
    assert response.status_code == 200 and SECRET not in response.text
    listed = {item["id"]: item for item in response.json()["items"]}
    assert set(ids) <= set(listed)
    item = listed[ids[0]]
    assert item["event_name"] == "TEST_GAVE_UP" and item["attempts"] == 5 and item["tenant_name"]


def test_discarding_needs_a_reason_and_is_recorded_per_tenant(platform, gave_up):
    ids, tenants = gave_up
    assert platform.post(f"{BASE}/discard", json={"ids": ids, "reason": "short"}).status_code == 422
    done = platform.post(f"{BASE}/discard", json={"ids": ids, "reason": REASON})
    assert done.status_code == 200 and done.json() == {"count": 3, "action": "DISCARDED"}
    assert all(_row(item) is None for item in ids)
    first, second = _audit("OUTBOX_EVENTS_DISCARDED", tenants[0]), _audit("OUTBOX_EVENTS_DISCARDED", tenants[2])
    assert first.reason == REASON and first.details["count"] == 2
    assert {item["id"] for item in first.details["items"]} == set(ids[:2])
    assert second.details["count"] == 1
    assert SECRET not in str(first.details)


def test_retrying_puts_the_work_back_in_the_queue_with_fresh_retries(platform, gave_up):
    ids, tenants = gave_up
    done = platform.post(f"{BASE}/retry", json={"ids": ids[:1], "reason": "The connector is fixed, send it again"})
    assert done.status_code == 200 and done.json()["action"] == "RETRIED"
    row = _row(ids[0])
    assert row.dead_lettered_at is None and row.attempts == 0 and row.next_attempt_at is not None
    assert _audit("OUTBOX_EVENTS_RETRIED", tenants[0]).details["items"][0]["id"] == ids[0]


def test_a_selection_that_changed_meanwhile_is_refused_whole(platform, gave_up):
    ids, _ = gave_up
    assert platform.post(f"{BASE}/discard", json={"ids": ids[:1], "reason": REASON}).status_code == 200
    refused = platform.post(f"{BASE}/discard", json={"ids": ids, "reason": REASON})
    assert refused.status_code == 409 and refused.json()["detail"]["code"] == "QUEUE_ITEMS_CHANGED"
    assert _row(ids[1]) is not None and _row(ids[2]) is not None


@pytest.mark.parametrize("path", [BASE, f"{BASE}/retry", f"{BASE}/discard", f"{BASE}/mail-log-check"])
def test_only_a_platform_administrator_may_see_or_act(path, gave_up):
    ids, _ = gave_up
    client = _client_with_role("CUSTOMER_ADMIN")
    body = {"ids": ids, "reason": REASON, "result": "NOT_DELIVERED"}
    response = client.get(path) if path == BASE else client.post(path, json=body)
    assert response.status_code == 403
    assert all(_row(item) is not None for item in ids)


# ------------------------------------------------------------------------------- held after a restore (B6b-D10)

HELD = "held after restore"  # scripts/recovery_check.py's marker (B6b Part D, D1 step 6)
CHECKED = "Resend log searched for the event's recipient and time: no delivery found"


@pytest.fixture
def held():
    """Two events a restored copy had not sent, held by the recovery check, in one tenant."""
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        bind_system(db, "test: events held after a restore")
        tenant = db.query(Tenant.id).order_by(Tenant.created_at).first()[0]
        rows = [
            OutboxEvent(
                id=uuid.uuid4(),
                tenant_id=tenant,
                event_name="TEST_HELD",
                aggregate_type="Test",
                payload={"narrative": SECRET},
                occurred_at=now,
                attempts=0,
                last_error=HELD,
                dead_lettered_at=now,
            )
            for _ in range(2)
        ]
        db.add_all(rows)
        db.commit()
        ids = [str(row.id) for row in rows]
    yield ids, tenant
    with SessionLocal() as db:
        bind_system(db, "test cleanup")
        db.query(OutboxEvent).filter(OutboxEvent.id.in_([uuid.UUID(i) for i in ids])).delete(synchronize_session=False)
        db.commit()


def test_an_event_held_after_a_restore_is_not_retried_without_a_mail_log_check(platform, held):
    ids, tenant = held
    refused = platform.post(f"{BASE}/retry", json={"ids": ids, "reason": REASON})
    assert refused.status_code == 409, refused.text
    detail = refused.json()["detail"]
    assert detail["code"] == "HELD_AFTER_RESTORE" and set(detail["ids"]) == set(ids)
    assert all(_row(item).dead_lettered_at is not None for item in ids)  # nothing was put back in the queue
    record = _audit("OUTBOX_RETRY_REFUSED", tenant)
    assert record.reason == REASON and record.details["code"] == "HELD_AFTER_RESTORE"
    assert {item["mail_log"] for item in record.details["items"]} == {"NOT_CHECKED"}
    assert SECRET not in str(record.details)


def test_a_held_event_the_mail_log_shows_delivered_is_still_refused(platform, held):
    ids, _ = held
    checked = platform.post(f"{BASE}/mail-log-check", json={"ids": ids[:1], "result": "DELIVERED", "reason": CHECKED})
    assert checked.status_code == 200, checked.text
    refused = platform.post(f"{BASE}/retry", json={"ids": ids[:1], "reason": REASON})
    assert refused.status_code == 409 and refused.json()["detail"]["code"] == "HELD_AFTER_RESTORE"


def test_only_the_held_events_the_mail_log_shows_not_delivered_are_retried(platform, held):
    ids, tenant = held
    checked = platform.post(
        f"{BASE}/mail-log-check", json={"ids": ids[:1], "result": "NOT_DELIVERED", "reason": CHECKED}
    )
    assert checked.status_code == 200, checked.text
    record = _audit("OUTBOX_MAIL_LOG_CHECKED", tenant)
    assert record.reason == CHECKED and record.details["items"][0] == {
        "id": ids[0],
        "event_name": "TEST_HELD",
        "result": "NOT_DELIVERED",
    }
    # The whole selection is refused while one of it is unchecked; the checked one alone is retried.
    assert platform.post(f"{BASE}/retry", json={"ids": ids, "reason": REASON}).status_code == 409
    assert _row(ids[0]).dead_lettered_at is not None
    retried = platform.post(f"{BASE}/retry", json={"ids": ids[:1], "reason": REASON})
    assert retried.status_code == 200, retried.text
    assert _row(ids[0]).dead_lettered_at is None and _row(ids[0]).last_error is None
    assert _row(ids[1]).dead_lettered_at is not None


def test_a_mail_log_check_is_recorded_only_for_held_events(platform, gave_up):
    ids, _ = gave_up
    body = {"ids": ids[:1], "result": "NOT_DELIVERED", "reason": CHECKED}
    refused = platform.post(f"{BASE}/mail-log-check", json=body)
    assert refused.status_code == 409 and refused.json()["detail"]["code"] == "NOT_HELD_AFTER_RESTORE"
    # Work that gave up for any other reason is retried as before.
    assert platform.post(f"{BASE}/retry", json={"ids": ids[:1], "reason": REASON}).status_code == 200
