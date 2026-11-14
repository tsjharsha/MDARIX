"""scripts/health_report.py (B6b Part D, D3; MDX-OPS-002): the monthly report of one customer organisation, built from
the registers only. Scenario row B6-56: a health report holds no other organisation's data."""

from __future__ import annotations

import csv
import importlib.util
import json
from datetime import date
from pathlib import Path

import pytest

from reports import pdf

ROOT = Path(__file__).resolve().parents[1]
_SPEC = importlib.util.spec_from_file_location("health_report", ROOT / "scripts" / "health_report.py")
health_report = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(health_report)

pytestmark = pytest.mark.unit
GENERATED = date(2026, 12, 2)


def _write(path: Path, rows: list[dict]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def _incident(number: int, customers: str, minutes: int, summary: str, category: str = "OUTAGE", **extra) -> dict:
    return {
        "incident_id": f"INC-2026-{number:03d}",
        "opened_utc": extra.get("opened", "2026-11-10T04:00:00Z"),
        "closed_utc": extra.get("closed", "2026-11-10T05:00:00Z"),
        "category": category,
        "severity": "S2",
        "customers": customers,
        "minutes_down": str(minutes),
        "summary": summary,
        "root_cause": "",
        "deviation_id": "",
        "capa_id": "",
        "customer_notice": "",
        "status": "CLOSED",
    }


def _ops(number: int, day: str, kind: str, customers: str, summary: str) -> dict:
    return {
        "entry_id": f"OPS-2026-{number:03d}",
        "date_utc": day,
        "type": kind,
        "customers": customers,
        "summary": summary,
        "result": "PASS",
        "reference": f"record {number}",
        "by": "Sriharsha T.",
    }


@pytest.fixture
def registers(tmp_path):
    _write(
        tmp_path / "incidents.csv",
        [
            _incident(1, "ALL", 60, "API unavailable for every customer"),
            _incident(2, "CUS-001", 30, "Mail-in delay for one organisation"),
            _incident(3, "CUS-002", 500, "Data plane of the other organisation unavailable"),
            _incident(4, "CUS-001 CUS-002", 0, "Nightly backup failed", category="BACKUP"),
            _incident(5, "ALL", 999, "October outage", opened="2026-10-02T01:00:00Z", closed="2026-10-02T17:39:00Z"),
        ],
    )
    _write(
        tmp_path / "operations-log.csv",
        [
            _ops(1, "2026-11-03", "RESTORE_DRILL", "ALL", "Quarterly restore drill"),
            _ops(2, "2026-11-20", "RELEASE", "ALL", "Release 0.11.04, change notice CN-2026-004"),
            _ops(3, "2026-11-21", "RELEASE", "CUS-002", "Dedicated plane upgrade of the other organisation"),
            _ops(4, "2026-11-25", "CLOCK_CHECK", "ALL", "Clock check ok"),
            _ops(5, "2026-12-15", "PLANNED_CHANGE", "ALL", "Release 0.11.05"),
            _ops(6, "2026-12-16", "PLANNED_CHANGE", "CUS-002", "Move of the other organisation to its own cell"),
        ],
    )
    _write(
        tmp_path / "deviation-log.csv",
        [
            {"dev_id": "DEV-0.11.04-009", "classification": "minor", "gxp_risk": "low", "status": "open"},
            {"dev_id": "DEV-0.11.04-001", "classification": "major", "gxp_risk": "high", "status": "closed"},
        ],
    )
    return tmp_path


def _build(registers, code="CUS-001"):
    return health_report.build(code, "2026-11", GENERATED, registers, registers / "deviation-log.csv")


@pytest.mark.requirement("B6-56")
def test_a_health_report_holds_no_other_organisations_data(registers):
    report = _build(registers)
    assert [item["incident_id"] for item in report["incidents"]] == ["INC-2026-001", "INC-2026-002", "INC-2026-004"]
    assert [item["entry_id"] for item in report["releases"]] == ["OPS-2026-002"]
    assert [item["entry_id"] for item in report["planned_changes"]] == ["OPS-2026-005"]
    text = json.dumps(report) + pdf.text_of(health_report.as_pdf(report))
    for other in ("CUS-002", "INC-2026-003", "other organisation", "OPS-2026-003", "OPS-2026-006"):
        assert other not in text
    # A row shared with another customer shows its reach, never the other customer's code.
    assert {item["reach"] for item in report["incidents"]} == {"all customers", "your organisation"}


@pytest.mark.requirement("B6-56")
def test_register_text_naming_another_customer_refuses_the_report(registers):
    rows = list(csv.DictReader((registers / "incidents.csv").open(encoding="utf-8")))
    rows[0]["summary"] = "API unavailable; first reported by CUS-002"
    _write(registers / "incidents.csv", rows)
    with pytest.raises(health_report.Refused, match="other customer code"):
        _build(registers)
    assert health_report.main(["--customer", "CUS-001", "--month", "2026-11", "--registers", str(registers)]) == 1


def test_uptime_against_the_target_from_the_minutes_down(registers):
    uptime = _build(registers)["uptime"]
    # November: 43,200 minutes; 60 (all) + 30 (this organisation) down; October's outage and the other's not counted.
    assert uptime["minutes_down"] == 90 and uptime["minutes_in_month"] == 43200
    assert uptime["percent"] == 99.792 and uptime["met"] is True
    assert "incident register" in uptime["source"]
    other = _build(registers, "CUS-002")["uptime"]
    assert other["minutes_down"] == 560 and other["met"] is False


def test_the_report_lists_drills_clock_backups_deviations_and_the_chain_line(registers):
    report = _build(registers)
    assert report["last_restore_drill"]["entry_id"] == "OPS-2026-001"
    assert report["last_clock_check"]["entry_id"] == "OPS-2026-004"
    assert report["last_recovery_record"] is None
    assert report["backups"]["failures_this_month"] == ["INC-2026-004"]
    assert report["open_deviations"] == [
        {"dev_id": "DEV-0.11.04-009", "classification": "minor", "gxp_risk": "low", "status": "open"}
    ]
    assert "result is available on request" in report["audit_chain"]


def test_bad_inputs_are_refused(registers):
    with pytest.raises(health_report.Refused, match="CUS-nnn"):
        _build(registers, "Acme")
    with pytest.raises(health_report.Refused, match="YYYY-MM"):
        health_report.build("CUS-001", "November", GENERATED, registers, registers / "deviation-log.csv")


def test_the_same_registers_and_date_give_the_same_files(registers, tmp_path):
    args = ["--customer", "CUS-001", "--month", "2026-11", "--date", "2026-12-02", "--registers", str(registers)]
    args += ["--deviation-log", str(registers / "deviation-log.csv")]
    first, second = tmp_path / "one", tmp_path / "two"
    assert health_report.main([*args, "--out", str(first)]) == 0
    assert health_report.main([*args, "--out", str(second)]) == 0
    for name in ("health-CUS-001-2026-11.json", "health-CUS-001-2026-11.pdf"):
        assert (first / name).read_bytes() == (second / name).read_bytes()


def test_the_repository_registers_build_a_report():
    report = health_report.build("CUS-001", "2026-11", GENERATED)
    assert report["last_restore_drill"]["entry_id"] == "OPS-2026-004"


def test_a_missing_register_or_a_bad_value_is_refused_never_a_clean_report(registers, tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    with pytest.raises(health_report.Refused, match="incidents.csv not found"):
        health_report.build("CUS-001", "2026-11", GENERATED, empty, registers / "deviation-log.csv")
    rows = list(csv.DictReader((registers / "incidents.csv").open(encoding="utf-8")))
    rows[1]["minutes_down"] = "45.5"
    _write(registers / "incidents.csv", rows)
    with pytest.raises(health_report.Refused, match="whole number"):
        _build(registers)
    rows[1]["minutes_down"] = "30"
    rows[1]["opened_utc"] = "2026-11-10T04:00:00"  # no zone
    _write(registers / "incidents.csv", rows)
    with pytest.raises(health_report.Refused, match="needs its zone"):
        _build(registers)


def test_a_spreadsheet_saved_register_a_local_time_and_a_lower_case_code(registers):
    rows = list(csv.DictReader((registers / "incidents.csv").open(encoding="utf-8")))
    # 02:00 IST on 1 Dec is 20:30 UTC on 30 Nov: a November incident.
    rows[1]["opened_utc"] = "2026-12-01T02:00:00+05:30"
    _write(registers / "incidents.csv", rows)
    text = (registers / "incidents.csv").read_text(encoding="utf-8")
    (registers / "incidents.csv").write_text("﻿" + text, encoding="utf-8")
    assert "INC-2026-002" in [item["incident_id"] for item in _build(registers)["incidents"]]
    rows[0]["summary"] = "first reported by cus-002"
    _write(registers / "incidents.csv", rows)
    with pytest.raises(health_report.Refused, match="other customer code"):
        _build(registers)


def test_downtime_never_exceeds_the_month(registers):
    rows = list(csv.DictReader((registers / "incidents.csv").open(encoding="utf-8")))
    rows[0]["minutes_down"] = "50000"
    _write(registers / "incidents.csv", rows)
    uptime = _build(registers)["uptime"]
    assert uptime["minutes_down"] == 43200 and uptime["percent"] == 0.0
