"""The sample's simulated sources (W5, spec section 1): where OrbitCare 300's records came from, as recorded import runs
from three generic systems (PLM, ERP, eQMS). "Simulated, not a live connection": no system is connected; each run is
the sample's own records read again as an export would hold them, through the trial import's real checks.

- **Seven runs** (``RUNS``), each with its file's headers (the ones not used are kept as "not used"), the mapping
  version they give, the import's own value and reference checks (``imports._check_values``, ``_check_references``),
  the rows set aside with the reasons those checks give, the lineage of every row written (R16) and the data-quality
  report (R17), balanced. Each run has one problem row except the change orders and the suppliers (clean runs).
- **Nothing is added to the business records:** every written row names a record the sample already holds; the problem
  rows are set aside. One ``TRIAL_DATA_IMPORTED`` audit record per run, marked ``sample`` and ``simulated_system``,
  with no created or updated counts, so nothing waits for signals and ``/runs`` (the trial's own import runs) leaves
  them out. Set-aside rows of these entities never reach Triage (it reads complaints only).
- The complaints and distribution runs the sample already has are reused as the eQMS's and the ERP's (``SYSTEM_OF``).

Never imports ``source_simulator`` (not in the API image). Every row is marked ``MDARIX_SAMPLE`` (lineage and
quarantine ``source``), so sample removal takes it. Idempotent; runs only after the sample's lot impact; flushes but
never commits (the caller owns the transaction).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.app import import_lineage, import_quarantine
from backend.app.db.models.ingestion import ImportLineage
from backend.app.enterprise_audit import make_audit_event
from backend.app.trial.imports import TEMPLATES, _check_references, _check_values, _Lookup, _Report
from backend.app.trial.imports import quality_report, stored_value
from backend.app.trial.sample_data import SAMPLE_SOURCE, STORY_WINDOWS_BY
from backend.app.trial.sample_lot_impact import ORBIT, has_sample_lot_impact

LABEL = "Simulated, not a live connection"
SYSTEMS = {
    "PLM": {
        "name": "PLM (product lifecycle)",
        "objects": ["Items and revisions", "Bill of materials", "Change orders"],
    },
    "ERP": {
        "name": "ERP (manufacturing and shipping)",
        "objects": ["Suppliers", "Batches", "Batch where-used", "Shipments"],
    },
    "eQMS": {"name": "eQMS (quality system)", "objects": ["Complaints", "CAPAs"]},
}
# The sample's two earlier runs, read as the system each export comes from.
SYSTEM_OF = {"complaints": "eQMS", "distribution": "ERP"}
CAPA, CASE = "SAMPLE-CAPA-02", "SAMPLE-INV-001"


def _h(header: str, column: str) -> dict:
    return {"header": header, "column": column}


# file name -> (system, entity, headers mapped onto the template, headers not used). One problem row per run except
# the change orders and the suppliers.
RUNS: list[dict] = [
    {
        "system": "PLM",
        "entity": "products",
        "file_name": "items and revisions (Simulated).csv",
        "columns": [
            _h("Item Number", "product_id"),
            _h("Item Description", "product_name"),
            _h("Revision", "version"),
            _h("Release Date", "version_release_date"),
        ],
        "not_used": ["Lifecycle Phase", "Change Order"],
    },
    {
        "system": "PLM",
        "entity": "bom",
        "file_name": "bill of materials (Simulated).csv",
        "columns": [
            _h("Parent Item", "product_id"),
            _h("Parent Revision", "version"),
            _h("Component Item", "component_id"),
        ],
        "not_used": ["Find Number", "Quantity Per"],
    },
    {
        "system": "PLM",
        "entity": "changes",
        "file_name": "change orders (Simulated).csv",
        "columns": [
            _h("Change Number", "change_id"),
            _h("Change Category", "change_type"),
            _h("Description", "description"),
            _h("Affected Items", "affected_ids"),
        ],
        "not_used": ["Workflow Status"],
    },
    {
        "system": "ERP",
        "entity": "suppliers",
        "file_name": "suppliers (Simulated).csv",
        "columns": [_h("Vendor Number", "supplier_id"), _h("Vendor Name", "supplier_name"), _h("Status", "status")],
        "not_used": ["Payment Terms"],
    },
    {
        "system": "ERP",
        "entity": "lots",
        "file_name": "batches (Simulated).csv",
        "columns": [
            _h("Batch", "lot_id"),
            _h("Material", "product_id"),
            _h("Material Revision", "version"),
            _h("Production Date", "manufacture_date"),
            _h("Yield Quantity", "quantity"),
        ],
        "not_used": ["Storage Location"],
    },
    {
        "system": "ERP",
        "entity": "lot_genealogy",
        "file_name": "batch where-used (Simulated).csv",
        "columns": [
            _h("Batch", "lot_id"),
            _h("Component Material", "component_id"),
            _h("Component Batch", "component_lot_id"),
        ],
        "not_used": ["Consumed Quantity"],
    },
    {
        "system": "eQMS",
        "entity": "capas",
        "file_name": "CAPAs (Simulated).csv",
        "columns": [
            _h("CAPA Number", "capa_id"),
            _h("Title", "title"),
            _h("State", "status"),
            _h("Product", "product_id"),
            _h("Source Record", "investigation_id"),
        ],
        "not_used": ["Assigned Group"],
    },
]
RUN_BY_FILE = {run["file_name"]: run for run in RUNS}
ENTITIES = sorted({run["entity"] for run in RUNS})
# The run whose lineage marks the simulated sources as staged (a run every sample has rows for).
MARKER_ENTITY = "bom"


def _day(value) -> str:
    return value.date().isoformat() if value is not None else ""


def _rows(db: Session, tenant_id) -> dict[str, list[dict]]:
    """Each run's rows: OrbitCare 300's records as the systems' exports hold them, then the problem row."""
    t = {"t": tenant_id, "p": ORBIT}
    q = lambda sql: db.execute(text(sql), t).mappings().all()  # noqa: E731
    products = q(
        "SELECT p.product_identifier, p.name, v.version_identifier, v.release_timestamp FROM products p "
        "JOIN product_versions v ON v.tenant_id=p.tenant_id AND v.product_id=p.id "
        "WHERE p.tenant_id=:t AND p.product_identifier=:p ORDER BY v.release_timestamp, v.version_identifier"
    )
    items = [
        {
            "product_id": row["product_identifier"],
            "product_name": row["name"],
            "version": row["version_identifier"],
            "version_release_date": _day(row["release_timestamp"]),
        }
        for row in products
    ]
    bom = [
        {"product_id": ORBIT, "version": row["version_identifier"], "component_id": row["component_identifier"]}
        for row in q(
            "SELECT v.version_identifier, c.component_identifier FROM product_components pc "
            "JOIN product_versions v ON v.tenant_id=pc.tenant_id AND v.id=pc.product_version_id "
            "JOIN products p ON p.tenant_id=v.tenant_id AND p.id=v.product_id "
            "JOIN components c ON c.tenant_id=pc.tenant_id AND c.id=pc.component_id "
            "WHERE pc.tenant_id=:t AND p.product_identifier=:p ORDER BY v.version_identifier, c.component_identifier"
        )
    ]
    changes = [
        {
            "change_id": row["change_identifier"],
            "change_type": row["change_type"],
            "description": row["description"],
            "affected_ids": ";".join(sorted(set(row["affected"] or []))),
        }
        for row in q(
            "SELECT ch.change_identifier, ch.change_type, ch.description, array_agg(c.component_identifier) AS affected "
            "FROM changes ch JOIN reality_relationships rr ON rr.tenant_id=ch.tenant_id AND rr.source_entity_id=ch.id "
            "AND rr.source_entity_type='Change' AND rr.relationship_type='AFFECTS' AND rr.target_entity_type='Component' "
            "JOIN components c ON c.tenant_id=rr.tenant_id AND c.id=rr.target_entity_id "
            "WHERE ch.tenant_id=:t AND ch.source_system='MDARIX_SAMPLE' AND c.component_identifier LIKE :p || '-%' "
            "GROUP BY ch.id ORDER BY ch.change_identifier"
        )
    ]
    suppliers = [
        {"supplier_id": row["supplier_identifier"], "supplier_name": row["name"], "status": row["status"] or ""}
        for row in q(
            "SELECT DISTINCT s.supplier_identifier, s.name, s.status FROM suppliers s "
            "JOIN component_suppliers cs ON cs.tenant_id=s.tenant_id AND cs.supplier_id=s.id "
            "JOIN components c ON c.tenant_id=cs.tenant_id AND c.id=cs.component_id "
            "WHERE s.tenant_id=:t AND c.component_identifier LIKE :p || '-%' ORDER BY s.supplier_identifier"
        )
    ]
    lots = [
        {
            "lot_id": row["lot_identifier"],
            "product_id": ORBIT,
            "version": row["version_identifier"],
            "manufacture_date": _day(row["effective_timestamp"]),
            "quantity": str(row["quantity"]) if row["quantity"] is not None else "",
        }
        for row in q(
            "SELECT l.lot_identifier, v.version_identifier, l.effective_timestamp, l.quantity FROM lot_batches l "
            "JOIN product_versions v ON v.tenant_id=l.tenant_id AND v.id=l.product_version_id "
            "JOIN products p ON p.tenant_id=v.tenant_id AND p.id=v.product_id "
            "WHERE l.tenant_id=:t AND p.product_identifier=:p ORDER BY l.lot_identifier"
        )
    ]
    genealogy = [
        # The ERP holds its own batch numbers; MDARIX marks the sample's "(Sample)" (an identifier check refuses it).
        {
            "lot_id": row["lot_identifier"],
            "component_id": row["component_identifier"],
            "component_lot_id": row["lot"].removesuffix(" (Sample)"),
        }
        for row in q(
            "SELECT l.lot_identifier, c.component_identifier, lc.component_lot_identifier AS lot FROM lot_components lc "
            "JOIN lot_batches l ON l.tenant_id=lc.tenant_id AND l.id=lc.lot_batch_id "
            "JOIN components c ON c.tenant_id=lc.tenant_id AND c.id=lc.component_id "
            "WHERE lc.tenant_id=:t AND l.lot_identifier LIKE :p || '-%' ORDER BY l.lot_identifier, c.component_identifier"
        )
    ]
    capas = [
        {
            "capa_id": row["capa_identifier"],
            "title": row["title"],
            "status": row["status"] or "",
            "product_id": ORBIT,
            "investigation_id": row["investigation_identifier"] or "",
        }
        for row in db.execute(
            text(
                "SELECT k.capa_identifier, k.title, k.status, i.investigation_identifier FROM capas k "
                "LEFT JOIN investigations i ON i.tenant_id=k.tenant_id AND i.id=k.investigation_id "
                "WHERE k.tenant_id=:t AND k.capa_identifier=:k"
            ),
            {"t": tenant_id, "k": CAPA},
        ).mappings()
    ]
    # The problem rows: what a real export holds now and then; the import's own checks set each aside.
    rev_b = next((row for row in items if row["version"] == "Rev B"), None)
    if rev_b:
        items.append(dict(rev_b))  # Rev B repeated
    bom.append({"product_id": ORBIT, "version": "Rev B", "component_id": f"{ORBIT}-C9"})  # an unknown part
    lots.append(
        {
            "lot_id": f"{ORBIT}-LOT-009",
            "product_id": ORBIT,
            "version": "Rev B",
            "manufacture_date": lots[-1]["manufacture_date"] if lots else "",
            "quantity": "12O",  # a letter O typed for a zero
        }
    )
    sensor = next(
        (row for row in genealogy if row["lot_id"] == f"{ORBIT}-LOT-003" and row["component_id"] == f"{ORBIT}-C1"), None
    )
    if sensor:
        genealogy.append(dict(sensor))  # lot 003's sensor row repeated
    capas.append(
        {
            "capa_id": "SAMPLE-CAPA-07",
            "title": "Review alarm thresholds after field feedback (Sample)",
            "status": "Open",
            "product_id": ORBIT,
            "investigation_id": "SAMPLE-INV-099",  # names an investigation that is not loaded
        }
    )
    return {
        "products": items,
        "bom": bom,
        "changes": changes,
        "suppliers": suppliers,
        "lots": lots,
        "lot_genealogy": genealogy,
        "capas": capas,
    }


def has_sample_sources(db: Session, tenant_id) -> bool:
    return (
        db.query(ImportLineage.id)
        .filter(
            ImportLineage.tenant_id == tenant_id,
            ImportLineage.source == SAMPLE_SOURCE,
            ImportLineage.entity == MARKER_ENTITY,
        )
        .first()
        is not None
    )


def _check(db: Session, tenant_id, entity: str, rows: list[dict]) -> tuple[list, list]:
    """The import's own checks on the run's rows: (written lines, set-aside lines with their reasons)."""
    report = _Report()
    lines = [(line, dict(row)) for line, row in enumerate(rows, 2)]
    _check_values(entity, lines, report, "ISO", False)
    checked = [(line, row) for line, row in lines if line not in report.row_problems]
    _check_references(entity, checked, _Lookup(db, tenant_id), report)
    written = [(line, row) for line, row in lines if line not in report.row_problems]
    aside = [(line, row, report.row_problems[line]) for line, row in lines if line in report.row_problems]
    return written, aside


def stage_sample_sources(db: Session, tenant_id, now: datetime) -> dict:
    """Record the seven simulated runs (once, after the sample's lot impact). Adds no business row."""
    if not has_sample_lot_impact(db, tenant_id) or has_sample_sources(db, tenant_id):
        return {"created": False}
    rows = _rows(db, tenant_id)
    staged = {}
    for run in RUNS:
        entity = run["entity"]
        written, aside = _check(db, tenant_id, entity, rows[entity])
        import_ref = uuid.uuid4()
        version = import_lineage.mapping_version(entity, run["columns"], "ISO")
        import_lineage.write(
            db, tenant_id, import_ref, entity, TEMPLATES[entity]["required"], written, version, SAMPLE_SOURCE
        )
        import_quarantine.store(db, tenant_id, import_ref, entity, SAMPLE_SOURCE, aside, stored_value)
        report = quality_report(len(written) + len(aside), len(written), len(aside), 0, not_used=run["not_used"])
        report["rows_duplicate"] = sum(1 for _, _, problems in aside if any("Duplicate of row" in p for p in problems))
        db.add(
            make_audit_event(
                tenant_id=tenant_id,
                actor_ref=STORY_WINDOWS_BY,
                action="TRIAL_DATA_IMPORTED",
                entity_type="TrialImport",
                # No created or updated counts: the records are the sample's own, nothing waits for signals.
                details={
                    "entity": entity,
                    "sample": True,
                    "simulated_system": run["system"],
                    "file_name": run["file_name"],
                    "import_ref": str(import_ref),
                    "mapping_version": version,
                    "quarantined_rows": len(aside),
                    "rejected_rows": len(aside),
                    "masked_values": 0,
                    "quality_report": report,
                },
                created_at=now,
            )
        )
        staged[run["file_name"]] = {"written": len(written), "set_aside": len(aside)}
    db.flush()
    return {"created": True, "runs": staged}
