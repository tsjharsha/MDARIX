"""A free trial's request for a pilot conversation (the paid step after the trial; "MVP" in code), from Next steps in the trial workspace.

Anyone in the trial may ask. They say what they expect from the MVP, the products, sites and systems they have in mind
and, if they like, how and when to reach them. The MVP runs on a dedicated MDARIX database for the organization and
uses its real data only, so the trial's data is moved into it only on request, and only when the organization has
removed the sample data and imported its own (``data_move``, checked here as well as on the screen). Otherwise nothing
is moved and the trial's data is deleted 30 days after the trial ends, as for every trial.

While a request that asks to move the data is open, the trial's data is not deleted (held, for at most 90 days after
the trial ends); once it is closed, the data is deleted 14 days later at the earliest (backend/app/trial/retention.py).

One open request (NEW or CONTACTED) per organization: asking again updates it. The MDARIX team sees every request in
Platform Admin (Demo and trial requests) and by email (``MDARIX_DEMO_ALERT_EMAIL``, else ``MDARIX_TRIAL_ALERT_EMAIL``,
as for the trial's demo request), marks it contacted when it has replied and closes it when the conversation is over;
a closed request lets the organization ask again. The requester gets the answer on screen; like the trial's demo
request, no confirmation email is sent. Each step is audited (``TRIAL_MVP_REQUESTED``, ``TRIAL_MVP_REQUEST_UPDATED``,
``TRIAL_MVP_REQUEST_STATUS_CHANGED``).

The request (``trial_mvp_requests``, md46) is a tenant table under row-level security and holds the requester's name and
email, so it is deleted with the trial's data (backend/app/tenant_purge.py).
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.db.models.foundation import AuthUser, Capa, Complaint, Investigation, LotBatch, Product, Risk, Tenant
from backend.app.db.models.stage2 import TrialMvpRequest
from backend.app.trial.sample_data import SAMPLE_SOURCE
from backend.app.trial.sample_removal import OWN_SOURCES

STATUSES = ("NEW", "CONTACTED", "CLOSED")
OPEN = ("NEW", "CONTACTED")
EXPECTATIONS_MIN = 10
TEXT_MAX = 2000
CONTACT_MAX = 200

# The records the sample and the organization's own uploads are counted in (as Getting started counts them).
_RECORDS = (Product, LotBatch, Complaint, Investigation, Capa, Risk)
_PHONE = re.compile(r"^\+?[0-9 ()\-.]{7,30}$")


def _error(status: int, code: str, message: str, field: str | None = None) -> HTTPException:
    detail = {"code": code, "message": message}
    if field:
        detail["field"] = field
    return HTTPException(status, detail=detail)


def _lines(value: str | None, limit: int) -> str | None:
    """The text with each line's runs of spaces collapsed and empty lines left out; None when nothing is left."""
    kept = [" ".join(line.split()) for line in (value or "").splitlines()]
    return "\n".join(line for line in kept if line)[:limit] or None


def _count(data: Session, tenant_id: uuid.UUID, sources: tuple[str, ...]) -> int:
    return sum(
        int(
            data.query(func.count(model.id))
            .filter(model.tenant_id == tenant_id, model.source_system.in_(sources))
            .scalar()
            or 0
        )
        for model in _RECORDS
    )


def data_move(data: Session, tenant_id: uuid.UUID) -> dict:
    """Whether the organization may ask to move its trial data into the MVP: only once the sample data is removed and
    its own data is imported. ``reason`` says which of the two is missing (the sample first)."""
    sample = _count(data, tenant_id, (SAMPLE_SOURCE,))
    own = _count(data, tenant_id, OWN_SOURCES)
    reason = "SAMPLE_DATA_PRESENT" if sample else ("NO_OWN_DATA" if not own else None)
    return {"allowed": reason is None, "reason": reason, "sample_records": sample, "own_records": own}


def latest(db: Session, tenant_id: uuid.UUID) -> TrialMvpRequest | None:
    return (
        db.query(TrialMvpRequest)
        .filter(TrialMvpRequest.tenant_id == tenant_id)
        .order_by(TrialMvpRequest.created_at.desc())
        .first()
    )


def _open(db: Session, tenant_id: uuid.UUID) -> TrialMvpRequest | None:
    return (
        db.query(TrialMvpRequest)
        .filter(TrialMvpRequest.tenant_id == tenant_id, TrialMvpRequest.status.in_(OPEN))
        .with_for_update()
        .first()
    )


def view(row: TrialMvpRequest | None) -> dict | None:
    """The request as the organization sees it."""
    if row is None:
        return None
    return {
        "id": str(row.id),
        "status": row.status,
        "expectations": row.expectations,
        "scope": row.scope,
        "phone": row.phone,
        "contact_preference": row.contact_preference,
        "move_trial_data": row.move_trial_data,
        "requested_by": row.display_name,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


def _audit(
    db: Session, tenant_id, actor, action: str, row: TrialMvpRequest, now: datetime, details: dict | None = None
) -> None:
    from backend.app.enterprise_audit import make_audit_event

    db.add(
        make_audit_event(
            tenant_id=tenant_id,
            actor_ref=str(actor),
            action=action,
            entity_type="TrialMvpRequest",
            entity_id=row.id,
            # What was asked, not the words or the contact details (those stay in the request).
            details={
                "request_id": str(row.id),
                "status": row.status,
                "move_trial_data": row.move_trial_data,
                **(details or {}),
            },
            created_at=now,
        )
    )


def submit(
    db: Session,
    data: Session,
    tenant_id: uuid.UUID,
    user: AuthUser,
    *,
    expectations: str | None,
    scope: str | None,
    phone: str | None,
    contact_preference: str | None,
    move_trial_data: bool,
    days_left: int,
    now: datetime | None = None,
) -> tuple[TrialMvpRequest, str]:
    """Ask for an MVP conversation, or update the open request. Returns (request, REQUESTED or UPDATED). Commits."""
    now = now or datetime.now(timezone.utc)
    wanted = _lines(expectations, TEXT_MAX)
    if not wanted or len(wanted) < EXPECTATIONS_MIN:
        raise _error(
            422, "MVP_REQUEST_INVALID", "Tell us in a sentence or two what you expect from the pilot", "expectations"
        )
    number = " ".join((phone or "").split()) or None
    if number and (not _PHONE.match(number) or len(re.sub(r"\D", "", number)) < 7):
        raise _error(422, "MVP_REQUEST_INVALID", "Enter a valid phone number", "phone")
    move = data_move(data, tenant_id)
    if move_trial_data and not move["allowed"]:
        raise _error(
            422,
            "MVP_DATA_MOVE_NOT_ALLOWED",
            "Trial data can be moved into the pilot only once the sample data is removed and your own data is imported",
            "move_trial_data",
        )
    fields = {
        "expectations": wanted,
        "scope": _lines(scope, TEXT_MAX),
        "phone": number,
        "contact_preference": " ".join((contact_preference or "").split())[:CONTACT_MAX] or None,
        "move_trial_data": bool(move_trial_data),
        "context": {
            "days_left": days_left,
            "sample_records": move["sample_records"],
            "own_records": move["own_records"],
        },
    }
    # Two people asking at the same moment: the open-request index lets one in, and the other updates it.
    for _attempt in range(2):
        row = _open(db, tenant_id)
        outcome = "UPDATED" if row is not None else "REQUESTED"
        if row is None:
            tenant = db.get(Tenant, tenant_id)
            row = TrialMvpRequest(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                status="NEW",
                organization=((tenant.name if tenant else None) or user.company or "Trial organization")[:160],
                created_at=now,
            )
            db.add(row)
        row.requested_by = user.id
        row.display_name = (user.display_name or user.username)[:120]
        row.email = user.username
        row.updated_at = now
        for name, value in fields.items():
            setattr(row, name, value)
        _audit(
            db,
            tenant_id,
            user.id,
            "TRIAL_MVP_REQUESTED" if outcome == "REQUESTED" else "TRIAL_MVP_REQUEST_UPDATED",
            row,
            now,
        )
        try:
            db.commit()
        except IntegrityError:
            db.rollback()
            continue
        db.refresh(row)
        return row, outcome
    raise _error(409, "MVP_REQUEST_BUSY", "Your request could not be saved just now. Please try again.")


def overview(db: Session) -> dict:
    """Every request, newest first, for the Platform Administrator: the organization, who asked and how to reach them,
    what they expect, the trial's days left, when its data is deleted (``retention``: held while a request to move it
    is open), and the counts per status."""
    from backend.app.trial import retention
    from backend.app.trial.early_exit import _days_until, _trial_ends

    from backend.app.paging import open_first

    # Every open request (new or contacted), however old: it holds the trial's data. Then the newest 500 closed ones.
    rows = open_first(
        db.query(TrialMvpRequest),
        TrialMvpRequest.id,
        TrialMvpRequest.status.in_(OPEN),
        [TrialMvpRequest.created_at.desc()],
        500,
    )
    tenant_ids = {row.tenant_id for row in rows}
    tenants = {tenant.id: tenant for tenant in db.query(Tenant).filter(Tenant.id.in_(tenant_ids))} if tenant_ids else {}
    ends = _trial_ends(db, tenant_ids)
    now = datetime.now(timezone.utc)
    # Only trials still holding data in the trial store have a deletion date (a converted one keeps its data).
    kept = {plan["tenant"].id: retention.plan_view(plan) for plan in retention.plans(db, now, tenant_ids)}
    items = []
    for row in rows:
        tenant = tenants.get(row.tenant_id)
        end = ends.get(row.tenant_id)
        items.append(
            {
                **(view(row) or {}),
                "email": row.email,
                "organization": row.organization,
                "tenant_id": str(row.tenant_id),
                "tenant_business_id": tenant.business_id if tenant else None,
                "context": row.context,
                "days_left": _days_until(end, now) if end is not None else None,
                "handled_at": row.handled_at.isoformat() if row.handled_at else None,
                "note": row.note,
                "retention": kept.get(row.tenant_id),
            }
        )
    return {
        "items": items,
        "counts": {status: sum(1 for item in items if item["status"] == status) for status in STATUSES},
    }


def change_status(
    db: Session, request_id: uuid.UUID, admin: AuthUser, status: str, note: str | None, now: datetime | None = None
) -> TrialMvpRequest:
    """Mark a request contacted, closed or new again, with an optional internal note. Commits."""
    now = now or datetime.now(timezone.utc)
    wanted = (status or "").strip().upper()
    if wanted not in STATUSES:
        raise _error(422, "MVP_REQUEST_STATUS_INVALID", "Status must be new, contacted or closed")
    row = db.query(TrialMvpRequest).filter(TrialMvpRequest.id == request_id).with_for_update().first()
    if row is None:
        raise _error(404, "MVP_REQUEST_NOT_FOUND", "MVP request not found")
    if wanted in OPEN and row.status not in OPEN and _open(db, row.tenant_id) is not None:
        raise _error(409, "MVP_REQUEST_OPEN", "This organization has another open MVP request")
    previous = row.status
    row.status = wanted
    row.note = " ".join((note or "").split())[:500] or row.note
    row.handled_by = admin.id
    row.handled_at = now
    row.updated_at = now
    details = {"from": previous, "to": wanted, "tenant_id": str(row.tenant_id)}
    _audit(db, admin.tenant_id, admin.id, "TRIAL_MVP_REQUEST_STATUS_CHANGED", row, now, details)
    db.commit()
    return row
