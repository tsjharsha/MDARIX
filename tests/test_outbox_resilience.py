"""The outbox worker retries for hours before giving up, commits one event at a time and stops promptly when asked."""

import importlib.util
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import text

from backend.app.db.models.stage2 import OutboxEvent
from backend.app.db.session import SessionLocal
from backend.app.db.tenant_scope import bind_system
from outbox.worker import OutboxWorker


def test_the_default_schedule_backs_off_from_30s_to_an_hour_over_12_attempts(monkeypatch):
    for name in ("MDARIX_OUTBOX_MAX_ATTEMPTS", "MDARIX_OUTBOX_BASE_DELAY_SECONDS", "MDARIX_OUTBOX_MAX_DELAY_SECONDS"):
        monkeypatch.delenv(name, raising=False)
    worker = OutboxWorker(lambda *_: None)
    assert worker.max_attempts == 12
    delays = [worker.retry_delay(attempt).total_seconds() for attempt in range(1, 12)]
    assert delays == [30, 60, 120, 240, 480, 960, 1920, 3600, 3600, 3600, 3600]
    assert timedelta(hours=5) < timedelta(seconds=sum(delays)) < timedelta(hours=6)


def test_the_schedule_is_configurable_from_the_environment(monkeypatch):
    monkeypatch.setenv("MDARIX_OUTBOX_MAX_ATTEMPTS", "3")
    monkeypatch.setenv("MDARIX_OUTBOX_BASE_DELAY_SECONDS", "5")
    monkeypatch.setenv("MDARIX_OUTBOX_MAX_DELAY_SECONDS", "12")
    worker = OutboxWorker(lambda *_: None)
    assert worker.max_attempts == 3
    assert [worker.retry_delay(n).total_seconds() for n in (1, 2, 3)] == [5, 10, 12]
    monkeypatch.setenv("MDARIX_OUTBOX_MAX_ATTEMPTS", "not a number")
    assert OutboxWorker(lambda *_: None).max_attempts == 12
    with pytest.raises(ValueError):
        OutboxWorker(lambda *_: None, max_attempts=0)


@pytest.fixture
def two_events():
    """Two pending events of one tenant, in order; names are unique to this test run."""
    tag = uuid.uuid4().hex[:8]
    names = (f"KILL_A_{tag}", f"KILL_B_{tag}")
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        bind_system(db, "test: two pending events")
        tenant = db.execute(text("select id from tenants order by created_at limit 1")).scalar_one()
        rows = [
            OutboxEvent(
                id=uuid.uuid4(),
                tenant_id=tenant,
                event_name=name,
                aggregate_type="Test",
                payload={},
                occurred_at=now + timedelta(milliseconds=index),
            )
            for index, name in enumerate(names)
        ]
        db.add_all(rows)
        db.commit()
        ids = {row.event_name: row.id for row in rows}
    yield ids
    with SessionLocal() as db:
        bind_system(db, "test cleanup")
        db.query(OutboxEvent).filter(OutboxEvent.id.in_(list(ids.values()))).delete(synchronize_session=False)
        db.commit()


def _row(event_id):
    with SessionLocal() as db:
        bind_system(db, "test: read outbox row")
        return db.get(OutboxEvent, event_id)


@pytest.mark.db
def test_each_delivered_event_is_committed_before_the_next_so_a_kill_cannot_resend_it(two_events):
    first, second = sorted(two_events)
    delivered = []

    def publisher(name, payload):
        if name == second:
            raise KeyboardInterrupt  # the process is killed while the second event is in hand
        delivered.append(name)

    with pytest.raises(KeyboardInterrupt):
        OutboxWorker(publisher).process_once(limit=500)
    assert first in delivered
    assert _row(two_events[first]).published_at is not None
    untouched = _row(two_events[second])
    assert untouched.published_at is None and untouched.attempts == 0 and untouched.claimed_at is None


@pytest.mark.db
def test_a_shutdown_request_is_honoured_between_events_after_finishing_the_current_one(two_events):
    first, second = sorted(two_events)
    delivered = []
    worker = OutboxWorker(lambda name, payload: delivered.append(name), should_stop=lambda: first in delivered)
    stats = worker.process_once(limit=500)
    assert first in delivered and second not in delivered and stats["published"] >= 1
    assert _row(two_events[second]).published_at is None


@pytest.mark.db
def test_a_failed_event_waits_the_configured_delay_and_records_the_error(two_events):
    first, second = sorted(two_events)
    worker = OutboxWorker(
        lambda name, payload: (_ for _ in ()).throw(RuntimeError("smtp token=abc down")),
        base_delay_seconds=30,
        max_attempts=12,
        should_stop=lambda: _row(two_events[first]).attempts > 0,
    )
    before = datetime.now(timezone.utc)
    worker.process_once(limit=500)
    row = _row(two_events[first])
    assert row.attempts == 1 and row.dead_lettered_at is None
    assert timedelta(seconds=25) <= row.next_attempt_at - before <= timedelta(seconds=40)
    assert row.last_error.startswith("RuntimeError:") and "abc" not in row.last_error and "[REDACTED]" in row.last_error


def _script():
    spec = importlib.util.spec_from_file_location(
        "run_outbox_worker", Path(__file__).resolve().parents[1] / "scripts" / "run_outbox_worker.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_an_unknown_publisher_is_refused_at_startup_with_the_supported_values(monkeypatch):
    script = _script()
    monkeypatch.setenv("MDARIX_OUTBOX_PUBLISHER", "kafka")
    with pytest.raises(SystemExit) as refused:
        script.configured_publisher()
    assert "OUTBOX_PUBLISHER_NOT_IMPLEMENTED" in str(refused.value) and "Supported values: noop" in str(refused.value)
    with pytest.raises(SystemExit, match="OUTBOX_PUBLISHER_NOT_IMPLEMENTED"):
        script.main()
    monkeypatch.setenv("MDARIX_OUTBOX_PUBLISHER", "noop")
    assert script.configured_publisher() == "noop"
    monkeypatch.delenv("MDARIX_OUTBOX_PUBLISHER")
    assert script.configured_publisher() == "noop"


def test_the_worker_script_applies_the_configuration_gate_before_anything_else(monkeypatch):
    import backend.app.config_check as config_check

    def refuse():
        raise SystemExit("MDARIX will not start: probe")

    monkeypatch.setattr(config_check, "enforce", refuse)
    with pytest.raises(SystemExit, match="probe"):
        _script().main()


def test_the_worker_routes_problem_reports_to_the_support_mailer(monkeypatch):
    import backend.app.support_api as support_api

    handled = []
    monkeypatch.setattr(support_api, "deliver_problem_report", lambda db, payload: handled.append(payload) or "SENT")
    _script().publish("SUPPORT_PROBLEM_REPORTED", {"report_id": "abc"})
    assert handled == [{"report_id": "abc"}]


def test_unknown_events_are_acknowledged_by_the_noop_publisher(monkeypatch):
    monkeypatch.delenv("MDARIX_OUTBOX_PUBLISHER", raising=False)
    assert _script().publish("AUDIT_ONLY_EVENT", {}) is None
