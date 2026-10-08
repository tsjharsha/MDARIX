"""Postgres row-level security under the least-privilege runtime role (the role every API request uses)."""

import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import func, text
from sqlalchemy.exc import DBAPIError

from backend.app.db.models.foundation import Product, Tenant
from backend.app.db.session import RuntimeSessionLocal, SessionLocal, runtime_role_active
from backend.app.db.tenant_scope import bind_system, bind_tenant

pytestmark = pytest.mark.skipif(not runtime_role_active(), reason="MDARIX_DB_RUNTIME_USER is not configured")


def _tenants_with_products():
    owner = SessionLocal()
    try:
        rows = (
            owner.query(Product.tenant_id, func.count(Product.id))
            .group_by(Product.tenant_id)
            .order_by(func.count(Product.id).desc())
            .limit(2)
            .all()
        )
        total = owner.query(func.count(Product.id)).scalar()
    finally:
        owner.close()
    assert len(rows) == 2, "the test database needs products in two tenants"
    return rows, total


def test_the_runtime_role_cannot_bypass_row_level_security():
    runtime = RuntimeSessionLocal()
    try:
        flags = runtime.execute(text("SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname = current_user")).one()
        assert flags.rolsuper is False and flags.rolbypassrls is False
    finally:
        runtime.close()


def test_without_a_scope_no_tenant_rows_are_visible():
    runtime = RuntimeSessionLocal()
    try:
        assert runtime.query(func.count(Product.id)).scalar() == 0
    finally:
        runtime.close()


def test_a_tenant_sees_only_its_own_rows_across_commits():
    rows, _ = _tenants_with_products()
    tenant_a, count_a = rows[0]
    runtime = RuntimeSessionLocal()
    try:
        bind_tenant(runtime, tenant_a)
        assert runtime.query(func.count(Product.id)).scalar() == count_a
        assert {row.tenant_id for row in runtime.query(Product.tenant_id).distinct()} == {tenant_a}
        runtime.commit()  # the scope is re-applied to the next transaction
        assert runtime.query(func.count(Product.id)).scalar() == count_a
    finally:
        runtime.close()


def test_a_tenant_cannot_write_a_row_for_another_tenant():
    rows, _ = _tenants_with_products()
    (tenant_a, _), (tenant_b, _) = rows
    runtime = RuntimeSessionLocal()
    now = datetime.now(timezone.utc)
    try:
        bind_tenant(runtime, tenant_a)
        runtime.add(
            Product(
                id=uuid.uuid4(),
                tenant_id=tenant_b,
                product_identifier=f"RLS-{uuid.uuid4().hex[:8]}",
                name="Cross-tenant write",
                lifecycle_status="active",
                created_at=now,
                updated_at=now,
            )
        )
        with pytest.raises(DBAPIError):
            runtime.flush()
    finally:
        runtime.rollback()
        runtime.close()


def test_system_scope_sees_every_tenant_and_never_leaks_to_the_next_session():
    _, total = _tenants_with_products()
    runtime = RuntimeSessionLocal()
    try:
        bind_system(runtime, "test")
        assert runtime.query(func.count(Product.id)).scalar() == total
    finally:
        runtime.close()
    # The pooled connection is reused; the transaction-local scope must not carry over.
    fresh = RuntimeSessionLocal()
    try:
        assert fresh.query(func.count(Product.id)).scalar() == 0
        # The organizations table is protected too (md34): an unscoped session sees no organization at all.
        assert fresh.query(func.count(Tenant.id)).scalar() == 0
    finally:
        fresh.close()
