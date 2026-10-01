"""Sample dataset loaded into every new free-trial workspace.

It tells one realistic story so a new user sees value without sharing data: OrbitCare 300 Rev B changed the
pressure-sensor supplier, and pressure-alarm complaints rose afterwards, concentrated in two lots. Two other
devices give the dashboard a realistic background. Every record is synthetic, carries no personal data, is marked
with ``SAMPLE_SOURCE`` and "(Sample)" in its name, and is written only to the given tenant.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from backend.app.db.models.foundation import (
    Change,
    Complaint,
    Component,
    ComponentSupplier,
    Evidence,
    Investigation,
    InvestigationComplaint,
    InvestigationEvidence,
    LotBatch,
    ManufacturingSite,
    Product,
    ProductComponent,
    ProductVersion,
    Supplier,
)

SAMPLE_SOURCE = "MDARIX_SAMPLE"

# (identifier, name, family, symptom, complaint pattern). The pattern lists days-ago for each complaint:
# OrbitCare complaints cluster after the day-75 Rev B release; the others stay flat.
_PRODUCTS = [
    (
        "SAMPLE-ORBIT-300",
        "OrbitCare 300 Infusion Pump (Sample)",
        "Infusion therapy",
        "pressure alarm during infusion",
        [170, 150, 128, 96, 70, 64, 58, 51, 47, 41, 36, 33, 29, 24, 20, 16, 11, 6],
    ),
    (
        "SAMPLE-PULSE-410",
        "PulseWatch 410 Patient Monitor (Sample)",
        "Patient monitoring",
        "SpO2 signal dropout",
        [160, 131, 102, 77, 45, 19],
    ),
    (
        "SAMPLE-VENTRA-250",
        "VentraLink 250 Respiratory Controller (Sample)",
        "Respiratory support",
        "flow reading variance",
        [140, 99, 52, 14],
    ),
]


def _stamp(now: datetime, days_ago: int) -> dict:
    value = now - timedelta(days=days_ago)
    return {
        "source_system": SAMPLE_SOURCE,
        "source_timestamp": value,
        "effective_timestamp": value,
        "recorded_timestamp": value,
        "ingestion_timestamp": now,
        "created_at": value,
        "updated_at": value,
    }


def has_sample_data(db: Session, tenant_id) -> bool:
    return (
        db.query(Product.id).filter(Product.tenant_id == tenant_id, Product.source_system == SAMPLE_SOURCE).first()
        is not None
    )


def seed_sample_workspace(db: Session, tenant_id, now: datetime | None = None) -> dict:
    """Add the sample dataset to one tenant. Idempotent; flushes but never commits (the caller owns the transaction)."""
    if has_sample_data(db, tenant_id):
        return {"created": False}
    now = now or datetime.now(timezone.utc)
    counts = {"products": 0, "lots": 0, "complaints": 0, "investigations": 0, "evidence": 0}

    site = ManufacturingSite(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        site_identifier="SAMPLE-SITE-01",
        name="Assembly Site 1 (Sample)",
        location="Synthetic",
        status="active",
        source_identifier="SAMPLE-SITE-01",
        **_stamp(now, 400),
    )
    supplier_a = Supplier(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        supplier_identifier="SAMPLE-SUP-A",
        name="Precision Sensors Ltd (Sample)",
        status="active",
        source_identifier="SAMPLE-SUP-A",
        **_stamp(now, 400),
    )
    supplier_b = Supplier(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        supplier_identifier="SAMPLE-SUP-B",
        name="NovaSense Components (Sample)",
        status="active",
        source_identifier="SAMPLE-SUP-B",
        **_stamp(now, 120),
    )
    db.add_all([site, supplier_a, supplier_b])
    db.add(
        Change(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            change_identifier="SAMPLE-CHG-014",
            change_type="Supplier change",
            description=(
                "OrbitCare 300 Rev B: pressure sensor sourced from NovaSense Components instead of Precision "
                "Sensors Ltd. Incoming inspection sampling reduced from 32 to 13 units per lot."
            ),
            event_timestamp=now - timedelta(days=80),
            source_identifier="SAMPLE-CHG-014",
            **_stamp(now, 80),
        )
    )
    db.flush()

    for index, (identifier, name, family, symptom, complaint_days) in enumerate(_PRODUCTS, 1):
        product = Product(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            product_identifier=identifier,
            name=name,
            description=f"Sample {family.lower()} device used to explore MDARIX.",
            lifecycle_status="active",
            product_family=family,
            manufacturer_context="Sample manufacturer",
            source_identifier=identifier,
            **_stamp(now, 380),
        )
        db.add(product)
        db.flush()
        counts["products"] += 1
        versions = []
        for revision, released in (("Rev A", 360), ("Rev B", 75)):
            version = ProductVersion(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                product_id=product.id,
                version_identifier=revision,
                description=f"{name} {revision}",
                lifecycle_status="active",
                release_timestamp=now - timedelta(days=released),
                source_identifier=f"{identifier}-{revision[-1]}",
                **_stamp(now, released),
            )
            db.add(version)
            versions.append(version)
        db.flush()

        components = []
        for c_index, label in enumerate(("Pressure Sensor", "Control Board", "Power Module"), 1):
            component = Component(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                component_identifier=f"{identifier}-C{c_index}",
                name=f"{label} (Sample)",
                revision="Rev B",
                description=f"{label} used in {name}.",
                status="active",
                source_identifier=f"{identifier}-C{c_index}",
                **_stamp(now, 90),
            )
            db.add(component)
            components.append(component)
        db.flush()
        for c_index, component in enumerate(components, 1):
            # The OrbitCare pressure sensor is the component whose supplier changed.
            supplier = supplier_b if (index == 1 and c_index == 1) else supplier_a
            db.add(
                ComponentSupplier(
                    id=uuid.uuid4(),
                    tenant_id=tenant_id,
                    component_id=component.id,
                    supplier_id=supplier.id,
                    effective_timestamp=now - timedelta(days=80),
                    created_at=now,
                )
            )
            db.add(
                ProductComponent(
                    id=uuid.uuid4(),
                    tenant_id=tenant_id,
                    product_version_id=versions[-1].id,
                    component_id=component.id,
                    relationship_status="active",
                    effective_timestamp=now - timedelta(days=75),
                    created_at=now,
                )
            )

        lots = []
        for lot_index, (built, version) in enumerate(
            ((200, versions[0]), (140, versions[0]), (70, versions[1]), (50, versions[1]), (30, versions[1])), 1
        ):
            lot = LotBatch(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                lot_identifier=f"{identifier}-LOT-{lot_index:03d}",
                product_version_id=version.id,
                manufacturing_site_id=site.id,
                status="active",
                source_identifier=f"{identifier}-LOT-{lot_index:03d}",
                **_stamp(now, built),
            )
            db.add(lot)
            lots.append(lot)
        db.flush()
        counts["lots"] += len(lots)

        complaints = []
        for c_index, days_ago in enumerate(complaint_days, 1):
            after_release = days_ago < 75
            if index == 1 and after_release:
                # Most post-release OrbitCare complaints come from lots 3 and 4 (first NovaSense sensors).
                lot = lots[2] if c_index % 3 else lots[3]
            else:
                lot = lots[(c_index - 1) % (4 if after_release else 2)]
            version = versions[1] if after_release else versions[0]
            complaint = Complaint(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                complaint_identifier=f"{identifier}-CMP-{c_index:03d}",
                product_id=product.id,
                product_version_id=version.id,
                lot_batch_id=lot.id,
                event_timestamp=now - timedelta(days=days_ago + 2),
                complaint_timestamp=now - timedelta(days=days_ago),
                description=(
                    f"Customer reported {symptom} on {version.version_identifier}, lot {lot.lot_identifier}. "
                    "Device returned for evaluation; no patient injury reported."
                ),
                status="open" if days_ago < 60 else "closed",
                source_identifier=f"{identifier}-CMP-{c_index:03d}",
                **_stamp(now, days_ago),
            )
            db.add(complaint)
            complaints.append(complaint)
        db.flush()
        counts["complaints"] += len(complaints)

        if index != 1:
            continue
        investigation = Investigation(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            product_id=product.id,
            investigation_identifier="SAMPLE-INV-001",
            investigation_question="Why did pressure-alarm complaints rise after OrbitCare 300 Rev B?",
            status="open",
            opened_at=now - timedelta(days=21),
            owner_ref="quality.lead@sample.invalid",
            source_identifier="SAMPLE-INV-001",
            **_stamp(now, 21),
        )
        db.add(investigation)
        db.flush()
        counts["investigations"] += 1
        for complaint in complaints:
            if complaint.complaint_timestamp >= now - timedelta(days=75):
                db.add(
                    InvestigationComplaint(
                        id=uuid.uuid4(),
                        tenant_id=tenant_id,
                        investigation_id=investigation.id,
                        complaint_id=complaint.id,
                        created_at=now,
                    )
                )
        for e_index, (title, content, relevance) in enumerate(
            (
                (
                    "Supplier change record SAMPLE-CHG-014",
                    "The pressure sensor supplier changed to NovaSense Components for Rev B. Incoming inspection "
                    "sampling was reduced from 32 to 13 units per lot.",
                    "Establishes what changed before the complaint rise.",
                ),
                (
                    "Incoming inspection results, lots 003-004",
                    "Two of 13 sampled sensors in lot 003 read 4-6% high at the upper pressure range; lot 004 "
                    "shows one similar reading. Lots 001-002 (Precision Sensors) show none.",
                    "Links the complaint lots to the new sensor supplier.",
                ),
                (
                    "Complaint trend summary",
                    "Pressure-alarm complaints averaged 0.8 per month on Rev A and 5.6 per month after Rev B, with "
                    "most from lots 003 and 004.",
                    "Quantifies the signal. It does not by itself establish the cause.",
                ),
            ),
            1,
        ):
            evidence = Evidence(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                evidence_identifier=f"SAMPLE-EV-{e_index:03d}",
                investigation_id=investigation.id,
                evidence_type="sample_record",
                title=f"{title} (Sample)",
                source_reference="MDARIX sample dataset",
                document_ref="sample://orbitcare-300",
                reliability_status="validated",
                fact_type="source_fact",
                content=content,
                source_identifier=f"SAMPLE-EV-{e_index:03d}",
                **_stamp(now, 15 - e_index),
            )
            db.add(evidence)
            db.flush()
            db.add(
                InvestigationEvidence(
                    id=uuid.uuid4(),
                    tenant_id=tenant_id,
                    investigation_id=investigation.id,
                    evidence_id=evidence.id,
                    relevance=relevance,
                    created_at=now,
                )
            )
            counts["evidence"] += 1
    db.flush()
    return {"created": True, **counts}
