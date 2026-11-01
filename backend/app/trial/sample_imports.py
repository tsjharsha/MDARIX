"""The sample's import run (T-SAM for 0.10.56): what a free trial's own Excel or CSV import shows, on the sample data.

- **One import run**, "Sample complaints export.xlsx": every sample complaint is one of its rows (its lineage, R16:
  the run, the row and the mapping version), and two rows were set aside with their reasons (stored quarantine, R14),
  so its data-quality report (R17) reads, writes, sets aside and balances like any other run. Its audit record is
  ``TRIAL_DATA_IMPORTED`` marked ``sample`` and holds no created or updated counts, so nothing waits for signals
  after it and no count elsewhere changes.
- **Set aside**: SAMPLE-RJ-01 has no description; SAMPLE-RJ-02 names a caller and a phone number and has a date that
  does not exist, and suggests harm (a patient taken to hospital), so it lists first. Its personal details are stored
  as placeholders, as the quarantine stores every set-aside row.
- **Regulatory identity (G2a)**: the three sample products carry a UDI-DI (GS1 restricted-circulation numbers, so never
  a real device) and a GMDN code and term; the sample's problem codes for alarms and flow map to IMDRF Annex A codes,
  approved by the sample's reviewer. The IMDRF terms themselves are read from the IMDRF release loaded
  (scripts/load_imdrf_annex.py); none is typed in here.

Every row is marked ``MDARIX_SAMPLE`` (lineage and quarantine in ``source``, mappings by their proposer
``system:trial-sample``), so sample removal takes it. No complaint, product or lot is added: every count quoted
elsewhere stays. Idempotent; flushes but never commits (the caller owns the transaction).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy.orm import Session

from backend.app import import_lineage, import_quarantine
from backend.app.db.models.foundation import Complaint, Product
from backend.app.db.models.ingestion import ImportLineage
from backend.app.db.models.regulatory_reference import ImdrfCodeMapping
from backend.app.enterprise_audit import make_audit_event
from backend.app.trial.imports import TEMPLATES, _check_values, _mask, _personal_data, _Report, quality_report
from backend.app.trial.sample_data import SAMPLE_SOURCE, STORY_WINDOWS_BY

SAMPLE_FILE = "Sample complaints export.xlsx"
SAMPLE_ACTOR = STORY_WINDOWS_BY  # "system:trial-sample"
# The export's headers as the sample's quality system names them, read under the template's columns.
SAMPLE_COLUMNS = [
    {"header": "Complaint Number", "column": "complaint_id"},
    {"header": "Product Code", "column": "product_id"},
    {"header": "Event Description", "column": "description"},
    {"header": "Event Date", "column": "event_date"},
]
# The two rows the sample's import set aside, as the export had them; their reasons are the import's own checks
# (``_set_aside``), so they read exactly as a trial's own import would give them.
SET_ASIDE = [
    {"complaint_id": "SAMPLE-RJ-01", "product_id": "SAMPLE-PULSE-410", "description": "", "event_date": ""},
    {
        "complaint_id": "SAMPLE-RJ-02",
        "product_id": "SAMPLE-ORBIT-300",
        "description": "Pump alarm did not stop; the patient was taken to hospital. Caller Maria Lopez, +1 415 555 0134.",
        "event_date": "2026-09-31",
    },
]
# identifier -> (UDI-DI, GMDN code, GMDN term). The UDI-DIs use GS1's restricted-circulation prefix 04. No GMDN code:
# the sample shows the term with "sample" in place of a number until real codes are verified (owner, 1 Nov 2026).
SAMPLE_IDENTITY = {
    "SAMPLE-ORBIT-300": ("04000000030010", None, "General-purpose infusion pump"),
    "SAMPLE-PULSE-410": ("04000000041016", None, "Multiple-parameter patient monitor"),
    "SAMPLE-VENTRA-250": ("04000000025016", None, "Intensive-care ventilator"),
}
# The IMDRF release the sample's links name; its terms show once that release is loaded.
SAMPLE_IMDRF_RELEASE = "2025"
# The sample's problem codes -> IMDRF Annex A codes (A14 infusion or flow problem, A16 protective measures problem,
# alarms among them). Under-infusion without an alarm links to both: one code may map to several.
SAMPLE_IMDRF_LINKS = {
    "PRESSURE_ALARM": ("A16",),
    "UNDER_INFUSION_NO_ALARM": ("A14", "A16"),
    "FREE_FLOW_DOOR": ("A14",),
    "ALARM_VOLUME_LOW": ("A16",),
}
SAMPLE_REVIEWER = "system:trial-sample-reviewer"
PROBLEM_CODES = "problem_code"


def _set_aside(first_line: int) -> list[tuple[int, dict, list[str]]]:
    """The set-aside rows with the problems the import's checks find in them (personal data refused, not masked)."""
    report = _Report()
    rows = [(line, dict(row)) for line, row in enumerate(SET_ASIDE, first_line)]
    _check_values("complaints", rows, report, "ISO", False)
    return [(line, row, report.row_problems[line]) for line, row in rows]


def has_sample_import(db: Session, tenant_id) -> bool:
    return (
        db.query(ImportLineage.id)
        .filter(ImportLineage.tenant_id == tenant_id, ImportLineage.source == SAMPLE_SOURCE)
        .first()
        is not None
    )


def stage_sample_import(db: Session, tenant_id, now: datetime) -> dict:
    """Add the sample's import run, its set-aside rows, the products' identity and the IMDRF links (once)."""
    if has_sample_import(db, tenant_id):
        return {"created": False}
    complaints = (
        db.query(Complaint.complaint_identifier, Product.product_identifier)
        .join(Product, (Product.id == Complaint.product_id) & (Product.tenant_id == Complaint.tenant_id))
        .filter(Complaint.tenant_id == tenant_id, Complaint.source_system == SAMPLE_SOURCE)
        .order_by(Complaint.complaint_timestamp, Complaint.complaint_identifier)
        .all()
    )
    if not complaints:
        return {"created": False}
    imported_at = now  # the lineage rows carry the same moment
    import_ref = uuid.uuid4()
    version = import_lineage.mapping_version("complaints", SAMPLE_COLUMNS, "ISO")
    rows = [(line, {"complaint_id": c, "product_id": p}) for line, (c, p) in enumerate(complaints, 2)]
    import_lineage.write(
        db, tenant_id, import_ref, "complaints", TEMPLATES["complaints"]["required"], rows, version, SAMPLE_SOURCE
    )
    set_aside = _set_aside(len(rows) + 2)
    import_quarantine.store(db, tenant_id, import_ref, "complaints", SAMPLE_SOURCE, set_aside, _personal_data, _mask)
    for item in db.query(Product).filter(Product.tenant_id == tenant_id, Product.source_system == SAMPLE_SOURCE):
        if item.product_identifier in SAMPLE_IDENTITY:
            item.udi_di, item.gmdn_code, item.gmdn_term = SAMPLE_IDENTITY[item.product_identifier]
    links = 0
    for code, annexes in SAMPLE_IMDRF_LINKS.items():
        for imdrf_code in annexes:
            db.add(
                ImdrfCodeMapping(
                    tenant_id=tenant_id,
                    customer_system=PROBLEM_CODES,
                    customer_code=code,
                    customer_term=code.replace("_", " ").capitalize(),
                    release=SAMPLE_IMDRF_RELEASE,
                    annex="A",
                    imdrf_code=imdrf_code,
                    status="APPROVED",
                    proposed_by=SAMPLE_ACTOR,
                    proposed_at=imported_at,
                    reviewed_by=SAMPLE_REVIEWER,
                    reviewed_at=imported_at,
                    review_note="Sample mapping.",
                )
            )
            links += 1
    report = quality_report(len(rows) + len(set_aside), len(rows), len(set_aside), 0)
    db.add(
        make_audit_event(
            tenant_id=tenant_id,
            actor_ref=SAMPLE_ACTOR,
            action="TRIAL_DATA_IMPORTED",
            entity_type="TrialImport",
            # No created or updated counts: the sample's complaints are already there, nothing waits for signals.
            details={
                "entity": "complaints",
                "sample": True,
                "file_name": SAMPLE_FILE,
                "import_ref": str(import_ref),
                "mapping_version": version,
                "quarantined_rows": len(set_aside),
                "rejected_rows": len(set_aside),
                "masked_values": 0,
                "skip_problem_rows": True,
                "mask_personal_data": False,
                "quality_report": report,
            },
            created_at=imported_at,
        )
    )
    db.flush()
    return {"created": True, "lineage": len(rows), "set_aside": len(set_aside), "imdrf_links": links}
