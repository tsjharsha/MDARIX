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

from backend.app.db.models.evidence_intelligence import EvidenceEntityLink
from evidence.extractors.chunker import EvidenceChunker

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
    RealityRelationship,
    Supplier,
)

SAMPLE_SOURCE = "MDARIX_SAMPLE"

# (identifier, name, family, symptom, complaint pattern, problem code). The pattern lists days-ago for each complaint:
# OrbitCare complaints cluster after the day-75 Rev B release; the others stay flat. With the story complaints
# (_STORY_COMPLAINTS), PulseWatch and VentraLink Rev B each have at most 2 complaints in the trend check's last 30 days,
# so neither is flagged as a rise (VentraLink's last one was at day 14, which made 3 there: a "significant rise").
# OrbitCare's complaints carry the problem code PRESSURE_ALARM, so its signal reads "5 complaints: pressure alarm on
# OrbitCare 300 ..." rather than "unspecified problem"; the others keep none.
_PRODUCTS = [
    (
        "SAMPLE-ORBIT-300",
        "OrbitCare 300 Infusion Pump (Sample)",
        "Infusion therapy",
        "pressure alarm during infusion",
        [170, 150, 128, 96, 70, 64, 58, 51, 47, 41, 36, 33, 29, 24, 20, 16, 11, 6],
        "PRESSURE_ALARM",
    ),
    (
        "SAMPLE-PULSE-410",
        "PulseWatch 410 Patient Monitor (Sample)",
        "Patient monitoring",
        "SpO2 signal dropout",
        [160, 131, 102, 77, 45, 19],
        None,
    ),
    (
        "SAMPLE-VENTRA-250",
        "VentraLink 250 Respiratory Controller (Sample)",
        "Respiratory support",
        "flow reading variance",
        [140, 99, 52, 33],
        None,
    ),
]


# The rest of the story (Complaints, Records and Readiness show findings from the first minute; MDARIX Final
# Lightweight MVP Plan, pains P1-P5). Records the quality system cancelled or logged as an inquiry although they carry
# signs of a complaint, a No Fault Found code that recurs, harm and malfunction complaints whose reporting clocks run,
# one closed without an investigation. Each has a problem code of its own, so none raises a signal, and none is in the
# guided investigation. Fields: identifier, product, version, lot number, days since awareness, description, fields.
STORY_MARKER = "SAMPLE-RV-01"
_STORY_COMPLAINTS = [
    (
        "SAMPLE-RV-01",
        "SAMPLE-PULSE-410",
        "Rev B",
        5,
        9,
        "Monitor's SpO2 reading dropped out overnight; the patient desaturated and was moved to intensive care. "
        "Record cancelled as a suspected duplicate.",
        {
            "status": "Cancelled",
            "problem_code": "SPO2_DROPOUT_HARM",
            "country": "US",
            "patient_involved": True,
            "serious_injury": True,
            "malfunction": True,
        },
    ),
    (
        "SAMPLE-RV-02",
        "SAMPLE-VENTRA-250",
        "Rev B",
        5,
        6,
        "Respiratory therapist asked how to clear alarm A-17; the flow reading had spiked while the patient was "
        "choking.",
        {"complaint_type": "Inquiry", "country": "Germany", "patient_involved": True},
    ),
    (
        "SAMPLE-RV-03",
        "SAMPLE-ORBIT-300",
        "Rev B",
        5,
        20,
        "Returned pump tested: no fault found. Ward reported intermittent pressure alarms during infusion.",
        {"status": "Closed", "problem_code": "NFF", "country": "US"},
    ),
    (
        "SAMPLE-RV-04",
        "SAMPLE-ORBIT-300",
        "Rev A",
        2,
        88,
        "Returned pump tested: no fault found. Nurse reported the pump stopped once.",
        {"status": "Closed", "problem_code": "NFF", "country": "US"},
    ),
    (
        "SAMPLE-RV-05",
        "SAMPLE-ORBIT-300",
        "Rev A",
        1,
        130,
        "Returned pump tested: no fault found. Alarm history showed one unexplained restart.",
        {"status": "Closed", "problem_code": "NFF", "country": "US"},
    ),
    (
        "SAMPLE-RV-06",
        "SAMPLE-ORBIT-300",
        "Rev B",
        4,
        24,
        "The pressure alarm did not sound during an occlusion; heparin was under-infused and the patient was moved "
        "to intensive care.",
        {
            "problem_code": "UNDER_INFUSION_NO_ALARM",
            "country": "US",
            "patient_involved": True,
            "serious_injury": True,
            "death": False,
            "malfunction": True,
            "severity": "Critical",
        },
    ),
    (
        "SAMPLE-RV-07",
        "SAMPLE-VENTRA-250",
        "Rev B",
        4,
        12,
        "Flow sensor showed zero flow for 40 seconds; staff switched to manual ventilation. No harm.",
        {
            "problem_code": "FLOW_ZERO_READING",
            "country": "France",
            "patient_involved": True,
            "serious_injury": False,
            "death": False,
            "malfunction": True,
        },
    ),
    (
        "SAMPLE-RV-08",
        "SAMPLE-ORBIT-300",
        "Rev B",
        5,
        3,
        "Nurse reports the pump free-flowed briefly after the door was opened; a patient was connected, outcome not "
        "yet known.",
        {"problem_code": "FREE_FLOW_DOOR", "country": "US", "patient_involved": True, "malfunction": True},
    ),
    (
        "SAMPLE-RV-09",
        "SAMPLE-PULSE-410",
        "Rev B",
        3,
        40,
        "Alarm volume too low to hear on a busy ward; the patient's desaturation was found late and needed oxygen "
        "therapy. Closed after a training call.",
        {
            "status": "Closed",
            "problem_code": "ALARM_VOLUME_LOW",
            "country": "US",
            "patient_involved": True,
            "serious_injury": True,
            "malfunction": True,
        },
    ),
]
# CAPAs from the quality system (Records › Effectiveness checks): one closed without an effectiveness check, and the
# OrbitCare action the sample brief recommends. That one follows the case: opened when the trial starts (after the
# sample brief was written and submitted, sample_decision.py), due after the trial's 30 days so it is never overdue in
# them, its effectiveness check planned 30 days after that. Fields: identifier, product, title, status, opened days
# ago, due days ago (negative: in the future), check in days.
_STORY_CAPAS = [
    (
        "SAMPLE-CAPA-01",
        "SAMPLE-PULSE-410",
        "Tighten incoming inspection of SpO2 sensor cables (Sample)",
        "Closed",
        200,
        140,
        None,
    ),
    (
        "SAMPLE-CAPA-02",
        "SAMPLE-ORBIT-300",
        "Restore incoming inspection to 32 units per lot for NovaSense pressure sensors (Sample)",
        "Open",
        0,
        -45,
        75,
    ),
]
# The risk register (Records › Risk file input): OrbitCare and VentraLink have risks no review has assessed since their
# harm and malfunction complaints; PulseWatch has none in MDARIX. Fields: identifier, product, description.
_STORY_RISKS = [
    ("SAMPLE-RSK-01", "SAMPLE-ORBIT-300", "False pressure alarm interrupts infusion and delays therapy."),
    ("SAMPLE-RSK-02", "SAMPLE-ORBIT-300", "Missed true occlusion leads to under-infusion."),
    ("SAMPLE-RSK-03", "SAMPLE-VENTRA-250", "Wrong flow reading delays detection of hypoventilation."),
]
# The FDA and EU reporting-window templates (reportability/rules.py), as a sample procedure would state them; a trial
# organization that set its own windows keeps them.
_STORY_WINDOW_TEMPLATES = (0, 1, 2)
STORY_WINDOWS_BY = "system:trial-sample"


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
    change = Change(
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
    db.add(change)
    db.flush()

    for index, (identifier, name, family, symptom, complaint_days, problem_code) in enumerate(_PRODUCTS, 1):
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
            # The OrbitCare pressure sensor is the component whose supplier changed; the change record names it as the
            # component it affects, as an imported change links its affected_ids (business_imports.py).
            changed = index == 1 and c_index == 1
            supplier = supplier_b if changed else supplier_a
            if changed:
                db.add(
                    RealityRelationship(
                        id=uuid.uuid4(),
                        tenant_id=tenant_id,
                        source_entity_type="Change",
                        source_entity_id=change.id,
                        target_entity_type="Component",
                        target_entity_id=component.id,
                        relationship_type="AFFECTS",
                        assertion_status="supported",
                        effective_timestamp=now - timedelta(days=80),
                        recorded_timestamp=now - timedelta(days=80),
                        provenance={"origin": "sample", "source_system": SAMPLE_SOURCE},
                        created_at=now,
                    )
                )
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
        # Days ago each lot was made: every complaint is on a lot of its own version, made before the event it reports.
        made = ((200, versions[0]), (160, versions[0]), (75, versions[1]), (68, versions[1]), (30, versions[1]))
        for lot_index, (built, version) in enumerate(made, 1):
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
            version = versions[1] if after_release else versions[0]
            if index == 1 and after_release:
                # Most post-release OrbitCare complaints come from lots 3 and 4 (first NovaSense sensors).
                lot = lots[2] if c_index % 3 else lots[3]
            else:
                # Its version's lots made before the event (two days before the complaint), in turn.
                usable = [item for item, (built, of) in zip(lots, made) if of is version and built >= days_ago + 2]
                lot = usable[(c_index - 1) % len(usable)]
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
                problem_code=problem_code,
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
                    "Pressure-alarm complaints averaged 0.8 per month in the 150 days before Rev B and 5.6 per month after Rev B, with "
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
            # Searchable from the first minute (Ask MDARIX, the investigator), like evidence a person adds, and linked
            # to the product and Rev B, so a search narrowed to OrbitCare 300 Rev B finds it.
            EvidenceChunker().create_chunks_for_evidence(
                db, tenant_id, evidence.id, content, {"record": evidence.evidence_identifier}
            )
            for entity_type, entity_id, reference in (
                ("Product", product.id, identifier),
                ("ProductVersion", versions[1].id, f"{identifier} Rev B"),
            ):
                db.add(
                    EvidenceEntityLink(
                        id=uuid.uuid4(),
                        tenant_id=tenant_id,
                        evidence_id=evidence.id,
                        entity_type=entity_type,
                        entity_id=entity_id,
                        raw_reference=reference,
                        resolution_status="RESOLVED",
                    )
                )
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


# Devices each sample lot released (md43): the mature Rev A lots ship more than the Rev B lots ramping up, so the trend
# check counts per unit in the field and the OrbitCare rise is a rise per device, not a growing installed base.
_SAMPLE_LOT_QUANTITY = {1: 400, 2: 400, 3: 150, 4: 150, 5: 150}


def seed_lot_quantities(db: Session, tenant_id) -> int:
    """Give the sample lots their quantities where none is set (trials approved before md43 included). Idempotent;
    never touches a lot the organization imported. Flushes but never commits. Returns the lots updated."""
    updated = 0
    for lot in db.query(LotBatch).filter(
        LotBatch.tenant_id == tenant_id, LotBatch.source_system == SAMPLE_SOURCE, LotBatch.quantity.is_(None)
    ):
        number = lot.lot_identifier.rsplit("-", 1)[-1]
        quantity = _SAMPLE_LOT_QUANTITY.get(int(number)) if number.isdigit() else None
        if quantity is not None:
            lot.quantity = quantity
            updated += 1
    db.flush()
    return updated


def has_story_examples(db: Session, tenant_id) -> bool:
    return (
        db.query(Complaint.id)
        .filter(Complaint.tenant_id == tenant_id, Complaint.complaint_identifier == STORY_MARKER)
        .first()
        is not None
    )


def seed_story_examples(db: Session, tenant_id, now: datetime | None = None) -> dict:
    """Add the rest of the story (hidden complaints, reporting clocks, CAPAs, the risk register and the sample
    reporting windows) to a workspace that holds the sample dataset. Idempotent: a workspace without the sample
    products, or with the examples already, is left as it is. Flushes but never commits."""
    from backend.app.db.models.foundation import Capa, Risk
    from backend.app.db.models.reportability import ReportabilitySettings
    from backend.app.reportability.rules import TEMPLATES, clean_window

    if not has_sample_data(db, tenant_id) or has_story_examples(db, tenant_id):
        return {"created": False}
    now = now or datetime.now(timezone.utc)
    products = {
        row.product_identifier: row
        for row in db.query(Product).filter(Product.tenant_id == tenant_id, Product.source_system == SAMPLE_SOURCE)
    }
    if {code for code, *_ in _PRODUCTS} - set(products):
        return {"created": False}
    versions = {
        (product.product_identifier, version.version_identifier): version
        for product in products.values()
        for version in db.query(ProductVersion).filter(
            ProductVersion.tenant_id == tenant_id, ProductVersion.product_id == product.id
        )
    }
    lots = {
        row.lot_identifier: row
        for row in db.query(LotBatch).filter(LotBatch.tenant_id == tenant_id, LotBatch.source_system == SAMPLE_SOURCE)
    }
    counts = {"complaints": 0, "capas": 0, "risks": 0, "reporting_windows": 0}
    for identifier, product_code, revision, lot_number, days, description, fields in _STORY_COMPLAINTS:
        aware = now - timedelta(days=days)
        version = versions.get((product_code, revision))
        lot = lots.get(f"{product_code}-LOT-{lot_number:03d}")
        db.add(
            Complaint(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                complaint_identifier=identifier,
                product_id=products[product_code].id,
                product_version_id=version.id if version else None,
                lot_batch_id=lot.id if lot else None,
                event_timestamp=aware - timedelta(days=1),
                complaint_timestamp=aware,
                awareness_timestamp=aware,
                description=description,
                source_identifier=identifier,
                **{"status": "open", **fields},
                **_stamp(now, days),
            )
        )
        counts["complaints"] += 1
    for identifier, product_code, title, status, opened, due, check_in in _STORY_CAPAS:
        db.add(
            Capa(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                capa_identifier=identifier,
                title=title,
                action_type="CORRECTIVE",
                source_type="QUALITY_SYSTEM",
                product_id=products[product_code].id,
                investigation_id=None,
                status=status,
                opened_at=now - timedelta(days=opened),
                due_at=now - timedelta(days=due),
                effectiveness_check_at=(now + timedelta(days=check_in)) if check_in is not None else None,
                source_identifier=identifier,
                **_stamp(now, opened),
            )
        )
        counts["capas"] += 1
    for identifier, product_code, description in _STORY_RISKS:
        db.add(
            Risk(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                risk_identifier=identifier,
                product_id=products[product_code].id,
                description=f"{description} (Sample)",
                source_identifier=identifier,
                **_stamp(now, 360),
            )
        )
        counts["risks"] += 1
    has_windows = (
        db.query(ReportabilitySettings.id).filter(ReportabilitySettings.tenant_id == tenant_id).first() is not None
    )
    if not has_windows:
        db.add(
            ReportabilitySettings(
                tenant_id=tenant_id,
                windows=[clean_window(TEMPLATES[index]) for index in _STORY_WINDOW_TEMPLATES],
                lookback_days=365,
                version=1,
                updated_by=STORY_WINDOWS_BY,
                updated_at=now,
            )
        )
        counts["reporting_windows"] = len(_STORY_WINDOW_TEMPLATES)
    db.flush()
    return {"created": True, **counts}
