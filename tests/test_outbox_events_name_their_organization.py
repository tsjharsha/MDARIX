"""RSK-026 follow-up: the events that belong to one organization name it in their payload (``tenant_id``), so the outbox
worker's payload check (``outbox.worker.payload_tenant_mismatch``) covers them too. Each test queues the event through
its real producer. SUBSCRIPTION_REMINDER and the scheduler's TRIAL_REMINDER are covered by
tests/test_scheduled_job_scope.py, SUPPORT_PROBLEM_REPORTED by tests/test_support_problems.py."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from backend.app.db.models.stage2 import OutboxEvent
from outbox.worker import payload_tenant_mismatch


def _covered_by_the_check(event: OutboxEvent) -> None:
    """The payload names the event's own organization: the worker hands it on, and the same payload on another
    organization's row is refused."""
    assert event.payload["tenant_id"] == str(event.tenant_id), (event.event_name, event.payload)
    assert not payload_tenant_mismatch(event)
    assert payload_tenant_mismatch(OutboxEvent(tenant_id=uuid.uuid4(), payload=dict(event.payload)))


@pytest.mark.unit
def test_the_trial_ended_early_email_names_its_organization():
    from backend.app.trial.early_exit import _queue_ended_email

    added: list = []
    subscription = SimpleNamespace(
        id=uuid.uuid4(), tenant_id=uuid.uuid4(), expires_at=datetime.now(timezone.utc) - timedelta(minutes=1)
    )
    _queue_ended_email(SimpleNamespace(add=added.append), subscription, datetime.now(timezone.utc))
    (event,) = added
    assert event.event_name == "TRIAL_REMINDER" and event.tenant_id == subscription.tenant_id
    _covered_by_the_check(event)


@pytest.mark.db
def test_a_requested_export_names_its_organization():
    from backend.app.db.session import SessionLocal
    from backend.app.db.tenant_scope import bind_tenant
    from backend.app.tenant_export import EVENT, request_export
    from tests.test_customer_admin_account_security import _tenant

    with SessionLocal() as db:
        tenant = _tenant(db, "EXPORT-EVENT")
        tenant_id = tenant.id
        db.commit()
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        row = request_export(db, tenant_id, "test:export-event", "Hand the data back")
        # Queued in the caller's session (request_export does not commit).
        (event,) = [item for item in db.new if isinstance(item, OutboxEvent) and item.aggregate_id == row.id]
        assert event.event_name == EVENT and event.tenant_id == tenant_id
        _covered_by_the_check(event)
        db.rollback()


@pytest.mark.db
def test_a_simulated_provider_record_names_its_organization():
    from sqlalchemy import text

    from backend.app.db.session import SessionLocal
    from backend.app.db.tenant_scope import bind_system
    from integration.simulator_ingestion import enqueue_provider_records

    external_id = f"SIM-ORG-{uuid.uuid4().hex[:8]}"
    with SessionLocal() as db:
        bind_system(db, "test: a simulated provider record")
        tenant_id = db.execute(text("select id from tenants order by created_at limit 1")).scalar_one()
        records = [{"external_id": external_id, "record_version": "1", "severity": "MAJOR"}]
        assert enqueue_provider_records(db, tenant_id, "SIMULATOR", "TENANT_A", "Complaint", records) == 1
        db.flush()
        event = (
            db.query(OutboxEvent)
            .filter(
                OutboxEvent.event_name == "PROVIDER_RECORD_RECEIVED",
                OutboxEvent.payload["external_id"].as_string() == external_id,
            )
            .one()
        )
        _covered_by_the_check(event)
        db.rollback()
