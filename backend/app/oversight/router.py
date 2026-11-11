"""Reminders and escalation, the oversight view and the event's closure (T-G25, T-G9, T-G28; MVP G25, G9, G28).

- ``GET /api/v1/oversight``: one place for the head of QA/RA: every dated item overdue or due soon (or all), with its
  owner, due time, hours left and who it escalated to, by category; filters by product, market and category; the
  events (ready to close, not ready, decision record not filed, closed in the QMS before readiness); who is away;
  the staffing warning. IDs, owners, dates and states only, never patient or reporter data;
- ``GET /api/v1/oversight/export.csv``: the same list for the monthly product review (data.export);
- ``GET /api/v1/oversight/deadlines.csv`` and ``.pdf``: the open reporting deadlines, an offline copy for an outage
  (B6a G18a, data.export, audited; oversight/deadline_list.py, which also e-mails it daily);
- ``GET``/``PUT /api/v1/oversight/settings``: the working calendar (time zone, working weekdays, holidays) and the
  simple escalation rule (reminder hours, escalation role); changing them needs quality review or regulatory
  approval;
- ``GET /api/v1/oversight/alerts`` and ``POST .../alerts/read``: the signed-in person's own reminders and
  escalations, with read state (brought up to date first);
- ``GET``/``POST /api/v1/oversight/absences`` and ``POST .../absences/{id}/cancel``: a person records their own
  absence with the colleague who covers it;
- ``GET /api/v1/oversight/events/{complaint_id}``: the event: owner, stage line, checklist, decision record;
  ``PUT .../owner``; ``POST .../ready`` (the event owner signs "ready to close in the QMS" with their password, with a
  reason when items are open); ``PUT .../filing`` (the QMS filing reference); ``GET .../decision-record.pdf``.

An alert never closes or changes an item; MDARIX never closes a complaint, never decides and never sends anything
to an external contact. These routes serve a free trial and a pilot alike (T-B1).
"""

from __future__ import annotations

import io
import logging
import uuid
from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.app.trial.sample_source import is_sample
from backend.app.downloads import attachment
from backend.app.access.permissions import (
    DATA_EXPORT,
    DECISION_SIGN,
    EVIDENCE_REQUEST,
    INVESTIGATION_CREATE,
    INVESTIGATION_WORK,
    QUALITY_REVIEW,
    REGULATORY_APPROVE,
    REGULATORY_REVIEW,
    SIGNAL_TRIAGE,
    require_permission,
)
from backend.app.complaint_review.service import people as names_of
from backend.app import signing_commit
from backend.app.db.data_plane import get_data_plane_db
from backend.app.db.models.foundation import Complaint, SignedApprovalRecord
from backend.app.db.models.oversight import DueAlert, EventClosure, OversightSettings, UserAbsence
from backend.app.db.session import get_db
from backend.app.enterprise_audit import make_audit_event
from backend.app.evidence_workflow.people import require_any_permission
from backend.app import links
from backend.app.oversight import closure, record_page, rules, service, service_work
from backend.app.reportability.deadlines import due_label
from backend.app.request_context import AuthenticatedRequestContext, get_request_context

logger = logging.getLogger("mdarix.oversight")
router = APIRouter(prefix="/api/v1/oversight", tags=["Oversight, reminders and escalation"])

WRITERS = Depends(
    require_any_permission(
        SIGNAL_TRIAGE, INVESTIGATION_WORK, EVIDENCE_REQUEST, QUALITY_REVIEW, REGULATORY_REVIEW, REGULATORY_APPROVE
    )
)
SETTERS = Depends(require_any_permission(QUALITY_REVIEW, REGULATORY_APPROVE))
SAMPLE_NAMES = {"system:trial-sample": "MDARIX sample data"}
EVENTS_MAX = 200
ESCALATION_ROLES = ("LEADER", "REVIEWER", "APPROVER", "REGULATORY_REVIEWER")
CSV_FIELDS = (
    "category",
    "title",
    "ref",
    "product",
    "market",
    "owner",
    "queue",
    "due_at",
    "due_label",
    "state",
    "hours_left",
    "escalated_to",
)
NEVER = (
    "An alert tells people in MDARIX; it never closes or changes the item. MDARIX sends no e-mail about it and never "
    "decides: a person does, and signs."
)


def _error(status: int, code: str, message: str, **extra) -> HTTPException:
    return HTTPException(status, detail={"code": code, "message": message, **extra})


def _tenant(ctx) -> uuid.UUID:
    return uuid.UUID(str(ctx.tenant_id))


def _iso(value) -> str | None:
    return value.isoformat() if value is not None else None


def _audit(db, ctx, action: str, entity_type: str, entity_id, **details) -> None:
    db.add(
        make_audit_event(
            tenant_id=_tenant(ctx),
            actor_ref=ctx.user_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            correlation_id=ctx.correlation_id,
            details=details,
        )
    )


def _names(control_db, tenant_id, refs) -> dict[str, str]:
    return {**SAMPLE_NAMES, **names_of(control_db, tenant_id, [ref for ref in refs if ref])}


def _trial(control_db, tenant_id) -> bool:
    from backend.app.signer_training.router import is_trial

    try:
        return is_trial(control_db, tenant_id)
    except Exception:
        return False


def _absence_view(item: dict, names: dict) -> dict:
    return {
        "id": item["id"],
        "user_id": item["user_id"],
        "user_name": names.get(item["user_id"]) or "A colleague",
        "backup_id": item["backup_id"],
        "backup_name": names.get(item["backup_id"]) or "A colleague",
        "starts_on": item["starts_on"].isoformat(),
        "ends_on": item["ends_on"].isoformat(),
        "note": item["note"],
        "sample": item["sample"],
    }


# --------------------------------------------------------------------------------------------- the oversight view


def _escalations(db, tenant_id) -> dict[str, list[str]]:
    found: dict[str, list[str]] = {}
    for alert in db.query(DueAlert).filter(
        DueAlert.tenant_id == tenant_id, DueAlert.tier == rules.ESCALATION, DueAlert.resolved_at.is_(None)
    ):
        found.setdefault(alert.item_key, []).append(alert.recipient_id)
    return found


def _item_views(
    db,
    control_db,
    tenant_id,
    now: datetime,
    complaint_ids: set[str] | None = None,
    watched: list[dict] | None = None,
    incomplete: list[str] | None = None,
) -> tuple[list[dict], dict]:
    """``incomplete`` (B6a run 3): the sources that could not be read, or were cut, so the screen says so."""
    view = service.settings_view(service.settings_row(db, tenant_id))
    calendar = service.calendar_from(view)
    today = calendar.local_day(now)
    away = service.absences(db, tenant_id, today)
    incomplete = [] if incomplete is None else incomplete
    items = service.due_items(db, control_db, tenant_id, now, incomplete, complaint_ids=complaint_ids, watched=watched)
    escalated = _escalations(db, tenant_id)
    refs = {ref for item in items for ref in (item["owner_id"], item["backup_id"])}
    refs |= {ref for found in escalated.values() for ref in found} | {a["backup_id"] for a in away}
    names = _names(control_db, tenant_id, refs)
    views = []
    for item in items:
        state = rules.state_of(item["due_at"], now, view["reminder_hours"])
        covering = rules.away_backup(away, item["owner_id"], today)
        views.append(
            {
                **{key: item[key] for key in ("key", "category", "title", "ref", "complaint_id", "market", "product")},
                "category_label": rules.CATEGORIES[item["category"]],
                "owner_id": item["owner_id"],
                "owner": names.get(item["owner_id"] or "") if item["owner_id"] else None,
                "queue": item["queue"],
                "away": {"backup": names.get(covering) or "A colleague"} if covering else None,
                "due_at": item["due_at"].isoformat(),
                # The due time in words with its time zone, as every other screen shows it (J16, J19: RV-08's report
                # read 28 Nov on Reports and 29 Nov here, midnight UTC seen from India).
                "due_label": due_label(item["due_at"], item["market"], calendar.zone),
                "state": state,
                "state_label": rules.STATE_LABELS[state],
                "hours_left": rules.hours_left(item["due_at"], now),
                "escalated_to": [names.get(ref) or "A colleague" for ref in escalated.get(item["key"], [])],
                "alerts": item["alerts"],
                "opens": item["opens"],
            }
        )
    return views, {"settings": view, "away": away, "names": names, "calendar": calendar, "incomplete": incomplete}


def _filtered(items, product, market, category, show) -> list[dict]:
    return [
        item
        for item in items
        if (not product or item["product"] == product)
        and (not market or item["market"] == market)
        and (not category or item["category"] == category)
        and (show == "all" or item["state"] != rules.LATER)
    ]


def _events(db, control_db, tenant_id) -> list[dict]:
    """The events MDARIX has worked on (a triage record, an assessment, an obligation, a communication, a disposition
    or a named owner), with their readiness to close."""
    from backend.app.db.models.authority_reports import ReportObligation
    from backend.app.db.models.complaint_disposition import ComplaintDisposition
    from backend.app.db.models.guides_communications import CommunicationEntry
    from backend.app.db.models.intake import TriageRecord
    from backend.app.db.models.market_assessment import ComplaintMarketAssessment

    ids: set = set()
    for model, column in (
        (EventClosure, EventClosure.complaint_id),
        (ComplaintMarketAssessment, ComplaintMarketAssessment.complaint_id),
        (ReportObligation, ReportObligation.complaint_id),
        (CommunicationEntry, CommunicationEntry.complaint_id),
        (ComplaintDisposition, ComplaintDisposition.complaint_id),
    ):
        ids |= {row[0] for row in db.query(column).filter(model.tenant_id == tenant_id, column.isnot(None)).distinct()}
    ids |= {
        row[0]
        for row in db.query(TriageRecord.subject_id).filter(
            TriageRecord.tenant_id == tenant_id, TriageRecord.subject_kind == "COMPLAINT"
        )
    }
    if not ids:
        return []
    # Capped at EVENTS_MAX; each kind of record is read once for them all (0.10.85, D3.13).
    complaints = (
        db.query(Complaint)
        .filter(Complaint.tenant_id == tenant_id, Complaint.id.in_(list(ids)))
        .order_by(Complaint.complaint_identifier)
        .limit(EVENTS_MAX)
        .all()
    )
    tasks = closure.open_tasks_by_complaint(db, tenant_id)
    triage = closure.open_on_triage(db, tenant_id)
    rows = {row.complaint_id: row for row in db.query(EventClosure).filter(EventClosure.tenant_id == tenant_id)}
    products = _products(db, tenant_id)
    facts = closure.facts_many(db, tenant_id, complaints, tasks, triage)
    found = [_event_summary(c, facts[str(c.id)], rows.get(c.id), products) for c in complaints]
    refs = {item["owner_id"] for item in found}
    names = _names(control_db, tenant_id, refs)
    for item in found:
        item["owner_name"] = names.get(item["owner_id"] or "") if item["owner_id"] else None
    order = {"CLOSED_BEFORE_READY": 0, "NOT_FILED": 1, "READY_TO_SIGN": 2, "NOT_READY": 3, "FILED": 4, "CLOSED": 5}
    found.sort(key=lambda item: (order[item["state"]], item["ref"]))
    return found


EVENT_STATES = {
    "NOT_READY": "Not ready to close",
    "READY_TO_SIGN": "Checklist clear: the owner signs ready to close",
    "NOT_FILED": "Ready to close; decision record not filed in the QMS",
    "FILED": "Ready to close; decision record filed",
    "CLOSED_BEFORE_READY": "Closed in the QMS before it was ready",
    "CLOSED": "Closed in the QMS",
}


def _products(db, tenant_id) -> dict:
    from backend.app.db.models.foundation import Product

    return {row.id: row.name for row in db.query(Product.id, Product.name).filter(Product.tenant_id == tenant_id)}


def _event_state(complaint, items: list[dict], row: EventClosure | None) -> str:
    blocked = [item for item in items if item["result"] == closure.BLOCKED]
    closed = str(complaint.status or "").lower() in closure.CLOSED_STATUSES
    ready = row is not None and row.ready_state is not None
    if closed:
        return "CLOSED" if ready else "CLOSED_BEFORE_READY"
    if ready:
        return "FILED" if row.qms_filing_ref else "NOT_FILED"
    return "NOT_READY" if blocked else "READY_TO_SIGN"


def _event_summary(complaint, facts: dict, row: EventClosure | None, products: dict) -> dict:
    from backend.app.reportability import markets

    items = closure.checklist(facts)
    blocked = [item for item in items if item["result"] == closure.BLOCKED]
    state = _event_state(complaint, items, row)
    stages = closure.stage_line(facts, items, row)
    current = next((stage for stage in stages if stage["state"] == "CURRENT"), None)
    return {
        "complaint_id": str(complaint.id),
        "ref": complaint.complaint_identifier,
        "product": products.get(complaint.product_id),
        "market": markets.market_of(complaint.country),
        "owner_id": closure.owner_of(row, facts["record"]),
        "stage": current["label"] if current else "Closed in the QMS",
        "blocked": len(blocked),
        "next": blocked[0]["action"] if blocked and not closure.settled(complaint, items, row) else None,
        "state": state,
        "state_label": EVENT_STATES[state],
        "sample": is_sample(complaint.source_system),
    }


# Who may sign each step of a complaint: the permissions its signing route checks (intake, market assessment,
# authority report approval, disposition or case decision, CAPA effectiveness, ready to close). Shown before the work
# starts (7.8); separation of duties is unchanged: each route still refuses the same person where it did.
STEP_SIGNERS: dict[str, tuple[str, ...]] = {
    "TRIAGE": (SIGNAL_TRIAGE, INVESTIGATION_CREATE, QUALITY_REVIEW),
    "FIRST_CONTACT": (SIGNAL_TRIAGE, INVESTIGATION_CREATE, QUALITY_REVIEW),
    "MARKETS": (REGULATORY_REVIEW, REGULATORY_APPROVE),
    "OBLIGATIONS": (REGULATORY_REVIEW, REGULATORY_APPROVE),
    "DECISION": (SIGNAL_TRIAGE, INVESTIGATION_CREATE, QUALITY_REVIEW),
    "CASE_DECISION": (DECISION_SIGN,),
    "CAPA": (QUALITY_REVIEW, DECISION_SIGN),
    "READY": (
        SIGNAL_TRIAGE,
        INVESTIGATION_WORK,
        EVIDENCE_REQUEST,
        QUALITY_REVIEW,
        REGULATORY_REVIEW,
        REGULATORY_APPROVE,
    ),
}
# The steps another person must sign: an authority report's snapshot is approved by someone other than its preparer.
SECOND_PERSON = {"OBLIGATIONS"}


def _signers(control_db, tenant_id, me: str, has_case: bool) -> dict[str, dict]:
    from backend.app.workflow import approvals

    out = {}
    everyone = approvals.colleagues(control_db, tenant_id)
    for code, permissions in STEP_SIGNERS.items():
        if code == "CASE_DECISION":
            continue
        wanted = STEP_SIGNERS["CASE_DECISION"] if code == "DECISION" and has_case else permissions
        people = approvals.holders(control_db, tenant_id, wanted, everyone=everyone)
        out[code] = {
            "people": [{"id": ref, "name": name} for ref, name in people],
            "you": any(ref == me for ref, _ in people),
            "second_person": code in SECOND_PERSON,
        }
    return out


def dated_reads(db, control_db, tenant_id, now) -> tuple[list[dict], dict, dict[str, list[dict]]]:
    """The dated items, their context and the watch's clocks that the list's views, its order and its work columns all
    read: read once per request (0.10.85, D3.13; each read the whole watch again)."""
    incomplete: list[str] = []
    watched = service.watch_read(db, control_db, tenant_id, now, None, incomplete)  # B6a: the watch read once
    views, context = _item_views(db, control_db, tenant_id, now, watched=watched, incomplete=incomplete)
    clocks = _watch_clocks(db, control_db, tenant_id, None, now, context["settings"]["reminder_hours"], watched)
    return views, context, clocks


def _dated_items(reads) -> list[dict]:
    """Every complaint's dated items: its deadlines and targets, and the watch's provisional clock of a market not
    assessed yet, as the complaint page lists them (complaint_work)."""
    views, _, clocks = reads
    items = [item for item in views if item["complaint_id"]]
    dated = {
        (item["complaint_id"], item["market"]) for item in items if item["category"] in ("REPORTING", "OBLIGATION")
    }
    for key, found in clocks.items():
        items += [{**clock, "complaint_id": key} for clock in found if (key, clock["market"]) not in dated]
    return items


def urgency(reads) -> dict[str, tuple]:
    """Each complaint's place in every list view (0.10.85, D3.1): overdue first, then the nearest legal deadline (a
    market's reporting clock or report, never a task filed under it), then the nearest of its other dates."""
    found: dict[str, list] = {}
    for item in _dated_items(reads):
        mine = found.setdefault(str(item["complaint_id"]), [1, "~", "~"])
        if item["state"] == rules.OVERDUE:
            mine[0] = 0
        place = 1 if item["category"] in ("REPORTING", "OBLIGATION") and not str(item["key"]).startswith("task:") else 2
        mine[place] = min(mine[place], item["due_at"])
    return {key: tuple(value) for key, value in found.items()}


def complaint_work(db, control_db, tenant_id, complaints: list, reads=None, facts=None) -> dict[str, dict]:
    """What the new navigation shows for each complaint (0.10.68), from the same reads as Oversight and the event:
    its owner, stage, next action, its dated items (a deadline per market, then its own targets, soonest first) and
    the markets they are for. The complaint page, the complaint list and My work show these values, so they agree
    with Oversight (tests/test_complaint_page.py). ``facts``: the complaints' ``closure.facts`` already read by the
    caller, by id (B6a run 3: the complaint page read them twice)."""
    from backend.app.reportability import markets

    if not complaints:
        return {}
    ids = {str(complaint.id) for complaint in complaints}
    now = service.now_utc()
    if reads is None:
        # B6a: only these complaints' items and watch, the watch read once (equal to the whole organization's read
        # filtered to them: tests/test_b6a_scoped_watch.py).
        watched = service.watch_read(db, control_db, tenant_id, now, ids)
        views, context = _item_views(db, control_db, tenant_id, now, complaint_ids=ids, watched=watched)
        clocks = _watch_clocks(db, control_db, tenant_id, ids, now, context["settings"]["reminder_hours"], watched)
    else:
        views, context, clocks = reads
    due = [view for view in views if view["complaint_id"] in ids]
    rows = {
        row.complaint_id: row
        for row in db.query(EventClosure).filter(
            EventClosure.tenant_id == tenant_id, EventClosure.complaint_id.in_([c.id for c in complaints])
        )
    }
    products = _products(db, tenant_id)
    # Each kind of record is read once for the page (0.10.85, D3.13; it was a dozen queries per complaint).
    if facts is None:
        tasks = closure.open_tasks_by_complaint(db, tenant_id)
        facts = closure.facts_many(db, tenant_id, complaints, tasks, closure.open_on_triage(db, tenant_id, ids))
    found = {str(c.id): _event_summary(c, facts[str(c.id)], rows.get(c.id), products) for c in complaints}
    names = _names(control_db, tenant_id, {item["owner_id"] for item in found.values()})
    out = {}
    for complaint in complaints:
        key = str(complaint.id)
        item = found[key]
        mine = [view for view in due if view["complaint_id"] == key]
        # A market not assessed yet runs the reportability watch's provisional clock, which Oversight does not list
        # (it lists a market's clock once its assessment is started): shown here, so the page says what the watch says.
        # A line with no market (Home's "Enter the ..." line) dates no market, so it never hides the Imported backlog
        # target of a complaint that has no country yet (gap matrix S): the page shows both, as with a known country.
        dated = {view["market"] for view in mine if view["category"] in ("REPORTING", "OBLIGATION") and view["market"]}
        listed = {view["key"] for view in mine}
        mine += [clock for clock in clocks.get(key, []) if clock["market"] not in dated and clock["key"] not in listed]
        mine.sort(key=lambda view: view["due_at"])
        own = markets.market_of(complaint.country)
        out[key] = {
            "owner_id": item["owner_id"],
            "owner_name": names.get(item["owner_id"] or "") if item["owner_id"] else None,
            "stage": item["stage"],
            "next": item["next"],
            "state": item["state"],
            "due": [
                {
                    k: view[k]
                    for k in (
                        "key",
                        "category",
                        "category_label",
                        "title",
                        "market",
                        "due_at",
                        "due_label",
                        "state",
                        "state_label",
                        "hours_left",
                        "opens",
                    )
                }
                for view in mine
            ],
            "markets": sorted({view["market"] for view in mine if view["market"]} | ({own} if own else set())),
        }
    return out


def _watch_clocks(
    db, control_db, tenant_id, ids: set[str] | None, now, reminder_hours: int, watched: list[dict] | None = None
) -> dict[str, list[dict]]:
    """The reportability watch's running clock of each complaint (its binding deadline), as a dated item (``ids``:
    these complaints only; None: every one; ``watched``: the watch already read for them)."""
    from backend.app.reportability import facts, markets

    out: dict[str, list[dict]] = {}
    for item in watched if watched is not None else service.watch_read(db, control_db, tenant_id, now, ids):
        binding = item.get("binding")
        if (ids is not None and str(item["id"]) not in ids) or not binding or not binding.get("due_at"):
            continue
        due_at = datetime.fromisoformat(binding["due_at"])
        needs = item.get("needs") or []
        # A complaint that needs its country or awareness date has no market's real clock yet (0.10.81, F3, F4): one
        # provisional line that says what to enter, as Home's (oversight/service.py _watch_items).
        market = None if needs else binding.get("market")
        state = rules.state_of(due_at, now, reminder_hours)
        # Section Q decision 3 (owner, 10 Nov): an Imported backlog complaint's clock is the backlog target, with its
        # note, never a market window read overdue (reportability/service.py backlog_binding).
        backlog = bool(binding.get("backlog"))
        if backlog:
            needs, market = [], binding.get("market")
        out.setdefault(str(item["id"]), []).append(
            {
                "key": f"watch:{item['id']}:{'backlog' if backlog else 'facts' if needs else market}",
                "category": "REPORTING",
                "category_label": rules.CATEGORIES["REPORTING"],
                "title": f"{binding['window']} (Imported backlog target)"
                if backlog
                else f"Enter {facts.labels(needs)}: needed for the reporting clocks (provisional deadline)"
                if needs
                else f"{markets.MARKET_LABELS.get(market, market)}: not assessed yet, provisional deadline",
                "market": market,
                "due_at": due_at.isoformat(),
                "due_label": binding.get("due_label"),
                "state": state,
                "state_label": rules.STATE_LABELS[state],
                "hours_left": rules.hours_left(due_at, now),
                "opens": links.target("Complaints", "Imported backlog")
                if backlog
                else links.target("Complaints", "Reportability", record=("complaint", item["id"])),
            }
        )
    return out


# The list views of the new navigation (0.10.74, Release C part C2): each a filter of the one complaint list, read from
# the same dated items, watch, requests and signatures as the complaint page, Home and Oversight. "open" is filtered by
# the list itself (the complaint's status in the QMS).
LIST_VIEWS = (
    "open",
    "overdue",
    "due-week",
    "legal-week",
    "reportability",
    "waiting-reporter",
    "my-approval",
    "signed-month",
)
# Not a view of its own: every complaint's nearest dated item, overdue first, which orders "open" (0.10.82, U-08).
DATED = "dated"
WEEK_HOURS = 7 * 24


def list_view(db, control_db, tenant_id, view: str, me: str, reads=None) -> dict[str, str]:
    """The complaints of a list view (``view`` other than "open"), each with the moment it is ordered by: its nearest
    deadline (soonest first), or, for "signed-month", its latest signature (newest first)."""
    from backend.app.communications.service import open_requests
    from backend.app.db.models.authority_reports import ReportObligation, ReportSnapshot
    from backend.app.db.models.complaint_disposition import ComplaintDisposition
    from backend.app.db.models.market_assessment import ComplaintMarketAssessment
    from backend.app.reportability import service as reportability
    from backend.app.reportability.markets import CONCLUSIONS

    now = service.now_utc()
    found: dict[str, str] = {}

    def keep(complaint_id, moment) -> None:
        key, at = str(complaint_id), moment.isoformat() if hasattr(moment, "isoformat") else str(moment or "")
        if key not in found or (at and (not found[key] or at < found[key])):
            found[key] = at

    if view in ("due-week", "legal-week", "overdue", DATED):
        for item in _dated_items(reads or dated_reads(db, control_db, tenant_id, now)):
            soon = item["hours_left"] <= WEEK_HOURS
            if view == DATED or (view == "overdue" and item["state"] == rules.OVERDUE):
                keep(item["complaint_id"], item["due_at"])
            elif view == "due-week" and soon and item["state"] != rules.OVERDUE:
                keep(item["complaint_id"], item["due_at"])
            elif view == "legal-week" and soon and item["category"] in ("REPORTING", "OBLIGATION"):
                keep(item["complaint_id"], item["due_at"])
    elif view == "reportability":
        for item in reportability.watch(db, control_db, tenant_id, show="open", page_size=10_000, today=now)["items"]:
            # A decision is needed while a market has no signed conclusion; a signed reportable one waiting for its
            # report is under "Authority reports", not here (0.10.85, D3.2; U-13).
            summary = item.get("markets") or []
            if summary and all(market["state"] in CONCLUSIONS for market in summary):
                continue
            keep(item["id"], (item.get("binding") or {}).get("due_at") or "")
    elif view == "waiting-reporter":
        for row in open_requests(db, tenant_id):
            if row.complaint_id:
                keep(row.complaint_id, row.reply_due_on or "")
    elif view == "my-approval":
        # A report snapshot waiting for approval that this person did not prepare; in a trial the owner may approve
        # their own as practice ("Practice approval: in a pilot a colleague approves this").
        practice = _trial(control_db, tenant_id)
        for snapshot, complaint_id in (
            db.query(ReportSnapshot, ReportObligation.complaint_id)
            .join(ReportObligation, ReportObligation.id == ReportSnapshot.obligation_id)
            .filter(ReportSnapshot.tenant_id == tenant_id, ReportSnapshot.state == "PENDING")
        ):
            if practice or snapshot.requested_by != me:
                keep(complaint_id, snapshot.requested_at)
    elif view == "signed-month":
        zone = service.calendar_from(service.settings_view(service.settings_row(db, tenant_id))).tz
        local = now.astimezone(zone)
        start = local.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        signed = [
            db.query(ComplaintMarketAssessment.complaint_id, ComplaintMarketAssessment.signed_at).filter(
                ComplaintMarketAssessment.tenant_id == tenant_id, ComplaintMarketAssessment.signed_at >= start
            ),
            db.query(ComplaintDisposition.complaint_id, ComplaintDisposition.signed_at).filter(
                ComplaintDisposition.tenant_id == tenant_id, ComplaintDisposition.signed_at >= start
            ),
            db.query(EventClosure.complaint_id, EventClosure.signed_at).filter(
                EventClosure.tenant_id == tenant_id, EventClosure.signed_at >= start
            ),
            db.query(ReportObligation.complaint_id, ReportSnapshot.approved_at)
            .join(ReportObligation, ReportObligation.id == ReportSnapshot.obligation_id)
            .filter(ReportSnapshot.tenant_id == tenant_id, ReportSnapshot.approved_at >= start),
        ]
        for query in signed:
            for complaint_id, at in query:
                key = str(complaint_id)
                found[key] = max(found.get(key, ""), at.isoformat())
    return found


def _staffing(everyone: list[dict], role: str) -> str | None:
    holders = service.escalation_people(everyone, role)
    if len(everyone) < 2:
        return "Only one person can receive alerts: invite a colleague, so an overdue item reaches someone else."
    if not holders:
        return "Nobody holds the escalation role: choose another role or give it to someone."
    return None


@router.get("")
def oversight(
    product: str | None = Query(default=None, max_length=200),
    market: str | None = Query(default=None, max_length=10),
    category: str | None = Query(default=None, max_length=30),
    show: str = Query(default="attention", pattern="^(attention|all)$"),
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    tenant_id = _tenant(ctx)
    now = service.now_utc()
    service.sweep_if_stale(db, control_db, tenant_id, now)
    items, context = _item_views(db, control_db, tenant_id, now)
    shown = _filtered(items, product, market, category, show)
    counts = {
        code: {
            "label": label,
            "overdue": sum(1 for item in items if item["category"] == code and item["state"] == rules.OVERDUE),
            "due_soon": sum(1 for item in items if item["category"] == code and item["state"] == rules.DUE_SOON),
        }
        for code, label in rules.CATEGORIES.items()
    }
    events = _events(db, control_db, tenant_id)
    everyone = service.people(control_db, tenant_id)
    names = {**context["names"], **{person["id"]: person["name"] for person in everyone}}
    return {
        "as_of": now.isoformat(),
        "items": shown,
        "total": len(items),
        "counts": counts,
        "overdue": sum(1 for item in items if item["state"] == rules.OVERDUE),
        "due_soon": sum(1 for item in items if item["state"] == rules.DUE_SOON),
        "filters": {
            "products": sorted({item["product"] for item in items if item["product"]}),
            "markets": sorted({item["market"] for item in items if item["market"]}),
            "categories": [{"code": code, "label": label} for code, label in rules.CATEGORIES.items()],
        },
        "events": events,
        "event_counts": {state: sum(1 for item in events if item["state"] == state) for state in EVENT_STATES},
        "away": [_absence_view(item, names) for item in context["away"]],
        "settings": {
            **context["settings"],
            "escalation_role_label": _role_label(context["settings"]["escalation_role"]),
        },
        "staffing": _staffing(everyone, context["settings"]["escalation_role"]),
        "never": NEVER,
        # B6a run 3: a source that could not be read or reached its read cut; the screen says the list is incomplete.
        "incomplete": context["incomplete"],
    }


def _role_label(code: str) -> str:
    from backend.app.workflow.labels import role_label

    return role_label(code) or code


@router.get("/export.csv", dependencies=[Depends(require_permission(DATA_EXPORT))])
def export(
    product: str | None = Query(default=None, max_length=200),
    market: str | None = Query(default=None, max_length=10),
    category: str | None = Query(default=None, max_length=30),
    show: str = Query(default="attention", pattern="^(attention|all)$"),
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """The oversight list as CSV: IDs, owners, dates and states only (no patient or reporter data)."""
    from backend.app import csv_safe

    from backend.app.oversight.deadline_list import incomplete_note

    tenant_id = _tenant(ctx)
    items, context = _item_views(db, control_db, tenant_id, service.now_utc())
    stream = io.StringIO()
    writer = csv_safe.writer(stream, fieldnames=list(CSV_FIELDS))
    writer.writeheader()
    for item in _filtered(items, product, market, category, show):
        writer.writerow(
            {
                "category": item["category_label"],
                "title": item["title"],
                "ref": item["ref"] or "",
                "product": item["product"] or "",
                "market": item["market"] or "",
                "owner": item["owner"] or "",
                "queue": item["queue"] or "",
                "due_at": item["due_at"],
                "due_label": item["due_label"],
                "state": item["state_label"],
                "hours_left": item["hours_left"],
                "escalated_to": "; ".join(item["escalated_to"]),
            }
        )
    if context["incomplete"]:  # B6a run 4: as the deadline list's CSV, a last line says the list is incomplete
        writer.writerow({"category": "INCOMPLETE", "title": incomplete_note(context["incomplete"])})
    _audit(db, ctx, "OVERSIGHT_EXPORTED", "OversightView", None, product=product, market=market, category=category)
    db.commit()
    return Response(
        content=stream.getvalue().encode("utf-8-sig"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": attachment("mdarix-oversight.csv")},
    )


def _deadlines(db, control_db, ctx, kind: str) -> tuple[dict, list[dict]]:
    """B6a G18a: the open reporting deadlines for an offline copy; the download is audited (the caller commits)."""
    from backend.app.oversight import deadline_list

    if not deadline_list.switched_on():
        raise _error(404, "DEADLINE_LIST_OFF", "The deadline list is switched off")
    tenant_id = _tenant(ctx)
    found = deadline_list.lines(db, control_db, tenant_id)
    rows = deadline_list.with_owners(control_db, tenant_id, found)
    _audit(db, ctx, "DEADLINE_LIST_DOWNLOADED", "DeadlineList", None, format=kind, day=found["day"], lines=len(rows))
    return found, rows


@router.get("/deadlines.csv", dependencies=[Depends(require_permission(DATA_EXPORT))])
def deadlines_csv(
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """The open reporting deadlines as CSV (references, markets, dates, states and owners only)."""
    from backend.app.oversight import deadline_list

    found, rows = _deadlines(db, control_db, ctx, "csv")
    db.commit()
    return Response(
        content=deadline_list.as_csv(rows, found["incomplete"]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": attachment(f"mdarix-deadlines-{found['day']}.csv")},
    )


@router.get("/deadlines.pdf", dependencies=[Depends(require_permission(DATA_EXPORT))])
def deadlines_pdf(
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """The open reporting deadlines as a printable PDF, one page per 40 lines, for an outage."""
    from backend.app.oversight import deadline_list
    from backend.app.stage3_workflow_router import _organization_name

    found, rows = _deadlines(db, control_db, ctx, "pdf")
    body = deadline_list.as_pdf(found, rows, _organization_name(control_db, _tenant(ctx)))
    db.commit()
    return Response(
        content=body,
        media_type="application/pdf",
        headers={"Content-Disposition": attachment(f"mdarix-deadlines-{found['day']}.pdf")},
    )


# --------------------------------------------------------------------------------------------- settings


class HolidayIn(BaseModel):
    date: date
    name: str = Field(default="", max_length=rules.HOLIDAY_NAME_MAX * 2)


class SettingsIn(BaseModel):
    time_zone: str = Field(max_length=60)
    work_days: list[int] = Field(max_length=7)
    holidays: list[HolidayIn] = Field(default_factory=list, max_length=rules.HOLIDAYS_MAX * 2)
    reminder_hours: int = Field(ge=rules.HOURS_MIN, le=rules.HOURS_MAX)
    escalation_role: str = Field(max_length=60)


def _settings_body(db, tenant_id) -> dict:
    view = service.settings_view(service.settings_row(db, tenant_id))
    return {
        **view,
        "escalation_role_label": _role_label(view["escalation_role"]),
        "roles": [{"code": code, "label": _role_label(code)} for code in ESCALATION_ROLES],
        "weekdays": list(rules.WEEKDAYS),
        "zones": list(rules.zone_names()),
        "range": [rules.HOURS_MIN, rules.HOURS_MAX],
    }


@router.get("/settings")
def settings(
    db: Session = Depends(get_data_plane_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    return _settings_body(db, _tenant(ctx))


@router.put("/settings", dependencies=[SETTERS])
def save_settings(
    payload: SettingsIn,
    db: Session = Depends(get_data_plane_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    tenant_id = _tenant(ctx)
    holidays = [{"date": item.date, "name": " ".join(item.name.split())} for item in payload.holidays]
    payload.time_zone = rules.canonical_zone(payload.time_zone)
    problem = rules.calendar_problem(payload.time_zone, payload.work_days, holidays)
    if problem is None and payload.escalation_role not in ESCALATION_ROLES:
        problem = "Choose the escalation role from the list"
    if problem:
        raise _error(422, "SETTINGS_INVALID", problem)
    now = service.now_utc()
    row = service.settings_row(db, tenant_id)
    old = service.settings_view(row)
    if row is None:
        row = OversightSettings(id=uuid.uuid4(), tenant_id=tenant_id)
        db.add(row)
    row.time_zone, row.work_days = payload.time_zone, sorted(payload.work_days)
    row.holidays = [
        {"date": item["date"].isoformat(), "name": item["name"]} for item in sorted(holidays, key=lambda h: h["date"])
    ]
    row.reminder_hours, row.escalation_role = payload.reminder_hours, payload.escalation_role
    row.updated_by, row.updated_at, row.swept_at = str(ctx.user_id), now, None
    db.flush()
    db.add(
        make_audit_event(
            tenant_id=tenant_id,
            actor_ref=ctx.user_id,
            action="OVERSIGHT_SETTINGS_CHANGED",
            entity_type="OversightSettings",
            entity_id=row.id,
            correlation_id=ctx.correlation_id,
            old_values={
                key: old[key] for key in ("time_zone", "work_days", "holidays", "reminder_hours", "escalation_role")
            },
            new_values={
                key: service.settings_view(row)[key]
                for key in ("time_zone", "work_days", "holidays", "reminder_hours", "escalation_role")
            },
        )
    )
    db.commit()
    return _settings_body(db, tenant_id)


class AlertsAndFilesIn(BaseModel):
    urgent_email: bool | None = None
    attachment_quota_mb: int | None = Field(default=None, ge=1, le=10240)


@router.put("/settings/alerts-and-files", dependencies=[SETTERS])
def save_alerts_and_files(
    payload: AlertsAndFilesIn,
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """B7: the opt-in urgent e-mail alert (off by default, B7-D12) and the attachment storage in MB (B7-D16; a free
    trial keeps 100 MB). Audited OVERSIGHT_SETTINGS_CHANGED with the old and new values."""
    from backend.app.signer_training.router import is_trial

    tenant_id = _tenant(ctx)
    if payload.attachment_quota_mb not in (None, 100) and is_trial(control_db, tenant_id):
        raise _error(422, "SETTINGS_INVALID", "A free trial keeps 100 MB of file storage")
    row = service.settings_row(db, tenant_id)
    if row is None:
        row = OversightSettings(id=uuid.uuid4(), tenant_id=tenant_id)
        db.add(row)
        db.flush()
    fields = ("urgent_email", "attachment_quota_mb")
    old = {key: service.settings_view(row)[key] for key in fields}
    for key in fields:
        if getattr(payload, key) is not None:
            setattr(row, key, getattr(payload, key))
    row.updated_by, row.updated_at = str(ctx.user_id), service.now_utc()
    db.flush()
    db.add(
        make_audit_event(
            tenant_id=tenant_id,
            actor_ref=ctx.user_id,
            action="OVERSIGHT_SETTINGS_CHANGED",
            entity_type="OversightSettings",
            entity_id=row.id,
            correlation_id=ctx.correlation_id,
            old_values=old,
            new_values={key: service.settings_view(row)[key] for key in fields},
        )
    )
    db.commit()
    return _settings_body(db, tenant_id)


# --------------------------------------------------------------------------------------------- my alerts


def _alert_view(alert: DueAlert, now: datetime, hours: int, names: dict, zone: str = "UTC") -> dict:
    due = alert.due_at
    state = rules.state_of(due, now, hours)
    legal = alert.category in ("REPORTING", "OBLIGATION")
    return {
        "id": str(alert.id),
        "tier": alert.tier,
        "tier_label": rules.TIER_LABELS[alert.tier],
        "reason": alert.reason,
        "reason_label": rules.REASON_LABELS.get(alert.reason, alert.reason),
        "category": alert.category,
        "category_label": rules.CATEGORIES.get(alert.category, alert.category),
        "title": alert.title,
        "ref": alert.ref,
        "owner": names.get(alert.owner_id or "") if alert.owner_id else None,
        "due_at": due.isoformat(),
        "due_label": due_label(due, None, zone, legal),
        "state": state,
        "state_label": rules.STATE_LABELS[state],
        "hours_left": rules.hours_left(due, now),
        "raised_at": alert.raised_at.isoformat(),
        "read": alert.read_at is not None,
        "opens": alert.opens,
        # A2 (B2): how it was delivered; a failure shows and the alert stays.
        "channel": alert.channel,
        "attempts": alert.attempts,
        "last_attempt_at": alert.last_attempt_at.isoformat() if alert.last_attempt_at else None,
        "delivery": alert.delivery,
        "delivery_error": alert.delivery_error,
    }


@router.get("/alerts")
def my_alerts(
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """The signed-in person's open reminders and escalations, escalations and overdue ones first."""
    tenant_id = _tenant(ctx)
    now = service.now_utc()
    service.sweep_if_stale(db, control_db, tenant_id, now)
    me = str(ctx.user_id)
    rows = (
        db.query(DueAlert)
        .filter(DueAlert.tenant_id == tenant_id, DueAlert.recipient_id == me, DueAlert.resolved_at.is_(None))
        .order_by(DueAlert.due_at)
        .limit(500)
        .all()
    )
    hours = service.settings_view(service.settings_row(db, tenant_id))["reminder_hours"]
    names = _names(control_db, tenant_id, {row.owner_id for row in rows})
    # One line per item: its escalation stands for its reminder too (both are marked read together).
    by_item: dict[str, dict] = {}
    zone = service.calendar_of(db, tenant_id).zone
    for row in rows:
        view = _alert_view(row, now, hours, names, zone)
        kept = by_item.get(row.item_key)
        if kept is None:
            by_item[row.item_key] = {**view, "ids": [view["id"]]}
            continue
        ids = [*kept["ids"], view["id"]]
        if view["tier"] == rules.ESCALATION:
            kept = {**view, "read": view["read"] and kept["read"]}
        by_item[row.item_key] = {**kept, "ids": ids, "read": kept["read"] and view["read"]}
    items = list(by_item.values())
    items.sort(key=lambda item: (item["tier"] != rules.ESCALATION, item["state"] != rules.OVERDUE, item["due_at"]))
    today = service.calendar_of(db, tenant_id).local_day(now)
    away = [item for item in service.absences(db, tenant_id, today) if me in (item["user_id"], item["backup_id"])]
    people_names = _names(control_db, tenant_id, {ref for item in away for ref in (item["user_id"], item["backup_id"])})
    return {
        "items": items,
        "unread": sum(1 for item in items if not item["read"]),
        "escalations": sum(1 for item in items if item["tier"] == rules.ESCALATION),
        "absences": [_absence_view(item, people_names) for item in away],
        "people": [{"id": p["id"], "name": p["name"]} for p in service.people(control_db, tenant_id) if p["id"] != me],
        "never": NEVER,
    }


class ReadIn(BaseModel):
    ids: list[uuid.UUID] = Field(default_factory=list, max_length=500)
    all: bool = False


@router.post("/alerts/read")
def mark_read(
    payload: ReadIn,
    db: Session = Depends(get_data_plane_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """Mark the person's own alerts read (``all``: every open one). Reading never resolves an alert."""
    tenant_id = _tenant(ctx)
    query = db.query(DueAlert).filter(
        DueAlert.tenant_id == tenant_id,
        DueAlert.recipient_id == str(ctx.user_id),
        DueAlert.resolved_at.is_(None),
        DueAlert.read_at.is_(None),
    )
    if not payload.all:
        if not payload.ids:
            return {"read": 0}
        query = query.filter(DueAlert.id.in_(payload.ids))
    now = service.now_utc()
    count = 0
    for alert in query.all():
        alert.read_at = now
        count += 1
    db.commit()
    return {"read": count}


# --------------------------------------------------------------------------------------------- absences


class AbsenceIn(BaseModel):
    starts_on: date
    ends_on: date
    backup_id: str = Field(max_length=64)
    note: str = Field(default="", max_length=rules.NOTE_MAX * 2)


@router.get("/absences")
def absence_list(
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    tenant_id = _tenant(ctx)
    today = service.calendar_of(db, tenant_id).local_day(service.now_utc())
    found = service.absences(db, tenant_id, today)
    names = _names(control_db, tenant_id, {ref for item in found for ref in (item["user_id"], item["backup_id"])})
    return {"items": [_absence_view(item, names) for item in found]}


@router.post("/absences")
def record_absence(
    payload: AbsenceIn,
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """The signed-in person's own absence, with the colleague who covers it. The backup receives the reminders and
    escalations; ownership stays, and the backup gains no signing right."""
    tenant_id = _tenant(ctx)
    me = str(ctx.user_id)
    now = service.now_utc()
    today = service.calendar_of(db, tenant_id).local_day(now)
    note = " ".join(payload.note.split())
    problem = rules.absence_problem(me, payload.backup_id, payload.starts_on, payload.ends_on, today)
    if problem is None and payload.backup_id not in {p["id"] for p in service.people(control_db, tenant_id)}:
        problem = "Choose your backup among your organization's people"
    if problem is None and len(note) > rules.NOTE_MAX:
        problem = f"Keep the note to {rules.NOTE_MAX} characters"
    if problem:
        raise _error(422, "ABSENCE_INVALID", problem)
    row = UserAbsence(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        user_id=me,
        starts_on=payload.starts_on,
        ends_on=payload.ends_on,
        backup_id=payload.backup_id,
        note=note or None,
        created_by=me,
        created_at=now,
    )
    db.add(row)
    db.flush()
    _audit(
        db,
        ctx,
        "ABSENCE_RECORDED",
        "UserAbsence",
        row.id,
        starts_on=payload.starts_on.isoformat(),
        ends_on=payload.ends_on.isoformat(),
        backup=payload.backup_id,
    )
    service.sweep(db, control_db, tenant_id, now)
    db.commit()
    return absence_list(db, control_db, ctx)


@router.post("/absences/{absence_id}/cancel")
def cancel_absence(
    absence_id: uuid.UUID,
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """End the person's own absence early (the record stays)."""
    tenant_id = _tenant(ctx)
    row = (
        db.query(UserAbsence)
        .filter(UserAbsence.tenant_id == tenant_id, UserAbsence.id == absence_id, UserAbsence.cancelled_at.is_(None))
        .one_or_none()
    )
    if row is None or row.user_id != str(ctx.user_id):
        raise _error(404, "ABSENCE_NOT_FOUND", "No such absence of yours")
    now = service.now_utc()
    row.cancelled_by, row.cancelled_at = str(ctx.user_id), now
    db.flush()  # the sweep below reads the absences again
    _audit(db, ctx, "ABSENCE_CANCELLED", "UserAbsence", row.id)
    service.sweep(db, control_db, tenant_id, now)
    db.commit()
    return absence_list(db, control_db, ctx)


# --------------------------------------------------------------------------------------------- the event


def _complaint(db, tenant_id, complaint_id) -> Complaint:
    """A complaint by its id, else (the complaint page, /app/complaints/<ref>) by the reference people see: the
    customer's own (unique in the organization), else its MDARIX ID."""
    key = complaint_id if isinstance(complaint_id, uuid.UUID) else None
    if key is None:
        try:
            key = uuid.UUID(str(complaint_id))
        except ValueError:
            key = None
    query = db.query(Complaint).filter(Complaint.tenant_id == tenant_id)
    complaint = query.filter(Complaint.id == key).one_or_none() if key else None
    if complaint is None and key is None:
        ref = str(complaint_id)[:120]
        complaint = (
            query.filter(Complaint.complaint_identifier == ref).one_or_none()
            or query.filter(Complaint.business_id == ref).one_or_none()
        )
    if complaint is None:
        raise _error(404, "COMPLAINT_NOT_FOUND", "No such complaint in your organization")
    return complaint


def harm_words(complaint) -> str:
    """The reported harm in plain words: a death, a serious injury, none reported, or not known yet (a blank flag)."""
    if complaint.death:
        return "Death"
    if complaint.serious_injury:
        return "Serious injury"
    if complaint.serious_injury is None and complaint.death is None:
        return "Not known yet"
    return "No harm reported"


def _resolve_label(db, control_db, tenant_id, complaint: Complaint, found: dict, blocked: list[dict]) -> str | None:
    """B7: the next step after triage is "Resolve and close" (its Connect wording) when the disposition is next and no
    escalation trigger is met; with a trigger it stays "Sign the disposition" (the decision tree escalates)."""
    from backend.app.feature_set import routine_path

    if not routine_path() or not blocked or blocked[0]["code"] != "DECISION" or found["disposition"] is not None:
        return None
    if ((blocked[0]["opens"] or {}).get("target") or {}).get("tab") != "Dispositions":
        return None  # decided in an investigation
    from backend.app.complaint_disposition import resolve, service as disposition_service

    facts = disposition_service.screen_facts(db, tenant_id, complaint.id, disposition_service.today_utc())
    if facts is None or facts["triggers"]:
        return None
    return resolve.BUTTONS[resolve.mode_of(db, control_db, tenant_id, complaint)]


def event_view(db, control_db, tenant_id, complaint: Complaint, me: str) -> dict:
    from backend.app.intake import service as intake_service
    from backend.app.reportability import facts, markets
    from backend.app.reportability.deadlines import day_only
    from backend.app.reportability import service as reporting_service

    found = closure.facts(db, tenant_id, complaint)
    row = closure.closure_row(db, tenant_id, complaint.id)
    items = closure.checklist(found)
    blocked = [item for item in items if item["result"] == closure.BLOCKED]
    next_label = _resolve_label(db, control_db, tenant_id, complaint, found, blocked)
    owner = closure.owner_of(row, found["record"])
    refs = {owner, row.signed_by if row else None, row.filed_by if row else None}
    refs |= {e.signed_by for e in found["first_contact"]} | {d.signed_by for d in found["dispositions"]}
    refs |= {v.signed_by for versions in found["assessments"].values() for v in versions}
    refs |= {s.approved_by for s in found["snapshots"]} | {str(d.decided_by_user_id) for d in found["decisions"]}
    refs |= {d.authorized_by_ref for d in found["decisions"]}
    if found["record"] is not None:
        refs |= {found["record"].completed_by, found["record"].triage_owner}
    refs.add(complaint.service_owner)
    refs |= {v.created_by for versions in found["assessments"].values() for v in versions}
    refs |= {s.requested_by for s in found["snapshots"]}
    # B9b: the countries' signers and the people who recorded an Other Regulatory Report as submitted.
    refs |= {v.signed_by for versions in found["other_assessments"].values() for v in versions}
    refs |= {submission.recorded_by for _, submission, _ in found["attached"]}
    names = _names(control_db, tenant_id, refs)
    record = closure.decision_record(control_db, found, row, names)
    signed_print = row.content_fingerprint if row is not None else None
    changed = bool(row and row.ready_state and signed_print != closure.fingerprint(complaint.id, items))
    work = complaint_work(db, control_db, tenant_id, [complaint], facts={str(complaint.id): found})[str(complaint.id)]
    nearest = work["due"][0] if work["due"] else None
    state = _event_state(complaint, items, row)
    signers = _signers(control_db, tenant_id, me, bool(found["cases"]))
    product = _products(db, tenant_id).get(complaint.product_id)
    version, lot = _version_and_lot(db, tenant_id, complaint)
    practice = _practice(control_db, tenant_id)
    return {
        "event": {
            "complaint_id": str(complaint.id),
            "ref": complaint.complaint_identifier,
            "business_id": complaint.business_id,
            "product": product,
            "lot_batch_id": str(complaint.lot_batch_id) if complaint.lot_batch_id else None,
            # What happened, as the complaint records it (the complaint page's header, 0.10.68).
            "description": complaint.description,
            "problem_code": complaint.problem_code,
            "version": version,
            "lot": lot,
            "country": complaint.country,
            "harm": "DEATH"
            if complaint.death
            else "SERIOUS_INJURY"
            if complaint.serious_injury
            else "PATIENT_INVOLVED"
            if complaint.patient_involved
            else None,
            # The harm in words, apart from whether a patient was involved (0.10.82, U-18): a blank serious-injury
            # flag is "not known yet", never "no harm".
            "harm_words": harm_words(complaint),
            "patient_involved": complaint.patient_involved,
            "market": markets.market_of(complaint.country),
            "awareness_at": _iso(complaint.awareness_timestamp),
            # A day given without a time is shown as a date (0.10.81, U-06).
            "awareness_date_only": day_only(complaint.awareness_timestamp),
            # The facts a reporting step needs and the record does not give (0.10.81, reportability/facts.py).
            "needs": facts.of_complaint(complaint, reporting_service._record(complaint, None, None)),
            "status_in_qms": complaint.status,
            "owner_id": owner,
            "owner_name": names.get(owner or "") if owner else None,
            "owner_named": bool(row and row.owner_id),
            "sample": is_sample(complaint.source_system),
        },
        # B2 (spec 4.6): where the complaint came from (a Case in MDARIX, or the QMS), and the Case's own card.
        "origin": {
            "from_case": complaint.source_system == "MDARIX_CASE",
            "case_ref": complaint.source_identifier if complaint.source_system == "MDARIX_CASE" else None,
            "created_at": _iso(complaint.created_at),
            "record_owner": complaint.record_owner,
            "qms_ref": complaint.qms_ref,
            "last_synced_at": _iso(complaint.last_synced_at),
        },
        "case": intake_service.case_of_complaint(db, tenant_id, complaint, names),
        "summary": {
            # The nearest dated item, the reportability watch's provisional clock included (0.10.68).
            "nearest_deadline": {key: nearest[key] for key in ("title", "due_at", "opens")} if nearest else None,
            "open_requests": len(found["requests"]),
            "next_action": {
                "label": next_label or blocked[0]["action"],
                "detail": blocked[0]["detail"],
                "opens": blocked[0]["opens"],
            }
            if blocked and not closure.settled(complaint, items, row)
            else None,
        },
        "stages": closure.stage_line(found, items, row),
        "checklist": items,
        "blocked": len(blocked),
        "state": state,
        "state_label": EVENT_STATES[state],
        "changed_since_signed": changed,
        "ready": {
            "state": row.ready_state,
            "reason": row.ready_reason,
            "version": row.version,
            "signed_by": names.get(row.signed_by or "") or "A colleague",
            "signed_at": _iso(row.signed_at),
            # B7: closed by MDARIX itself (Complete); reopened with a reason.
            "closed_at": _iso(row.closed_at),
        }
        if row is not None and row.ready_state
        else None,
        "decision_record": record,
        # The linked service work (0.10.71, A5): its reference, owner and status; it never moves the complaint.
        "service": service_work.view(complaint, names),
        "you_are_owner": owner == me,
        "people": [{"id": p["id"], "name": p["name"]} for p in service.people(control_db, tenant_id)],
        "reason_min": closure.REASON_MIN,
        "never_closes": closure.NEVER_CLOSES,
        "practice_label": practice,
        # The owner, stage, next action and dated items the lists and My work show for it (0.10.68).
        "work": work,
        # Who may sign each step, before the work starts (7.8).
        "signers": signers,
        # Who prepared, who may approve and who approved the decision record's work (0.10.71, A6); apart from the
        # record so its fingerprint is unchanged.
        "record_people": _record_people(found, row, names, signers, me, bool(practice)),
        # The page's Related (0.10.74, C2): the records linked to the complaint, in plain lines.
        "related": record_page.related(
            db, found, complaint, names, service_work.view(complaint, names), work["markets"]
        ),
    }


def _record_people(found: dict, row, names: dict, signers: dict, me: str, trial: bool) -> dict:
    from backend.app.workflow.approvals import PRACTICE_APPROVAL

    """Separation of duties, shown honestly (0.10.71, A6): who prepared the event's work (the triage record, the
    market assessments, the reports asked for approval), who may approve it (the market conclusions and the reports)
    and who approved (every signature). Working alone in a trial one person is all three: practice approval."""

    def named(refs) -> list[str]:
        found_names: list[str] = []
        for ref in refs:
            name = names.get(ref or "")
            if ref and name and name not in found_names:
                found_names.append(name)
        return found_names

    record = found["record"]
    versions = [v for items in found["assessments"].values() for v in items]
    prepared = named(
        [record.completed_by if record is not None and record.completed_at else None]
        + [v.created_by for v in versions]
        + [s.requested_by for s in found["snapshots"]]
    )
    may = [p for code in ("MARKETS", "OBLIGATIONS") for p in (signers.get(code) or {}).get("people", [])]
    approved = named(
        [v.signed_by for v in versions if v.signed_at is not None]
        + [s.approved_by for s in found["snapshots"] if s.approved_at is not None]
        + [d.signed_by for d in found["dispositions"] if d.signed_at is not None]
        + [row.signed_by if row is not None and row.signed_at else None]
    )
    alone = {p["id"] for p in may} == {me}
    return {
        "prepared_by": prepared,
        "may_approve": list(dict.fromkeys(p["name"] for p in may)),
        "approved_by": approved,
        "practice_note": PRACTICE_APPROVAL if trial and alone else None,
    }


def _version_and_lot(db, tenant_id, complaint) -> tuple[str | None, str | None]:
    from backend.app.db.models.foundation import LotBatch, ProductVersion

    version = (
        db.query(ProductVersion.version_identifier)
        .filter(ProductVersion.tenant_id == tenant_id, ProductVersion.id == complaint.product_version_id)
        .scalar()
        if complaint.product_version_id
        else None
    )
    lot = (
        db.query(LotBatch.lot_identifier)
        .filter(LotBatch.tenant_id == tenant_id, LotBatch.id == complaint.lot_batch_id)
        .scalar()
        if complaint.lot_batch_id
        else None
    )
    return version, lot


def _practice(control_db, tenant_id) -> str | None:
    from backend.app.reportability import markets

    return markets.PRACTICE_LABEL if _trial(control_db, tenant_id) else None


@router.get("/latest-signed")
def latest_signed(
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """The newest record the signed-in person signed in this organization (Records leads with it, 0.10.74), or
    ``{"record": null}``; while it is null, ``organization`` is the newest anyone signed there (a trial's sample
    signatures, 0.10.92, A2), or null."""
    tenant_id = _tenant(ctx)

    def names(refs):
        return _names(control_db, tenant_id, refs)

    record = record_page.latest_signed(db, tenant_id, str(ctx.user_id), names)
    return {
        "record": record,
        "organization": None if record else record_page.latest_signed(db, tenant_id, None, names),
    }


@router.get("/events/{complaint_id}/activity")
def event_activity(
    complaint_id: str,
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """The complaint page's Activity (0.10.74): the complaint's own audit events, newest first, in plain words."""
    tenant_id = _tenant(ctx)
    complaint = _complaint(db, tenant_id, complaint_id)
    found = closure.facts(db, tenant_id, complaint)
    return record_page.activity(db, found, complaint, lambda refs: _names(control_db, tenant_id, refs))


@router.get("/events/{complaint_id}")
def event(
    # The complaint's id, or (the complaint page, 0.10.68) the reference people see: its own, else its MDARIX ID.
    complaint_id: str,
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    tenant_id = _tenant(ctx)
    return event_view(db, control_db, tenant_id, _complaint(db, tenant_id, complaint_id), str(ctx.user_id))


class SendBody(BaseModel):
    step: str = Field(pattern="^(TRIAGE|FIRST_CONTACT|MARKETS|OBLIGATIONS|DECISION|CAPA|READY)$")
    to_user_id: str = Field(min_length=1, max_length=64)
    note: str | None = Field(default=None, max_length=500)


@router.post("/events/{complaint_id}/send", dependencies=[WRITERS])
def send_step(
    complaint_id: uuid.UUID,
    body: SendBody,
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """ "Send to <colleague>" (0.10.68, 7.8): the step lands in that person's My work as a task naming the complaint.
    Only a colleague who may sign the step can receive it; sending changes no record and signs nothing."""
    from backend.app.workflow.tasks import create_task

    tenant_id = _tenant(ctx)
    complaint = _complaint(db, tenant_id, complaint_id)
    me = str(ctx.user_id)
    found = closure.facts(db, tenant_id, complaint)
    signers = _signers(control_db, tenant_id, me, bool(found["cases"]))[body.step]
    person = next((item for item in signers["people"] if item["id"] == body.to_user_id), None)
    if person is None:
        raise _error(409, "NOT_A_SIGNER", "That colleague may not sign this step; choose one of the people named.")
    action = next(
        (item["action"] for item in closure.checklist(found) if item["code"] == body.step and item.get("action")),
        None,
    )
    title = f"{action or STEP_TITLES[body.step]} on {complaint.complaint_identifier}"
    task = create_task(
        db,
        tenant_id,
        task_type="COMPLAINT_STEP",
        title=title,
        source_type="Complaint",
        source_id=complaint.id,
        assigned_user_id=person["id"],
        created_by=me,
        details={"complaint_id": str(complaint.id), "step": body.step, "note": (body.note or "").strip() or None},
    )
    _audit(db, ctx, "COMPLAINT_STEP_SENT", "Complaint", complaint.id, step=body.step, to=person["id"])
    db.commit()
    return {"task_id": str(task.id), "to": person["name"], "title": task.title}


class ServiceBody(BaseModel):
    reference: str = Field(max_length=service_work.REFERENCE_MAX * 2)
    status: str = Field(max_length=20)
    owner_id: str | None = Field(default=None, max_length=64)


@router.put("/events/{complaint_id}/service", dependencies=[WRITERS])
def record_service(
    complaint_id: uuid.UUID,
    body: ServiceBody,
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """The complaint's linked service work (0.10.71, A5): its reference in the customer's service system, its owner and
    status, dated now. It changes nothing else: the complaint, its assessments and its checklist stay as they are."""
    tenant_id = _tenant(ctx)
    complaint = _complaint(db, tenant_id, complaint_id)
    reference, status = " ".join(body.reference.split()), body.status.strip().upper()
    owner = (body.owner_id or "").strip() or None
    people = {item["id"] for item in service.people(control_db, tenant_id)}
    problem = service_work.problem(reference, status, owner, people)
    if problem:
        raise _error(422, "SERVICE_INVALID", problem)
    before = {
        "reference": complaint.service_reference,
        "status": complaint.service_status,
        "owner": complaint.service_owner,
    }
    complaint.service_reference, complaint.service_owner = reference, owner
    if status != complaint.service_status or complaint.service_status_at is None:
        complaint.service_status, complaint.service_status_at = status, service.now_utc()
    _audit(
        db,
        ctx,
        "COMPLAINT_SERVICE_RECORDED",
        "Complaint",
        complaint.id,
        before=before,
        after={"reference": reference, "status": status, "owner": owner},
    )
    db.commit()
    return event_view(db, control_db, tenant_id, complaint, str(ctx.user_id))


STEP_TITLES = {
    "TRIAGE": "Complete the triage",
    "FIRST_CONTACT": "Sign the first-contact check",
    "MARKETS": "Sign the market assessments",
    "OBLIGATIONS": "Approve the authority report",
    "DECISION": "Sign the decision",
    "CAPA": "Sign the CAPA's effectiveness check",
    "READY": "Sign ready to close",
}


def _closure_for_update(db, tenant_id, complaint_id) -> EventClosure:
    row = (
        db.query(EventClosure)
        .filter(EventClosure.tenant_id == tenant_id, EventClosure.complaint_id == complaint_id)
        .with_for_update()
        .one_or_none()
    )
    if row is None:
        row = EventClosure(
            id=uuid.uuid4(), tenant_id=tenant_id, complaint_id=complaint_id, version=0, updated_at=service.now_utc()
        )
        db.add(row)
        db.flush()
    return row


class OwnerIn(BaseModel):
    owner_id: str = Field(max_length=64)


@router.put("/events/{complaint_id}/owner", dependencies=[WRITERS])
def set_owner(
    complaint_id: uuid.UUID,
    payload: OwnerIn,
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    tenant_id = _tenant(ctx)
    complaint = _complaint(db, tenant_id, complaint_id)
    if payload.owner_id not in {p["id"] for p in service.people(control_db, tenant_id)}:
        raise _error(422, "OWNER_UNKNOWN", "Choose the event owner among your organization's people")
    row = _closure_for_update(db, tenant_id, complaint.id)
    old = row.owner_id
    now = service.now_utc()
    row.owner_id, row.owner_set_by, row.owner_set_at, row.updated_at = payload.owner_id, str(ctx.user_id), now, now
    db.add(
        make_audit_event(
            tenant_id=tenant_id,
            actor_ref=ctx.user_id,
            action="EVENT_OWNER_SET",
            entity_type="EventClosure",
            entity_id=row.id,
            correlation_id=ctx.correlation_id,
            old_values={"owner": old},
            new_values={"owner": payload.owner_id},
            details={"complaint": complaint.complaint_identifier},
        )
    )
    db.commit()
    return event_view(db, control_db, tenant_id, complaint, str(ctx.user_id))


class ReadyIn(BaseModel):
    password: str = Field(min_length=1, max_length=128)
    mfa_code: str | None = Field(default=None, max_length=12)
    reason: str = Field(default="", max_length=closure.REASON_MAX * 2)


@router.post("/events/{complaint_id}/ready", dependencies=[WRITERS])
def sign_ready(
    complaint_id: uuid.UUID,
    payload: ReadyIn,
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """The event owner signs "ready to close in the QMS": the checklist clear, or with a reason when items are open.
    MDARIX never closes the complaint."""
    from backend.app.evidence_workflow.people import current_person
    from backend.app.governance_router import verify_signing_credentials
    from backend.app.human_decision.rules import signature_hash
    from backend.app.role_codes import is_administrator_role

    tenant_id = _tenant(ctx)
    complaint = _complaint(db, tenant_id, complaint_id)
    me = str(ctx.user_id)
    found = closure.facts(db, tenant_id, complaint)
    row = closure.closure_row(db, tenant_id, complaint.id)
    owner = closure.owner_of(row, found["record"])
    if owner != me:
        raise _error(
            403, "EVENT_OWNER_SIGNS", "Only the event owner signs ready to close: name yourself the owner first"
        )
    person = current_person(control_db, ctx)
    if is_administrator_role(person.account_role or ""):
        raise _error(403, "ADMINISTRATOR_NEVER_SIGNS", "An administrator account never signs")
    items = closure.checklist(found)
    blocked = [item for item in items if item["result"] == closure.BLOCKED]
    reason = " ".join(payload.reason.split())
    if blocked and len(reason) < closure.REASON_MIN:
        raise _error(
            422,
            "REASON_REQUIRED",
            f"{len(blocked)} items are still open: give the reason to sign anyway, in at least {closure.REASON_MIN} "
            "characters, or resolve them first",
            blocked=[item["label"] for item in blocked],
        )
    if len(reason) > closure.REASON_MAX:
        raise _error(422, "REASON_TOO_LONG", f"Keep the reason to {closure.REASON_MAX} characters")

    def refused(action: str) -> None:
        control_db.add(
            make_audit_event(
                tenant_id=tenant_id,
                actor_ref=ctx.user_id,
                action=action,
                entity_type=closure.OBJECT_TYPE,
                entity_id=row.id if row else None,
                correlation_id=ctx.correlation_id,
                details={"attempt": "EVENT_READY_TO_CLOSE", "complaint": complaint.complaint_identifier},
            )
        )

    verify_signing_credentials(
        control_db, ctx, password=payload.password, mfa_code=payload.mfa_code, record_refusal=refused
    )
    row = _closure_for_update(db, tenant_id, complaint.id)
    now = service.now_utc()
    version = row.version + 1
    print_ = closure.fingerprint(complaint.id, items)
    meaning = closure.signature_meaning(complaint.complaint_identifier, version, len(blocked))
    record = SignedApprovalRecord(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        object_type=closure.OBJECT_TYPE,
        object_id=row.id,
        object_version=f"v{version}",
        decision_type=closure.DECISION_TYPE,
        decision="APPROVED",
        remarks=(reason or "Checklist clear")[:500],
        signer_user_id=me,
        signer_role=person.role_for(QUALITY_REVIEW) or person.account_role or "UNKNOWN",
        signature_meaning=meaning,
        content_fingerprint=print_,
        signature_hash=signature_hash(print_, me, f"v{version}"),
        status="SIGNED",
        signed_at=now,
        created_at=now,
    )
    control_db.add(record)
    control_db.add(
        make_audit_event(
            tenant_id=tenant_id,
            actor_ref=ctx.user_id,
            action="EVENT_READY_TO_CLOSE_SIGNED",
            entity_type=closure.OBJECT_TYPE,
            entity_id=row.id,
            correlation_id=ctx.correlation_id,
            details={
                "complaint": complaint.complaint_identifier,
                "version": version,
                "open_items": len(blocked),
                "signature_id": str(record.id),
                "fingerprint": print_,
            },
            created_at=now,
        )
    )
    row.version, row.ready_state = version, "READY_WITH_REASON" if blocked else "READY"
    row.ready_reason, row.checklist, row.content_fingerprint = reason or None, items, print_
    row.signed_record_id, row.signed_by, row.signed_at, row.updated_at = record.id, me, now, now
    row.qms_filing_ref = row.filed_by = row.filed_at = None  # a new version is filed again
    signing_commit.commit(db, control_db, "event closure")
    return event_view(db, control_db, tenant_id, complaint, me)


class FilingIn(BaseModel):
    reference: str = Field(max_length=closure.FILING_MAX * 2)


@router.put("/events/{complaint_id}/filing", dependencies=[WRITERS])
def record_filing(
    complaint_id: uuid.UUID,
    payload: FilingIn,
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """The QMS reference under which the event decision record was filed (before the QMS closure)."""
    tenant_id = _tenant(ctx)
    complaint = _complaint(db, tenant_id, complaint_id)
    reference = " ".join(payload.reference.split())
    if not 3 <= len(reference) <= closure.FILING_MAX:
        raise _error(422, "REFERENCE_INVALID", f"Give the QMS reference, 3 to {closure.FILING_MAX} characters")
    row = _closure_for_update(db, tenant_id, complaint.id)
    if row.ready_state is None:
        raise _error(409, "NOT_READY", "Sign ready to close first: the record you file is the signed one")
    now = service.now_utc()
    row.qms_filing_ref, row.filed_by, row.filed_at, row.updated_at = reference, str(ctx.user_id), now, now
    _audit(
        db,
        ctx,
        "EVENT_DECISION_RECORD_FILED",
        closure.OBJECT_TYPE,
        row.id,
        complaint=complaint.complaint_identifier,
        reference=reference,
        version=row.version,
    )
    db.commit()
    return event_view(db, control_db, tenant_id, complaint, str(ctx.user_id))


@router.get("/events/{complaint_id}/decision-record.pdf", dependencies=[Depends(require_permission(DATA_EXPORT))])
def decision_record_pdf(
    complaint_id: uuid.UUID,
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    from backend.app.stage3_workflow_router import _organization_name

    tenant_id = _tenant(ctx)
    complaint = _complaint(db, tenant_id, complaint_id)
    view = event_view(db, control_db, tenant_id, complaint, str(ctx.user_id))
    body = closure.render_pdf(view, _organization_name(control_db, tenant_id))
    _audit(
        db,
        ctx,
        "EVENT_DECISION_RECORD_DOWNLOADED",
        closure.OBJECT_TYPE,
        None,
        complaint=complaint.complaint_identifier,
        sha256=view["decision_record"]["sha256"],
    )
    db.commit()
    return Response(
        content=body,
        media_type="application/pdf",
        headers={"Content-Disposition": attachment(f"mdarix-event-record-{complaint.complaint_identifier}.pdf")},
    )
