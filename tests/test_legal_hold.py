"""Legal hold (backend/app/legal_hold_api.py): while set, nothing of the organization is purged, erased or retired."""

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from backend.app.db.models.foundation import AuditEvent, AuthUser, Product, Tenant
from backend.app.db.models.stage2 import SubscriptionLifecycle
from backend.app.db.session import SessionLocal
from backend.app.db.tenant_scope import bind_system
from backend.app.tenant_purge import PurgeFailed, complete_pending_purges, purge_tenant, reapply_erasures
from backend.app.trial import retention
from object_storage.service import ObjectStorageService
from tests.conftest import authenticated_client
from tests.test_tenant_data import (
    PURGE_BODY,
    BrokenStorage,
    _count,
    _set_status,
    make_organization,
    use_local_storage,
)


@pytest.fixture(autouse=True)
def storage_root(monkeypatch, tmp_path):
    return use_local_storage(monkeypatch, tmp_path)


@pytest.fixture
def platform():
    return authenticated_client()


@pytest.fixture
def organization(platform):
    return make_organization(platform)


HOLD = {"hold": True, "reason": "Recall investigation REF-2026-17: preserve all records (regulator letter 2026-10-01)"}


def _hold_url(tenant_id) -> str:
    return f"/api/v1/platform-admin/tenants/{tenant_id}/legal-hold"


def _set_hold(tenant_id, hold: bool) -> None:
    db = SessionLocal()
    bind_system(db, "test")
    tenant = db.get(Tenant, tenant_id)
    tenant.legal_hold = hold
    tenant.legal_hold_reason = HOLD["reason"] if hold else None
    tenant.legal_hold_set_at = datetime.now(timezone.utc) if hold else None
    db.commit()
    db.close()


def test_a_platform_administrator_sets_and_clears_a_hold_with_an_audited_reason(platform, organization):
    tenant_id = organization["tenant_id"]
    assert platform.get(_hold_url(tenant_id)).json()["legal_hold"] is False
    # Clearing a hold that is not set is refused, so no misleading LEGAL_HOLD_CLEARED record is written.
    cleared = platform.put(_hold_url(tenant_id), json={**HOLD, "hold": False})
    assert cleared.status_code == 409 and cleared.json()["detail"]["code"] == "LEGAL_HOLD_NOT_SET"
    assert platform.put(_hold_url(tenant_id), json={"hold": True, "reason": "short"}).status_code == 422

    response = platform.put(_hold_url(tenant_id), json=HOLD)
    assert response.status_code == 200, response.text
    state = response.json()
    assert state["legal_hold"] is True and state["legal_hold_reason"] == HOLD["reason"]
    assert state["legal_hold_set_at"] and state["legal_hold_set_by"]
    assert platform.get(_hold_url(tenant_id)).json()["legal_hold"] is True

    release = {"hold": False, "reason": "Regulator closed REF-2026-17 on 2026-12-01; normal retention resumes"}
    assert platform.put(_hold_url(tenant_id), json=release).status_code == 200
    db = SessionLocal()
    bind_system(db, "test")
    try:
        events = (
            db.query(AuditEvent)
            .filter(AuditEvent.tenant_id == tenant_id, AuditEvent.action.like("LEGAL_HOLD_%"))
            .order_by(AuditEvent.chain_seq)
            .all()
        )
        assert [(event.action, event.reason) for event in events] == [
            ("LEGAL_HOLD_SET", HOLD["reason"]),
            ("LEGAL_HOLD_CLEARED", release["reason"]),
        ]
        assert events[1].details["previous_reason"] == HOLD["reason"]
        assert db.get(Tenant, tenant_id).legal_hold is False
    finally:
        db.close()


def test_only_a_fully_signed_in_platform_administrator_may_set_a_hold(platform, organization, monkeypatch):
    from tests.test_business_permissions import _client_with_role

    tenant_id = organization["tenant_id"]
    customer_admin = _client_with_role("CUSTOMER_ADMIN")
    assert customer_admin.put(_hold_url(tenant_id), json=HOLD).status_code in (401, 403)
    # Where administrators must use an authenticator, one who has not enrolled cannot set a hold.
    monkeypatch.setenv("MDARIX_REQUIRE_MFA_ROLES", "PLATFORM_ADMIN")
    assert platform.put(_hold_url(tenant_id), json=HOLD).status_code == 403
    assert platform.get(_hold_url(tenant_id)).json()["legal_hold"] is False


def test_a_hold_stops_the_purge_and_the_erasure_and_records_the_refusal(platform, organization):
    tenant_id, user_id = organization["tenant_id"], organization["user_id"]
    _set_status(tenant_id, "SUSPENDED")
    assert platform.put(_hold_url(tenant_id), json=HOLD).status_code == 200

    body = {**PURGE_BODY, "confirm_tenant_key": organization["tenant_key"], "export_waiver_reason": "Not needed here"}
    refused = platform.post(f"/api/v1/platform-admin/tenants/{tenant_id}/purge", json=body)
    assert refused.status_code == 409 and refused.json()["detail"]["code"] == "LEGAL_HOLD"
    assert _count(AuditEvent, tenant_id=tenant_id, action="TENANT_PURGE_REFUSED_LEGAL_HOLD") == 1
    db = SessionLocal()
    try:
        with pytest.raises(PurgeFailed, match="LEGAL_HOLD"):
            purge_tenant(db, tenant_id, "test", reason="Direct call must be refused too")
    finally:
        db.close()

    db = SessionLocal()
    bind_system(db, "test")
    db.get(AuthUser, user_id).status = "OFFBOARDED"
    db.commit()
    db.close()
    erase = platform.post(f"/api/v1/platform-admin/users/{user_id}/erase", json={"reason": "Request from the person"})
    assert erase.status_code == 409
    db = SessionLocal()
    bind_system(db, "test")
    try:
        assert db.get(AuthUser, user_id).display_name == "Pat Person"
        assert db.get(Tenant, tenant_id).status == "SUSPENDED"
    finally:
        db.close()
    assert _count(Product, tenant_id=tenant_id) == 1
    assert ObjectStorageService().list_tenant_objects(str(tenant_id)) != []


def test_a_hold_set_on_an_unfinished_purge_preserves_what_is_left(organization, monkeypatch):
    monkeypatch.setattr("backend.app.alerts.send_alert", lambda subject, body: {})
    tenant_id = organization["tenant_id"]
    _set_status(tenant_id, "SUSPENDED")
    db = SessionLocal()
    try:
        first = purge_tenant(db, tenant_id, "test", reason="Files step fails", storage=BrokenStorage())
    finally:
        db.close()
    assert first["status"] == "PURGING"
    _set_hold(tenant_id, True)
    db = SessionLocal()
    try:
        summary = complete_pending_purges(db, "test", tenant_ids=[tenant_id])
        restored = reapply_erasures(db, "test", tenant_ids=[tenant_id])
    finally:
        db.close()
    assert [item["why"] for item in summary["skipped"]] == ["LEGAL_HOLD"] and summary["archived"] == []
    assert restored["reapplied"] == [] and restored["failed"] == []
    assert ObjectStorageService().list_tenant_objects(str(tenant_id)) != []
    _set_hold(tenant_id, False)
    db = SessionLocal()
    try:
        assert [
            item["tenant_id"] for item in complete_pending_purges(db, "test", tenant_ids=[tenant_id])["archived"]
        ] == [str(tenant_id)]
    finally:
        db.close()


def test_trial_retention_skips_a_trial_under_hold_and_says_so(monkeypatch):
    from tests.test_free_trial import _approved_trial_client

    _user, approval, _email = _approved_trial_client()
    tenant_id = uuid.UUID(approval["tenant_id"])
    db = SessionLocal()
    bind_system(db, "test")
    db.query(SubscriptionLifecycle).filter(SubscriptionLifecycle.tenant_id == tenant_id).one().expires_at = (
        datetime.now(timezone.utc) - timedelta(days=31)
    )
    db.commit()
    db.close()
    _set_hold(tenant_id, True)
    try:
        db = SessionLocal()
        bind_system(db, "test")
        try:
            due = [trial for trial in retention.trials_due(db) if trial["tenant_id"] == str(tenant_id)]
        finally:
            db.close()
        assert len(due) == 1 and due[0]["legal_hold"] is True
        # Only this trial is offered to the run, so other tests' trials in the shared database are not touched.
        monkeypatch.setattr(retention, "trials_due", lambda db, now=None: due)
        db = SessionLocal()
        try:
            result = retention.run_retention(db, "test")
        finally:
            db.close()
        assert result["purged"] == 0 and [item["why"] for item in result["skipped"]] == ["LEGAL_HOLD"]
        assert _count(AuditEvent, tenant_id=tenant_id, action="TRIAL_RETENTION_SKIPPED_LEGAL_HOLD") == 1
        assert _count(Product, tenant_id=tenant_id) > 0
    finally:
        # Leave no trial business data behind for tests that count rows across the database.
        _set_hold(tenant_id, False)
        db = SessionLocal()
        try:
            retention.purge_trial(db, tenant_id, "test")
        finally:
            db.close()
    assert _count(Product, tenant_id=tenant_id) == 0
