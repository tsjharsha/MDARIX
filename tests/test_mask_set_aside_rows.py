"""scripts/mask_set_aside_rows.py masks the set-aside rows stored before 0.10.62: a dry run by default, idempotent,
counts per organization, identifiers kept (J7)."""

import uuid
from datetime import datetime, timezone

import pytest

from backend.app.db.models.foundation import AuditEvent, Tenant
from backend.app.db.models.ingestion import ImportQuarantineRow
from backend.app.db.session import SessionLocal
from backend.app.db.tenant_scope import bind_system
from scripts.mask_set_aside_rows import mask_rows

pytestmark = pytest.mark.db

AS_SENT = {
    "complaint_id": "OLD-1",
    "serial_number": "9845012345",
    "description": "Mr. John Smith called on 98450 12345: the pump stopped",
}


@pytest.fixture
def stored_before():
    with SessionLocal() as db:
        bind_system(db, "test: a set-aside row stored before 0.10.62")
        tenant = db.query(Tenant).filter(Tenant.tenant_key == "ACME_CARE_SYNTHETIC").first() or db.query(Tenant).first()
        row = ImportQuarantineRow(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            import_ref=uuid.uuid4(),
            entity="complaints",
            source="CSV_IMPORT",
            line=4,
            row=dict(AS_SENT),
            problems=["product_id: not found"],
            harm_words=[],
            status="OPEN",
            created_at=datetime.now(timezone.utc),
        )
        db.add(row)
        db.commit()
        ids = (tenant.id, row.id)
    yield ids
    with SessionLocal() as db:
        bind_system(db, "test: clean up")
        db.query(ImportQuarantineRow).filter(ImportQuarantineRow.id == ids[1]).delete()
        db.commit()


def _stored(row_id):
    with SessionLocal() as db:
        bind_system(db, "test: read")
        return db.get(ImportQuarantineRow, row_id).row


def _audits(tenant_id) -> list:
    with SessionLocal() as db:
        bind_system(db, "test: read the audit")
        rows = db.query(AuditEvent).filter(
            AuditEvent.tenant_id == tenant_id, AuditEvent.action == "SET_ASIDE_ROWS_MASKED"
        )
        return [row.details for row in rows]


def test_a_dry_run_counts_and_changes_nothing_then_apply_masks_once(stored_before):
    tenant_id, row_id = stored_before
    audits = len(_audits(tenant_id))
    with SessionLocal() as db:
        dry = mask_rows(db, apply=False, tenant_ids={tenant_id})
    (counts,) = dry.values()
    assert counts["changed"] >= 1 and _stored(row_id) == AS_SENT
    with SessionLocal() as db:
        applied = mask_rows(db, apply=True, tenant_ids={tenant_id})
    assert list(applied.values())[0]["changed"] == counts["changed"]
    stored = _stored(row_id)
    assert stored["description"] == "[PERSON] called on [PHONE]: the pump stopped"
    assert stored["complaint_id"] == "OLD-1" and stored["serial_number"] == "9845012345"
    with SessionLocal() as db:
        again = mask_rows(db, apply=True, tenant_ids={tenant_id})
    assert list(again.values())[0]["changed"] == 0 and _stored(row_id) == stored
    written = _audits(tenant_id)
    assert len(written) == audits + 1 and "John" not in str(written)
