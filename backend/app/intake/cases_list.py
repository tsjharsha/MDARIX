"""The Cases list (B2 step 5, A5) and every Case's header (A3).

A5: one page of Cases at a time, filtered and searched in SQL, with a fixed number of queries whatever the page size
(no query per row): the page, its count, the per-view counts, then one batched read each for products, lots, checks,
tasks, triage records and people. A3: every open Case says its owner, next action, due time, why, what information is
missing (unconfirmed identifiers included) and its escalation state; a Case is never "done" because a form was sent.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta

from sqlalchemy import String, and_, cast, exists, func, or_
from sqlalchemy.orm import Session

from backend.app.db.models.foundation import Complaint, LotBatch, Product
from backend.app.db.models.intake import FirstContactCheck, IntakeEvent, TriageRecord
from backend.app.db.models.workflow import OPEN_TASK_STATUSES, WorkflowTask
from backend.app.intake import case_rules, rules, service, triage_rules
from backend.app.trial.sample_source import is_sample

C = case_rules
PAGE_MAX = 100
# The list's views (A5 and spec 4.3), each a SQL condition on the Case. "Which cases" first, then the work views.
VIEWS = {
    "all": "All",
    "to_check": "To check",
    "waiting_reporter": "Waiting for the reporter",
    "waiting_internal": "Waiting for internal team",
    "qa_review": "QA review",
    "became_complaints": "Became complaints (30 days)",
    "closed": "Closed",
    "withdrawn": "Withdrawn",
    "mine": "My cases",
    "unassigned": "Unassigned",
    "needs_information": "Needs more information",
    "critical_high": "Critical or high",
    "overdue": "Overdue",
    "service_only": "Service only",
    "potential_complaints": "Potential complaints",
}
LIVE = (C.OPEN, C.PENDING, C.WAITING_INTERNAL, C.IN_REVIEW)
_HIGH = (triage_rules.NOT_KNOWN, "SERIOUS", "CRITICAL", "CATASTROPHIC")
_NEXT = {
    C.OPEN: ("Answer and sign the Case check", "A Case is checked the same working day"),
    C.PENDING: ("Follow up with the reporter", "The Case check is pending: the answers need the reporter"),
    C.WAITING_INTERNAL: ("Chase the internal team", "Waiting for an internal team's answer"),
    C.IN_REVIEW: ("QA review", "A service only, inquiry or not-a-complaint outcome is reviewed by Quality"),
}


def _signed(event_id):
    return and_(
        FirstContactCheck.intake_event_id == event_id,
        FirstContactCheck.signed_at.isnot(None),
        FirstContactCheck.superseded_by.is_(None),
    )


def _condition(view: str, user_id: str, now: datetime):
    """The SQL condition of a view, on IntakeEvent (a correlated EXISTS where it needs another table)."""
    E = IntakeEvent
    triage = exists().where(
        TriageRecord.tenant_id == E.tenant_id,
        TriageRecord.subject_kind == service.INTAKE,
        TriageRecord.subject_id == E.id,
    )
    match view:
        case "to_check":
            return E.status == C.OPEN
        case "waiting_reporter":
            return E.status == C.PENDING
        case "waiting_internal":
            return E.status == C.WAITING_INTERNAL
        case "qa_review":
            return E.status == C.IN_REVIEW
        case "became_complaints":
            return and_(E.status == C.ESCALATED, E.escalated_at >= now - timedelta(days=30))
        case "closed":
            return E.status == C.CLOSED
        case "withdrawn":
            return E.status == C.VOIDED
        case "mine":
            return and_(E.owner_id == str(user_id), E.status.in_(LIVE))
        case "unassigned":
            return and_(E.owner_id.is_(None), E.status.in_(LIVE))
        case "needs_information":
            # shortcut: reads the identifiers' JSON as text (JSONB prints "key": value); a GIN path query if it is slow.
            text = cast(E.identifiers, String)
            return and_(E.status.in_(LIVE), or_(text.like('%"UNCONFIRMED"%'), text.like('%"not_sure": true%')))
        case "critical_high":
            fast = triage.where(or_(TriageRecord.speed == triage_rules.FAST, TriageRecord.severity.in_(_HIGH)))
            return and_(or_(E.kind == "URGENT", fast), E.status.notin_((C.CLOSED, C.VOIDED)))
        case "overdue":
            late = exists().where(
                WorkflowTask.tenant_id == E.tenant_id,
                WorkflowTask.source_entity_type == service.SOURCE_TYPE,
                WorkflowTask.source_entity_id == E.id,
                WorkflowTask.status.in_(OPEN_TASK_STATUSES),
                WorkflowTask.due_at < now,
            )
            # An unsigned Case check is due the same working day: an OPEN Case logged before today is late.
            unsigned = and_(E.status == C.OPEN, E.created_at < now.replace(hour=0, minute=0, second=0, microsecond=0))
            return and_(E.status.in_(LIVE), or_(late, unsigned))
        case "service_only":
            return exists().where(
                FirstContactCheck.tenant_id == E.tenant_id,
                _signed(E.id),
                FirstContactCheck.classification == rules.SERVICE_ONLY,
            )
        case "potential_complaints":
            # Not yet a complaint, but the answers or the words point to one: flagged for triage, or suggested so.
            suggested = exists().where(
                FirstContactCheck.tenant_id == E.tenant_id,
                FirstContactCheck.intake_event_id == E.id,
                FirstContactCheck.signed_at.is_(None),
                FirstContactCheck.suggestion.in_((rules.COMPLAINT, rules.BOTH)),
            )
            return and_(E.status.in_((C.OPEN, C.PENDING, C.WAITING_INTERNAL)), or_(suggested, triage))
    return None


def _search(q: str):
    """Search by reference, product (master or typed), lot, serial number, UDI or customer (site, reporter type)."""
    E = IntakeEvent
    like = f"%{q.replace('%', '').replace('_', '')}%"
    product = exists().where(Product.tenant_id == E.tenant_id, Product.id == E.product_id, Product.name.ilike(like))
    lot = exists().where(
        LotBatch.tenant_id == E.tenant_id, LotBatch.id == E.lot_batch_id, LotBatch.lot_identifier.ilike(like)
    )
    return or_(
        E.reference.ilike(like),
        E.serial_number.ilike(like),
        E.udi.ilike(like),
        E.product_text.ilike(like),
        E.lot_text.ilike(like),
        E.reporter_site.ilike(like),
        E.reporter_type.ilike(like),
        product,
        lot,
    )


def header(
    event: IntakeEvent,
    signed: FirstContactCheck | None,
    answers: dict,
    tasks: list,
    owner: str | None,
    complaint_ref: str | None,
    record: TriageRecord | None,
    check_due: datetime | None,
    now: datetime,
) -> dict:
    """A3: owner, next action, due, reason, missing information and escalation state of one Case."""
    task = min(
        (t for t in tasks if t.status in OPEN_TASK_STATUSES and t.due_at is not None),
        key=lambda t: rules.utc(t.due_at),
        default=None,
    )
    action, reason = _NEXT.get(event.status, (None, None))
    due = rules.utc(task.due_at) if task is not None else check_due if event.status == C.OPEN else None
    if task is not None and event.status != C.OPEN:
        action, reason = task.title, reason
    if event.status == C.OPEN and signed is None and record is not None and record.completed_at is None:
        reason = "On the triage list: safety never waits for the check"
    if event.status == C.ESCALATED:
        state, label = "ESCALATED", f"Became complaint {complaint_ref}" if complaint_ref else "Became a complaint"
    elif event.kind == "URGENT":
        state, label = "URGENT", "Urgent: a complaint at once"
    elif record is not None and record.completed_at is None:
        state, label = (
            "TRIAGE",
            f"On the triage list ({triage_rules.SPEED_LABELS.get(record.speed or '', 'to triage')})",
        )
    elif record is not None:
        state, label = "TRIAGED", "Triaged"
    else:
        state, label = "NONE", "Not escalated"
    return {
        "owner": owner,
        "next_action": action,
        "due_at": service._iso(due),
        "overdue": bool(due and due < now and event.status in LIVE),
        "reason": reason,
        "missing": C.missing_information(event.identifiers or {}, answers),
        "escalation": {
            "state": state,
            "label": label,
            "complaint_id": str(event.complaint_id) if event.complaint_id else None,
        },
    }


def cases_page(
    db: Session,
    control_db: Session | None,
    tenant_id: uuid.UUID,
    user_id: str,
    view: str = "all",
    q: str = "",
    page: int = 1,
    size: int = 25,
    now: datetime | None = None,
) -> dict:
    now = now or service.now_utc()
    E = IntakeEvent
    size = max(1, min(size, PAGE_MAX))
    base = db.query(E).filter(E.tenant_id == tenant_id)
    q = rules.clean(q, 80)
    if q:
        base = base.filter(_search(q))
    condition = _condition(view, user_id, now)
    shown = base.filter(condition) if condition is not None else base
    total = shown.order_by(None).count()
    events = shown.order_by(E.created_at.desc(), E.id.desc()).offset((max(page, 1) - 1) * size).limit(size).all()
    # The counts of "Which cases" in one grouped read (the same search applied).
    by_status = dict(base.order_by(None).with_entities(E.status, func.count()).group_by(E.status).all())
    ids = [event.id for event in events]
    products = _by_id(db, Product, tenant_id, {e.product_id for e in events})
    lots = _by_id(db, LotBatch, tenant_id, {e.lot_batch_id for e in events})
    complaints = _by_id(db, Complaint, tenant_id, {e.complaint_id for e in events})
    checks = service.checks_of(db, tenant_id, ids)
    tasks = service.tasks_of(db, tenant_id, ids)
    records = {
        row.subject_id: row
        for row in db.query(TriageRecord).filter(
            TriageRecord.tenant_id == tenant_id,
            TriageRecord.subject_kind == service.INTAKE,
            TriageRecord.subject_id.in_(ids or [uuid.uuid4()]),
        )
    }
    names = service.names_of(control_db, tenant_id, {e.owner_id for e in events})
    calendar = service.calendar(db, tenant_id)
    items = []
    for event in events:
        versions = checks.get(event.id, [])
        latest = versions[-1] if versions else None
        signed = service.current_signed(versions)
        answers = latest.answers if latest else {}
        product, lot, complaint = (
            products.get(event.product_id),
            lots.get(event.lot_batch_id),
            complaints.get(event.complaint_id),
        )
        check_due = service.working_day_end(rules.utc(event.created_at), 0, calendar) if signed is None else None
        owner = names.get(event.owner_id) if event.owner_id else None
        items.append(
            {
                "id": str(event.id),
                "reference": event.reference,
                "kind": event.kind,
                "sample": is_sample(event.source_system),
                "received_at": service._iso(event.received_at or event.created_at),
                "words": (event.reporter_words or "")[:200],
                "product_name": product.name if product else event.product_text,
                "lot": lot.lot_identifier if lot else event.lot_text,
                "not_in_master": [
                    k for k, typed in (("product", event.product_text), ("lot", event.lot_text)) if typed
                ],
                "status": event.status,
                "status_label": C.STATE_LABELS.get(event.status),
                "classification": signed.classification if signed else None,
                "classification_label": C.OUTCOME_LABELS.get(signed.classification) if signed else None,
                "suggestion_label": C.OUTCOME_LABELS.get(latest.suggestion) if latest and not signed else None,
                "issue_category_label": C.ISSUE_CATEGORIES.get(event.issue_category or ""),
                "flagged": bool(rules.intake_flags(event.kind, event.reporter_words, answers)),
                "complaint_ref": complaint.complaint_identifier if complaint else None,
                "row_version": event.version,
                "header": header(
                    event,
                    signed,
                    answers,
                    tasks.get(event.id, []),
                    owner,
                    complaint.complaint_identifier if complaint else None,
                    records.get(event.id),
                    check_due,
                    now,
                ),
            }
        )
    return {
        "items": items,
        "total": total,
        "page": max(page, 1),
        "size": size,
        "view": view,
        "views": [{"code": code, "label": label} for code, label in VIEWS.items()],
        # Who a Case may be assigned to (bulk "Assign to…", CI-36).
        "people": service.colleagues(control_db, tenant_id),
        "counts": {**{state: by_status.get(state, 0) for state in C.STATES}, "all": sum(by_status.values())},
    }


def _by_id(db: Session, model, tenant_id: uuid.UUID, ids: set) -> dict:
    wanted = [value for value in ids if value]
    if not wanted:
        return {}
    return {row.id: row for row in db.query(model).filter(model.tenant_id == tenant_id, model.id.in_(wanted))}
