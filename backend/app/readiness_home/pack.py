"""The inspection pack: everything Readiness shows, in one ZIP, for the day an inspector or auditor arrives.

``build_pack`` writes, for one organization and period:

- ``00-README.txt``: what the pack holds, for whom, the regulatory basis each file supports (from the one catalog in
  backend/app/standards.py), how to check it is complete, and its limits;
- ``01-readiness-summary.pdf``: the management review summary (summary.py), as Readiness downloads it;
- ``02-inspection-checks.csv``: every inspection check with its state, number, detail, why it matters and its basis;
- one CSV per check with every record behind it (not the first few the home screen names): hidden complaints, the
  backlog past target, reporting clocks, harm complaints closed without a case, signals past their triage date, trends
  without CAPA or risk review, CAPAs without a verified effect, products whose post-market data has not reached the
  risk file;
- ``manifest.json``: each file's SHA-256, so anyone can check the pack has not changed since it was made.

Read from the organization's records with the same functions the checks use, so the pack and the screen agree. Rules
only; nothing is changed. The route (router.py) audits every export.
"""

from __future__ import annotations

import csv
import hashlib
import io
import json
import zipfile
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from backend.app.csv_safe import safe_cell
from backend.app.readiness_home import service, summary
from backend.app.standards import BY_ID, DISCLAIMER, entries, known

PACK_VERSION = "MDARIX_INSPECTION_PACK_V1"
EVERYTHING = 10**6


def _text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "Yes" if value else "No"
    if isinstance(value, (list, tuple)):
        return "; ".join(_text(item) for item in value if _text(item))
    if isinstance(value, dict):
        return _text(value.get("label") or value.get("name") or value.get("business_id"))
    return " ".join(str(value).split())


def _cell(value):
    """A value as the pack's CSV holds it: a number as itself, anything else as text a spreadsheet never runs as a
    formula (csv_safe.safe_cell). Record names and descriptions come from people, and colleagues and inspectors open
    the pack in a spreadsheet (SEC-06)."""
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return value
    return safe_cell(_text(value))


def _csv(header: list[str], rows: list[list]) -> bytes:
    """UTF-8 with a byte-order mark, so spreadsheet programs read the characters right."""
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\r\n")
    writer.writerow(header)
    for row in rows:
        writer.writerow([_cell(value) for value in row])
    return ("﻿" + buffer.getvalue()).encode("utf-8")


def _ref(item: dict) -> str:
    return item.get("business_id") or item.get("complaint_identifier") or item.get("id") or ""


def _labels(items) -> list[str]:
    return [item.get("label") for item in items or [] if isinstance(item, dict) and item.get("label")]


def hidden_complaints(db: Session, tenant_id, today) -> bytes:
    from backend.app.complaint_review.service import second_look

    items = second_look(db, None, tenant_id, state="open", page=1, page_size=EVERYTHING, today=today)["items"]
    return _csv(
        ["Complaint", "Source ID", "Product", "Version", "Status", "Type", "Received", "Why flagged", "Signs"],
        [
            [
                _ref(item),
                item.get("complaint_identifier"),
                item.get("product_name"),
                item.get("version"),
                item.get("status"),
                item.get("complaint_type"),
                item.get("received_date"),
                _labels(item.get("reasons")),
                _labels(item.get("signs")),
            ]
            for item in items
        ],
    )


def backlog_past_target(db: Session, tenant_id, today) -> bytes:
    from backend.app.complaint_review.service import backlog

    found = backlog(db, tenant_id, show="past_target", page=1, page_size=EVERYTHING, today=today)
    target = found["summary"].get("target_days")
    return _csv(
        ["Complaint", "Source ID", "Product", "Version", "Status", "Received", "Age (days)", "Target (days)"],
        [
            [
                _ref(item),
                item.get("complaint_identifier"),
                item.get("product_name"),
                item.get("version"),
                item.get("status"),
                item.get("received_date"),
                item.get("age_days"),
                target,
            ]
            for item in found["items"]
        ],
    )


def reporting_clocks(db: Session, tenant_id, today) -> bytes:
    from backend.app.reportability.service import watch

    found = watch(db, None, tenant_id, show="open", page=1, page_size=EVERYTHING, today=today)
    flagged = [item for item in found["items"] if item["state"] in ("OVERDUE", "DUE_SOON") or item.get("follow_ups")]
    rows = []
    for item in flagged:
        binding = item.get("binding") or {}
        rows.append(
            [
                _ref(item),
                item.get("complaint_identifier"),
                item.get("product_name"),
                item.get("country"),
                item.get("state"),
                binding.get("window"),
                binding.get("due_date"),
                binding.get("days_left"),
                _labels(item.get("follow_ups")),
            ]
        )
    return _csv(
        ["Complaint", "Source ID", "Product", "Country", "State", "Window", "Due", "Days left", "Missing answers"],
        rows,
    )


def harm_closed(db: Session, tenant_id, today) -> bytes:
    return _csv(
        ["Complaint", "Source ID", "Product", "Status"],
        [
            [row.business_id or row.complaint_identifier, row.complaint_identifier, row.name, row.status]
            for row in service.harm_closed_rows(db, tenant_id, today)
        ],
    )


def triage_overdue(db: Session, tenant_id, today) -> bytes:
    return _csv(
        ["Signal", "Title", "Status", "Triage due"],
        [
            [
                row.business_id,
                service.signal_title(row),
                row.status,
                row.due_at.date().isoformat() if row.due_at else None,
            ]
            for row in service.triage_overdue_rows(db, tenant_id)
        ],
    )


def trends_without_action(db: Session, tenant_id, today) -> bytes:
    decided, rising = service.trends_without_action_rows(db, tenant_id, today)
    rows = [
        ["Decided signal, no CAPA and no risk review", row.business_id, service.signal_title(row), None]
        for row in decided
    ]
    rows += [["Significant rise, no signal", None, item.get("name"), item.get("sentence")] for item in rising]
    return _csv(["Finding", "Signal", "Name", "Trend check"], rows)


def capa_effectiveness(db: Session, tenant_id, today) -> bytes:
    from backend.app.capa_effectiveness.service import board

    items = board(db, None, tenant_id, show="attention", page=1, page_size=EVERYTHING, today=today)["items"]
    rows = []
    for item in items:
        if item.get("state") not in ("NOT_PLANNED", "OVERDUE"):
            continue
        capa = item.get("capa") or {}
        rows.append(
            [
                capa.get("business_id") or capa.get("capa_identifier"),
                capa.get("capa_identifier"),
                capa.get("title"),
                capa.get("product_name"),
                capa.get("status"),
                item.get("state"),
                item.get("closed_without_check"),
                item.get("planned_on"),
            ]
        )
    return _csv(
        ["CAPA", "Source ID", "Title", "Product", "Status", "Check", "Closed without a check", "Check day"], rows
    )


def risk_file_input(db: Session, tenant_id, today) -> bytes:
    from backend.app.post_market import risk_file

    flagged = (risk_file.NOT_REVIEWED, risk_file.OVERDUE, risk_file.OPEN, risk_file.NO_REGISTER)
    rows = []
    for item in risk_file.board(db, tenant_id, today=today)["items"]:
        if item.get("state") not in flagged:
            continue
        market, file = item.get("post_market") or {}, item.get("risk_file") or {}
        rows.append(
            [
                (item.get("product") or {}).get("name"),
                item.get("label"),
                market.get("complaints"),
                market.get("harm"),
                market.get("malfunction"),
                market.get("signals_decided"),
                file.get("risks"),
                file.get("risk_reviews"),
                file.get("last_review_at"),
                file.get("reassessments_open"),
                file.get("reassessments_overdue"),
            ]
        )
    return _csv(
        [
            "Product",
            "State",
            "Complaints",
            "Harm",
            "Malfunction",
            "Signals decided",
            "Risks",
            "Risk reviews",
            "Last review",
            "Reassessments open",
            "Reassessments overdue",
        ],
        rows,
    )


# file name, check code, writer
CHECK_FILES = (
    ("03-hidden-complaints.csv", "COMPLAINTS_TO_RECHECK", hidden_complaints),
    ("04-complaints-past-target.csv", "COMPLAINTS_PAST_TARGET", backlog_past_target),
    ("05-reporting-clocks.csv", "REPORTING_CLOCKS", reporting_clocks),
    ("06-harm-closed-without-investigation.csv", "HARM_CLOSED_WITHOUT_CASE", harm_closed),
    ("07-signals-past-triage-date.csv", "TRIAGE_OVERDUE", triage_overdue),
    ("08-trends-without-capa-or-risk-review.csv", "TRENDS_WITHOUT_ACTION", trends_without_action),
    ("09-capas-without-verified-effect.csv", "CAPA_EFFECTIVENESS", capa_effectiveness),
    ("10-risk-file-input.csv", "RISK_FILE_INPUT", risk_file_input),
)


# The basis of the files that are not one check's records, as catalog ids: the summary is organized by the
# management review inputs; the manifest keeps any change to a file identifiable, as the control of records asks.
FILE_BASIS = {
    "01-readiness-summary.pdf": ("ISO13485_5_6_2",),
    "manifest.json": ("ISO13485_4_2_5",),
}


def _shorts(ids) -> str:
    return "; ".join(BY_ID[code].short for code in ids)


def file_basis(name: str) -> list[str]:
    """The catalog ids a file of the pack supports: a check's records carry the check's basis, the list of checks
    every check's."""
    checks = {file: code for file, code, _ in CHECK_FILES}
    if name in checks:
        return list(service.BASIS.get(checks[name], ()))
    if name == "02-inspection-checks.csv":
        return known(code for _, check, _ in CHECK_FILES for code in service.BASIS.get(check, ()))
    return list(FILE_BASIS.get(name, ()))


def _checks_csv(readiness: dict) -> bytes:
    files = {code: name for name, code, _ in CHECK_FILES}
    return _csv(
        ["Check", "Title", "State", "Number", "Detail", "Why it matters", "Basis", "Records in"],
        [
            [
                check.get("code"),
                check.get("title"),
                check.get("state"),
                check.get("value"),
                check.get("detail"),
                check.get("why"),
                [chip.get("short") for chip in check.get("basis") or []],
                files.get(check.get("code")),
            ]
            for check in readiness.get("checks", [])
        ],
    )


def _readme(organization: str, generated_at: str, period: dict, readiness: dict, names: list[str]) -> bytes:
    counts = readiness.get("summary") or {}
    inside = []
    for name in [*names, "manifest.json"]:
        basis = file_basis(name)
        label = "manifest.json (the SHA-256 of every file above)" if name == "manifest.json" else name
        inside.append(f"  {label}" + (f"; basis: {_shorts(basis)}" if basis else ""))
    cited = known(code for name in [*names, "manifest.json"] for code in file_basis(name))
    lines = [
        "MDARIX inspection pack",
        "",
        f"Organization: {organization}",
        f"Generated: {generated_at}",
        f"Summary period: {period.get('from')} to {period.get('to')} ({period.get('days')} days)",
        f"Inspection checks: {counts.get('clear', 0)} of {counts.get('checks', 0)} clear, "
        f"{counts.get('critical', 0)} critical, {counts.get('attention', 0)} needing attention, "
        f"{counts.get('not_set', 0)} not set up",
        "",
        "What is inside, with the basis each file supports",
        *inside,
        "",
        "Standards referenced",
        *[f"  {entry['short']}: {entry['title']} ({entry['jurisdiction']})" for entry in entries(cited)],
        f"  {DISCLAIMER}",
        "",
        "How to use it",
        "  Start with 01-readiness-summary.pdf, organized by the management review inputs of ISO 13485 clause 5.6.2.",
        "  02-inspection-checks.csv lists every check with its basis; each check names the file with every record "
        "behind it.",
        "  To confirm nothing changed since export, compare each file's SHA-256 with manifest.json.",
        "",
        "Limits",
        "  Read from the records as imported into MDARIX on the date above; verify against the source records.",
        "  The checks are rules, not regulatory determinations. A person decides reportability, cause and closure.",
        "",
    ]
    return "\r\n".join(lines).encode("utf-8")


def build_pack(
    db: Session,
    tenant_id,
    *,
    organization: str,
    period_days: int = summary.PERIOD_DEFAULT,
    now: datetime | None = None,
) -> tuple[bytes, dict]:
    """(the ZIP's bytes, its manifest). A check whose records cannot be read gets a file saying so; the pack is still
    made."""
    now = now or datetime.now(timezone.utc)
    today = now.date()
    generated_at = now.strftime("%Y-%m-%d %H:%M UTC")
    data = summary.build(db, tenant_id, period_days=period_days, today=today)
    files: list[tuple[str, bytes]] = [
        ("01-readiness-summary.pdf", summary.render_pdf(data, organization, generated_at)),
        ("02-inspection-checks.csv", _checks_csv(data["readiness"])),
    ]
    unreadable = []
    for name, code, writer in CHECK_FILES:
        try:
            content = writer(db, tenant_id, today)
        except Exception:  # one list that cannot be read never stops the pack; the file says so
            db.rollback()
            unreadable.append(code)
            content = _csv(["Note"], [[f"The records behind {code} could not be read when this pack was made."]])
        files.append((name, content))
    names = [name for name, _ in files]
    readme = _readme(organization, generated_at, data["period"], data["readiness"], names)
    files.insert(0, ("00-README.txt", readme))
    manifest = {
        "pack_version": PACK_VERSION,
        "organization": organization,
        "generated_at": now.isoformat(),
        "period": data["period"],
        "checks": data["readiness"].get("summary"),
        "unreadable": unreadable,
        "files": [
            {"name": name, "bytes": len(content), "sha256": hashlib.sha256(content).hexdigest()}
            for name, content in files
        ],
    }
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in files:
            archive.writestr(name, content)
        archive.writestr("manifest.json", json.dumps(manifest, indent=2, ensure_ascii=False))
    return buffer.getvalue(), manifest
