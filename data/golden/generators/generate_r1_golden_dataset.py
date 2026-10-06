import csv
import hashlib
import json
import random
import shutil
from datetime import date, timedelta
from pathlib import Path

DATASET_VERSION = "r1-ai-golden-v2"
SEED = 31003
NOTICE = "MDARIX R1 GOLDEN DATASET - SYNTHETIC TEST DATA ONLY. NOT FOR CLINICAL OR REGULATORY USE."
ROOT = Path(__file__).resolve().parents[3]
BASE = ROOT / "data" / "golden"
SOURCE = BASE / "source"
CANONICAL = BASE / "canonical"
EVIDENCE_DIR = SOURCE / "evidence"
EVAL = ROOT / "evaluation"
GROUND = EVAL / "ground_truth"
SCENARIOS = EVAL / "scenarios"


def iso(day: date) -> str:
    return day.isoformat()


def write_json(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8", newline="\n")


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        # LF on every platform so regenerated files are byte-identical to the
        # committed copies (see .gitattributes) and ingestion checksums stay stable.
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()), lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)


def stable_id(prefix: str, value: str) -> str:
    digest = hashlib.sha1(f"{prefix}:{value}".encode("utf-8")).hexdigest()[:10]
    return f"{prefix}-{digest}"


def reset_outputs() -> None:
    for path in [SOURCE, CANONICAL, GROUND, SCENARIOS]:
        if path.exists():
            shutil.rmtree(path)
    for path in [SOURCE, CANONICAL, GROUND, SCENARIOS, EVIDENCE_DIR]:
        path.mkdir(parents=True, exist_ok=True)


def build_dataset() -> dict:
    random.seed(SEED)
    reset_outputs()

    tenant = {
        "tenant_id": "ten-acme-care-fictive",
        "tenant_key": "ACME_CARE_SYNTHETIC",
        "name": "AcmeCare Instruments",
        "fictional": True,
        "notice": NOTICE,
    }

    product_families = [
        {"family_id": "FAM-INFUSION", "name": "AsterFlow Infusion Platform"},
        {"family_id": "FAM-MONITOR", "name": "NimbusView Monitoring Platform"},
    ]
    products = [
        {
            "product_id": "PRD-ASTER-100",
            "family_id": "FAM-INFUSION",
            "product_identifier": "AF-100",
            "name": "AsterFlow 100 Controller",
        },
        {
            "product_id": "PRD-NIMBUS-200",
            "family_id": "FAM-MONITOR",
            "product_identifier": "NV-200",
            "name": "NimbusView 200 Monitor",
        },
    ]
    version_specs = [
        ("PV-ASTER-A", "PRD-ASTER-100", "Rev A", date(2025, 7, 1), "PRD-100-A"),
        ("PV-ASTER-B", "PRD-ASTER-100", "Rev B", date(2025, 10, 1), "PRD100 Rev B"),
        ("PV-ASTER-C", "PRD-ASTER-100", "Rev C", date(2025, 12, 10), "Product-100 / Revision C"),
        ("PV-ASTER-D", "PRD-ASTER-100", "Rev D", date(2026, 1, 25), "PRD100 Rev D"),
        ("PV-NIMBUS-A", "PRD-NIMBUS-200", "Rev A", date(2025, 8, 15), "NV200-A"),
        ("PV-NIMBUS-B", "PRD-NIMBUS-200", "Rev B", date(2026, 2, 1), "Nimbus 200 Revision B"),
    ]
    versions = [
        {
            "product_version_id": vid,
            "product_id": product_id,
            "version_identifier": rev,
            "effective_timestamp": iso(eff),
            "source_alias": alias,
        }
        for vid, product_id, rev, eff, alias in version_specs
    ]

    suppliers = [
        {
            "supplier_id": "SUP-NOVACAP",
            "supplier_identifier": "SUP-001",
            "name": "NovaCap Components",
            "aliases": ["Nova Cap", "NVC Components"],
        },
        {
            "supplier_id": "SUP-ORBIT",
            "supplier_identifier": "SUP-002",
            "name": "OrbitFlex Electronics",
            "aliases": ["Orbit Flex", "OFX"],
        },
        {
            "supplier_id": "SUP-LUMEN",
            "supplier_identifier": "SUP-003",
            "name": "LumenTrace Plastics",
            "aliases": ["Lumen Trace"],
        },
        {
            "supplier_id": "SUP-QUANTA",
            "supplier_identifier": "SUP-004",
            "name": "QuantaSeal Packaging",
            "aliases": ["QS Packaging"],
        },
        {
            "supplier_id": "SUP-HELIOS",
            "supplier_identifier": "SUP-005",
            "name": "Helios Boardworks",
            "aliases": ["Helios BW"],
        },
    ]
    sites = [
        {"site_id": "SITE-RIVER", "site_identifier": "MFG-01", "name": "Riverbend Assembly"},
        {"site_id": "SITE-SUMMIT", "site_identifier": "MFG-02", "name": "Summit Final Test"},
    ]

    component_names = [
        ("COMP-PWR", "Power Regulation Module", "SUP-NOVACAP"),
        ("COMP-CAP", "Reservoir Capacitor", "SUP-NOVACAP"),
        ("COMP-FW", "Firmware Control Package", "SUP-ORBIT"),
        ("COMP-SENSOR", "Flow Sensor Board", "SUP-HELIOS"),
        ("COMP-BATT", "Backup Cell", "SUP-ORBIT"),
        ("COMP-CASE", "Outer Housing", "SUP-LUMEN"),
        ("COMP-LABEL", "Package Label", "SUP-QUANTA"),
        ("COMP-DISPLAY", "Status Display", "SUP-HELIOS"),
        ("COMP-CONN", "Harness Connector", "SUP-ORBIT"),
        ("COMP-PUMP", "Pump Drive", "SUP-NOVACAP"),
        ("COMP-VALVE", "Valve Assembly", "SUP-LUMEN"),
        ("COMP-SEAL", "Fluid Seal", "SUP-LUMEN"),
        ("COMP-LOGIC", "Logic Board", "SUP-HELIOS"),
        ("COMP-CHARGE", "Charge Controller", "SUP-NOVACAP"),
        ("COMP-SPEAKER", "Alert Speaker", "SUP-ORBIT"),
        ("COMP-CLIP", "Mounting Clip", "SUP-QUANTA"),
    ]
    components = []
    for idx, (cid, name, supplier_id) in enumerate(component_names, 1):
        rev = "Rev B" if cid in {"COMP-PWR", "COMP-CAP"} else ("Rev A" if idx % 3 else "Rev C")
        components.append(
            {
                "component_id": cid,
                "component_identifier": f"C-{idx:03d}",
                "name": name,
                "revision": rev,
                "supplier_id": supplier_id,
                "description": f"Synthetic {name.lower()} used for R1 evaluation.",
            }
        )

    lots = []
    for idx in range(1, 19):
        product_version_id = "PV-ASTER-D" if idx in range(8, 15) else ("PV-ASTER-C" if idx < 8 else "PV-NIMBUS-B")
        lots.append(
            {
                "lot_id": f"LOT-{idx:03d}",
                "lot_identifier": f"AFD-26-{idx:03d}" if product_version_id == "PV-ASTER-D" else f"GEN-26-{idx:03d}",
                "product_version_id": product_version_id,
                "manufacturing_site_id": "SITE-RIVER" if idx % 2 else "SITE-SUMMIT",
                "manufactured_timestamp": iso(date(2026, 1, 20) + timedelta(days=idx)),
                "traceability_status": "incomplete" if idx in {10, 13, 17} else "complete",
            }
        )

    requirements = [
        {
            "requirement_id": f"REQ-{idx:03d}",
            "product_id": "PRD-ASTER-100" if idx <= 18 else "PRD-NIMBUS-200",
            "requirement_identifier": f"REQ-{idx:03d}",
            "requirement_type": "safety" if idx % 4 == 0 else "performance",
            "text": f"Synthetic lifecycle requirement {idx}.",
        }
        for idx in range(1, 25)
    ]

    change_specs = [
        (
            "CHG-SUP-PROC-001",
            "supplier_process",
            "NovaCap dielectric curing profile adjusted",
            date(2026, 1, 10),
            date(2026, 1, 15),
            "SUP-NOVACAP",
        ),
        (
            "CHG-COMP-PWR-B",
            "component_revision",
            "Power Regulation Module Rev B introduced",
            date(2026, 1, 18),
            date(2026, 1, 18),
            "COMP-PWR",
        ),
        (
            "CHG-PROD-D",
            "product_revision",
            "AsterFlow Rev D configuration released",
            date(2026, 1, 25),
            date(2026, 1, 25),
            "PV-ASTER-D",
        ),
        (
            "CHG-LABEL-042",
            "packaging_label",
            "Outer carton label layout changed",
            date(2026, 1, 27),
            date(2026, 1, 28),
            "COMP-LABEL",
        ),
        (
            "CHG-FW-113",
            "firmware",
            "Firmware logging level adjusted",
            date(2025, 12, 15),
            date(2025, 12, 20),
            "COMP-FW",
        ),
    ]
    while len(change_specs) < 16:
        n = len(change_specs) + 1
        change_specs.append(
            (
                f"CHG-GEN-{n:03d}",
                "process" if n % 2 else "component_revision",
                f"Synthetic controlled change {n}",
                date(2025, 9, 1) + timedelta(days=n * 13),
                date(2025, 9, 3) + timedelta(days=n * 13),
                "PRD-ASTER-100",
            )
        )
    changes = [
        {
            "change_id": cid,
            "change_identifier": cid,
            "change_type": ctype,
            "description": desc,
            "event_timestamp": iso(evt),
            "effective_timestamp": iso(eff),
            "related_object_id": related,
        }
        for cid, ctype, desc, evt, eff, related in change_specs
    ]

    risks = [
        {
            "risk_id": f"RISK-{idx:03d}",
            "risk_identifier": f"RISK-{idx:03d}",
            "product_id": "PRD-ASTER-100" if idx <= 10 else "PRD-NIMBUS-200",
            "description": f"Synthetic risk {idx}",
        }
        for idx in range(1, 16)
    ]
    failure_modes = [
        {"failure_mode_id": f"FM-{idx:03d}", "failure_mode_identifier": f"FM-{idx:03d}", "name": name}
        for idx, name in enumerate(
            [
                "Intermittent shutdown",
                "Delayed restart",
                "False alarm",
                "Display freeze",
                "Battery warning",
                "Flow interruption",
                "Connector intermittency",
                "Sensor drift",
                "Seal leak",
                "Label mismatch",
                "Charging interruption",
                "Housing crack",
                "Speaker low volume",
                "Firmware log overflow",
                "No fault found",
            ],
            1,
        )
    ]
    controls = [
        {
            "control_id": f"CTRL-{idx:03d}",
            "control_identifier": f"CTRL-{idx:03d}",
            "control_type": "validation" if idx % 2 else "process",
            "description": f"Synthetic control {idx}",
        }
        for idx in range(1, 13)
    ]

    complaints = []
    complaint_id = 1
    pre_rev_b_days = [date(2025, 11, 18), date(2025, 12, 4), date(2026, 1, 8)]
    for day in pre_rev_b_days:
        complaints.append(
            make_complaint(
                complaint_id, "PV-ASTER-C", None, day, "Intermittent shutdown before Rev B", "shutdown", duplicate=False
            )
        )
        complaint_id += 1
    for i in range(117):
        if i < 48:
            version = "PV-ASTER-D"
            lot = random.choice(["LOT-008", "LOT-009", "LOT-010", "LOT-011", "LOT-012", "LOT-013", "LOT-014", None])
            failure = "shutdown" if i < 36 else random.choice(["delayed_restart", "no_fault_found", "false_alarm"])
            event_day = date(2026, 2, 5) + timedelta(days=i % 55)
            narrative = (
                "Intermittent shutdown during field use" if failure == "shutdown" else f"Synthetic {failure} complaint"
            )
        elif i < 75:
            version = "PV-ASTER-C"
            lot = random.choice(["LOT-001", "LOT-002", "LOT-003", None])
            failure = random.choice(["shutdown", "battery_warning", "connector_intermittency"])
            event_day = date(2025, 12, 1) + timedelta(days=i)
            narrative = f"Pre-Rev D {failure} complaint"
        elif i < 96:
            version = "PV-NIMBUS-B"
            lot = random.choice(["LOT-015", "LOT-016", "LOT-017", "LOT-018", None])
            failure = random.choice(["display_freeze", "false_alarm", "shutdown"])
            event_day = date(2026, 2, 2) + timedelta(days=i % 40)
            narrative = f"Nimbus {failure} complaint"
        else:
            version = random.choice(["PV-ASTER-A", "PV-ASTER-B", "PV-NIMBUS-A"])
            lot = None
            failure = random.choice(["no_fault_found", "speaker_low_volume", "label_mismatch"])
            event_day = date(2025, 8, 20) + timedelta(days=i)
            narrative = f"Background {failure} complaint"
        complaints.append(
            make_complaint(
                complaint_id, version, lot, event_day, narrative, failure, duplicate=(complaint_id in {44, 45})
            )
        )
        complaint_id += 1

    investigations = [
        {
            "investigation_id": f"INV-{idx:03d}",
            "investigation_identifier": f"INV-{idx:03d}",
            "product_id": "PRD-ASTER-100" if idx <= 7 else "PRD-NIMBUS-200",
            "question": question,
            "opened_at": iso(date(2026, 2, 20) + timedelta(days=idx * 3)),
            "status": "open" if idx in {1, 3, 10} else "closed",
        }
        for idx, question in enumerate(
            [
                "Why did intermittent device shutdown complaints increase after Product Rev D was introduced?",
                "Did the package label revision influence shutdown complaints?",
                "Which records are missing for affected lots?",
                "Why do source timelines conflict for Component Rev B?",
                "Which lots share the Power Regulation Module?",
                "Was investigation INV-006 closed prematurely?",
                "Did process control drift contribute to the complaint cluster?",
                "What constrained counterfactual can be evaluated for Rev B?",
                "How should AI model-change outputs be compared?",
                "When should MDARIX abstain due to insufficient evidence?",
            ],
            1,
        )
    ]

    evidence = make_evidence()
    hypotheses = [
        {
            "hypothesis_id": "HYP-VS001-LEAD",
            "investigation_id": "INV-001",
            "statement": "Component Rev B may have contributed to the shutdown complaint increase.",
            "origin": "human",
        },
        {
            "hypothesis_id": "HYP-VS001-FALSE",
            "investigation_id": "INV-001",
            "statement": "Packaging label revision may explain the shutdown complaint increase.",
            "origin": "human",
        },
        {
            "hypothesis_id": "HYP-VS011-MULTI",
            "investigation_id": "INV-001",
            "statement": "Multiple mechanisms may explain different shutdown subsets.",
            "origin": "human",
        },
    ]
    unknowns = [
        {
            "unknown_id": "UNK-VS001-COMPARE",
            "investigation_id": "INV-001",
            "description": "Comparative Rev A versus Rev B testing unavailable",
            "why_it_matters": "Limits causality assessment",
            "evidence_needed": "Controlled comparative test report",
        },
        {
            "unknown_id": "UNK-VS001-TRACE",
            "investigation_id": "INV-001",
            "description": "Lot/component traceability incomplete for LOT-010 and LOT-013",
            "why_it_matters": "Limits exposure certainty",
            "evidence_needed": "MES component genealogy export",
        },
        {
            "unknown_id": "UNK-VS012-FIELD",
            "investigation_id": "INV-010",
            "description": "Field operating condition not recorded",
            "why_it_matters": "Correct behavior is abstention",
            "evidence_needed": "Field use logs",
        },
    ]
    failure_chains = [
        {
            "failure_chain_id": "FC-VS001",
            "investigation_id": "INV-001",
            "nodes": [
                "Supplier Process Change",
                "Component Rev B",
                "Product Rev D",
                "Affected lots",
                "Shutdown complaints",
            ],
            "edges": [
                {"from": "Supplier Process Change", "to": "Component Rev B", "status": "SUPPORTED"},
                {"from": "Component Rev B", "to": "Product Rev D", "status": "ESTABLISHED"},
                {"from": "Product Rev D", "to": "Affected lots", "status": "SUPPORTED"},
                {"from": "Affected lots", "to": "Shutdown complaints", "status": "HYPOTHESIZED"},
            ],
        }
    ]

    scenarios = make_scenarios()
    anomalies = make_anomalies()
    aliases = make_aliases()

    canonical = {
        "notice": NOTICE,
        "dataset_version": DATASET_VERSION,
        "tenant": tenant,
        "product_families": product_families,
        "products": products,
        "product_versions": versions,
        "components": components,
        "suppliers": suppliers,
        "manufacturing_sites": sites,
        "lots": lots,
        "requirements": requirements,
        "changes": changes,
        "complaints": complaints,
        "investigations": investigations,
        "risks": risks,
        "failure_modes": failure_modes,
        "controls": controls,
        "evidence": evidence,
        "hypotheses": hypotheses,
        "unknowns": unknowns,
        "failure_chains": failure_chains,
        "aliases": aliases,
        "intentional_anomalies": anomalies,
        "scenarios": [
            {"scenario_id": s["scenario_id"], "title": s["title"], "investigation_id": s["investigation_id"]}
            for s in scenarios
        ],
    }
    write_json(CANONICAL / "r1_canonical_golden_dataset.json", canonical)

    write_source_files(
        products,
        versions,
        components,
        suppliers,
        sites,
        lots,
        requirements,
        changes,
        complaints,
        investigations,
        risks,
        failure_modes,
        controls,
        evidence,
    )
    write_ground_truth(scenarios, anomalies, aliases)
    write_manifest(canonical, scenarios, anomalies)
    return canonical


def make_complaint(
    num: int, version: str, lot: str | None, event_day: date, narrative: str, failure: str, duplicate: bool
) -> dict:
    recorded = event_day + timedelta(days=4 + (num % 5))
    ingestion = recorded + timedelta(days=3 + (num % 4))
    alias = {"PV-ASTER-D": "PRD100 Rev D", "PV-ASTER-C": "Product-100 / Revision C"}.get(version, version)
    return {
        "complaint_id": f"CMP-{num:04d}",
        "complaint_identifier": f"QMS-{num:05d}",
        "product_version_id": version,
        "source_product_version": alias,
        "lot_id": lot,
        "event_timestamp": iso(event_day),
        "recorded_timestamp": iso(recorded),
        "ingestion_timestamp": iso(ingestion),
        "failure_mode": failure,
        "narrative": narrative,
        "duplicate_candidate": duplicate,
        "data_quality_status": "missing_lot" if lot is None else ("duplicate_candidate" if duplicate else "reviewed"),
    }


def make_evidence() -> list[dict]:
    specs = [
        (
            "EV-VS001-001",
            "supplier_process_notification",
            "NovaCap process-change notification",
            "approved_supplier_record",
            "higher",
            "Supplier process change became effective before Component Rev B.",
        ),
        (
            "EV-VS001-002",
            "engineering_change_record",
            "Power module Rev B engineering change",
            "formal_change_record",
            "higher",
            "Component Rev B introduced after supplier process change.",
        ),
        (
            "EV-VS001-003",
            "manufacturing_record",
            "Rev D lots component genealogy",
            "controlled_manufacturing_record",
            "higher",
            "Several Rev D lots used Component Rev B; LOT-010 and LOT-013 have incomplete traceability.",
        ),
        (
            "EV-VS001-004",
            "complaint_summary",
            "Shutdown complaint frequency trend",
            "qms_summary",
            "higher",
            "Shutdown complaints increased after Rev D field deployment.",
        ),
        (
            "EV-VS001-005",
            "validation_report",
            "Rev B qualification passed",
            "approved_validation_report",
            "higher",
            "Relevant Rev B validation test passed acceptance criteria.",
        ),
        (
            "EV-VS001-006",
            "complaint_history",
            "Pre-Rev B shutdown complaints",
            "qms_records",
            "higher",
            "At least three shutdown complaints existed before Component Rev B.",
        ),
        (
            "EV-VS001-007",
            "investigation_note",
            "Comparative Rev A versus Rev B testing unavailable",
            "investigation_note",
            "uncertain",
            "No controlled comparative Rev A vs Rev B test was available.",
        ),
        (
            "EV-VS002-001",
            "engineering_change_record",
            "Packaging label revision",
            "formal_change_record",
            "higher",
            "Packaging label changed near complaint increase but has no electrical mechanism.",
        ),
        (
            "EV-VS003-001",
            "investigation_note",
            "Required comparative test unavailable",
            "investigation_note",
            "uncertain",
            "The controlled Rev A versus Rev B comparative test is unavailable.",
        ),
        (
            "EV-VS004-001",
            "complaint_history",
            "Historical shutdowns before Rev B",
            "qms_records",
            "higher",
            "Shutdown complaints were recorded before Component Rev B was introduced.",
        ),
        (
            "EV-VS004-002",
            "validation_report",
            "Rev B qualification acceptance",
            "approved_validation_report",
            "higher",
            "Rev B qualification met the documented acceptance criteria.",
        ),
        (
            "EV-VS005-001",
            "manufacturing_record",
            "Late lot genealogy",
            "controlled_manufacturing_record",
            "uncertain",
            "Lot genealogy was ingested after the initial closure decision.",
        ),
        (
            "EV-VS006-001",
            "bom_extract",
            "Shared power-module exposure",
            "controlled_plm_extract",
            "higher",
            "AsterFlow Rev C and Rev D share the Power Regulation Module.",
        ),
        (
            "EV-VS007-001",
            "investigation_note",
            "Closure rationale with unresolved contradiction",
            "investigation_note",
            "uncertain",
            "Historical closure did not address pre-Rev B complaints.",
        ),
        (
            "EV-VS008-001",
            "process_control_record",
            "Process control acceptance record",
            "approved_process_record",
            "higher",
            "The sampled process-control result remained within its acceptance limit.",
        ),
        (
            "EV-VS009-001",
            "counterfactual_note",
            "Counterfactual baseline limitation",
            "investigation_note",
            "uncertain",
            "The baseline lacks a controlled matched comparator.",
        ),
        (
            "EV-VS010-001",
            "ai_run_metadata",
            "AI model change comparison fixture",
            "evaluation_fixture",
            "higher",
            "Same evidence packet evaluated under two model metadata records.",
        ),
        (
            "EV-VS011-001",
            "service_observation",
            "Connector intermittency subset",
            "controlled_service_record",
            "higher",
            "A subset of shutdown complaints aligns with connector intermittency.",
        ),
        (
            "EV-VS012-001",
            "field_record",
            "Field operating condition missing",
            "field_note",
            "uncertain",
            "The operating condition required to assess the event was not recorded.",
        ),
    ]
    while len(specs) < 38:
        n = len(specs) + 1
        specs.append(
            (
                f"EV-GEN-{n:03d}",
                "risk_analysis_excerpt" if n % 3 == 0 else "service_observation",
                f"Synthetic evidence artifact {n}",
                "controlled_document" if n % 2 else "field_note",
                "higher" if n % 4 else "uncertain",
                f"Concise synthetic evidence content {n}.",
            )
        )
    evidence = []
    for idx, (eid, etype, title, source, quality, content) in enumerate(specs, 1):
        availability = date(2026, 2, 1) + timedelta(days=idx)
        if eid == "EV-VS001-003":
            availability = date(2026, 4, 8)  # late-arriving after one closure decision
        evidence.append(
            {
                "evidence_id": eid,
                "investigation_id": (
                    f"INV-{min(int(eid[5:8]), 10):03d}"
                    if eid.startswith("EV-VS")
                    else f"INV-{((idx - 1) % 10) + 1:03d}"
                ),
                "evidence_type": etype,
                "title": title,
                "source": source,
                "quality": quality,
                "content": content,
                "event_timestamp": iso(date(2026, 1, 10) + timedelta(days=idx)),
                "recorded_timestamp": iso(date(2026, 1, 15) + timedelta(days=idx)),
                "ingestion_timestamp": iso(availability),
                "document_path": f"source/evidence/{eid}.md",
            }
        )
    return evidence


def make_scenarios() -> list[dict]:
    titles = {
        "VS001": "Supplier Change Correlation",
        "VS002": "False Correlation",
        "VS003": "Missing Evidence",
        "VS004": "Conflicting Evidence",
        "VS005": "Incorrect Timeline",
        "VS006": "Shared Component Exposure",
        "VS007": "Premature Closure",
        "VS008": "Control Failure",
        "VS009": "Counterfactual",
        "VS010": "AI Model Change",
        "VS011": "Multiple Causes",
        "VS012": "Correct Abstention",
    }
    expectations = {
        "VS001": {
            "evidence": ["EV-VS001-001", "EV-VS001-002", "EV-VS001-003", "EV-VS001-004"],
            "contradictions": ["Pre-Rev B shutdown complaints", "Rev B validation passed"],
            "unknowns": ["Comparative Rev A vs Rev B testing unavailable"],
            "prohibited": ["Component Rev B definitively caused all shutdowns.", "All Rev D devices are affected."],
            "anomalies": ["ANOM-LOT-001", "ANOM-TIME-001"],
        },
        "VS002": {
            "evidence": ["EV-VS002-001"],
            "contradictions": ["Packaging label change has no electrical mechanism"],
            "unknowns": ["No causal mechanism links the label to shutdowns"],
            "prohibited": ["The packaging label change caused the shutdown increase."],
            "anomalies": ["ANOM-FALSE-001"],
        },
        "VS003": {
            "evidence": ["EV-VS003-001"],
            "contradictions": [],
            "unknowns": ["Comparative Rev A versus Rev B testing unavailable"],
            "prohibited": ["The available evidence is complete."],
            "anomalies": ["ANOM-LOT-001"],
        },
        "VS004": {
            "evidence": ["EV-VS004-001", "EV-VS004-002"],
            "contradictions": [
                "Shutdown complaints existed before Rev B",
                "Rev B qualification met acceptance criteria",
            ],
            "unknowns": ["The conflicting records do not establish a single cause"],
            "prohibited": ["Rev B qualification proves there is no product issue."],
            "anomalies": ["ANOM-FALSE-001"],
        },
        "VS005": {
            "evidence": ["EV-VS005-001"],
            "contradictions": ["Lot genealogy arrived after the initial closure"],
            "unknowns": ["The original decision did not include late evidence"],
            "prohibited": ["The original closure considered all available evidence."],
            "anomalies": ["ANOM-TIME-001", "ANOM-DATE-001"],
        },
        "VS006": {
            "evidence": ["EV-VS006-001"],
            "contradictions": [],
            "unknowns": ["Shared component exposure does not establish defect or causality"],
            "prohibited": ["Every product sharing the component is affected."],
            "anomalies": ["ANOM-LOT-001"],
        },
        "VS007": {
            "evidence": ["EV-VS007-001"],
            "contradictions": ["Closure rationale omitted pre-Rev B complaints"],
            "unknowns": ["Unresolved contradiction requires review before closure"],
            "prohibited": ["The investigation was ready for final closure."],
            "anomalies": ["ANOM-TIME-001"],
        },
        "VS008": {
            "evidence": ["EV-VS008-001"],
            "contradictions": ["Complaint trend persists despite an accepted process-control sample"],
            "unknowns": ["A passing sample does not establish continuous control"],
            "prohibited": ["The passing process-control record rules out process contribution."],
            "anomalies": ["ANOM-MULTI-001"],
        },
        "VS009": {
            "evidence": ["EV-VS009-001"],
            "contradictions": [],
            "unknowns": ["No controlled matched comparator is available"],
            "prohibited": ["The counterfactual proves the outcome would not have occurred."],
            "anomalies": ["ANOM-FALSE-001"],
        },
        "VS010": {
            "evidence": ["EV-VS010-001"],
            "contradictions": ["Model outputs must be compared against the same evidence packet"],
            "unknowns": ["A model change alone does not establish improved correctness"],
            "prohibited": ["The newer model is automatically more accurate."],
            "anomalies": ["ANOM-ID-001"],
        },
        "VS011": {
            "evidence": ["EV-VS011-001"],
            "contradictions": ["Connector intermittency explains only a subset"],
            "unknowns": ["Multiple mechanisms may explain different complaint subsets"],
            "prohibited": ["A single mechanism caused every shutdown complaint."],
            "anomalies": ["ANOM-MULTI-001"],
        },
        "VS012": {
            "evidence": ["EV-VS012-001"],
            "contradictions": [],
            "unknowns": ["Field operating condition not recorded"],
            "prohibited": ["A root cause can be concluded despite the missing field condition."],
            "anomalies": ["ANOM-LOT-001"],
        },
    }
    scenarios = []
    for idx, sid in enumerate(titles, 1):
        expected = expectations[sid]
        scenarios.append(
            {
                "scenario_id": sid,
                "title": titles[sid],
                "investigation_id": f"INV-{min(idx, 10):03d}",
                "purpose": f"Evaluate {titles[sid].lower()} behavior.",
                "expected_system_behavior": "Cite the required evidence, surface the defined contradictions and unknowns, avoid the prohibited conclusion, and require human review.",
                "expected_evidence": expected["evidence"],
                "prohibited_conclusions": expected["prohibited"],
                "expected_unknowns": expected["unknowns"],
                "expected_contradictions": expected["contradictions"],
                "intentional_anomalies": expected["anomalies"],
                "acceptance_criteria": [
                    "All expected evidence identifiers are cited and authorized for the investigation.",
                    "All defined contradictions and unknowns are explicitly surfaced.",
                    "No prohibited conclusion, causal certainty, or regulatory decision is asserted.",
                    "The output remains advisory and requires human review.",
                ],
            }
        )
    return scenarios


def make_anomalies() -> list[dict]:
    return [
        {
            "anomaly_id": "ANOM-ID-001",
            "type": "identity_variation",
            "description": "PRD-100-D, PRD100 Rev D, and Product-100 / Revision D refer to PV-ASTER-D",
        },
        {
            "anomaly_id": "ANOM-SUP-001",
            "type": "supplier_alias",
            "description": "Nova Cap and NVC Components refer to NovaCap Components",
        },
        {
            "anomaly_id": "ANOM-LOT-001",
            "type": "missing_traceability",
            "description": "LOT-010 and LOT-013 have incomplete Component Rev B genealogy",
        },
        {
            "anomaly_id": "ANOM-DATE-001",
            "type": "delayed_record_entry",
            "description": "Complaint events occur days before QMS entry and MDARIX ingestion",
        },
        {
            "anomaly_id": "ANOM-DUP-001",
            "type": "duplicate_candidate",
            "description": "QMS-00044 and QMS-00045 are controlled duplicate candidates",
        },
        {
            "anomaly_id": "ANOM-TIME-001",
            "type": "late_arriving_evidence",
            "description": "LOT genealogy evidence arrived after an initial closure decision",
        },
        {
            "anomaly_id": "ANOM-FALSE-001",
            "type": "false_correlation",
            "description": "Packaging label revision occurs near complaint increase but is non-causal",
        },
        {
            "anomaly_id": "ANOM-MULTI-001",
            "type": "multiple_causes",
            "description": "Some shutdown complaints align with a pre-existing connector intermittency condition",
        },
    ]


def make_aliases() -> list[dict]:
    return [
        {"source_value": "PRD-100-D", "canonical_id": "PV-ASTER-D", "entity_type": "product_version"},
        {"source_value": "PRD100 Rev D", "canonical_id": "PV-ASTER-D", "entity_type": "product_version"},
        {"source_value": "Product-100 / Revision D", "canonical_id": "PV-ASTER-D", "entity_type": "product_version"},
        {"source_value": "Nova Cap", "canonical_id": "SUP-NOVACAP", "entity_type": "supplier"},
        {"source_value": "NVC Components", "canonical_id": "SUP-NOVACAP", "entity_type": "supplier"},
    ]


# PLM configuration membership (which components each product version is built
# from). Source layer only: it is ingested from plm/product_components.csv and
# does not change the canonical dataset or its manifest hash.
PRODUCT_VERSION_COMPONENTS = [
    ("PV-ASTER-A", ["COMP-FW", "COMP-SENSOR"]),
    ("PV-ASTER-B", ["COMP-FW", "COMP-SENSOR"]),
    ("PV-ASTER-C", ["COMP-PWR", "COMP-FW", "COMP-SENSOR"]),
    ("PV-ASTER-D", ["COMP-PWR", "COMP-CAP", "COMP-FW", "COMP-CONN"]),
    ("PV-NIMBUS-A", ["COMP-PUMP", "COMP-VALVE"]),
    ("PV-NIMBUS-B", ["COMP-PUMP", "COMP-VALVE", "COMP-SEAL"]),
]


def product_component_rows(versions):
    effective = {row["product_version_id"]: row["effective_timestamp"] for row in versions}
    return [
        {
            "product_component_id": f"PC-{version_id}-{component_id}",
            "product_version_id": version_id,
            "component_id": component_id,
            "effective_timestamp": effective[version_id],
        }
        for version_id, component_ids in PRODUCT_VERSION_COMPONENTS
        for component_id in component_ids
    ]


def write_source_files(
    products,
    versions,
    components,
    suppliers,
    sites,
    lots,
    requirements,
    changes,
    complaints,
    investigations,
    risks,
    failure_modes,
    controls,
    evidence,
):
    write_csv(SOURCE / "plm" / "products.csv", products)
    write_csv(SOURCE / "plm" / "product_versions.csv", versions)
    write_csv(SOURCE / "plm" / "components.csv", components)
    write_csv(SOURCE / "plm" / "product_components.csv", product_component_rows(versions))
    write_csv(SOURCE / "plm" / "requirements.csv", requirements)
    write_csv(SOURCE / "plm" / "changes.csv", changes)
    write_csv(SOURCE / "qms" / "complaints.csv", complaints)
    write_csv(SOURCE / "qms" / "investigations.csv", investigations)
    write_csv(SOURCE / "qms" / "risks.csv", risks)
    write_csv(SOURCE / "qms" / "failure_modes.csv", failure_modes)
    write_csv(SOURCE / "qms" / "controls.csv", controls)
    write_csv(SOURCE / "erp_mes" / "suppliers.csv", suppliers)
    write_csv(SOURCE / "erp_mes" / "manufacturing_sites.csv", sites)
    write_csv(SOURCE / "erp_mes" / "lots.csv", lots)
    for item in evidence:
        (EVIDENCE_DIR / f"{item['evidence_id']}.md").write_text(
            f"# {item['title']}\n\n{NOTICE}\n\nType: {item['evidence_type']}\nQuality: {item['quality']}\n\n{item['content']}\n",
            encoding="utf-8",
            newline="\n",
        )
    write_json(SOURCE / "documents" / "evidence_metadata.json", evidence)


def write_ground_truth(scenarios, anomalies, aliases):
    for scenario in scenarios:
        write_json(
            GROUND / scenario["scenario_id"] / "ground_truth.json",
            {
                "notice": NOTICE,
                "evaluation_only": True,
                **scenario,
                "hidden_ground_truth": "Evaluation-only. Not application-facing.",
                "intentional_anomalies": scenario["intentional_anomalies"],
            },
        )
    write_json(GROUND / "identity_resolution_map.json", {"notice": NOTICE, "evaluation_only": True, "aliases": aliases})
    write_json(
        GROUND / "intentional_anomaly_registry.json",
        {"notice": NOTICE, "evaluation_only": True, "anomalies": anomalies},
    )
    (GROUND / "VS001" / "manual_verification.md").write_text(
        "# VS001 Manual Verification\n\n"
        f"{NOTICE}\n\n"
        "Supplier Process Change -> Component Rev B -> Product Rev D -> LOT-008/009/010/011/012/013/014 -> shutdown complaints.\n\n"
        "Supporting evidence: EV-VS001-001 through EV-VS001-004.\n\n"
        "Contradicting evidence: EV-VS001-005 and EV-VS001-006.\n\n"
        "Unknowns: comparative Rev A vs Rev B testing unavailable; incomplete traceability for LOT-010 and LOT-013.\n\n"
        "False lead: packaging label revision CHG-LABEL-042.\n\n"
        "Expected evaluation behavior: leading hypothesis allowed, causality not established.\n",
        encoding="utf-8",
        newline="\n",
    )
    write_json(SCENARIOS / "scenario_index.json", {"notice": NOTICE, "scenarios": scenarios})


def write_manifest(canonical: dict, scenarios: list[dict], anomalies: list[dict]) -> None:
    counts = {
        "product_families": len(canonical["product_families"]),
        "products": len(canonical["products"]),
        "product_versions": len(canonical["product_versions"]),
        "components": len(canonical["components"]),
        "suppliers": len(canonical["suppliers"]),
        "manufacturing_sites": len(canonical["manufacturing_sites"]),
        "lots": len(canonical["lots"]),
        "requirements": len(canonical["requirements"]),
        "changes": len(canonical["changes"]),
        "complaints": len(canonical["complaints"]),
        "investigations": len(canonical["investigations"]),
        "risks": len(canonical["risks"]),
        "failure_modes": len(canonical["failure_modes"]),
        "controls": len(canonical["controls"]),
        "evidence": len(canonical["evidence"]),
        "hypotheses": len(canonical["hypotheses"]),
        "unknowns": len(canonical["unknowns"]),
        "failure_chains": len(canonical["failure_chains"]),
        "scenarios": len(scenarios),
        "intentional_anomalies": len(anomalies),
    }
    digest = hashlib.sha256(json.dumps(canonical, sort_keys=True).encode("utf-8")).hexdigest()
    write_json(
        BASE / "GOLDEN_DATASET_MANIFEST.json",
        {
            "notice": NOTICE,
            "dataset_version": DATASET_VERSION,
            "deterministic_seed": SEED,
            "fictional_company": canonical["tenant"]["name"],
            "synthetic_only": True,
            "canonical_sha256": digest,
            "counts": counts,
            "layers": {
                "source": "data/golden/source",
                "canonical": "data/golden/canonical",
                "ground_truth": "evaluation/ground_truth",
            },
        },
    )


if __name__ == "__main__":
    build_dataset()
    print(f"Generated {DATASET_VERSION}")
