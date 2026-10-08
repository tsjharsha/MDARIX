"""Support access: neither the platform administrator who requested it nor the one who would receive it approves it.

A grant records who asked for it (md35). Before that, the requester could approve a grant made for a colleague, so
two platform administrators could give each other access to a customer's records with no third person involved.
"""

import secrets
import uuid
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient

from auth.durable import persist_session
from auth.service import _hash
from backend.app.auth_router import PLATFORM_TENANT_KEY
from backend.app.db.models.foundation import AuthUser, Tenant, TenantMembership
from backend.app.db.session import SessionLocal
from backend.app.db.tenant_scope import bind_system
from backend.app.main import app

SUPPORT_ACCESS = "/api/v1/platform-admin/support-access"


def _platform_admin() -> tuple[TestClient, uuid.UUID]:
    db = SessionLocal()
    try:
        bind_system(db, "test: add a platform administrator")
        tenant = db.query(Tenant).filter(Tenant.tenant_key == PLATFORM_TENANT_KEY).first() or db.query(Tenant).first()
        now = datetime.now(timezone.utc)
        user = AuthUser(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            username=f"support-sod-{uuid.uuid4().hex[:8]}@example.invalid",
            display_name="Platform Admin",
            company="MDARIX",
            password_hash=_hash("Support test 2026!"),
            role="PLATFORM_ADMIN",
            status="ACTIVE",
            email_verified=True,
            created_at=now,
            updated_at=now,
        )
        db.add(user)
        db.flush()
        db.add(
            TenantMembership(
                id=uuid.uuid4(),
                tenant_id=tenant.id,
                user_id=user.id,
                status="ACTIVE",
                is_default=True,
                created_at=now,
                updated_at=now,
            )
        )
        db.commit()
        token = secrets.token_urlsafe(32)
        persist_session(db, token, user.id, tenant.id)
        user_id = user.id
    finally:
        db.close()
    client = TestClient(app)
    client.cookies.set("mdarix_session", token)
    return client, user_id


def _customer_tenant(platform: TestClient) -> str:
    code = f"SOD{uuid.uuid4().hex[:6].upper()}"
    created = platform.post(
        "/api/v1/platform-admin/customers",
        json={"company_name": f"Support Access Test {code}", "tenant_code": code, "plan_code": "STARTER"},
    )
    assert created.status_code == 200, created.text
    return created.json()["id"]


def test_a_third_administrator_approves_support_access():
    requester, requester_id = _platform_admin()
    recipient, recipient_id = _platform_admin()
    third, third_id = _platform_admin()
    tenant = _customer_tenant(requester)
    starts_at = datetime.now(timezone.utc) + timedelta(minutes=5)
    created = requester.post(
        SUPPORT_ACCESS,
        json={
            "tenant_id": tenant,
            "platform_user_id": str(recipient_id),
            "scope": {"read": ["integration-runs"]},
            "reason": "Investigate the customer's failed synchronization",
            "starts_at": starts_at.isoformat(),
            "expires_at": (starts_at + timedelta(hours=2)).isoformat(),
        },
    )
    assert created.status_code == 200, created.text
    grant = created.json()["id"]
    decision = {"reason": "Reviewed the request with the customer"}

    for client in (requester, recipient):
        refused = client.post(f"{SUPPORT_ACCESS}/{grant}/approve", json=decision)
        assert refused.status_code == 409, refused.text
        assert refused.json()["detail"]["code"] == "SUPPORT_ACCESS_SOD"
    approved = third.post(f"{SUPPORT_ACCESS}/{grant}/approve", json=decision)
    assert approved.status_code == 200, approved.text
    assert approved.json()["approved_by"] == str(third_id)

    listed = next(item for item in third.get(SUPPORT_ACCESS).json()["items"] if item["id"] == grant)
    assert listed["requested_by"] == str(requester_id)
    assert listed["platform_user_id"] == str(recipient_id)
    assert listed["approved_by"] == str(third_id)
    assert listed["status"] == "APPROVED"
