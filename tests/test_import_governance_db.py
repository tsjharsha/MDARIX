"""The database side of R14, R16, R17 and G2a, end to end in the service layer (no HTTP, no browser):

- an import with problem rows stores them in quarantine, writes lineage for the rows it accepts and balances its
  report against the file, including a row with too many values;
- a corrected quarantined row imports and closes, keeping its first import's lineage;
- quarantined rows that suggest harm list first;
- an IMDRF mapping proposed by one person and approved by another reaches ``approved_imdrf_codes``;
- another organization sees none of the first one's rows (row-level security).

Needs the PostgreSQL test database migrated to md52 or later.
"""

import uuid
from datetime import datetime, timezone

import pytest
from fastapi import HTTPException

from backend.app import import_lineage, import_quarantine
from backend.app import regulatory_reference as reference
from backend.app.db.models.ingestion import ImportLineage, ImportQuarantineRow
from backend.app.db.models.regulatory_reference import ImdrfCode, ImdrfCodeMapping
from backend.app.db.session import SessionLocal
from backend.app.db.tenant_scope import bind_system, bind_tenant
from backend.app.trial import imports
from tests.test_customer_admin_account_security import _tenant

pytestmark = pytest.mark.db

RELEASE = f"T{uuid.uuid4().hex[:8]}"


@pytest.fixture(scope="module")
def orgs():
    with SessionLocal() as db:
        bind_system(db, "test: import governance")
        first, second = _tenant(db, "GOVA"), _tenant(db, "GOVB")
        db.add(
            ImdrfCode(
                release=RELEASE,
                annex="A",
                code="A0101",
                term="Crack",
                loaded_at=datetime.now(timezone.utc),
            )
        )
        db.commit()
        return first.id, second.id


def _import(db, tenant_id, csv_text: str) -> dict:
    return imports.import_file(
        db, tenant_id, "products", csv_text.encode(), imports.WORKSPACE_POLICY, "ISO", True, False
    )


def test_an_import_quarantines_problem_rows_and_writes_lineage(orgs):
    tenant_id, _ = orgs
    raw = "product_id,product_name\nGOV-P1,Good pump\nGOV-P2,Pump with an extra, comma,more\n\n"
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        result = _import(db, tenant_id, raw)
        db.commit()
        ref = uuid.UUID(result["import_ref"])
        assert result["quality_report"]["rows_read"] == 2
        assert result["quality_report"]["rows_accepted"] == 1
        assert result["quality_report"]["rows_quarantined"] == 1
        assert result["quality_report"]["balanced"] is True
        lineage = db.query(ImportLineage).filter(ImportLineage.import_ref == ref).all()
        assert [(item.record_key, item.line) for item in lineage] == [("GOV-P1", 2)]
        stored = db.query(ImportQuarantineRow).filter(ImportQuarantineRow.import_ref == ref).one()
        assert stored.line == 3 and stored.status == "OPEN"
        assert import_lineage.of_record(db, tenant_id, "products", "GOV-P1")[0]["import_ref"] == str(ref)


def test_a_corrected_row_imports_and_keeps_its_first_lineage(orgs):
    tenant_id, _ = orgs
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        result = _import(db, tenant_id, "product_id,product_name\nGOV-P3,Fine\nGOV-P4,Bad, row,extra\n")
        db.commit()
        ref = uuid.UUID(result["import_ref"])
        row = db.query(ImportQuarantineRow).filter(ImportQuarantineRow.import_ref == ref).one()
        corrected = {"product_id": "GOV-P4", "product_name": "Bad row fixed"}
        import_quarantine.reprocess(
            db, tenant_id, row.id, corrected, imports.import_records, imports.WORKSPACE_POLICY, "tester"
        )
        db.commit()
        db.refresh(row)
        assert row.status == "REPROCESSED"
        history = import_lineage.of_record(db, tenant_id, "products", "GOV-P4")
        assert history[0]["import_ref"] == str(ref)
        assert history[0]["mapping_version"] == import_lineage.REPROCESSED_MAPPING
        with pytest.raises(HTTPException):
            import_quarantine.reprocess(
                db, tenant_id, row.id, corrected, imports.import_records, imports.WORKSPACE_POLICY, "tester"
            )


def test_harm_rows_list_first(orgs):
    tenant_id, _ = orgs
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        ref = uuid.uuid4()
        set_aside = [
            (2, {"complaint_id": "GOV-C1", "description": "display flicker"}, ["product_id: not found"]),
            (3, {"complaint_id": "GOV-C2", "description": "patient taken to hospital"}, ["product_id: not found"]),
        ]
        import_quarantine.store(
            db, tenant_id, ref, "complaints", "CSV_IMPORT", set_aside, imports._personal_data, imports._mask
        )
        db.commit()
        items = import_quarantine.listing(db, tenant_id, import_ref=ref)["items"]
        assert [item["line"] for item in items] == [3, 2]


def test_an_approved_mapping_reaches_worksheets_and_stays_in_its_organization(orgs):
    first, second = orgs
    with SessionLocal() as db, SessionLocal() as control:
        bind_tenant(db, first)
        bind_system(control, "test: read IMDRF codes")
        payload = {
            "customer_system": "problem_code",
            "customer_code": "PC-GOV",
            "release": RELEASE,
            "annex": "A",
            "imdrf_code": "A0101",
        }
        proposed = reference.propose_mapping(db, control, first, payload, "alice")
        db.commit()
        with pytest.raises(HTTPException):
            reference.propose_mapping(db, control, first, payload, "alice")  # the same link twice: 409
        db.rollback()
        reference.review_mapping(db, first, uuid.UUID(proposed["id"]), True, None, "bob")
        db.commit()
        assert reference.approved_imdrf_codes(db, first, "problem_code", "PC-GOV", RELEASE) == [("A", "A0101")]
    with SessionLocal() as other:
        bind_tenant(other, second)
        assert other.query(ImdrfCodeMapping).filter(ImdrfCodeMapping.customer_code == "PC-GOV").count() == 0
        assert other.query(ImportQuarantineRow).filter(ImportQuarantineRow.tenant_id == first).count() == 0
