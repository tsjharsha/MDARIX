"""Connector syncs page through the provider, retry transient failures, stay within limits, and run on a schedule."""

import io
import json
import uuid
from datetime import datetime, timedelta, timezone
from urllib.error import HTTPError

import pytest

import backend.app.access.connector_sync as sync
from backend.app.db.models.enterprise import ConnectorRun
from backend.app.db.models.foundation import ConnectorConfiguration, Tenant
from backend.app.db.session import SessionLocal
from backend.app.db.tenant_scope import bind_system

BASE = "https://provider.example/api/records/Complaint"


class _Reply:
    def __init__(self, body: dict):
        self.raw = json.dumps(body).encode()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, limit=None):
        return self.raw


@pytest.fixture
def provider(monkeypatch):
    """A fake provider: ``pages`` maps a URL to its JSON reply (or an exception to raise)."""
    pages: dict = {}
    calls: list = []

    def urlopen(request, timeout=None):
        calls.append(request.full_url)
        reply = pages[request.full_url]
        if isinstance(reply, list):
            reply = reply.pop(0)
        if isinstance(reply, Exception):
            raise reply
        return _Reply(reply)

    monkeypatch.setattr(sync, "safe_urlopen", urlopen)
    monkeypatch.setattr(sync, "_safe_provider_url", lambda endpoint, path, timeout=10: BASE)
    monkeypatch.setattr(sync, "_connector_credential", lambda configuration, row: None)
    monkeypatch.setattr(sync.time, "sleep", lambda seconds: None)
    return pages, calls


def _row(**configuration):
    return ConnectorConfiguration(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        code="TW",
        connector_type="QMS",
        configuration={"endpoint": "https://provider.example/api", **configuration},
        status="ACTIVE",
    )


def _error(code: int) -> HTTPError:
    return HTTPError(BASE, code, "error", {"retry-after": "0"}, io.BytesIO(b"{}"))


def test_every_page_is_read_by_next_link_and_by_cursor(provider):
    pages, _ = provider
    pages[BASE] = {"records": [{"id": "1"}], "next": "/api/records/Complaint?page=2"}
    pages[BASE + "?page=2"] = {"records": [{"id": "2"}], "next_cursor": "abc"}
    pages[BASE + "?cursor=abc"] = {"records": [{"id": "3"}]}
    assert [item["id"] for item in sync.fetch_provider_records(_row(), "Complaint")] == ["1", "2", "3"]


def test_a_next_link_to_another_host_is_refused(provider):
    pages, _ = provider
    pages[BASE] = {"records": [], "next": "https://elsewhere.example/steal"}
    with pytest.raises(sync.ProviderReadError, match="PROVIDER_NEXT_LINK_REFUSED"):
        sync.fetch_provider_records(_row(), "Complaint")


def test_transient_failures_are_retried_and_refusals_are_not(provider):
    pages, calls = provider
    pages[BASE] = [_error(503), _error(429), {"records": [{"id": "1"}]}]
    assert len(sync.fetch_provider_records(_row(), "Complaint")) == 1 and len(calls) == 3
    calls.clear()
    pages[BASE] = [_error(404), {"records": []}]
    with pytest.raises(sync.ProviderReadError, match="PROVIDER_READ_FAILED"):
        sync.fetch_provider_records(_row(), "Complaint")
    assert len(calls) == 1


def test_a_sync_stops_at_its_size_and_page_limits(provider, monkeypatch):
    pages, _ = provider
    pages[BASE] = {"records": [{"id": "1"}], "next": "/api/records/Complaint?page=2"}
    pages[BASE + "?page=2"] = {"records": [{"id": "2"}], "next": "/api/records/Complaint?page=3"}
    with pytest.raises(sync.ProviderReadError, match="PROVIDER_TOO_MANY_PAGES"):
        sync.fetch_provider_records(_row(max_pages=2), "Complaint")
    monkeypatch.setenv("MDARIX_CONNECTOR_MAX_BYTES", "10")
    with pytest.raises(sync.ProviderReadError, match="PROVIDER_RESPONSE_TOO_LARGE"):
        sync.fetch_provider_records(_row(), "Complaint")


def test_scheduled_connections_sync_when_due_and_failures_are_recorded(provider):
    pages, calls = provider
    db = SessionLocal()
    bind_system(db, "test")
    tenant = db.query(Tenant).filter(Tenant.tenant_key == "ACME_CARE_SYNTHETIC").first() or db.query(Tenant).first()
    now = datetime.now(timezone.utc)
    code = f"SCHED-{uuid.uuid4().hex[:6]}"
    row = ConnectorConfiguration(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        code=code,
        connector_type="QMS",
        configuration={
            "endpoint": "https://provider.example/api",
            "sync_every_minutes": 60,
            "source_object": "Complaint",
        },
        status="ACTIVE",
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    db.commit()
    try:
        pages[BASE] = {"records": [{"id": "s-1"}]}
        assert sync.run_scheduled_syncs(db, now)["synced"] >= 1
        runs = db.query(ConnectorRun).filter(ConnectorRun.connection_id == code).all()
        assert [(run.run_type, run.status, run.records_received) for run in runs] == [("SCHEDULED", "COMPLETED", 1)]
        calls.clear()
        sync.run_scheduled_syncs(db, now + timedelta(minutes=10))  # not due yet
        assert BASE not in calls
        pages[BASE] = [_error(500), _error(500), _error(500)]
        result = sync.run_scheduled_syncs(db, now + timedelta(minutes=61))
        assert {"tenant_id": str(tenant.id), "connection": code, "error": "PROVIDER_READ_FAILED"} in result["failed"]
        failed = (
            db.query(ConnectorRun).filter(ConnectorRun.connection_id == code, ConnectorRun.status == "FAILED").one()
        )
        assert failed.failure_category == "PROVIDER_READ_FAILED"
    finally:
        db.rollback()
        bind_system(db, "test cleanup")
        db.query(ConnectorRun).filter(ConnectorRun.connection_id == code).delete()
        db.query(ConnectorConfiguration).filter(ConnectorConfiguration.code == code).delete()
        db.commit()
        db.close()
