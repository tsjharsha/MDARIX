"""Export everything one organization stored, as one zip (data portability, offboarding, data-subject requests).

``request_export`` records the request and queues an outbox event; the background worker runs ``run_export``:
every table with rows for the organization (discovered from the database, so new tables are included) is written as
JSON Lines under ``data/``, every stored file under ``files/``, and ``manifest.json`` lists row counts, file counts,
a SHA-256 of each entry and the audit trail's verified head. Credentials are never exported: columns holding
passwords, secrets, tokens, recovery codes or encrypted keys are left out. The zip goes to encrypted object storage
and can be downloaded for ``EXPORT_DAYS`` days; the scheduler then deletes it (``expire_exports``).
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import tempfile
import uuid
import zipfile
from datetime import datetime, timedelta, timezone

from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.app.db.models.foundation import AuditEvent, Tenant
from backend.app.db.models.stage2 import OutboxEvent, TenantExport

logger = logging.getLogger("mdarix.tenant_export")

EXPORT_DAYS = 7
EVENT = "TENANT_EXPORT_REQUESTED"
# Columns never exported: credentials and secrets, even encrypted or hashed.
SECRET_COLUMN = re.compile(
    r"(?i)(password|secret|token|encrypted|api_key|private_key|recovery_hashes|session_hash|key_hash|code_hash|signing)"
)
SCHEMAS = ("public", "md_master")


class ExportInProgress(RuntimeError):
    pass


def request_export(db: Session, tenant_id, requested_by: str, reason: str) -> TenantExport:
    """Queue a full export (one at a time per organization). Does not commit."""
    tenant_id = uuid.UUID(str(tenant_id))
    busy = (
        db.query(TenantExport)
        .filter(TenantExport.tenant_id == tenant_id, TenantExport.status.in_(["QUEUED", "RUNNING"]))
        .first()
    )
    if busy is not None:
        raise ExportInProgress(str(busy.id))
    now = datetime.now(timezone.utc)
    row = TenantExport(
        id=uuid.uuid4(), tenant_id=tenant_id, requested_by=requested_by, reason=reason, status="QUEUED", created_at=now
    )
    db.add(row)
    db.flush()
    db.add(
        OutboxEvent(
            tenant_id=tenant_id,
            event_name=EVENT,
            aggregate_type="TenantExport",
            aggregate_id=row.id,
            payload={"export_id": str(row.id)},
            occurred_at=now,
        )
    )
    db.add(
        AuditEvent(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            actor_ref=requested_by,
            action="TENANT_EXPORT_REQUESTED",
            entity_type="TenantExport",
            entity_id=row.id,
            reason=reason,
            details={},
            created_at=now,
        )
    )
    return row


def describe(row: TenantExport) -> dict:
    return {
        "id": str(row.id),
        "status": row.status,
        "requested_by": row.requested_by,
        "reason": row.reason,
        "size_bytes": row.size_bytes,
        "sha256": row.sha256,
        "summary": row.summary,
        "error": row.error,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "completed_at": row.completed_at.isoformat() if row.completed_at else None,
        "expires_at": row.expires_at.isoformat() if row.expires_at else None,
    }


def _tables(db: Session) -> list[tuple[str, str]]:
    return [
        (schema, table)
        for schema, table in db.execute(
            text(
                "SELECT c.table_schema, c.table_name FROM information_schema.columns c "
                "JOIN information_schema.tables t ON t.table_schema = c.table_schema AND t.table_name = c.table_name "
                "WHERE c.column_name = 'tenant_id' AND t.table_type = 'BASE TABLE' AND c.table_schema = ANY(:schemas) "
                "ORDER BY 1, 2"
            ),
            {"schemas": list(SCHEMAS)},
        ).all()
    ]


def _write_tables(db: Session, archive: zipfile.ZipFile, tenant_id, prefix: str, manifest: dict) -> None:
    for schema, table in _tables(db):
        result = db.execute(
            text(f'SELECT * FROM "{schema}"."{table}" WHERE tenant_id = :tenant'), {"tenant": tenant_id}
        )
        columns = [name for name in result.keys() if not SECRET_COLUMN.search(name)]
        digest = hashlib.sha256()
        count = 0
        name = f"{prefix}{schema}.{table}.jsonl"
        with archive.open(name, "w") as handle:
            while rows := result.fetchmany(1000):
                for row in rows:
                    line = (json.dumps({key: row._mapping[key] for key in columns}, default=str) + "\n").encode()
                    handle.write(line)
                    digest.update(line)
                    count += 1
        # Tables from a dedicated data plane are listed as "plane:<schema>.<table>" beside the control database's.
        key = f"{schema}.{table}" if prefix == "data/" else f"plane:{schema}.{table}"
        manifest["tables"][key] = {"rows": count, "file": name, "sha256": digest.hexdigest()}


def run_export(export_id) -> dict:
    """Build the export's zip (worker). Raises on failure so the outbox retries; the row records the outcome."""
    from backend.app.audit_chain import verify_tenant_chain
    from backend.app.db.data_plane import open_tenant_data_session
    from backend.app.db.session import SessionLocal
    from backend.app.db.tenant_scope import bind_system
    from object_storage.service import ObjectStorageService

    db = SessionLocal()
    try:
        bind_system(db, f"tenant export {export_id}")
        row = db.get(TenantExport, uuid.UUID(str(export_id)))
        if row is None or row.status in {"READY", "EXPIRED"}:
            return {"status": row.status if row else "MISSING"}
        tenant_id = row.tenant_id
        tenant = db.get(Tenant, tenant_id)
        row.status, row.error = "RUNNING", None
        db.commit()
        storage = ObjectStorageService()
        now = datetime.now(timezone.utc)
        manifest: dict = {
            "organization": {"id": str(tenant_id), "name": tenant.display_name if tenant else None},
            "generated_at": now.isoformat(),
            "format": "JSON Lines per table; credentials and secrets are not included",
            "tables": {},
            "files": {},
        }
        bind_system(db, f"tenant export {export_id}")
        with tempfile.TemporaryFile() as buffer:
            with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                _write_tables(db, archive, tenant_id, "data/", manifest)
                # A dedicated data plane holds the business records in its own database.
                with open_tenant_data_session(tenant_id) as data:
                    if str(data.get_bind().url) != str(db.get_bind().url):
                        _write_tables(data, archive, tenant_id, "data/plane/", manifest)
                for key in storage.list_tenant_objects(str(tenant_id)):
                    relative = key.split("/", 1)[1]
                    if relative.startswith("exports/"):
                        continue
                    content = storage.get(str(tenant_id), key)
                    archive.writestr(f"files/{relative}", content)
                    manifest["files"][relative] = {"bytes": len(content), "sha256": hashlib.sha256(content).hexdigest()}
                chain = verify_tenant_chain(db, tenant_id)
                manifest["audit_chain"] = {key: chain[key] for key in ("valid", "checked", "last_seq", "last_hash")}
                archive.writestr("manifest.json", json.dumps(manifest, indent=2, default=str))
            buffer.seek(0)
            content = buffer.read()
        stored = storage.put(
            str(tenant_id), f"exports/{export_id}.zip", content, content_type="application/zip", internal=True
        )
        bind_system(db, f"tenant export {export_id}: done")
        row = db.get(TenantExport, uuid.UUID(str(export_id)))
        row.status = "READY"
        row.object_key = stored["object_key"]
        row.size_bytes = len(content)
        row.sha256 = stored["checksum"]
        row.summary = {
            "tables": sum(1 for item in manifest["tables"].values() if item["rows"]),
            "rows": sum(item["rows"] for item in manifest["tables"].values()),
            "files": len(manifest["files"]),
        }
        row.completed_at = datetime.now(timezone.utc)
        row.expires_at = row.completed_at + timedelta(days=EXPORT_DAYS)
        db.add(
            AuditEvent(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                actor_ref="system:worker",
                action="TENANT_EXPORT_CREATED",
                entity_type="TenantExport",
                entity_id=row.id,
                details={**row.summary, "size_bytes": row.size_bytes, "sha256": row.sha256},
                created_at=row.completed_at,
            )
        )
        db.commit()
        return describe(row)
    except Exception as exc:
        db.rollback()
        bind_system(db, f"tenant export {export_id}: failed")
        row = db.get(TenantExport, uuid.UUID(str(export_id)))
        if row is not None:
            row.status, row.error = "FAILED", type(exc).__name__
            db.commit()
        logger.exception("Tenant export %s failed", export_id)
        raise
    finally:
        db.close()


def read_export(db: Session, tenant_id, export_id) -> tuple[TenantExport, bytes]:
    from object_storage.service import ObjectStorageService

    row = (
        db.query(TenantExport)
        .filter(TenantExport.id == uuid.UUID(str(export_id)), TenantExport.tenant_id == uuid.UUID(str(tenant_id)))
        .first()
    )
    if row is None or row.status != "READY" or not row.object_key:
        raise LookupError("EXPORT_NOT_AVAILABLE")
    return row, ObjectStorageService().get(str(tenant_id), row.object_key)


def expire_exports(db: Session, now: datetime | None = None) -> int:
    """Delete exports past their download period (scheduler)."""
    from object_storage.service import ObjectStorageService

    now = now or datetime.now(timezone.utc)
    rows = db.query(TenantExport).filter(TenantExport.status == "READY", TenantExport.expires_at <= now).all()
    storage = ObjectStorageService() if rows else None
    for row in rows:
        try:
            storage.delete(str(row.tenant_id), row.object_key)
        except FileNotFoundError:
            pass
        row.status = "EXPIRED"
        row.object_key = None
    return len(rows)
