"""Export everything one organization stored, as one zip (data portability, offboarding, data-subject requests).

``request_export`` records the request and queues an outbox event; the background worker runs ``run_export``:
every table with rows for the organization (discovered from the database, so new tables are included) is written as
JSON Lines under ``data/``, every stored file under ``files/``, a human-readable CSV bundle of the quality records
under ``readable/`` (investigations, complaints, CAPAs and an evidence index), and ``manifest.json`` lists row
counts, file counts, a SHA-256 of each entry and the audit trail's verified head. Credentials are never exported:
columns holding passwords, secrets, tokens, recovery codes or encrypted keys are left out.

The zip is built on disk, not in memory: the archive is written to a temporary file and handed to object storage
as a memory-mapped file, so the server never holds a second copy of a large export. It goes to encrypted object
storage and can be downloaded for ``EXPORT_DAYS`` days (streamed, tenant_export_api.py); the scheduler then deletes
it (``expire_exports``).
"""

from __future__ import annotations

import base64
import csv
import hashlib
import io
import json
import logging
import mmap
import os
import re
import tempfile
import uuid
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.app.csv_safe import safe_cell
from backend.app.db.models.foundation import AuditEvent, Tenant
from backend.app.db.models.stage2 import OutboxEvent, TenantExport

logger = logging.getLogger("mdarix.tenant_export")

EXPORT_DAYS = 7
# The largest full export (code audit 16): the zip is encrypted and decrypted whole, so the worker and the download
# hold it in memory about twice, and the encryption takes at most 2 GiB. Refused before work starts (the stored files
# alone are larger) and again once the zip is built. shortcut: a size limit, not chunked encryption; upgrade when an
# organization's files approach 1 GiB.
MAX_EXPORT_BYTES = int(os.getenv("MDARIX_EXPORT_MAX_BYTES", str(1024**3)))
EVENT = "TENANT_EXPORT_REQUESTED"
# Columns never exported: credentials and secrets, even encrypted or hashed.
SECRET_COLUMN = re.compile(
    r"(?i)(password|secret|token|encrypted|api_key|private_key|recovery_hashes|session_hash|key_hash|code_hash|signing)"
)
SCHEMAS = ("public", "md_master")
# OD-1 (B2): customer contacts are masked in exports by default ("Contact held: yes"); unmasked only on request by a
# person with data.export, with a reason, audited; a trial's export is always masked.
CONTACT_COLUMNS = {
    "external_parties": (
        "primary_name",
        "primary_details",
        "second_name",
        "second_details",
        "contact_role",
        "contact_email",
        "contact_phone",
    )
}
CONTACT_HELD = "Contact held: yes"
MASKED, UNMASKED = "MASKED", "UNMASKED"


# tr30 (B9-D9 / B8-D9): patient and reporter details typed at Send for approval live only in that report's snapshot;
# a masked export writes "Personal data held: yes" in their place, and in place of the frozen files that carry them.
PERSONAL_HELD = "Personal data held: yes"
# The official India/Canada form frozen at approval (base64 PDF) prints them too (B8 run 6 review).
PERSONAL_FILES = ("mir_xml", "emdr_xml", "emdr_left_out", "official_pdf")
# Owner, 11 Nov ("tick-box"): an unmasked export leaves them out too unless "Include patient and reporter details from
# submitted reports" is ticked (data.export, the export's reason, audited EXPORT_PERSONAL_DATA_INCLUDED). The hand-back
# made while the organization is suspended or terminated (account closing) always holds everything.
INCLUDED, LEFT_OUT = "INCLUDED", "LEFT_OUT"
EXIT_STATUSES = ("SUSPENDED", "TERMINATED")
PERSONAL_EVENT = "EXPORT_PERSONAL_DATA_INCLUDED"


def _held(item: dict) -> bool:
    return bool(item.get("personal") and item.get("value"))


def personal_held(fields) -> tuple[list[str], list[str]]:
    """The patient and reporter boxes a snapshot holds values in, and its frozen files that carry them: ids only."""
    if not isinstance(fields, dict):
        return [], []
    ids = sorted(
        {
            str(item.get("id"))
            for section in fields.get("sections") or []
            for item in section.get("fields") or []
            if _held(item)
        }
    )
    return ids, [key for key in PERSONAL_FILES if ids and fields.get(key)]


def _tally(tally: dict, fields) -> None:
    ids, files = personal_held(fields)
    if not ids:
        return
    tally["snapshots"] += 1
    for group, keys in (("fields", ids), ("files", files)):
        for key in keys:
            tally[group][key] = tally[group].get(key, 0) + 1


def masked_snapshot(fields):
    """A report snapshot's frozen content without its patient and reporter values (unchanged when it holds none)."""
    if not isinstance(fields, dict):
        return fields
    sections = fields.get("sections") or []
    if not any(_held(item) for section in sections for item in section.get("fields") or []):
        return fields
    return {
        **fields,
        "sections": [
            {
                **section,
                "fields": [
                    {**item, "value": PERSONAL_HELD} if _held(item) else item for item in section.get("fields") or []
                ],
            }
            for section in sections
        ],
        **{key: PERSONAL_HELD for key in PERSONAL_FILES if fields.get(key)},
    }


def masked_row(table: str, row: dict) -> dict:
    """The row as a masked export writes it: each contact value held is replaced by "Contact held: yes"; a report
    snapshot's patient and reporter values by "Personal data held: yes"."""
    columns = CONTACT_COLUMNS.get(table, ())
    out = {key: (CONTACT_HELD if key in columns and value else value) for key, value in row.items()}
    if table == "report_snapshots" and "fields" in out:
        out["fields"] = masked_snapshot(out["fields"])
    return out


FETCH_ROWS = 1000
# The quality records a reader opens first, as spreadsheets: table -> (file name, columns in reading order). Each
# starts with the record's MDARIX identifier (business_id), then the customer's own number for it.
# Columns absent from a schema are skipped, so an older dedicated plane still exports.
READABLE_TABLES: dict[str, tuple[str, tuple[str, ...]]] = {
    "investigations": (
        "readable/investigations.csv",
        (
            "business_id",
            "investigation_identifier",
            "status",
            "investigation_question",
            "product_id",
            "owner_ref",
            "opened_at",
            "closed_at",
            "created_at",
            "updated_at",
            "id",
        ),
    ),
    "complaints": (
        "readable/complaints.csv",
        (
            "business_id",
            "complaint_identifier",
            "status",
            "severity",
            "complaint_type",
            "problem_code",
            "description",
            "product_id",
            "product_version_id",
            "lot_batch_id",
            "serial_number",
            "udi",
            "country",
            "reporter_type",
            "event_timestamp",
            "complaint_timestamp",
            "awareness_timestamp",
            "device_returned",
            "patient_involved",
            "serious_injury",
            "death",
            "malfunction",
            "created_at",
            "updated_at",
            "id",
        ),
    ),
    "capas": (
        "readable/capas.csv",
        (
            "business_id",
            "capa_identifier",
            "title",
            "status",
            "action_type",
            "source_type",
            "source_reference",
            "product_id",
            "investigation_id",
            "opened_at",
            "due_at",
            "effectiveness_check_at",
            "created_at",
            "updated_at",
            "id",
        ),
    ),
    "evidence": (
        "readable/evidence_index.csv",
        (
            "business_id",
            "evidence_identifier",
            "title",
            "evidence_type",
            "fact_type",
            "reliability_status",
            "investigation_id",
            "source_reference",
            "document_ref",
            "created_at",
            "updated_at",
            "id",
        ),
    ),
}


class ExportInProgress(RuntimeError):
    pass


class ExportTooLarge(RuntimeError):
    """A full export over MAX_EXPORT_BYTES (the message is the size found)."""


def request_export(
    db: Session,
    tenant_id,
    requested_by: str,
    reason: str,
    unmask_contacts: bool = False,
    include_personal: bool = False,
) -> TenantExport:
    """Queue a full export (one at a time per organization). Does not commit. Contacts are masked unless the caller
    (who checked data.export) asks to unmask them; a trial's export stays masked whatever is asked (OD-1). Patient and
    reporter details from submitted reports are left out unless an unmasked export asks for them (``include_personal``).
    The hand-back of a suspended or terminated organization (not a trial) holds everything."""
    tenant_id = uuid.UUID(str(tenant_id))
    busy = (
        db.query(TenantExport)
        .filter(TenantExport.tenant_id == tenant_id, TenantExport.status.in_(["QUEUED", "RUNNING"]))
        .first()
    )
    if busy is not None:
        raise ExportInProgress(str(busy.id))
    from object_storage.service import ObjectStorageService

    files = ObjectStorageService().stored_bytes(str(tenant_id), skip="exports")
    if files > MAX_EXPORT_BYTES:
        raise ExportTooLarge(str(files))
    now = datetime.now(timezone.utc)
    trial = _trial(db, tenant_id)
    tenant = db.get(Tenant, tenant_id)
    leaving = not trial and tenant is not None and tenant.status in EXIT_STATUSES
    contacts = UNMASKED if leaving or (unmask_contacts and not trial) else MASKED
    personal = INCLUDED if leaving or (contacts == UNMASKED and include_personal) else LEFT_OUT
    summary = {"contacts": contacts, "personal": personal, "exit": leaving}
    row = TenantExport(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        requested_by=requested_by,
        reason=reason,
        status="QUEUED",
        created_at=now,
        summary=summary,
    )
    db.add(row)
    db.flush()
    db.add(
        OutboxEvent(
            tenant_id=tenant_id,
            event_name=EVENT,
            aggregate_type="TenantExport",
            aggregate_id=row.id,
            payload={"tenant_id": str(tenant_id), "export_id": str(row.id)},  # tenant: the worker's check (RSK-026)
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
            details=summary,
            created_at=now,
        )
    )
    return row


def _trial(db: Session, tenant_id) -> bool:
    from backend.app.trial.service import trial_subscription

    return trial_subscription(db, tenant_id) is not None


def describe(row: TenantExport) -> dict:
    return {
        "id": str(row.id),
        "business_id": row.business_id,
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


class _HashingWriter:
    """Writes to a zip entry while keeping its SHA-256 and byte count, so the manifest is built without re-reading."""

    def __init__(self, handle):
        self.handle = handle
        self.digest = hashlib.sha256()
        self.size = 0

    def write(self, data) -> int:
        chunk = data.encode("utf-8") if isinstance(data, str) else data
        self.handle.write(chunk)
        self.digest.update(chunk)
        self.size += len(chunk)
        return len(chunk)


def _json_default(value):
    """What JSON cannot write: a binary column (a submitted PDF) as base64, anything else as its text."""
    if isinstance(value, (bytes, bytearray, memoryview)):
        return base64.b64encode(bytes(value)).decode()
    return str(value)


def _write_tables(
    db: Session,
    archive: zipfile.ZipFile,
    tenant_id,
    prefix: str,
    manifest: dict,
    unmask: bool = False,
    personal: bool = False,
) -> None:
    for schema, table in _tables(db):
        result = db.execute(
            text(f'SELECT * FROM "{schema}"."{table}" WHERE tenant_id = :tenant'), {"tenant": tenant_id}
        )
        columns = [name for name in result.keys() if not SECRET_COLUMN.search(name)]
        count = 0
        name = f"{prefix}{schema}.{table}.jsonl"
        with archive.open(name, "w") as handle:
            writer = _HashingWriter(handle)
            while rows := result.fetchmany(FETCH_ROWS):
                for row in rows:
                    values = {key: row._mapping[key] for key in columns}
                    if table == "report_snapshots" and "fields" in values:
                        _tally(manifest["personal_data"], values["fields"])
                        if not personal:
                            values["fields"] = masked_snapshot(values["fields"])
                    values = values if unmask else masked_row(table, values)
                    writer.write(json.dumps(values, default=_json_default) + "\n")
                    count += 1
        # Tables from a dedicated data plane are listed as "plane:<schema>.<table>" beside the control database's.
        key = f"{schema}.{table}" if prefix == "data/" else f"plane:{schema}.{table}"
        manifest["tables"][key] = {"rows": count, "file": name, "sha256": writer.digest.hexdigest()}


def _write_readable(db: Session, archive: zipfile.ZipFile, tenant_id, manifest: dict) -> None:
    """The CSV bundle: one spreadsheet per quality record type, columns in reading order, rows streamed."""
    present = {
        name
        for (name,) in db.execute(
            text(
                "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' AND table_type = 'BASE TABLE'"
            )
        )
    }
    for table, (name, preferred) in READABLE_TABLES.items():
        if table not in present:
            continue
        result = db.execute(
            text(f'SELECT * FROM "{table}" WHERE tenant_id = :tenant ORDER BY created_at, id'), {"tenant": tenant_id}
        )
        available = set(result.keys())
        columns = [column for column in preferred if column in available]
        count = 0
        with archive.open(name, "w") as handle:
            writer = _HashingWriter(handle)
            # csv writes text: each batch of rows is rendered to a small text buffer and flushed into the entry.
            buffer = io.StringIO()
            sheet = csv.DictWriter(buffer, fieldnames=columns, extrasaction="ignore", lineterminator="\r\n")
            sheet.writeheader()
            while rows := result.fetchmany(FETCH_ROWS):
                for row in rows:
                    # Formula-safe: a value starting with =, +, -, @ must not run when the sheet is opened.
                    sheet.writerow({key: safe_cell(_cell(row._mapping[key])) for key in columns})
                    count += 1
                writer.write(buffer.getvalue())
                buffer.seek(0)
                buffer.truncate()
            writer.write(buffer.getvalue())
        manifest["readable"][table] = {"rows": count, "file": name, "sha256": writer.digest.hexdigest()}


def _cell(value):
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, (dict, list)):
        return json.dumps(value, default=str)
    return value


def _build_archive(
    db: Session, tenant_id, tenant: Tenant | None, storage, path: Path, unmask: bool = False, personal: bool = False
) -> dict:
    """Write the export zip to ``path`` and return its manifest."""
    from backend.app.audit_chain import verify_tenant_chain
    from backend.app.db.data_plane import open_tenant_data_session

    now = datetime.now(timezone.utc)
    manifest: dict = {
        "organization": {
            "id": str(tenant_id),
            "business_id": tenant.business_id if tenant else None,
            "name": tenant.display_name if tenant else None,
        },
        "generated_at": now.isoformat(),
        "format": (
            "JSON Lines per table under data/; CSV spreadsheets of the quality records under readable/; "
            "stored files under files/. Credentials and secrets are not included"
        ),
        "tables": {},
        "readable": {},
        "files": {},
        # Box ids and counts only, never values.
        "personal_data": {
            "included": personal,
            "note": (
                "Patient and reporter details typed into submitted reports are included"
                if personal
                else f"Patient and reporter details typed into submitted reports are left out: each value, and each "
                f"frozen official file (PDF, XML) that carries them, reads '{PERSONAL_HELD}'"
            ),
            "snapshots": 0,
            "fields": {},
            "files": {},
        },
    }
    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        _write_tables(db, archive, tenant_id, "data/", manifest, unmask, personal)
        # A dedicated data plane holds the business records in its own database; the shared plane is the control
        # database. The readable bundle always comes from wherever the business records live.
        with open_tenant_data_session(tenant_id) as data:
            if str(data.get_bind().url) != str(db.get_bind().url):
                _write_tables(data, archive, tenant_id, "data/plane/", manifest, unmask, personal)
            _write_readable(data, archive, tenant_id, manifest)
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
    return manifest


def _store_archive(storage, tenant_id, export_id, path: Path) -> dict:
    """Hand the finished zip to object storage without reading it into a Python bytes object: the file is memory-
    mapped, so the storage client reads it page by page and the operating system frees the pages behind it."""
    with open(path, "rb") as handle, mmap.mmap(handle.fileno(), 0, access=mmap.ACCESS_READ) as view:
        return storage.put(
            str(tenant_id), f"exports/{export_id}.zip", view, content_type="application/zip", internal=True
        )


def run_export(export_id) -> dict:
    """Build the export's zip (worker). Raises on failure so the outbox retries; the row records the outcome."""
    from backend.app.db.session import SessionLocal
    from backend.app.db.tenant_scope import bind_system
    from object_storage.service import ObjectStorageService

    db = SessionLocal()
    temp: Path | None = None
    try:
        bind_system(db, f"tenant export {export_id}")
        row = db.get(TenantExport, uuid.UUID(str(export_id)))
        if row is None or row.status in {"READY", "EXPIRED"}:
            return {"status": row.status if row else "MISSING"}
        tenant_id = row.tenant_id
        tenant = db.get(Tenant, tenant_id)
        asked = row.summary or {}
        unmask = asked.get("contacts") == UNMASKED and not _trial(
            db, tenant_id
        )  # a trial is masked even if it became one later
        personal = unmask and asked.get("personal") == INCLUDED
        leaving = bool(asked.get("exit"))
        row.status, row.error = "RUNNING", None
        db.commit()
        storage = ObjectStorageService()
        bind_system(db, f"tenant export {export_id}")
        with tempfile.NamedTemporaryFile(prefix="mdarix-export-", suffix=".zip", delete=False) as handle:
            temp = Path(handle.name)
        manifest = _build_archive(db, tenant_id, tenant, storage, temp, unmask, personal)
        if temp.stat().st_size > MAX_EXPORT_BYTES:
            # Not retried: the same records give the same size.
            bind_system(db, f"tenant export {export_id}: too large")
            row = db.get(TenantExport, uuid.UUID(str(export_id)))
            row.status, row.error = "FAILED", ExportTooLarge.__name__
            db.commit()
            return describe(row)
        stored = _store_archive(storage, tenant_id, export_id, temp)
        bind_system(db, f"tenant export {export_id}: done")
        row = db.get(TenantExport, uuid.UUID(str(export_id)))
        row.status = "READY"
        row.object_key = stored["object_key"]
        row.size_bytes = temp.stat().st_size
        row.sha256 = stored["checksum"]
        row.summary = {
            "tables": sum(1 for item in manifest["tables"].values() if item["rows"]),
            "rows": sum(item["rows"] for item in manifest["tables"].values()),
            "files": len(manifest["files"]),
            "readable": {table: item["rows"] for table, item in manifest["readable"].items()},
            "contacts": UNMASKED if unmask else MASKED,
            "personal": INCLUDED if personal else LEFT_OUT,
            "exit": leaving,
        }
        row.completed_at = datetime.now(timezone.utc)
        row.expires_at = row.completed_at + timedelta(days=EXPORT_DAYS)
        if personal:
            tally = manifest["personal_data"]
            db.add(
                AuditEvent(
                    id=uuid.uuid4(),
                    tenant_id=tenant_id,
                    actor_ref=row.requested_by,
                    action=PERSONAL_EVENT,
                    entity_type="TenantExport",
                    entity_id=row.id,
                    reason=row.reason,
                    details={"exit": leaving, **{key: tally[key] for key in ("snapshots", "fields", "files")}},
                    created_at=row.completed_at,
                )
            )
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
        if temp is not None:
            try:
                os.unlink(temp)
            except OSError:
                logger.warning("Temporary export file %s could not be removed", temp)


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
