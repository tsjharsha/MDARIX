"""Connector checks report what really happened: a reachability test through the outbound policy, FILE health from
object storage, and an email to administrators when an unattended sync starts failing (once per outage)."""

import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from backend.app.access import configuration, connector_sync
from backend.app.db.models.enterprise import ConnectorRun
from backend.app.db.models.foundation import ConnectorConfiguration, Tenant
from backend.app.db.models.stage2 import OutboxEvent
from backend.app.db.session import SessionLocal
from backend.app.db.tenant_scope import bind_system
from tests.test_business_permissions import _client_with_role


def _row(**configuration_values):
    return SimpleNamespace(
        id=uuid.uuid4(), code="erp", connector_type="REST", configuration=configuration_values, version="v1"
    )


def test_a_reachable_system_succeeds_and_an_unreachable_one_fails(monkeypatch):
    calls = []

    def probe(row, path_key):
        calls.append(path_key)
        return {"status": "HEALTHY", "http_status": 200, "payload": {"secret": "not echoed"}}

    monkeypatch.setattr(configuration, "_provider_get", probe)
    ok = configuration.connection_test(_row(endpoint="https://erp.example.com"))
    assert ok == {"status": "SUCCESS", "connector_type": "REST", "http_status": 200} and calls == ["health_path"]

    monkeypatch.setattr(
        configuration, "_provider_get", lambda row, key: {"status": "FAILED", "reason": "PROVIDER_UNREACHABLE"}
    )
    assert configuration.connection_test(_row(endpoint="https://erp.example.com")) == {
        "status": "FAILED",
        "connector_type": "REST",
        "reason": "PROVIDER_UNREACHABLE",
    }
    monkeypatch.setattr(
        configuration,
        "_provider_get",
        lambda row, key: {"status": "INVALID_CONFIGURATION", "reason": "CONNECTOR_PRIVATE_DESTINATION_BLOCKED"},
    )
    blocked = configuration.connection_test(_row(endpoint="http://169.254.169.254"))
    assert blocked["status"] == "INVALID_CONFIGURATION"


def test_without_an_endpoint_nothing_is_claimed():
    assert configuration.connection_test(_row())["status"] == "NOT_CONFIGURED"
    file_row = _row()
    file_row.connector_type = "FILE"
    assert configuration.connection_test(file_row)["status"] == "NOT_APPLICABLE"


def test_the_real_outbound_policy_refuses_a_private_endpoint():
    """No monkeypatching: a loopback address is refused by the SSRF-safe client, so the test cannot succeed."""
    result = configuration.connection_test(_row(endpoint="http://127.0.0.1:9", timeout_seconds=1))
    assert result["status"] in {"FAILED", "INVALID_CONFIGURATION"}


@pytest.mark.db
def test_file_health_follows_object_storage(monkeypatch):
    client = _client_with_role("Investigator")
    from backend.app import readiness

    monkeypatch.setattr(readiness, "_object_storage", lambda: {"provider": "local"})
    assert client.get("/api/v1/integrations/health/FILE").json()["status"] == "HEALTHY"

    def down():
        raise ConnectionError("bucket unreachable")

    monkeypatch.setattr(readiness, "_object_storage", down)
    body = client.get("/api/v1/integrations/health/FILE").json()
    assert body["status"] == "UNAVAILABLE" and body["configuration_valid"] is False
    rest = client.get("/api/v1/integrations/health/REST").json()
    assert rest["status"] in {"CONFIGURED", "NOT_CONFIGURED"}  # never HEALTHY without a check


# ------------------------------------------------------------------------------------------- failure emails


@pytest.fixture
def db():
    session = SessionLocal()
    bind_system(session, "connector failure tests")
    try:
        yield session
    finally:
        session.rollback()
        session.close()


def _connector(db) -> ConnectorConfiguration:
    tenant_id = (
        db.query(Tenant.id).filter(Tenant.tenant_key == "ACME_CARE_SYNTHETIC").scalar()
        or db.query(Tenant.id).first()[0]
    )
    now = datetime.now(timezone.utc)
    row = ConnectorConfiguration(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        code=f"sync-{uuid.uuid4().hex[:8]}",
        connector_type="REST",
        configuration={"endpoint": "https://erp.example.com"},
        version="v1",
        status="ACTIVE",
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    db.flush()
    return row


def _run(db, row, status, minutes_ago):
    started = datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)
    db.add(
        ConnectorRun(
            id=uuid.uuid4(),
            tenant_id=row.tenant_id,
            connection_id=row.code,
            source_system="ERP",
            run_type="SCHEDULED",
            status=status,
            records_received=0,
            records_accepted=0,
            records_rejected=0,
            started_at=started,
            completed_at=started,
            created_at=started,
        )
    )
    db.flush()


def _alerts(db, row) -> list:
    return (
        db.query(OutboxEvent)
        .filter(OutboxEvent.event_name == "CONNECTOR_SYNC_FAILED", OutboxEvent.aggregate_id == row.id)
        .all()
    )


@pytest.mark.db
def test_an_unattended_failure_is_emailed_once_per_outage(db):
    row = _connector(db)
    _run(db, row, "COMPLETED", 60)
    connector_sync._notify_failure(db, row.tenant_id, row, "PROVIDER_READ_FAILED", "SCHEDULED")
    _run(db, row, "FAILED", 0)
    alerts = _alerts(db, row)
    assert len(alerts) == 1 and alerts[0].payload["failure"] == "PROVIDER_READ_FAILED"
    # Still failing a quarter of an hour later: no second email.
    connector_sync._notify_failure(db, row.tenant_id, row, "PROVIDER_READ_FAILED", "SCHEDULED")
    assert len(_alerts(db, row)) == 1


@pytest.mark.db
def test_a_failed_sync_now_is_not_emailed(db):
    row = _connector(db)
    connector_sync._notify_failure(db, row.tenant_id, row, "PROVIDER_READ_FAILED", "MANUAL")
    assert _alerts(db, row) == []
