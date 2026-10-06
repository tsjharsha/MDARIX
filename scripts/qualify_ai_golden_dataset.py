"""Validate the controlled AI golden dataset and enforce its qualification lock."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DATA_ROOT = ROOT / "data" / "golden"
CANONICAL = DATA_ROOT / "canonical" / "r1_canonical_golden_dataset.json"
MANIFEST = DATA_ROOT / "GOLDEN_DATASET_MANIFEST.json"
SCENARIOS = ROOT / "evaluation" / "scenarios" / "scenario_index.json"
GROUND = ROOT / "evaluation" / "ground_truth"
LOCK = ROOT / "evaluation" / "GOLDEN_DATASET_QUALIFICATION.json"
DEFAULT_REPORT = ROOT / "artifacts" / "ai-golden-dataset-qualification.json"
EXPECTED_IDS = {f"VS{number:03d}" for number in range(1, 13)}
SYNTHETIC_NOTICE = "SYNTHETIC TEST DATA ONLY"
SECRET_PATTERNS = (re.compile(r"\bgsk_[A-Za-z0-9]{20,}"), re.compile(r"\bgh[oprsu]_[A-Za-z0-9]{20,}"))


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def canonical_hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def file_bundle_hash(root: Path) -> str:
    entries = []
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        entries.append(
            {"path": path.relative_to(root).as_posix(), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
        )
    return canonical_hash(entries)


def hashes() -> dict[str, str]:
    return {
        "canonical_sha256": canonical_hash(read_json(CANONICAL)),
        "source_bundle_sha256": file_bundle_hash(DATA_ROOT / "source"),
        "scenario_index_sha256": canonical_hash(read_json(SCENARIOS)),
        "ground_truth_bundle_sha256": file_bundle_hash(GROUND),
    }


def qualify() -> dict[str, Any]:
    errors: list[str] = []
    for path in (CANONICAL, MANIFEST, SCENARIOS):
        if not path.exists():
            errors.append(f"Missing controlled file: {path.relative_to(ROOT)}")
    if errors:
        return {"status": "FAILED", "errors": errors}

    canonical = read_json(CANONICAL)
    manifest = read_json(MANIFEST)
    index = read_json(SCENARIOS)
    scenarios = index.get("scenarios") or []
    scenario_ids = {item.get("scenario_id") for item in scenarios}
    if scenario_ids != EXPECTED_IDS or len(scenarios) != 12:
        errors.append(f"Scenario set must be exactly VS001-VS012; found {sorted(scenario_ids)}")
    if SYNTHETIC_NOTICE not in str(canonical.get("notice", "")):
        errors.append("Canonical dataset is missing the synthetic-data notice")

    current_hashes = hashes()
    if current_hashes["canonical_sha256"] != manifest.get("canonical_sha256"):
        errors.append("Canonical dataset hash does not match the manifest")

    evidence = {item["evidence_id"]: item for item in canonical.get("evidence", [])}
    anomaly_ids = {item["anomaly_id"] for item in canonical.get("intentional_anomalies", [])}
    forbidden_application_keys = {
        "hidden_ground_truth",
        "correct_answer",
        "actual_root_cause",
        "prohibited_conclusions",
    }

    def walk_keys(value: Any):
        if isinstance(value, dict):
            for key, child in value.items():
                yield key
                yield from walk_keys(child)
        elif isinstance(value, list):
            for child in value:
                yield from walk_keys(child)

    leaked = forbidden_application_keys & set(walk_keys(canonical))
    if leaked:
        errors.append(f"Evaluation-only keys leaked into application-facing data: {sorted(leaked)}")

    for scenario in scenarios:
        sid = scenario.get("scenario_id", "UNKNOWN")
        required_text = ("title", "purpose", "investigation_id", "expected_system_behavior")
        for field in required_text:
            if not str(scenario.get(field, "")).strip():
                errors.append(f"{sid}: missing {field}")
        for field in (
            "expected_evidence",
            "expected_unknowns",
            "prohibited_conclusions",
            "acceptance_criteria",
            "intentional_anomalies",
        ):
            if not scenario.get(field):
                errors.append(f"{sid}: {field} must be non-empty")
        if len(scenario.get("acceptance_criteria") or []) < 4:
            errors.append(f"{sid}: at least four acceptance criteria are required")
        if not (scenario.get("expected_contradictions") or scenario.get("expected_unknowns")):
            errors.append(f"{sid}: must test at least one contradiction or unknown")
        for evidence_id in scenario.get("expected_evidence") or []:
            row = evidence.get(evidence_id)
            if not row:
                errors.append(f"{sid}: expected evidence {evidence_id} does not exist")
            elif row.get("investigation_id") != scenario.get("investigation_id"):
                errors.append(
                    f"{sid}: {evidence_id} belongs to {row.get('investigation_id')}, not {scenario.get('investigation_id')}"
                )
        for anomaly_id in scenario.get("intentional_anomalies") or []:
            if anomaly_id not in anomaly_ids:
                errors.append(f"{sid}: intentional anomaly {anomaly_id} does not exist")
        gt_path = GROUND / sid / "ground_truth.json"
        if not gt_path.exists():
            errors.append(f"{sid}: ground truth file is missing")
            continue
        ground_truth = read_json(gt_path)
        if ground_truth.get("evaluation_only") is not True:
            errors.append(f"{sid}: ground truth is not marked evaluation_only")
        for field in (
            "investigation_id",
            "expected_evidence",
            "expected_contradictions",
            "expected_unknowns",
            "prohibited_conclusions",
            "acceptance_criteria",
            "intentional_anomalies",
        ):
            if ground_truth.get(field) != scenario.get(field):
                errors.append(f"{sid}: ground truth {field} differs from the scenario index")

    for path in [DATA_ROOT, ROOT / "evaluation"]:
        for controlled_file in path.rglob("*"):
            if controlled_file.is_file() and controlled_file.suffix.lower() in {".json", ".csv", ".md"}:
                content = controlled_file.read_text(encoding="utf-8", errors="ignore")
                if any(pattern.search(content) for pattern in SECRET_PATTERNS):
                    errors.append(f"Potential secret in {controlled_file.relative_to(ROOT)}")

    lock = read_json(LOCK) if LOCK.exists() else None
    lock_valid = (
        bool(lock) and lock.get("hashes") == current_hashes and lock.get("status") == "QUALIFIED_FOR_INTERNAL_MVP"
    )
    if not lock:
        errors.append("Qualification lock is missing; use --approve after review")
    elif not lock_valid:
        errors.append("Qualification lock does not match the controlled dataset")

    return {
        "status": "PASS" if not errors else "FAIL",
        "qualification_status": lock.get("status") if lock_valid else "UNQUALIFIED",
        "dataset_version": canonical.get("dataset_version"),
        "scenario_count": len(scenarios),
        "hashes": current_hashes,
        "errors": errors,
        "scope": "Synthetic internal MVP AI assurance; not clinical, regulatory, or production certification.",
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--approve", action="store_true", help="write a reviewed qualification lock")
    parser.add_argument("--reviewer", default="MDARIX Engineering")
    parser.add_argument("--change-control", default="MVP-AI-GOLDEN-001")
    parser.add_argument("--report", default=str(DEFAULT_REPORT))
    args = parser.parse_args()

    if args.approve:
        temporary = qualify()
        non_lock_errors = [item for item in temporary["errors"] if item.startswith("Qualification lock")]
        actual_errors = [item for item in temporary["errors"] if item not in non_lock_errors]
        if actual_errors:
            print("\n".join(actual_errors), file=sys.stderr)
            return 1
        lock = {
            "qualification_version": "MDARIX_AI_GOLDEN_QUALIFICATION_V1",
            "status": "QUALIFIED_FOR_INTERNAL_MVP",
            "qualified_at": datetime.now(timezone.utc).isoformat(),
            "reviewer": args.reviewer,
            "change_control": args.change_control,
            "hashes": temporary["hashes"],
            "scope": temporary["scope"],
            "release_policy": {
                "required_scenarios": 12,
                "allowed_dataset_errors": 0,
                "live_model_gate_required_for_model_promotion": True,
            },
        }
        LOCK.write_text(json.dumps(lock, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    report = qualify()
    report["generated_at"] = datetime.now(timezone.utc).isoformat()
    report_path = Path(args.report)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"AI golden dataset qualification: {report['status']} ({report['scenario_count']} scenarios)")
    for error in report["errors"]:
        print(f"- {error}")
    print(f"Report: {report_path}")
    return 0 if report["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
