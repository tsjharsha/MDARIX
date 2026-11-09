"""The sample's supply chain for Product 360 and Supplier 360 (W1, 0.10.94, spec 5.2):

- **S1, Rev A configurations.** OrbitCare 300 Rev A gets its own pressure sensor, ``SAMPLE-ORBIT-300-C1`` revision
  "Rev A", supplied by Precision Sensors Ltd from day -360; with the control board and power module it makes Rev A's
  configuration, so "Compare with Rev A" shows the sensor's supplier change. PulseWatch and VentraLink Rev A use their
  three components too (the flagship SAMPLE-RV-11 is on PulseWatch Rev A). The Rev A sensor has no AFFECTS link, so no
  change shows on any Rev A trend card; no complaint, lot or quantity changes, so the trend check, the signals and the
  day 0/7/15/29 story read the same.
- **S2, evidence links.** SAMPLE-EV-001 (the supplier change record) and SAMPLE-EV-002 (the incoming inspection
  results) are linked to NovaSense Components and to the Rev B pressure sensor, so Supplier 360 lists them.

Not seeded (OD-6): a second product with NovaSense parts, and Rev A lot genealogy. Not seeded yet (OD-4, held for the
owner): SAMPLE-CAPA-02's link to SAMPLE-INV-001, which closure checks, Readiness and report worksheets also read.

Every new row is reached from sample rows through its foreign keys (components, versions, suppliers, evidence), so
sample removal, restart and the sample clock take it. Idempotent; flushes but never commits.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from backend.app.db.models.evidence_intelligence import EvidenceEntityLink
from backend.app.db.models.foundation import (
    Component,
    ComponentSupplier,
    Evidence,
    Product,
    ProductComponent,
    ProductVersion,
    Supplier,
)
from backend.app.trial.sample_data import SAMPLE_SOURCE, _stamp

ORBIT = "SAMPLE-ORBIT-300"
PRODUCTS = (ORBIT, "SAMPLE-PULSE-410", "SAMPLE-VENTRA-250")
SENSOR, REV_A, REV_B = f"{ORBIT}-C1", "Rev A", "Rev B"
REV_A_DAYS = 360
EVIDENCE = ("SAMPLE-EV-001", "SAMPLE-EV-002")


def refresh(db: Session, tenant_id, apply: bool, now: datetime) -> int:
    """The rows S1 and S2 add where they are missing (all of them in a new trial): counted, and added with ``apply``.
    0 when the organization has no sample."""
    versions = {
        (identifier, revision): version
        for version, identifier, revision in db.query(
            ProductVersion, Product.product_identifier, ProductVersion.version_identifier
        )
        .join(Product, (Product.tenant_id == ProductVersion.tenant_id) & (Product.id == ProductVersion.product_id))
        .filter(
            ProductVersion.tenant_id == tenant_id,
            Product.source_system == SAMPLE_SOURCE,
            Product.product_identifier.in_(PRODUCTS),
        )
    }
    suppliers = {
        row.supplier_identifier: row
        for row in db.query(Supplier).filter(Supplier.tenant_id == tenant_id, Supplier.source_system == SAMPLE_SOURCE)
    }
    if len(versions) < 2 * len(PRODUCTS) or not {"SAMPLE-SUP-A", "SAMPLE-SUP-B"} <= set(suppliers):
        return 0
    owed = 0
    components = {
        (row.component_identifier, row.revision): row
        for row in db.query(Component).filter(
            Component.tenant_id == tenant_id, Component.source_system == SAMPLE_SOURCE
        )
    }
    sensor_a = components.get((SENSOR, REV_A))
    if sensor_a is None:
        owed += 2
        if apply:
            sensor_a = Component(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                component_identifier=SENSOR,
                name="Pressure Sensor (Sample)",
                revision=REV_A,
                description="Pressure Sensor used in OrbitCare 300 Rev A.",
                status="active",
                source_identifier=f"{SENSOR}-A",
                **_stamp(now, REV_A_DAYS),
            )
            db.add(sensor_a)
            db.flush()
            db.add(
                ComponentSupplier(
                    id=uuid.uuid4(),
                    tenant_id=tenant_id,
                    component_id=sensor_a.id,
                    supplier_id=suppliers["SAMPLE-SUP-A"].id,
                    effective_timestamp=now - timedelta(days=REV_A_DAYS),
                    created_at=now,
                )
            )
    linked = {
        (row.product_version_id, row.component_id)
        for row in db.query(ProductComponent.product_version_id, ProductComponent.component_id).filter(
            ProductComponent.tenant_id == tenant_id
        )
    }
    for identifier in PRODUCTS:
        rev_a = versions[(identifier, REV_A)]
        for index in (1, 2, 3):
            part_id = f"{identifier}-C{index}"
            # OrbitCare's Rev B sensor is NovaSense's; Rev A has its own (Precision Sensors).
            component = sensor_a if part_id == SENSOR else components.get((part_id, REV_B))
            if component is None:
                owed += part_id == SENSOR  # a dry run counts the link of the sensor it would add
                continue
            if (rev_a.id, component.id) in linked:
                continue
            owed += 1
            if apply:
                db.add(
                    ProductComponent(
                        id=uuid.uuid4(),
                        tenant_id=tenant_id,
                        product_version_id=rev_a.id,
                        component_id=component.id,
                        relationship_status="active",
                        effective_timestamp=now - timedelta(days=REV_A_DAYS),
                        created_at=now,
                    )
                )
    sensor_b = components.get((SENSOR, REV_B))
    evidence = db.query(Evidence).filter(
        Evidence.tenant_id == tenant_id,
        Evidence.source_system == SAMPLE_SOURCE,
        Evidence.evidence_identifier.in_(EVIDENCE),
    )
    links = {
        (row.evidence_id, row.entity_type, row.entity_id)
        for row in db.query(EvidenceEntityLink).filter(
            EvidenceEntityLink.tenant_id == tenant_id, EvidenceEntityLink.entity_type.in_(["Supplier", "Component"])
        )
    }
    targets = [("Supplier", suppliers["SAMPLE-SUP-B"].id, "SAMPLE-SUP-B")]
    if sensor_b is not None:
        targets.append(("Component", sensor_b.id, f"{SENSOR} {REV_B}"))
    for item in evidence:
        for entity_type, entity_id, reference in targets:
            if (item.id, entity_type, entity_id) in links:
                continue
            owed += 1
            if apply:
                db.add(
                    EvidenceEntityLink(
                        id=uuid.uuid4(),
                        tenant_id=tenant_id,
                        evidence_id=item.id,
                        entity_type=entity_type,
                        entity_id=entity_id,
                        raw_reference=reference,
                        resolution_status="RESOLVED",
                    )
                )
    if apply:
        db.flush()
    return owed


def stage_sample_supply(db: Session, tenant_id, now: datetime) -> dict:
    added = refresh(db, tenant_id, apply=True, now=now)
    return {"created": bool(added), "rows": added}
