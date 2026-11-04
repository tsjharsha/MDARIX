"""Health endpoints: the public one-word status, the scheduler readiness check, request ids and log hygiene."""

import logging
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from backend.app import readiness
from backend.app.db.models.stage2 import SchedulerRun
from backend.app.db.session import SessionLocal
from backend.app.db.tenant_scope import bind_system
from backend.app.logging_setup import JsonFormatter, redact
from backend.app.main import app
from backend.app.request_context import get_request_context


@pytest.fixture
def fresh_cache():
    readiness._cached = None
    yield
    readiness._cached = None


@pytest.mark.parametrize(
    "internal, word, code",
    [("ready", "ok", 200), ("degraded", "degraded", 200), ("not_ready", "down", 503)],
)
def test_the_public_status_is_one_word_and_never_the_component_list(monkeypatch, internal, word, code):
    report = {"status": internal, "checks": [{"name": "database", "ok": False, "error": "schema at md22"}]}
    monkeypatch.setattr(readiness, "readiness_report", lambda: report)
    response = TestClient(app).get("/health/status")
    assert response.status_code == code and response.json() == {"status": word}
    assert "schema" not in response.text and response.headers["Cache-Control"] == "no-store"


def test_the_public_status_shares_the_readiness_cache(fresh_cache):
    client = TestClient(app)
    first = client.get("/health/status").json()
    assert first["status"] in {"ok", "degraded", "down"} and set(first) == {"status"}
    cached_at = readiness._cached[0]
    client.get("/health/status")
    assert readiness._cached[0] == cached_at  # the second call did not probe again


def test_readiness_reports_the_scheduler_as_a_component(fresh_cache):
    report = TestClient(app).get("/health/ready").json()
    names = [item["name"] for item in report["checks"]]
    assert "scheduler" in names and names.index("scheduler") > names.index("database")


@pytest.fixture
def job_row():
    name = f"readiness-test-{uuid.uuid4().hex[:8]}"
    yield name
    with SessionLocal() as db:
        bind_system(db, "test cleanup")
        db.query(SchedulerRun).filter(SchedulerRun.job == name).delete(synchronize_session=False)
        db.commit()


def _set_finished(name, finished):
    with SessionLocal() as db:
        bind_system(db, "test: scheduler run")
        row = db.get(SchedulerRun, name) or SchedulerRun(job=name, consecutive_failures=0, state={})
        row.last_finished_at = finished
        db.add(row)
        db.commit()


@pytest.mark.db
def test_the_scheduler_check_degrades_after_fifteen_minutes_of_silence(job_row):
    with pytest.raises(RuntimeError, match="NOT_REPORTED"):
        readiness._scheduler(job_row)
    _set_finished(job_row, datetime.now(timezone.utc) - timedelta(minutes=2))
    assert 100 <= readiness._scheduler(job_row)["seconds_since"] <= 130
    _set_finished(job_row, datetime.now(timezone.utc) - timedelta(minutes=16))
    with pytest.raises(RuntimeError, match="STALE"):
        readiness._scheduler(job_row)
    check = readiness._check("scheduler", lambda: readiness._scheduler(job_row))
    assert check["ok"] is False and check["error"] == "RuntimeError"


def test_a_500_carries_the_request_id_in_body_and_header():
    def boom():
        raise RuntimeError("secret detail password=hunter2")

    app.dependency_overrides[get_request_context] = boom
    try:
        response = TestClient(app, raise_server_exceptions=False).get(
            "/api/v1/support/problems", headers={"X-Request-ID": "req-500-check-1"}
        )
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 500 and response.headers["X-Request-ID"] == "req-500-check-1"
    body = response.json()["detail"]
    assert body["request_id"] == "req-500-check-1" and body["code"] == "INTERNAL_ERROR"
    assert "hunter2" not in response.text


def test_every_response_has_a_request_id_even_for_unknown_paths():
    response = TestClient(app).get("/no/such/path")
    assert response.status_code == 404 and len(response.headers["X-Request-ID"]) >= 8


def test_the_request_log_line_carries_the_path_without_the_query_string(caplog):
    with caplog.at_level(logging.INFO, logger="mdarix.api"):
        TestClient(app).get("/api/v1/support/problems?token=supersecret&code=123456")
    lines = [record for record in caplog.records if record.name == "mdarix.api"]
    assert lines and lines[-1].getMessage() == "GET /api/v1/support/problems 401"
    assert "supersecret" not in lines[-1].getMessage() and lines[-1].path == "/api/v1/support/problems"


def test_logged_text_never_shows_tokens_or_passwords():
    assert (
        redact("sent https://app/activate-account?token=abc123&x=1")
        == "sent https://app/activate-account?token=[REDACTED]&x=1"
    )
    assert redact("Password=hunter2; api_key=k") == "Password=[REDACTED]; api_key=[REDACTED]"
    record = logging.LogRecord("t", logging.INFO, __file__, 1, "reset link token=%s", ("tok-xyz",), None)
    formatted = JsonFormatter().format(record)
    assert "tok-xyz" not in formatted and "token=[REDACTED]" in formatted


@pytest.mark.db
def test_the_outbox_backlog_counts_due_retrying_and_failing_email_events():
    """0.10.88 (DEV-13): the queue's lag and the e-mails the provider refused, read from the outbox itself."""
    from backend.app.db.models.stage2 import OutboxEvent

    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        before = readiness.outbox_backlog(db)
        tenant = db.execute(readiness.text("SELECT id FROM tenants LIMIT 1")).scalar()
        rows = [
            OutboxEvent(
                id=uuid.uuid4(),
                tenant_id=tenant,
                event_name="TEST_EMAIL",
                aggregate_type="Test",
                payload={},
                occurred_at=now - timedelta(minutes=20),
                attempts=1,
                last_error="EmailDeliveryError: The email provider refused the message",
            ),
            # Backing off until later: waiting, but not due, so it adds no lag.
            OutboxEvent(
                id=uuid.uuid4(),
                tenant_id=tenant,
                event_name="TEST_LATER",
                aggregate_type="Test",
                payload={},
                occurred_at=now,
                attempts=2,
                next_attempt_at=now + timedelta(hours=1),
                last_error="RuntimeError: x",
            ),
        ]
        db.add_all(rows)
        db.commit()
        try:
            after = readiness.outbox_backlog(db)
            assert after["waiting"] == before["waiting"] + 2 and after["retrying"] == before["retrying"] + 2
            assert after["email_failing"] == before["email_failing"] + 1
            assert after["lag_seconds"] >= 20 * 60 - 5
        finally:
            bind_system(db, "test cleanup")
            db.query(OutboxEvent).filter(OutboxEvent.id.in_([row.id for row in rows])).delete(synchronize_session=False)
            db.commit()


def test_the_outbox_and_email_checks_degrade_on_lag_and_failing_delivery(monkeypatch):
    import auth.emailer

    backlog = {"waiting": 3, "retrying": 0, "email_failing": 0, "lag_seconds": 30}
    monkeypatch.setattr(readiness, "outbox_backlog", lambda db: dict(backlog))
    monkeypatch.setattr(auth.emailer, "smtp_configuration_status", lambda: {"configured": True})
    outbox = readiness._check("outbox", readiness._outbox)
    assert outbox["ok"] is True
    assert readiness._check("email", lambda: readiness._email(outbox["email_failing"]))["ok"] is True
    backlog.update(lag_seconds=16 * 60, email_failing=2)
    assert readiness._check("outbox", readiness._outbox)["ok"] is False
    assert readiness._check("email", lambda: readiness._email(backlog["email_failing"]))["ok"] is False


def test_readiness_reports_the_outbox_as_a_component(fresh_cache):
    names = [item["name"] for item in TestClient(app).get("/health/ready").json()["checks"]]
    assert "outbox" in names
