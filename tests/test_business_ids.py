"""Business identifiers assigned by the database (migration md26): format, scope, re-imports, gaps, immutability."""

import re
import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import text

from backend.app.db.models.customer_lifecycle import Customer
from backend.app.db.models.foundation import Product
from backend.app.db.session import SessionLocal
from backend.app.db.tenant_scope import bind_system
from tests.test_customer_admin_account_security import _tenant


@pytest.fixture
def db():
    session = SessionLocal()
    bind_system(session, "test: business identifiers")
    yield session
    session.rollback()
    session.close()


def _product(db, tenant_id, identifier: str) -> Product:
    now = datetime.now(timezone.utc)
    row = Product(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        product_identifier=identifier,
        name=f"Business id test {identifier}",
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    db.flush()
    return row


def test_a_new_customer_gets_the_next_global_number(db):
    first = _tenant(db, "BIZA")
    second = _tenant(db, "BIZB")
    customers = [db.get(Customer, first.customer_id), db.get(Customer, second.customer_id)]
    numbers = [int(row.business_id[4:]) for row in customers]
    assert all(re.fullmatch(r"CUST\d{6,}", row.business_id) for row in customers)
    assert numbers[1] == numbers[0] + 1
    assert re.fullmatch(r"TEN\d{6,}", first.business_id) and first.business_id != second.business_id


def test_each_organization_numbers_its_own_records_from_one(db):
    one, two = _tenant(db, "BIZ1"), _tenant(db, "BIZ2")
    assert _product(db, one.id, "P-1").business_id == "PROD000001"
    assert _product(db, one.id, "P-2").business_id == "PROD000002"
    assert _product(db, two.id, "P-1").business_id == "PROD000001"


def test_a_reimport_keeps_the_existing_number(db):
    organization = _tenant(db, "BIZRE")
    first = _product(db, organization.id, "P-RE")
    db.execute(
        text(
            "INSERT INTO products (id, tenant_id, product_identifier, name, created_at, updated_at) "
            "VALUES (gen_random_uuid(), :t, 'P-RE', 'Renamed', now(), now()) "
            "ON CONFLICT (tenant_id, product_identifier) DO UPDATE SET name = EXCLUDED.name"
        ),
        {"t": organization.id},
    )
    db.refresh(first)
    assert first.business_id == "PROD000001" and first.name == "Renamed"
    # The re-import consumed nothing: the next new product is number two.
    assert _product(db, organization.id, "P-NEW").business_id == "PROD000002"


def test_a_rolled_back_save_does_not_leave_a_gap(db):
    organization = _tenant(db, "BIZGAP")
    _product(db, organization.id, "P-A")
    db.commit()
    savepoint = db.begin_nested()
    _product(db, organization.id, "P-CANCELLED")
    savepoint.rollback()
    assert _product(db, organization.id, "P-B").business_id == "PROD000002"


def test_a_business_id_cannot_be_changed(db):
    organization = _tenant(db, "BIZIMM")
    product = _product(db, organization.id, "P-IMM")
    with pytest.raises(Exception, match="IMMUTABLE_IDENTIFIER"):
        db.execute(text("UPDATE products SET business_id = 'PROD999999' WHERE id = :id"), {"id": product.id})
        db.flush()


def test_a_copied_row_keeps_its_number_and_the_counter_moves_past_it(db):
    organization = _tenant(db, "BIZCOPY")
    db.execute(
        text(
            "INSERT INTO products (id, tenant_id, product_identifier, name, business_id, created_at, updated_at) "
            "VALUES (gen_random_uuid(), :t, 'P-COPY', 'Copied', 'PROD000040', now(), now())"
        ),
        {"t": organization.id},
    )
    assert _product(db, organization.id, "P-AFTER").business_id == "PROD000041"
