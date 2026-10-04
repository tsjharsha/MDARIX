"""Browser error reports: accepted from anyone, attributed when a session exists, capped, rate limited, never a 500."""

import secrets
import uuid

import pytest
from fastapi.testclient import TestClient

from backend.app import client_errors
from backend.app.db.models.pilot_support import ClientErrorReport
from backend.app.db.session import SessionLocal
from backend.app.db.tenant_scope import bind_system
from backend.app.main import app
from tests.conftest import authenticated_client

URL = "/api/v1/client-errors"


@pytest.fixture
def cleanup():
    tags = []
    yield tags
    with SessionLocal() as db:
        bind_system(db, "test cleanup")
        for tag in tags:
            db.query(ClientErrorReport).filter(ClientErrorReport.message.contains(tag)).delete(
                synchronize_session=False
            )
        db.commit()


def _row(tag):
    with SessionLocal() as db:
        bind_system(db, "test: read client error")
        return db.query(ClientErrorReport).filter(ClientErrorReport.message.contains(tag)).one_or_none()


def _report(tag, **extra):
    return {"path": "/app/investigations", "message": f"TypeError: x is undefined [{tag}]", **extra}


def test_an_anonymous_report_is_stored_without_an_organization(cleanup, monkeypatch):
    monkeypatch.setenv("MDARIX_RELEASE", "2026.10.3")
    tag = uuid.uuid4().hex[:10]
    cleanup.append(tag)
    response = TestClient(app).post(
        URL,
        json=_report(tag, stack="at render (bundle.js:1:2)", component="SignIn", request_id="req-browser-001"),
        headers={"User-Agent": "TestBrowser/2.0"},
    )
    assert response.status_code == 202 and response.json() == {"accepted": True}
    row = _row(tag)
    assert row.tenant_id is None and row.user_id is None
    assert row.component == "SignIn" and row.stack == "at render (bundle.js:1:2)"
    assert row.user_agent == "TestBrowser/2.0" and row.request_id == "req-browser-001" and row.release == "2026.10.3"


def test_a_signed_in_report_is_filed_under_the_organization_and_user(cleanup):
    tag = uuid.uuid4().hex[:10]
    cleanup.append(tag)
    client = authenticated_client()
    assert client.post(URL, json=_report(tag, request_id="bad id!")).status_code == 202
    row = _row(tag)
    assert row.tenant_id is not None and row.user_id is not None
    assert row.request_id is None  # an unusable caller id is dropped, not stored


def test_a_stale_or_unknown_cookie_falls_back_to_anonymous(cleanup):
    tag = uuid.uuid4().hex[:10]
    cleanup.append(tag)
    client = TestClient(app)
    client.cookies.set("mdarix_session", "not-a-real-session-token")
    assert client.post(URL, json=_report(tag)).status_code == 202
    assert _row(tag).tenant_id is None


def test_oversized_and_invalid_reports_are_refused_without_a_500(cleanup):
    client = TestClient(app)
    huge = client.post(URL, json=_report("huge", stack="x" * (client_errors.MAX_BODY_BYTES + 100)))
    assert huge.status_code == 413 and huge.json()["detail"]["code"] == "REPORT_TOO_LARGE"
    invalid = client.post(URL, json={"path": "/app"})
    assert invalid.status_code == 422 and invalid.json()["detail"]["code"] == "REPORT_INVALID"
    assert client.post(URL, content=b"not json", headers={"Content-Type": "application/json"}).status_code == 422
    assert _row("huge") is None


def test_a_storage_failure_still_answers_202(monkeypatch, caplog):
    def broken(*_args, **_kwargs):
        raise RuntimeError("database away")

    monkeypatch.setattr(client_errors, "_store", broken)
    response = TestClient(app).post(URL, json=_report("unstored"))
    assert response.status_code == 202 and response.json() == {"accepted": True}
    assert any("could not be stored" in record.getMessage() for record in caplog.records)


def test_reports_are_rate_limited_per_address(monkeypatch, cleanup):
    monkeypatch.setenv("MDARIX_RATE_LIMITS_ENABLED", "true")
    monkeypatch.setenv("MDARIX_RATE_LIMIT_SALT", secrets.token_hex(16))
    monkeypatch.setenv("MDARIX_TRUSTED_PROXY_HOPS", "1")
    tag = uuid.uuid4().hex[:10]
    cleanup.append(tag)
    client = TestClient(app)
    headers = {"X-Forwarded-For": "203.0.113.77"}
    for _ in range(30):
        assert client.post(URL, json=_report(tag), headers=headers).status_code == 202
    refused = client.post(URL, json=_report(tag), headers=headers)
    assert refused.status_code == 429 and refused.json()["detail"]["code"] == "RATE_LIMITED"
    assert int(refused.headers["Retry-After"]) > 0
    assert client.post(URL, json=_report(tag), headers={"X-Forwarded-For": "198.51.100.9"}).status_code == 202
