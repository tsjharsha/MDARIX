"""Resolve and close (B7, spec b7-routine-path section 1.2): the routine complaint's one screen and one signature.

- ``GET /api/v1/complaints/{id}/resolve-and-close``: the disposition screen, plus what this screen adds: the values
  pre-filled from the Case, whether it is offered in full (or "Resolve" only, with what still blocks closing), the
  similar complaints of the last 12 months, the event owner, and the mode (MDARIX Complete closes; Connect marks ready
  to close in the QMS).
- ``POST /api/v1/complaints/{id}/resolve-and-close``: one password (and code) check writes two signed records, each
  with its own meaning (B7-D1): the disposition (service level, the routine conclusions or the signed markets, the
  classification, the customer told) and ready to close. In Complete it also closes the complaint. The problem code
  is set (audited), the event owner taken over when the signer ticks it, and a reply logged to each reporter with a
  contact. Signing over an open item is never offered here; anything still open refuses.
- ``POST /api/v1/complaints/{id}/reopen``: Complete only, with a reason, no signature (the safe direction); the
  closure signature is superseded. ``reopen_closed`` is also called when a closed complaint's triage reopens (T-D7).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.app.access.permissions import QUALITY_REVIEW, SIGNAL_TRIAGE
from backend.app.complaint_disposition import rules, service
from backend.app.complaint_disposition.router import (
    DECIDERS,
    ClassificationIn,
    ServiceRecordIn,
    SignRequest,
    _error,
    screen,
    sign,
)
from backend.app.complaint_review.service import people
from backend.app.db.data_plane import get_data_plane_db
from backend.app.db.models.foundation import Complaint, SignedApprovalRecord
from backend.app.db.models.oversight import EventClosure
from backend.app.db.session import get_db
from backend.app.enterprise_audit import make_audit_event
from backend.app.oversight import closure
from backend.app.request_context import AuthenticatedRequestContext, get_request_context
from backend.app.signer_training.router import is_trial

router = APIRouter(prefix="/api/v1/complaints", tags=["Resolve and close"])

COMPLETE, CONNECT = "COMPLETE", "CONNECT"
BUTTONS = {COMPLETE: "Resolve and close", CONNECT: "Resolve and mark ready to close in your QMS"}
# Complaints MDARIX itself made; any other source (an import) is owned by the QMS unless its record says MDARIX.
NATIVE_SOURCES = ("MDARIX_CASE", "MDARIX_SAMPLE", "MDARIX")
TOLD_CHANNELS = {
    "PHONE": "PHONE",
    "EMAIL": "EMAIL",
    "LETTER": "LETTER",
    "IN_PERSON": "IN_PERSON",
    "DISTRIBUTOR": "OTHER",
}
REOPEN_MIN = 20


class ToldIn(BaseModel):
    how: str = Field(default="", max_length=20)
    at: str | None = Field(default=None, max_length=40)
    note: str = Field(default="", max_length=rules.TEXT_MAX * 2)
    qms_letter_id: str = Field(default="", max_length=rules.TICKET_MAX * 2)
    reason: str = Field(default="", max_length=rules.TEXT_MAX * 2)


class ResolveIn(BaseModel):
    problem_code: str = Field(default="", max_length=120)
    service_record: ServiceRecordIn
    attribution: str | None = Field(default=None, max_length=30)
    attribution_reason: str = Field(default="", max_length=rules.TEXT_MAX * 2)
    classification: ClassificationIn
    customer_told: ToldIn
    not_known_reason: str = Field(default="", max_length=rules.TEXT_MAX * 2)
    known_behaviour_ref: str = Field(default="", max_length=240)
    change_reason: str = Field(default="", max_length=rules.TEXT_MAX * 2)
    take_over: bool = False
    # False: "Resolve" only (the disposition), when something else still blocks closing.
    close: bool = True
    seen_triggers: list[str] = Field(default_factory=list, max_length=20)
    seen_version: int = Field(default=0, ge=0)
    opened_at: str | None = Field(default=None, max_length=40)
    password: str = Field(min_length=1, max_length=128)
    mfa_code: str | None = Field(default=None, max_length=12)


class ReopenIn(BaseModel):
    reason: str = Field(max_length=rules.TEXT_MAX * 2)


def mode_of(db: Session, control_db: Session, tenant_id, complaint: Complaint) -> str:
    """MDARIX Complete closes a complaint only when MDARIX holds its record (OD-6; never one the QMS owns)."""
    from backend.app.intake.service import case_setup

    owner = complaint.record_owner
    if owner is None and complaint.source_system in NATIVE_SOURCES:
        owner = case_setup(db, tenant_id, is_trial(control_db, tenant_id))[0]
    return COMPLETE if owner == "MDARIX" else CONNECT


def _case_of(db: Session, tenant_id, complaint_id):
    from backend.app.db.models.intake import IntakeEvent

    return (
        db.query(IntakeEvent)
        .filter(IntakeEvent.tenant_id == tenant_id, IntakeEvent.complaint_id == complaint_id)
        .order_by(IntakeEvent.created_at)
        .first()
    )


def _reporters(db: Session, tenant_id, complaint_id) -> list:
    """The reporters with a contact, on the Cases this complaint came from (RT-28: each one is told)."""
    from backend.app.db.models.guides_communications import ExternalParty
    from backend.app.db.models.intake import IntakeEvent

    cases = [
        row.id
        for row in db.query(IntakeEvent.id).filter(
            IntakeEvent.tenant_id == tenant_id, IntakeEvent.complaint_id == complaint_id
        )
    ]
    if not cases:
        return []
    return (
        db.query(ExternalParty)
        .filter(
            ExternalParty.tenant_id == tenant_id,
            ExternalParty.party_type == "REPORTER",
            ExternalParty.intake_event_id.in_(cases),
            ExternalParty.contact_erased_at.is_(None),
            (ExternalParty.contact_email.is_not(None)) | (ExternalParty.contact_phone.is_not(None)),
        )
        .all()
    )


def similar_count(db: Session, tenant_id, complaint: Complaint, today) -> int:
    """Complaints on the same product and problem code in the last 12 months, this one excluded (the facts beside
    "why no investigation")."""
    code = (complaint.problem_code or "").strip().upper()
    if complaint.product_id is None or not code:
        return 0
    since = datetime.combine(today - timedelta(days=365), datetime.min.time(), tzinfo=timezone.utc)
    return (
        db.query(func.count(Complaint.id))
        .filter(
            Complaint.tenant_id == tenant_id,
            Complaint.product_id == complaint.product_id,
            func.upper(func.trim(Complaint.problem_code)) == code,
            Complaint.id != complaint.id,
            service.RECEIVED_AT >= since,
        )
        .scalar()
        or 0
    )


def offer(db: Session, tenant_id, complaint: Complaint, facts: dict) -> dict:
    """Whether Resolve and close is offered in full (rules.combined_offer): on the routine path, or on the watch with
    every relevant market signed and no trigger (B7-D7); and nothing else open."""
    items = closure.checklist(closure.facts(db, tenant_id, complaint))
    blocked = [item for item in items if item["result"] == closure.BLOCKED]
    routine = facts["routine"]["offered"]
    markets_signed = (
        facts["on_watch"]
        and not facts["triggers"]
        and facts["second_look"] is None
        and not any(item["code"] in ("MARKETS", "OBLIGATIONS") for item in blocked)
    )
    return {**rules.combined_offer(routine or markets_signed, blocked, routine), "routine": routine}


def _owner(db: Session, tenant_id, complaint_id):
    return closure.owner_of(
        closure.closure_row(db, tenant_id, complaint_id), closure.triage_record(db, tenant_id, complaint_id)
    )


@router.get("/{complaint_id}/resolve-and-close")
def resolve_screen(
    complaint_id: uuid.UUID,
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    tenant_id = uuid.UUID(ctx.tenant_id)
    disposition = screen(db, control_db, ctx, complaint_id)
    today = service.today_utc()
    facts = service.screen_facts(db, tenant_id, complaint_id, today)
    complaint = facts["complaint"]
    case = _case_of(db, tenant_id, complaint.id)
    mode = mode_of(db, control_db, tenant_id, complaint)
    owner = _owner(db, tenant_id, complaint.id)
    row = closure.closure_row(db, tenant_id, complaint.id)
    return {
        "disposition": disposition,
        "mode": mode,
        "button": BUTTONS[mode],
        "offer": offer(db, tenant_id, complaint, facts),
        "closed": row is not None and row.closed_at is not None,
        "prefill": {
            "troubleshooting": (case.troubleshooting if case else None) or "",
            "correction_type": rules.default_correction(case.requested if case else None),
            "service_ticket": (case.service_ticket if case else None) or complaint.service_reference or "",
            "problem_code": complaint.problem_code or "",
        },
        # Connect: the QMS sends the problem code; once the QMS owns the record it is read only here.
        "problem_code_read_only": complaint.record_owner == "EXTERNAL",
        "similar_last_12_months": similar_count(db, tenant_id, complaint, today),
        "owner": {
            "id": owner,
            "name": people(control_db, tenant_id, [owner]).get(owner) if owner else None,
            "is_me": owner == str(ctx.user_id),
        },
        "reporters_with_contact": len(_reporters(db, tenant_id, complaint.id)),
        "no_contact_reason": case.no_contact_reason if case else None,
        "reasons": rules.NO_INVESTIGATION_REASONS,
        "device_returned": rules.DEVICE_RETURNED,
        "told_how": rules.TOLD_HOW,
        "ticket_corrections": list(rules.TICKET_CORRECTIONS),
    }


def _audit(db, ctx, tenant_id, action, entity_type, entity_id, now, **details):
    db.add(
        make_audit_event(
            tenant_id=tenant_id,
            actor_ref=ctx.user_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            correlation_id=ctx.correlation_id,
            details=details,
            created_at=now,
        )
    )


def _closure_for_update(db: Session, tenant_id, complaint_id, now) -> EventClosure:
    row = (
        db.query(EventClosure)
        .filter(EventClosure.tenant_id == tenant_id, EventClosure.complaint_id == complaint_id)
        .with_for_update()
        .one_or_none()
    )
    if row is None:
        row = EventClosure(id=uuid.uuid4(), tenant_id=tenant_id, complaint_id=complaint_id, version=0, updated_at=now)
        db.add(row)
        db.flush()
    return row


def _told_at(value: str | None, now: datetime) -> datetime:
    try:
        parsed = datetime.fromisoformat(value) if value else None
    except ValueError:
        parsed = None
    if parsed is None or parsed.tzinfo is None or parsed > now:
        return now
    return parsed


@router.post("/{complaint_id}/resolve-and-close", dependencies=[DECIDERS])
def resolve_and_close(
    complaint_id: uuid.UUID,
    payload: ResolveIn,
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    from backend.app.communications import rules as comms
    from backend.app.db.models.guides_communications import CommunicationEntry
    from backend.app.evidence_workflow.people import current_person
    from backend.app.human_decision.rules import signature_hash

    tenant_id = uuid.UUID(ctx.tenant_id)
    me = str(ctx.user_id)
    found = service.complaint_row(db, tenant_id, complaint_id)
    if found is None:
        raise _error(404, "COMPLAINT_NOT_FOUND", "No such complaint in your organization")
    complaint = found[0]
    ref = service.ref_of(complaint)
    existing = closure.closure_row(db, tenant_id, complaint.id)
    if existing is not None and existing.closed_at is not None:
        raise _error(409, "ALREADY_CLOSED", "This complaint is closed: reopen it first, with your reason")
    mode = mode_of(db, control_db, tenant_id, complaint)
    connect = mode == CONNECT
    old_code = complaint.problem_code
    code = rules.collapse(payload.problem_code).upper()
    if complaint.record_owner == "EXTERNAL":
        code = old_code  # read only: the QMS sends it (an empty one stays empty; recurrence checks cannot run)
    elif not code:
        raise _error(
            422, "PROBLEM_CODE_REQUIRED", "Choose the problem code: recurrence and new failure modes depend on it"
        )
    # The triggers are read with the code chosen: a recurrence or a new failure mode it makes refuses the signature.
    complaint.problem_code = code
    db.flush()
    told = payload.customer_told.model_dump()
    told["how"] = rules.collapse(told["how"]).upper()
    problem = rules.customer_told_problem(told, connect)
    if problem:
        raise _error(422, "CUSTOMER_TOLD_REQUIRED", problem)
    owner = _owner(db, tenant_id, complaint.id)
    if owner and owner != me and not payload.take_over:
        name = people(control_db, tenant_id, [owner]).get(owner) or "a colleague"
        raise _error(409, "OWNER_TAKE_OVER", f"Take over as owner from {name}? Tick it to sign as the event owner")
    now = datetime.now(timezone.utc)
    told_record = {
        "how": told["how"],
        "at": _told_at(told.get("at"), now).isoformat(),
        "note": rules.collapse(told.get("note")) or None,
        "qms_letter_id": rules.collapse(told.get("qms_letter_id")) or None,
        "reason": rules.collapse(told.get("reason")) or None,
    }
    pre = service.screen_facts(db, tenant_id, complaint.id, service.today_utc())
    answered = rules.answered_triggers(pre["triggers"], payload.known_behaviour_ref)
    unrecorded = rules.routine_unrecorded(service.watch_record(complaint))
    routine = service.routine_offer(pre["on_watch"], pre["second_look"], answered, unrecorded)["offered"]
    request = SignRequest(
        branch=rules.SERVICE_LEVEL,
        not_known_reason=payload.not_known_reason,
        service_record=payload.service_record,
        attribution=payload.attribution,
        attribution_reason=payload.attribution_reason,
        classification=payload.classification,
        change_reason=payload.change_reason,
        seen_triggers=payload.seen_triggers,
        seen_version=payload.seen_version,
        routine=routine,
        opened_at=payload.opened_at,
        known_behaviour_ref=payload.known_behaviour_ref,
        password=payload.password,
        mfa_code=payload.mfa_code,
    )

    def before_sign(facts: dict) -> None:
        if not payload.close:
            return
        found_offer = offer(db, tenant_id, complaint, {**facts, "triggers": answered})
        if not found_offer["full"]:
            raise _error(
                409,
                "RESOLVE_AND_CLOSE_NOT_OFFERED",
                "Resolve and close is not offered: "
                + ("; ".join(found_offer["blocking"]) or "the routine path is not open and not every market is signed")
                + ". Resolve only, or finish them first",
                blocking=found_offer["blocking"],
            )

    def before_commit(facts: dict, record_id, signed_at) -> None:
        if code != old_code:
            _audit(
                db,
                ctx,
                tenant_id,
                "PROBLEM_CODE_SET",
                "Complaint",
                complaint.id,
                signed_at,
                complaint=ref,
                old=old_code,
                new=code,
            )
        for party in _reporters(db, tenant_id, complaint.id) if told_record["how"] != rules.NOT_POSSIBLE else []:
            db.add(
                CommunicationEntry(
                    tenant_id=tenant_id,
                    complaint_id=complaint.id,
                    intake_event_id=party.intake_event_id,
                    party_id=party.id,
                    direction=comms.SENT,
                    purpose=comms.RESPONSE,
                    subject=f"Resolution of {ref}"[:400],
                    note=told_record["note"],
                    channel=TOLD_CHANNELS.get(told_record["how"], "OTHER"),
                    occurred_at=datetime.fromisoformat(told_record["at"]),
                    logged_at=signed_at,
                    logged_by=me,
                    qms_reference=told_record["qms_letter_id"],
                    updated_at=signed_at,
                )
            )
        if not payload.close:
            return
        row = _closure_for_update(db, tenant_id, complaint.id, signed_at)
        if owner != me:
            action = "EVENT_OWNER_TAKEN_OVER" if owner else "EVENT_OWNER_SET"
            row.owner_id, row.owner_set_by, row.owner_set_at = me, me, signed_at
            _audit(db, ctx, tenant_id, action, closure.OBJECT_TYPE, row.id, signed_at, complaint=ref, old=owner, new=me)
        db.flush()
        items = closure.checklist(closure.facts(db, tenant_id, complaint))
        still = [item["label"] for item in items if item["result"] == closure.BLOCKED]
        if still:
            raise _error(409, "STILL_OPEN", "Not closed: " + "; ".join(still), blocking=still)
        version = row.version + 1
        print_ = closure.fingerprint(complaint.id, items)
        meaning = closure.signature_meaning(ref, version, 0) if connect else closure.close_meaning(ref, version)
        person = current_person(control_db, ctx)
        ready = SignedApprovalRecord(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            object_type=closure.OBJECT_TYPE,
            object_id=row.id,
            object_version=f"v{version}",
            decision_type=closure.DECISION_TYPE,
            decision="APPROVED",
            remarks="Resolve and close: checklist clear",
            signer_user_id=me,
            signer_role=person.role_for(QUALITY_REVIEW) or person.role_for(SIGNAL_TRIAGE) or "UNKNOWN",
            signature_meaning=meaning,
            content_fingerprint=print_,
            signature_hash=signature_hash(print_, me, f"v{version}"),
            status="SIGNED",
            signed_at=signed_at,
            created_at=signed_at,
        )
        control_db.add(ready)
        details = {"complaint": ref, "version": version, "signature_id": str(ready.id), "fingerprint": print_}
        details["disposition_signature_id"] = str(record_id)
        _audit(
            control_db,
            ctx,
            tenant_id,
            "EVENT_READY_TO_CLOSE_SIGNED",
            closure.OBJECT_TYPE,
            row.id,
            signed_at,
            open_items=0,
            **details,
        )
        row.version, row.ready_state, row.ready_reason = version, "READY", None
        row.checklist, row.content_fingerprint = items, print_
        row.signed_record_id, row.signed_by, row.signed_at, row.updated_at = ready.id, me, signed_at, signed_at
        row.qms_filing_ref = row.filed_by = row.filed_at = None
        if not connect:
            row.closed_at, row.closed_by = signed_at, me
            complaint.status = "closed"
            _audit(
                db,
                ctx,
                tenant_id,
                "COMPLAINT_CLOSED",
                "Complaint",
                complaint.id,
                signed_at,
                complaint=ref,
                version=version,
            )

    sign(db, control_db, ctx, complaint.id, request, {"customer_told": told_record}, before_sign, before_commit)
    return resolve_screen(complaint.id, db, control_db, ctx)


def reopen_closed(
    db: Session, tenant_id, complaint_id, actor: str, reason: str, trigger: str, now, correlation_id=None
) -> bool:
    """Reopen a complaint MDARIX closed (Complete): the closure signature is superseded (ready to close is signed again
    later), the reason and trigger audited. Flushes; the caller commits. False when it was not closed in MDARIX."""
    row = (
        db.query(EventClosure)
        .filter(EventClosure.tenant_id == tenant_id, EventClosure.complaint_id == complaint_id)
        .with_for_update()
        .one_or_none()
    )
    if row is None or row.closed_at is None:
        return False
    complaint = db.query(Complaint).filter(Complaint.tenant_id == tenant_id, Complaint.id == complaint_id).one()
    row.reopened_at, row.reopened_by, row.reopen_reason = now, actor, reason
    row.closed_at = row.closed_by = row.ready_state = None
    row.updated_at = now
    complaint.status = "open"
    db.add(
        make_audit_event(
            tenant_id=tenant_id,
            actor_ref=actor,
            action="COMPLAINT_REOPENED",
            entity_type="Complaint",
            entity_id=complaint_id,
            correlation_id=correlation_id,
            reason=reason,
            details={"complaint": service.ref_of(complaint), "trigger": trigger, "superseded_version": row.version},
            created_at=now,
        )
    )
    db.flush()
    return True


@router.post("/{complaint_id}/reopen", dependencies=[DECIDERS])
def reopen(
    complaint_id: uuid.UUID,
    payload: ReopenIn,
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    tenant_id = uuid.UUID(ctx.tenant_id)
    reason = rules.collapse(payload.reason)
    if len(reason) < REOPEN_MIN:
        raise _error(422, "REASON_REQUIRED", f"Say in at least {REOPEN_MIN} characters why the complaint reopens")
    if service.complaint_row(db, tenant_id, complaint_id) is None:
        raise _error(404, "COMPLAINT_NOT_FOUND", "No such complaint in your organization")
    if not reopen_closed(
        db, tenant_id, complaint_id, str(ctx.user_id), reason, "MANUAL", datetime.now(timezone.utc), ctx.correlation_id
    ):
        raise _error(409, "NOT_CLOSED", "Only a complaint MDARIX closed reopens here; in Connect your QMS reopens it")
    db.commit()
    return resolve_screen(complaint_id, db, control_db, ctx)
