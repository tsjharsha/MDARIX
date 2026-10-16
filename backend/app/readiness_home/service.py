"""Readiness: what an FDA investigator or a notified-body auditor would find in the organization's complaints today,
read from its own records (rules only, no AI), each check with the list it opens.

The four numbers of the home screen (the lightweight MVP plan):
- COMPLAINTS_TO_RECHECK: records the second look flags and nobody has decided (hidden complaints);
- COMPLAINTS_PAST_TARGET: open complaints in no signal and no case, past the organization's target (backlog);
- REPORTING_CLOCKS: reporting clocks overdue or due soon against the organization's windows (late reports);
- TRENDS_WITHOUT_ACTION: decided signals whose cases have no CAPA and no completed risk review, and significant trend
  check results with no open signal (trends never acted on, post-market data not reaching the risk file).

Further inspection checks drawn from 2025-2026 findings:
- HARM_CLOSED_WITHOUT_CASE: complaints reporting a death or serious injury, closed, in no investigation;
- CAPA_EFFECTIVENESS: CAPAs closed without an effectiveness check, and checks overdue;
- TRIAGE_OVERDUE: signals still awaiting triage past their due date.

Nothing here changes a record. Every count is of the organization's records as imported into MDARIX.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import exists, func, or_
from sqlalchemy.orm import Session

from backend.app.complaint_review import rules as review_rules
from backend.app.db.models.complaint_review import ComplaintSecondLook
from backend.app.db.models.foundation import Capa, Complaint, InvestigationComplaint, Product
from backend.app.db.models.reviews import CaseReview
from backend.app.db.models.signals import InvestigationSignal, Signal
from backend.app.signals.labels import AWAITING_TRIAGE

LOOKBACK_DAYS = 365
ITEMS_MAX = 8
CLEAR, ATTENTION, CRITICAL, NOT_SET = "CLEAR", "ATTENTION", "CRITICAL", "NOT_SET"
DECIDED_SIGNAL_STATUSES = ("DECISION_RECORDED", "CLOSED")

# Why each check matters, in plain words; worded from published 2025-2026 FDA warning letters and inspection
# summaries and from the EU, UK and Canadian vigilance rules (MDARIX gives no legal advice).
WHY = {
    "COMPLAINTS_TO_RECHECK": "2026 FDA warning letters cite complaints cancelled or logged as inquiries although they "
    "met the firm's own complaint definition, and No Fault Found codes that hid a recurring problem.",
    "COMPLAINTS_PAST_TARGET": "Complaint handling is among the observations FDA cites most often; complaint backlogs "
    "were cited in 2026 warning letters.",
    "REPORTING_CLOCKS": "A 2026 warning letter cites a report filed about nine months late; FDA, EU, UK and Canadian "
    "rules set reporting windows of 2 to 30 days from awareness.",
    "TRENDS_WITHOUT_ACTION": "Trends must reach CAPA and the risk file: FDA's QMSR inspections follow the risk file, "
    "and the EU MDR (Article 88) asks for statistically significant increases to be reported.",
    "HARM_CLOSED_WITHOUT_CASE": "A 2026 warning letter cites complaints of potentially fatal harm closed without "
    "corrective action.",
    "CAPA_EFFECTIVENESS": "CAPA is among the observations FDA cites most often, and closing a CAPA without verifying "
    "that it worked is a recurring finding.",
    "TRIAGE_OVERDUE": "Signals left waiting are trends nobody has looked at.",
    "RISK_FILE_INPUT": "Under the QMSR, FDA inspections follow the risk file and name post-market data not used as "
    "input to risk management a significant deficiency (the first QMSR warning letter cited it); ISO 14971:2019 "
    "clause 10 asks for post-production information to reach risk management.",
}


def today_utc() -> date:
    return datetime.now(timezone.utc).date()


def _midnight(day: date) -> datetime:
    return datetime.combine(day, datetime.min.time(), tzinfo=timezone.utc)


def _n(count: int, noun: str) -> str:
    """ "1 complaint", "3 complaints"."""
    return f"{count} {noun}{'' if count == 1 else 's'}"


def _check(code, title, value, state, detail, opens, items=None, extra=None) -> dict:
    return {
        "code": code,
        "title": title,
        "value": value,
        "state": state,
        "detail": detail,
        "why": WHY[code],
        "opens": opens,
        "items": (items or [])[:ITEMS_MAX],
        **(extra or {}),
    }


# ------------------------------------------------------------------------------------------------- the four numbers


def complaints_to_recheck(db: Session, tenant_id: uuid.UUID, today: date) -> dict:
    from backend.app.complaint_review.service import second_look

    found = second_look(db, None, tenant_id, state="open", page=1, page_size=ITEMS_MAX, today=today)
    summary = found["summary"]
    count, harm = summary["to_review"], summary["with_harm"]
    return _check(
        "COMPLAINTS_TO_RECHECK",
        "Complaints to recheck",
        count,
        CRITICAL if harm else ATTENTION if count else CLEAR,
        f"{harm} report a death or serious injury" if count else "No cancelled record or inquiry shows complaint signs",
        {"section": "Complaints", "tab": "Second look"},
        [{"id": item["id"], "ref": item["business_id"] or item["complaint_identifier"]} for item in found["items"]],
        {"harm": harm},
    )


def complaints_past_target(db: Session, tenant_id: uuid.UUID, today: date) -> dict:
    from backend.app.complaint_review.service import backlog

    found = backlog(db, tenant_id, show="past_target", page=1, page_size=ITEMS_MAX, today=today)
    summary = found["summary"]
    past = summary["past_target"]
    return _check(
        "COMPLAINTS_PAST_TARGET",
        "Complaints past target",
        past,
        # The number is what is past the target; complaints still inside it are no finding (named in the detail).
        CRITICAL if past else CLEAR,
        f"{_n(summary['open_unlinked'], 'complaint')} open in no signal or case; {summary['due_soon']} due within a "
        f"week; target {summary['target_days']} days",
        {"section": "Complaints", "tab": "Backlog"},
        [{"id": item["id"], "ref": item["business_id"] or item["complaint_identifier"]} for item in found["items"]],
        {"open_unlinked": summary["open_unlinked"], "oldest_days": summary["oldest_days"]},
    )


def reporting_clocks(db: Session, tenant_id: uuid.UUID, today: date) -> dict:
    from backend.app.reportability.service import watch

    found = watch(db, None, tenant_id, show="open", page=1, page_size=10**6, today=today)
    summary = found["summary"]
    # The number: complaints awaiting a decision whose clock is overdue or due soon, or whose answers are missing.
    flagged = [item for item in found["items"] if item["state"] in ("OVERDUE", "DUE_SOON") or item["follow_ups"]]
    if not summary["configured"]:
        # Without the organization's windows there are no due dates: that itself is the finding.
        state = NOT_SET
        detail = (
            f"{_n(summary['open'], 'complaint')} awaiting a reportability decision; enter your reporting windows to "
            "see their due dates"
        )
    else:
        state = CRITICAL if summary["overdue"] else ATTENTION if flagged else CLEAR
        detail = (
            f"{summary['overdue']} overdue, {summary['due_soon']} due soon, {summary['follow_up']} with missing "
            f"answers; {summary['decided_late']} decided after the window"
        )
    return _check(
        "REPORTING_CLOCKS",
        "Reporting clocks",
        len(flagged),
        state,
        detail,
        {"section": "Complaints", "tab": "Reportability" if summary["configured"] else "Reporting windows"},
        [{"id": item["id"], "ref": item["business_id"] or item["complaint_identifier"]} for item in flagged],
        {
            "overdue": summary["overdue"],
            "due_soon": summary["due_soon"],
            "open": summary["open"],
            "configured": summary["configured"],
        },
    )


def trends_without_action_rows(db: Session, tenant_id: uuid.UUID, today: date) -> tuple[list, list]:
    """(decided signals whose cases have neither a CAPA nor a completed risk review, significant trend check groups
    with no open signal): every one, for the check and the inspection pack."""
    from backend.app.signals.insight import trend_board

    has_capa = exists().where(
        Capa.tenant_id == InvestigationSignal.tenant_id, Capa.investigation_id == InvestigationSignal.investigation_id
    )
    has_risk_review = exists().where(
        CaseReview.tenant_id == InvestigationSignal.tenant_id,
        CaseReview.investigation_id == InvestigationSignal.investigation_id,
        CaseReview.review_type == "RISK",
        CaseReview.status == "COMPLETED",
    )
    acted_on = (
        exists()
        .where(InvestigationSignal.tenant_id == Signal.tenant_id, InvestigationSignal.signal_id == Signal.id)
        .where(or_(has_capa, has_risk_review))
    )
    decided = (
        db.query(Signal.id, Signal.business_id, Signal.title)
        .filter(Signal.tenant_id == tenant_id, Signal.status.in_(DECIDED_SIGNAL_STATUSES), ~acted_on)
        .order_by(Signal.updated_at.desc())
        .all()
    )
    board = trend_board(db, tenant_id, grouping="problem", today=today)
    rising = [item for item in board["items"] if item["result"] == "SIGNIFICANT" and not item["open_signals"]]
    return decided, rising


def trends_without_action(db: Session, tenant_id: uuid.UUID, today: date) -> dict:
    """Decided signals whose cases have neither a CAPA nor a completed risk review, and significant trend check
    results with no open signal."""
    decided, rising = trends_without_action_rows(db, tenant_id, today)
    value = len(decided) + len(rising)
    items = [{"id": str(row.id), "ref": row.business_id, "label": row.title} for row in decided] + [
        {"id": item["key"], "ref": None, "label": item["name"]} for item in rising
    ]
    return _check(
        "TRENDS_WITHOUT_ACTION",
        "Trends without CAPA or risk review",
        value,
        CRITICAL if decided else ATTENTION if rising else CLEAR,
        f"{_n(len(decided), 'decided signal')} with no CAPA and no risk review; "
        f"{_n(len(rising), 'significant rise')} with no signal",
        {"section": "Signals", "tab": "Trend check" if rising and not decided else "Signal inbox"},
        items,
        {"decided_without_action": len(decided), "rising_without_signal": len(rising)},
    )


# ------------------------------------------------------------------------------------------------- further checks


def harm_closed_rows(db: Session, tenant_id: uuid.UUID, today: date) -> list:
    """Complaints of the last LOOKBACK_DAYS reporting a death or serious injury, closed, in no case and not dismissed
    on the second look: every one, for the check and the inspection pack."""
    since = _midnight(today - timedelta(days=LOOKBACK_DAYS))
    received = func.coalesce(Complaint.complaint_timestamp, Complaint.event_timestamp, Complaint.created_at)
    in_case = exists().where(
        InvestigationComplaint.tenant_id == Complaint.tenant_id, InvestigationComplaint.complaint_id == Complaint.id
    )
    dismissed = exists().where(
        ComplaintSecondLook.tenant_id == Complaint.tenant_id,
        ComplaintSecondLook.complaint_id == Complaint.id,
        ComplaintSecondLook.decision == "DISMISSED",
    )
    rows = (
        db.query(Complaint.id, Complaint.business_id, Complaint.complaint_identifier, Complaint.status, Product.name)
        .outerjoin(Product, (Product.tenant_id == Complaint.tenant_id) & (Product.id == Complaint.product_id))
        .filter(
            Complaint.tenant_id == tenant_id,
            or_(Complaint.death.is_(True), Complaint.serious_injury.is_(True)),
            received >= since,
            ~in_case,
            ~dismissed,
        )
        .order_by(received.desc())
        .all()
    )
    return [row for row in rows if review_rules.is_closed(row.status)]


def harm_closed_without_case(db: Session, tenant_id: uuid.UUID, today: date) -> dict:
    closed = harm_closed_rows(db, tenant_id, today)
    return _check(
        "HARM_CLOSED_WITHOUT_CASE",
        "Harm complaints closed without an investigation",
        len(closed),
        CRITICAL if closed else CLEAR,
        f"Closed in the last {LOOKBACK_DAYS} days, reporting a death or serious injury, in no case",
        {"section": "Complaints", "tab": "Reportability"},
        [{"id": str(row.id), "ref": row.business_id or row.complaint_identifier, "label": row.name} for row in closed],
    )


def capa_effectiveness(db: Session, tenant_id: uuid.UUID, today: date) -> dict:
    from backend.app.capa_effectiveness.service import board

    found = board(db, None, tenant_id, show="attention", page=1, page_size=ITEMS_MAX, today=today)
    summary = found["summary"]
    # The number: CAPAs with no check planned (closed ones among them) and checks past their day. A check still ahead
    # of its day is no finding.
    value = summary["not_planned"] + summary["overdue"]
    return _check(
        "CAPA_EFFECTIVENESS",
        "CAPAs without a verified effect",
        value,
        CRITICAL if (summary["closed_without_check"] or summary["overdue"]) else ATTENTION if value else CLEAR,
        f"{summary['closed_without_check']} closed without a check, {_n(summary['overdue'], 'check')} overdue, "
        f"{summary['not_planned']} with no check planned",
        {"section": "Records", "tab": "Effectiveness checks"},
        [
            {"id": item["capa"]["id"], "ref": item["capa"]["business_id"] or item["capa"]["capa_identifier"]}
            for item in found["items"]
            if item["state"] in ("NOT_PLANNED", "OVERDUE")
        ],
        {"not_planned": summary["not_planned"], "effective": summary["effective"]},
    )


def triage_overdue_rows(db: Session, tenant_id: uuid.UUID) -> list:
    """Signals new or in triage past their due date: every one, for the check and the inspection pack."""
    now = datetime.now(timezone.utc)
    return (
        db.query(Signal.id, Signal.business_id, Signal.title, Signal.status, Signal.due_at)
        .filter(Signal.tenant_id == tenant_id, Signal.status.in_(AWAITING_TRIAGE), Signal.due_at < now)
        .order_by(Signal.due_at)
        .all()
    )


def triage_overdue(db: Session, tenant_id: uuid.UUID, today: date) -> dict:
    rows = triage_overdue_rows(db, tenant_id)
    return _check(
        "TRIAGE_OVERDUE",
        "Signals waiting past their triage date",
        len(rows),
        ATTENTION if rows else CLEAR,
        "New or in triage, past the due date their priority set",
        {"section": "Signals", "tab": "Signal inbox"},
        [{"id": str(row.id), "ref": row.business_id, "label": row.title} for row in rows],
    )


def risk_file_input(db: Session, tenant_id: uuid.UUID, today: date) -> dict:
    """Products whose post-market data has not reached the risk file, or whose risk reassessments are still open."""
    from backend.app.post_market import risk_file

    found = risk_file.board(db, tenant_id, today=today)
    summary = found["summary"]
    urgent = summary["not_reviewed"] + summary["reassessment_overdue"]
    pending = summary["reassessment_open"] + summary["no_risk_register"]
    flagged = [
        item
        for item in found["items"]
        if item["state"] in (risk_file.NOT_REVIEWED, risk_file.OVERDUE, risk_file.OPEN, risk_file.NO_REGISTER)
    ]
    return _check(
        "RISK_FILE_INPUT",
        "Post-market data not in the risk file",
        len(flagged),
        CRITICAL if urgent else ATTENTION if pending else CLEAR,
        f"{_n(summary['not_reviewed'], 'product')} with harm, malfunctions or rising trends and no risk review in the "
        f"last year; {summary['reassessment_overdue']} with risk reassessments overdue, "
        f"{summary['reassessment_open']} open; {summary['no_risk_register']} with no risks in MDARIX",
        {"section": "Records", "tab": "Risk file input"},
        [
            {"id": item["product"]["id"], "ref": item["product"]["business_id"], "label": item["product"]["name"]}
            for item in flagged
        ],
        {"products": summary["products"]},
    )


HOME = ("COMPLAINTS_TO_RECHECK", "COMPLAINTS_PAST_TARGET", "REPORTING_CLOCKS", "TRENDS_WITHOUT_ACTION")
CHECKS = (
    complaints_to_recheck,
    complaints_past_target,
    reporting_clocks,
    trends_without_action,
    risk_file_input,
    harm_closed_without_case,
    capa_effectiveness,
    triage_overdue,
)


def readiness(db: Session, tenant_id: uuid.UUID, today: date | None = None) -> dict:
    """Every check, the four home numbers first. A check that cannot be read (an older database) is shown as such and
    never fails the others."""
    from backend.app.case_workflow.readiness import safely

    today = today or today_utc()
    checks = []
    for step in CHECKS:
        found = safely(db, step.__name__, lambda session, step=step: step(session, tenant_id, today))
        if found is None:
            code = step.__name__.upper()
            found = {
                "code": code,
                "title": step.__name__.replace("_", " ").capitalize(),
                "value": None,
                "state": NOT_SET,
                "detail": "This check could not be read; try again shortly",
                "why": WHY.get(code, ""),
                "opens": None,
                "items": [],
            }
        checks.append(found)
    states = [check["state"] for check in checks]
    return {
        "as_of": today.isoformat(),
        "home": [check for check in checks if check["code"] in HOME],
        "checks": checks,
        "summary": {
            "checks": len(checks),
            "clear": states.count(CLEAR),
            "attention": states.count(ATTENTION),
            "critical": states.count(CRITICAL),
            "not_set": states.count(NOT_SET),
        },
        "note": "Read from your records as imported into MDARIX; rules only, no AI. A person decides what each finding "
        "means.",
    }
