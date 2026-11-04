"""Identity context comes only from the durable session and the persisted user."""

import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from starlette.requests import Request

from auth.durable import hash_token, new_session, new_token
from backend.app.access import authz
from backend.app.db.models.foundation import Tenant
from backend.app.db.models.stage2 import AuthSession
from backend.app.db.session import SessionLocal
from backend.app.main import app
from tests.conftest import _ensure_legacy_user


def _legacy():
    db = SessionLocal()
    try:
        tenant = db.query(Tenant).filter(Tenant.tenant_key == "ACME_CARE_SYNTHETIC").first() or db.query(Tenant).first()
        user = _ensure_legacy_user(db, tenant)
        return user.id, user.tenant_id, user.username, user.role
    finally:
        db.close()


def _client(token: str) -> TestClient:
    client = TestClient(app)
    client.cookies.set("mdarix_session", token)
    return client


@pytest.mark.db
def test_context_uses_the_persisted_user():
    user_id, tenant_id, email, role = _legacy()
    db = SessionLocal()
    try:
        token = new_session(db, user_id, tenant_id)
    finally:
        db.close()
    result = _client(token).get("/api/v1/me/context")
    assert result.status_code == 200, result.text
    body = result.json()
    assert body["user_id"] == str(user_id)
    assert body["tenant_id"] == str(tenant_id)
    assert body["email"] == email


def test_context_requires_authentication():
    response = TestClient(app).get("/api/v1/me/context")
    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "UNAUTHENTICATED"


@pytest.mark.db
def test_a_session_for_another_tenant_than_the_user_is_refused():
    user_id, _tenant_id, _email, _role = _legacy()
    db = SessionLocal()
    try:
        other_tenant = db.query(Tenant).filter(Tenant.id != _tenant_id).first()
        assert other_tenant is not None
        token = new_token()
        now = datetime.now(timezone.utc)
        db.add(
            AuthSession(
                session_hash=hash_token(token),
                user_id=user_id,
                tenant_id=other_tenant.id,
                expires_at=now + timedelta(hours=1),
                created_at=now,
                last_seen_at=now,
            )
        )
        db.commit()
    finally:
        db.close()
    response = _client(token).get("/api/v1/me/context")
    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "UNAUTHENTICATED"


@pytest.mark.db
def test_active_role_rejects_an_unassigned_role():
    user_id, tenant_id, _email, role = _legacy()
    db = SessionLocal()
    try:
        token = new_session(db, user_id, tenant_id)
    finally:
        db.close()
    other = "Viewer" if role != "Viewer" else "Approver"
    response = _client(token).post("/api/v1/me/active-role", json={"role": other})
    assert response.status_code == 403
    assert response.json()["detail"]["code"] == "ROLE_NOT_ASSIGNED"


def test_the_removed_tenant_switch_endpoint_is_gone():
    assert TestClient(app).post("/api/v1/me/tenant-context", json={"tenant_id": str(uuid.uuid4())}).status_code in {
        404,
        405,
    }


def _request() -> Request:
    return Request({"type": "http", "method": "GET", "path": "/", "headers": [], "query_string": b""})


def _user(role: str):
    return SimpleNamespace(
        id="user-a", tenant_id="tenant-a", username="user-a@example.invalid", role=role, status="ACTIVE"
    )


def test_administrator_gate_rejects_viewer(monkeypatch):
    monkeypatch.setattr(authz, "_authenticated_user", lambda request, db: _user("Viewer"))
    with pytest.raises(HTTPException) as error:
        authz._require_administrator(_request(), None)
    assert error.value.status_code == 403
    assert error.value.detail["code"] == "ADMINISTRATOR_REQUIRED"


def test_administrator_gate_accepts_administrator(monkeypatch):
    admin = _user("Administrator")
    monkeypatch.setattr(authz, "_authenticated_user", lambda request, db: admin)
    assert authz._require_administrator(_request(), None) is admin
