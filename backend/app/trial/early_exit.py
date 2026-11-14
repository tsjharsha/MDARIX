"""Ending a free trial early, at the organization's request.

The trial owner asks (Getting started), with an optional reason and whether the data should be deleted. A Platform
Administrator decides:

- **Approve**: the trial ends now (the subscription's end is set to now, so sign-in to the workspace closes as on its
  last day). With ``delete_data`` the organization's data is purged at once (backend/app/tenant_purge.py: records,
  files and the people's identities; a minimal record that the trial existed is kept). Without it the data is kept for
  the usual 30 days after the end, then deleted by the retention run. The owner is emailed either way and asked,
  simply by replying, why they ended early.
- **Decline**: the trial continues; the administrator's note is emailed to the owner and shown in Getting started.

The owner may withdraw a request that is still pending. One pending request per trial at a time. The request itself
(``trial_exit_requests``) names the organization by ``trial_tenant_id`` and holds no name or email address, so it, and
the reason given, remain as the record of the decision after a purge.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy.orm import Session

from backend.app.db.models.foundation import AuthUser, Tenant
from backend.app.db.models.stage2 import OutboxEvent, TrialExitRequest

# Why an organization ends early: a short list to choose from, and its own words.
EXIT_REASONS: dict[str, str] = {
    "FINISHED": "We have seen what we needed",
    "NO_TIME": "No time to evaluate it now",
    "NOT_A_FIT": "Not a fit for how we work",
    "MISSING": "Something we need is missing",
    "DATA_CONCERNS": "Concerns about our data",
    "OTHER_SOLUTION": "We chose another solution",
    "OTHER": "Another reason",
}

# Raised by MDARIX from Trial organizations (TO-1, backend/app/trial/admin_actions.py); never offered to the owner.
MDARIX_REASONS: dict[str, str] = {"ENDED_BY_MDARIX": "Ended by MDARIX"}

PENDING = "PENDING"


def _error(status: int, code: str, message: str) -> HTTPException:
    return HTTPException(status, detail={"code": code, "message": message})


def latest(db: Session, tenant_id: uuid.UUID) -> TrialExitRequest | None:
    return (
        db.query(TrialExitRequest)
        .filter(TrialExitRequest.trial_tenant_id == tenant_id)
        .order_by(TrialExitRequest.created_at.desc())
        .first()
    )


def view(row: TrialExitRequest | None) -> dict | None:
    """The request as the owner and the Platform Administrator see it."""
    if row is None:
        return None
    return {
        "id": str(row.id),
        "status": row.status,
        "reason_code": row.reason_code,
        "reason_label": EXIT_REASONS.get(row.reason_code or "") or MDARIX_REASONS.get(row.reason_code or ""),
        "reason": row.reason,
        "delete_data": row.delete_data,
        "data_deleted": row.data_deleted,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "decided_at": row.decided_at.isoformat() if row.decided_at else None,
        "decision_note": row.decision_note,
    }


def _audit(db: Session, tenant_id: uuid.UUID, actor: uuid.UUID, action: str, row: TrialExitRequest, now: datetime):
    from backend.app.enterprise_audit import make_audit_event

    db.add(
        make_audit_event(
            tenant_id=tenant_id,
            actor_ref=str(actor),
            action=action,
            entity_type="TrialExitRequest",
            entity_id=row.id,
            details={
                "reason_code": row.reason_code,
                "delete_data": row.delete_data,
                "status": row.status,
            },
            created_at=now,
        )
    )


def request_exit(
    db: Session,
    tenant_id: uuid.UUID,
    user: AuthUser,
    *,
    reason_code: str | None,
    reason: str | None,
    delete_data: bool,
    now: datetime | None = None,
) -> tuple[TrialExitRequest, bool]:
    """The owner asks to end the trial early. Returns (request, created): a pending request is returned unchanged.
    Commits."""
    from backend.app.trial import team

    now = now or datetime.now(timezone.utc)
    if not team.is_trial_owner(db, tenant_id, user):
        raise _error(403, "TRIAL_OWNER_ONLY", "Only the person who started the trial can end it early")
    current = latest(db, tenant_id)
    if current is not None and current.status == PENDING:
        return current, False
    code = (reason_code or "").strip().upper() or None
    if code is not None and code not in EXIT_REASONS:
        raise _error(422, "TRIAL_EXIT_REASON_UNKNOWN", "Choose one of the listed reasons")
    tenant = db.get(Tenant, tenant_id)
    row = TrialExitRequest(
        id=uuid.uuid4(),
        trial_tenant_id=tenant_id,
        organization=((tenant.name if tenant else None) or "Trial organization")[:160],
        requested_by=user.id,
        reason_code=code,
        reason=" ".join((reason or "").split())[:1000] or None,
        delete_data=bool(delete_data),
        status=PENDING,
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    _audit(db, tenant_id, user.id, "TRIAL_EXIT_REQUESTED", row, now)
    db.commit()
    db.refresh(row)
    return row, True


def withdraw(db: Session, tenant_id: uuid.UUID, user: AuthUser, now: datetime | None = None) -> TrialExitRequest:
    """The owner withdraws a pending request; the trial simply continues. Commits."""
    from backend.app.trial import team

    now = now or datetime.now(timezone.utc)
    if not team.is_trial_owner(db, tenant_id, user):
        raise _error(403, "TRIAL_OWNER_ONLY", "Only the person who started the trial can change this request")
    row = latest(db, tenant_id)
    if row is None or row.status != PENDING:
        raise _error(409, "TRIAL_EXIT_NOT_PENDING", "There is no pending request to withdraw")
    row.status = "WITHDRAWN"
    row.updated_at = now
    _audit(db, tenant_id, user.id, "TRIAL_EXIT_WITHDRAWN", row, now)
    db.commit()
    return row


def overview(db: Session) -> list[dict]:
    """Every request, pending first then newest, for the Platform Administrator, with the trial's days left and who
    asked (their name, unless the trial's data, people included, has been deleted).

    A fixed number of statements however many requests there are (as the trial overview, story.trial_overview): the
    requests, then their organizations, the people who asked and the trials' subscriptions, each read for every
    request at once. Before 0.10.17 each request cost four statements of its own."""
    from backend.app.paging import open_first

    # Every pending request, however old; then the newest 500 decided ones.
    rows = open_first(
        db.query(TrialExitRequest),
        TrialExitRequest.id,
        TrialExitRequest.status == PENDING,
        [TrialExitRequest.created_at.desc()],
        500,
    )
    tenant_ids = {row.trial_tenant_id for row in rows}
    person_ids = {row.requested_by for row in rows if row.requested_by}
    tenants = {tenant.id: tenant for tenant in db.query(Tenant).filter(Tenant.id.in_(tenant_ids))} if tenant_ids else {}
    people = (
        {person.id: person for person in db.query(AuthUser).filter(AuthUser.id.in_(person_ids))} if person_ids else {}
    )
    trial_ends = _trial_ends(db, tenant_ids)
    now = datetime.now(timezone.utc)
    items = []
    for row in rows:
        tenant = tenants.get(row.trial_tenant_id)
        person = people.get(row.requested_by) if row.requested_by else None
        ends = trial_ends.get(row.trial_tenant_id)
        items.append(
            {
                **(view(row) or {}),
                "organization": row.organization,
                "trial_tenant_id": str(row.trial_tenant_id),
                "tenant_business_id": tenant.business_id if tenant else None,
                "tenant_status": tenant.status if tenant else None,
                "requested_by": (person.display_name or person.username)
                if person is not None and not row.data_deleted
                else None,
                "days_left": _days_until(ends, now) if ends is not None else None,
            }
        )
    items.sort(key=lambda item: 0 if item["status"] == PENDING else 1)
    return items


def _trial_ends(db: Session, tenant_ids) -> dict:
    """``{tenant id: end of its Free Trial subscription}`` for the tenants still on the Free Trial plan, in one
    statement: each tenant's latest Free Trial subscription, as ``service.trial_subscription`` reads it for one."""
    from backend.app.db.models.foundation import PlanDefinition
    from backend.app.db.models.stage2 import SubscriptionLifecycle
    from backend.app.trial import service

    if not tenant_ids:
        return {}
    ends: dict = {}
    for tenant_id, expires_at in (
        db.query(SubscriptionLifecycle.tenant_id, SubscriptionLifecycle.expires_at)
        .join(PlanDefinition, PlanDefinition.id == SubscriptionLifecycle.plan_id)
        .filter(SubscriptionLifecycle.tenant_id.in_(tenant_ids), PlanDefinition.code == service.FREE_TRIAL_PLAN)
        .order_by(SubscriptionLifecycle.created_at)
    ):
        ends[tenant_id] = expires_at  # the latest subscription comes last
    return ends


def _days_until(expires_at: datetime, now: datetime) -> int:
    """Whole days left until ``expires_at``, rounded up; 0 once it has passed (as ``days_left``)."""
    return max(0, int(-(-(expires_at - now).total_seconds() // 86400)))


def _owner_email(db: Session, tenant_id: uuid.UUID) -> str | None:
    """The trial owner's address (the trial request's), read before any purge pseudonymizes it."""
    from backend.app.trial.team import trial_request

    request = trial_request(db, tenant_id)
    return request.email if request is not None and request.email else None


def _end_subscription(db: Session, tenant_id: uuid.UUID, now: datetime):
    from backend.app.trial.service import trial_subscription

    subscription = trial_subscription(db, tenant_id)
    if subscription is None:
        raise _error(409, "TRIAL_EXIT_NOT_A_TRIAL", "This organization is no longer on the free trial")
    if subscription.expires_at > now:
        subscription.expires_at = now
    subscription.grace_ends_at = None
    subscription.status = "EXPIRED"
    subscription.expiry_version += 1
    subscription.updated_at = now
    return subscription


def _queue_ended_email(db: Session, subscription, now: datetime) -> None:
    """The owner's "trial ended early, data kept" email goes through the trial reminders (notifications.py), which also
    keeps the scheduler from sending the usual "trial ended" email as well."""
    from backend.app.notifications import trial_reminder_end

    db.add(
        OutboxEvent(
            tenant_id=subscription.tenant_id,
            event_name="TRIAL_REMINDER",
            aggregate_type="SubscriptionLifecycle",
            aggregate_id=subscription.id,
            payload={
                "subscription_id": str(subscription.id),
                "stage": "ENDED",
                "early": True,
                # The end date it is sent for, as the scheduler's reminders keep it (FUN-04).
                "expires_at": trial_reminder_end(subscription.expires_at),
            },
            occurred_at=now,
        )
    )


def _pending(db: Session, request_id: uuid.UUID) -> TrialExitRequest:
    row = db.get(TrialExitRequest, request_id)
    if row is None:
        raise _error(404, "TRIAL_EXIT_NOT_FOUND", "Request not found")
    if row.status != PENDING:
        raise _error(409, "TRIAL_EXIT_ALREADY_DECIDED", "This request has already been decided or withdrawn")
    return row


def _purge(db: Session, row: TrialExitRequest, admin: AuthUser, now: datetime) -> str | None:
    """Delete the trial's data now. Returns None when the rows are gone, else why not (nothing was deleted then)."""
    from backend.app.tenant_purge import PurgeFailed, purge_tenant

    try:
        purge_tenant(
            db,
            row.trial_tenant_id,
            str(admin.id),
            reason="Free trial ended early at the organization's request; its data is deleted as it asked.",
            now=now,
            evidence={"trial_exit_request": str(row.id), "reason_code": row.reason_code},
        )
    except PurgeFailed as exc:
        db.rollback()
        return str(exc)
    return None


def approve(
    db: Session,
    request_id: uuid.UUID,
    admin: AuthUser,
    *,
    delete_data: bool,
    note: str | None = None,
    now: datetime | None = None,
) -> dict:
    """End the trial now and, with ``delete_data``, purge its data. Returns the outcome and, when the data was deleted,
    who to email (the owner, whose address the purge removes from the records). Commits."""
    now = now or datetime.now(timezone.utc)
    row = _pending(db, request_id)
    tenant = db.get(Tenant, row.trial_tenant_id)
    if delete_data and tenant is not None and tenant.legal_hold:
        raise _error(
            409, "TRIAL_EXIT_LEGAL_HOLD", "This organization is under a legal hold: its data cannot be deleted"
        )
    recipient = _owner_email(db, row.trial_tenant_id)
    subscription = _end_subscription(db, row.trial_tenant_id, now)
    row.status = "APPROVED"
    row.decided_by = admin.id
    row.decided_at = now
    row.decision_note = " ".join((note or "").split())[:500] or None
    row.updated_at = now
    _audit(db, row.trial_tenant_id, admin.id, "TRIAL_ENDED_EARLY", row, now)
    if not delete_data:
        _queue_ended_email(db, subscription, now)
        db.commit()
        return {"status": "APPROVED", "data_deleted": False, "request": view(row), "notify": None}
    db.commit()
    failure = _purge(db, row, admin, now)
    row = db.get(TrialExitRequest, request_id)
    if failure is not None:
        # Nothing was deleted: the trial has ended and its data follows the usual retention; the owner is told so.
        row.decision_note = ((row.decision_note or "") + f" Data not deleted ({failure}).").strip()[:500]
        row.updated_at = now
        from backend.app.trial.service import trial_subscription

        subscription = trial_subscription(db, row.trial_tenant_id)
        if subscription is not None:
            _queue_ended_email(db, subscription, now)
        db.commit()
        return {
            "status": "APPROVED",
            "data_deleted": False,
            "purge_error": failure,
            "request": view(row),
            "notify": None,
        }
    row.data_deleted = True
    row.updated_at = now
    db.commit()
    notify = {"recipient": recipient, "organization": row.organization} if recipient else None
    return {"status": "APPROVED", "data_deleted": True, "request": view(row), "notify": notify}


def delete_data_now(db: Session, request_id: uuid.UUID, admin: AuthUser, now: datetime | None = None) -> dict:
    """For a trial ended early whose data was kept: delete it now rather than at the end of the 30 days. Commits."""
    now = now or datetime.now(timezone.utc)
    row = db.get(TrialExitRequest, request_id)
    if row is None:
        raise _error(404, "TRIAL_EXIT_NOT_FOUND", "Request not found")
    if row.status != "APPROVED" or row.data_deleted:
        raise _error(409, "TRIAL_EXIT_NOTHING_TO_DELETE", "Only an ended trial whose data was kept can be deleted here")
    tenant = db.get(Tenant, row.trial_tenant_id)
    if tenant is not None and tenant.legal_hold:
        raise _error(
            409, "TRIAL_EXIT_LEGAL_HOLD", "This organization is under a legal hold: its data cannot be deleted"
        )
    recipient = _owner_email(db, row.trial_tenant_id)
    failure = _purge(db, row, admin, now)
    row = db.get(TrialExitRequest, request_id)
    if failure is not None:
        raise _error(409, "TRIAL_EXIT_DELETE_FAILED", f"The data could not be deleted ({failure}); nothing was changed")
    row.data_deleted = True
    row.updated_at = now
    db.commit()
    notify = {"recipient": recipient, "organization": row.organization} if recipient else None
    return {"status": row.status, "data_deleted": True, "request": view(row), "notify": notify}


def decline(db: Session, request_id: uuid.UUID, admin: AuthUser, *, note: str, now: datetime | None = None) -> dict:
    """Keep the trial running; the note goes to the owner. Commits."""
    now = now or datetime.now(timezone.utc)
    text = " ".join((note or "").split())[:500]
    if len(text) < 10:
        raise _error(422, "TRIAL_EXIT_NOTE_REQUIRED", "Write a short note to the trial owner (10 characters or more)")
    row = _pending(db, request_id)
    row.status = "DECLINED"
    row.decided_by = admin.id
    row.decided_at = now
    row.decision_note = text
    row.updated_at = now
    _audit(db, row.trial_tenant_id, admin.id, "TRIAL_EXIT_DECLINED", row, now)
    recipient = _owner_email(db, row.trial_tenant_id)
    db.commit()
    notify = {"recipient": recipient, "organization": row.organization, "note": text} if recipient else None
    return {"status": "DECLINED", "request": view(row), "notify": notify}


def days_left(db: Session, tenant_id: uuid.UUID, now: datetime | None = None) -> int:
    from backend.app.trial.service import trial_subscription

    now = now or datetime.now(timezone.utc)
    subscription = trial_subscription(db, tenant_id)
    if subscription is None:
        return 0
    return max(0, int(-(-(subscription.expires_at - now).total_seconds() // 86400)))
