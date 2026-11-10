"""B7b step 10 (spec 4.3, 4.4 steps 5-6, 4.6): "E-mail to check" and the intake address. Every route answers 404
while e-mail intake is switched off (``MDARIX_EMAIL_INTAKE``).

- ``GET /api/v1/email-intake/messages``: the messages to check (or ``?state=NOT_A_CASE`` etc.), for the people who
  work Cases. The sender is shown by domain only, marked unverified.
- "Make it a case" is the ordinary ``POST /api/v1/intake`` with ``inbound_message_id`` (intake/router.py): channel
  E-mail, the Message-ID as the reference and our server's receipt time as Received; the clean files move to the Case.
- ``POST .../{id}/add-to-case``: an EMAIL addendum ("said by the reporter") on the Case; the clean files move with it.
- ``POST .../{id}/not-a-case``: a reason (spam, auto-reply, setup message, internal, duplicate, other). On a message
  with a harm or fault word only a quality reviewer may choose it. Audited; the raw message is kept 30 days (B7-D11).
- ``GET .../{id}/raw``: the original message, for the OD-1 contact roles only; every view audited.
- ``GET/PUT /api/v1/email-intake/settings`` and ``POST .../settings/rotate``: the Customer Admin's address (on/off,
  rotate, allowed sender domains, daily limit). A free trial gets no real address (B7-D9): its SAMPLE e-mail shows the
  flow instead.
"""

from __future__ import annotations

import uuid
from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.app import mail_in
from backend.app.access.permissions import CASE_CLASSIFY, CASE_LOG, QUALITY_REVIEW, effective_permissions
from backend.app.db.data_plane import get_data_plane_db
from backend.app.db.models.intake import CaseAttachment, InboundMessage
from backend.app.db.session import get_db
from backend.app.enterprise_audit import make_audit_event
from backend.app.intake import service
from backend.app.intake.router import require_any_permission_audited
from backend.app.mail_in import processing
from backend.app.request_context import AuthenticatedRequestContext, get_request_context


def _switched_on() -> None:
    if not mail_in.enabled():
        raise HTTPException(404, detail={"code": "EMAIL_INTAKE_OFF", "message": "E-mail intake is switched off"})


router = APIRouter(prefix="/api/v1/email-intake", tags=["E-mail intake"], dependencies=[Depends(_switched_on)])
READERS = require_any_permission_audited(CASE_LOG, CASE_CLASSIFY, QUALITY_REVIEW)
STATES = ("NEW", "MADE_CASE", "ADDED_TO_CASE", "NOT_A_CASE")


def _error(status: int, code: str, message: str) -> HTTPException:
    return HTTPException(status, detail={"code": code, "message": message})


def _audit(db: Session, ctx, action: str, row: InboundMessage, **details) -> None:
    db.add(
        make_audit_event(
            tenant_id=row.tenant_id,
            actor_ref=ctx.user_id,
            action=action,
            entity_type="InboundMessage",
            entity_id=row.id,
            correlation_id=ctx.correlation_id,
            details=details,
        )
    )


def view(row: InboundMessage) -> dict:
    flags = row.flags or {}
    return {
        "id": str(row.id),
        "state": row.state,
        "received_at": service._iso(row.received_at),
        "from_domain": row.from_domain,
        "sender_verified": False,  # SPF, DKIM and DMARC are not checked (spec 4.5)
        "subject": row.subject_masked,
        "words": (row.draft or {}).get("words") or "",
        "identifiers": (row.draft or {}).get("identifiers") or {},
        "site_suggestion": (row.draft or {}).get("site"),
        "note": (row.draft or {}).get("note"),
        "checked": bool(flags.get("checked")),
        "harm_words": flags.get("harm_words") or [],
        "fault_words": flags.get("fault_words") or [],
        "may_not_be_english": bool(flags.get("may_not_be_english")),
        "add_to_case": flags.get("add_to_case"),
        "possible_duplicate": flags.get("possible_duplicate"),
        "possibly_known_earlier": row.header_dates or [],
        "attachments": row.attachments or [],
        "message_id": row.message_id,
        "reason": row.reason,
        "case_id": str(row.intake_event_id) if row.intake_event_id else None,
        "decided_at": service._iso(row.decided_at),
        "purge_after": service._iso(row.purge_after),
        "sample": row.message_id.startswith("<SAMPLE-"),
    }


def message_or_404(db: Session, tenant_id, message_id, lock: bool = False) -> InboundMessage:
    query = db.query(InboundMessage).filter(InboundMessage.tenant_id == tenant_id, InboundMessage.id == message_id)
    row = (query.with_for_update() if lock else query).first()
    if row is None:
        raise _error(404, "MESSAGE_NOT_FOUND", "No such e-mail in your organization")
    return row


def open_message(db: Session, tenant_id, message_id) -> InboundMessage:
    """A message still waiting for a decision (locked), else 409."""
    row = message_or_404(db, tenant_id, message_id, lock=True)
    if row.state != "NEW":
        raise _error(409, "MESSAGE_DECIDED", "Someone already decided this e-mail")
    return row


def to_case(db: Session, row: InboundMessage, event_id, state: str, actor, now) -> None:
    """The decision that puts a message on a Case: the clean files move with it; the raw message is kept as long as
    the Case record (B7-D11)."""
    row.state, row.intake_event_id, row.decided_by, row.decided_at = state, event_id, str(actor), now
    row.purge_after, row.version = None, row.version + 1
    db.query(CaseAttachment).filter(
        CaseAttachment.tenant_id == row.tenant_id,
        CaseAttachment.inbound_message_id == row.id,
        CaseAttachment.usable.is_(True),
    ).update({"intake_event_id": event_id}, synchronize_session=False)


SAMPLE_ID = "<SAMPLE-EMAIL-1@intake.mdarix.com>"
SAMPLE_EML = (
    "From: Ward Desk <ward.desk@citycare-hospital.example>\r\n"
    "To: cases-sample@intake.mdarix.com\r\n"
    "Subject: PulseWatch monitor alarm keeps sounding\r\n"
    f"Message-ID: {SAMPLE_ID}\r\n"
    "Content-Type: text/plain; charset=utf-8\r\n\r\n"
    "Hello, our PulseWatch monitor on ward 4 gave a low battery alarm three times last night although it was on "
    "charge. Serial number: PW-20931. We swapped to a spare unit; nobody was harmed. Can someone check it?\r\n"
    "-- \r\nWard Desk, CityCare Hospital (SAMPLE: fictional)\r\n"
)


def ensure_sample(db: Session, control_db: Session, tenant_id) -> None:
    """B7-D9: a free trial has no real address; one SAMPLE e-mail (fictional, no personal data) shows the flow."""
    from object_storage.service import ObjectStorageService

    from backend.app.signer_training.router import is_trial

    if not is_trial(control_db, tenant_id):
        return
    known = db.query(InboundMessage.id).filter(
        InboundMessage.tenant_id == tenant_id, InboundMessage.message_id == SAMPLE_ID
    )
    if known.first() is not None:
        return
    now, row_id, content = service.now_utc(), uuid.uuid4(), SAMPLE_EML.encode()
    storage = ObjectStorageService()
    stored = storage.put(str(tenant_id), f"mail-{row_id.hex}", content, content_type="message/rfc822", internal=True)
    row = InboundMessage(
        id=row_id,
        tenant_id=tenant_id,
        message_id=SAMPLE_ID,
        received_at=now,
        raw_object_key=stored["object_key"],
        raw_size=len(content),
        flags={},
        created_at=now,
    )
    db.add(row)
    db.flush()
    processing.analyse(db, control_db, tenant_id, row, content, storage)
    db.commit()


@router.get("/messages", dependencies=[READERS])
def list_messages(
    state: str = "NEW",
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    if state not in STATES:
        raise _error(422, "UNKNOWN_STATE", "Choose one of: " + ", ".join(STATES))
    if state == "NEW":
        ensure_sample(db, control_db, uuid.UUID(str(ctx.tenant_id)))
    rows = (
        db.query(InboundMessage)
        .filter(InboundMessage.tenant_id == uuid.UUID(str(ctx.tenant_id)), InboundMessage.state == state)
        .order_by(InboundMessage.received_at.desc())
        .limit(200)
        .all()
    )
    # Spec 4.4 step 6: the first person to see a message to check is the one who opened it (no other record exists).
    unopened = [row for row in rows if row.state == "NEW" and not (row.flags or {}).get("opened_by")]
    for row in unopened:
        row.flags = {**(row.flags or {}), "opened_by": str(ctx.user_id), "opened_at": service.now_utc().isoformat()}
    if unopened:
        db.commit()
    return {"items": [view(row) for row in rows], "reasons": list(processing.NOT_A_CASE_REASONS)}


class AddToCaseIn(BaseModel):
    case_id: uuid.UUID


@router.post("/messages/{message_id}/add-to-case", dependencies=[require_any_permission_audited(CASE_LOG)])
def add_to_case(
    message_id: uuid.UUID,
    payload: AddToCaseIn,
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    from backend.app.db.models.intake import CaseAddendum
    from backend.app.intake import case_rules
    from backend.app.intake.router import _commit, _event_or_404, _new_information, intake_detail

    tenant_id = uuid.UUID(str(ctx.tenant_id))
    row = open_message(db, tenant_id, message_id)
    event = _event_or_404(db, tenant_id, payload.case_id, lock=True)
    if event.status == case_rules.VOIDED:
        raise _error(409, "CASE_VOIDED", "This case was withdrawn: entered in error")
    now = service.now_utc()
    words = (row.draft or {}).get("words") or "(no readable words)"
    db.add(
        CaseAddendum(
            tenant_id=tenant_id,
            intake_event_id=event.id,
            kind="EMAIL",
            said_by_role="REPORTER",
            said_at=row.received_at,
            said_zone="UTC",
            text=words,
            masked={"personal_data": 1},
            source_system="EMAIL",
            created_by=str(ctx.user_id),
            created_at=now,
        )
    )
    to_case(db, row, event.id, "ADDED_TO_CASE", ctx.user_id, now)
    _audit(db, ctx, "EMAIL_ADDED_TO_CASE", row, case=event.reference)
    db.flush()
    _new_information(db, control_db, ctx, event, words, now, "An e-mail added to the case")
    _commit(db, control_db)
    return intake_detail(event.id, db, control_db, ctx)


class NotACaseIn(BaseModel):
    reason: str = Field(max_length=30)
    note: str = Field(default="", max_length=500)


@router.post("/messages/{message_id}/not-a-case", dependencies=[READERS])
def not_a_case(
    message_id: uuid.UUID,
    payload: NotACaseIn,
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    tenant_id = uuid.UUID(str(ctx.tenant_id))
    reason = payload.reason.strip().upper()
    if reason not in processing.NOT_A_CASE_REASONS:
        raise _error(422, "REASON_NEEDED", "Choose why it is not a case")
    note = payload.note.strip()
    if reason == "OTHER" and len(note) < 10:
        raise _error(422, "REASON_NEEDED", "Say why in at least 10 characters")
    row = open_message(db, tenant_id, message_id)
    flags = row.flags or {}
    # A downward decision on words that may hide a complaint: a quality reviewer's (EM-12), audited like B2's.
    if (flags.get("harm_words") or flags.get("fault_words")) and QUALITY_REVIEW not in effective_permissions(
        control_db, ctx
    ):
        _audit(db, ctx, "EMAIL_NOT_A_CASE_REFUSED", row, reason=reason)
        db.commit()
        raise _error(403, "QUALITY_REVIEWER_NEEDED", "It has harm or fault words: a quality reviewer decides")
    from backend.app.signer_training.router import is_trial

    # Outside a trial, the reviewer who opened the message does not also dismiss it (four eyes, like B2's SAME_PERSON).
    if (
        (flags.get("harm_words") or flags.get("fault_words"))
        and flags.get("opened_by") == str(ctx.user_id)
        and not is_trial(control_db, tenant_id)
    ):
        _audit(db, ctx, "EMAIL_NOT_A_CASE_REFUSED", row, reason=reason, why="SAME_PERSON")
        db.commit()
        raise _error(
            403, "SAME_PERSON", "You opened this e-mail first: another quality reviewer decides it is not a case"
        )
    now = service.now_utc()
    row.state, row.reason, row.decided_by, row.decided_at = "NOT_A_CASE", reason, str(ctx.user_id), now
    row.purge_after, row.version = now + processing.KEEP_NOT_A_CASE, row.version + 1
    _audit(db, ctx, "EMAIL_NOT_A_CASE", row, reason=reason, note=processing._mask(note) or None)
    db.commit()
    return view(row)


@router.get("/messages/{message_id}/raw")
def raw_message(
    message_id: uuid.UUID,
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """OD-1: the original message (sender, signature, attachments) for the contact roles only; each view audited."""
    from object_storage.service import ObjectStorageService

    from backend.app.access.permissions import effective_roles
    from backend.app.intake.router import CONTACT_READERS
    from backend.app.role_codes import role_code

    tenant_id = uuid.UUID(str(ctx.tenant_id))
    row = message_or_404(db, tenant_id, message_id)
    if not {role_code(role) for role in effective_roles(control_db, ctx)} & CONTACT_READERS:
        _audit(db, ctx, "EMAIL_RAW_REFUSED", row)
        db.commit()
        raise _error(403, "PERMISSION_DENIED", "The original e-mail is for the people who handle contacts")
    if not row.raw_object_key:
        raise _error(404, "MESSAGE_PURGED", "The original e-mail is no longer kept")
    content = ObjectStorageService().get(str(tenant_id), row.raw_object_key)
    _audit(db, ctx, "EMAIL_RAW_OPENED", row)
    db.commit()
    return Response(
        content=content,
        media_type="message/rfc822",
        headers={"Content-Disposition": f'attachment; filename="email-{row.id.hex[:8]}.eml"'},
    )


def purge_expired(db: Session, tenant_id, now) -> int:
    """B7-D11: a "Not a case" message's raw bytes and files are deleted 30 days after the decision (the 15-minute
    pass); the row stays as PURGED, so nothing disappears without a trace."""
    from object_storage.service import ObjectStorageService

    rows = (
        db.query(InboundMessage)
        .filter(
            InboundMessage.tenant_id == tenant_id,
            InboundMessage.state == "NOT_A_CASE",
            InboundMessage.purge_after < now,
        )
        .limit(500)
        .all()
    )
    if not rows:
        return 0
    storage = ObjectStorageService()
    for row in rows:
        files = db.query(CaseAttachment).filter(
            CaseAttachment.tenant_id == tenant_id, CaseAttachment.inbound_message_id == row.id
        )
        for key in [row.raw_object_key] + [item.object_key for item in files]:
            if key:
                try:
                    storage.delete(str(tenant_id), key)
                except FileNotFoundError:
                    pass
        files.delete(synchronize_session=False)
        row.state, row.raw_object_key, row.attachments, row.draft = "PURGED", None, [], {}
        row.subject_masked = None
    return len(rows)


# --------------------------------------------------------------------------------------------- the address (settings)


def _customer_admin(request: Request, control_db: Session = Depends(get_db)):
    from backend.app.access.authz import _authenticated_user
    from backend.app.role_codes import is_customer_admin_role

    user = _authenticated_user(request, control_db)
    if not is_customer_admin_role(user.role):
        raise _error(403, "CUSTOMER_ADMIN_REQUIRED", "The Customer Admin sets the intake address")
    return user


def _settings_view(db: Session, control_db: Session, tenant_id) -> dict:
    from backend.app.mail_in import addresses
    from backend.app.oversight import service as oversight
    from backend.app.signer_training.router import is_trial

    settings = oversight.settings_row(db, tenant_id)
    trial = is_trial(control_db, tenant_id)
    return {
        **(addresses.view(control_db, tenant_id, service.now_utc()) if not trial else {"address": None, "on": False}),
        "trial": trial,
        "allowed_domains": list(settings.mail_allowed_domains or []) if settings else [],
        "daily_limit": settings.mail_daily_limit if settings else 200,
    }


@router.get("/settings")
def get_settings(
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    user=Depends(_customer_admin),
):
    return _settings_view(db, control_db, user.tenant_id)


class SettingsIn(BaseModel):
    on: bool
    allowed_domains: list[str] = Field(default_factory=list, max_length=50)
    daily_limit: int = Field(default=200, ge=1, le=5000)


def _no_trial(control_db: Session, tenant_id) -> None:
    from backend.app.signer_training.router import is_trial

    if is_trial(control_db, tenant_id):
        raise _error(409, "TRIAL_NO_ADDRESS", "A free trial has no real intake address: try the SAMPLE e-mail")


@router.put("/settings")
def put_settings(
    payload: SettingsIn,
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    user=Depends(_customer_admin),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    import re

    from backend.app.db.models.oversight import OversightSettings
    from backend.app.mail_in import addresses
    from backend.app.oversight import service as oversight

    tenant_id = user.tenant_id
    _no_trial(control_db, tenant_id)
    domains = sorted({item.strip().lower().lstrip("@") for item in payload.allowed_domains if item.strip()})
    if any(not re.fullmatch(r"[a-z0-9-]+(\.[a-z0-9-]+)+", item) for item in domains):
        raise _error(422, "DOMAIN_INVALID", "Write each sender domain like hospital.example")
    settings = oversight.settings_row(db, tenant_id)
    if settings is None:
        settings = OversightSettings(tenant_id=tenant_id)
        db.add(settings)
    settings.mail_allowed_domains, settings.mail_daily_limit = domains, payload.daily_limit
    now = service.now_utc()
    addresses.switch(control_db, tenant_id, payload.on, now)
    db.add(
        make_audit_event(
            tenant_id=tenant_id,
            actor_ref=ctx.user_id,
            action="EMAIL_INTAKE_SETTINGS_CHANGED",
            entity_type="EmailIntake",
            entity_id=tenant_id,
            correlation_id=ctx.correlation_id,
            details={"on": payload.on, "allowed_domains": domains, "daily_limit": payload.daily_limit},
        )
    )
    control_db.commit()
    db.commit()
    return _settings_view(db, control_db, tenant_id)


@router.post("/settings/rotate")
def rotate_address(
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    user=Depends(_customer_admin),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    from backend.app.mail_in import addresses

    _no_trial(control_db, user.tenant_id)
    addresses.rotate(control_db, user.tenant_id, service.now_utc())
    db.add(
        make_audit_event(
            tenant_id=user.tenant_id,
            actor_ref=ctx.user_id,
            action="EMAIL_INTAKE_ADDRESS_ROTATED",
            entity_type="EmailIntake",
            entity_id=user.tenant_id,
            correlation_id=ctx.correlation_id,
            details={"old_address_kept_days": addresses.ROTATE_GRACE // timedelta(days=1)},
        )
    )
    control_db.commit()
    db.commit()
    return _settings_view(db, control_db, user.tenant_id)
