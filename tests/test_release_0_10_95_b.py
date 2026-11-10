"""Hardening 0.10.95, run 2 (code-audit fixes 13-20) against the database."""

from __future__ import annotations

import uuid

import pytest

from backend.app import import_quarantine
from backend.app.db.models.ingestion import ImportQuarantineRow
from backend.app.db.session import SessionLocal
from backend.app.db.tenant_scope import bind_system, bind_tenant
from backend.app.trial import imports
from tests.test_customer_admin_account_security import _tenant

pytestmark = pytest.mark.db

# Two set-aside rows per template that share the first column and differ in the rest of the record's identity.
SAME_FIRST_COLUMN = {
    "products": [
        {"product_id": "P-1", "product_name": "Pump", "version": "Rev C"},
        {"product_id": "P-1", "product_name": "Pump", "version": "Rev D"},
    ],
    "bom": [
        {"product_id": "P-1", "version": "Rev D", "component_id": "C-1"},
        {"product_id": "P-1", "version": "Rev D", "component_id": "C-2"},
    ],
    "lot_genealogy": [
        {"lot_id": "L-1", "component_id": "C-1", "component_lot_id": "K-1"},
        {"lot_id": "L-1", "component_id": "C-1", "component_lot_id": "K-2"},
    ],
    "distribution": [
        {
            "lot_id": "L-1",
            "consignee": "Lakeside Hospital",
            "country": "IE",
            "quantity": "x",
            "ship_date": "2026-07-28",
        },
        {
            "lot_id": "L-1",
            "consignee": "Lakeside Hospital",
            "country": "IE",
            "quantity": "x",
            "ship_date": "2026-08-02",
        },
    ],
}


@pytest.fixture(scope="module")
def tenant_id():
    with SessionLocal() as db:
        bind_system(db, "test: hardening run 2")
        tenant = _tenant(db, "H95B")
        db.commit()
        return tenant.id


@pytest.mark.parametrize("entity", sorted(SAME_FIRST_COLUMN))
def test_a_later_import_closes_only_the_set_aside_row_of_the_record_it_wrote(tenant_id, entity):  # audit 13
    fixed, other = SAME_FIRST_COLUMN[entity]
    source = imports.WORKSPACE_POLICY.source
    columns = imports.identity_columns(entity)
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        ref = uuid.uuid4()
        import_quarantine.store(
            db, tenant_id, ref, entity, source, [(2, fixed, ["x"]), (3, other, ["x"])], imports.stored_value
        )
        db.flush()
        closed = import_quarantine.close_fixed(
            db, tenant_id, entity, columns, {import_quarantine.record_identity(fixed, columns)}, set(), "test", source
        )
        stored = {item.line: item for item in db.query(ImportQuarantineRow).filter_by(import_ref=ref)}
        assert closed == [str(stored[2].id)]
        assert (stored[2].status, stored[3].status) == ("REPROCESSED", "OPEN")
        db.rollback()
