"""Reading and writing the external communications log (T-G30; rules.py decides, this module keeps the records and
their tasks).

- An information request sent to a party has an owner and a reply due date, and a My Work task for its owner
  (``EXTERNAL_REPLY_DUE``) until it is answered, closed or unresolved after attempts.
- **Unknown answers raise a request.** A market assessment saved with an Unknown on a question that drives the
  conclusion raises one open request to the complaint's reporter per market, naming the questions; a first-contact
  check's follow-up (0.10.57) gets a request linked to its existing dated task, which the request then finishes, so a
  follow-up recorded before 0.10.59 keeps working as it did.
- Nothing here sends anything, and nothing commits: the caller owns the transaction.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone

from sqlalchemy.orm import Session

from backend.app.communications import rules
from backend.app.db.models.foundation import Complaint
from backend.app.db.models.guides_communications import CommunicationEntry, CommunicationSettings, ExternalParty

TASK_TYPE = "EXTERNAL_REPLY_DUE"
SOURCE_TYPE = "CommunicationEntry"
ASSESSMENT, INTAKE = "MarketAssessment", "IntakeEvent"


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def attempts_limit(db: Session, tenant_id: uuid.UUID) -> int:
    row = db.query(CommunicationSettings).filter(CommunicationSettings.tenant_id == tenant_id).one_or_none()
    return row.attempts_before_escalation if row is not None else rules.ATTEMPTS_DEFAULT


def has_second(party: ExternalParty) -> bool:
    return bool(party.second_name or party.second_details)


def reporter_party(db: Session, tenant_id, complaint: Complaint, actor: str, now: datetime, source_system=None):
    """The complaint's reporter as a party (made once, without contact details until a person records them)."""
    found = (
        db.query(ExternalParty)
        .filter(
            ExternalParty.tenant_id == tenant_id,
            ExternalParty.complaint_id == complaint.id,
            ExternalParty.party_type == rules.REPORTER,
        )
        .order_by(ExternalParty.created_at)
        .first()
    )
    if found is not None:
        return found
    ref = complaint.business_id or complaint.complaint_identifier
    kind = f" ({complaint.reporter_type})" if complaint.reporter_type else ""
    party = ExternalParty(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        party_type=rules.REPORTER,
        name=f"Reporter of {ref}{kind}",
        complaint_id=complaint.id,
        source_system=source_system,
        created_by=actor,
        created_at=now,
        updated_by=actor,
        updated_at=now,
    )
    db.add(party)
    db.flush()
    return party


def _task(db, tenant_id, entry: CommunicationEntry, party: ExternalParty, actor: str, ref: str | None):
    from backend.app.intake.service import _user_or_none, working_day_end
    from backend.app.workflow.tasks import create_task

    due = datetime.combine(entry.reply_due_on, datetime.max.time(), tzinfo=timezone.utc) if entry.reply_due_on else None
    task = create_task(
        db,
        tenant_id,
        task_type=TASK_TYPE,
        title=f"Reply due from {party.name}" + (f" on {ref}" if ref else "") + f": {entry.subject}",
        source_type=SOURCE_TYPE,
        source_id=entry.id,
        assigned_user_id=_user_or_none(entry.owner_id),
        due_at=due or working_day_end(entry.logged_at, 1),
        created_by=actor,
        details={"complaint_id": str(entry.complaint_id) if entry.complaint_id else None, "reference": ref},
    )
    entry.task_id = task.id
    return task


def record(
    db: Session,
    tenant_id,
    *,
    complaint: Complaint | None,
    party: ExternalParty,
    direction: str,
    purpose: str,
    subject: str,
    channel: str,
    occurred_at: datetime,
    actor: str,
    now: datetime,
    owner_id: str | None = None,
    reply_due_on: date | None = None,
    note: str | None = None,
    evidence: list | None = None,
    qms_reference: str | None = None,
    in_reply_to: uuid.UUID | None = None,
    origin: dict | None = None,
    intake_event_id: uuid.UUID | None = None,
    sent: bool = True,
    task_id: uuid.UUID | None = None,
    source_system: str | None = None,
) -> CommunicationEntry:
    """A new entry (shared with the sample). A request sent records its first attempt, unless it was raised to be sent
    (``sent=False``); it gets its owner's task unless it finishes one that exists (``task_id``). Flushes."""
    status = rules.status_for(direction, purpose)
    attempts = []
    if status == rules.OPEN and sent:
        attempts.append(
            {
                "at": occurred_at.isoformat(),
                "channel": channel,
                "contact": rules.PRIMARY,
                "outcome": rules.WAITING,
                "note": None,
                "logged_at": now.isoformat(),
                "logged_by": actor,
            }
        )
    entry = CommunicationEntry(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        complaint_id=complaint.id if complaint is not None else None,
        intake_event_id=intake_event_id,
        party_id=party.id,
        direction=direction,
        purpose=purpose,
        subject=subject,
        note=note,
        channel=channel,
        occurred_at=occurred_at,
        logged_at=now,
        logged_by=actor,
        owner_id=owner_id,
        reply_due_on=reply_due_on,
        status=status,
        current_contact=rules.PRIMARY,
        attempts=attempts,
        evidence=list(evidence or []),
        qms_reference=qms_reference,
        in_reply_to=in_reply_to,
        origin=origin,
        task_id=task_id,
        source_system=source_system,
        updated_at=now,
    )
    if status != rules.OPEN:
        entry.closed_at, entry.closed_by = now, actor
    db.add(entry)
    db.flush()
    if status == rules.OPEN and task_id is None:
        ref = (complaint.business_id or complaint.complaint_identifier) if complaint is not None else None
        _task(db, tenant_id, entry, party, actor, ref)
        db.flush()
    return entry


def _finish_task(db, entry: CommunicationEntry, outcome: str, actor: str, note: str | None) -> None:
    """Finish the request's task (its own, or the first-contact follow-up it answers) with the request's outcome."""
    from backend.app.db.models.workflow import WorkflowTask
    from backend.app.workflow.tasks import complete_tasks

    if entry.task_id is None:
        return
    task = db.get(WorkflowTask, entry.task_id)
    if task is None:
        return
    complete_tasks(
        db,
        entry.tenant_id,
        source_type=task.source_entity_type,
        source_id=task.source_entity_id,
        task_types=[task.task_type],
        outcome=outcome,
        actor_ref=actor,
        reason=note,
    )


def add_attempt(
    db: Session,
    entry: CommunicationEntry,
    party: ExternalParty,
    *,
    at: datetime,
    channel: str,
    outcome: str,
    note: str | None,
    actor: str,
    now: datetime,
    limit: int,
) -> str | None:
    """Record one attempt and apply the escalation rule; returns "MOVED_TO_SECOND", "UNRESOLVED" or None."""
    contact = entry.current_contact
    attempts = [
        *(entry.attempts or []),
        {
            "at": at.isoformat(),
            "channel": channel,
            "contact": contact,
            "outcome": outcome,
            "note": note,
            "logged_at": now.isoformat(),
            "logged_by": actor,
        },
    ]
    entry.attempts = attempts
    status, next_contact = rules.after_attempts(attempts, contact, has_second(party), limit)
    entry.updated_at = now
    event = None
    if next_contact != contact:
        entry.current_contact, event = next_contact, "MOVED_TO_SECOND"
    elif status == rules.UNRESOLVED:
        entry.status, entry.closed_at, entry.closed_by = rules.UNRESOLVED, now, actor
        entry.close_note = f"No answer after {limit} attempts" + (" to each contact" if has_second(party) else "")
        _finish_task(db, entry, "UNRESOLVED", actor, entry.close_note)
        event = "UNRESOLVED"
    db.flush()
    return event


def close(db: Session, entry: CommunicationEntry, status: str, note: str | None, actor: str, now: datetime) -> None:
    """End a request: answered, closed (no longer needed) or unresolved after attempts."""
    entry.status, entry.closed_at, entry.closed_by, entry.close_note = status, now, actor, note
    entry.updated_at = now
    _finish_task(db, entry, "ANSWERED" if status == rules.ANSWERED else status, actor, note)
    db.flush()


def open_requests(db: Session, tenant_id, complaint_ids=None) -> list[CommunicationEntry]:
    query = db.query(CommunicationEntry).filter(
        CommunicationEntry.tenant_id == tenant_id, CommunicationEntry.status == rules.OPEN
    )
    if complaint_ids is not None:
        ids = list(complaint_ids)
        if not ids:
            return []
        query = query.filter(CommunicationEntry.complaint_id.in_(ids))
    return query.order_by(CommunicationEntry.reply_due_on.nullslast(), CommunicationEntry.logged_at).all()


def summary(db: Session, tenant_id, today: date, complaint_ids=None) -> dict:
    """Open and overdue requests (for Readiness and the decision brief), overdue first."""
    rows = open_requests(db, tenant_id, complaint_ids)
    parties = {
        party.id: party
        for party in db.query(ExternalParty).filter(
            ExternalParty.tenant_id == tenant_id, ExternalParty.id.in_([row.party_id for row in rows] or [None])
        )
    }
    refs = {
        row.id: row.business_id or row.complaint_identifier
        for row in db.query(Complaint.id, Complaint.business_id, Complaint.complaint_identifier).filter(
            Complaint.tenant_id == tenant_id,
            Complaint.id.in_([row.complaint_id for row in rows if row.complaint_id] or [None]),
        )
    }
    items = []
    for row in rows:
        late = rules.overdue(row.status, row.reply_due_on, today)
        party = parties.get(row.party_id)
        items.append(
            {
                "id": str(row.id),
                "complaint_id": str(row.complaint_id) if row.complaint_id else None,
                "ref": refs.get(row.complaint_id),
                "party": party.name if party else None,
                "party_type": party.party_type if party else None,
                "subject": row.subject,
                "reply_due_on": row.reply_due_on.isoformat() if row.reply_due_on else None,
                "overdue": late,
                "attempts": len(row.attempts or []),
                "contact": row.current_contact,
            }
        )
    items.sort(key=lambda item: (not item["overdue"], item["reply_due_on"] or "9999"))
    unresolved_query = db.query(CommunicationEntry.id).filter(
        CommunicationEntry.tenant_id == tenant_id, CommunicationEntry.status == rules.UNRESOLVED
    )
    if complaint_ids is not None:
        unresolved_query = unresolved_query.filter(CommunicationEntry.complaint_id.in_(list(complaint_ids) or [None]))
    return {
        "open": len(items),
        "overdue": sum(item["overdue"] for item in items),
        "unresolved": unresolved_query.count(),
        "items": items,
    }


# --------------------------------------------------------------------------------------------- raised by Unknowns


def _open_from(db, tenant_id, kind: str, key: str, value: str, complaint_id=None):
    query = db.query(CommunicationEntry).filter(
        CommunicationEntry.tenant_id == tenant_id,
        CommunicationEntry.status == rules.OPEN,
        CommunicationEntry.origin["type"].astext == kind,
        CommunicationEntry.origin[key].astext == value,
    )
    if complaint_id is not None:
        query = query.filter(CommunicationEntry.complaint_id == complaint_id)
    return query.first()


def ensure_assessment_request(
    db: Session, tenant_id, complaint: Complaint, market: str, unknown: list[str], labels: dict, actor: str, now
) -> CommunicationEntry | None:
    """One open request to the reporter per complaint and market while its assessment has Unknown answers on questions
    that drive the conclusion: raised to be sent, owned by the person who saved, due at the end of the next working
    day; the questions it asks follow the latest save."""
    from backend.app.intake.service import working_day_end

    if not unknown:
        return None
    subject = f"Ask the reporter: {', '.join(labels.get(q, q) for q in unknown)} ({market} assessment, Unknown)"
    subject = subject[: rules.SUBJECT_MAX]
    found = _open_from(db, tenant_id, ASSESSMENT, "market", market, complaint.id)
    if found is not None:
        if (found.origin or {}).get("questions") != unknown:
            found.origin = {**(found.origin or {}), "questions": unknown}
            found.subject, found.updated_at = subject, now
            db.flush()
        return found
    party = reporter_party(db, tenant_id, complaint, actor, now)
    return record(
        db,
        tenant_id,
        complaint=complaint,
        party=party,
        direction=rules.SENT,
        purpose=rules.REQUEST,
        subject=subject,
        channel="EMAIL",
        occurred_at=now,
        actor=actor,
        now=now,
        owner_id=actor,
        reply_due_on=working_day_end(now, 1).date(),
        origin={"type": ASSESSMENT, "market": market, "questions": unknown},
        sent=False,
    )


def ensure_intake_request(db: Session, tenant_id, event, task, questions: list[str], actor: str, now) -> None:
    """The first-contact follow-up (0.10.57) as a request to the reporter, linked to its dated task: answering or
    giving up on the request finishes the task with the same outcome."""
    if task is None or _open_from(db, tenant_id, INTAKE, "event", str(event.id)) is not None:
        return
    party = _intake_party(db, tenant_id, event, actor, now)
    asks = (
        "whether any deficiency is alleged"
        if questions == ["NO_DEFICIENCY"]
        else ", ".join(f"question {q[1:]}" for q in questions)
    )
    record(
        db,
        tenant_id,
        complaint=None,
        party=party,
        direction=rules.SENT,
        purpose=rules.REQUEST,
        subject=f"First-contact follow-up of {event.reference}: ask {asks}"[: rules.SUBJECT_MAX],
        channel="PHONE",
        occurred_at=now,
        actor=actor,
        now=now,
        owner_id=str(task.assigned_user_id) if task.assigned_user_id else actor,
        reply_due_on=task.due_at.date() if task.due_at else None,
        origin={"type": INTAKE, "event": str(event.id), "reference": event.reference, "questions": questions},
        intake_event_id=event.id,
        sent=False,
        task_id=task.id,
        source_system=event.source_system,  # a sample contact's request is sample data too
    )


def _intake_party(db, tenant_id, event, actor: str, now):
    party = ExternalParty(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        party_type=rules.REPORTER,
        name=f"Reporter of {event.reference}" + (f" ({event.reporter_site})" if event.reporter_site else ""),
        source_system=event.source_system,
        created_by=actor,
        created_at=now,
        updated_by=actor,
        updated_at=now,
    )
    db.add(party)
    db.flush()
    return party


def close_for_intake(db: Session, tenant_id, event_id, status: str, note: str | None, actor: str, now) -> None:
    """The first-contact follow-up was closed on its own screen: its linked request ends the same way."""
    entry = _open_from(db, tenant_id, INTAKE, "event", str(event_id))
    if entry is not None:
        entry.status, entry.closed_at, entry.closed_by, entry.close_note = status, now, actor, note
        entry.updated_at = now
        db.flush()
