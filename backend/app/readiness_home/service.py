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
- TRIAGE_OVERDUE: signals still awaiting triage past their due date;
- DISPOSITIONS_DUE: complaints without a disposition past the backlog target, service-level and known-issue
  dispositions that meet a trigger since they were signed ("disposition to review"), and the escalations of the last
  30 days (the trial's stand-in for the head-of-QA notice);
- RECURRING_SERVICE_LEVEL: two or more service-level resolutions on one product and problem code within 30 days
  that no open case covers.

Each check names its regulatory basis (``BASIS``, ids of the one catalog in backend/app/standards.py).

Nothing here changes a record. Every count is of the organization's records as imported into MDARIX.
"""

from __future__ import annotations

from backend.app import links
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
from backend.app.signals.logic import display_title
from backend.app.standards import DISCLAIMER, chips
from backend.app.business_ids import complaint_ref
from backend.app.reportability.markets import MARKET_LABELS

LOOKBACK_DAYS = 365
ITEMS_MAX = 8
CLEAR, ATTENTION, CRITICAL, NOT_SET = "CLEAR", "ATTENTION", "CRITICAL", "NOT_SET"
DECIDED_SIGNAL_STATUSES = ("DECISION_RECORDED", "CLOSED")

# Why each check matters, in plain words; worded from published 2025-2026 FDA warning letters and inspection
# summaries and from the EU, UK and Canadian vigilance rules (MDARIX gives no legal advice).
WHY = {
    "COMPLAINTS_TO_RECHECK": "Recent FDA inspection findings include complaints cancelled or logged as inquiries although "
    "they met the firm's own complaint definition, and No Fault Found codes that hid a recurring problem.",
    "COMPLAINTS_PAST_TARGET": "Complaint handling is among the observations FDA cites most often, complaint backlogs "
    "included.",
    "REPORTING_CLOCKS": "FDA has cited a report filed about nine months late; FDA, EU, UK and Canadian "
    "rules set reporting windows of 2 to 30 days from awareness.",
    "TRENDS_WITHOUT_ACTION": "Trends must reach CAPA and the risk file: FDA's QMSR inspections follow the risk file, "
    "and the EU MDR (Article 88) asks for statistically significant increases to be reported.",
    "HARM_CLOSED_WITHOUT_CASE": "FDA has cited complaints of potentially fatal harm closed without corrective action.",
    "CAPA_EFFECTIVENESS": "CAPA is among the observations FDA cites most often, and closing a CAPA without verifying "
    "that it worked is a recurring finding.",
    "TRIAGE_OVERDUE": "Signals left waiting are trends nobody has looked at.",
    "DISPOSITIONS_DUE": "ISO 13485 clause 8.2.2 lets a complaint close without an investigation only when the reason "
    "is documented; a complaint left without a decision is a backlog finding.",
    "RECURRING_SERVICE_LEVEL": "A recurring problem fixed in the field each time is a trend: closed service tickets must "
    "still reach the analysis of data.",
    "EXTERNAL_REQUESTS": "A question to a reporter, distributor, hospital or service partner needs an owner, a due "
    "date and a record of every attempt; an unanswered one is a gap in the complaint file.",
    "RISK_FILE_INPUT": "Under the QMSR, FDA inspections follow the risk file and name post-market data not used as "
    "input to risk management a significant deficiency; ISO 14971:2019 "
    "clause 10 asks for post-production information to reach risk management.",
}

# The regulatory basis of each check, from the one catalog (backend/app/standards.py), shown as chips under "why it
# matters" and listed in the management review summary and the inspection pack.
BASIS = {
    # Hidden complaints: records that meet the complaint definition must be handled as complaints, and their records
    # kept as complaint records.
    "COMPLAINTS_TO_RECHECK": ("ISO13485_8_2_2", "CFR820_35"),
    # The backlog: complaint handling asks for complaints to be handled in a timely manner.
    "COMPLAINTS_PAST_TARGET": ("ISO13485_8_2_2",),
    # Late or at-risk reports: reporting to regulatory authorities, the FDA 30-day and 5-day reports and EU vigilance.
    "REPORTING_CLOCKS": ("ISO13485_8_2_3", "CFR803_50", "CFR803_53", "MDR_87"),
    # Trends never acted on: analysis of data, and EU trend reporting of statistically significant increases.
    "TRENDS_WITHOUT_ACTION": ("ISO13485_8_4", "MDR_88"),
    # Harm complaints closed without an investigation: complaint handling asks for each complaint to be investigated,
    # or the reason it is not to be recorded.
    "HARM_CLOSED_WITHOUT_CASE": ("ISO13485_8_2_2",),
    # CAPAs closed without an effectiveness check: corrective action includes verifying that it was effective.
    "CAPA_EFFECTIVENESS": ("ISO13485_8_5_2",),
    # Signals waiting past their triage date: signals come from the analysis of complaint data, and one left waiting
    # is data nobody has analysed.
    "TRIAGE_OVERDUE": ("ISO13485_8_4",),
    # Complaints without a documented disposition, or one to review: complaint handling (clause 8.2.2).
    "DISPOSITIONS_DUE": ("ISO13485_8_2_2",),
    # Service-level matters that recur: analysis of data (clause 8.4).
    "RECURRING_SERVICE_LEVEL": ("ISO13485_8_4", "ISO13485_8_2_2"),
    # Requests to external contacts left open or unanswered (tr06, G30): complaint handling (clause 8.2.2).
    "EXTERNAL_REQUESTS": ("ISO13485_8_2_2",),
    # Post-market data not in the risk file: production and post-production information feeds risk management.
    "RISK_FILE_INPUT": ("ISO14971_10",),
}


def today_utc() -> date:
    return datetime.now(timezone.utc).date()


def organization_today(db: Session, tenant_id: uuid.UUID, now: datetime | None = None) -> date:
    """Today on the organization's working calendar (its time zone), as its own due times end (0.10.63): 2 Nov in
    India from 00:00 IST, where the UTC date still read 1 Nov until 05:30."""
    from backend.app.oversight.service import calendar_of

    return calendar_of(db, tenant_id).local_day(now or datetime.now(timezone.utc))


def _midnight(day: date) -> datetime:
    return datetime.combine(day, datetime.min.time(), tzinfo=timezone.utc)


def _n(count: int, noun: str) -> str:
    """ "1 complaint", "4,993 complaints": grouped the en-US way (DEV-025)."""
    return f"{count:,} {noun}{'' if count == 1 else 's'}"


def _check(code, title, value, state, detail, opens, items=None, extra=None) -> dict:
    return {
        "code": code,
        "title": title,
        "value": value,
        "state": state,
        "detail": detail,
        "why": WHY[code],
        "basis": chips(BASIS[code]),
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
    # "1 of 5 records to recheck reports a death or serious injury": the share, never a bare number before the verb.
    if not count:
        detail = "No cancelled record or inquiry shows complaint signs"
    elif harm:
        verb = "reports" if harm == 1 else "report"
        detail = f"{harm:,} of {_n(count, 'record')} to recheck {verb} a death or serious injury"
    else:
        detail = f"{_n(count, 'record')} to recheck, none reporting a death or serious injury"
    return _check(
        "COMPLAINTS_TO_RECHECK",
        "Complaints to recheck",
        count,
        CRITICAL if harm else ATTENTION if count else CLEAR,
        detail,
        links.target("Complaints", "Second look"),
        [{"id": item["id"], "ref": item["complaint_identifier"] or item["business_id"]} for item in found["items"]],
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
        f"{_n(summary['open_unlinked'], 'complaint')} open in no trend or investigation; {summary['due_soon']:,} due within a "
        f"week; target {summary['target_days']} days",
        links.target("Complaints", "Backlog"),
        [{"id": item["id"], "ref": item["complaint_identifier"] or item["business_id"]} for item in found["items"]],
        {"open_unlinked": summary["open_unlinked"], "oldest_days": summary["oldest_days"]},
    )


def _disagreement_items(db: Session, tenant_id: uuid.UUID, rows, listed: set[str]) -> list[dict]:
    ids = [row.complaint_id for row in rows if str(row.complaint_id) not in listed]
    refs = {
        complaint_id: business_id or identifier
        for complaint_id, business_id, identifier in (
            db.query(Complaint.id, Complaint.business_id, Complaint.complaint_identifier)
            .filter(Complaint.tenant_id == tenant_id, Complaint.id.in_(ids))
            .all()
            if ids
            else []
        )
    }
    found, seen = [], set()
    for row in rows:
        if row.complaint_id in refs and row.complaint_id not in seen:
            seen.add(row.complaint_id)
            found.append(
                {
                    "id": str(row.complaint_id),
                    "ref": f"{refs[row.complaint_id]} ({MARKET_LABELS.get(row.market, row.market)}: against the scale)",
                }
            )
    return found


def reporting_clocks(db: Session, tenant_id: uuid.UUID, today: date) -> dict:
    from backend.app.reportability.service import watch

    from backend.app.reportability.assessments import disagreements

    # Today is read as now, so a deadline that ended at 23:59 in its market's time zone is overdue here when it is on
    # the watch (one deadline everywhere, 0.10.63); another day (an older read, a test) stays a day.
    moment = datetime.now(timezone.utc)
    found = watch(
        db, None, tenant_id, show="open", page=1, page_size=10**6, today=moment if today == moment.date() else today
    )
    summary = found["summary"]
    # The number: complaints awaiting a decision whose clock is overdue or due soon, or whose answers are missing.
    flagged = [item for item in found["items"] if item["state"] in ("OVERDUE", "DUE_SOON") or item["follow_ups"]]
    # Signed market conclusions whose answers disagree with the harm-severity scale, each with its written reason
    # (T-G15H): listed so that a reviewer sees them.
    disagreeing = disagreements(db, tenant_id)
    against_scale = _disagreement_items(db, tenant_id, disagreeing, {item["id"] for item in flagged})
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
        if disagreeing:
            state = CRITICAL if state == CRITICAL else ATTENTION
            detail += f"; {_n(len(disagreeing), 'signed answer')} against the harm-severity scale, with a reason"
    return _check(
        "REPORTING_CLOCKS",
        "Reporting clocks",
        len(flagged) + len(against_scale),
        state,
        detail,
        links.target("Complaints", "Reportability" if summary["configured"] else "Reporting windows"),
        [{"id": item["id"], "ref": item["complaint_identifier"] or item["business_id"]} for item in flagged]
        + against_scale,
        {
            "overdue": summary["overdue"],
            "due_soon": summary["due_soon"],
            "open": summary["open"],
            "configured": summary["configured"],
            "scale_disagreements": len(disagreeing),
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
        db.query(Signal.id, Signal.business_id, Signal.title, Signal.origin)
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
    items = [{"id": str(row.id), "ref": row.business_id, "label": signal_title(row)} for row in decided] + [
        {"id": item["key"], "ref": None, "label": item["name"]} for item in rising
    ]
    return _check(
        "TRENDS_WITHOUT_ACTION",
        "Trends without CAPA or risk review",
        value,
        CRITICAL if decided else ATTENTION if rising else CLEAR,
        f"{_n(len(decided), 'decided trend')} with no CAPA and no risk review; "
        f"{_n(len(rising), 'significant rise')} with no trend to review",
        links.target("Signals", "Trend check" if rising and not decided else "Signal inbox"),
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
        f"Closed in the last {LOOKBACK_DAYS} days, reporting a death or serious injury, in no investigation",
        links.target("Complaints", "Reportability"),
        [{"id": str(row.id), "ref": complaint_ref(row), "label": row.name} for row in closed],
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
        f"{summary['closed_without_check']:,} closed without a check, {_n(summary['overdue'], 'check')} overdue, "
        f"{summary['not_planned']:,} with no check planned",
        links.target("Records", "Effectiveness checks"),
        [
            {"id": item["capa"]["id"], "ref": item["capa"]["business_id"] or item["capa"]["capa_identifier"]}
            for item in found["items"]
            if item["state"] in ("NOT_PLANNED", "OVERDUE")
        ],
        {"not_planned": summary["not_planned"], "effective": summary["effective"]},
    )


def signal_title(row) -> str | None:
    """A signal row's title as every list shows it (a rule title from before 0.10.44 with its count grouped)."""
    return display_title(row.title, row.origin)


def triage_overdue_rows(db: Session, tenant_id: uuid.UUID) -> list:
    """Signals new or in triage past their due date: every one, for the check and the inspection pack."""
    now = datetime.now(timezone.utc)
    return (
        db.query(Signal.id, Signal.business_id, Signal.title, Signal.origin, Signal.status, Signal.due_at)
        .filter(Signal.tenant_id == tenant_id, Signal.status.in_(AWAITING_TRIAGE), Signal.due_at < now)
        .order_by(Signal.due_at)
        .all()
    )


def triage_overdue(db: Session, tenant_id: uuid.UUID, today: date) -> dict:
    rows = triage_overdue_rows(db, tenant_id)
    return _check(
        "TRIAGE_OVERDUE",
        "Trends waiting past their triage date",
        len(rows),
        ATTENTION if rows else CLEAR,
        "New or in triage, past the due date their priority set",
        links.target("Signals", "Signal inbox"),
        [{"id": str(row.id), "ref": row.business_id, "label": signal_title(row)} for row in rows],
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
        links.target("Records", "Risk file input"),
        [
            {"id": item["product"]["id"], "ref": item["product"]["business_id"], "label": item["product"]["name"]}
            for item in flagged
        ],
        {"products": summary["products"]},
    )


def dispositions_due(db: Session, tenant_id: uuid.UUID, today: date) -> dict:
    """Complaints waiting for a disposition past the backlog target, dispositions to review (a trigger met after
    signing), and the escalations of the last 30 days, which every Leader sees here."""
    from backend.app.complaint_disposition import service as disposition
    from backend.app.complaint_disposition.triggers import codes
    from backend.app.complaint_disposition.triggers import words as trigger_words
    from backend.app.complaint_review.service import settings_of

    target = settings_of(db, tenant_id)["backlog_target_days"]
    review = disposition.to_review(db, tenant_id, today)
    late = disposition.waiting_past_target(db, tenant_id, today, target)
    escalated = disposition.escalations(db, tenant_id, _midnight(today - timedelta(days=30)))
    refs = {
        row.id: complaint_ref(row)
        for row in db.query(Complaint.id, Complaint.business_id, Complaint.complaint_identifier).filter(
            Complaint.tenant_id == tenant_id,
            Complaint.id.in_(
                [item[0] for item in late[:ITEMS_MAX]] + [row.complaint_id for row in escalated] or [None]
            ),
        )
    }
    items = [
        {
            "id": item["id"],
            "ref": item["ref"],
            "label": f"Disposition to review: {trigger_words(item['triggers'])} met after signing",
        }
        for item in review
    ]
    items += [
        {"id": str(complaint_id), "ref": refs.get(complaint_id), "label": f"No disposition, {age} days"}
        for complaint_id, age in late
    ]
    items += [
        {
            "id": str(row.complaint_id),
            "ref": refs.get(row.complaint_id),
            "label": "Escalated: " + (trigger_words(codes(row.triggers or [])) or "by choice"),
        }
        for row in escalated
    ]
    value = len(review) + len(late)
    return _check(
        "DISPOSITIONS_DUE",
        # What it counts (J19): complaints past the target without a disposition, and dispositions to review; the
        # Dispositions board's "waiting" is every complaint without one, a larger number.
        f"Dispositions past the {target}-day target or to review",
        value,
        CRITICAL if review else ATTENTION if late or escalated else CLEAR,
        f"{_n(len(late), 'complaint')} without a disposition past the {target}-day target; "
        f"{_n(len(review), 'disposition')} to review (a trigger met after signing); "
        f"{_n(len(escalated), 'escalation')} to an investigation in the last 30 days",
        links.target("Complaints", "Dispositions"),
        items,
        {"to_review": len(review), "past_target": len(late), "escalated": len(escalated)},
    )


def recurring_service_level(db: Session, tenant_id: uuid.UUID, today: date) -> dict:
    from backend.app.complaint_disposition import service as disposition
    from backend.app.complaint_disposition.triggers import RECURRING_COUNT, RECURRING_DAYS

    found = disposition.recurring(db, tenant_id, today)
    return _check(
        "RECURRING_SERVICE_LEVEL",
        "Recurring service-level matters",
        len(found),
        ATTENTION if found else CLEAR,
        f"{RECURRING_COUNT} or more service-level resolutions on one product and problem code within {RECURRING_DAYS} "
        "days that no open investigation covers (starter threshold); the next such complaint is escalated by the recurrence trigger",
        links.target("Signals", "By resolution"),
        [
            {
                "id": item["product_id"],
                "ref": f"{item['product_name']}, {item['problem_code'].replace('_', ' ').lower()}",
                "label": f"{item['count']} service-level resolutions in {RECURRING_DAYS} days ({', '.join(item['complaints'])})"
                ", no investigation covers it",
            }
            for item in found
        ],
    )


def external_requests(db: Session, tenant_id: uuid.UUID, today: date) -> dict:
    """Requests to external contacts that are open, overdue, or ended unresolved after attempts (tr06, G30)."""
    from backend.app.communications.service import summary

    found = summary(db, tenant_id, today)
    return _check(
        "EXTERNAL_REQUESTS",
        "Requests to external contacts",
        found["open"],
        ATTENTION if found["overdue"] else CLEAR,
        f"{_n(found['open'], 'open request')}, {found['overdue']:,} past the reply due date; "
        f"{_n(found['unresolved'], 'request')} unresolved after attempts",
        links.target("Complaints", "Communications"),
        [
            {
                "id": item["complaint_id"] or item["id"],
                "ref": item["ref"],
                "label": ("Overdue: " if item["overdue"] else "Open: ")
                + f"{item['party']}, reply due {item['reply_due_on'] or 'not set'}, {item['attempts']} attempts",
            }
            for item in found["items"]
        ],
        {"overdue": found["overdue"], "unresolved": found["unresolved"]},
    )


HOME = ("COMPLAINTS_TO_RECHECK", "COMPLAINTS_PAST_TARGET", "REPORTING_CLOCKS", "TRENDS_WITHOUT_ACTION")
# The records each check reads: with none of them, the check has nothing to read, so it is not set, never clear
# (an empty workspace is not "Ready", J24). Every other check reads complaints.
NOT_SET_YET = "Not set: no records yet"
CHECK_RECORDS = {"CAPA_EFFECTIVENESS": Capa, "RISK_FILE_INPUT": Product}


def _no_records_yet(db: Session, tenant_id: uuid.UUID, check: dict, counts: dict) -> dict:
    """The check as it reads when its records are missing: not set, no number."""
    model = CHECK_RECORDS.get(check["code"], Complaint)
    if model not in counts:
        counts[model] = db.query(func.count(model.id)).filter(model.tenant_id == tenant_id).scalar() or 0
    if counts[model] or check["state"] != CLEAR:
        return check
    return {**check, "state": NOT_SET, "value": None, "detail": NOT_SET_YET, "items": []}


CHECKS = (
    complaints_to_recheck,
    complaints_past_target,
    reporting_clocks,
    trends_without_action,
    risk_file_input,
    harm_closed_without_case,
    capa_effectiveness,
    triage_overdue,
    dispositions_due,
    recurring_service_level,
    external_requests,
)


def readiness(db: Session, tenant_id: uuid.UUID, today: date | None = None) -> dict:
    """Every check, the four home numbers first. A check that cannot be read (an older database) is shown as such and
    never fails the others."""
    from backend.app.case_workflow.readiness import safely
    from backend.app.signals.insight import shared_trend_boards

    today = today or organization_today(db, tenant_id)
    checks = []
    # The trend check and the risk file check read the same trend board: once (0.10.43).
    with shared_trend_boards():
        found_checks = [
            (step, safely(db, step.__name__, lambda session, step=step: step(session, tenant_id, today)))
            for step in CHECKS
        ]
    for step, found in found_checks:
        if found is None:
            code = step.__name__.upper()
            found = {
                "code": code,
                "title": step.__name__.replace("_", " ").capitalize(),
                "value": None,
                "state": NOT_SET,
                "detail": "This check could not be read; try again shortly",
                "why": WHY.get(code, ""),
                "basis": chips(BASIS.get(code, ())),
                "opens": None,
                "items": [],
            }
        checks.append(found)
    counts: dict = {}
    checks = [_no_records_yet(db, tenant_id, check, counts) for check in checks]
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
        "note": "Read from your records as imported into MDARIX; rules only, no AI.",
        "basis_note": DISCLAIMER,
    }
