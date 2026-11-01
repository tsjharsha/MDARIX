"""Row lineage (R16): every row a workspace import writes carries the import it came in with and the mapping version
it was read under. The import's DATA_IMPORTED audit event holds the same ``import_ref`` with the run's counts.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from backend.app.db.models.ingestion import ImportLineage

REPROCESSED_MAPPING = "quarantine-correction"


def mapping_version(entity: str, columns: list[dict], date_format: str) -> str:
    """The template and the way this file's headers mapped onto it: the same headers give the same version."""
    digest = hashlib.sha256(json.dumps([entity, columns, date_format], sort_keys=True).encode()).hexdigest()
    return f"{entity}-template:{digest[:12]}"


def record_key(required: list[str], row: dict) -> str:
    """The record's identity in the file: its required identifier columns (``*_id`` and ``version``), in order."""
    keys = [column for column in required if column.endswith("_id") or column == "version"]
    return ":".join(str(row.get(column, "")) for column in keys)[:400]


def write(
    db: Session, tenant_id, import_ref: uuid.UUID, entity: str, required: list[str], rows, version: str, source: str
) -> None:
    now = datetime.now(timezone.utc)
    for line, row in rows:
        db.add(
            ImportLineage(
                tenant_id=tenant_id,
                import_ref=import_ref,
                entity=entity,
                record_key=record_key(required, row),
                line=line,
                mapping_version=version,
                source=source,
                created_at=now,
            )
        )


def of_record(db: Session, tenant_id, entity: str, key: str) -> list[dict]:
    """The imports that brought this record in, newest first."""
    items = (
        db.query(ImportLineage)
        .filter(ImportLineage.tenant_id == tenant_id, ImportLineage.entity == entity, ImportLineage.record_key == key)
        .order_by(ImportLineage.created_at.desc())
        .limit(100)
        .all()
    )
    return [
        {
            "import_ref": str(item.import_ref),
            "line": item.line,
            "mapping_version": item.mapping_version,
            "source": item.source,
            "imported_at": item.created_at.isoformat(),
        }
        for item in items
    ]


def present(db: Session, tenant_id, refs: list[str]) -> set[str]:
    """Which of these imports still have lineage rows (a sample run's go with the sample data)."""
    if not refs:
        return set()
    rows = (
        db.query(ImportLineage.import_ref)
        .filter(ImportLineage.tenant_id == tenant_id, ImportLineage.import_ref.in_([uuid.UUID(ref) for ref in refs]))
        .distinct()
        .all()
    )
    return {str(ref) for (ref,) in rows}


def key_of(db: Session, tenant_id, entity: str, record_id: uuid.UUID) -> tuple[str, str | None]:
    """A product's, lot's or complaint's lineage key (``record_key``, from its own identifiers) and the system it came
    from; 404 when the organization has no such record."""
    from fastapi import HTTPException

    from backend.app.db.models.foundation import Complaint, LotBatch, Product, ProductVersion

    product = (Product.id == Complaint.product_id) & (Product.tenant_id == Complaint.tenant_id)
    if entity == "complaints":
        row = (
            db.query(Complaint.complaint_identifier, Product.product_identifier, Complaint.source_system)
            .join(Product, product)
            .filter(Complaint.tenant_id == tenant_id, Complaint.id == record_id)
            .first()
        )
    elif entity == "lots":
        row = (
            db.query(
                LotBatch.lot_identifier,
                Product.product_identifier,
                ProductVersion.version_identifier,
                LotBatch.source_system,
            )
            .join(
                ProductVersion,
                (ProductVersion.id == LotBatch.product_version_id) & (ProductVersion.tenant_id == LotBatch.tenant_id),
            )
            .join(Product, (Product.id == ProductVersion.product_id) & (Product.tenant_id == LotBatch.tenant_id))
            .filter(LotBatch.tenant_id == tenant_id, LotBatch.id == record_id)
            .first()
        )
    elif entity == "products":
        row = (
            db.query(Product.product_identifier, Product.source_system)
            .filter(Product.tenant_id == tenant_id, Product.id == record_id)
            .first()
        )
    else:
        raise HTTPException(404, detail={"code": "TEMPLATE_NOT_FOUND", "message": "Unknown template"})
    if row is None:
        raise HTTPException(404, detail={"code": "RECORD_NOT_FOUND", "message": "No such record"})
    *identifiers, source = row
    return ":".join(str(value or "") for value in identifiers)[:400], source
