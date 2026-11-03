"""External communications log API (T-G30, MVP G30).

- ``GET /api/v1/communications``: every entry (``complaint_id`` narrows to one complaint), open and overdue requests
  first, with the parties, the attempts setting and the S4 count (done in MDARIX or outside);
- ``POST /api/v1/communications``: record a message sent or received (a request sent records its first attempt);
- ``GET /api/v1/communications/{id}``; ``PUT`` its owner, reply due date, evidence references, QMS reference and note;
- ``POST .../attempts``: another attempt, including an unsuccessful one; after the organization's number of unanswered
  attempts the request moves to the party's second contact, then shows "unresolved after attempts";
- ``POST .../reply``: the answer received (a new entry linked to the request, which is then answered);
- ``POST .../close``: closed (no longer needed) or unresolved after attempts, with a note;
- ``GET``/``POST /api/v1/communications/parties`` and ``PUT .../parties/{id}``: reporters, distributors, hospitals and
  service partners, each with a primary and a second contact;
- ``GET``/``PUT /api/v1/communications/settings``: the number of unanswered attempts (default 3).

MDARIX never sends anything: people send from their own mail and record it here. Reading is open to every signed-in
member; recording needs a complaint-handling, investigation or regulatory permission; the setting needs quality review
or regulatory approval. These routes serve a free trial and a pilot alike (T-B1).
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import false
from sqlalchemy.orm import Session

from backend.app.trial.sample_source import is_sample
from backend.app.access.permissions import (
    EVIDENCE_REQUEST,
    INVESTIGATION_WORK,
    QUALITY_REVIEW,
    REGULATORY_APPROVE,
    REGULATORY_REVIEW,
    SIGNAL_TRIAGE,
)
from backend.app.communications import rules, service
from backend.app.complaint_review.service import people
from backend.app.db.data_plane import get_data_plane_db
from backend.app.db.models.foundation import Complaint
from backend.app.db.models.guides_communications import CommunicationEntry, CommunicationSettings, ExternalParty
from backend.app.db.session import get_db
from backend.app.enterprise_audit import make_audit_event
from backend.app.evidence_workflow.people import require_any_permission
from backend.app.oversight.service import calendar_of
from backend.app.request_context import AuthenticatedRequestContext, get_request_context
from backend.app.business_ids import complaint_ref

router = APIRouter(prefix="/api/v1/communications", tags=["Communications log"])

WRITERS = Depends(
    require_any_permission(
        SIGNAL_TRIAGE, INVESTIGATION_WORK, EVIDENCE_REQUEST, QUALITY_REVIEW, REGULATORY_REVIEW, REGULATORY_APPROVE
    )
)
SETTERS = Depends(require_any_permission(QUALITY_REVIEW, REGULATORY_APPROVE))
SAMPLE_NAMES = {"system:trial-sample": "MDARIX sample data"}


def _error(status: int, code: str, message: str, **extra) -> HTTPException:
    return HTTPException(status, detail={"code": code, "message": message, **extra})


def _text(value, limit: int) -> str | None:
    text = " ".join(str(value or "").split())
    if len(text) > limit:
        raise _error(422, "TEXT_TOO_LONG", f"Keep it to {limit} characters")
    return text or None


def _tenant(ctx) -> uuid.UUID:
    return uuid.UUID(ctx.tenant_id)


def _iso(value) -> str | None:
    return value.isoformat() if value is not None else None


def _evidence(items: list[str]) -> list[str]:
    found: list[str] = []
    for item in items or []:
        text = _text(item, rules.EVIDENCE_ITEM_MAX)
        if text and text not in found:
            found.append(text)
    if len(found) > rules.EVIDENCE_MAX:
        raise _error(422, "TOO_MUCH_EVIDENCE", f"Attach at most {rules.EVIDENCE_MAX} evidence references")
    return found


def _aware(moment: datetime) -> datetime:
    if moment.tzinfo is None:
        raise _error(422, "TIME_ZONE_REQUIRED", "Give the time with its time zone")
    return moment


def _audit(db, ctx, action: str, entry: CommunicationEntry, **details) -> None:
    db.add(
        make_audit_event(
            tenant_id=entry.tenant_id,
            actor_ref=ctx.user_id,
            action=action,
            entity_type="CommunicationEntry",
            entity_id=entry.id,
            correlation_id=ctx.correlation_id,
            details={"complaint_id": str(entry.complaint_id) if entry.complaint_id else None, **details},
        )
    )


# --------------------------------------------------------------------------------------------- views


def party_view(party: ExternalParty) -> dict:
    return {
        "id": str(party.id),
        "type": party.party_type,
        "type_label": rules.PARTY_LABELS[party.party_type],
        "name": party.name,
        "complaint_id": str(party.complaint_id) if party.complaint_id else None,
        "primary": {"name": party.primary_name, "details": party.primary_details},
        "second": {"name": party.second_name, "details": party.second_details} if service.has_second(party) else None,
        "note": party.note,
        "sample": is_sample(party.source_system),
    }


def _attempt_view(
    index: int, attempt: dict, attempts: list[dict], party: ExternalParty | None, names: dict, calendar=None
) -> dict:
    contact = party_view(party)["primary" if attempt.get("contact") == rules.PRIMARY else "second"] if party else None
    latest = index == len(attempts) - 1
    at, logged = datetime.fromisoformat(attempt["at"]), datetime.fromisoformat(attempt["logged_at"])
    return {
        "number": index + 1,
        "at": attempt["at"],
        "channel": attempt["channel"],
        "channel_label": rules.CHANNELS.get(attempt["channel"], attempt["channel"]),
        "contact": attempt.get("contact"),
        "contact_name": (contact or {}).get("name")
        or ("Primary contact" if attempt.get("contact") == rules.PRIMARY else "Second contact"),
        "outcome": attempt["outcome"],
        "outcome_label": rules.ATTEMPT_OUTCOMES.get(attempt["outcome"], attempt["outcome"]),
        "unanswered": attempt["outcome"] != rules.WAITING or not latest,
        "note": attempt.get("note"),
        "logged_at": attempt["logged_at"],
        "logged_by": names.get(attempt.get("logged_by")) or "A colleague",
        "in_mdarix": rules.in_mdarix(at, logged, calendar),
    }


def entry_view(
    entry: CommunicationEntry,
    party: ExternalParty | None,
    refs: dict,
    names: dict,
    today: date,
    limit: int,
    calendar=None,
) -> dict:
    attempts = entry.attempts or []
    contact = party_view(party)["primary" if entry.current_contact == rules.PRIMARY else "second"] if party else None
    origin = entry.origin or {}
    return {
        "id": str(entry.id),
        "complaint_id": str(entry.complaint_id) if entry.complaint_id else None,
        "complaint_ref": refs.get(entry.complaint_id),
        "intake_reference": origin.get("reference") if origin.get("type") == service.INTAKE else None,
        "party": party_view(party) if party else None,
        "direction": entry.direction,
        "direction_label": rules.DIRECTION_LABELS[entry.direction],
        "purpose": entry.purpose,
        "purpose_label": rules.PURPOSE_LABELS[entry.purpose],
        "subject": entry.subject,
        "note": entry.note,
        "channel": entry.channel,
        "channel_label": rules.CHANNELS.get(entry.channel, entry.channel),
        "occurred_at": _iso(entry.occurred_at),
        "logged_at": _iso(entry.logged_at),
        "logged_by": names.get(entry.logged_by) or "A colleague",
        "in_mdarix": rules.in_mdarix(entry.occurred_at, entry.logged_at, calendar)
        if attempts or entry.purpose != rules.REQUEST
        else None,
        "owner_id": entry.owner_id,
        "owner": names.get(entry.owner_id) if entry.owner_id else None,
        "reply_due_on": _iso(entry.reply_due_on),
        "overdue": rules.overdue(entry.status, entry.reply_due_on, today),
        "status": entry.status,
        "status_label": rules.STATUS_LABELS[entry.status],
        "is_request": entry.purpose == rules.REQUEST and entry.direction == rules.SENT,
        "not_sent_yet": entry.status == rules.OPEN and not attempts,
        "current_contact": entry.current_contact,
        "contact_now": contact,
        "attempts": [
            _attempt_view(index, item, attempts, party, names, calendar) for index, item in enumerate(attempts)
        ],
        "unanswered": rules.unanswered(attempts, entry.current_contact),
        "attempts_limit": limit,
        "evidence": entry.evidence or [],
        "qms_reference": entry.qms_reference,
        "in_reply_to": str(entry.in_reply_to) if entry.in_reply_to else None,
        "origin": (
            {
                **origin,
                "label": f"Raised by an Unknown answer in the {origin.get('market')} assessment"
                if origin.get("type") == service.ASSESSMENT
                else f"Follow-up of first contact {origin.get('reference')}"
                if origin.get("type") == service.INTAKE
                else None,
            }
            if origin
            else None
        ),
        "closed_at": _iso(entry.closed_at),
        "closed_by": names.get(entry.closed_by) if entry.closed_by else None,
        "close_note": entry.close_note,
        "sample": is_sample(entry.source_system),
    }


def _views(db, control_db, tenant_id, rows: list[CommunicationEntry], today: date) -> list[dict]:
    parties = {
        party.id: party
        for party in db.query(ExternalParty).filter(
            ExternalParty.tenant_id == tenant_id, ExternalParty.id.in_({row.party_id for row in rows} or {None})
        )
    }
    refs = {
        row.id: complaint_ref(row)
        for row in db.query(Complaint.id, Complaint.business_id, Complaint.complaint_identifier).filter(
            Complaint.tenant_id == tenant_id,
            Complaint.id.in_({row.complaint_id for row in rows if row.complaint_id} or {None}),
        )
    }
    who = {ref for row in rows for ref in (row.logged_by, row.owner_id, row.closed_by)}
    who |= {attempt.get("logged_by") for row in rows for attempt in row.attempts or []}
    names = {**SAMPLE_NAMES, **people(control_db, tenant_id, [ref for ref in who if ref])}
    limit = service.attempts_limit(db, tenant_id)
    # S4 counts working time on the organization's own calendar (T-G25).
    calendar = calendar_of(db, tenant_id)
    return [entry_view(row, parties.get(row.party_id), refs, names, today, limit, calendar) for row in rows]


def _calendar(db, tenant_id):
    from backend.app.intake.service import calendar

    return calendar(db, tenant_id)


def _today(db, tenant_id) -> date:
    """Today on the organization's calendar: a reply due today is not overdue until its day ends there (J16)."""
    return _calendar(db, tenant_id).local_day(service.now_utc())


def _entry(db, tenant_id, entry_id, *, lock: bool = False) -> CommunicationEntry:
    query = db.query(CommunicationEntry).filter(
        CommunicationEntry.tenant_id == tenant_id, CommunicationEntry.id == entry_id
    )
    found = (query.with_for_update() if lock else query).one_or_none()
    if found is None:
        raise _error(404, "ENTRY_NOT_FOUND", "No such entry in your organization's communications log")
    return found


def _detail(db, control_db, ctx, entry: CommunicationEntry) -> dict:
    tenant_id = _tenant(ctx)
    replies = (
        db.query(CommunicationEntry)
        .filter(CommunicationEntry.tenant_id == tenant_id, CommunicationEntry.in_reply_to == entry.id)
        .order_by(CommunicationEntry.occurred_at)
        .all()
    )
    views = _views(db, control_db, tenant_id, [entry, *replies], _today(db, tenant_id))
    return {**views[0], "replies": views[1:], "never_sends": rules.NEVER_SENDS}


def _colleagues(control_db, tenant_id) -> list[dict]:
    from backend.app.intake.service import colleagues

    return colleagues(control_db, tenant_id)


@router.get("")
def communications(
    complaint_id: uuid.UUID | None = Query(default=None),
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """The log, open and overdue requests first, then the newest; with the parties that can be chosen."""
    tenant_id = _tenant(ctx)
    query = db.query(CommunicationEntry).filter(CommunicationEntry.tenant_id == tenant_id)
    complaint = None
    if complaint_id is not None:
        complaint = (
            db.query(Complaint).filter(Complaint.tenant_id == tenant_id, Complaint.id == complaint_id).one_or_none()
        )
        if complaint is None:
            raise _error(404, "COMPLAINT_NOT_FOUND", "No such complaint in your organization")
        query = query.filter(CommunicationEntry.complaint_id == complaint_id)
    rows = query.order_by(CommunicationEntry.occurred_at.desc()).limit(500).all()
    today = _today(db, tenant_id)
    items = _views(db, control_db, tenant_id, rows, today)
    items.sort(key=lambda item: (not item["overdue"], item["status"] != rules.OPEN))
    parties = (
        db.query(ExternalParty)
        .filter(
            ExternalParty.tenant_id == tenant_id,
            # A reporter is chosen only on their own complaint; the others on any.
            ((ExternalParty.complaint_id.is_(None)) & (ExternalParty.party_type != rules.REPORTER))
            | ((ExternalParty.complaint_id == complaint_id) if complaint_id is not None else false()),
        )
        .order_by(ExternalParty.party_type, ExternalParty.name)
        .all()
    )
    messages = [flag for item in items for flag in [item["in_mdarix"], *(a["in_mdarix"] for a in item["attempts"])]]
    messages = [flag for flag in messages if flag is not None]
    return {
        "complaint": (
            {
                "id": str(complaint.id),
                "ref": complaint_ref(complaint),
                "identifier": complaint.complaint_identifier,
                "description": complaint.description,
                "sample": is_sample(complaint.source_system),
            }
            if complaint is not None
            else None
        ),
        "items": items,
        "counts": {
            "open": sum(item["status"] == rules.OPEN for item in items),
            "overdue": sum(item["overdue"] for item in items),
            "unresolved": sum(item["status"] == rules.UNRESOLVED for item in items),
        },
        "s4": {"in_mdarix": messages.count(True), "outside": messages.count(False)},
        "parties": [party_view(party) for party in parties],
        "colleagues": _colleagues(control_db, tenant_id),
        "attempts_limit": service.attempts_limit(db, tenant_id),
        "labels": {
            "party_types": rules.PARTY_LABELS,
            "purposes": rules.PURPOSE_LABELS,
            "directions": rules.DIRECTION_LABELS,
            "statuses": rules.STATUS_LABELS,
            "channels": rules.CHANNELS,
            "outcomes": rules.ATTEMPT_OUTCOMES,
        },
        "never_sends": rules.NEVER_SENDS,
    }


# --------------------------------------------------------------------------------------------- parties and settings


class ContactIn(BaseModel):
    name: str = Field(default="", max_length=400)
    details: str = Field(default="", max_length=600)


class PartyIn(BaseModel):
    type: str = Field(max_length=20)
    name: str = Field(max_length=400)
    complaint_id: uuid.UUID | None = None
    primary: ContactIn = Field(default_factory=ContactIn)
    second: ContactIn | None = None
    note: str = Field(default="", max_length=4000)


def _apply_party(party: ExternalParty, payload: PartyIn, actor: str, now) -> None:
    kind = str(payload.type or "").strip().upper()
    if kind not in rules.PARTY_LABELS:
        raise _error(422, "PARTY_TYPE_UNKNOWN", "Choose a reporter, distributor, hospital or service partner")
    name = _text(payload.name, 200)
    if not name or len(name) < 2:
        raise _error(422, "PARTY_NAME_REQUIRED", "Name the party")
    party.party_type, party.name = kind, name
    party.primary_name, party.primary_details = _text(payload.primary.name, 200), _text(payload.primary.details, 300)
    second = payload.second or ContactIn()
    party.second_name, party.second_details = _text(second.name, 200), _text(second.details, 300)
    party.note = _text(payload.note, rules.NOTE_MAX)
    party.updated_by, party.updated_at = actor, now


@router.get("/parties")
def parties(
    db: Session = Depends(get_data_plane_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    rows = (
        db.query(ExternalParty)
        .filter(ExternalParty.tenant_id == _tenant(ctx))
        .order_by(ExternalParty.party_type, ExternalParty.name)
        .all()
    )
    return {"parties": [party_view(row) for row in rows], "types": rules.PARTY_LABELS}


@router.post("/parties", dependencies=[WRITERS])
def create_party(
    payload: PartyIn,
    db: Session = Depends(get_data_plane_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    tenant_id = _tenant(ctx)
    now = service.now_utc()
    if payload.complaint_id is not None and (
        db.query(Complaint.id).filter(Complaint.tenant_id == tenant_id, Complaint.id == payload.complaint_id).first()
        is None
    ):
        raise _error(404, "COMPLAINT_NOT_FOUND", "No such complaint in your organization")
    party = ExternalParty(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        complaint_id=payload.complaint_id,
        created_by=str(ctx.user_id),
        created_at=now,
    )
    _apply_party(party, payload, str(ctx.user_id), now)
    db.add(party)
    db.flush()
    db.add(
        make_audit_event(
            tenant_id=tenant_id,
            actor_ref=ctx.user_id,
            action="EXTERNAL_PARTY_ADDED",
            entity_type="ExternalParty",
            entity_id=party.id,
            correlation_id=ctx.correlation_id,
            details={"type": party.party_type, "second_contact": service.has_second(party)},
        )
    )
    db.commit()
    return party_view(party)


@router.put("/parties/{party_id}", dependencies=[WRITERS])
def update_party(
    party_id: uuid.UUID,
    payload: PartyIn,
    db: Session = Depends(get_data_plane_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    tenant_id = _tenant(ctx)
    party = (
        db.query(ExternalParty)
        .filter(ExternalParty.tenant_id == tenant_id, ExternalParty.id == party_id)
        .with_for_update()
        .one_or_none()
    )
    if party is None:
        raise _error(404, "PARTY_NOT_FOUND", "No such party in your organization")
    old = party_view(party)
    _apply_party(party, payload, str(ctx.user_id), service.now_utc())
    db.add(
        make_audit_event(
            tenant_id=tenant_id,
            actor_ref=ctx.user_id,
            action="EXTERNAL_PARTY_CHANGED",
            entity_type="ExternalParty",
            entity_id=party.id,
            correlation_id=ctx.correlation_id,
            old_values={"primary": old["primary"], "second": old["second"]},
            new_values={"primary": party_view(party)["primary"], "second": party_view(party)["second"]},
        )
    )
    db.commit()
    return party_view(party)


class SettingsIn(BaseModel):
    attempts_before_escalation: int = Field(ge=rules.ATTEMPTS_MIN, le=rules.ATTEMPTS_MAX)


@router.get("/settings")
def settings(
    db: Session = Depends(get_data_plane_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    return {
        "attempts_before_escalation": service.attempts_limit(db, _tenant(ctx)),
        "default": rules.ATTEMPTS_DEFAULT,
        "range": [rules.ATTEMPTS_MIN, rules.ATTEMPTS_MAX],
    }


@router.put("/settings", dependencies=[SETTERS])
def save_settings(
    payload: SettingsIn,
    db: Session = Depends(get_data_plane_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    tenant_id = _tenant(ctx)
    now = service.now_utc()
    row = db.query(CommunicationSettings).filter(CommunicationSettings.tenant_id == tenant_id).one_or_none()
    old = row.attempts_before_escalation if row is not None else rules.ATTEMPTS_DEFAULT
    if row is None:
        row = CommunicationSettings(id=uuid.uuid4(), tenant_id=tenant_id)
        db.add(row)
    row.attempts_before_escalation, row.updated_by, row.updated_at = (
        payload.attempts_before_escalation,
        str(ctx.user_id),
        now,
    )
    db.flush()
    db.add(
        make_audit_event(
            tenant_id=tenant_id,
            actor_ref=ctx.user_id,
            action="COMMUNICATION_SETTINGS_CHANGED",
            entity_type="CommunicationSettings",
            entity_id=row.id,
            correlation_id=ctx.correlation_id,
            old_values={"attempts_before_escalation": old},
            new_values={"attempts_before_escalation": payload.attempts_before_escalation},
        )
    )
    db.commit()
    return {"attempts_before_escalation": row.attempts_before_escalation}


# --------------------------------------------------------------------------------------------- entries


class EntryIn(BaseModel):
    complaint_id: uuid.UUID
    party_id: uuid.UUID
    direction: str = Field(max_length=10)
    purpose: str = Field(max_length=30)
    subject: str = Field(max_length=rules.SUBJECT_MAX * 2)
    channel: str = Field(max_length=20)
    occurred_at: datetime
    owner_id: str | None = Field(default=None, max_length=64)
    reply_due_on: date | None = None
    note: str = Field(default="", max_length=rules.NOTE_MAX * 2)
    evidence: list[str] = Field(default_factory=list, max_length=rules.EVIDENCE_MAX * 2)
    qms_reference: str = Field(default="", max_length=240)
    in_reply_to: uuid.UUID | None = None


def _owner(control_db, tenant_id, owner_id: str | None) -> str | None:
    if not owner_id:
        return None
    if owner_id not in {item["id"] for item in _colleagues(control_db, tenant_id)}:
        raise _error(422, "OWNER_UNKNOWN", "Choose the owner among your organization's people")
    return owner_id


@router.post("", dependencies=[WRITERS])
def create_entry(
    payload: EntryIn,
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    tenant_id = _tenant(ctx)
    now = service.now_utc()
    complaint = (
        db.query(Complaint).filter(Complaint.tenant_id == tenant_id, Complaint.id == payload.complaint_id).one_or_none()
    )
    if complaint is None:
        raise _error(404, "COMPLAINT_NOT_FOUND", "No such complaint in your organization")
    party = (
        db.query(ExternalParty)
        .filter(ExternalParty.tenant_id == tenant_id, ExternalParty.id == payload.party_id)
        .one_or_none()
    )
    if party is None:
        raise _error(404, "PARTY_NOT_FOUND", "No such party in your organization")
    direction, purpose = payload.direction.strip().upper(), payload.purpose.strip().upper()
    channel, subject = payload.channel.strip().upper(), _text(payload.subject, rules.SUBJECT_MAX) or ""
    owner = _owner(control_db, tenant_id, payload.owner_id)
    problem = rules.entry_problem(direction, purpose, channel, subject, owner, payload.reply_due_on)
    if problem:
        raise _error(422, "ENTRY_INVALID", problem)
    occurred = _aware(payload.occurred_at)
    if occurred > now:
        raise _error(422, "IN_FUTURE", "Record a message once it has been sent or received")
    if payload.reply_due_on is not None and payload.reply_due_on < occurred.date():
        raise _error(422, "DUE_BEFORE_SENT", "The reply cannot be due before the request was sent")
    request = None
    if payload.in_reply_to is not None:
        request = _entry(db, tenant_id, payload.in_reply_to, lock=True)
    entry = service.record(
        db,
        tenant_id,
        complaint=complaint,
        party=party,
        direction=direction,
        purpose=purpose,
        subject=subject,
        channel=channel,
        occurred_at=occurred,
        actor=str(ctx.user_id),
        now=now,
        owner_id=owner,
        reply_due_on=payload.reply_due_on,
        note=_text(payload.note, rules.NOTE_MAX),
        evidence=_evidence(payload.evidence),
        qms_reference=_text(payload.qms_reference, 120),
        in_reply_to=request.id if request is not None else None,
    )
    _audit(db, ctx, "COMMUNICATION_RECORDED", entry, direction=direction, purpose=purpose, party=party.party_type)
    db.commit()
    return _detail(db, control_db, ctx, entry)


@router.get("/{entry_id}")
def entry_detail(
    entry_id: uuid.UUID,
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    return _detail(db, control_db, ctx, _entry(db, _tenant(ctx), entry_id))


class UpdateIn(BaseModel):
    owner_id: str | None = Field(default=None, max_length=64)
    reply_due_on: date | None = None
    evidence: list[str] = Field(default_factory=list, max_length=rules.EVIDENCE_MAX * 2)
    qms_reference: str = Field(default="", max_length=240)
    note: str = Field(default="", max_length=rules.NOTE_MAX * 2)


@router.put("/{entry_id}", dependencies=[WRITERS])
def update_entry(
    entry_id: uuid.UUID,
    payload: UpdateIn,
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """The owner, the reply due date (an open request), the evidence references, the QMS reference and the note."""
    from backend.app.db.models.workflow import WorkflowTask

    tenant_id = _tenant(ctx)
    entry = _entry(db, tenant_id, entry_id, lock=True)
    owner = _owner(control_db, tenant_id, payload.owner_id)
    old = {
        "owner_id": entry.owner_id,
        "reply_due_on": _iso(entry.reply_due_on),
        "evidence": entry.evidence,
        "qms_reference": entry.qms_reference,
    }
    if entry.status == rules.OPEN and entry.purpose == rules.REQUEST:
        if not owner or payload.reply_due_on is None:
            raise _error(422, "ENTRY_INVALID", "A request needs its owner and the date a reply is due")
        entry.owner_id, entry.reply_due_on = owner, payload.reply_due_on
        task = db.get(WorkflowTask, entry.task_id) if entry.task_id else None
        if task is not None and task.task_type == service.TASK_TYPE:
            task.assigned_user_id = uuid.UUID(owner)
            # The end of the reply day on the organization's calendar, as every other MDARIX due time (J16).
            task.due_at = _calendar(db, tenant_id).day_end(payload.reply_due_on)
    entry.evidence = _evidence(payload.evidence)
    entry.qms_reference = _text(payload.qms_reference, 120)
    entry.note = _text(payload.note, rules.NOTE_MAX)
    entry.updated_at = service.now_utc()
    _audit(
        db,
        ctx,
        "COMMUNICATION_CHANGED",
        entry,
        old=old,
        new={
            "owner_id": entry.owner_id,
            "reply_due_on": _iso(entry.reply_due_on),
            "evidence": entry.evidence,
            "qms_reference": entry.qms_reference,
        },
    )
    db.commit()
    return _detail(db, control_db, ctx, entry)


def _open_request(db, tenant_id, entry_id) -> tuple[CommunicationEntry, ExternalParty]:
    entry = _entry(db, tenant_id, entry_id, lock=True)
    if entry.status != rules.OPEN:
        raise _error(409, "NOT_OPEN", "This request is no longer open")
    return entry, db.get(ExternalParty, entry.party_id)


class AttemptIn(BaseModel):
    at: datetime
    channel: str = Field(max_length=20)
    outcome: str = Field(max_length=20)
    note: str = Field(default="", max_length=2000)


@router.post("/{entry_id}/attempts", dependencies=[WRITERS])
def attempt(
    entry_id: uuid.UUID,
    payload: AttemptIn,
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    tenant_id = _tenant(ctx)
    entry, party = _open_request(db, tenant_id, entry_id)
    channel, outcome = payload.channel.strip().upper(), payload.outcome.strip().upper()
    if channel not in rules.CHANNELS:
        raise _error(422, "CHANNEL_UNKNOWN", "Choose how you tried")
    if outcome not in rules.ATTEMPT_OUTCOMES:
        raise _error(422, "OUTCOME_UNKNOWN", "Say what happened: sent and waiting, no answer, message left or bounced")
    at, now = _aware(payload.at), service.now_utc()
    if at > now:
        raise _error(422, "IN_FUTURE", "Record an attempt once it is made")
    limit = service.attempts_limit(db, tenant_id)
    if not entry.attempts:
        entry.occurred_at = at  # the request raised to be sent is sent now
    event = service.add_attempt(
        db,
        entry,
        party,
        at=at,
        channel=channel,
        outcome=outcome,
        note=_text(payload.note, 2000),
        actor=str(ctx.user_id),
        now=now,
        limit=limit,
    )
    _audit(db, ctx, "COMMUNICATION_ATTEMPT_RECORDED", entry, outcome=outcome, number=len(entry.attempts), event=event)
    db.commit()
    return _detail(db, control_db, ctx, entry)


class ReplyIn(BaseModel):
    received_at: datetime
    channel: str = Field(max_length=20)
    summary: str = Field(max_length=rules.SUBJECT_MAX * 2)
    note: str = Field(default="", max_length=rules.NOTE_MAX * 2)
    evidence: list[str] = Field(default_factory=list, max_length=rules.EVIDENCE_MAX * 2)
    qms_reference: str = Field(default="", max_length=240)


@router.post("/{entry_id}/reply", dependencies=[WRITERS])
def reply(
    entry_id: uuid.UUID,
    payload: ReplyIn,
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """The answer received: a new entry (received, response) linked to the request, which is then answered."""
    tenant_id = _tenant(ctx)
    entry, party = _open_request(db, tenant_id, entry_id)
    channel, summary = payload.channel.strip().upper(), _text(payload.summary, rules.SUBJECT_MAX) or ""
    problem = rules.entry_problem(rules.RECEIVED, rules.RESPONSE, channel, summary, None, None)
    if problem:
        raise _error(422, "ENTRY_INVALID", problem)
    received, now = _aware(payload.received_at), service.now_utc()
    if received > now or received < entry.occurred_at:
        raise _error(422, "TIME_INVALID", "The reply arrives after the request and before now")
    complaint = db.get(Complaint, entry.complaint_id) if entry.complaint_id else None
    answer = service.record(
        db,
        tenant_id,
        complaint=complaint,
        party=party,
        direction=rules.RECEIVED,
        purpose=rules.RESPONSE,
        subject=summary,
        channel=channel,
        occurred_at=received,
        actor=str(ctx.user_id),
        now=now,
        note=_text(payload.note, rules.NOTE_MAX),
        evidence=_evidence(payload.evidence),
        qms_reference=_text(payload.qms_reference, 120),
        in_reply_to=entry.id,
        intake_event_id=entry.intake_event_id,
    )
    service.close(db, entry, rules.ANSWERED, summary, str(ctx.user_id), now)
    _audit(db, ctx, "COMMUNICATION_ANSWERED", entry, reply=str(answer.id))
    db.commit()
    return _detail(db, control_db, ctx, entry)


class CloseIn(BaseModel):
    status: str = Field(max_length=20)
    note: str = Field(max_length=2000)


@router.post("/{entry_id}/close", dependencies=[WRITERS])
def close(
    entry_id: uuid.UUID,
    payload: CloseIn,
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """Close a request no longer needed, or mark it unresolved after attempts; either with a note."""
    tenant_id = _tenant(ctx)
    entry, _ = _open_request(db, tenant_id, entry_id)
    status = payload.status.strip().upper()
    if status not in (rules.CLOSED, rules.UNRESOLVED):
        raise _error(422, "STATUS_UNKNOWN", "Close it, or mark it unresolved after attempts")
    note = _text(payload.note, 2000) or ""
    if len(note) < rules.REASON_MIN:
        raise _error(422, "NOTE_NEEDED", f"Say in at least {rules.REASON_MIN} characters why")
    if status == rules.UNRESOLVED and not entry.attempts:
        raise _error(409, "NO_ATTEMPTS", "Record the attempts made before marking it unresolved")
    service.close(db, entry, status, note, str(ctx.user_id), service.now_utc())
    _audit(db, ctx, "COMMUNICATION_CLOSED", entry, status=status)
    db.commit()
    return _detail(db, control_db, ctx, entry)
