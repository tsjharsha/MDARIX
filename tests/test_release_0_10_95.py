"""Hardening 0.10.95 (code-audit fixes 6-12) against the database."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from backend.app.db.models.authority_reports import ReportObligation
from backend.app.db.models.foundation import AuditEvent, AuthUser, PlanDefinition
from backend.app.db.models.stage2 import SubscriptionLifecycle
from backend.app.db.session import SessionLocal
from backend.app.db.tenant_scope import bind_system, bind_tenant
from tests.test_authority_reports_api import REPORTS, _ok, _start_rv06, trial  # noqa: F401 (trial is a fixture)
from tests.conftest import authenticated_client
from tests.support_grants import grant_support_access
from tests.test_platform_customer_admins import _activate, _add_admin
from tests.test_reporting_capa_api import PASSWORD as COLLEAGUE_PASSWORD
from tests.test_support_access_sod import _platform_admin

pytestmark = pytest.mark.db


def test_a_cancellation_committed_before_the_lock_refuses_the_approval(trial, monkeypatch):  # noqa: F811 (audit 6)
    from backend.app import governance_router

    user, colleague = trial["user"], trial["colleague"]
    detail = _start_rv06(trial)
    assert detail["state"] == "DRAFT", detail["state"]
    _ok(user.put(f"{REPORTS}/{detail['id']}/fields/MFR_REPORT", json={"value": "1234567-2026-00001"}))
    snapshot = _ok(user.post(f"{REPORTS}/{detail['id']}/snapshots"))["pending_snapshot"]
    real = governance_router.verify_signing_credentials

    def cancelled_meanwhile(*args, **kwargs):
        real(*args, **kwargs)
        # Another request cancels the report after the approval read it, before the approval takes the lock.
        with SessionLocal() as other:
            bind_tenant(other, trial["tenant_id"])
            row = other.get(ReportObligation, uuid.UUID(detail["id"]))
            row.state = "CANCELLED"
            other.commit()

    monkeypatch.setattr(governance_router, "verify_signing_credentials", cancelled_meanwhile)
    refused = colleague.post(
        f"{REPORTS}/{detail['id']}/snapshots/{snapshot['id']}/approve", json={"password": COLLEAGUE_PASSWORD}
    )
    assert refused.status_code == 409, refused.text
    with SessionLocal() as db:
        bind_tenant(db, trial["tenant_id"])
        assert db.get(ReportObligation, uuid.UUID(detail["id"])).state == "CANCELLED"


def _organization(platform, plan: str = "STARTER") -> str:
    code = f"H95{uuid.uuid4().hex[:6].upper()}"
    created = platform.post(
        "/api/v1/platform-admin/customers",
        json={"company_name": f"Hardening {code}", "tenant_code": code, "plan_code": plan, "customer_admin_limit": 5},
    )
    assert created.status_code == 200, created.text
    return created.json()["id"]


def _self_add(me, tenant_id: str):
    client, user_id = me
    with SessionLocal() as db:
        bind_system(db, "test: the platform administrator's own e-mail")
        email = db.get(AuthUser, user_id).username
    return client.post(
        f"/api/v1/platform-admin/tenants/{tenant_id}/customer-admins",
        json={"email": email, "display_name": "Platform Self", "reason": "Joining to help the customer"},
    )


def _refused(response, tenant_id: str) -> None:
    assert response.status_code == 403, response.text
    assert response.json()["detail"]["code"] == "CUSTOMER_APPROVAL_REQUIRED"
    with SessionLocal() as db:
        bind_system(db, "test: the refusal is in the organization's audit trail")
        assert (
            db.query(AuditEvent)
            .filter(AuditEvent.tenant_id == uuid.UUID(tenant_id), AuditEvent.action == "SUPPORT_ACCESS_REFUSED")
            .count()
            == 1
        )


def test_a_platform_admin_joins_an_administered_organization_only_with_people_access():  # audit 8
    platform, me = authenticated_client(), _platform_admin()
    unadministered = _organization(platform)
    assert _self_add(me, unadministered).status_code == 200  # nobody administers it yet: not asked
    tenant = _organization(platform)
    _activate(_add_admin(platform, tenant)["id"])
    _refused(_self_add(me, tenant), tenant)
    grant_support_access(tenant, me[1], areas=("PEOPLE",))
    assert _self_add(me, tenant).status_code == 200


def test_any_admin_a_platform_admin_adds_to_an_administered_organization_needs_people_access():  # owner (c)
    platform, me = authenticated_client(), _platform_admin()
    tenant = _organization(platform)
    _activate(_add_admin(me[0], tenant)["id"])  # a new customer: its first administrator is not asked
    colleague = {
        "email": f"ada-{uuid.uuid4().hex[:6]}@example.invalid",
        "display_name": "Ada",
        "reason": "Second admin",
    }
    _refused(me[0].post(f"/api/v1/platform-admin/tenants/{tenant}/customer-admins", json=colleague), tenant)
    grant_support_access(tenant, me[1], areas=("PEOPLE",))
    added = me[0].post(f"/api/v1/platform-admin/tenants/{tenant}/customer-admins", json=colleague)
    assert added.status_code == 200, added.text
    with SessionLocal() as db:
        bind_system(db, "test: the use is in the organization's audit trail")
        used = db.query(AuditEvent).filter(
            AuditEvent.tenant_id == uuid.UUID(tenant), AuditEvent.action == "SUPPORT_ACCESS_USED"
        )
        assert used.count() >= 1


def test_a_platform_admin_joins_a_trial_only_with_people_access():  # audit 8
    platform, me = authenticated_client(), _platform_admin()
    tenant = _organization(platform, "FREE_TRIAL")
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        bind_system(db, "test: a free-trial subscription")
        plan = db.query(PlanDefinition).filter(PlanDefinition.code == "FREE_TRIAL").first()
        db.add(
            SubscriptionLifecycle(
                id=uuid.uuid4(),
                tenant_id=uuid.UUID(tenant),
                plan_id=plan.id,
                plan_version="1",
                starts_at=now,
                expires_at=now + timedelta(days=30),
                created_at=now,
                updated_at=now,
            )
        )
        db.commit()
    _refused(_self_add(me, tenant), tenant)
    grant_support_access(tenant, me[1], areas=("PEOPLE",))
    assert _self_add(me, tenant).status_code == 200
