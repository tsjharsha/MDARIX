"""Reading the records for the second look and the backlog board (rules.py decides; this module only reads).

Both read the organization's data plane (backend/app/db/data_plane.py), so they work the same on the shared database
and on a dedicated one. Neither changes a complaint.
"""

from __future__ import annotations

import uuid
from collections import Counter
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import any_, exists, func, or_
from sqlalchemy.dialects.postgresql import array
from sqlalchemy.orm import Session

from backend.app.complaint_review import rules
from backend.app.db.models.complaint_disposition import ComplaintDisposition
from backend.app.db.models.complaint_review import ComplaintSecondLook, ComplaintSettings
from backend.app.db.models.foundation import AuthUser, Complaint, InvestigationComplaint, Product, ProductVersion
from backend.app.db.models.signals import SignalComplaint

# When a complaint was received: the quality system's date, else the event date, else when MDARIX recorded it.
RECEIVED_AT = func.coalesce(Complaint.complaint_timestamp, Complaint.event_timestamp, Complaint.created_at)
# At most this many records are read for one screen; the screen says so when there were more.
READ_LIMIT = 20000


def today_utc() -> date:
    return datetime.now(timezone.utc).date()


def _day(value) -> date | None:
    if value is None:
        return None
    return value.date() if isinstance(value, datetime) else value


def settings_of(db: Session, tenant_id: uuid.UUID, control_db: Session | None = None) -> dict:
    """The organization's settings; with ``control_db`` also who last changed them, by name (never their user id)."""
    row = db.query(ComplaintSettings).filter(ComplaintSettings.tenant_id == tenant_id).first()
    custom = row is not None and row.second_look_words is not None
    editor = row.updated_by if row else None
    names = people(control_db, tenant_id, [editor]) if editor and control_db is not None else {}
    return {
        "backlog_target_days": row.backlog_target_days if row else rules.DEFAULT_TARGET_DAYS,
        "second_look_words": rules.clean_words(row.second_look_words) if custom else list(rules.DEFAULT_WORDS),
        "custom_words": custom,
        "default_words": list(rules.DEFAULT_WORDS),
        "version": row.version if row else 0,
        "updated_by": editor,
        "updated_by_name": (names.get(editor) or "A colleague") if editor else None,
        "updated_at": row.updated_at.isoformat() if row and row.updated_at else None,
    }


def _same_organization(column):
    """``column`` (a link's organization) is the complaint's, written so that PostgreSQL can only use it to look up each
    complaint's links by organization and complaint at once (0.10.42). As a plain equality it joins the organization
    of the outer query, and while the planner's statistics do not know a new organization's rows yet (until autovacuum
    analyzes the tables, after a large import) it read every link of the organization for every complaint: 10 s and
    more for one import's backlog check, on the trial's story and Readiness."""
    return column == any_(array([Complaint.tenant_id]))


def _records(db: Session, tenant_id: uuid.UUID):
    """Complaints with their product's name and version (a complaint without a product is still read)."""
    return (
        db.query(Complaint, Product.name, ProductVersion.version_identifier, RECEIVED_AT)
        .outerjoin(Product, (Product.id == Complaint.product_id) & (Product.tenant_id == Complaint.tenant_id))
        .outerjoin(
            ProductVersion,
            (ProductVersion.id == Complaint.product_version_id) & (ProductVersion.tenant_id == Complaint.tenant_id),
        )
        .filter(Complaint.tenant_id == tenant_id)
    )


def record_of(complaint: Complaint, product_name, version, received) -> dict:
    """What the rules read and what the screens show of one complaint."""
    return {
        "id": str(complaint.id),
        "business_id": complaint.business_id,
        "complaint_identifier": complaint.complaint_identifier,
        "product_id": str(complaint.product_id) if complaint.product_id else None,
        "product_name": product_name,
        "version": version,
        "status": complaint.status,
        "complaint_type": complaint.complaint_type,
        "problem_code": complaint.problem_code,
        "severity": complaint.severity,
        "description": complaint.description,
        "received_date": _day(received).isoformat() if _day(received) else None,
        "awareness_date": complaint.awareness_timestamp.date().isoformat() if complaint.awareness_timestamp else None,
        "patient_involved": complaint.patient_involved,
        "serious_injury": complaint.serious_injury,
        "death": complaint.death,
        "malfunction": complaint.malfunction,
        "source_system": complaint.source_system,
    }


def _decisions(db: Session, tenant_id: uuid.UUID, ids) -> dict[uuid.UUID, ComplaintSecondLook]:
    ids = list(ids)
    if not ids:
        return {}
    rows = (
        db.query(ComplaintSecondLook)
        .filter(ComplaintSecondLook.tenant_id == tenant_id, ComplaintSecondLook.complaint_id.in_(ids))
        .all()
    )
    return {row.complaint_id: row for row in rows}


def people(control_db: Session | None, tenant_id: uuid.UUID, refs) -> dict[str, str]:
    """``{user id: name people read}`` for the deciders among ``refs``; empty when the names cannot be read, so a
    screen never fails because of a name."""
    wanted = []
    for ref in refs:
        try:
            wanted.append(uuid.UUID(str(ref)))
        except (TypeError, ValueError):
            continue
    if control_db is None or not wanted:
        return {}
    try:
        rows = (
            control_db.query(AuthUser.id, AuthUser.display_name, AuthUser.username)
            .filter(AuthUser.tenant_id == tenant_id, AuthUser.id.in_(wanted))
            .all()
        )
    except Exception:
        return {}
    return {str(row.id): row.display_name or row.username for row in rows}


def decision_of(row: ComplaintSecondLook | None, names: dict[str, str]) -> dict | None:
    if row is None:
        return None
    return {
        "decision": row.decision,
        "reason": row.reason,
        "decided_by": names.get(row.decided_by) or "A colleague",
        "decided_at": row.decided_at.isoformat() if row.decided_at else None,
    }


def _nff_counts(records: list[dict], today: date) -> Counter:
    """How many records of each product carry each No Fault Found / User Error family within the window."""
    since = today - timedelta(days=rules.NFF_WINDOW_DAYS)
    counts: Counter = Counter()
    for record in records:
        family = rules.nff_family(record["problem_code"], record["complaint_type"], record["status"])
        received = date.fromisoformat(record["received_date"]) if record["received_date"] else None
        if family and received and received >= since:
            counts[(record["product_id"], family)] += 1
    return counts


def _nff_count_for(record: dict, counts: Counter, today: date) -> int:
    family = rules.nff_family(record["problem_code"], record["complaint_type"], record["status"])
    received = date.fromisoformat(record["received_date"]) if record["received_date"] else None
    if not family or not received or received < today - timedelta(days=rules.NFF_WINDOW_DAYS):
        return 0
    return counts[(record["product_id"], family)]


def _candidates(db: Session, tenant_id: uuid.UUID, product_id: uuid.UUID | None = None):
    """The database's broad first filter: a status, type or code that may mean cancelled, an inquiry or service
    record, or No Fault Found / User Error. rules.flag then decides exactly."""
    columns = (Complaint.status, Complaint.complaint_type, Complaint.problem_code)
    patterns = [
        func.lower(func.coalesce(column, "")).like(pattern)
        for column in columns
        for pattern in rules.CANDIDATE_PATTERNS
    ]
    query = _records(db, tenant_id).filter(or_(*patterns))
    if product_id:
        query = query.filter(Complaint.product_id == product_id)
    return query


def second_look(
    db: Session,
    control_db: Session | None,
    tenant_id: uuid.UUID,
    *,
    state: str = "open",
    product_id: uuid.UUID | None = None,
    page: int = 1,
    page_size: int = 25,
    today: date | None = None,
) -> dict:
    """The records worth a second look (``state=open``: not decided yet; ``decided``: decided), most serious first,
    with a summary of everything flagged."""
    today = today or today_utc()
    words = settings_of(db, tenant_id)["second_look_words"]
    rows = _candidates(db, tenant_id, product_id).order_by(RECEIVED_AT.desc(), Complaint.id).limit(READ_LIMIT + 1).all()
    truncated = len(rows) > READ_LIMIT
    records = [record_of(*row) for row in rows[:READ_LIMIT]]
    counts = _nff_counts(records, today)
    flagged = []
    for record in records:
        result = rules.flag(record, words, _nff_count_for(record, counts, today))
        if result:
            flagged.append((record, result))
    decisions = _decisions(db, tenant_id, (uuid.UUID(record["id"]) for record, _ in flagged))
    names = people(control_db, tenant_id, (row.decided_by for row in decisions.values()))
    open_items, decided_items = [], []
    for record, result in flagged:
        decided = decisions.get(uuid.UUID(record["id"]))
        item = {**record, **result.as_dict(), "decision": decision_of(decided, names)}
        (decided_items if decided else open_items).append(item)
    open_items.sort(key=lambda item: (-item["score"], item["received_date"] or ""), reverse=False)
    decided_items.sort(key=lambda item: item["decision"]["decided_at"] or "", reverse=True)
    by_reason = Counter(reason["code"] for item in open_items for reason in item["reasons"])
    summary = {
        "to_review": len(open_items),
        "with_harm": sum(
            1 for item in open_items if any(sign["code"] in {"DEATH", "SERIOUS_INJURY"} for sign in item["signs"])
        ),
        "confirmed": sum(1 for item in decided_items if item["decision"]["decision"] == "CONFIRMED"),
        "dismissed": sum(1 for item in decided_items if item["decision"]["decision"] == "DISMISSED"),
        "by_reason": {code: by_reason.get(code, 0) for code in (rules.CANCELLED, rules.INQUIRY, rules.NFF_RECURRING)},
    }
    chosen = decided_items if state == "decided" else open_items
    start = (page - 1) * page_size
    return {
        "summary": summary,
        "state": "decided" if state == "decided" else "open",
        "total": len(chosen),
        "page": page,
        "page_size": page_size,
        "pages": max(1, -(-len(chosen) // page_size)),
        "truncated": truncated,
        "items": chosen[start : start + page_size],
    }


def assess(db: Session, tenant_id: uuid.UUID, complaint_id: uuid.UUID, today: date | None = None):
    """One complaint and what the second look sees in it now: (record, Flag or None); (None, None) when the
    organization has no such complaint."""
    today = today or today_utc()
    row = _records(db, tenant_id).filter(Complaint.id == complaint_id).first()
    if row is None:
        return None, None
    record = record_of(*row)
    words = settings_of(db, tenant_id)["second_look_words"]
    count = 0
    if rules.nff_family(record["problem_code"], record["complaint_type"], record["status"]):
        product = uuid.UUID(record["product_id"]) if record["product_id"] else None
        same = [record_of(*item) for item in _candidates(db, tenant_id, product).limit(READ_LIMIT).all()]
        if product is None:
            same = [item for item in same if item["product_id"] is None]
        count = _nff_count_for(record, _nff_counts(same, today), today)
    return record, rules.flag(record, words, count)


def backlog(
    db: Session,
    tenant_id: uuid.UUID,
    *,
    show: str = "all",
    product_id: uuid.UUID | None = None,
    page: int = 1,
    page_size: int = 25,
    today: date | None = None,
) -> dict:
    """Open complaints that are in no signal and no case and not resolved by a signed disposition, oldest first,
    against the organization's target days.

    The board is counted from a few columns of each complaint; only the page shown reads the whole records. After a
    large import thousands of complaints are open, and reading every one whole (with all its timestamps, which the
    database driver parses in Python) was most of the time of Readiness and of the trial's story (0.10.43)."""
    today = today or today_utc()
    target = settings_of(db, tenant_id)["backlog_target_days"]
    in_signal = exists().where(
        _same_organization(SignalComplaint.tenant_id), SignalComplaint.complaint_id == Complaint.id
    )
    in_case = exists().where(
        _same_organization(InvestigationComplaint.tenant_id), InvestigationComplaint.complaint_id == Complaint.id
    )
    # A signed service-level or known-issue disposition (tr02) takes the complaint off the board.
    resolved = exists().where(
        _same_organization(ComplaintDisposition.tenant_id),
        ComplaintDisposition.complaint_id == Complaint.id,
        ComplaintDisposition.superseded_by.is_(None),
        ComplaintDisposition.branch.in_(("SERVICE_LEVEL", "KNOWN_ISSUE")),
    )
    query = (
        db.query(Complaint.id, Complaint.status, Complaint.complaint_type, ComplaintSecondLook.decision, RECEIVED_AT)
        .outerjoin(
            ComplaintSecondLook,
            (ComplaintSecondLook.complaint_id == Complaint.id) & (ComplaintSecondLook.tenant_id == Complaint.tenant_id),
        )
        .filter(Complaint.tenant_id == tenant_id, ~in_signal, ~in_case, ~resolved)
    )
    if product_id:
        query = query.filter(Complaint.product_id == product_id)
    rows = query.order_by(RECEIVED_AT.asc(), Complaint.id).limit(READ_LIMIT + 1).all()
    truncated = len(rows) > READ_LIMIT
    items = []
    for complaint_id, status, complaint_type, decision, received in rows[:READ_LIMIT]:
        if not rules.counts_as_open(status, complaint_type, decision):
            continue
        age = rules.age_days(_day(received), today)
        if age is None:
            continue
        items.append(
            {
                "id": str(complaint_id),
                "age_days": age,
                "days_past_target": max(0, age - target),
                "state": rules.backlog_state(age, target),
                "band": rules.age_band(age),
                "confirmed_on_second_look": decision == "CONFIRMED",
            }
        )
    items.sort(key=lambda item: (-item["age_days"], item["id"]))
    states = Counter(item["state"] for item in items)
    bands = Counter(item["band"] for item in items)
    summary = {
        "target_days": target,
        "open_unlinked": len(items),
        "past_target": states.get("PAST_TARGET", 0),
        "due_soon": states.get("DUE_SOON", 0),
        "on_track": states.get("ON_TRACK", 0),
        "oldest_days": items[0]["age_days"] if items else None,
        "bands": [{"band": name, "count": bands.get(name, 0)} for name, _, _ in rules.AGE_BANDS],
    }
    wanted = {"past_target": "PAST_TARGET", "due_soon": "DUE_SOON"}.get(show)
    chosen = [item for item in items if item["state"] == wanted] if wanted else items
    start = (page - 1) * page_size
    shown = chosen[start : start + page_size]
    records = _records_by_id(db, tenant_id, [uuid.UUID(item["id"]) for item in shown])
    return {
        "summary": summary,
        "show": show if wanted else "all",
        "total": len(chosen),
        "page": page,
        "page_size": page_size,
        "pages": max(1, -(-len(chosen) // page_size)),
        "truncated": truncated,
        # Each complaint shown whole, then what the board says of it (a complaint deleted meanwhile is left out).
        "items": [{**records[item["id"]], **item} for item in shown if item["id"] in records],
    }


# At most this many complaints are read whole by one statement (the driver sends one parameter per id).
RECORDS_CHUNK = 5000


def _records_by_id(db: Session, tenant_id: uuid.UUID, ids: list[uuid.UUID]) -> dict[str, dict]:
    """``{complaint id: record_of(...)}`` of these complaints of the organization."""
    found: dict[str, dict] = {}
    for start in range(0, len(ids), RECORDS_CHUNK):
        for row in _records(db, tenant_id).filter(Complaint.id.in_(ids[start : start + RECORDS_CHUNK])).all():
            record = record_of(*row)
            found[record["id"]] = record
    return found
