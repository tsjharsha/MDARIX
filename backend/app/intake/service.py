"""Reading and writing the first contact, triage and duplicates (rules.py decides; this module reads the records and
keeps the tasks).

It reads the organization's data plane, so it works the same on the shared database and on a dedicated one. It never
changes an imported complaint.

- **One event, several sources.** Records a person linked (``record_links`` LINKED) are one event; the event uses the
  earliest awareness among its sources (G20), and every clock counted from awareness is recomputed from it, the
  reportability watch's included (``linked_awareness``).
- **The triage list** (``triage``) shows, before every other queue, each event that is flagged or escalated by hand and
  not yet triaged: urgent intakes, flagged contacts, flagged imported complaints and set-aside rows that suggest harm
  (T-R14), and any event whose new link raised an "awareness conflict".
- **Tasks** are ``workflow_tasks`` of the intake event: the follow-up with the reporter (since T-G30 also a request in
  the communications log, linked to the task), the QMS-complaint
  task and the QA review of a "service only".
"""

from __future__ import annotations

import time
import uuid
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import event as sa_event, or_
from sqlalchemy.orm import Session

from backend.app.trial.sample_source import is_sample
from backend.app.complaint_review import rules as review_rules
from backend.app.db.models.complaint_disposition import ComplaintDisposition
from backend.app.db.models.complaint_review import ComplaintSecondLook
from backend.app.db.models.foundation import AuthUser, Complaint, InvestigationComplaint, LotBatch, Product
from backend.app.db.models.ingestion import ImportQuarantineRow
from backend.app.db.models.intake import FirstContactCheck, IntakeEvent, RecordFieldChange, RecordLink, TriageRecord
from backend.app.db.models.workflow import OPEN_TASK_STATUSES, WorkflowTask
from backend.app.intake import case_rules, rules, triage_rules
from backend.app.reportability import markets
from backend.app.reportability.deadlines import day_only
from backend.app.business_ids import complaint_ref

SOURCE_TYPE = "IntakeEvent"
FOLLOW_UP, QMS, REVIEW = "FIRST_CONTACT_FOLLOW_UP", "QMS_COMPLAINT", "SERVICE_ONLY_REVIEW"
TASK_TYPES = (FOLLOW_UP, QMS, REVIEW)
INTAKE, COMPLAINT, QUARANTINE = "INTAKE", "COMPLAINT", "QUARANTINE"
READ_LIMIT = 2000
AWAITING_IMPORT = "Awaiting import confirmation"


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def working_day_end(moment: datetime, days: int = 0, calendar=None) -> datetime:
    """The end of the working day ``days`` working days after ``moment``, on the organization's working calendar
    (``calendar``, backend/app/oversight/rules.py; the default is Monday to Friday in UTC). Day 0 is the same day, or
    the next working day when ``moment`` falls on a day off."""
    from backend.app.oversight.rules import Calendar

    return (calendar or Calendar()).working_day_end(moment, days)


def calendar(db: Session, tenant_id):
    from backend.app.oversight.service import calendar_of

    return calendar_of(db, tenant_id)


def _iso(value) -> str | None:
    return value.isoformat() if value is not None else None


def enabled_markets(db: Session, tenant_id: uuid.UUID) -> list[str]:
    from backend.app.reportability import service as reporting_service

    return markets.enabled_markets(reporting_service.settings_of(db, tenant_id)["windows"]) or list(markets.MARKETS)


def colleagues(control_db: Session | None, tenant_id: uuid.UUID) -> list[dict]:
    """The organization's active people (the trial's three seats), for the owners of a triage record."""
    if control_db is None:
        return []
    rows = (
        control_db.query(AuthUser.id, AuthUser.display_name, AuthUser.username, AuthUser.role)
        .filter(AuthUser.tenant_id == tenant_id, AuthUser.status == "ACTIVE")
        .order_by(AuthUser.display_name)
        .all()
    )
    return [
        {"id": str(row.id), "name": row.display_name or row.username}
        for row in rows
        if "ADMIN" not in str(row.role or "").upper().replace(" ", "_")
    ]


def names_of(control_db: Session | None, tenant_id: uuid.UUID, refs) -> dict[str, str]:
    from backend.app.complaint_review.service import people

    return people(control_db, tenant_id, [ref for ref in refs if ref])


# --------------------------------------------------------------------------------------------- events and checks


def checks_of(db: Session, tenant_id: uuid.UUID, event_ids) -> dict[uuid.UUID, list[FirstContactCheck]]:
    found: dict[uuid.UUID, list[FirstContactCheck]] = {}
    ids = list(event_ids)
    if not ids:
        return found
    for row in (
        db.query(FirstContactCheck)
        .filter(FirstContactCheck.tenant_id == tenant_id, FirstContactCheck.intake_event_id.in_(ids))
        .order_by(FirstContactCheck.version)
    ):
        found.setdefault(row.intake_event_id, []).append(row)
    return found


def current_signed(versions: list[FirstContactCheck]) -> FirstContactCheck | None:
    signed = [row for row in versions if row.signed_at is not None and row.superseded_by is None]
    return signed[-1] if signed else None


def tasks_of(db: Session, tenant_id: uuid.UUID, event_ids) -> dict[uuid.UUID, list[WorkflowTask]]:
    found: dict[uuid.UUID, list[WorkflowTask]] = {}
    ids = list(event_ids)
    if not ids:
        return found
    for row in (
        db.query(WorkflowTask)
        .filter(
            WorkflowTask.tenant_id == tenant_id,
            WorkflowTask.source_entity_type == SOURCE_TYPE,
            WorkflowTask.source_entity_id.in_(ids),
        )
        .order_by(WorkflowTask.created_at)
    ):
        found.setdefault(row.source_entity_id, []).append(row)
    return found


def open_task(tasks: list[WorkflowTask], task_type: str) -> WorkflowTask | None:
    return next((t for t in tasks if t.task_type == task_type and t.status in OPEN_TASK_STATUSES), None)


def task_view(task: WorkflowTask, now: datetime) -> dict:
    due = rules.utc(task.due_at)
    return {
        "id": str(task.id),
        "type": task.task_type,
        "title": task.title,
        "status": task.status,
        "open": task.status in OPEN_TASK_STATUSES,
        "due_at": _iso(due),
        "overdue": bool(due and due < now and task.status in OPEN_TASK_STATUSES),
        "outcome": task.completion_outcome,
        "completed_at": _iso(task.completed_at),
        "details": task.details or {},
    }


def event_awareness(event: IntakeEvent, record: TriageRecord | None = None) -> dict:
    """The awareness an intake counts from: a contact's is the time of the contact; an urgent intake's is the time
    entered, else the earliest of first knowledge and receipt (unresolved); a confirmed time at triage wins."""
    if record is not None and record.awareness_confirmed_at is not None:
        return {"at": rules.utc(record.awareness_confirmed_at), "source": "CONFIRMED", "unresolved": False}
    found = rules.awareness(
        event.awareness_at,
        [(event.first_knowledge_at, "FIRST_KNOWLEDGE"), (event.received_at, "RECEIVED")],
        event.created_at,
    )
    if event.kind == "CONTACT" and found["source"] == "AWARENESS":
        found["source"] = "CONTACT"
    return found


def complaint_awareness(complaint: Complaint, record: TriageRecord | None = None) -> dict:
    if record is not None and record.awareness_confirmed_at is not None:
        return {"at": rules.utc(record.awareness_confirmed_at), "source": "CONFIRMED", "unresolved": False}
    # With neither an awareness nor a received date, the event date counts too (0.10.81, as the watch does).
    event = (
        complaint.event_timestamp
        if complaint.awareness_timestamp is None and complaint.complaint_timestamp is None
        else None
    )
    return rules.awareness(
        complaint.awareness_timestamp,
        [
            (complaint.complaint_timestamp, "RECEIVED"),
            (event, "EVENT_DATE"),
            (complaint.recorded_timestamp, "SOURCE_DATE"),
        ],
        complaint.ingestion_timestamp or complaint.created_at,
        earliest=True,
    )


def make_reference(db: Session, tenant_id: uuid.UUID, kind: str) -> str:
    prefix = {"CONTACT": "CALL", "URGENT": "URG", "SERVICE_RECORD": "SVC"}[kind]
    for _ in range(5):
        reference = f"{prefix}-{uuid.uuid4().hex[:6].upper()}"
        taken = (
            db.query(IntakeEvent.id)
            .filter(IntakeEvent.tenant_id == tenant_id, IntakeEvent.reference == reference)
            .first()
        )
        if taken is None:
            return reference
    raise RuntimeError("No free reference")


def ensure_follow_up(db, tenant_id, event: IntakeEvent, answers: dict, suggestion: str, actor, now) -> None:
    """Every Unknown and Not stated raises a follow-up with the reporter (a dated task, and its request in the
    communications log since T-G30): one open task per
    event, due at the end of the next working day (T9), naming the questions it asks."""
    from backend.app.workflow.tasks import create_task

    asks = case_rules.follow_up_questions(answers)
    if suggestion == rules.PENDING_CONFIRM:
        asks = ["NO_DEFICIENCY"]
    if not asks:
        return
    # A short title (V6); the questions it asks stay in the task's details.
    title = f"Follow up {event.reference} with the reporter: " + (
        "is a deficiency alleged?"
        if asks == ["NO_DEFICIENCY"]
        else f"{len(asks)} open question{'s' if len(asks) != 1 else ''}"
    )
    task = create_task(
        db,
        tenant_id,
        task_type=FOLLOW_UP,
        title=title,
        source_type=SOURCE_TYPE,
        source_id=event.id,
        assigned_user_id=_user_or_none(actor),
        due_at=working_day_end(now, 1, calendar(db, tenant_id)),
        created_by=actor,
        details={"questions": asks, "reference": event.reference},
    )
    task.details = {**(task.details or {}), "questions": asks, "reference": event.reference}
    # The communications log (T-G30, 0.10.59): the follow-up is also a request to the reporter, linked to this task.
    from backend.app.communications.service import ensure_intake_request

    ensure_intake_request(db, tenant_id, event, task, asks, str(actor), now)


def ensure_qms_task(db, tenant_id, event: IntakeEvent, actor, now) -> None:
    """The task to create or link the QMS complaint (G20, T16): owned by the person who entered the event, due at the
    end of the next working day. Reporting never waits for it."""
    from backend.app.workflow.tasks import create_task

    create_task(
        db,
        tenant_id,
        task_type=QMS,
        title=f"Create or link the QMS complaint for {event.reference}",
        source_type=SOURCE_TYPE,
        source_id=event.id,
        assigned_user_id=_user_or_none(actor),
        due_at=working_day_end(now, 1, calendar(db, tenant_id)),
        created_by=actor,
        details={"reference": event.reference},
    )


def ensure_review_task(db, tenant_id, event: IntakeEvent, check: FirstContactCheck, actor, now) -> None:
    """The QA review sample (T-G32: every "service only" in the trial): a reviewer's queue task, due in 5 working days,
    or 1 working day (never later than 24 hours) when the text matches a fault word or a harm word."""
    from backend.app.workflow.tasks import create_task

    matched = rules.fault_words(event.reporter_words) + rules.harm_words(event.reporter_words)
    days = calendar(db, tenant_id)
    due = min(working_day_end(now, 1, days), now + timedelta(hours=24)) if matched else working_day_end(now, 5, days)
    create_task(
        db,
        tenant_id,
        task_type=REVIEW,
        title=f"QA review: {event.reference} was signed service only",
        source_type=SOURCE_TYPE,
        source_id=event.id,
        due_at=due,
        created_by=actor,
        details={"reference": event.reference, "check": str(check.id), "words": matched},
    )


def _user_or_none(actor) -> uuid.UUID | None:
    try:
        return uuid.UUID(str(actor))
    except (TypeError, ValueError):
        return None


# --------------------------------------------------------------------------------------------- links and events


def links_of(db: Session, tenant_id: uuid.UUID) -> list[RecordLink]:
    return (
        db.query(RecordLink)
        .filter(RecordLink.tenant_id == tenant_id)
        .order_by(RecordLink.decided_at)
        .limit(READ_LIMIT)
        .all()
    )


def groups(links: list[RecordLink]) -> dict[tuple[str, uuid.UUID], tuple]:
    """``{(kind, id): group key}`` for every record in a LINKED link: records linked to each other share a key."""
    parent: dict = {}

    def find(item):
        parent.setdefault(item, item)
        while parent[item] != item:
            parent[item] = parent[parent[item]]
            item = parent[item]
        return item

    for link in links:
        if link.state == "LINKED":
            a, b = find((link.left_kind, link.left_id)), find((link.right_kind, link.right_id))
            if a != b:
                parent[b] = a
    return {item: find(item) for item in parent}


def linked_awareness(db: Session, tenant_id: uuid.UUID, complaint_ids) -> dict[uuid.UUID, datetime]:
    """For complaints linked to other sources, the earliest awareness among them (G20): every deadline counted from
    awareness, the reportability watch's included, uses it."""
    ids = set(complaint_ids)
    if not ids:
        return {}
    links = [link for link in links_of(db, tenant_id) if link.state == "LINKED"]
    if not links:
        return {}
    group = groups(links)
    wanted = {key for (kind, rid), key in group.items() if kind == COMPLAINT and rid in ids}
    if not wanted:
        return {}
    members = [(kind, rid) for (kind, rid), key in group.items() if key in wanted]
    complaint_ids_all = [rid for kind, rid in members if kind == COMPLAINT]
    event_ids = [rid for kind, rid in members if kind == INTAKE]
    times: dict[tuple, datetime] = {}
    for complaint in db.query(Complaint).filter(Complaint.tenant_id == tenant_id, Complaint.id.in_(complaint_ids_all)):
        times[(COMPLAINT, complaint.id)] = complaint_awareness(complaint)["at"]
    if event_ids:
        for event in db.query(IntakeEvent).filter(IntakeEvent.tenant_id == tenant_id, IntakeEvent.id.in_(event_ids)):
            times[(INTAKE, event.id)] = event_awareness(event)["at"]
    earliest: dict[tuple, datetime] = {}
    for member, moment in times.items():
        key = group[member]
        if moment is not None and (key not in earliest or moment < earliest[key]):
            earliest[key] = moment
    return {
        rid: earliest[group[(COMPLAINT, rid)]]
        for rid in ids
        if (COMPLAINT, rid) in group and group[(COMPLAINT, rid)] in earliest
    }


# --------------------------------------------------------------------------------------------- the triage list


def _excluded_complaints(db: Session, tenant_id: uuid.UUID, ids: list[uuid.UUID]) -> set[uuid.UUID]:
    """Complaints a person has already taken up: in a case's scope, with a current signed disposition, or dismissed on
    the second look."""
    if not ids:
        return set()
    in_case = {
        row[0]
        for row in db.query(InvestigationComplaint.complaint_id).filter(
            InvestigationComplaint.tenant_id == tenant_id, InvestigationComplaint.complaint_id.in_(ids)
        )
    }
    disposed = {
        row[0]
        for row in db.query(ComplaintDisposition.complaint_id).filter(
            ComplaintDisposition.tenant_id == tenant_id,
            ComplaintDisposition.complaint_id.in_(ids),
            ComplaintDisposition.superseded_by.is_(None),
        )
    }
    dismissed = {
        row[0]
        for row in db.query(ComplaintSecondLook.complaint_id).filter(
            ComplaintSecondLook.tenant_id == tenant_id,
            ComplaintSecondLook.complaint_id.in_(ids),
            ComplaintSecondLook.decision == "DISMISSED",
        )
    }
    return in_case | disposed | dismissed


def _complaint_record(complaint: Complaint) -> dict:
    return {
        "description": complaint.description,
        "death": complaint.death,
        "serious_injury": complaint.serious_injury,
        "patient_involved": complaint.patient_involved,
        "malfunction": complaint.malfunction,
        "severity": complaint.severity,
    }


def subjects(db: Session, tenant_id: uuid.UUID, records: dict, now: datetime) -> dict[tuple, dict]:
    """Every record the triage list may show, by ``(kind, id)``: intake events, open imported complaints and open
    set-aside rows, each with its flags, availability and awareness."""
    found: dict[tuple, dict] = {}
    products = {
        row.id: row.name
        for row in db.query(Product.id, Product.name).filter(Product.tenant_id == tenant_id).limit(READ_LIMIT)
    }
    lots = {
        row.id: row.lot_identifier
        for row in db.query(LotBatch.id, LotBatch.lot_identifier).filter(LotBatch.tenant_id == tenant_id)
    }
    events = (
        db.query(IntakeEvent)
        .filter(IntakeEvent.tenant_id == tenant_id)
        .order_by(IntakeEvent.created_at.desc())
        .limit(READ_LIMIT)
        .all()
    )
    checks = checks_of(db, tenant_id, [event.id for event in events])
    for event in events:
        versions = checks.get(event.id, [])
        latest = versions[-1] if versions else None
        record = records.get((INTAKE, event.id))
        flags = rules.intake_flags(event.kind, event.reporter_words, latest.answers if latest else {})
        signed = current_signed(versions)
        found[(INTAKE, event.id)] = {
            "kind": INTAKE,
            "id": event.id,
            "ref": event.reference,
            "source": rules.KIND_LABELS[event.kind],
            "intake_kind": event.kind,
            "country": event.country,
            "product_id": event.product_id,
            "product_name": products.get(event.product_id),
            "lot": lots.get(event.lot_batch_id),
            "words": event.reporter_words,
            "flags": flags,
            "available_at": rules.utc(event.created_at),
            "awareness": event_awareness(event, record),
            "classification": signed.classification if signed else None,
            "signed_by": signed.signed_by if signed else None,
            "suggestion": latest.suggestion if latest else None,
            "sample": is_sample(event.source_system),
        }
    complaints = (
        db.query(Complaint)
        .filter(Complaint.tenant_id == tenant_id)
        .order_by(Complaint.ingestion_timestamp.desc().nullslast())
        .limit(READ_LIMIT)
        .all()
    )
    for complaint in complaints:
        if review_rules.is_closed(complaint.status):
            continue
        record = records.get((COMPLAINT, complaint.id))
        found[(COMPLAINT, complaint.id)] = {
            "kind": COMPLAINT,
            "id": complaint.id,
            "ref": complaint_ref(complaint),
            "business_id": complaint.business_id,
            "identifier": complaint.complaint_identifier,
            "source": "Imported complaint",
            "country": complaint.country,
            "product_id": complaint.product_id,
            "product_name": products.get(complaint.product_id),
            "lot": lots.get(complaint.lot_batch_id),
            "words": complaint.description,
            "flags": rules.complaint_flags(_complaint_record(complaint)),
            "available_at": rules.utc(complaint.ingestion_timestamp or complaint.created_at),
            "awareness": complaint_awareness(complaint, record),
            "sample": complaint.source_system == "MDARIX_SAMPLE",
            # B2: a Complaint a Case became is triaged, routine or fast (spec 3.4).
            "case_complaint": complaint.source_system == "MDARIX_CASE",
        }
    excluded = _excluded_complaints(db, tenant_id, [key[1] for key in found if key[0] == COMPLAINT])
    for complaint_id in excluded:
        found[(COMPLAINT, complaint_id)]["taken_up"] = True
    rows = (
        db.query(ImportQuarantineRow)
        .filter(
            ImportQuarantineRow.tenant_id == tenant_id,
            ImportQuarantineRow.entity == "complaints",
            ImportQuarantineRow.status == "OPEN",
        )
        .limit(READ_LIMIT)
        .all()
    )
    for row in rows:
        record = records.get((QUARANTINE, row.id))
        values = row.row or {}
        moment = None
        for column in ("awareness_date", "received_date", "event_date"):
            try:
                moment = datetime.fromisoformat(str(values.get(column) or "")).replace(tzinfo=timezone.utc)
                break
            except ValueError:
                continue
        found[(QUARANTINE, row.id)] = {
            "kind": QUARANTINE,
            "id": row.id,
            "ref": str(values.get("complaint_id") or f"Row {row.line}"),
            "source": f"Set-aside import row (line {row.line})",
            "import_ref": str(row.import_ref),
            "country": values.get("country") or None,
            "product_id": None,
            "product_name": values.get("product_id") or None,
            "lot": values.get("lot_id") or None,
            "words": values.get("description") or "",
            "flags": rules.quarantine_flags(list(row.harm_words or [])),
            "problems": list(row.problems or []),
            "available_at": rules.utc(row.created_at),
            "awareness": (
                {"at": rules.utc(record.awareness_confirmed_at), "source": "CONFIRMED", "unresolved": False}
                if record is not None and record.awareness_confirmed_at is not None
                else rules.awareness(None, [(moment, "SOURCE_DATE")], row.created_at)
            ),
            "sample": row.source == "MDARIX_SAMPLE",
        }
    return found


def _listed(subject: dict, record: TriageRecord | None) -> bool:
    """Whether a record calls for triage: flagged (an imported complaint a person has not yet taken up), an urgent
    intake, or escalated by hand."""
    if record is not None and record.escalated_at is not None:
        return True
    if subject["kind"] == INTAKE and subject.get("intake_kind") == "URGENT":
        return True
    if subject.get("case_complaint"):
        return True
    return bool(subject["flags"]) and not subject.get("taken_up")


def triage_records(db: Session, tenant_id: uuid.UUID) -> dict[tuple, TriageRecord]:
    return {
        (row.subject_kind, row.subject_id): row
        for row in db.query(TriageRecord).filter(TriageRecord.tenant_id == tenant_id).limit(READ_LIMIT * 2)
    }


# The triage list read once per request (0.10.85, D3.13): one page read it up to seven times (the watch, the list's
# checklists, the story). A read is kept on the database session for a few seconds and dropped on any write, so a
# change in the same request is read fresh. Callers only read it.
_MEMO, _MEMO_SECONDS = "intake.triage", 5.0


@sa_event.listens_for(Session, "after_flush")
@sa_event.listens_for(Session, "after_rollback")
def _forget_triage(session, *_) -> None:
    session.info.pop(_MEMO, None)


def triage(
    db: Session, control_db: Session | None, tenant_id: uuid.UUID, show: str = "open", now: datetime | None = None
) -> dict:
    """The triage list: one item per event (linked records together), the open ones most urgent first."""
    # A moment given is kept to the minute: the watch passes its own "now", microseconds apart within one request.
    minute = now.replace(second=0, microsecond=0) if isinstance(now, datetime) else now
    key = (str(tenant_id), show, control_db is not None, minute)
    memo = db.info.setdefault(_MEMO, {})
    kept = memo.get(key)
    if kept and time.monotonic() - kept[0] < _MEMO_SECONDS:
        return kept[1]
    found = _triage(db, control_db, tenant_id, show, now)
    memo[key] = (time.monotonic(), found)
    return found


def _triage(
    db: Session, control_db: Session | None, tenant_id: uuid.UUID, show: str, now: datetime | date | None
) -> dict:
    now = now or now_utc()
    if not isinstance(now, datetime):
        # A day (the readiness checks' watch passes one): read at its noon UTC. It raised AttributeError before, and
        # Records' "Reported in window" check read nothing (seen in 0.10.85's speed measurements).
        now = datetime(now.year, now.month, now.day, 12, tzinfo=timezone.utc)
    today = now.date()
    records = triage_records(db, tenant_id)
    found = subjects(db, tenant_id, records, now)
    links = links_of(db, tenant_id)
    group = groups(links)
    enabled = enabled_markets(db, tenant_id)
    context = _deadline_context(db, tenant_id, found, now)
    by_group: dict = {}
    for key, subject in found.items():
        by_group.setdefault(group.get(key, key), []).append(key)
    names = names_of(
        control_db,
        tenant_id,
        {
            value
            for row in records.values()
            for value in (row.event_owner, row.triage_owner, row.backup_owner, row.completed_by, row.escalated_by)
        },
    )
    items = []
    for group_key, members in by_group.items():
        listed = [key for key in members if _listed(found[key], records.get(key))]
        conflicts = [
            link
            for link in links
            if link.state == "LINKED"
            and link.conflict
            and group.get((link.left_kind, link.left_id)) == group_key
            and (link.left_kind, link.left_id) in found
        ]
        member_records = [records[key] for key in members if key in records]
        last_done = max((rules.utc(row.completed_at) for row in member_records if row.completed_at), default=None)
        conflict = [link for link in conflicts if last_done is None or rules.utc(link.decided_at) > last_done]
        if not listed and not conflict:
            continue
        done = not conflict and all(
            records.get(key) is not None and records[key].completed_at is not None for key in listed
        )
        if (show == "open" and done) or (show == "done" and not done):
            continue
        items.append(_item(found, members, listed, records, conflict, enabled, names, now, today, context))
    order = {rules.THREAT: 0, rules.FLAGGED: 1, rules.UNFLAGGED: 2}
    items.sort(key=lambda item: (order[item["tier"]], item["earliest_due"] or "9999", item["ref"]))
    return {
        "items": items,
        "summary": _summary(db, tenant_id, records, found, group, links),
        "people": colleagues(control_db, tenant_id),
        "enabled_markets": enabled,
        "harm_words_version": rules.HARM_WORDS_VERSION,
        "provisional_version": rules.PROVISIONAL_VERSION,
        "starter_mark": _starter(),
        "now": now.isoformat(),
    }


def _deadline_context(db: Session, tenant_id: uuid.UUID, found: dict, now: datetime) -> dict:
    """What triage's deadlines need besides the records: the organization's time zone, each complaint's signed market
    conclusions with their clocks (J3; None for "not reportable"), and the products' words (an IVD cites the IVDR)."""
    from backend.app.reportability import assessments
    from backend.app.reportability import service as reporting_service
    from backend.app.reportability.deadlines import org_zone as zone_of

    zone = zone_of(db, tenant_id)
    windows = reporting_service.settings_of(db, tenant_id)["windows"]
    complaint_ids = [key[1] for key in found if key[0] == COMPLAINT]
    rows = assessments.rows_by_complaint(db, tenant_id, complaint_ids) if complaint_ids else {}
    signed: dict = {}
    for complaint_id, by_market in rows.items():
        key = (COMPLAINT, complaint_id)
        for market, versions in by_market.items():
            current, _ = assessments.current_and_draft(versions)
            if current is None or current.conclusion is None:
                continue
            clock = markets.market_clock(
                market, current.conclusion, current.report_type, windows, found[key]["awareness"]["at"], now, zone
            )
            signed.setdefault(key, {})[market] = clock
    products = {
        row.id: markets.product_is_ivd(row)
        for row in db.query(Product).filter(Product.tenant_id == tenant_id).limit(READ_LIMIT)
    }
    return {
        "org_zone": zone,
        "signed": signed,
        "products": products,
        "fast_hours": fast_hours(db, tenant_id),
        "calendar": calendar(db, tenant_id),
    }


def fast_hours(db: Session, tenant_id) -> int:
    from backend.app.db.models.oversight import OversightSettings

    row = db.query(OversightSettings.triage_fast_hours).filter(OversightSettings.tenant_id == tenant_id).first()
    return row.triage_fast_hours if row else 4


def _starter() -> str:
    from backend.app.standards import STARTER_MARK

    return STARTER_MARK


def _summary(db, tenant_id, records, found, group, links) -> dict:
    open_count = 0
    for key, subject in found.items():
        record = records.get(key)
        if _listed(subject, record) and (record is None or record.completed_at is None):
            open_count += 1
    return {
        "open": open_count,
        "done": sum(1 for row in records.values() if row.completed_at is not None),
        "conflicts": sum(1 for link in links if link.state == "LINKED" and link.conflict),
    }


def _item(found, members, listed, records, conflict, enabled, names, now, today, context) -> dict:
    primary_key = next((key for key in listed if key[0] == INTAKE), None) or (listed or members)[0]
    primary = found[primary_key]
    member_records = {key: records.get(key) for key in members}
    awareness = min((found[key]["awareness"] for key in members), key=lambda item: item["at"])
    earliest_source = next(key for key in members if found[key]["awareness"] is awareness)
    if earliest_source != primary_key:
        awareness = {**awareness, "source": "LINKED", "linked_ref": found[earliest_source]["ref"]}
    threat = any(row is not None and row.public_health_threat for row in member_records.values())
    remedial = any(row is not None and row.remedial_action for row in member_records.values())
    escalated = [row for row in member_records.values() if row is not None and row.escalated_at is not None]
    flags = list({flag["label"]: flag for key in members for flag in found[key]["flags"]}.values())
    if escalated:
        flags.append(
            {
                "code": "MANUAL",
                "label": "Escalated by hand: " + (escalated[0].escalation_reason or ""),
                "by": names.get(escalated[0].escalated_by) or "A colleague",
            }
        )
    level = rules.tier(bool(flags), threat)
    countries = (markets.market_of(found[key].get("country")) for key in [primary_key, *members])
    own = next((market for market in countries if market), None)
    signed: dict = {}
    for key in members:
        signed = {**context["signed"].get(key, {}), **signed}
    deadlines = rules.provisional_deadlines(
        awareness["at"],
        enabled,
        level,
        now,
        remedial,
        own=own,
        signed=signed,
        org_zone=context["org_zone"],
        ivd=context["products"].get(primary.get("product_id"), False),
    )
    record = member_records.get(primary_key)
    opened = rules.utc(record.opened_at) if record is not None else primary["available_at"]
    # A link that brought an earlier awareness reopens triage: its target counts from the link (G19's reopening).
    opened = max([opened, *(rules.utc(link.decided_at) for link in conflict)])
    # B2: two speeds, the floor and the acknowledgement of a fast-track item (triage_rules).
    found_facts = triage_rules.facts(flags, threat)
    reopened = bool(record is not None and record.reopened_at is not None and record.completed_at is None)
    pace = triage_rules.speed(
        found_facts,
        record.potential_severity if record is not None else None,
        record.severity if record is not None else None,
        reopened or bool(conflict),
    )
    target = triage_rules.due(pace, opened, context["fast_hours"], context["calendar"])
    least, floor_reasons = triage_rules.floor(found_facts)
    acked = rules.utc(record.acknowledged_at) if record is not None and record.acknowledged_at else None
    acked = acked if acked is not None and acked >= opened else None
    ack_due = triage_rules.ack_due(opened, target)
    signer = next((found[key].get("signed_by") for key in members if found[key].get("signed_by")), None)
    return {
        "key": f"{primary['kind']}:{primary['id']}",
        "kind": primary["kind"],
        "id": str(primary["id"]),
        "ref": primary["ref"],
        "identifier": primary.get("identifier"),
        "source": primary["source"],
        "intake_kind": primary.get("intake_kind"),
        "product_name": primary["product_name"],
        "lot": primary["lot"],
        "words": primary["words"],
        "problems": primary.get("problems"),
        "import_ref": primary.get("import_ref"),
        "classification": primary.get("classification"),
        "suggestion": primary.get("suggestion"),
        "sample": primary["sample"],
        "flags": flags,
        "tier": level,
        "tier_label": rules.TIER_LABELS[level],
        "linked": [
            {"kind": found[key]["kind"], "id": str(found[key]["id"]), "ref": found[key]["ref"]}
            for key in members
            if key != primary_key
        ],
        "awareness": {
            "at": awareness["at"].isoformat(),
            # A day given without a time is shown as a date (0.10.81, U-06).
            "date_only": day_only(awareness["at"]),
            "source": awareness["source"],
            "source_label": rules.AWARENESS_LABELS.get(awareness["source"], awareness["source"]),
            "linked_ref": awareness.get("linked_ref"),
            "unresolved": awareness["unresolved"],
            "label": rules.UNRESOLVED_LABEL if awareness["unresolved"] else None,
        },
        "available_at": primary["available_at"].isoformat(),
        "delay": rules.delay_text(awareness["at"], primary["available_at"]),
        "triage_clock": triage_rules.clock(opened, target, now),
        "speed": pace,
        "speed_label": triage_rules.SPEED_LABELS[pace],
        "speed_why": triage_rules.why_fast(
            found_facts,
            record.potential_severity if record is not None else None,
            record.severity if record is not None else None,
            reopened or bool(conflict),
        ),
        "facts": found_facts,
        "severity_floor": least,
        "floor_note": floor_reasons[0] if floor_reasons else None,
        "acknowledgement": {
            "required": pace == triage_rules.FAST,
            "done": acked is not None,
            "due_at": ack_due.isoformat(),
            "overdue": pace == triage_rules.FAST and acked is None and ack_due < now,
            "acknowledged_at": _iso(acked),
            "acknowledged_by": (names.get(record.acknowledged_by) or "A colleague") if acked else None,
        },
        "routine_prefill": {**triage_rules.ROUTINE_PREFILL, "triage_owner": signer, "event_owner": signer}
        if pace == triage_rules.ROUTINE
        else None,
        "deadlines": deadlines,
        "own_market": own,
        "earliest_due": deadlines[0]["due_at"] if deadlines else None,
        "conflict": [
            {
                "link": str(link.id),
                "before": _iso(link.awareness_before),
                "after": _iso(link.awareness_after),
                "decided_at": _iso(link.decided_at),
            }
            for link in conflict
        ],
        "record": record_view(record, names) if record is not None else None,
        "members": [f"{found[key]['kind']}:{found[key]['id']}" for key in members],
    }


def record_view(record: TriageRecord, names: dict) -> dict:
    def name(ref):
        return (names.get(ref) or "A colleague") if ref else None

    return {
        "id": str(record.id),
        "opened_at": _iso(record.opened_at),
        "target_hours": record.target_hours,
        "escalated_by": name(record.escalated_by),
        "escalated_at": _iso(record.escalated_at),
        "escalation_reason": record.escalation_reason,
        "severity": record.severity,
        "severity_label": markets.LEVEL_LABELS.get(record.severity) if record.severity else None,
        "public_health_threat": record.public_health_threat,
        "remedial_action": record.remedial_action,
        "event_owner": record.event_owner,
        "event_owner_name": name(record.event_owner),
        "triage_owner": record.triage_owner,
        "triage_owner_name": name(record.triage_owner),
        "backup_owner": record.backup_owner,
        "backup_owner_name": name(record.backup_owner),
        "immediate_action": record.immediate_action,
        "no_action_reason": record.no_action_reason,
        "awareness_confirmed_at": _iso(record.awareness_confirmed_at),
        "awareness_note": record.awareness_note,
        "completed_by": name(record.completed_by),
        "completed_at": _iso(record.completed_at),
        # B2 (tr19): versions, two speeds, the floor, containment, reopening, the signed threat exclusion.
        "version": record.version,
        "speed": record.speed,
        "potential_severity": record.potential_severity,
        "severity_floor": record.severity_floor,
        "containment": record.containment,
        "change_reason": record.change_reason,
        "reopened_at": _iso(record.reopened_at),
        "reopen_trigger": record.reopen_trigger,
        "threat_excluded_at": _iso(record.threat_excluded_at),
        "threat_exclusion_reason": record.threat_exclusion_reason,
        "inherited_from": str(record.inherited_from) if record.inherited_from else None,
    }


# --------------------------------------------------------------------------------------------- possible duplicates


def _duplicate_fields(kind: str, row, lots: dict) -> dict:
    if kind == INTAKE:
        moment = row.event_at or row.received_at
        return {
            "product_id": row.product_id,
            "lot_id": lots.get(row.lot_batch_id),
            "serial": row.serial_number,
            "site": row.reporter_site,
            "country": row.country,
            "event_on": rules.utc(moment).date() if moment else None,
        }
    moment = row.event_timestamp or row.complaint_timestamp
    return {
        "product_id": row.product_id,
        "lot_id": lots.get(row.lot_batch_id),
        "serial": row.serial_number,
        "site": None,
        "country": row.country,
        "event_on": rules.utc(moment).date() if moment else None,
    }


def candidate_pairs(fields: list[dict]) -> list[tuple[int, int]]:
    """The pairs of records (``i < j``, in the order a nested loop meets them) that may be duplicates: only records of
    one product with the same lot or the same serial number can be (``rules.duplicate_reasons``), so they are paired
    by those keys instead of every record with every other (0.10.88, DEV-13: 2,500 records made 3 million pairs)."""
    groups: dict[tuple, list[int]] = {}
    for index, item in enumerate(fields):
        if not item.get("product_id"):
            continue
        for key in ("lot_id", "serial"):
            value = rules.normalize(item.get(key))
            if value:
                groups.setdefault((item["product_id"], key, value), []).append(index)
    pairs = {(a, b) for members in groups.values() for i, a in enumerate(members) for b in members[i + 1 :]}
    return sorted(pairs)


def duplicates(db: Session, tenant_id: uuid.UUID) -> list[dict]:
    """The possible duplicates across the trial's sources (uploads, the sample, logged contacts, urgent intakes) that
    nobody has decided on: each pair with its reasons."""
    lots = {
        row.id: row.lot_identifier
        for row in db.query(LotBatch.id, LotBatch.lot_identifier).filter(LotBatch.tenant_id == tenant_id)
    }
    products = {row.id: row.name for row in db.query(Product.id, Product.name).filter(Product.tenant_id == tenant_id)}
    events = (
        db.query(IntakeEvent)
        .filter(IntakeEvent.tenant_id == tenant_id, IntakeEvent.kind != "SERVICE_RECORD")
        .order_by(IntakeEvent.created_at.desc())
        .limit(500)
        .all()
    )
    product_ids = {event.product_id for event in events if event.product_id}
    complaints = (
        db.query(Complaint)
        .filter(Complaint.tenant_id == tenant_id)
        .order_by(Complaint.ingestion_timestamp.desc().nullslast())
        .limit(READ_LIMIT)
        .all()
    )
    links = links_of(db, tenant_id)
    decided = {frozenset({(l.left_kind, l.left_id), (l.right_kind, l.right_id)}) for l in links}
    group = groups(links)
    records = [(INTAKE, event, _duplicate_fields(INTAKE, event, lots)) for event in events]
    sources = {}
    for complaint in complaints:
        # A complaint is compared with the intake events, and with complaints from another source (an upload against
        # the sample); complaints of one source are one export, already one record each.
        if complaint.product_id in product_ids or complaint.source_system != "MDARIX_SAMPLE":
            records.append((COMPLAINT, complaint, _duplicate_fields(COMPLAINT, complaint, lots)))
            sources[complaint.id] = complaint.source_system
    found = []
    for index, other in candidate_pairs([fields for _, _, fields in records]):
        (left_kind, left, left_fields), (right_kind, right, right_fields) = records[index], records[other]
        if left_kind == COMPLAINT and right_kind == COMPLAINT and sources[left.id] == sources[right.id]:
            continue
        pair = frozenset({(left_kind, left.id), (right_kind, right.id)})
        if pair in decided:
            continue
        a, b = group.get((left_kind, left.id)), group.get((right_kind, right.id))
        if a is not None and a == b:
            continue
        reasons = rules.duplicate_reasons(left_fields, right_fields)
        if reasons:
            found.append(
                {
                    "left": _side(left_kind, left, products),
                    "right": _side(right_kind, right, products),
                    "reasons": reasons,
                }
            )
    return found[:100]


def _side(kind: str, row, products: dict) -> dict:
    if kind == INTAKE:
        aware = event_awareness(row)
        return {
            "kind": INTAKE,
            "id": str(row.id),
            "ref": row.reference,
            "source": rules.KIND_LABELS[row.kind],
            "product_name": products.get(row.product_id),
            "words": row.reporter_words,
            "event_at": _iso(row.event_at),
            "awareness_at": aware["at"].isoformat(),
            "awareness_source": rules.AWARENESS_LABELS.get(aware["source"]),
        }
    aware = complaint_awareness(row)
    return {
        "kind": COMPLAINT,
        "id": str(row.id),
        "ref": complaint_ref(row),
        "source": "Sample complaint" if row.source_system == "MDARIX_SAMPLE" else "Uploaded complaint",
        "product_name": products.get(row.product_id),
        "words": row.description,
        "event_at": _iso(row.event_timestamp),
        "awareness_at": aware["at"].isoformat(),
        "awareness_source": rules.AWARENESS_LABELS.get(aware["source"]),
    }


def awareness_of(db: Session, tenant_id: uuid.UUID, kind: str, record_id: uuid.UUID) -> datetime | None:
    """The earliest awareness of the event a record belongs to (its own when it is linked to nothing)."""
    links = [link for link in links_of(db, tenant_id) if link.state == "LINKED"]
    group = groups(links)
    key = group.get((kind, record_id))
    members = [item for item, value in group.items() if value == key] if key else [(kind, record_id)]
    times = []
    for member_kind, member_id in members:
        if member_kind == INTAKE:
            event = db.get(IntakeEvent, member_id)
            if event is not None and event.tenant_id == tenant_id:
                times.append(event_awareness(event)["at"])
        else:
            complaint = db.get(Complaint, member_id)
            if complaint is not None and complaint.tenant_id == tenant_id:
                times.append(complaint_awareness(complaint)["at"])
    return min((moment for moment in times if moment is not None), default=None)


# --------------------------------------------------------------------------------------------- imports


def record_changes(db: Session, tenant_id, changes: list[dict], import_ref, source: str, now: datetime) -> int:
    """Store the field changes a re-upload made (G20: the history of field changes)."""
    for change in changes:
        db.add(
            RecordFieldChange(
                tenant_id=tenant_id,
                entity=change["entity"],
                record_id=change["record_id"],
                record_key=change["record_key"][:400],
                import_ref=import_ref,
                field=change["field"],
                before=change["before"],
                after=change["after"],
                source=source,
                changed_at=now,
            )
        )
    return len(changes)


def changes_of(db: Session, tenant_id, *, import_ref=None, record_id=None) -> list[dict]:
    query = db.query(RecordFieldChange).filter(RecordFieldChange.tenant_id == tenant_id)
    if import_ref is not None:
        query = query.filter(RecordFieldChange.import_ref == import_ref)
    if record_id is not None:
        query = query.filter(RecordFieldChange.record_id == record_id)
    return [
        {
            "record_id": str(row.record_id),
            "record_key": row.record_key,
            "field": row.field,
            "before": row.before,
            "after": row.after,
            "import_ref": str(row.import_ref) if row.import_ref else None,
            "changed_at": row.changed_at.isoformat(),
        }
        for row in query.order_by(RecordFieldChange.changed_at.desc(), RecordFieldChange.field).limit(500)
    ]


def confirm_by_import(db: Session, tenant_id, identifiers, actor: str, now: datetime) -> int:
    """The QMS-complaint task closes when an upload brings the complaint ID entered on the intake (T-G20): the intake
    is linked to the imported complaint, and the task completed."""
    from backend.app.workflow.tasks import complete_tasks

    wanted = {str(value).strip() for value in identifiers if value}
    if not wanted:
        return 0
    events = (
        db.query(IntakeEvent)
        .filter(IntakeEvent.tenant_id == tenant_id, IntakeEvent.qms_ref.in_(wanted))
        .limit(READ_LIMIT)
        .all()
    )
    closed = 0
    for event in events:
        complaint = (
            db.query(Complaint)
            .filter(Complaint.tenant_id == tenant_id, Complaint.complaint_identifier == event.qms_ref)
            .first()
        )
        if complaint is None:
            continue
        already = (
            db.query(RecordLink.id)
            .filter(
                RecordLink.tenant_id == tenant_id,
                RecordLink.state == "LINKED",
                or_(
                    (RecordLink.left_id == event.id) & (RecordLink.right_id == complaint.id),
                    (RecordLink.left_id == complaint.id) & (RecordLink.right_id == event.id),
                ),
            )
            .first()
        )
        if already is None:
            add_link(db, tenant_id, (INTAKE, event.id), (COMPLAINT, complaint.id), actor, now, "Confirmed by import")
        if complete_tasks(
            db,
            tenant_id,
            source_type=SOURCE_TYPE,
            source_id=event.id,
            task_types=[QMS],
            outcome="IMPORT_CONFIRMED",
            actor_ref=actor,
        ):
            closed += 1
    return closed


def add_link(db: Session, tenant_id, left: tuple, right: tuple, actor: str, now: datetime, reason: str) -> RecordLink:
    """Link two records into one event, with the event's awareness before (the later of the two) and after (the
    earliest): an earlier time raises "awareness conflict" on the triage list."""
    before_left = awareness_of(db, tenant_id, *left)
    before_right = awareness_of(db, tenant_id, *right)
    known = [moment for moment in (before_left, before_right) if moment is not None]
    after = min(known) if known else None
    before = max(known) if known else None
    link = RecordLink(
        tenant_id=tenant_id,
        left_kind=left[0],
        left_id=left[1],
        right_kind=right[0],
        right_id=right[1],
        state="LINKED",
        reason=reason,
        decided_by=str(actor),
        decided_at=now,
        awareness_before=before,
        awareness_after=after,
        conflict=bool(after and before and after < before),
        created_at=now,
    )
    db.add(link)
    db.flush()
    return link


def today_of(now: datetime) -> date:
    return now.astimezone(timezone.utc).date()


# --------------------------------------------------------------------------------------------- the Case (0.10.93, B2)


class CaseStateRefused(ValueError):
    """A move the Case's state rules do not allow (case_rules.TRANSITIONS)."""


def _audit(audit_db, tenant_id, actor, action: str, event: IntakeEvent, now, correlation_id, **details) -> None:
    from backend.app.enterprise_audit import make_audit_event

    audit_db.add(
        make_audit_event(
            tenant_id=tenant_id,
            actor_ref=actor,
            action=action,
            entity_type=SOURCE_TYPE,
            entity_id=event.id,
            correlation_id=correlation_id,
            details={"reference": event.reference, **details},
            created_at=now,
        )
    )


def set_case_status(
    _db: Session,
    audit_db,
    tenant_id,
    event: IntakeEvent,
    target: str,
    actor,
    now,
    correlation_id=None,
    why=None,
    *,
    classification: str | None = None,
) -> None:
    """The only writer of a Case's state. An allowed move bumps the Case's row version and is audited; any other
    move is refused, audited as refused, and raises CaseStateRefused (B2-08). ``classification``: the signed outcome,
    for the rule that a service-only Case closes only with its resolution summary (S-2)."""
    current = event.status or case_rules.OPEN
    if current == target:
        return
    problem = case_rules.transition_problem(current, target)
    if problem is None and target == case_rules.CLOSED:
        problem = case_rules.close_problem(classification, event.resolution_summary)
    if problem:
        _audit(
            audit_db,
            tenant_id,
            actor,
            "CASE_STATE_REFUSED",
            event,
            now,
            correlation_id,
            **{"from": current, "to": target, "problem": problem},
        )
        raise CaseStateRefused(problem)
    event.status, event.version, event.updated_at = target, (event.version or 1) + 1, now
    _audit(
        audit_db,
        tenant_id,
        actor,
        "CASE_STATE_CHANGED",
        event,
        now,
        correlation_id,
        **{"from": current, "to": target, "why": why or case_rules.TRANSITIONS[(current, target)]},
    )


def linked_complaint(db: Session, tenant_id, event: IntakeEvent) -> Complaint | None:
    """The complaint a person linked this Case to (the earliest LINKED link), if any."""
    for link in links_of(db, tenant_id):
        if link.state != "LINKED" or event.id not in (link.left_id, link.right_id):
            continue
        kind, other = (link.right_kind, link.right_id) if link.left_id == event.id else (link.left_kind, link.left_id)
        if kind == COMPLAINT:
            found = db.get(Complaint, other)
            if found is not None and found.tenant_id == tenant_id:
                return found
    return None


def case_setup(db: Session, tenant_id, trial: bool) -> tuple[str, str]:
    """(record owner of a new complaint, case flow): the organization's system of record for complaints (no row: a
    trial is MDARIX, a pilot EXTERNAL, M3) and how Cases become complaints (default one record)."""
    from backend.app.db.models.oversight import OversightSettings, RecordOwnership

    row = (
        db.query(RecordOwnership)
        .filter(RecordOwnership.tenant_id == tenant_id, RecordOwnership.domain == "COMPLAINTS")
        .first()
    )
    owner = row.owner if row else ("MDARIX" if trial else "EXTERNAL")
    settings = db.query(OversightSettings).filter(OversightSettings.tenant_id == tenant_id).first()
    return owner, (settings.case_flow if settings else "ONE_RECORD")


def _flag(answers: dict, question: str) -> bool | None:
    """An answer carried to a complaint's harm field: Yes -> true, No -> false, anything else -> unknown (never false)."""
    answer = rules.answer_of(answers, question)
    return True if answer == rules.YES else False if answer == rules.NO else None


def escalate_case(
    db: Session,
    audit_db,
    tenant_id,
    event: IntakeEvent,
    check: FirstContactCheck | None,
    actor,
    now: datetime,
    *,
    record_owner: str,
    flow: str = "ONE_RECORD",
    attach_to: Complaint | None = None,
    correlation_id=None,
) -> Complaint:
    """D1: a Case signed a complaint becomes the Complaint at once, in the same transaction as the signature. "Create"
    copies each fact once (the Case keeps what came in; from now on the Complaint is where a shared fact is corrected);
    in one-record mode the Complaint takes the Case's reference. "Attach" joins an existing Complaint. Either way the
    Case and the Complaint are linked (one event, the earliest awareness) and the Case is ESCALATED. Idempotent: a Case
    that already became a Complaint returns it and creates nothing (A4)."""
    if event.complaint_id is not None:
        existing = db.get(Complaint, event.complaint_id)
        if existing is not None:
            return existing
    aware = event_awareness(event)
    # A Case a person already linked to a complaint (a duplicate, an imported service record's complaint) joins it.
    linked = linked_complaint(db, tenant_id, event)
    attach_to = attach_to or linked
    if attach_to is not None:
        complaint, mode = attach_to, "ATTACHED"
    else:
        answers = (check.answers if check else None) or {}
        complaint = Complaint(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            complaint_identifier=event.reference if flow == "ONE_RECORD" else f"CMP-{event.reference}",
            product_id=event.product_id,
            product_version_id=event.product_version_id,
            lot_batch_id=event.lot_batch_id,
            product_text=event.product_text,
            lot_text=event.lot_text,
            software_version=event.software_version,
            event_timestamp=event.event_at,
            complaint_timestamp=event.received_at,
            awareness_timestamp=aware["at"],
            description=event.reporter_words,
            status="open",
            country=event.country,
            reporter_type=event.reporter_type,
            serial_number=event.serial_number,
            udi=event.udi,
            patient_involved=_flag(answers, "Q4"),
            # Question 5 asks "a death or a serious injury": a Yes says which only after follow-up, so death stays
            # unknown; a No rules out both.
            serious_injury=_flag(answers, "Q5"),
            death=False if rules.answer_of(answers, "Q5") == rules.NO else None,
            malfunction=_flag(answers, "Q6"),
            service_reference=event.service_ticket,
            qms_ref=event.qms_ref,
            record_owner=record_owner,
            source_system="MDARIX_CASE",
            source_identifier=event.reference,
            recorded_timestamp=event.received_at,
            created_at=now,
            updated_at=now,
        )
        db.add(complaint)
        db.flush()
        mode = "CREATED"
        _audit(
            audit_db,
            tenant_id,
            actor,
            "COMPLAINT_CREATED_FROM_CASE",
            event,
            now,
            correlation_id,
            complaint_id=str(complaint.id),
            flow=flow,
            check_version=check.version if check else None,
        )
    if linked is None or linked.id != complaint.id:
        add_link(
            db,
            tenant_id,
            (INTAKE, event.id),
            (COMPLAINT, complaint.id),
            str(actor),
            now,
            f"Escalated from case {event.reference}",
        )
    event.complaint_id, event.escalation, event.escalated_at, event.escalated_by = complaint.id, mode, now, str(actor)
    # T-D8: a Case triaged before signing (flagged) hands its triage to the Complaint.
    inherit_triage(db, audit_db, tenant_id, (INTAKE, event.id), (COMPLAINT, complaint.id), actor, now, correlation_id)
    set_case_status(
        db,
        audit_db,
        tenant_id,
        event,
        case_rules.ESCALATED,
        actor,
        now,
        correlation_id,
        f"Signed {check.classification.lower()} (check version {check.version})"
        if check
        else "Urgent case: a complaint by definition",
    )
    _audit(
        audit_db,
        tenant_id,
        actor,
        "CASE_ESCALATED",
        event,
        now,
        correlation_id,
        complaint_id=str(complaint.id),
        escalation=mode,
        flow=flow,
        awareness_at=_iso(aware["at"]),
    )
    if record_owner == "EXTERNAL":
        ensure_qms_id_task(db, tenant_id, event, actor, now)
    return complaint


def ensure_qms_id_task(db, tenant_id, event: IntakeEvent, actor, now) -> None:
    """Connect (spec 3.3 step 6, 5.4): the Complaint exists in MDARIX; its QMS complaint ID is entered by hand or
    filled by the next import, due in 5 working days. Complete organizations get no task."""
    from backend.app.workflow.tasks import create_task

    create_task(
        db,
        tenant_id,
        task_type=QMS,
        title=f"Enter the QMS complaint ID for {event.reference} (optional: your import fills it)",
        source_type=SOURCE_TYPE,
        source_id=event.id,
        assigned_user_id=_user_or_none(actor),
        due_at=working_day_end(now, 5, calendar(db, tenant_id)),
        created_by=actor,
        details={"reference": event.reference, "complaint_id": str(event.complaint_id)},
    )


# --------------------------------------------------------------------------------------------- triage versions (B2)

# The fields a triage version keeps (spec 3.4: "Versions": who changed what, old -> new).
TRACKED = (
    "severity",
    "potential_severity",
    "speed",
    "public_health_threat",
    "remedial_action",
    "event_owner",
    "triage_owner",
    "backup_owner",
    "immediate_action",
    "no_action_reason",
    "containment",
    "awareness_confirmed_at",
    "threat_excluded_at",
)


def triage_snapshot(record: TriageRecord) -> dict:
    found = {}
    for name in TRACKED:
        value = getattr(record, name)
        found[name] = value.isoformat() if isinstance(value, datetime) else value
    return found


def add_triage_version(
    db: Session, tenant_id, record: TriageRecord, before: dict | None, actor, now, reason=None, signed=None
) -> dict:
    """Keep the record's current state as a new version (never overwritten); returns the changed fields old -> new.
    The first version is 1; each later one adds 1 to the record's ``version``."""
    from backend.app.db.models.intake import TriageRecordVersion

    after = triage_snapshot(record)
    changed = {
        name: {"old": (before or {}).get(name), "new": after[name]}
        for name in TRACKED
        if (before or {}).get(name) != after[name]
    }
    has_versions = (
        db.query(TriageRecordVersion.id)
        .filter(TriageRecordVersion.tenant_id == tenant_id, TriageRecordVersion.triage_record_id == record.id)
        .first()
        is not None
    )
    if has_versions:
        record.version = (record.version or 1) + 1
    db.add(
        TriageRecordVersion(
            tenant_id=tenant_id,
            triage_record_id=record.id,
            version=record.version or 1,
            snapshot=after,
            changed_fields=changed,
            change_reason=reason,
            changed_by=str(actor),
            changed_at=now,
            signed_record_id=signed,
        )
    )
    return changed


def triage_versions(db: Session, tenant_id, record_id) -> list:
    from backend.app.db.models.intake import TriageRecordVersion

    return (
        db.query(TriageRecordVersion)
        .filter(TriageRecordVersion.tenant_id == tenant_id, TriageRecordVersion.triage_record_id == record_id)
        .order_by(TriageRecordVersion.version)
        .all()
    )


_INHERITED = (
    "opened_at",
    "target_hours",
    "severity",
    "public_health_threat",
    "remedial_action",
    "event_owner",
    "triage_owner",
    "backup_owner",
    "immediate_action",
    "no_action_reason",
    "awareness_confirmed_at",
    "awareness_note",
    "completed_by",
    "completed_at",
    "speed",
    "potential_severity",
    "severity_floor",
    "floor_reasons",
    "flags_at_completion",
    "containment",
    "acknowledged_at",
    "acknowledged_by",
)


def inherit_triage(db: Session, audit_db, tenant_id, source: tuple, target: tuple, actor, now, correlation_id=None):
    """T-D8: triage belongs to the event. A record joining an event already triaged gets an INHERITED copy (version 1,
    ``inherited_from`` set). Nothing happens when the source is not triaged or the target has its own record."""
    from backend.app.enterprise_audit import make_audit_event

    rows = {
        (row.subject_kind, row.subject_id): row
        for row in db.query(TriageRecord).filter(
            TriageRecord.tenant_id == tenant_id,
            or_(
                (TriageRecord.subject_kind == source[0]) & (TriageRecord.subject_id == source[1]),
                (TriageRecord.subject_kind == target[0]) & (TriageRecord.subject_id == target[1]),
            ),
        )
    }
    origin = rows.get(source)
    if origin is None or origin.completed_at is None or target in rows:
        return None
    copy = TriageRecord(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        subject_kind=target[0],
        subject_id=target[1],
        created_by=str(actor),
        created_at=now,
        updated_at=now,
        inherited_from=origin.id,
        version=1,
        **{name: getattr(origin, name) for name in _INHERITED},
    )
    db.add(copy)
    db.flush()
    add_triage_version(db, tenant_id, copy, None, actor, now, f"Inherited from the event's triage {origin.id}")
    audit_db.add(
        make_audit_event(
            tenant_id=tenant_id,
            actor_ref=actor,
            action="TRIAGE_INHERITED",
            entity_type="TriageRecord",
            entity_id=copy.id,
            correlation_id=correlation_id,
            details={"from": str(origin.id), "subject": f"{target[0]}:{target[1]}"},
            created_at=now,
        )
    )
    return copy


def reopen_raised(db: Session, control_db, tenant_id, actor, now, correlation_id=None, why: str = "") -> list[str]:
    """T-D7: a finished triage whose facts now hold a death, a serious injury or a threat it did not hold at completion,
    or a higher floor, reopens on the fast track; its target counts from now and it must be acknowledged again (A1).
    Returns the reopened items' references. Flushes; the caller commits."""
    from backend.app.enterprise_audit import make_audit_event

    records = triage_records(db, tenant_id)
    reopened = []
    hours = fast_hours(db, tenant_id)
    for item in triage(db, control_db, tenant_id, "all", now)["items"]:
        for member in item["members"]:
            kind, member_id = member.split(":")
            record = records.get((kind, uuid.UUID(member_id)))
            if record is None or record.completed_at is None or not record.flags_at_completion:
                continue
            trigger = triage_rules.reopen_trigger(
                record.flags_at_completion.get("facts"), item["facts"], record.severity_floor, item["severity_floor"]
            )
            if trigger is None:
                continue
            record.completed_at = record.completed_by = None
            record.opened_at = record.reopened_at = record.updated_at = now
            record.reopen_trigger, record.speed = trigger, triage_rules.FAST
            record.due_at = now + timedelta(hours=hours)
            record.acknowledge_due_at = triage_rules.ack_due(now, record.due_at)
            db.add(
                make_audit_event(
                    tenant_id=tenant_id,
                    actor_ref=actor,
                    action="TRIAGE_REOPENED",
                    entity_type="TriageRecord",
                    entity_id=record.id,
                    correlation_id=correlation_id,
                    reason=why or None,
                    details={
                        "trigger": trigger,
                        "before": record.flags_at_completion.get("facts"),
                        "after": item["facts"],
                        "floor_before": record.severity_floor,
                        "floor_after": item["severity_floor"],
                    },
                    created_at=now,
                )
            )
            reopened.append(item["ref"])
    db.flush()
    return reopened
