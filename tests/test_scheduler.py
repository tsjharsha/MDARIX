"""The scheduler: the run loop, the per-job lock, failure and recovery alerts, the heartbeat file, missed jobs and
the operations-alerts job's dead-letter counting."""

import importlib.util
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import text

from backend.app import scheduler
from backend.app.db.models.stage2 import OutboxEvent, SchedulerRun
from backend.app.db.session import SessionLocal, engine
from backend.app.db.tenant_scope import bind_system
from backend.app.scheduler import Job


@pytest.fixture
def alerts(monkeypatch):
    sent = []
    monkeypatch.setattr(scheduler, "send_alert", lambda subject, body: sent.append((subject, body)) or {})
    return sent


@pytest.fixture
def job_name():
    name = f"test-job-{uuid.uuid4().hex[:8]}"
    yield name
    with SessionLocal() as db:
        bind_system(db, "test cleanup")
        db.query(SchedulerRun).filter(SchedulerRun.job == name).delete(synchronize_session=False)
        db.commit()


def _run_row(name):
    with SessionLocal() as db:
        bind_system(db, "test: read scheduler run")
        return db.get(SchedulerRun, name)


@pytest.mark.db
def test_a_due_job_runs_once_and_its_run_is_recorded(job_name):
    calls = []
    job = Job(job_name, timedelta(minutes=5), lambda db, state: calls.append(1) or {"done": len(calls)}, "Test job")
    first = scheduler.run_due_jobs(jobs=(job,))
    assert [item["status"] for item in first] == ["OK"] and first[0]["result"] == {"done": 1}
    # Not due again until its interval has passed.
    assert scheduler.run_due_jobs(jobs=(job,)) == [] and calls == [1]
    row = _run_row(job_name)
    assert row.last_status == "OK" and row.consecutive_failures == 0 and row.last_finished_at is not None


@pytest.mark.db
def test_state_persists_between_runs_only_when_the_job_succeeds(job_name):
    seen = []

    def run(db, state):
        seen.append(dict(state))
        state["counter"] = state.get("counter", 0) + 1
        if state["counter"] == 2:
            raise RuntimeError("second run fails")
        return {}

    job = Job(job_name, timedelta(seconds=0), run, "Test job")
    scheduler.run_job(job)
    scheduler.run_job(job)
    scheduler.run_job(job)
    assert seen == [{}, {"counter": 1}, {"counter": 1}]


@pytest.mark.db
def test_another_instance_holding_the_lock_means_the_job_is_skipped(job_name):
    job = Job(job_name, timedelta(minutes=5), lambda db, state: {"ran": True}, "Test job")
    with engine.connect() as other:
        got = other.execute(text("SELECT pg_try_advisory_lock(hashtext(:key))"), {"key": f"mdarix-job:{job_name}"})
        assert got.scalar() is True
        other.commit()
        try:
            assert scheduler.run_job(job) is None
        finally:
            other.execute(text("SELECT pg_advisory_unlock(hashtext(:key))"), {"key": f"mdarix-job:{job_name}"})
            other.commit()
    assert scheduler.run_job(job)["status"] == "OK"


@pytest.mark.db
def test_three_failures_alert_once_and_recovery_alerts_once(job_name, alerts):
    broken = {"now": True}

    def run(db, state):
        if broken["now"]:
            raise RuntimeError("provider down")
        return {"ok": True}

    job = Job(job_name, timedelta(seconds=0), run, "Test job")
    for _ in range(4):
        assert scheduler.run_job(job)["status"] == "FAILED"
    failing = [item for item in alerts if item[0] == f"Scheduled job failing: {job_name}"]
    assert len(failing) == 1 and "RuntimeError: provider down" in failing[0][1]
    assert _run_row(job_name).consecutive_failures == 4
    broken["now"] = False
    assert scheduler.run_job(job)["status"] == "OK"
    assert alerts[-1][0] == f"Scheduled job recovered: {job_name}" and _run_row(job_name).consecutive_failures == 0


def test_the_loop_writes_the_heartbeat_file_and_stops_at_once_when_told(monkeypatch, tmp_path, alerts):
    heartbeat = tmp_path / "scheduler" / "heartbeat"
    monkeypatch.setenv("MDARIX_SCHEDULER_HEARTBEAT_FILE", str(heartbeat))
    shutdown = threading.Event()
    cycles = []

    def one_cycle():
        cycles.append(time.monotonic())
        return []

    monkeypatch.setattr(scheduler, "run_due_jobs", one_cycle)
    monkeypatch.setattr(scheduler, "check_missed_jobs", lambda: [])
    # The loop would sleep an hour between cycles; a shutdown request must end it immediately.
    threading.Timer(0.5, shutdown.set).start()
    started = time.monotonic()
    scheduler.serve(poll_seconds=3600, shutdown=shutdown)
    assert time.monotonic() - started < 5 and len(cycles) == 1
    written = datetime.fromisoformat(heartbeat.read_text(encoding="utf-8"))
    assert abs((datetime.now(timezone.utc) - written).total_seconds()) < 5
    assert not heartbeat.with_name(heartbeat.name + ".tmp").exists()


def test_a_cycle_that_fails_is_logged_and_the_heartbeat_still_written(monkeypatch, tmp_path, caplog):
    heartbeat = tmp_path / "heartbeat"
    monkeypatch.setenv("MDARIX_SCHEDULER_HEARTBEAT_FILE", str(heartbeat))
    shutdown = threading.Event()

    def broken():
        shutdown.set()
        raise RuntimeError("database away")

    monkeypatch.setattr(scheduler, "run_due_jobs", broken)
    scheduler.serve(poll_seconds=0, shutdown=shutdown)
    assert heartbeat.exists() and any("Scheduler cycle failed" in record.getMessage() for record in caplog.records)


def test_a_job_silent_for_twice_its_interval_is_alerted_once_and_its_return_once(alerts):
    scheduler._missed_reported.clear()
    now = datetime.now(timezone.utc)
    job = Job("missed-test", timedelta(minutes=5), lambda db, state: {}, "Missed test job")
    stale = SchedulerRun(
        job=job.name, last_started_at=now - timedelta(minutes=12), last_finished_at=now - timedelta(minutes=11)
    )
    assert scheduler.check_missed_jobs(now, jobs=(job,), rows={job.name: stale}) == ["missed-test"]
    assert scheduler.check_missed_jobs(now, jobs=(job,), rows={job.name: stale}) == ["missed-test"]
    assert [subject for subject, _ in alerts] == ["Scheduled job missed: missed-test"]
    assert "11 minutes ago" in alerts[0][1]
    fresh = SchedulerRun(job=job.name, last_started_at=now - timedelta(minutes=1), last_finished_at=now)
    assert scheduler.check_missed_jobs(now, jobs=(job,), rows={job.name: fresh}) == []
    assert alerts[-1][0] == "Scheduled job running again: missed-test" and len(alerts) == 2
    scheduler._missed_reported.clear()


def test_a_long_running_job_and_a_job_that_never_ran_are_not_missed():
    now = datetime.now(timezone.utc)
    job = Job("long", timedelta(minutes=5), lambda db, state: {}, "Long job")
    running = SchedulerRun(
        job="long", last_started_at=now - timedelta(minutes=3), last_finished_at=now - timedelta(hours=2)
    )
    assert scheduler.missed_jobs({"long": running}, now, (job,)) == []
    assert scheduler.missed_jobs({}, now, (job,)) == []
    assert scheduler.missed_jobs({"long": SchedulerRun(job="long")}, now, (job,)) == []


@pytest.fixture
def dead_letter():
    with SessionLocal() as db:
        bind_system(db, "test: a dead-lettered event")
        tenant = db.execute(text("select id from tenants order by created_at limit 1")).scalar_one()
        row = OutboxEvent(
            id=uuid.uuid4(),
            tenant_id=tenant,
            event_name="TEST_DEAD",
            aggregate_type="Test",
            payload={},
            occurred_at=datetime.now(timezone.utc),
            attempts=12,
            last_error="RuntimeError: x",
            dead_lettered_at=datetime.now(timezone.utc),
        )
        db.add(row)
        db.commit()
        row_id = row.id
    yield row_id
    with SessionLocal() as db:
        bind_system(db, "test cleanup")
        db.query(OutboxEvent).filter(OutboxEvent.id == row_id).delete(synchronize_session=False)
        db.commit()


def _dead_count(db):
    return int(db.execute(text("SELECT count(*) FROM event_outbox WHERE dead_lettered_at IS NOT NULL")).scalar())


@pytest.mark.db
def test_the_operations_job_alerts_only_when_the_dead_letter_count_rises(alerts, monkeypatch, dead_letter):
    from backend.app.worker_status import worker_status

    monkeypatch.setenv("MDARIX_SCHEDULER_HEARTBEAT_URL", "")
    with SessionLocal() as db:
        bind_system(db, "test: operations alerts")
        total = _dead_count(db)
        worker = worker_status(db)["state"]
        # Nothing seen yet: everything already in the queue is reported, nothing is assumed known.
        state = {"worker": worker}
        result = scheduler.operations_alerts(db, state)
        assert result["dead_letters"] == total and state["dead_letters"] == total
        assert [subject for subject, _ in alerts] == ["Dead-letter queue grew"] and f"({total} in total)" in alerts[0][
            1
        ]
        # Same count: silence.
        scheduler.operations_alerts(db, state)
        assert len(alerts) == 1
        # One fewer (an operator discarded it): the count is remembered, nobody is alerted.
        db.query(OutboxEvent).filter(OutboxEvent.id == dead_letter).update({OutboxEvent.dead_lettered_at: None})
        db.commit()
        scheduler.operations_alerts(db, state)
        assert state["dead_letters"] == total - 1 and len(alerts) == 1
        # Back up by one: exactly one alert naming the increase.
        db.query(OutboxEvent).filter(OutboxEvent.id == dead_letter).update(
            {OutboxEvent.dead_lettered_at: datetime.now(timezone.utc)}
        )
        db.commit()
        scheduler.operations_alerts(db, state)
        assert len(alerts) == 2 and alerts[1][1].startswith("1 more event(s)")


def test_the_operations_job_pings_the_dead_mans_switch(monkeypatch):
    pinged = []
    monkeypatch.setattr(scheduler, "_ping", lambda url, timeout: pinged.append((url, timeout)))
    monkeypatch.setenv("MDARIX_SCHEDULER_HEARTBEAT_URL", "")
    assert scheduler.ping_heartbeat_url() == "NOT_CONFIGURED" and pinged == []
    monkeypatch.setenv("MDARIX_SCHEDULER_HEARTBEAT_URL", "https://hc.example.test/ping/abc")
    assert scheduler.ping_heartbeat_url() == "SENT" and pinged == [("https://hc.example.test/ping/abc", 10.0)]
    monkeypatch.setattr(scheduler, "_ping", lambda url, timeout: (_ for _ in ()).throw(OSError("unreachable")))
    assert scheduler.ping_heartbeat_url() == "FAILED"


def _script():
    spec = importlib.util.spec_from_file_location(
        "run_scheduler", Path(__file__).resolve().parents[1] / "scripts" / "run_scheduler.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_once_runs_the_due_jobs_and_exits_nonzero_when_one_failed(monkeypatch, capsys):
    outcomes = [{"job": "a", "status": "OK", "result": {}, "error": None, "seconds": 0.1}]
    monkeypatch.setattr(scheduler, "run_due_jobs", lambda: outcomes)
    assert _script().main(["--once"]) == 0
    assert '"job": "a"' in capsys.readouterr().out
    outcomes.append({"job": "b", "status": "FAILED", "result": {}, "error": "RuntimeError: x", "seconds": 0.1})
    assert _script().main(["--once"]) == 1


def test_the_scheduler_script_applies_the_configuration_gate_first(monkeypatch):
    import backend.app.config_check as config_check

    def refuse():
        raise SystemExit("MDARIX will not start: probe")

    monkeypatch.setattr(config_check, "enforce", refuse)
    monkeypatch.setattr(scheduler, "run_due_jobs", lambda: pytest.fail("jobs ran before the configuration check"))
    with pytest.raises(SystemExit, match="probe"):
        _script().main(["--once"])


def test_a_stuck_or_unsettled_signature_alerts_once_and_its_clearing_once(alerts, monkeypatch):
    """0.10.88 (DEV-13): a signature PENDING over 30 minutes, or one the settlement could not settle, reaches the
    operators; before, the job only logged it."""
    from backend.app import signing_commit

    outcome = {"failed": ["sig-1"], "stuck": 0}
    monkeypatch.setattr(
        signing_commit, "settle_pending", lambda db: {"pending": 1, "settled": {}, "failed": outcome["failed"]}
    )
    monkeypatch.setattr(scheduler, "_stuck_signatures", lambda db: outcome["stuck"])
    state: dict = {}
    assert scheduler.signature_settlement(None, state)["failed"] == ["sig-1"]
    assert [subject for subject, _ in alerts] == ["Signatures not settled"]
    outcome.update(failed=[], stuck=2)
    assert scheduler.signature_settlement(None, state)["stuck"] == 2
    assert len(alerts) == 1  # still a problem: no second alert
    outcome.update(stuck=0)
    scheduler.signature_settlement(None, state)
    assert [subject for subject, _ in alerts] == ["Signatures not settled", "Signatures settled again"]


@pytest.mark.db
def test_stuck_signatures_are_counted_in_the_control_database():
    with SessionLocal() as db:
        assert scheduler._stuck_signatures(db, timedelta(days=36500)) == 0
        assert scheduler._stuck_signatures(db) >= 0
