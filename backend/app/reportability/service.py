"""Reading the reportability watch (rules.py decides; this module only reads).

It reads the organization's data plane, so it works the same on the shared database and on a dedicated one. It never
changes a complaint and never submits anything.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from backend.app.complaint_review import rules as review_rules
from backend.app.complaint_review.service import people
from backend.app.db.models.complaint_review import ComplaintSecondLook
from backend.app.db.models.foundation import Complaint, Investigation, InvestigationComplaint, Product, ProductVersion
from backend.app.db.models.reportability import ComplaintReportability, ReportabilitySettings
from backend.app.db.models.reviews import CaseReview
from backend.app.reportability import rules

# When the organization became aware, for the database's first filter (rules then take the earliest of the three).
AWARE_AT = func.coalesce(Complaint.awareness_timestamp, Complaint.complaint_timestamp, Complaint.recorded_timestamp)
READ_LIMIT = 20000
SHOWS = ("open", "overdue", "due_soon", "follow_up", "decided", "all")


def today_utc() -> date:
    return datetime.now(timezone.utc).date()


def _day(value) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        moment = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        return moment.astimezone(timezone.utc).date()
    return value


def settings_of(db: Session, tenant_id: uuid.UUID, control_db: Session | None = None) -> dict:
    """The organization's reporting windows (none until someone enters them), with the templates to start from."""
    row = db.query(ReportabilitySettings).filter(ReportabilitySettings.tenant_id == tenant_id).first()
    windows = [rules.clean_window(item) for item in (row.windows if row else None) or []]
    editor = row.updated_by if row else None
    names = people(control_db, tenant_id, [editor]) if editor and control_db is not None else {}
    return {
        "windows": windows,
        "lookback_days": row.lookback_days if row else rules.LOOKBACK_DEFAULT,
        "configured": bool(windows),
        "templates": [rules.clean_window(item) for item in rules.TEMPLATES],
        "triggers": [{"code": code, "label": rules.TRIGGER_LABELS[code]} for code in rules.TRIGGERS],
        "version": row.version if row else 0,
        "updated_by": editor,
        "updated_by_name": (names.get(editor) or "A colleague") if editor else None,
        "updated_at": row.updated_at.isoformat() if row and row.updated_at else None,
    }


def awareness(complaint: Complaint) -> tuple[date | None, str | None]:
    """The day the organization became aware: the earliest of the awareness, received and recorded days (as the case's
    regulatory review reads it; the earliest only ever makes a due date earlier), and which of them it is."""
    days = [
        (_day(complaint.awareness_timestamp), "AWARENESS_DATE"),
        (_day(complaint.complaint_timestamp), "RECEIVED_DATE"),
        (_day(complaint.recorded_timestamp), "RECORDED_DATE"),
    ]
    known = [(day, source) for day, source in days if day is not None]
    if not known:
        return None, None
    earliest = min(day for day, _ in known)
    return earliest, next(source for day, source in known if day == earliest)


def _record(complaint: Complaint, product_name, version) -> dict:
    return {
        "id": str(complaint.id),
        "business_id": complaint.business_id,
        "complaint_identifier": complaint.complaint_identifier,
        "product_id": str(complaint.product_id) if complaint.product_id else None,
        "product_name": product_name,
        "version": version,
        "status": complaint.status,
        "complaint_type": complaint.complaint_type,
        "description": complaint.description,
        "country": complaint.country,
        "severity": complaint.severity,
        "problem_code": complaint.problem_code,
        "received_date": _day(complaint.complaint_timestamp).isoformat() if complaint.complaint_timestamp else None,
        "patient_involved": complaint.patient_involved,
        "serious_injury": complaint.serious_injury,
        "death": complaint.death,
        "malfunction": complaint.malfunction,
    }


def _case_reviews(db: Session, tenant_id: uuid.UUID, complaint_ids: list[uuid.UUID]) -> dict[uuid.UUID, dict]:
    """For each complaint in a case, the case and the latest regulatory review of it (if any)."""
    found: dict[uuid.UUID, dict] = {}
    if not complaint_ids:
        return found
    links = (
        db.query(InvestigationComplaint.complaint_id, Investigation.id, Investigation.business_id)
        .join(
            Investigation,
            (Investigation.tenant_id == InvestigationComplaint.tenant_id)
            & (Investigation.id == InvestigationComplaint.investigation_id),
        )
        .filter(InvestigationComplaint.tenant_id == tenant_id, InvestigationComplaint.complaint_id.in_(complaint_ids))
        .all()
    )
    case_ids = {case_id for _, case_id, _ in links}
    reviews: dict[uuid.UUID, CaseReview] = {}
    if case_ids:
        for review in (
            db.query(CaseReview)
            .filter(
                CaseReview.tenant_id == tenant_id,
                CaseReview.investigation_id.in_(case_ids),
                CaseReview.review_type == "REGULATORY",
                CaseReview.status.in_(["REQUESTED", "IN_PROGRESS", "COMPLETED"]),
            )
            .order_by(CaseReview.created_at)
            .all()
        ):
            reviews[review.investigation_id] = review  # the latest one wins
    for complaint_id, case_id, case_business_id in links:
        review = reviews.get(case_id)
        entry = {
            "case": {"id": str(case_id), "business_id": case_business_id},
            "review": (
                {
                    "id": str(review.id),
                    "business_id": review.business_id,
                    "status": review.status,
                    "outcome": review.outcome,
                    "completed_at": review.completed_at.isoformat() if review.completed_at else None,
                }
                if review is not None
                else None
            ),
        }
        current = found.get(complaint_id)
        # A complaint in several cases: a case with a review is more telling than one without.
        if current is None or (current["review"] is None and entry["review"] is not None):
            found[complaint_id] = entry
    return found


def decision_view(row: ComplaintReportability | None, names: dict[str, str]) -> dict | None:
    if row is None:
        return None
    decided_on = row.reported_on if row.decision == rules.REPORTED else _day(row.decided_at)
    return {
        "decision": row.decision,
        "rationale": row.rationale,
        "report_reference": row.report_reference,
        "reported_on": row.reported_on.isoformat() if row.reported_on else None,
        "window": row.window_name,
        "due_on": row.due_on.isoformat() if row.due_on else None,
        "on_time": rules.on_time(decided_on, row.due_on),
        "decided_by": names.get(row.decided_by) or "A colleague",
        "decided_at": row.decided_at.isoformat() if row.decided_at else None,
    }


def assess(complaint: Complaint, record: dict, windows: list[dict], case: dict | None, today: date) -> dict:
    """What the watch shows for one complaint (without the person's decision)."""
    aware, source = awareness(complaint)
    clock_list = rules.clocks(record, windows, aware, today)
    review = (case or {}).get("review")
    settled = bool(review and review["status"] == "COMPLETED" and review["outcome"] in rules.SETTLING_OUTCOMES)
    in_review = bool(review and review["status"] in ("REQUESTED", "IN_PROGRESS"))
    return {
        "aware_date": aware.isoformat() if aware else None,
        "aware_source": source,
        "days_since_aware": (today - aware).days if aware else None,
        "triggers": rules.triggers_of(record),
        "clocks": [clock.as_dict() for clock in clock_list],
        "binding": clock_list[0].as_dict() if clock_list else None,
        "follow_ups": rules.follow_ups(record, windows, complaint.awareness_timestamp is not None),
        "case": case,
        "settled_by_case": settled,
        "in_review": in_review,
    }


def _rows(db: Session, tenant_id: uuid.UUID, since: date, product_id: uuid.UUID | None):
    query = (
        db.query(Complaint, Product.name, ProductVersion.version_identifier, ComplaintSecondLook.decision)
        .outerjoin(Product, (Product.tenant_id == Complaint.tenant_id) & (Product.id == Complaint.product_id))
        .outerjoin(
            ProductVersion,
            (ProductVersion.tenant_id == Complaint.tenant_id) & (ProductVersion.id == Complaint.product_version_id),
        )
        .outerjoin(
            ComplaintSecondLook,
            (ComplaintSecondLook.tenant_id == Complaint.tenant_id) & (ComplaintSecondLook.complaint_id == Complaint.id),
        )
        .filter(
            Complaint.tenant_id == tenant_id,
            or_(
                Complaint.death.is_(True),
                Complaint.serious_injury.is_(True),
                Complaint.malfunction.is_(True),
                Complaint.patient_involved.is_(True),
            ),
            or_(AWARE_AT.is_(None), AWARE_AT >= datetime.combine(since, datetime.min.time(), tzinfo=timezone.utc)),
        )
    )
    if product_id:
        query = query.filter(Complaint.product_id == product_id)
    return query.order_by(AWARE_AT.asc(), Complaint.id).limit(READ_LIMIT + 1).all()


def counts_as_complaint(status, complaint_type, second_look: str | None) -> bool:
    """A record the watch follows: not dismissed on the second look, and not a cancelled record or inquiry unless a
    person confirmed it is a complaint (until then it waits on the second look). A closed complaint is followed: closing
    it does not settle whether it had to be reported."""
    if second_look == "DISMISSED":
        return False
    if second_look == "CONFIRMED":
        return True
    return not review_rules.is_cancelled(status) and not review_rules.is_inquiry(status, complaint_type)


def watch(
    db: Session,
    control_db: Session | None,
    tenant_id: uuid.UUID,
    *,
    show: str = "open",
    product_id: uuid.UUID | None = None,
    page: int = 1,
    page_size: int = 25,
    today: date | None = None,
) -> dict:
    """The complaints whose reportability needs a person's decision, most urgent first, with a summary."""
    today = today or today_utc()
    settings = settings_of(db, tenant_id)
    windows = settings["windows"]
    since = today - timedelta(days=settings["lookback_days"])
    rows = _rows(db, tenant_id, since, product_id)
    truncated = len(rows) > READ_LIMIT
    candidates = []
    held_on_second_look = 0
    for complaint, product_name, version, second_look in rows[:READ_LIMIT]:
        record = _record(complaint, product_name, version)
        if not rules.watched(record):
            continue
        aware, _ = awareness(complaint)
        if aware is not None and aware < since:
            continue
        if not counts_as_complaint(complaint.status, complaint.complaint_type, second_look):
            if second_look is None and rules.triggers_of(record):
                held_on_second_look += 1
            continue
        candidates.append((complaint, record))
    ids = [complaint.id for complaint, _ in candidates]
    cases = _case_reviews(db, tenant_id, ids)
    decisions = {
        row.complaint_id: row
        for row in (
            db.query(ComplaintReportability)
            .filter(ComplaintReportability.tenant_id == tenant_id, ComplaintReportability.complaint_id.in_(ids))
            .all()
            if ids
            else []
        )
    }
    names = people(control_db, tenant_id, (row.decided_by for row in decisions.values()))
    items = []
    for complaint, record in candidates:
        seen = assess(complaint, record, windows, cases.get(complaint.id), today)
        decided = decisions.get(complaint.id)
        is_decided = decided is not None or seen["settled_by_case"]
        state = rules.watch_state(
            seen["binding"]["state"] if seen["binding"] else None,
            is_decided,
            seen["in_review"],
            bool(seen["triggers"]),
        )
        items.append({**record, **seen, "state": state, "decision": decision_view(decided, names)})

    def urgency(item: dict):
        binding = item["binding"]
        return (
            rules.STATE_ORDER.get(item["state"], 9),
            binding["due_date"] if binding else "9999-12-31",
            item["aware_date"] or "9999-12-31",
            item["business_id"] or "",
        )

    items.sort(key=urgency)
    undecided = [item for item in items if item["state"] != rules.DECIDED]
    decided_items = [item for item in items if item["state"] == rules.DECIDED]
    decided_rows = [item["decision"] for item in decided_items if item["decision"]]
    summary = {
        "configured": settings["configured"],
        "windows": len(windows),
        "lookback_days": settings["lookback_days"],
        "open": len(undecided),
        "overdue": sum(1 for item in undecided if item["state"] == rules.OVERDUE),
        "due_soon": sum(1 for item in undecided if item["state"] == rules.DUE_SOON),
        "running": sum(1 for item in undecided if item["binding"]),
        "in_review": sum(1 for item in undecided if item["in_review"]),
        "follow_up": sum(1 for item in undecided if item["follow_ups"]),
        "no_window": sum(1 for item in undecided if item["state"] == rules.NO_WINDOW),
        "decided": len(decided_items),
        "decided_in_window": sum(1 for row in decided_rows if row["on_time"] is True),
        "decided_late": sum(1 for row in decided_rows if row["on_time"] is False),
        "held_on_second_look": held_on_second_look,
    }
    chosen = {
        "open": undecided,
        "overdue": [item for item in undecided if item["state"] == rules.OVERDUE],
        "due_soon": [item for item in undecided if item["state"] == rules.DUE_SOON],
        "follow_up": [item for item in undecided if item["follow_ups"]],
        "decided": sorted(
            decided_items, key=lambda item: (item["decision"] or {}).get("decided_at") or "", reverse=True
        ),
        "all": items,
    }[show if show in SHOWS else "open"]
    start = (page - 1) * page_size
    return {
        "summary": summary,
        "show": show if show in SHOWS else "open",
        "total": len(chosen),
        "page": page,
        "page_size": page_size,
        "pages": max(1, -(-len(chosen) // page_size)),
        "truncated": truncated,
        "items": chosen[start : start + page_size],
    }


def one(db: Session, tenant_id: uuid.UUID, complaint_id: uuid.UUID, today: date | None = None):
    """``(complaint, record, assessment, second-look decision)`` for one complaint, or None when it does not exist."""
    today = today or today_utc()
    row = (
        db.query(Complaint, Product.name, ProductVersion.version_identifier, ComplaintSecondLook.decision)
        .outerjoin(Product, (Product.tenant_id == Complaint.tenant_id) & (Product.id == Complaint.product_id))
        .outerjoin(
            ProductVersion,
            (ProductVersion.tenant_id == Complaint.tenant_id) & (ProductVersion.id == Complaint.product_version_id),
        )
        .outerjoin(
            ComplaintSecondLook,
            (ComplaintSecondLook.tenant_id == Complaint.tenant_id) & (ComplaintSecondLook.complaint_id == Complaint.id),
        )
        .filter(Complaint.tenant_id == tenant_id, Complaint.id == complaint_id)
        .first()
    )
    if row is None:
        return None
    complaint, product_name, version, second_look = row
    record = _record(complaint, product_name, version)
    windows = settings_of(db, tenant_id)["windows"]
    seen = assess(complaint, record, windows, _case_reviews(db, tenant_id, [complaint.id]).get(complaint.id), today)
    return complaint, record, seen, second_look
