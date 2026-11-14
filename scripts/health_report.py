"""Monthly service health report for one customer organisation (B6b Part D, D3; G9; record MDX-OPS-002).

    python scripts/health_report.py --customer CUS-001 --month 2026-11 [--date 2026-12-02] [--out artifacts/health]

Built only from the registers in the repository (owner decision B6b-D11, "if no answer" default: no production
reads): ``docs/validation/registers/incidents.csv`` and ``operations-log.csv`` (MDX-OPS-003) and
``docs/validation/deviation-log.csv`` (MDX-VAL-010). Customers are named by code (``CUS-nnn``); the key from code to
name is kept outside the repository.

The report holds: uptime against the 99.5 % target with its source (the incident register's minutes down), downtime
minutes, the incidents that touched this organisation, the releases deployed with their change notices, the open
deviations, backups (failures recorded as incidents), the last restore drill and recovery record, the last clock
check, the audit chain line, and the planned changes. A register row is used only when its ``customers`` field is
``ALL`` or names this customer; every other organisation's rows are left out, and the report is refused (exit 1) if
any text in it names another customer code (B6-56). The quality approver reviews the PDF before it is sent.

Writes ``health-<customer>-<month>.json`` and ``.pdf``; the same registers and ``--date`` give the same files.
"""

from __future__ import annotations

import argparse
import calendar
import csv
import json
import re
import sys
from datetime import date, datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

REGISTERS = ROOT / "docs" / "validation" / "registers"
DEVIATION_LOG = ROOT / "docs" / "validation" / "deviation-log.csv"
SLO_PERCENT = 99.5  # owner-approved uptime target (3 Nov 2026)
CODE = re.compile(r"^CUS-\d{3}$")
ANY_CODE = re.compile(r"\bCUS-\d{3}\b", re.IGNORECASE)
CHAIN_LINE = (
    "Verified daily by the scheduler for every organisation; your organisation's result is available on request "
    "(no production data is read for this report, owner decision B6b-D11)."
)


class Refused(Exception):
    """The report would show another organisation's data, or an input is not valid."""


def _rows(path: Path, required: bool = True) -> list[dict]:
    """A register's rows; a missing register is refused (a wrong folder must never give a clean report). A file saved
    by a spreadsheet keeps working (byte-order mark); a row with more fields than the header is refused."""
    if not path.is_file():
        if required:
            raise Refused(f"register {path.name} not found in {path.parent}")
        return []
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = []
        for number, row in enumerate(csv.DictReader(handle), start=2):
            if None in row:
                raise Refused(f"{path.name} line {number}: more fields than the header")
            rows.append({k: (v or "").strip() for k, v in row.items()})
        return rows


def _day(value: str) -> date | None:
    """A register date: ``YYYY-MM-DD`` or an ISO time in UTC (only its day is used)."""
    if not value:
        return None
    try:
        if "T" not in value:
            return date.fromisoformat(value)
        moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise Refused(f"date {value!r}: expected YYYY-MM-DD or YYYY-MM-DDTHH:MM:SSZ") from exc
    if moment.tzinfo is None:
        raise Refused(f"time {value!r}: needs its zone (UTC: end it with Z)")
    return moment.astimezone(timezone.utc).date()


def _minutes(row: dict) -> int:
    value = row["minutes_down"] or "0"
    if not value.isdigit():
        raise Refused(f"{row['incident_id']}: minutes_down {value!r} is not a whole number of minutes")
    return int(value)


def concerns(customers: str, code: str) -> bool:
    """A row concerns this customer when its ``customers`` field is ALL or names the code."""
    names = set(re.split(r"[\s;,]+", customers.strip().upper())) - {""}
    return "ALL" in names or code in names


def _scope(customers: str) -> str:
    """How a row's reach is shown: never the other customers' codes."""
    return "all customers" if "ALL" in re.split(r"[\s;,]+", customers.strip().upper()) else "your organisation"


def build(
    code: str, month: str, generated: date, registers: Path = REGISTERS, deviations: Path = DEVIATION_LOG
) -> dict:
    if not CODE.match(code):
        raise Refused(f"customer code {code!r}: expected CUS-nnn")
    try:
        year, number = (int(part) for part in month.split("-"))
        start = date(year, number, 1)
    except ValueError as exc:
        raise Refused(f"month {month!r}: expected YYYY-MM") from exc
    end = date(year, number, calendar.monthrange(year, number)[1])
    minutes_in_month = end.day * 24 * 60

    incidents = []
    for row in _rows(registers / "incidents.csv"):
        opened, closed = _day(row["opened_utc"]), _day(row["closed_utc"])
        if not concerns(row["customers"], code) or opened is None or opened > end or (closed and closed < start):
            continue
        incidents.append(
            {
                "incident_id": row["incident_id"],
                "opened_utc": row["opened_utc"],
                "closed_utc": row["closed_utc"] or "open",
                "category": row["category"],
                "severity": row["severity"],
                "reach": _scope(row["customers"]),
                # shortcut: an incident's minutes count in the month it opened (a cross-month outage is not split)
                "minutes_down": _minutes(row) if start <= opened <= end else 0,
                "summary": row["summary"],
                "customer_notice": row["customer_notice"],
                "status": row["status"],
            }
        )
    # shortcut: overlapping incidents add up; the total is capped at the month's minutes
    down = min(sum(item["minutes_down"] for item in incidents), minutes_in_month)
    uptime = round(100 * (1 - down / minutes_in_month), 3)

    log = [row for row in _rows(registers / "operations-log.csv") if concerns(row["customers"], code)]

    def entries(kind: str, *, after: date | None = None, upto: date | None = None) -> list[dict]:
        found = []
        for row in log:
            day = _day(row["date_utc"])
            if row["type"] != kind or day is None:
                continue
            if (after and day <= after) or (upto and day > upto):
                continue
            found.append({key: row[key] for key in ("entry_id", "date_utc", "summary", "result", "reference")})
        return sorted(found, key=lambda item: item["date_utc"])

    def latest(kind: str) -> dict | None:
        found = entries(kind, upto=end)
        return found[-1] if found else None

    releases = [item for item in entries("RELEASE", upto=end) if _day(item["date_utc"]) >= start]
    open_deviations = [
        {key: row[key] for key in ("dev_id", "classification", "gxp_risk", "status")}
        for row in _rows(deviations)
        if row.get("status", "").lower() != "closed"
    ]
    backup_failures = [item["incident_id"] for item in incidents if item["category"].upper() == "BACKUP"]
    report = {
        "report": "MDARIX monthly service health report (MDX-OPS-002)",
        "customer": code,
        "month": month,
        "period": {"from": start.isoformat(), "to": end.isoformat()},
        "generated": generated.isoformat(),
        "uptime": {
            "percent": uptime,
            "target_percent": SLO_PERCENT,
            "met": uptime >= SLO_PERCENT,
            "minutes_down": down,
            "minutes_in_month": minutes_in_month,
            "source": "incident register, minutes down of the incidents that reached your organisation "
            "(no monitoring data is read: owner decision B6b-D11)",
        },
        "incidents": incidents,
        "releases": releases,
        "open_deviations": open_deviations,
        "backups": {
            "how": "Daily encrypted backup copied off-site; an alert when the newest is older than 26 hours "
            "(scripts/check_backup_age.sh)",
            "failures_this_month": backup_failures,
        },
        "last_restore_drill": latest("RESTORE_DRILL"),
        "last_recovery_record": latest("RECOVERY_RECORD"),
        "last_clock_check": latest("CLOCK_CHECK"),
        "audit_chain": CHAIN_LINE,
        "planned_changes": entries("PLANNED_CHANGE", after=end),
    }
    others = sorted({found.upper() for found in ANY_CODE.findall(json.dumps(report))} - {code})
    if others:
        # Register text names another customer: the report is not produced (B6-56); the register row is corrected.
        raise Refused(f"the report would name {len(others)} other customer code(s); correct the register text")
    return report


def as_pdf(report: dict) -> bytes:
    from reports import pdf

    uptime = report["uptime"]
    body: list[tuple[str, str]] = [
        ("Availability", "heading"),
        (
            f"Uptime {uptime['percent']} % against the {uptime['target_percent']} % target: "
            f"{'met' if uptime['met'] else 'NOT met'}. Downtime {uptime['minutes_down']} minutes "
            f"of {uptime['minutes_in_month']}.",
            "body",
        ),
        (f"Source: {uptime['source']}.", "muted"),
    ]

    def section(title: str, value, empty: str) -> None:
        body.append((title, "heading"))
        body.extend(pdf.flatten(value) if value else [(empty, "body")])

    section("Incidents that reached your organisation", report["incidents"], "None.")
    section("Releases deployed, with their change notices", report["releases"], "None this month.")
    section("Open deviations", report["open_deviations"], "None.")
    section("Backups", report["backups"], "-")
    section("Last restore drill", report["last_restore_drill"], "None recorded.")
    section("Last recovery record", report["last_recovery_record"], "None recorded (no recovery so far).")
    section("Last clock check", report["last_clock_check"], "None recorded.")
    section("Audit trail chain", report["audit_chain"], "-")
    section("Planned changes", report["planned_changes"], "None announced.")
    body.append(("Review", "heading"))
    body.append(("Reviewed by the quality approver before sending: name ________ date ________", "body"))
    return pdf.render(
        f"MDARIX service health report, {report['month']}",
        [
            f"Customer: {report['customer']}",
            f"Period {report['period']['from']} to {report['period']['to']} (UTC)",
            f"Generated {report['generated']}",
        ],
        body,
        watermark="HEALTH REPORT",
        footer=f"MDX-OPS-002 {report['customer']} {report['month']}",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--customer", required=True, help="customer code, CUS-nnn")
    parser.add_argument("--month", required=True, help="YYYY-MM")
    parser.add_argument("--date", default=datetime.now(timezone.utc).date().isoformat(), help="generation date")
    parser.add_argument("--registers", type=Path, default=REGISTERS)
    parser.add_argument("--deviation-log", type=Path, default=DEVIATION_LOG)
    parser.add_argument("--out", type=Path, default=ROOT / "artifacts" / "health")
    args = parser.parse_args(argv)
    try:
        report = build(args.customer, args.month, date.fromisoformat(args.date), args.registers, args.deviation_log)
    except Refused as exc:
        print(f"Refused: {exc}", file=sys.stderr)
        return 1
    args.out.mkdir(parents=True, exist_ok=True)
    stem = args.out / f"health-{report['customer']}-{report['month']}"
    stem.with_suffix(".json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    stem.with_suffix(".pdf").write_bytes(as_pdf(report))
    print(f"Saved {stem}.json and {stem}.pdf")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
