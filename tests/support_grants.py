"""Test helper: a customer-approved support grant (backend/app/support_access.py), for tests whose subject is
something a platform administrator does with an organization's data, not the approval itself (that is covered by
tests/test_support_access_customer_approval.py, through the real request, MDARIX approval and customer decision)."""

import uuid
from datetime import datetime, timedelta, timezone

from backend.app import support_access
from backend.app.db.models.customer_lifecycle import SupportAccessGrant
from backend.app.db.models.foundation import Tenant
from backend.app.db.session import SessionLocal
from backend.app.db.tenant_scope import bind_system

ALL_AREAS = tuple(support_access.AREAS)
LEGACY_PLATFORM_ADMIN = "legacy-test-auth@synthetic.invalid"  # tests/conftest.py authenticated_client()


def legacy_platform_admin_id() -> uuid.UUID:
    """The account tests/conftest.py authenticated_client() signs in as (same organization, same rule)."""
    from tests.conftest import _ensure_legacy_user

    with SessionLocal() as db:
        bind_system(db, "test: the legacy platform administrator")
        tenant = db.query(Tenant).filter(Tenant.tenant_key == "ACME_CARE_SYNTHETIC").first() or db.query(Tenant).first()
        user = _ensure_legacy_user(db, tenant)
        return user.id


def grant_for(client, tenant_id, **kwargs):
    """A customer-approved grant for whoever ``client`` is signed in as (see grant_support_access)."""
    user_id = client.get("/api/v1/session/context").json()["user_id"]
    return grant_support_access(tenant_id, user_id, **kwargs)


def grant_support_access(tenant_id, platform_user_id=None, *, areas=ALL_AREAS, write: bool = True, hours: int = 4):
    """An approved grant (for MDARIX and by the customer) for ``platform_user_id`` (the legacy platform
    administrator by default) on ``tenant_id``, inside its window now. Returns its id."""
    platform_user_id = platform_user_id or legacy_platform_admin_id()
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        bind_system(db, "test: a customer-approved support grant")
        row = SupportAccessGrant(
            id=uuid.uuid4(),
            tenant_id=uuid.UUID(str(tenant_id)),
            platform_user_id=uuid.UUID(str(platform_user_id)),
            scope={"areas": list(areas), "write": write},
            reason="Test: support access the customer approved",
            status=support_access.APPROVED,
            requested_by=uuid.uuid4(),
            approved_by=uuid.uuid4(),
            approved_at=now,
            customer_decided_by=uuid.uuid4(),
            customer_decided_at=now,
            customer_decision_reason="Test: approved by the customer",
            starts_at=now - timedelta(minutes=1),
            expires_at=now + timedelta(hours=hours),
            created_at=now,
            updated_at=now,
        )
        db.add(row)
        db.commit()
        return row.id
