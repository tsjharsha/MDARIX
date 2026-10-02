"""Validated import of products, lots and complaints: CSV uploads (trials and workspaces) and mapped connector records.

Every batch is checked in full before anything is written: only template columns are accepted, references must
resolve inside the tenant, and text that looks like personal data (emails, phone numbers, dates of birth, patient
or record numbers, named people) is rejected. A batch with any problem imports nothing. An ImportPolicy sets the
source label recorded on each row and any row or file limits (free trials have both).
"""

from __future__ import annotations

import csv
import io
import re
import uuid
from dataclasses import dataclass
from datetime import date, datetime, time, timezone

from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.app.db.models.foundation import Complaint, LotBatch, Product, ProductVersion
from backend.app.trial.sample_data import SAMPLE_SOURCE
from backend.app.trial.service import TRIAL_FILE_LIMIT_BYTES, TRIAL_ROW_LIMIT

UPLOAD_SOURCE = "TRIAL_UPLOAD"
WORKSPACE_UPLOAD_SOURCE = "CSV_IMPORT"
MAX_ISSUES = 50


@dataclass(frozen=True)
class ImportPolicy:
    source: str
    row_limit: int | None = None
    file_limit_bytes: int = 10 * 1024 * 1024
    file_too_large: str = "Files can be up to 10 MB"
    limit_label: str = "your workspace"


TRIAL_POLICY = ImportPolicy(
    source=UPLOAD_SOURCE,
    row_limit=TRIAL_ROW_LIMIT,
    file_limit_bytes=TRIAL_FILE_LIMIT_BYTES,
    file_too_large="Files can be up to 2 MB during the free trial",
    limit_label="your trial",
)
WORKSPACE_POLICY = ImportPolicy(source=WORKSPACE_UPLOAD_SOURCE)
COMPLAINT_STATUSES = {"open", "closed", "under investigation"}

TEMPLATES: dict[str, dict] = {
    "products": {
        "title": "Products and versions",
        "required": ["product_id", "product_name"],
        # A version is optional so sources that only list products (e.g. a PLM product list) can load them.
        "optional": ["version", "product_family", "version_release_date"],
        "example": [
            ["PUMP-200", "AquaFlow 200 Infusion Pump", "Rev C", "Infusion therapy", "2026-03-15"],
            ["PUMP-200", "AquaFlow 200 Infusion Pump", "Rev D", "Infusion therapy", "2026-07-01"],
        ],
    },
    "lots": {
        "title": "Lots and batches",
        "required": ["lot_id", "product_id", "version"],
        "optional": ["manufacture_date"],
        "example": [["L24-0815", "PUMP-200", "Rev D", "2026-07-20"], ["L24-0902", "PUMP-200", "Rev D", "2026-08-11"]],
    },
    "complaints": {
        "title": "Complaints",
        "required": ["complaint_id", "product_id", "description"],
        "optional": ["version", "lot_id", "event_date", "received_date", "status"],
        "example": [
            [
                "CMP-10021",
                "PUMP-200",
                "Occlusion alarm sounded with no occlusion present. Device returned for evaluation.",
                "Rev D",
                "L24-0815",
                "2026-08-28",
                "2026-08-30",
                "open",
            ]
        ],
    },
}

_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 ._/#:-]{0,119}$")
_PERSONAL_DATA = [
    (re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"), "an email address"),
    (re.compile(r"(?<!\w)(\+\d{1,3}[\s-]?)?\(?\d{3}\)?[\s.-]?\d{3}[\s.-]?\d{4}(?!\w)"), "a phone number"),
    (re.compile(r"\b\d{3}-\d{2}-\d{4}\b"), "a national ID number"),
    (re.compile(r"\b(d\.?o\.?b\.?|date of birth|born on|birth ?date)\b", re.I), "a date of birth"),
    (
        re.compile(
            r"\b(mrn|medical record|patient (id|no|number|name)|ssn|social security|nhs (no|number)|aadhaar)\b",
            re.I,
        ),
        "a patient or record identifier",
    ),
    (re.compile(r"\b(mr|mrs|ms|miss|dr)\.?\s+[A-Z][a-z]+"), "a person's name"),
]


def template_csv(entity: str) -> str:
    spec = TEMPLATES[entity]
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\n")
    writer.writerow(spec["required"] + spec["optional"])
    for example in spec["example"]:
        writer.writerow(example)
    return out.getvalue()


def _spreadsheet_formula(value: str) -> bool:
    """Text a spreadsheet would run as a formula when the data is exported and opened (CSV injection)."""
    first = value[:1]
    return first in {"=", "+", "@", "\t", "\r"} or (first == "-" and "(" in value[:40])


def _personal_data(value: str) -> str | None:
    for pattern, label in _PERSONAL_DATA:
        if pattern.search(value):
            return label
    return None


def _date(value: str) -> datetime | None:
    return datetime.combine(date.fromisoformat(value), time(12, 0), tzinfo=timezone.utc)


class _Report:
    def __init__(self) -> None:
        self.issues: list[dict] = []
        self.error_count = 0

    def add(self, row: int | None, column: str | None, message: str) -> None:
        self.error_count += 1
        if len(self.issues) < MAX_ISSUES:
            self.issues.append({"row": row, "column": column, "message": message})


def _parse(entity: str, raw: bytes, report: _Report, policy: ImportPolicy = TRIAL_POLICY) -> list[tuple[int, dict]]:
    if entity not in TEMPLATES:
        raise HTTPException(404, detail={"code": "TEMPLATE_NOT_FOUND", "message": "Unknown template"})
    if len(raw) > policy.file_limit_bytes:
        raise HTTPException(413, detail={"code": "FILE_TOO_LARGE", "message": policy.file_too_large})
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        report.add(None, None, "The file is not UTF-8 text. Save it as 'CSV UTF-8' and try again.")
        return []
    reader = csv.reader(io.StringIO(text))
    header = next(reader, None)
    if not header:
        report.add(None, None, "The file is empty.")
        return []
    spec = TEMPLATES[entity]
    columns = [cell.strip().lower() for cell in header]
    allowed = spec["required"] + spec["optional"]
    for column in columns:
        if column not in allowed:
            report.add(
                1, column, f"Column '{column}' is not in the template. Remove it; only template columns are accepted."
            )
    for column in spec["required"]:
        if column not in columns:
            report.add(1, column, f"Required column '{column}' is missing.")
    if len(set(columns)) != len(columns):
        report.add(1, None, "A column appears more than once.")
    if report.error_count:
        return []
    rows = []
    for line_number, cells in enumerate(reader, 2):
        if not any(cell.strip() for cell in cells):
            continue
        if len(cells) > len(columns):
            report.add(line_number, None, "This row has more values than the header has columns.")
            continue
        rows.append(
            (line_number, {column: (cells[i].strip() if i < len(cells) else "") for i, column in enumerate(columns)})
        )
    if not rows:
        report.add(None, None, "The file has a header but no data rows.")
    return rows


def _check_values(entity: str, rows: list[tuple[int, dict]], report: _Report) -> None:
    spec = TEMPLATES[entity]
    key = spec["required"][0]
    seen: dict[tuple, int] = {}
    for line, row in rows:
        for column in spec["required"]:
            if not row.get(column):
                report.add(line, column, f"'{column}' is required.")
        for column, value in row.items():
            if not value:
                continue
            if column.endswith("_id") or column == "version":
                if not _ID.match(value):
                    report.add(line, column, "Use up to 120 letters, numbers, spaces or . _ / # : - characters.")
            elif column.endswith("_date"):
                try:
                    date.fromisoformat(value)
                except ValueError:
                    report.add(line, column, f"'{value}' is not a date in YYYY-MM-DD format.")
            else:
                limit = 4000 if column == "description" else 255
                if len(value) > limit:
                    report.add(line, column, f"Keep this under {limit} characters.")
                found = _personal_data(value)
                if found:
                    report.add(line, column, f"This looks like it contains {found}. Remove personal data and retry.")
                if _spreadsheet_formula(value):
                    report.add(line, column, "Text cannot start with =, +, @ or a formula; spreadsheets would run it.")
        if entity == "complaints" and row.get("status") and row["status"].lower() not in COMPLAINT_STATUSES:
            report.add(line, "status", "Status must be open, closed or under investigation.")
        identity = (row.get(key), row.get("version")) if entity == "products" else (row.get(key),)
        if identity in seen:
            report.add(line, key, f"Duplicate of row {seen[identity]}.")
        else:
            seen[identity] = line


class _Lookup:
    """Tenant-scoped product, version and lot lookups, including rows created earlier in the same file."""

    def __init__(self, db: Session, tenant_id) -> None:
        self.db, self.tenant_id = db, tenant_id
        self.products: dict[str, Product | None] = {}
        self.versions: dict[tuple[str, str], ProductVersion | None] = {}
        self.lots: dict[str, LotBatch | None] = {}

    def product(self, identifier: str) -> Product | None:
        if identifier not in self.products:
            self.products[identifier] = (
                self.db.query(Product)
                .filter(Product.tenant_id == self.tenant_id, Product.product_identifier == identifier)
                .first()
            )
        return self.products[identifier]

    def version(self, product: Product, identifier: str) -> ProductVersion | None:
        key = (product.product_identifier, identifier)
        if key not in self.versions:
            self.versions[key] = (
                self.db.query(ProductVersion)
                .filter(
                    ProductVersion.tenant_id == self.tenant_id,
                    ProductVersion.product_id == product.id,
                    ProductVersion.version_identifier == identifier,
                )
                .first()
            )
        return self.versions[key]

    def lot(self, identifier: str) -> LotBatch | None:
        if identifier not in self.lots:
            self.lots[identifier] = (
                self.db.query(LotBatch)
                .filter(LotBatch.tenant_id == self.tenant_id, LotBatch.lot_identifier == identifier)
                .first()
            )
        return self.lots[identifier]


def _check_references(entity: str, rows, lookup: _Lookup, report: _Report) -> int:
    """Validate references and count the rows that would be new records."""
    new = 0
    new_products: set[str] = set()
    for line, row in rows:
        if entity == "products":
            product = lookup.product(row["product_id"])
            if product is None and row["product_id"] not in new_products:
                new_products.add(row["product_id"])
                new += 1
            if row.get("version") and (product is None or lookup.version(product, row["version"]) is None):
                new += 1
            continue
        product = lookup.product(row["product_id"])
        if product is None:
            report.add(line, "product_id", f"Product '{row['product_id']}' is not in your workspace. Load it first.")
            continue
        version = None
        if row.get("version"):
            version = lookup.version(product, row["version"])
            if version is None:
                report.add(line, "version", f"Version '{row['version']}' of '{row['product_id']}' is not loaded yet.")
        if entity == "lots":
            existing = lookup.lot(row["lot_id"])
            if existing is None:
                new += 1
            elif version is not None and existing.product_version_id not in (None, version.id):
                report.add(line, "lot_id", f"Lot '{row['lot_id']}' already belongs to another version.")
            continue
        if row.get("lot_id"):
            lot = lookup.lot(row["lot_id"])
            if lot is None:
                report.add(line, "lot_id", f"Lot '{row['lot_id']}' is not loaded yet.")
            else:
                lot_version = (
                    lookup.db.query(ProductVersion).filter(ProductVersion.id == lot.product_version_id).first()
                )
                if lot_version is not None and lot_version.product_id != product.id:
                    report.add(line, "lot_id", f"Lot '{row['lot_id']}' belongs to a different product.")
        exists = (
            lookup.db.query(Complaint.id)
            .filter(Complaint.tenant_id == lookup.tenant_id, Complaint.complaint_identifier == row["complaint_id"])
            .first()
        )
        if exists is None:
            new += 1
    return new


def rows_from_records(entity: str, records: list[dict], report: _Report) -> list[tuple[int, dict]]:
    """Mapped connector records as template rows (record number instead of a file line)."""
    if entity not in TEMPLATES:
        raise HTTPException(404, detail={"code": "TEMPLATE_NOT_FOUND", "message": "Unknown template"})
    spec = TEMPLATES[entity]
    allowed = set(spec["required"] + spec["optional"])
    rows = []
    for number, record in enumerate(records, 1):
        unknown = sorted(set(record) - allowed)
        if unknown:
            report.add(number, unknown[0], f"Field '{unknown[0]}' is not part of the {entity} template.")
            continue
        rows.append((number, {column: str(record.get(column) or "").strip() for column in record}))
    if not records:
        report.add(None, None, "No records to import.")
    return rows


def uploaded_rows(db: Session, tenant_id, source: str = UPLOAD_SOURCE) -> int:
    total = 0
    for model in (Product, ProductVersion, LotBatch, Complaint):
        total += (
            db.query(func.count(model.id)).filter(model.tenant_id == tenant_id, model.source_system == source).scalar()
            or 0
        )
    return int(total)


def check_file(db: Session, tenant_id, entity: str, raw: bytes, policy: ImportPolicy = TRIAL_POLICY) -> dict:
    report = _Report()
    rows = _parse(entity, raw, report, policy)
    return _check_rows(db, tenant_id, entity, rows, report, policy)


def check_records(db: Session, tenant_id, entity: str, records: list[dict], policy: ImportPolicy) -> dict:
    report = _Report()
    rows = rows_from_records(entity, records, report)
    return _check_rows(db, tenant_id, entity, rows, report, policy)


def _check_rows(db: Session, tenant_id, entity: str, rows, report: _Report, policy: ImportPolicy) -> dict:
    new_rows = 0
    if rows:
        _check_values(entity, rows, report)
        if not report.error_count:
            new_rows = _check_references(entity, rows, _Lookup(db, tenant_id), report)
    used = uploaded_rows(db, tenant_id, policy.source)
    if policy.row_limit is not None and new_rows and used + new_rows > policy.row_limit:
        report.add(
            None,
            None,
            f"This file adds {new_rows} records; {policy.limit_label} has {max(policy.row_limit - used, 0)} of "
            f"{policy.row_limit} left.",
        )
    return {
        "entity": entity,
        "rows": len(rows),
        "new_records": new_rows,
        "updated_records": max(len(rows) - new_rows, 0) if entity != "products" else None,
        "error_count": report.error_count,
        "issues": report.issues,
        "ready": bool(rows) and report.error_count == 0,
        "preview": [row for _, row in rows[:8]],
        "rows_used": used,
        "row_limit": policy.row_limit,
    }


def _stamp(now: datetime, row_date: datetime | None = None, source: str = UPLOAD_SOURCE) -> dict:
    when = row_date or now
    return {
        "source_system": source,
        "source_timestamp": when,
        "effective_timestamp": when,
        "recorded_timestamp": now,
        "ingestion_timestamp": now,
        "created_at": now,
        "updated_at": now,
    }


def import_file(db: Session, tenant_id, entity: str, raw: bytes, policy: ImportPolicy = TRIAL_POLICY) -> dict:
    report = check_file(db, tenant_id, entity, raw, policy)
    if not report["ready"]:
        raise HTTPException(
            422, detail={"code": "IMPORT_CHECK_FAILED", "message": "Fix the listed problems first", "report": report}
        )
    return _write_rows(db, tenant_id, entity, _parse(entity, raw, _Report(), policy), policy)


def import_records(db: Session, tenant_id, entity: str, records: list[dict], policy: ImportPolicy) -> dict:
    report = check_records(db, tenant_id, entity, records, policy)
    if not report["ready"]:
        raise HTTPException(
            422, detail={"code": "IMPORT_CHECK_FAILED", "message": "Fix the listed problems first", "report": report}
        )
    return _write_rows(db, tenant_id, entity, rows_from_records(entity, records, _Report()), policy)


def _write_rows(db: Session, tenant_id, entity: str, rows, policy: ImportPolicy) -> dict:
    source = policy.source
    lookup = _Lookup(db, tenant_id)
    now = datetime.now(timezone.utc)
    created = updated = 0
    for _, row in rows:
        if entity == "products":
            product = lookup.product(row["product_id"])
            if product is None:
                product = Product(
                    id=uuid.uuid4(),
                    tenant_id=tenant_id,
                    product_identifier=row["product_id"],
                    name=row["product_name"],
                    product_family=row.get("product_family") or None,
                    lifecycle_status="active",
                    source_identifier=row["product_id"],
                    **_stamp(now, None, source),
                )
                db.add(product)
                db.flush()
                lookup.products[row["product_id"]] = product
                created += 1
            elif product.source_system == source:
                product.name = row["product_name"]
                product.product_family = row.get("product_family") or product.product_family
                product.updated_at = now
            if not row.get("version"):
                db.flush()
                continue
            released = _date(row["version_release_date"]) if row.get("version_release_date") else None
            version = lookup.version(product, row["version"])
            if version is None:
                version = ProductVersion(
                    id=uuid.uuid4(),
                    tenant_id=tenant_id,
                    product_id=product.id,
                    version_identifier=row["version"],
                    lifecycle_status="active",
                    release_timestamp=released,
                    source_identifier=f"{row['product_id']}:{row['version']}",
                    **_stamp(now, released, source),
                )
                db.add(version)
                lookup.versions[(row["product_id"], row["version"])] = version
                created += 1
            else:
                if released:
                    version.release_timestamp = released
                version.updated_at = now
                updated += 1
            db.flush()
            continue
        product = lookup.product(row["product_id"])
        version = lookup.version(product, row["version"]) if row.get("version") else None
        if entity == "lots":
            built = _date(row["manufacture_date"]) if row.get("manufacture_date") else None
            lot = lookup.lot(row["lot_id"])
            if lot is None:
                lot = LotBatch(
                    id=uuid.uuid4(),
                    tenant_id=tenant_id,
                    lot_identifier=row["lot_id"],
                    product_version_id=version.id if version else None,
                    status="active",
                    source_identifier=row["lot_id"],
                    **_stamp(now, built, source),
                )
                db.add(lot)
                lookup.lots[row["lot_id"]] = lot
                created += 1
            else:
                lot.product_version_id = version.id if version else lot.product_version_id
                if built:
                    lot.effective_timestamp = built
                lot.updated_at = now
                updated += 1
            db.flush()
            continue
        lot = lookup.lot(row["lot_id"]) if row.get("lot_id") else None
        event = _date(row["event_date"]) if row.get("event_date") else None
        received = _date(row["received_date"]) if row.get("received_date") else None
        complaint = (
            db.query(Complaint)
            .filter(Complaint.tenant_id == tenant_id, Complaint.complaint_identifier == row["complaint_id"])
            .first()
        )
        values = {
            "product_id": product.id,
            "product_version_id": version.id if version else (lot.product_version_id if lot else None),
            "lot_batch_id": lot.id if lot else None,
            "event_timestamp": event,
            "complaint_timestamp": received or event,
            "description": row["description"],
            "status": (row.get("status") or "open").lower(),
        }
        if complaint is None:
            db.add(
                Complaint(
                    id=uuid.uuid4(),
                    tenant_id=tenant_id,
                    complaint_identifier=row["complaint_id"],
                    source_identifier=row["complaint_id"],
                    **values,
                    **_stamp(now, received or event, source),
                )
            )
            created += 1
        else:
            for name, value in values.items():
                setattr(complaint, name, value)
            complaint.updated_at = now
            updated += 1
        db.flush()
    return {"entity": entity, "created": created, "updated": updated, "rows": len(rows)}


def insights(db: Session, tenant_id) -> dict:
    """Counts and concentrations computed from the workspace's complaints; facts for a person to interpret."""
    own = (
        db.query(Complaint.id)
        .filter(Complaint.tenant_id == tenant_id, Complaint.source_system == UPLOAD_SOURCE)
        .first()
        is not None
    )
    scope = UPLOAD_SOURCE if own else SAMPLE_SOURCE
    base = db.query(Complaint).filter(Complaint.tenant_id == tenant_id, Complaint.source_system == scope)
    complaints = base.all()
    total = len(complaints)
    products = {p.id: p for p in db.query(Product).filter(Product.tenant_id == tenant_id).all()}
    versions = {v.id: v for v in db.query(ProductVersion).filter(ProductVersion.tenant_id == tenant_id).all()}
    lots = {lot.id: lot for lot in db.query(LotBatch).filter(LotBatch.tenant_id == tenant_id).all()}

    def tally(key):
        counts: dict = {}
        for complaint in complaints:
            value = key(complaint)
            if value is not None:
                counts[value] = counts.get(value, 0) + 1
        return sorted(counts.items(), key=lambda item: (-item[1], str(item[0])))

    by_product = [
        {"product_id": products[pid].product_identifier, "name": products[pid].name, "complaints": n}
        for pid, n in tally(lambda c: c.product_id)
        if pid in products
    ]
    by_version = [
        {
            "product_id": products[versions[vid].product_id].product_identifier
            if versions[vid].product_id in products
            else None,
            "version": versions[vid].version_identifier,
            "complaints": n,
        }
        for vid, n in tally(lambda c: c.product_version_id)
        if vid in versions
    ]
    by_lot = [
        {"lot_id": lots[lid].lot_identifier, "complaints": n}
        for lid, n in tally(lambda c: c.lot_batch_id)
        if lid in lots
    ][:5]
    by_month = sorted(
        (
            {"month": month, "complaints": n}
            for month, n in tally(
                lambda c: (
                    (c.complaint_timestamp or c.event_timestamp or c.created_at).strftime("%Y-%m")
                    if (c.complaint_timestamp or c.event_timestamp or c.created_at)
                    else None
                )
            )
        ),
        key=lambda item: item["month"],
    )
    findings = []
    if by_version and total:
        top = by_version[0]
        share = round(100 * top["complaints"] / total)
        if share >= 40 and len(by_version) > 1:
            findings.append(
                f"{share}% of complaints ({top['complaints']} of {total}) concern {top['product_id']} {top['version']}."
            )
    if by_lot and total:
        top_lots = by_lot[:2]
        share = round(100 * sum(item["complaints"] for item in top_lots) / total)
        if share >= 30 and len(by_lot) > 2:
            findings.append(
                f"{share}% of complaints come from lots {' and '.join(item['lot_id'] for item in top_lots)}."
            )
    if len(by_month) >= 4:
        recent = sum(item["complaints"] for item in by_month[-3:]) / 3
        earlier = sum(item["complaints"] for item in by_month[:-3]) / max(len(by_month) - 3, 1)
        if earlier and recent >= 1.5 * earlier:
            findings.append(
                f"Complaints in the last 3 months average {recent:.1f} per month, up from {earlier:.1f} before."
            )
    questions = []
    if by_version:
        questions.append(f"What changed in {by_version[0]['product_id']} {by_version[0]['version']}?")
    if by_lot:
        questions.append(f"Which components and suppliers do lots {by_lot[0]['lot_id']} share?")
    questions.append("What evidence is still missing before we can explain this complaint trend?")
    return {
        "scope": "your data" if own else "sample data",
        "total_complaints": total,
        "by_product": by_product,
        "by_version": by_version[:6],
        "by_lot": by_lot,
        "by_month": by_month,
        "findings": findings,
        "suggested_questions": questions,
        "note": "Counts and patterns from your records. They point to where to look; people decide what they mean.",
    }
