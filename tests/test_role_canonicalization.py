import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from backend.app.access.authz import _is_customer_admin, _is_platform_admin
from backend.app.access.permissions import (
    ALL,
    AI_RUN,
    DATA_EXPORT,
    RECORDS_WRITE,
    REGULATORY_APPROVE,
    normalize_role,
    permissions_for_role,
)
from backend.app.db.models.foundation import AuthUser, Tenant
from backend.app.db.session import SessionLocal
from backend.app.db.tenant_scope import bind_system
from backend.app.role_codes import canonical_stored_role


@pytest.mark.parametrize(
    "alias",
    ["Administrator", "Admin", "MDARIX Administrator", "platform-admin", "PLATFORM_ADMIN"],
)
def test_platform_administrator_aliases_resolve_to_one_role(alias):
    assert normalize_role(alias) == "PLATFORM_ADMIN"
    assert canonical_stored_role(alias) == "PLATFORM_ADMIN"
    assert permissions_for_role(alias) == ALL


@pytest.mark.parametrize("alias", ["Customer Admin", "customer-administrator", "CUSTOMER_ADMIN"])
def test_customer_administrator_aliases_resolve_to_one_role(alias):
    assert normalize_role(alias) == "CUSTOMER_ADMIN"
    assert canonical_stored_role(alias) == "CUSTOMER_ADMIN"
    # Investigator-level workspace rights, never regulatory approval.
    assert permissions_for_role(alias) == frozenset({RECORDS_WRITE, AI_RUN, DATA_EXPORT})
    assert REGULATORY_APPROVE not in permissions_for_role(alias)


def test_auth_user_model_persists_canonical_administrator_roles():
    platform = AuthUser(role="Administrator")
    customer = AuthUser(role="Customer Admin")
    assert platform.role == "PLATFORM_ADMIN"
    assert customer.role == "CUSTOMER_ADMIN"
    assert _is_platform_admin(platform)
    assert _is_customer_admin(customer)


def test_database_rejects_noncanonical_administrator_role():
    with SessionLocal() as db:
        bind_system(db, "test canonical administrator constraint")
        tenant = db.query(Tenant).order_by(Tenant.created_at).first()
        now = datetime.now(timezone.utc)
        with pytest.raises(DBAPIError):
            db.execute(
                text(
                    "INSERT INTO auth_users "
                    "(id, tenant_id, username, display_name, company, password_hash, role, status, "
                    "email_verified, mfa_required, created_at, updated_at) "
                    "VALUES (:id, :tenant, :username, 'Alias User', 'Test', 'not-used', "
                    "'Administrator', 'ACTIVE', true, false, :now, :now)"
                ),
                {
                    "id": uuid.uuid4(),
                    "tenant": tenant.id,
                    "username": f"role-alias-{uuid.uuid4()}@synthetic.invalid",
                    "now": now,
                },
            )
            db.flush()
        db.rollback()
