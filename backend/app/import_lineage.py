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
