"""The AcmeCare demo workspace: its own tenant with a curated story, a named team per role, and a reset."""

import time
import uuid
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from backend.app import demo_story as story
from backend.app.db.models.customer_lifecycle import TenantDataPlane
from backend.app.db.models.foundation import AuthUser, Decision, Investigation, Product, Tenant, TenantMembership
from backend.app.db.session import SessionLocal
from backend.app.demo_workspace import (
    DEMO_TEAM,
    DEMO_TENANT_KEY,
    LEGACY_DEMO_TENANT_KEY,
    DemoWorkspaceError,
    reset_demo,
    setup_demo,
    status,
)
from backend.app.main import app

PASSWORD = "Demo workspace test 2026!"
STORY = {
    "products": len(story.PRODUCTS),
    "complaints": len(story.COMPLAINTS),
    "investigations": len(story.INVESTIGATIONS),
    "evidence": sum(len(records) for records in story.EVIDENCE.values()),
    "changes": len(story.CHANGES),
    "suppliers": len(story.SUPPLIERS),
}


def _golden_products() -> int:
    db = SessionLocal()
    try:
        golden = db.query(Tenant).filter(Tenant.tenant_key == LEGACY_DEMO_TENANT_KEY).one()
        return db.query(Product).filter(Product.tenant_id == golden.id).count()
    finally:
        db.close()


@pytest.fixture(scope="module")
def demo():
    golden_before = _golden_products()
    db = SessionLocal()
    try:
        first = setup_demo(db, PASSWORD)
        second = setup_demo(db, PASSWORD)
        yield {"first": first, "second": second, "golden_before": golden_before}
    finally:
        db.close()


def _signin(email: str) -> TestClient:
    client = TestClient(app)
    response = client.post("/api/v1/auth/signin", json={"email": email, "password": PASSWORD})
    assert response.status_code == 200, response.text
    return client


def test_setup_creates_its_own_tenant_and_is_idempotent(demo):
    assert demo["second"]["created"] == [] and demo["second"]["moved"] == []
    db = SessionLocal()
    try:
        tenant = db.query(Tenant).filter(Tenant.tenant_key == DEMO_TENANT_KEY).one()
        assert tenant.tenant_key != LEGACY_DEMO_TENANT_KEY
        assert db.query(TenantDataPlane).filter(TenantDataPlane.tenant_id == tenant.id).one().status == "ACTIVE"
        for role, email, _ in DEMO_TEAM:
            user = db.query(AuthUser).filter(AuthUser.username == email).one()
            assert (user.tenant_id, user.role, user.status) == (tenant.id, role, "ACTIVE")
        assert status(db)["plan"] == "R1_GOVERNANCE_DEMO"
    finally:
        db.close()


def test_the_golden_evaluation_tenant_is_never_touched(demo):
    assert _golden_products() == demo["golden_before"]
    db = SessionLocal()
    try:
        golden = db.query(Tenant).filter(Tenant.tenant_key == LEGACY_DEMO_TENANT_KEY).one()
        demo_users = [email for _, email, _ in DEMO_TEAM]
        assert (
            db.query(AuthUser).filter(AuthUser.tenant_id == golden.id, AuthUser.username.in_(demo_users)).count() == 0
        )
    finally:
        db.close()


def test_the_story_is_curated_and_current(demo):
    db = SessionLocal()
    try:
        assert status(db)["records"] == STORY
        tenant = db.query(Tenant).filter(Tenant.tenant_key == DEMO_TENANT_KEY).one()
        cases = db.query(Investigation).filter(Investigation.tenant_id == tenant.id).all()
        assert {case.investigation_identifier for case in cases} == {item[0] for item in story.INVESTIGATIONS}
        # Dated relative to today, so recent views are never empty.
        newest = max(case.opened_at for case in cases)
        assert (datetime.now(timezone.utc) - newest).days <= 60
    finally:
        db.close()


def test_setup_refuses_a_weak_password():
    db = SessionLocal()
    try:
        with pytest.raises(DemoWorkspaceError):
            setup_demo(db, "short")
    finally:
        db.close()


def test_a_demo_account_left_in_the_golden_tenant_is_retired_and_recreated(demo):
    email = "viewer@acmecare-demo.invalid"
    db = SessionLocal()
    try:
        golden = db.query(Tenant).filter(Tenant.tenant_key == LEGACY_DEMO_TENANT_KEY).one()
        # An old-style demo account: the address lives in the golden tenant.
        current = db.query(AuthUser).filter(AuthUser.username == email).one()
        current.username = f"parked-{uuid.uuid4().hex[:8]}-{email}"
        now = datetime.now(timezone.utc)
        old = AuthUser(
            id=uuid.uuid4(),
            tenant_id=golden.id,
            username=email,
            display_name="Old demo viewer",
            company="Test",
            password_hash=current.password_hash,
            role="Viewer",
            status="ACTIVE",
            email_verified=True,
            created_at=now,
            updated_at=now,
        )
        db.add(old)
        db.flush()
        db.add(
            TenantMembership(
                id=uuid.uuid4(),
                tenant_id=golden.id,
                user_id=old.id,
                status="ACTIVE",
                is_default=True,
                created_at=now,
                updated_at=now,
            )
        )
        db.commit()
        result = setup_demo(db, PASSWORD)
        assert result["moved"] == [email]
        db.expire_all()
        tenant = db.query(Tenant).filter(Tenant.tenant_key == DEMO_TENANT_KEY).one()
        assert db.query(AuthUser).filter(AuthUser.username == email).one().tenant_id == tenant.id
        retired = db.query(AuthUser).filter(AuthUser.id == old.id).one()
        assert retired.status == "INACTIVE" and retired.username.startswith("retired-")
        assert db.query(TenantMembership).filter_by(tenant_id=golden.id, user_id=old.id).one().status == "INACTIVE"
    finally:
        db.close()


def test_a_user_of_another_tenant_is_never_moved(demo):
    email = "reviewer@acmecare-demo.invalid"
    db = SessionLocal()
    try:
        tenant = db.query(Tenant).filter(Tenant.tenant_key == DEMO_TENANT_KEY).one()
        other = (
            db.query(Tenant)
            .filter(Tenant.tenant_key.notin_([DEMO_TENANT_KEY, LEGACY_DEMO_TENANT_KEY]))
            .order_by(Tenant.tenant_key)
            .first()
        )
        # The address belongs to a user of an unrelated tenant.
        current = db.query(AuthUser).filter(AuthUser.username == email).one()
        parked = f"parked-{uuid.uuid4().hex[:8]}-{email}"
        current.username = parked
        now = datetime.now(timezone.utc)
        foreign = AuthUser(
            id=uuid.uuid4(),
            tenant_id=other.id,
            username=email,
            display_name="Someone else",
            company="Other",
            password_hash=current.password_hash,
            role="Viewer",
            status="ACTIVE",
            email_verified=True,
            created_at=now,
            updated_at=now,
        )
        db.add(foreign)
        db.commit()
        try:
            with pytest.raises(DemoWorkspaceError):
                setup_demo(db, PASSWORD)
            db.rollback()
            assert db.query(AuthUser).filter(AuthUser.id == foreign.id).one().tenant_id == other.id
        finally:
            db.rollback()
            db.query(AuthUser).filter(AuthUser.id == foreign.id).delete()
            db.query(AuthUser).filter(AuthUser.username == parked).one().username = email
            db.commit()
            assert db.query(AuthUser).filter(AuthUser.username == email).one().tenant_id == tenant.id
    finally:
        db.close()


def test_each_demo_role_signs_in_and_sees_the_story(demo):
    for role, email, _ in DEMO_TEAM:
        counts = _signin(email).get("/api/v1/analytics/command-center").json()["counts"]
        assert (counts["products"], counts["investigations"]) == (STORY["products"], STORY["investigations"]), role


def test_the_demo_viewer_is_read_only(demo):
    viewer = _signin("viewer@acmecare-demo.invalid")
    assert viewer.get("/api/v1/session/context").json()["business_permissions"] == []
    investigation = viewer.get("/api/v1/analytics/investigations").json()["investigations"][0]["id"]
    refused = viewer.post(f"/api/v1/investigations/{investigation}/analysis", json={})
    assert refused.status_code == 403 and refused.json()["detail"]["code"] == "PERMISSION_DENIED"


def test_reset_removes_what_the_demo_created_and_restores_the_story(demo):
    golden_before = _golden_products()
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
    assert _golden_products() == golden_before
    # The team survives a reset and can still sign in.
    assert _signin("investigator@acmecare-demo.invalid").get("/api/v1/auth/session").status_code == 200
