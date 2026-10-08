"""The customer administrator's Plan screen sees when the subscription ends (GET /api/v1/admin/tenant/lifecycle)."""

import uuid
from datetime import datetime, timedelta, timezone

from backend.app.db.models.foundation import PlanDefinition
from backend.app.db.models.stage2 import SubscriptionLifecycle
from backend.app.db.session import SessionLocal
from backend.app.db.tenant_scope import bind_system
from tests.test_customer_admin_account_security import _client_for, _tenant, _user


def test_the_lifecycle_answer_carries_the_current_subscription_end():
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        bind_system(db, "test: a subscription for the Plan screen")
        tenant = _tenant(db, "PLAN")
        admin = _user(db, tenant, "CUSTOMER_ADMIN", "plan-admin")
        plan = db.query(PlanDefinition).first()
        for ends in (now + timedelta(days=30), now + timedelta(days=200)):  # the later one is the current one
            db.add(
                SubscriptionLifecycle(
                    id=uuid.uuid4(),
                    tenant_id=tenant.id,
                    plan_id=plan.id,
                    plan_version="1",
                    starts_at=now - timedelta(days=10),
                    expires_at=ends,
                    created_at=now,
                    updated_at=now,
                )
            )
        db.commit()
        client = _client_for(db, admin)
    answer = client.get("/api/v1/admin/tenant/lifecycle")
    assert answer.status_code == 200, answer.text
    subscription = answer.json()["subscription"]
    assert subscription["status"] == "ACTIVE" and subscription["grace_ends_at"] is None
    assert datetime.fromisoformat(subscription["expires_at"]).date() == (now + timedelta(days=200)).date()


def test_an_organization_without_a_subscription_gets_none():
    with SessionLocal() as db:
        bind_system(db, "test: an organization without a subscription")
        admin = _user(db, _tenant(db, "NOPLAN"), "CUSTOMER_ADMIN", "noplan-admin")
        db.commit()
        client = _client_for(db, admin)
    answer = client.get("/api/v1/admin/tenant/lifecycle")
    assert answer.status_code == 200 and answer.json()["subscription"] is None
