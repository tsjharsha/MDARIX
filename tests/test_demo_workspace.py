"""The AcmeCare demo workspace: a named team per role, the full story visible, and a reset that restores it."""

import time
import uuid
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from backend.app.db.models.customer_lifecycle import TenantDataPlane
from backend.app.db.models.foundation import AuthUser, Decision, Investigation, Tenant
from backend.app.db.session import SessionLocal
from backend.app.demo_workspace import DEMO_TEAM, DEMO_TENANT_KEY, DemoWorkspaceError, reset_demo, setup_demo, status
from backend.app.main import app

PASSWORD = "Demo workspace test 2026!"
STORY = {"products": 5, "complaints": 135, "investigations": 19, "evidence": 47, "changes": 16, "suppliers": 8}


@pytest.fixture(scope="module")
def demo():
    db = SessionLocal()
    try:
        first = setup_demo(db, PASSWORD)
        second = setup_demo(db, PASSWORD)
        yield {"first": first, "second": second}
    finally:
        db.close()


def _signin(email: str) -> TestClient:
    client = TestClient(app)
    response = client.post("/api/v1/auth/signin", json={"email": email, "password": PASSWORD})
    assert response.status_code == 200, response.text
    return client


def test_setup_is_idempotent_and_registers_the_data_location(demo):
    assert demo["second"]["created"] == []
    assert len(demo["first"]["created"]) + len(demo["first"]["refreshed"]) == len(DEMO_TEAM)
    db = SessionLocal()
    try:
        tenant = db.query(Tenant).filter(Tenant.tenant_key == DEMO_TENANT_KEY).one()
        assert db.query(TenantDataPlane).filter(TenantDataPlane.tenant_id == tenant.id).one().status == "ACTIVE"
        for role, email, _ in DEMO_TEAM:
            user = db.query(AuthUser).filter(AuthUser.username == email).one()
            assert (user.tenant_id, user.role, user.status) == (tenant.id, role, "ACTIVE")
    finally:
        db.close()


def test_setup_refuses_a_weak_password():
    db = SessionLocal()
    try:
        with pytest.raises(DemoWorkspaceError):
            setup_demo(db, "short")
    finally:
        db.close()


def test_each_demo_role_signs_in_and_sees_the_story(demo):
    for role, email, _ in DEMO_TEAM:
        counts = _signin(email).get("/api/v1/analytics/command-center").json()["counts"]
        assert counts["products"] >= 5 and counts["investigations"] >= 19, (role, counts)


def test_the_demo_viewer_is_read_only(demo):
    viewer = _signin("viewer@acmecare-demo.invalid")
    investigation = viewer.get("/api/v1/analytics/investigations").json()["investigations"][0]["id"]
    refused = viewer.post(f"/api/v1/investigations/{investigation}/analysis", json={})
    assert refused.status_code == 403 and refused.json()["detail"]["code"] == "PERMISSION_DENIED"


def test_reset_removes_what_the_demo_created_and_restores_the_story(demo):
    db = SessionLocal()
    try:
        tenant = db.query(Tenant).filter(Tenant.tenant_key == DEMO_TENANT_KEY).one()
        investigation = db.query(Investigation).filter(Investigation.tenant_id == tenant.id).first()
        now = datetime.now(timezone.utc)
        decision_id = uuid.uuid4()
        db.add(
            Decision(
                id=decision_id,
                tenant_id=tenant.id,
                investigation_id=investigation.id,
                decision_identifier=f"DEMO-RUN-{decision_id.hex[:8]}",
                decision_type="INVESTIGATION_REVIEW",
                disposition="REQUIRES_REVIEW",
                rationale="Made during a demo",
                decision_status="REQUIRES_REVIEW",
                authorized_by_ref="leader@acmecare-demo.invalid",
                updated_at=now,
                decision_timestamp=now,
                created_at=now,
            )
        )
        db.commit()
        started = time.monotonic()
        result = reset_demo(db)
        assert time.monotonic() - started < 120
        assert db.query(Decision).filter(Decision.id == decision_id).first() is None
        assert result["records"] == STORY
        assert status(db)["data_location_registered"] is True
    finally:
        db.close()
    # The team survives a reset and can still sign in.
    assert _signin("investigator@acmecare-demo.invalid").get("/api/v1/auth/session").status_code == 200
