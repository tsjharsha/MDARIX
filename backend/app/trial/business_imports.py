"""Import of the business records beyond products, lots and complaints: components, suppliers, sites, bills of
materials, approved suppliers, lot genealogy, distribution, changes, requirements, risks, failure modes, controls,
investigations, evidence and CAPAs.

These templates plug into backend/app/trial/imports.py, which keeps the rules for every import: the whole batch is
checked first, references must resolve inside the tenant, personal data is refused, and a batch with any problem
writes nothing. A record that refers to another (a BOM line to its component) needs that record loaded first.
"""

from __future__ import annotations

from backend.app.countries import CODES

import uuid
from datetime import date, datetime

from sqlalchemy.orm import Session

from backend.app.db.models.foundation import (
    Capa,
    Change,
    Complaint,
    Component,
    ComponentSupplier,
    Control,
    Evidence,
    FailureMode,
    Investigation,
    InvestigationComplaint,
    LotComponent,
    ManufacturingSite,
    ProductComponent,
    RealityRelationship,
    Requirement,
    Risk,
    Supplier,
)
from retrieval.record_evidence import RecordEvidence, summary, upsert_record_evidences

TEMPLATES: dict[str, dict] = {
    "components": {
        "title": "Components",
        "required": ["component_id", "component_name"],
        "optional": ["revision", "description", "status"],
        "example": [["PS-110", "Downstream pressure sensor assembly", "B", "Measures line pressure", "active"]],
    },
    "suppliers": {
        "title": "Suppliers",
        "required": ["supplier_id", "supplier_name"],
        "optional": ["status"],
        "example": [["SUP-1001", "Kestrel Sensors Ltd", "active"]],
    },
    "sites": {
        "title": "Manufacturing sites",
        "required": ["site_id", "site_name"],
        "optional": ["location", "status"],
        "example": [["1100", "Galway final assembly", "IE Galway", "active"]],
    },
    "bom": {
        "title": "Bill of materials",
        "required": ["product_id", "version", "component_id"],
        "optional": ["effective_date"],
        "identity": ["product_id", "version", "component_id"],
        "example": [["PUMP-200", "Rev D", "PS-110", "2026-07-01"]],
    },
    "component_suppliers": {
        "title": "Approved suppliers of components",
        "required": ["component_id", "supplier_id"],
        "optional": ["effective_date"],
        "identity": ["component_id", "supplier_id"],
        "example": [["PS-110", "SUP-1001", "2025-01-01"]],
    },
    "lot_genealogy": {
        "title": "Lot genealogy",
        "required": ["lot_id", "component_id"],
        "optional": ["component_lot_id"],
        "identity": ["lot_id", "component_id", "component_lot_id"],
        "example": [["L24-0815", "PS-110", "KS-5521"]],
    },
    # Where each lot's units went (T-G5): consignees are organizations, never people; a free trial only for now
    # (imports.TRIAL_ONLY). A shipment is one lot, consignee, country and ship date: a re-upload updates it.
    "distribution": {
        "title": "Distribution",
        "required": ["lot_id", "consignee", "country", "quantity", "ship_date"],
        "optional": ["consignee_type", "consignee_reference"],
        "identity": ["lot_id", "consignee", "country", "ship_date"],
        "example": [
            ["L24-0815", "Galway University Hospital", "IE", "120", "2026-07-28", "Hospital", "C-1182"],
            ["L24-0815", "Medisupply Distribution GmbH", "DE", "80", "2026-08-02", "Distributor", "C-2207"],
        ],
    },
    "changes": {
        "title": "Engineering changes",
        "required": ["change_id", "change_type", "description"],
        "optional": ["effective_date", "affected_ids"],
        "example": [
            ["ECN-4471", "ECN", "Occlusion threshold lowered from 12 to 9 kPa", "2026-07-01", "PUMP-200;PS-110"]
        ],
    },
    "requirements": {
        "title": "Requirements",
        "required": ["requirement_id", "product_id", "text"],
        "optional": ["version", "requirement_type", "status", "risk_id"],
        "example": [
            [
                "REQ-AF200-045",
                "PUMP-200",
                "The occlusion alarm shall trigger within 30 s.",
                "Rev D",
                "Safety",
                "approved",
                "RSK-0012",
            ]
        ],
    },
    "risks": {
        "title": "Risks",
        "required": ["risk_id", "product_id", "description"],
        "optional": ["version", "status"],
        "example": [["RSK-0012", "PUMP-200", "Delayed therapy after a false occlusion alarm", "Rev D", "controlled"]],
    },
    "failure_modes": {
        "title": "Failure modes",
        "required": ["failure_mode_id", "failure_mode_name"],
        "optional": ["description", "risk_id"],
        "example": [["FM-031", "Sensor reading drifts high", "False occlusion alarm", "RSK-0012"]],
    },
    "controls": {
        "title": "Risk controls",
        "required": ["control_id", "description"],
        "optional": ["control_type", "status", "risk_id"],
        "example": [
            ["CTL-019", "Occlusion threshold verified in production test", "Protective measure", "verified", "RSK-0012"]
        ],
    },
    "investigations": {
        "title": "Investigations",
        "required": ["investigation_id", "product_id", "question"],
        "optional": ["status", "opened_date", "owner", "complaint_ids"],
        "example": [
            [
                "INV-3001",
                "PUMP-200",
                "Why do Rev D pumps raise false occlusion alarms?",
                "open",
                "2026-09-02",
                "QE-INV-014",
                "CMP-10021;CMP-10022",
            ]
        ],
    },
    "evidence": {
        "title": "Evidence documents and test results",
        "required": ["evidence_id", "title", "evidence_type"],
        "optional": ["content", "document_ref", "effective_date", "review_status", "product_id"],
        "example": [
            [
                "TR-88120",
                "Sensor drift test lot KS-5521",
                "Test result",
                "Offset 7.8 kPa, limit 5 kPa: fail",
                "",
                "2026-09-08",
                "approved",
                "PUMP-200",
            ]
        ],
    },
    "capas": {
        "title": "CAPAs",
        "required": ["capa_id", "title"],
        "optional": [
            "status",
            "action_type",
            "source_type",
            "source_reference",
            "product_id",
            "investigation_id",
            "opened_date",
            "due_date",
            "effectiveness_check_date",
        ],
        "example": [
            [
                "CAPA-0450",
                "Restore occlusion threshold margin",
                "open",
                "Corrective",
                "Investigation",
                "INV-3001",
                "PUMP-200",
                "INV-3001",
                "2026-09-15",
                "2026-12-15",
                "",
            ]
        ],
    },
}

# Model and identifier column behind each template that holds one record per key.
KEYED = {
    "components": (Component, "component_identifier", "component_id"),
    "suppliers": (Supplier, "supplier_identifier", "supplier_id"),
    "sites": (ManufacturingSite, "site_identifier", "site_id"),
    "changes": (Change, "change_identifier", "change_id"),
    "requirements": (Requirement, "requirement_identifier", "requirement_id"),
    "risks": (Risk, "risk_identifier", "risk_id"),
    "failure_modes": (FailureMode, "failure_mode_identifier", "failure_mode_id"),
    "controls": (Control, "control_identifier", "control_id"),
    "investigations": (Investigation, "investigation_identifier", "investigation_id"),
    "evidence": (Evidence, "evidence_identifier", "evidence_id"),
    "capas": (Capa, "capa_identifier", "capa_id"),
}
MODELS = (
    Component,
    Supplier,
    ManufacturingSite,
    Change,
    Requirement,
    Risk,
    FailureMode,
    Control,
    Investigation,
    Evidence,
    Capa,
)
REVIEW_STATUS = {
    "approved": "validated",
    "effective": "validated",
    "valid": "validated",
    "verified": "validated",
    "superseded": "superseded",
    "expired": "superseded",
    "withdrawn": "superseded",
    "obsolete": "superseded",
}


def split_ids(value: str | None) -> list[str]:
    return [part.strip() for part in (value or "").split(";") if part.strip()]


class Records:
    """Tenant-scoped lookups by business identifier, including records created earlier in the same batch."""

    def __init__(self, db: Session, tenant_id) -> None:
        self.db, self.tenant_id = db, tenant_id
        self.cache: dict[tuple[type, str], object | None] = {}

    def get(self, model, column: str, identifier: str):
        key = (model, identifier)
        if key not in self.cache:
            self.cache[key] = (
                self.db.query(model)
                .filter(model.tenant_id == self.tenant_id, getattr(model, column) == identifier)
                .order_by(model.created_at.desc())
                .first()
            )
        return self.cache[key]

    def remember(self, model, identifier: str, record) -> None:
        self.cache[(model, identifier)] = record

    def component(self, identifier: str):
        return self.get(Component, "component_identifier", identifier)

    def supplier(self, identifier: str):
        return self.get(Supplier, "supplier_identifier", identifier)

    def risk(self, identifier: str):
        return self.get(Risk, "risk_identifier", identifier)

    def complaint(self, identifier: str):
        return self.get(Complaint, "complaint_identifier", identifier)

    def investigation(self, identifier: str):
        return self.get(Investigation, "investigation_identifier", identifier)


def check(entity: str, rows, lookup, report) -> int:
    """Check references for one batch; return how many rows would add a record. lookup is imports._Lookup."""
    records = Records(lookup.db, lookup.tenant_id)
    new = 0
    for line, row in rows:

        def need(found, column: str, label: str) -> bool:
            if found is None:
                report.add(line, column, f"{label} '{row[column]}' is not in your workspace. Load it first.")
                return False
            return True

        product = version = None
        if row.get("product_id"):
            product = lookup.product(row["product_id"])
            if not need(product, "product_id", "Product"):
                continue
            if row.get("version"):
                version = lookup.version(product, row["version"])
                if version is None:
                    report.add(
                        line, "version", f"Version '{row['version']}' of '{row['product_id']}' is not loaded yet."
                    )
                    continue
        if row.get("risk_id") and entity != "risks" and not need(records.risk(row["risk_id"]), "risk_id", "Risk"):
            continue
        if entity in KEYED:
            model, column, key = KEYED[entity]
            if row.get("investigation_id") and entity == "capas":
                if not need(records.investigation(row["investigation_id"]), "investigation_id", "Investigation"):
                    continue
            if entity == "investigations":
                missing = [cid for cid in split_ids(row.get("complaint_ids")) if records.complaint(cid) is None]
                if missing:
                    report.add(line, "complaint_ids", f"Complaints not loaded yet: {', '.join(missing[:5])}.")
                    continue
            if entity == "changes":
                unknown = [
                    item
                    for item in split_ids(row.get("affected_ids"))
                    if lookup.product(item) is None and records.component(item) is None
                ]
                if unknown:
                    report.add(line, "affected_ids", f"Not a loaded product or component: {', '.join(unknown[:5])}.")
                    continue
            if records.get(model, column, row[key]) is None:
                new += 1
            continue
        if entity == "bom":
            component = records.component(row["component_id"])
            if not need(component, "component_id", "Component"):
                continue
            exists = (
                lookup.db.query(ProductComponent.id)
                .filter(
                    ProductComponent.tenant_id == lookup.tenant_id,
                    ProductComponent.product_version_id == version.id,
                    ProductComponent.component_id == component.id,
                )
                .first()
            )
            new += exists is None
        elif entity == "component_suppliers":
            component, supplier = records.component(row["component_id"]), records.supplier(row["supplier_id"])
            if not need(component, "component_id", "Component") or not need(supplier, "supplier_id", "Supplier"):
                continue
            exists = (
                lookup.db.query(ComponentSupplier.id)
                .filter(
                    ComponentSupplier.tenant_id == lookup.tenant_id,
                    ComponentSupplier.component_id == component.id,
                    ComponentSupplier.supplier_id == supplier.id,
                )
                .first()
            )
            new += exists is None
        elif entity == "lot_genealogy":
            lot, component = lookup.lot(row["lot_id"]), records.component(row["component_id"])
            if not need(lot, "lot_id", "Lot") or not need(component, "component_id", "Component"):
                continue
            new += _genealogy(lookup.db, lookup.tenant_id, lot.id, component.id, row.get("component_lot_id")) is None
        elif entity == "distribution":
            problem = distribution_problem(row)
            if problem:
                report.add(line, problem[0], problem[1])
                continue
            lot = lookup.lot(row["lot_id"])
            if not need(lot, "lot_id", "Lot"):
                continue
            new += _shipment(lookup.db, lookup.tenant_id, lot.id, row) is None
    return new


# ISO 3166-1 alpha-2: the officially assigned codes (one list, backend/app/countries.py).
COUNTRY_CODES = CODES


def distribution_problem(row: dict) -> tuple[str, str] | None:
    """A shipment row's own problem, before its lot is looked up: the country code and the units."""
    if (row.get("country") or "").strip().upper() not in COUNTRY_CODES:
        return "country", "Use the two-letter ISO country code, for example IN, US or DE (GB for the United Kingdom)."
    if not units(row.get("quantity")):
        return "quantity", "A shipment has at least one unit."
    return None


def units(value) -> int:
    """A whole number as the import's checks accept it ("1,250", "1 250"), 0 when there is none."""
    digits = "".join(character for character in str(value or "") if character.isdigit())
    return int(digits) if digits else 0


def _shipment(db: Session, tenant_id, lot_id, row: dict):
    from backend.app.db.models.lot_impact import LotDistribution

    return (
        db.query(LotDistribution)
        .filter(
            LotDistribution.tenant_id == tenant_id,
            LotDistribution.lot_batch_id == lot_id,
            LotDistribution.consignee == row["consignee"],
            LotDistribution.country == row["country"].strip().upper(),
            LotDistribution.ship_date == date.fromisoformat(row["ship_date"]),
        )
        .first()
    )


def distribution_flags(db: Session, tenant_id, lot_identifiers) -> list[dict]:
    """Lots this import shipped from whose units shipped (every shipment held, not only this file's) now exceed the
    units they released: the data-quality report flags them; nothing is refused."""
    from sqlalchemy import func

    from backend.app.db.models.foundation import LotBatch
    from backend.app.db.models.lot_impact import LotDistribution

    wanted = sorted(set(lot_identifiers))
    if not wanted:
        return []
    rows = (
        db.query(LotBatch.lot_identifier, LotBatch.quantity, func.sum(LotDistribution.quantity))
        .join(
            LotDistribution,
            (LotDistribution.lot_batch_id == LotBatch.id) & (LotDistribution.tenant_id == LotBatch.tenant_id),
        )
        .filter(LotBatch.tenant_id == tenant_id, LotBatch.lot_identifier.in_(wanted), LotBatch.quantity.isnot(None))
        .group_by(LotBatch.lot_identifier, LotBatch.quantity)
        .order_by(LotBatch.lot_identifier)
        .all()
    )
    return [
        {
            "lot_id": lot,
            "released": int(released),
            "shipped": int(shipped),
            "message": f"Lot {lot}: {int(shipped):,} units shipped, {int(released):,} released. Check the distribution "
            "or the lot's quantity.",
        }
        for lot, released, shipped in rows
        if shipped is not None and int(shipped) > int(released)
    ]


def _genealogy(db: Session, tenant_id, lot_id, component_id, component_lot: str | None):
    return (
        db.query(LotComponent)
        .filter(
            LotComponent.tenant_id == tenant_id,
            LotComponent.lot_batch_id == lot_id,
            LotComponent.component_id == component_id,
            LotComponent.component_lot_identifier == (component_lot or None),
        )
        .first()
    )


def _relate(db: Session, tenant_id, source: tuple[str, uuid.UUID], target: tuple[str, uuid.UUID], kind: str, now):
    exists = (
        db.query(RealityRelationship.id)
        .filter(
            RealityRelationship.tenant_id == tenant_id,
            RealityRelationship.source_entity_type == source[0],
            RealityRelationship.source_entity_id == source[1],
            RealityRelationship.target_entity_type == target[0],
            RealityRelationship.target_entity_id == target[1],
            RealityRelationship.relationship_type == kind,
        )
        .first()
    )
    if exists is None:
        db.add(
            RealityRelationship(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                source_entity_type=source[0],
                source_entity_id=source[1],
                target_entity_type=target[0],
                target_entity_id=target[1],
                relationship_type=kind,
                assertion_status="supported",
                effective_timestamp=now,
                recorded_timestamp=now,
                provenance={"origin": "import"},
                created_at=now,
            )
        )


def write(
    entity: str, rows, db: Session, tenant_id, lookup, stamp, parse_date, now: datetime, source: str
) -> tuple[int, int]:
    """Write one checked batch. stamp(row_date) gives the source and timestamp columns; parse_date reads a date."""
    records = Records(db, tenant_id)
    created = updated = 0
    evidence: list[RecordEvidence] = []
    for _, row in rows:
        product = lookup.product(row["product_id"]) if row.get("product_id") else None
        version = lookup.version(product, row["version"]) if product is not None and row.get("version") else None
        when = parse_date(row["effective_date"]) if row.get("effective_date") else None

        if entity in KEYED:
            model, column, key = KEYED[entity]
            record = records.get(model, column, row[key])
            values = _values(entity, row, product, version, records, parse_date)
            if record is None:
                record = model(
                    id=uuid.uuid4(),
                    tenant_id=tenant_id,
                    source_identifier=row[key],
                    **{column: row[key]},
                    **values,
                    **stamp(values.get("opened_at") or when),
                )
                db.add(record)
                records.remember(model, row[key], record)
                created += 1
            else:
                # A re-upload sets only what its file holds: an optional column it leaves out keeps the stored value
                # (a CAPA's or an investigation's status is not reset to open), and "updated" counts real changes (J9).
                kept = {name: value for name, value in values.items() if _given(name, row, key)}
                if apply_values(record, kept):
                    record.updated_at = now
                    updated += 1
            db.flush()
            _links(entity, row, record, db, tenant_id, lookup, records, now)
            item = _index(entity, row, record, product, version, db, tenant_id, source)
            if item is not None:
                evidence.append(item)
            continue

        if entity == "bom":
            component = records.component(row["component_id"])
            link = (
                db.query(ProductComponent)
                .filter(
                    ProductComponent.tenant_id == tenant_id,
                    ProductComponent.product_version_id == version.id,
                    ProductComponent.component_id == component.id,
                )
                .first()
            )
            if link is None:
                db.add(
                    ProductComponent(
                        id=uuid.uuid4(),
                        tenant_id=tenant_id,
                        product_version_id=version.id,
                        component_id=component.id,
                        relationship_status="active",
                        effective_timestamp=when,
                        created_at=now,
                    )
                )
                created += 1
            elif apply_values(link, {"effective_timestamp": when or link.effective_timestamp}):
                updated += 1
        elif entity == "component_suppliers":
            component, supplier = records.component(row["component_id"]), records.supplier(row["supplier_id"])
            link = (
                db.query(ComponentSupplier)
                .filter(
                    ComponentSupplier.tenant_id == tenant_id,
                    ComponentSupplier.component_id == component.id,
                    ComponentSupplier.supplier_id == supplier.id,
                )
                .first()
            )
            if link is None:
                db.add(
                    ComponentSupplier(
                        id=uuid.uuid4(),
                        tenant_id=tenant_id,
                        component_id=component.id,
                        supplier_id=supplier.id,
                        effective_timestamp=when,
                        created_at=now,
                    )
                )
                created += 1
            elif apply_values(link, {"effective_timestamp": when or link.effective_timestamp}):
                updated += 1
        elif entity == "lot_genealogy":
            lot, component = lookup.lot(row["lot_id"]), records.component(row["component_id"])
            if _genealogy(db, tenant_id, lot.id, component.id, row.get("component_lot_id")) is None:
                db.add(
                    LotComponent(
                        id=uuid.uuid4(),
                        tenant_id=tenant_id,
                        lot_batch_id=lot.id,
                        component_id=component.id,
                        component_lot_identifier=row.get("component_lot_id") or None,
                        created_at=now,
                    )
                )
                created += 1
        elif entity == "distribution":
            from backend.app.db.models.lot_impact import LotDistribution

            lot = lookup.lot(row["lot_id"])
            shipment = _shipment(db, tenant_id, lot.id, row)
            values = {
                "quantity": units(row["quantity"]),
                "consignee_type": row.get("consignee_type") or None,
                "consignee_reference": row.get("consignee_reference") or None,
            }
            if shipment is None:
                db.add(
                    LotDistribution(
                        id=uuid.uuid4(),
                        tenant_id=tenant_id,
                        lot_batch_id=lot.id,
                        consignee=row["consignee"],
                        country=row["country"].strip().upper(),
                        ship_date=parse_date(row["ship_date"]).date(),
                        source_system=source,
                        created_at=now,
                        updated_at=now,
                        **values,
                    )
                )
                created += 1
            elif apply_values(shipment, values):
                shipment.updated_at = now
                updated += 1
        db.flush()
    upsert_record_evidences(db, tenant_id, evidence)
    return created, updated


# The optional column each record field comes from (a required column is always in the row).
OPTIONAL_COLUMN = {
    "revision": "revision",
    "description": "description",
    "status": "status",
    "location": "location",
    "event_timestamp": "effective_date",
    "product_version_id": "version",
    "requirement_type": "requirement_type",
    "control_type": "control_type",
    "opened_at": "opened_date",
    "owner_ref": "owner",
    "content": "content",
    "document_ref": "document_ref",
    "reliability_status": "review_status",
    "action_type": "action_type",
    "source_type": "source_type",
    "source_reference": "source_reference",
    "product_id": "product_id",
    "investigation_id": "investigation_id",
    "due_at": "due_date",
    "effectiveness_check_at": "effectiveness_check_date",
}


def _given(field: str, row: dict, key: str) -> bool:
    """Whether the row's file gives this field: its column is there (for a status, with a value: a blank status keeps
    the stored one)."""
    column = OPTIONAL_COLUMN.get(field, key)
    return bool(row.get(column)) if field == "status" else column in row


def apply_values(record, values: dict) -> bool:
    """Set the values on the record; True when one of them changed."""
    changed = False
    for name, value in values.items():
        if getattr(record, name) != value:
            setattr(record, name, value)
            changed = True
    return changed


def _values(entity: str, row: dict, product, version, records: Records, parse_date) -> dict:
    status = (row.get("status") or "").lower() or None
    if entity == "components":
        return {
            "name": row["component_name"],
            "revision": row.get("revision") or None,
            "description": row.get("description") or None,
            "status": status or "active",
        }
    if entity == "suppliers":
        return {"name": row["supplier_name"], "status": status or "active"}
    if entity == "sites":
        return {"name": row["site_name"], "location": row.get("location") or None, "status": status or "active"}
    if entity == "changes":
        return {
            "change_type": row["change_type"],
            "description": row["description"],
            "event_timestamp": parse_date(row["effective_date"]) if row.get("effective_date") else None,
        }
    if entity == "requirements":
        return {
            "product_id": product.id,
            "product_version_id": version.id if version else None,
            "requirement_type": row.get("requirement_type") or None,
            "text": row["text"],
            "status": status or "active",
        }
    if entity == "risks":
        return {
            "product_id": product.id,
            "product_version_id": version.id if version else None,
            "description": row["description"],
            "status": status or "active",
        }
    if entity == "failure_modes":
        return {"name": row["failure_mode_name"], "description": row.get("description") or None}
    if entity == "controls":
        return {
            "control_type": row.get("control_type") or None,
            "description": row["description"],
            "status": status or "active",
        }
    if entity == "investigations":
        return {
            "product_id": product.id,
            "investigation_question": row["question"],
            "status": status or "open",
            "opened_at": parse_date(row["opened_date"]) if row.get("opened_date") else None,
            "owner_ref": row.get("owner") or None,
        }
    if entity == "evidence":
        return {
            "title": row["title"],
            "evidence_type": row["evidence_type"],
            "content": row.get("content") or None,
            "document_ref": row.get("document_ref") or None,
            "reliability_status": REVIEW_STATUS.get((row.get("review_status") or "").lower(), "unreviewed"),
            "fact_type": "source_fact",
        }
    if entity == "capas":
        investigation = records.investigation(row["investigation_id"]) if row.get("investigation_id") else None
        return {
            "title": row["title"],
            "status": status or "open",
            "action_type": row.get("action_type") or None,
            "source_type": row.get("source_type") or None,
            "source_reference": row.get("source_reference") or None,
            "product_id": product.id if product else None,
            "investigation_id": investigation.id if investigation else None,
            "opened_at": parse_date(row["opened_date"]) if row.get("opened_date") else None,
            "due_at": parse_date(row["due_date"]) if row.get("due_date") else None,
            "effectiveness_check_at": (
                parse_date(row["effectiveness_check_date"]) if row.get("effectiveness_check_date") else None
            ),
        }
    raise ValueError(entity)


def _links(entity: str, row: dict, record, db: Session, tenant_id, lookup, records: Records, now) -> None:
    """Relationships carried by a row: complaints of an investigation, the risk a control or requirement serves."""
    if entity == "investigations":
        for complaint_identifier in split_ids(row.get("complaint_ids")):
            complaint = records.complaint(complaint_identifier)
            exists = (
                db.query(InvestigationComplaint.id)
                .filter(
                    InvestigationComplaint.tenant_id == tenant_id,
                    InvestigationComplaint.investigation_id == record.id,
                    InvestigationComplaint.complaint_id == complaint.id,
                )
                .first()
            )
            if exists is None:
                db.add(
                    InvestigationComplaint(
                        id=uuid.uuid4(),
                        tenant_id=tenant_id,
                        investigation_id=record.id,
                        complaint_id=complaint.id,
                        created_at=now,
                    )
                )
    if row.get("risk_id") and entity in {"controls", "failure_modes", "requirements"}:
        kinds = {"controls": "CONTROLS", "failure_modes": "CAN_LEAD_TO", "requirements": "MITIGATES"}
        label = {"controls": "Control", "failure_modes": "FailureMode", "requirements": "Requirement"}[entity]
        _relate(db, tenant_id, (label, record.id), ("Risk", records.risk(row["risk_id"]).id), kinds[entity], now)
    if entity == "evidence" and row.get("product_id"):
        from backend.app.db.models.evidence_intelligence import EvidenceEntityLink

        product = lookup.product(row["product_id"])
        linked = (
            db.query(EvidenceEntityLink.id)
            .filter(
                EvidenceEntityLink.tenant_id == tenant_id,
                EvidenceEntityLink.evidence_id == record.id,
                EvidenceEntityLink.entity_type == "Product",
                EvidenceEntityLink.entity_id == product.id,
            )
            .first()
        )
        if linked is None:
            db.add(
                EvidenceEntityLink(
                    id=uuid.uuid4(),
                    tenant_id=tenant_id,
                    evidence_id=record.id,
                    entity_type="Product",
                    entity_id=product.id,
                    raw_reference=row["product_id"],
                    resolution_status="RESOLVED",
                )
            )
    if entity == "changes":
        for item in split_ids(row.get("affected_ids")):
            product = lookup.product(item)
            target = ("Product", product.id) if product is not None else ("Component", records.component(item).id)
            _relate(db, tenant_id, ("Change", record.id), target, "AFFECTS", now)
    db.flush()


def _index(
    entity: str, row: dict, record, product, version, db: Session, tenant_id, source: str
) -> RecordEvidence | None:
    """Make the record searchable by the AI (see retrieval/record_evidence.py): its evidence row, which write() adds
    for the whole batch at once (NEW-4). An imported evidence record is chunked here, as it is its own evidence."""
    product_link = [("Product", product.id if product else None), ("ProductVersion", version.id if version else None)]
    facts: dict[str, object]
    if entity == "investigations":
        complaints = split_ids(row.get("complaint_ids"))
        text = summary(
            f"Investigation {row['investigation_id']}",
            {
                "Product": row["product_id"],
                "Status": record.status,
                "Opened": record.opened_at,
                "Complaints": ", ".join(complaints),
            },
            f"Question: {row['question']}",
        )
        return RecordEvidence(
            kind="INVESTIGATION",
            identifier=row["investigation_id"],
            title=f"Investigation {row['investigation_id']}",
            content=text,
            links=[("Investigation", record.id), *product_link],
            source=source,
            investigation_id=record.id,
        )
    elif entity == "capas":
        facts = {
            "Type": record.action_type,
            "Status": record.status,
            "Source": record.source_reference,
            "Product": row.get("product_id"),
            "Due": record.due_at,
        }
        return RecordEvidence(
            kind="CAPA",
            identifier=row["capa_id"],
            title=f"CAPA {row['capa_id']}: {row['title']}",
            content=summary(f"CAPA {row['capa_id']}: {row['title']}", facts),
            links=[("Capa", record.id), *product_link],
            source=source,
            investigation_id=record.investigation_id,
        )
    elif entity == "changes":
        facts = {
            "Type": record.change_type,
            "Effective": record.event_timestamp,
            "Affects": row.get("affected_ids", "").replace(";", ", "),
        }
        return RecordEvidence(
            kind="CHANGE",
            identifier=row["change_id"],
            title=f"Change {row['change_id']}",
            content=summary(f"Change {row['change_id']}", facts, record.description),
            links=[("Change", record.id)],
            source=source,
        )
    elif entity in {"requirements", "risks", "failure_modes", "controls"}:
        label = {
            "requirements": "Requirement",
            "risks": "Risk",
            "failure_modes": "Failure mode",
            "controls": "Control",
        }[entity]
        key = KEYED[entity][2]
        narrative = row.get("text") or row.get("description") or row.get("failure_mode_name")
        facts = {
            "Product": row.get("product_id"),
            "Version": row.get("version"),
            "Status": row.get("status"),
            "Risk": row.get("risk_id"),
        }
        return RecordEvidence(
            kind=entity.upper().rstrip("S"),
            identifier=row[key],
            title=f"{label} {row[key]}",
            content=summary(f"{label} {row[key]}", facts, narrative),
            links=[(label.replace(" ", ""), record.id), *product_link],
            source=source,
        )
    elif entity == "evidence" and record.content:
        from evidence.extractors.chunker import EvidenceChunker

        EvidenceChunker().create_chunks_for_evidence(
            db, tenant_id, record.id, record.content, {"record": row["evidence_id"]}
        )
