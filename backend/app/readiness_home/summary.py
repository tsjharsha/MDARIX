"""The readiness summary for management review, as data and as a PDF.

Organized by the management review inputs of ISO 13485:2016 clause 5.6.2 that MDARIX holds records for (feedback and
complaint handling, reporting to regulatory authorities, corrective and preventive action), with the trend check and
today's readiness checks; under the QMSR, FDA can now read management review records. Counts come from the
organization's records as imported into MDARIX for the period chosen; nothing here is a conclusion or advice. The
summary ends with the standards it references (the sections' clauses, each check's basis and the reporting windows'
basis), from the one catalog in backend/app/standards.py.
"""

from __future__ import annotations

import textwrap
import uuid
from collections import Counter
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.app.complaint_review import rules as review_rules
from backend.app.db.models.capa_effectiveness import CapaEffectivenessCheck
from backend.app.db.models.complaint_review import ComplaintSecondLook
from backend.app.db.models.foundation import Capa, Complaint, Product, ProductVersion
from backend.app.db.models.reportability import ComplaintReportability
from backend.app.db.models.signals import Signal
from backend.app.readiness_home import service
from backend.app.reportability import rules as report_rules
from backend.app.standards import DISCLAIMER, entries, known

PERIOD_DEFAULT, PERIOD_MIN, PERIOD_MAX = 365, 30, 1095
TOP_GROUPS = 15
WATERMARK = "MANAGEMENT REVIEW INPUT - VERIFY AGAINST SOURCE RECORDS"
# The clauses the sections' headings cite, as catalog ids: management review inputs (sections 2, 3 and 6) and
# post-production information in the risk file (section 5).
SECTION_BASIS = ("ISO13485_5_6_2", "ISO14971_10")
# The standards table's column widths in characters (the PDF is set in Courier, so the columns line up).
SHORT_WIDTH, TITLE_WIDTH = 25, 52
STATE_WORDS = {
    service.CLEAR: "clear",
    service.ATTENTION: "needs attention",
    service.CRITICAL: "critical",
    service.NOT_SET: "not set up",
}


def _midnight(day: date) -> datetime:
    return datetime.combine(day, datetime.min.time(), tzinfo=timezone.utc)


def _day(value) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        moment = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        return moment.astimezone(timezone.utc).date()
    return value


def _n(count: int, noun: str, plural: str | None = None) -> str:
    """ "1 CAPA", "3 CAPAs", "4,993 complaints" (grouped the en-US way, DEV-025)."""
    return f"{count:,} {noun if count == 1 else (plural or noun + 's')}"


def build(db: Session, tenant_id: uuid.UUID, *, period_days: int = PERIOD_DEFAULT, today: date | None = None) -> dict:
    """Everything the summary shows, for ``period_days`` up to ``today`` (included)."""
    today = today or service.today_utc()
    start = today - timedelta(days=period_days - 1)
    begin, end = _midnight(start), _midnight(today + timedelta(days=1))
    received = func.coalesce(Complaint.complaint_timestamp, Complaint.event_timestamp, Complaint.created_at)

    rows = (
        db.query(
            Complaint.status,
            Complaint.death,
            Complaint.serious_injury,
            Complaint.malfunction,
            Product.name,
            ProductVersion.version_identifier,
        )
        .outerjoin(Product, (Product.tenant_id == Complaint.tenant_id) & (Product.id == Complaint.product_id))
        .outerjoin(
            ProductVersion,
            (ProductVersion.tenant_id == Complaint.tenant_id) & (ProductVersion.id == Complaint.product_version_id),
        )
        .filter(Complaint.tenant_id == tenant_id, received >= begin, received < end)
        .all()
    )
    groups = Counter(
        f"{name or 'No product'} {version or '(version not recorded)'}" for _, _, _, _, name, version in rows
    )
    complaints = {
        "received": len(rows),
        "closed": sum(1 for row in rows if review_rules.is_closed(row.status)),
        "death": sum(1 for row in rows if row.death),
        "serious_injury": sum(1 for row in rows if row.serious_injury),
        "malfunction": sum(1 for row in rows if row.malfunction),
        "by_product_version": [{"group": name, "complaints": count} for name, count in groups.most_common(TOP_GROUPS)],
        "more_groups": max(0, len(groups) - TOP_GROUPS),
    }
    second_look = Counter(
        decision
        for (decision,) in db.query(ComplaintSecondLook.decision).filter(
            ComplaintSecondLook.tenant_id == tenant_id,
            ComplaintSecondLook.decided_at >= begin,
            ComplaintSecondLook.decided_at < end,
        )
    )
    decisions = (
        db.query(ComplaintReportability)
        .filter(
            ComplaintReportability.tenant_id == tenant_id,
            ComplaintReportability.decided_at >= begin,
            ComplaintReportability.decided_at < end,
        )
        .all()
    )
    timeliness = [
        report_rules.on_time(
            row.reported_on if row.decision == report_rules.REPORTED else _day(row.decided_at), row.due_on
        )
        for row in decisions
    ]
    from backend.app.reportability.assessments import signed_counts
    from backend.app.reportability.service import settings_of

    windows = settings_of(db, tenant_id)["windows"]
    reporting = {
        "decisions": len(decisions),
        "reported": sum(1 for row in decisions if row.decision == report_rules.REPORTED),
        "not_reportable": sum(1 for row in decisions if row.decision == report_rules.NOT_REPORTABLE),
        "inside_window": sum(1 for value in timeliness if value is True),
        "after_window": sum(1 for value in timeliness if value is False),
        "windows": [window["name"] for window in windows],
        "basis": known(code for window in windows for code in window.get("basis") or []),
        # Per-market conclusions signed in the period (tr01); the counts above are single decisions made before.
        "markets": signed_counts(db, tenant_id, begin, end),
    }
    signals = Counter(
        status
        for (status,) in db.query(Signal.status).filter(
            Signal.tenant_id == tenant_id, Signal.created_at >= begin, Signal.created_at < end
        )
    )
    from backend.app.signals.insight import trend_board

    board = trend_board(db, tenant_id, grouping="problem", today=today)
    trends = {
        "signals_raised": sum(signals.values()),
        "signals_by_status": dict(sorted(signals.items())),
        "rising": [item["sentence"] for item in board["items"] if item["result"] in ("SIGNIFICANT", "ELEVATED")][
            :TOP_GROUPS
        ],
    }
    capas_opened = int(
        db.query(func.count(Capa.id))
        .filter(Capa.tenant_id == tenant_id, Capa.opened_at >= begin, Capa.opened_at < end)
        .scalar()
        or 0
    )
    signed = Counter(
        status
        for (status,) in db.query(CapaEffectivenessCheck.status).filter(
            CapaEffectivenessCheck.tenant_id == tenant_id,
            CapaEffectivenessCheck.signed_at >= begin,
            CapaEffectivenessCheck.signed_at < end,
        )
    )
    from backend.app.post_market import risk_file as risk_file_board

    risk_board = risk_file_board.board(
        db, tenant_id, period_days=max(period_days, risk_file_board.PERIOD_MIN), today=today
    )
    risk_file = {
        "summary": risk_board["summary"],
        "products": [
            {
                "name": item["product"]["name"],
                "label": item["label"],
                "complaints": item["post_market"]["complaints"],
                "harm": item["post_market"]["harm"],
                "risk_reviews": item["risk_file"]["risk_reviews"],
                "risks_assessed": item["risk_file"]["risks_assessed"],
                "risks": item["risk_file"]["risks"],
                "reassessments_open": item["risk_file"]["reassessments_open"],
            }
            for item in risk_board["items"][:TOP_GROUPS]
        ],
    }
    checks = service.readiness(db, tenant_id, today=today)
    capa_check = next((item for item in checks["checks"] if item["code"] == "CAPA_EFFECTIVENESS"), {})
    capa = {
        "opened": capas_opened,
        "checks_signed_effective": signed.get("EFFECTIVE", 0),
        "checks_signed_not_effective": signed.get("NOT_EFFECTIVE", 0),
        "now": capa_check.get("detail"),
    }
    data = {
        "period": {"from": start.isoformat(), "to": today.isoformat(), "days": period_days},
        "readiness": checks,
        "complaints": complaints,
        "second_look": {
            "confirmed": second_look.get("CONFIRMED", 0),
            "dismissed": second_look.get("DISMISSED", 0),
        },
        "reporting": reporting,
        "trends": trends,
        "risk_file": risk_file,
        "capa": capa,
        "limitations": [
            "Counts are of the records imported into MDARIX for the period; check them against the source systems.",
            _trend_basis_limitation(board.get("basis") or {}),
            "Reporting windows are the organization's own; MDARIX keeps the clock and decides nothing.",
        ],
    }
    data["standards"] = {"entries": entries(referenced(data)), "note": DISCLAIMER}
    return data


def _ids(chips) -> list[str]:
    return [chip["id"] for chip in chips or [] if isinstance(chip, dict) and chip.get("id")]


def referenced(data: dict) -> list[str]:
    """The catalog ids the summary cites: its sections' clauses, each check's basis and the reporting windows' basis."""
    cited = [*SECTION_BASIS]
    for check in (data.get("readiness") or {}).get("checks") or []:
        cited += _ids(check.get("basis"))
    cited += (data.get("reporting") or {}).get("basis") or []
    return known(cited)


def _trend_basis_limitation(basis: dict) -> str:
    """What the trend check counted by: units in the field where lots have quantities, else calendar days."""
    units, time = int(basis.get("units") or 0), int(basis.get("time") or 0)
    base = (
        "The trend check compares each product version with its own history, or a new version with the one it replaced"
    )
    if units and not time:
        return f"{base}, per unit in the field (lot quantities)."
    if units:
        return (
            f"{base}: {units} group(s) per unit in the field (lot quantities), {time} per calendar day where lots have "
            "no quantity, so a growing installed base can raise their rate by itself."
        )
    return (
        f"{base}, per calendar day: lot quantities are not recorded, so a growing installed base can raise a rate by "
        "itself. Add quantities to the lot import to count per unit in the field."
    )


def lines(data: dict) -> list[tuple[str, str]]:
    """The summary as the PDF's lines: (text, style) with style heading, body or muted."""
    out: list[tuple[str, str]] = []

    def heading(text: str) -> None:
        if out:
            out.append(("", "body"))
        out.append((text, "heading"))

    def body(text: str) -> None:
        out.append((text, "body"))

    def muted(text: str) -> None:
        out.append((text, "muted"))

    period = data["period"]
    readiness = data["readiness"]
    heading("1. Readiness today")
    summary = readiness["summary"]
    body(
        f"{summary['clear']} of {summary['checks']} checks clear; {summary['critical']} critical, "
        f"{summary['attention']} needing attention, {summary['not_set']} not set up."
    )
    for check in readiness["checks"]:
        value = "-" if check["value"] is None else check["value"]
        body(f"- {check['title']}: {value} ({STATE_WORDS.get(check['state'], check['state'])}). {check['detail']}")
        muted(f"    Why: {check['why']}")
        if check.get("basis"):
            muted("    Basis: " + "; ".join(chip["short"] for chip in check["basis"]))

    complaints = data["complaints"]
    heading("2. Feedback and complaint handling (management review inputs, ISO 13485:2016 clause 5.6.2)")
    body(
        f"{_n(complaints['received'], 'complaint')} received from {period['from']} to {period['to']}; "
        f"{complaints['closed']} closed. {complaints['death']} report a death, {complaints['serious_injury']} a "
        f"serious injury, {complaints['malfunction']} a malfunction."
    )
    body("By product version:")
    for group in complaints["by_product_version"]:
        body(f"- {group['group']}: {group['complaints']}")
    if complaints["more_groups"]:
        muted(f"  and {_n(complaints['more_groups'], 'more product version')}")
    second = data["second_look"]
    body(
        f"Second look: {_n(second['confirmed'], 'record')} confirmed as complaints and {second['dismissed']} dismissed in the "
        "period."
    )

    reporting = data["reporting"]
    heading("3. Reporting to regulatory authorities (management review input, clause 5.6.2)")
    per_market = reporting.get("markets") or {}
    body(
        f"{_n(per_market.get('signed', 0), 'market conclusion')} signed in the period: "
        f"{per_market.get('reportable', 0)} reportable ({per_market.get('filed', 0)} with the filing recorded), "
        f"{per_market.get('not_reportable', 0)} not reportable."
    )
    body(
        f"{_n(reporting['decisions'], 'single reportability decision')} (recorded before per-market assessment) in the "
        f"period: {reporting['reported']} reported, {reporting['not_reportable']} not reportable; "
        f"{reporting['inside_window']} inside the window, {reporting['after_window']} after it."
    )
    body(
        "Reporting windows: " + ("; ".join(reporting["windows"]) if reporting["windows"] else "none entered yet") + "."
    )
    window_basis = entries(reporting.get("basis") or [])
    if window_basis:
        muted("    Basis of the windows: " + "; ".join(entry["short"] for entry in window_basis))

    trends = data["trends"]
    heading("4. Trends (inputs to risk management and CAPA)")
    statuses = ", ".join(
        f"{status.replace('_', ' ').lower()} {count}" for status, count in trends["signals_by_status"].items()
    )
    body(f"{_n(trends['signals_raised'], 'signal')} raised in the period" + (f" ({statuses})." if statuses else "."))
    if trends["rising"]:
        body("Trend check, groups above their own history:")
        for sentence in trends["rising"]:
            body(f"- {sentence}")
    else:
        body("Trend check: no product version above its own history.")

    risk = data["risk_file"]
    heading("5. Post-market data and the risk file (ISO 14971:2019 clause 10)")
    counts = risk["summary"]
    body(
        f"{_n(counts['products'], 'product')}: {counts['not_reviewed']} with post-market data not reviewed against the "
        f"risk file, {counts['reassessment_overdue']} with risk reassessments overdue, {counts['reassessment_open']} "
        f"open, {counts['no_risk_register']} with no risks in MDARIX, {counts['reviewed']} reviewed."
    )
    for product in risk["products"]:
        body(
            f"- {product['name']}: {product['label'].lower()}; {_n(product['complaints'], 'complaint')} "
            f"({product['harm']} with harm), {_n(product['risk_reviews'], 'risk review')}, "
            f"{product['risks_assessed']} of {_n(product['risks'], 'risk')} assessed, "
            f"{_n(product['reassessments_open'], 'reassessment')} open."
        )

    capa = data["capa"]
    heading("6. Corrective and preventive action (management review inputs, clause 5.6.2)")
    body(
        f"{_n(capa['opened'], 'CAPA')} opened in the period; effectiveness checks signed: {capa['checks_signed_effective']} "
        f"effective, {capa['checks_signed_not_effective']} not effective."
    )
    if capa["now"]:
        body(f"Today: {capa['now']}.")

    heading("7. Limitations")
    for item in data["limitations"]:
        muted(f"- {item}")

    heading("8. Standards referenced")
    body(f"{'Standard':<{SHORT_WIDTH}}{'Title':<{TITLE_WIDTH}}Jurisdiction")
    for entry in entries(referenced(data)):
        title = textwrap.wrap(entry["title"], TITLE_WIDTH - 2) or [""]
        body(f"{entry['short']:<{SHORT_WIDTH}}{title[0]:<{TITLE_WIDTH}}{entry['jurisdiction']}")
        for more in title[1:]:
            body(" " * SHORT_WIDTH + more)
    muted(DISCLAIMER)
    return out


def render_pdf(data: dict, organization: str, generated_at: str) -> bytes:
    from reports import pdf

    period = data["period"]
    header = [
        f"Organization: {organization}",
        f"Period: {period['from']} to {period['to']} ({period['days']} days)",
        f"Generated: {generated_at}",
        "For management review: counts from your records; a person reviews and decides.",
    ]
    footer = f"{organization} - readiness summary - generated {generated_at}"
    return pdf.render("MDARIX readiness summary", header, lines(data), watermark=WATERMARK, footer=footer)
