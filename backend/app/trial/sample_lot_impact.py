"""The sample's lot genealogy and distribution (T-G5 for 0.10.61): what a case's Lot impact shows on the sample data.

- **Genealogy** (``lot_components``): the OrbitCare 300 Rev B pressure sensor (NovaSense Components) comes from sensor
  lot ``NS-SL-2417 (Sample)`` in lots 003 and 004 (the two lots with most pressure-alarm complaints) and in three lots
  without complaints, 006 to 008; lot 005 used the next sensor lot, ``NS-SL-2533 (Sample)``. Each lot also names its
  control board lot (Precision Sensors Ltd), so the factor picker has more than one choice.
- **Three lots without complaints** (006 to 008, Rev B), made the same day as lot 005. Lot 005 now releases 60 units
  and each new lot 30: Rev B still releases 450 units on the same day, so the trend check's units in the field, the
  OrbitCare rise and the signal's numbers stay exactly as they were. No complaint is added or moved.
- **Distribution** to fictional consignees "(Sample)" in India, the US and EU countries, with units still in stock;
  lot 008 has no distribution imported (the "distribution not imported" state). A PulseWatch lot shipped more units
  than it released, so the data-quality report's flag shows.
- **One import run**, "Sample distribution export.csv": its lineage, one row set aside (a lot not loaded) and the
  shipped-beyond-released flag in its data-quality report.

Every row is marked ``MDARIX_SAMPLE`` (lineage and quarantine in ``source``), so sample removal takes it; genealogy
rows go with their lots. Idempotent; flushes but never commits (the caller owns the transaction).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from backend.app import import_lineage, import_quarantine
from backend.app.db.models.foundation import Component, LotBatch, LotComponent
from backend.app.db.models.lot_impact import LotDistribution
from backend.app.enterprise_audit import make_audit_event
from backend.app.trial import business_imports
from backend.app.trial.imports import TEMPLATES, _check_references, _Lookup, _Report, stored_value
from backend.app.trial.imports import quality_report
from backend.app.trial.sample_data import SAMPLE_SOURCE, STORY_WINDOWS_BY

ORBIT = "SAMPLE-ORBIT-300"
SENSOR = f"{ORBIT}-C1"
BOARD = f"{ORBIT}-C2"
SENSOR_LOT, NEXT_SENSOR_LOT = "NS-SL-2417 (Sample)", "NS-SL-2533 (Sample)"
# Lot number -> (sensor lot, control board lot).
GENEALOGY = {
    3: (SENSOR_LOT, "CB-1180 (Sample)"),
    4: (SENSOR_LOT, "CB-1181 (Sample)"),
    5: (NEXT_SENSOR_LOT, "CB-1204 (Sample)"),
    6: (SENSOR_LOT, "CB-1204 (Sample)"),
    7: (SENSOR_LOT, "CB-1204 (Sample)"),
    8: (SENSOR_LOT, "CB-1204 (Sample)"),
}
# Units released: lot 005 and the three new lots release 150 together, as lot 005 alone did (the trend check's units).
NEW_LOTS = {6: 30, 7: 30, 8: 30}
LOT_005_UNITS, LOT_005_BEFORE = 60, 150
SAMPLE_FILE = "Sample distribution export.csv"
SAMPLE_ACTOR = STORY_WINDOWS_BY
CEDAR = ("Cedar Plains Medical Center (Sample)", "US", "Hospital", "SMP-C-1001")
BLUEGATE = ("Bluegate Medical Supply (Sample)", "US", "Distributor", "SMP-C-1002")
ASHOKA = ("Ashoka Lakes Hospital (Sample)", "IN", "Hospital", "SMP-C-2001")
DECCAN = ("Deccan Medical Distributors (Sample)", "IN", "Distributor", "SMP-C-2002")
RHEINWALD = ("Rheinwald Clinic (Sample)", "DE", "Hospital", "SMP-C-3001")
BELVUE = ("Centre Hospitalier Belvue (Sample)", "FR", "Hospital", "SMP-C-3002")
BENELUX = ("MedLogistiek Benelux (Sample)", "NL", "Distributor", "SMP-C-3003")
# Lot -> [(consignee, units, days after the lot was made)]. Lot 008: no distribution imported.
SHIPMENTS = {
    f"{ORBIT}-LOT-003": [(CEDAR, 60, 5), (BLUEGATE, 40, 10), (ASHOKA, 30, 15), (RHEINWALD, 20, 20)],
    f"{ORBIT}-LOT-004": [(BLUEGATE, 50, 6), (DECCAN, 40, 10), (BELVUE, 30, 18)],
    f"{ORBIT}-LOT-005": [(ASHOKA, 20, 6), (BENELUX, 20, 10)],
    f"{ORBIT}-LOT-006": [(RHEINWALD, 10, 8), (CEDAR, 10, 12)],
    f"{ORBIT}-LOT-007": [(DECCAN, 12, 9), (BELVUE, 8, 15)],
    # 410 units shipped of the 400 the lot released: the data-quality report flags it.
    "SAMPLE-PULSE-410-LOT-002": [(CEDAR, 250, 10), (ASHOKA, 160, 20)],
}
# The row the sample's import set aside: a lot that is not loaded.
SET_ASIDE = {
    "lot_id": f"{ORBIT}-LOT-099",
    "consignee": BLUEGATE[0],
    "country": "US",
    "quantity": "25",
    "ship_date": "",
}


def has_sample_lot_impact(db: Session, tenant_id) -> bool:
    return (
        db.query(LotDistribution.id)
        .filter(LotDistribution.tenant_id == tenant_id, LotDistribution.source_system == SAMPLE_SOURCE)
        .first()
        is not None
    )


def _lots(db: Session, tenant_id) -> dict[str, LotBatch]:
    return {
        lot.lot_identifier: lot
        for lot in db.query(LotBatch).filter(LotBatch.tenant_id == tenant_id, LotBatch.source_system == SAMPLE_SOURCE)
    }


def stage_sample_lot_impact(db: Session, tenant_id, now: datetime) -> dict:
    """Add the lots without complaints, the genealogy, the distribution and its import run (once)."""
    if has_sample_lot_impact(db, tenant_id):
        return {"created": False}
    lots = _lots(db, tenant_id)
    base = lots.get(f"{ORBIT}-LOT-005")
    components = {
        row.component_identifier: row
        for row in db.query(Component).filter(
            Component.tenant_id == tenant_id,
            Component.component_identifier.in_([SENSOR, BOARD]),
            # Rev B's parts: since 0.10.94 OrbitCare Rev A has a sensor of its own with the same identifier.
            Component.revision == "Rev B",
        )
    }
    if base is None or set(components) != {SENSOR, BOARD}:
        return {"created": False}
    # Same day, version and site as lot 005: the units in the field over any window stay those of lot 005 alone.
    if base.quantity in (None, LOT_005_BEFORE):
        base.quantity = LOT_005_UNITS
    for number, units in NEW_LOTS.items():
        identifier = f"{ORBIT}-LOT-{number:03d}"
        if identifier in lots:
            continue
        lot = LotBatch(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            lot_identifier=identifier,
            product_version_id=base.product_version_id,
            manufacturing_site_id=base.manufacturing_site_id,
            status="active",
            quantity=units,
            source_identifier=identifier,
            source_system=SAMPLE_SOURCE,
            source_timestamp=base.source_timestamp,
            effective_timestamp=base.effective_timestamp,
            recorded_timestamp=base.recorded_timestamp,
            ingestion_timestamp=base.ingestion_timestamp,
            created_at=base.created_at,
            updated_at=base.updated_at,
        )
        db.add(lot)
        lots[identifier] = lot
    db.flush()
    genealogy = 0
    for number, (sensor_lot, board_lot) in GENEALOGY.items():
        lot = lots[f"{ORBIT}-LOT-{number:03d}"]
        for component, part in ((components[SENSOR], sensor_lot), (components[BOARD], board_lot)):
            db.add(
                LotComponent(
                    id=uuid.uuid4(),
                    tenant_id=tenant_id,
                    lot_batch_id=lot.id,
                    component_id=component.id,
                    component_lot_identifier=part,
                    created_at=lot.created_at,
                )
            )
            genealogy += 1
    rows = []
    for identifier, shipments in SHIPMENTS.items():
        lot = lots.get(identifier)
        if lot is None:
            continue
        made = lot.effective_timestamp or lot.created_at
        for (consignee, country, kind, reference), units, after in shipments:
            shipped = min(made + timedelta(days=after), now).date()
            db.add(
                LotDistribution(
                    id=uuid.uuid4(),
                    tenant_id=tenant_id,
                    lot_batch_id=lot.id,
                    consignee=consignee,
                    consignee_type=kind,
                    consignee_reference=reference,
                    country=country,
                    quantity=units,
                    ship_date=shipped,
                    source_system=SAMPLE_SOURCE,
                    created_at=now,
                    updated_at=now,
                )
            )
            rows.append({"lot_id": identifier, "consignee": consignee, "country": country, "ship_date": str(shipped)})
    db.flush()
    import_ref = uuid.uuid4()
    columns = [{"header": "Ship To Name", "column": "consignee"}, {"header": "Ship Date", "column": "ship_date"}]
    version = import_lineage.mapping_version("distribution", columns, "ISO")
    lines = list(enumerate(rows, 2))
    import_lineage.write(
        db, tenant_id, import_ref, "distribution", TEMPLATES["distribution"]["required"], lines, version, SAMPLE_SOURCE
    )
    # The set-aside row's reasons are the import's own checks, so they read as a trial's own import gives them.
    report = _Report()
    aside_line = len(rows) + 2
    aside = [(aside_line, dict(SET_ASIDE, ship_date=str(now.date())))]
    _check_references("distribution", aside, _Lookup(db, tenant_id), report)
    set_aside = [(line, row, report.row_problems.get(line, [])) for line, row in aside]
    import_quarantine.store(db, tenant_id, import_ref, "distribution", SAMPLE_SOURCE, set_aside, stored_value)
    quality = quality_report(len(rows) + 1, len(rows), 1, 0)
    quality["flags"] = business_imports.distribution_flags(db, tenant_id, SHIPMENTS)
    db.add(
        make_audit_event(
            tenant_id=tenant_id,
            actor_ref=SAMPLE_ACTOR,
            action="TRIAL_DATA_IMPORTED",
            entity_type="TrialImport",
            # No created or updated counts: nothing waits for signals after it.
            details={
                "entity": "distribution",
                "sample": True,
                "file_name": SAMPLE_FILE,
                "import_ref": str(import_ref),
                "mapping_version": version,
                "quarantined_rows": 1,
                "rejected_rows": 1,
                "masked_values": 0,
                "skip_problem_rows": True,
                "mask_personal_data": False,
                "quality_report": quality,
            },
            created_at=now,
        )
    )
    db.flush()
    return {
        "created": True,
        "lots": len(NEW_LOTS),
        "genealogy": genealogy,
        "shipments": len(rows),
        "flags": len(quality["flags"]),
    }
