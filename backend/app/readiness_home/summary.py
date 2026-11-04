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
from datetime import date, datetime, time, timedelta, timezone

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
from backend.app.complaint_disposition.triggers import LABELS as TRIGGER_LABELS

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


def _bounds(db: Session, tenant_id: uuid.UUID, start: date, today: date) -> tuple[datetime, datetime]:
    """The period from ``start`` to ``today`` (included) as UTC moments, between midnights in the organization's time
    zone: ``today`` is the organization's day, so a UTC midnight would drop its evening (or add the next morning)."""
    from backend.app.oversight.service import calendar_of

    zone = calendar_of(db, tenant_id).tz
    return tuple(
        datetime.combine(day, time.min, tzinfo=zone).astimezone(timezone.utc)
        for day in (start, today + timedelta(days=1))
    )


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
    today = today or service.organization_today(db, tenant_id)
    start = today - timedelta(days=period_days - 1)
    begin, end = _bounds(db, tenant_id, start, today)
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
        # The same groups with their product, for the management review report's links (T-G35.1).
        "rising_products": [
            item["product"] for item in board["items"] if item["result"] in ("SIGNIFICANT", "ELEVATED")
        ][:TOP_GROUPS],
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
                "id": item["product"]["id"],
                "business_id": item["product"]["business_id"],
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
    from backend.app.complaint_disposition.service import counts_by_branch

    dispositions = counts_by_branch(db, tenant_id, begin, end)
    data = {
        "period": {"from": start.isoformat(), "to": today.isoformat(), "days": period_days},
        "readiness": checks,
        "complaints": complaints,
        "second_look": {
            "confirmed": second_look.get("CONFIRMED", 0),
            "dismissed": second_look.get("DISMISSED", 0),
        },
        # Dispositions signed in the period (tr02), by branch, with the escalations by trigger.
        "dispositions": dispositions,
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
    signed = data.get("dispositions") or {}
    if signed:
        branches = signed["by_branch"]
        body(
            f"Dispositions: {_n(signed['signed'], 'disposition')} signed in the period: "
            f"{branches.get('SERVICE_LEVEL', 0)} resolved at service level ({signed['routine']} on the routine path), "
            f"{branches.get('KNOWN_ISSUE', 0)} known issues linked to an open case, "
            f"{branches.get('ESCALATED_BY_TRIGGER', 0)} escalated by a trigger and "
            f"{branches.get('ESCALATED_BY_CHOICE', 0)} by choice."
        )
        triggered = [
            f"{TRIGGER_LABELS.get(code, code)} {count}" for code, count in signed["by_trigger"].items() if count
        ]
        if triggered:
            body("Escalations by trigger: " + "; ".join(triggered) + ".")

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


# ------------------------------------------------------------------------------- the management review report

# T-MSG's framing of post-market surveillance (F7.8), the same words as the trial guide and the in-app user guide
# (frontend/src/features/help/besideYourQms.ts PMS_FRAMING). The proactive sources are recorded from 0.10.55 only.
PMS_FRAMING = (
    "Post-market surveillance gathers data reactively, from what reaches you (complaints, service records, incidents, "
    "field actions), and proactively, from what you go out to look for. The results feed one loop: PMS → risk "
    "management → clinical evaluation → PSUR → back to the PMS plan."
)


def management_review(
    db: Session, tenant_id: uuid.UUID, *, period_days: int, today: date, control_db: Session | None = None, **_
) -> dict:
    """The management review report (T-G35.1, ISO 13485:2016 5.6.2 and 8.2.1): the readiness summary's figures for the
    period (``build``, so they match Readiness), each row with the records it counts, and the PMS section with the
    reactive sources and the loop; the PMS conclusion and the actions decided are written by the manufacturer."""
    from backend.app.complaint_classification.rules import USE_ENVIRONMENT_LABELS, USER_TYPE_LABELS
    from backend.app.complaint_disposition import rules as disposition_rules
    from backend.app.complaint_disposition import triggers
    from backend.app.complaint_disposition.service import recurring
    from backend.app.db.models.complaint_disposition import ComplaintDisposition
    from backend.app.db.models.market_assessment import ComplaintClassification, ComplaintMarketAssessment
    from backend.app.qms_documents.content import (
        complaint_ref,
        data,
        finding_rows,
        judgement,
        plural,
        risk_reviews,
        row,
        src,
    )
    from backend.app.reportability import markets

    summary = build(db, tenant_id, period_days=period_days, today=today)
    start = today - timedelta(days=period_days - 1)
    begin, end = _bounds(db, tenant_id, start, today)
    received = func.coalesce(Complaint.complaint_timestamp, Complaint.event_timestamp, Complaint.created_at)
    found = (
        db.query(Complaint, Product.name, ProductVersion.version_identifier)
        .outerjoin(Product, (Product.tenant_id == Complaint.tenant_id) & (Product.id == Complaint.product_id))
        .outerjoin(
            ProductVersion,
            (ProductVersion.tenant_id == Complaint.tenant_id) & (ProductVersion.id == Complaint.product_version_id),
        )
        .filter(Complaint.tenant_id == tenant_id, received >= begin, received < end)
        .order_by(Complaint.complaint_identifier)
        .all()
    )
    refs = {complaint.id: complaint_ref(complaint) for complaint, _, _ in found}

    def of(ids) -> list[dict]:
        return [src("Complaint", item, refs.get(item) or str(item)) for item in ids]

    def grouped(key) -> list[tuple[str, list]]:
        groups: dict[str, list] = {}
        for complaint, name, version in found:
            groups.setdefault(key(complaint, name, version), []).append(complaint.id)
        return sorted(groups.items(), key=lambda pair: (-len(pair[1]), pair[0]))

    complaints = summary["complaints"]
    period = summary["period"]
    complaint_rows = [
        row(
            f"{plural(complaints['received'], 'complaint')} received from {period['from']} to {period['to']}; "
            f"{complaints['closed']} closed. {complaints['death']} report a death, {complaints['serious_injury']} a "
            f"serious injury, {complaints['malfunction']} a malfunction.",
            of(refs),
        )
    ]
    for title, key in (
        ("By product version", lambda c, n, v: f"{n or 'No product'} {v or '(version not recorded)'}"),
        ("By problem code", lambda c, n, v: (c.problem_code or "not coded").replace("_", " ").lower()),
    ):
        complaint_rows += [row(f"{title}: {name}: {len(ids)}.", of(ids)) for name, ids in grouped(key)[:TOP_GROUPS]]

    current = {
        item.complaint_id: item
        for item in db.query(ComplaintClassification)
        .filter(
            ComplaintClassification.tenant_id == tenant_id,
            ComplaintClassification.superseded_by.is_(None),
            ComplaintClassification.complaint_id.in_(list(refs) or [uuid.uuid4()]),
        )
        .order_by(ComplaintClassification.version)
    }
    for title, field, labels in (
        ("By use environment", "use_environment", USE_ENVIRONMENT_LABELS),
        ("By user type", "user_type", USER_TYPE_LABELS),
    ):
        groups: dict[str, list] = {}
        for complaint_id in refs:
            value = getattr(current.get(complaint_id), field, None) or "UNKNOWN"
            groups.setdefault(labels.get(value, value.replace("_", " ").capitalize()), []).append(complaint_id)
        complaint_rows += [
            row(f"{title}: {name}: {len(ids)}.", of(ids))
            for name, ids in sorted(groups.items(), key=lambda pair: (-len(pair[1]), pair[0]))
        ]

    by_look: dict[str, list] = {"CONFIRMED": [], "DISMISSED": []}
    for decision, complaint_id in db.query(ComplaintSecondLook.decision, ComplaintSecondLook.complaint_id).filter(
        ComplaintSecondLook.tenant_id == tenant_id,
        ComplaintSecondLook.decided_at >= begin,
        ComplaintSecondLook.decided_at < end,
    ):
        by_look.setdefault(decision, []).append(complaint_id)
    look_refs = {
        item.id: complaint_ref(item)
        for item in db.query(Complaint.id, Complaint.business_id, Complaint.complaint_identifier).filter(
            Complaint.tenant_id == tenant_id,
            Complaint.id.in_([key for ids in by_look.values() for key in ids] or [uuid.uuid4()]),
        )
    }
    second = summary["second_look"]
    look_rows = [
        row(
            f"{plural(second['confirmed'], 'record')} confirmed as complaints in the period.",
            [src("SecondLook", item, look_refs.get(item)) for item in by_look["CONFIRMED"]],
        ),
        row(
            f"{plural(second['dismissed'], 'record')} dismissed, each with its reason.",
            [src("SecondLook", item, look_refs.get(item)) for item in by_look["DISMISSED"]],
        ),
    ]

    signed = (
        db.query(ComplaintDisposition, Complaint.business_id, Complaint.complaint_identifier)
        .join(
            Complaint,
            (Complaint.tenant_id == ComplaintDisposition.tenant_id)
            & (Complaint.id == ComplaintDisposition.complaint_id),
        )
        .filter(
            ComplaintDisposition.tenant_id == tenant_id,
            ComplaintDisposition.superseded_by.is_(None),
            ComplaintDisposition.signed_at >= begin,
            ComplaintDisposition.signed_at < end,
        )
        .order_by(Complaint.complaint_identifier)
        .all()
    )

    def disposition_sources(chosen) -> list[dict]:
        return [
            src("Disposition", item.complaint_id, f"{business_id or identifier} v{item.version}")
            for item, business_id, identifier in chosen
        ]

    counted = summary["dispositions"]
    disposition_rows = [
        row(
            f"{plural(counted['signed'], 'disposition')} signed in the period, {counted['routine']} of them on the "
            "routine path.",
            disposition_sources(signed),
        )
    ]
    for branch in disposition_rules.BRANCHES:
        disposition_rows.append(
            row(
                f"{disposition_rules.BRANCH_LABELS[branch]}: {counted['by_branch'].get(branch, 0)}.",
                disposition_sources([item for item in signed if item[0].branch == branch]),
            )
        )
    for code, count in counted["by_trigger"].items():
        if count:
            disposition_rows.append(
                row(
                    f"Escalated by the trigger {triggers.LABELS.get(code, code).lower()}: {count}.",
                    disposition_sources([item for item in signed if code in triggers.codes(item[0].triggers or [])]),
                )
            )

    assessments = (
        db.query(ComplaintMarketAssessment, Complaint.business_id, Complaint.complaint_identifier)
        .join(
            Complaint,
            (Complaint.tenant_id == ComplaintMarketAssessment.tenant_id)
            & (Complaint.id == ComplaintMarketAssessment.complaint_id),
        )
        .filter(ComplaintMarketAssessment.tenant_id == tenant_id, ComplaintMarketAssessment.superseded_by.is_(None))
        .all()
    )

    def in_period(item) -> bool:
        return item.signed_at is not None and begin <= item.signed_at < end

    def cite(chosen) -> list[dict]:
        return [
            src("MarketAssessment", item.complaint_id, f"{business_id or identifier} {item.market} v{item.version}")
            for item, business_id, identifier in chosen
        ]

    vigilance_rows = []
    for market in markets.MARKETS:
        mine = [entry for entry in assessments if entry[0].market == market]
        concluded = [entry for entry in mine if entry[0].conclusion and in_period(entry[0])]
        reportable = [entry for entry in concluded if entry[0].conclusion == markets.REPORTABLE]
        routine = [entry for entry in concluded if entry[0].question_set == disposition_rules.ROUTINE_QUESTION_SET]
        assessed = [entry for entry in concluded if entry not in reportable and entry not in routine]
        filed = [entry for entry in reportable if entry[0].filed_on]
        pending = [entry for entry in mine if entry[0].conclusion is None]
        late = [
            entry
            for entry in reportable
            if entry[0].due_on
            and (
                (entry[0].filed_on and entry[0].filed_on > entry[0].due_on)
                or (not entry[0].filed_on and entry[0].due_on < today)
            )
        ]
        if not (concluded or pending):
            continue
        vigilance_rows.append(
            row(
                f"{markets.MARKET_LABELS[market]}: {plural(len(reportable), 'conclusion')} reportable "
                f"({len(filed)} with the report filed, {len(late)} late), {len(assessed)} not reportable on the "
                f"assessment, {len(routine)} not reportable on the routine basis; {len(pending)} pending now.",
                cite(concluded + pending),
            )
        )
        if late:
            vigilance_rows.append(row(f"{markets.MARKET_LABELS[market]}: late reports.", cite(late)))
    reporting = summary["reporting"]
    vigilance_rows.append(
        row(
            f"{plural(reporting['decisions'], 'single reportability decision')} recorded before per-market assessment: "
            f"{reporting['reported']} reported, {reporting['not_reportable']} not reportable; "
            f"{reporting['inside_window']} inside the window, {reporting['after_window']} after it."
        )
    )

    trends = summary["trends"]
    statuses = ", ".join(
        f"{status.replace('_', ' ').lower()} {count}" for status, count in trends["signals_by_status"].items()
    )
    signal_rows = [
        row(
            f"{plural(trends['signals_raised'], 'signal')} raised in the period"
            + (f" ({statuses})." if statuses else "."),
            [
                src("Signal", item_id, business_id)
                for item_id, business_id in db.query(Signal.id, Signal.business_id).filter(
                    Signal.tenant_id == tenant_id, Signal.created_at >= begin, Signal.created_at < end
                )
            ],
        )
    ]
    rising = [
        row(
            f"Trend check: {sentence}",
            [src("Product", product.get("id"), product.get("business_id") or product.get("name"))],
        )
        for sentence, product in zip(trends["rising"], trends.get("rising_products") or [])
    ]
    signal_rows += rising or [row("Trend check: no product version above its own history.")]
    for matter in recurring(db, tenant_id, today):
        ids = dict(
            db.query(Complaint.business_id, Complaint.id).filter(
                Complaint.tenant_id == tenant_id, Complaint.business_id.in_(matter["complaints"])
            )
        )
        signal_rows.append(
            row(
                f"Service-level trend: {matter['count']} service-level resolutions of "
                f"{matter['problem_code'].replace('_', ' ').lower()} on {matter['product_name']} within "
                f"{triggers.RECURRING_DAYS} days; no case covers it.",
                [src("Complaint", ids.get(ref), ref) for ref in matter["complaints"]],
            )
        )

    risk = summary["risk_file"]
    counts = risk["summary"]
    risk_rows = [
        row(
            f"{plural(counts['products'], 'product')}: {counts['not_reviewed']} with post-market data not reviewed "
            f"against the risk file, {counts['reassessment_overdue']} with risk reassessments overdue, "
            f"{counts['reassessment_open']} open, {counts['no_risk_register']} with no risks in MDARIX, "
            f"{counts['reviewed']} reviewed."
        )
    ] + [
        row(
            f"{product['name']}: {product['label'].lower()}; {plural(product['complaints'], 'complaint')} "
            f"({product['harm']} with harm), {plural(product['risk_reviews'], 'risk review')}, "
            f"{product['risks_assessed']} of {plural(product['risks'], 'risk')} assessed, "
            f"{plural(product['reassessments_open'], 'reassessment')} open.",
            [src("Product", product["id"], product["business_id"] or product["name"])],
        )
        for product in risk["products"]
    ]

    capa = summary["capa"]
    opened = db.query(Capa.id, Capa.business_id, Capa.capa_identifier).filter(
        Capa.tenant_id == tenant_id, Capa.opened_at >= begin, Capa.opened_at < end
    )
    checked = (
        db.query(Capa.id, Capa.business_id, Capa.capa_identifier)
        .join(
            CapaEffectivenessCheck,
            (CapaEffectivenessCheck.tenant_id == Capa.tenant_id) & (CapaEffectivenessCheck.capa_id == Capa.id),
        )
        .filter(
            Capa.tenant_id == tenant_id,
            CapaEffectivenessCheck.signed_at >= begin,
            CapaEffectivenessCheck.signed_at < end,
        )
    )
    capa_rows = [
        row(
            f"{plural(capa['opened'], 'CAPA')} opened in the period (as imported from your QMS).",
            [src("Capa", item.id, item.business_id or item.capa_identifier) for item in opened],
        ),
        row(
            f"Effectiveness checks signed: {capa['checks_signed_effective']} effective, "
            f"{capa['checks_signed_not_effective']} not effective.",
            [src("Capa", item.id, item.business_id or item.capa_identifier) for item in checked],
        ),
    ]
    if capa["now"]:
        capa_rows.append(row(f"At the cut-off: {capa['now']}."))

    service_level = [item for item in signed if item[0].branch == disposition_rules.SERVICE_LEVEL]
    reportable_events = [
        item for item in assessments if item[0].conclusion == markets.REPORTABLE and in_period(item[0])
    ]
    answers, updates = finding_rows(db, tenant_id, risk_reviews(db, tenant_id, begin=begin, end=end), control_db)
    pms_rows = [
        row(PMS_FRAMING),
        row(f"Reactive source, complaints: {plural(complaints['received'], 'complaint')} received.", of(refs)),
        row(
            f"Reactive source, service records: {plural(len(service_level), 'service-level resolution')}.",
            disposition_sources(service_level),
        ),
        row(
            f"Reactive source, reportable events: {plural(len(reportable_events), 'reportable market conclusion')}.",
            cite(reportable_events),
        ),
        row(
            f"Into risk management: {plural(len(answers), 'risk-control answer')} and "
            f"{plural(len(updates), 'risk file update')} required, from the risk reviews completed in the period."
        ),
        *answers,
        *updates,
        row(
            "Into the clinical evaluation and the PSUR, and back to the PMS plan: the complaints, reportable events and "
            "risk-control answers above are this period's post-market input; the clinical evaluation, the PSUR and the "
            "PMS plan are kept in your QMS."
        ),
    ]
    return {
        "sections": [
            data("COMPLAINTS", "Feedback and complaint handling", complaint_rows),
            data("SECOND_LOOK", "The second look", look_rows),
            data("DISPOSITIONS", "Complaint dispositions", disposition_rows),
            data("VIGILANCE", "Reporting to regulatory authorities, by market", vigilance_rows),
            data("TRENDS", "Signals and trends", signal_rows),
            data("RISK_FILE", "Post-market data and the risk file", risk_rows),
            data("CAPA", "Corrective and preventive action", capa_rows),
            data("PMS", "Post-market surveillance", pms_rows),
            judgement("MANAGEMENT_REVIEW", "PMS_CONCLUSION"),
            judgement("MANAGEMENT_REVIEW", "ACTIONS_DECIDED"),
            data("LIMITATIONS", "Limitations", [row(item) for item in summary["limitations"]]),
        ],
        "figures": {"complaints": complaints["received"], "dispositions": counted, "markets": reporting["markets"]},
    }
