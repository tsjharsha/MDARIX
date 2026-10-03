"""Customer notifications delivered by the background worker from outbox events.

Each event names what happened; the worker calls ``handle_event``, which emails the right people and raises when an
email could not be sent, so the outbox retries (and finally dead-letters and alerts). Events:

* ``SUBSCRIPTION_REMINDER`` (scheduler, subscription lifecycle): the organization's customer administrators.
* ``TENANT_LIFECYCLE_NOTIFICATION`` (scheduled tenant status change): the organization's customer administrators.
* ``TRIAL_REMINDER`` (scheduler, trial reminders): the person who requested the trial.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.app.db.models.foundation import AuthUser, Tenant
from backend.app.db.models.stage2 import OutboxEvent, SubscriptionLifecycle

logger = logging.getLogger("mdarix.notifications")
TRIAL_STAGES = ("7_DAY", "1_DAY", "ENDED")


class NotificationFailed(RuntimeError):
    """An email could not be delivered; the outbox retries the event."""


def _long_date(value: datetime) -> str:
    return f"{value.day} {value:%B %Y}"


def _organization(db: Session, tenant_id) -> str:
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    return (tenant.display_name or tenant.name) if tenant else "your organization"


def customer_admin_emails(db: Session, tenant_id) -> list[str]:
    normalized = func.upper(func.replace(func.trim(func.coalesce(AuthUser.role, "")), " ", "_"))
    rows = (
        db.query(AuthUser.username)
        .filter(
            AuthUser.tenant_id == tenant_id, normalized == "CUSTOMER_ADMIN", func.upper(AuthUser.status) == "ACTIVE"
        )
        .all()
    )
    return sorted({row.username for row in rows if row.username})


def _deliver(send, recipients: list[str], **details) -> None:
    from auth.emailer import EmailDeliveryError

    failures = 0
    for recipient in recipients:
        try:
            outcome = send(recipient, **details)
        except EmailDeliveryError:
            failures += 1
            continue
        if outcome == "NOT_CONFIGURED":
            logger.warning("Email is not configured; notification not sent")
    if failures:
        raise NotificationFailed(f"{failures} of {len(recipients)} emails could not be delivered")


def handle_event(db: Session, event_name: str, payload: dict) -> bool:
    """Send the notification for one outbox event. False when the event is not a notification."""
    from auth import emailer

    if event_name == "SUBSCRIPTION_REMINDER":
        row = db.get(SubscriptionLifecycle, uuid.UUID(str(payload["subscription_id"])))
        if row is None:
            return True
        days_left = max(0, (row.expires_at - datetime.now(timezone.utc)).days)
        _deliver(
            lambda recipient, **kw: emailer.send_subscription_reminder(recipient, **kw),
            customer_admin_emails(db, row.tenant_id),
            organization=_organization(db, row.tenant_id),
            expires_on=_long_date(row.expires_at),
            days_left=days_left,
        )
        return True
    if event_name == "TENANT_LIFECYCLE_NOTIFICATION":
        tenant_id = uuid.UUID(str(payload["tenant_id"]))
        _deliver(
            lambda recipient, **kw: emailer.send_tenant_lifecycle_notice(recipient, **kw),
            customer_admin_emails(db, tenant_id),
            organization=_organization(db, tenant_id),
            transition=str(payload.get("transition") or ""),
            reason=payload.get("reason"),
        )
        return True
    if event_name == "TRIAL_REMINDER":
        from backend.app.trial.team import trial_request

        row = db.get(SubscriptionLifecycle, uuid.UUID(str(payload["subscription_id"])))
        request = trial_request(db, row.tenant_id) if row is not None else None
        if row is None or request is None:
            return True
        organization = _organization(db, row.tenant_id)
        delete_on = _long_date(row.expires_at + timedelta(days=30))
        if payload.get("stage") == "ENDED":
            _deliver(
                lambda recipient, **kw: emailer.send_trial_ended(recipient, **kw),
                [request.email],
                organization=organization,
                delete_on=delete_on,
            )
        else:
            _deliver(
                lambda recipient, **kw: emailer.send_trial_reminder(recipient, **kw),
                [request.email],
                organization=organization,
                days_left=max(0, (row.expires_at - datetime.now(timezone.utc)).days),
                ends_on=_long_date(row.expires_at),
                delete_on=delete_on,
            )
        return True
    return False


def queue_trial_reminders(db: Session, now: datetime | None = None) -> int:
    """Queue each trial's reminders once: 7 days and 1 day before it ends, and when it has ended (caller commits)."""
    from backend.app.trial.service import FREE_TRIAL_PLAN
    from backend.app.db.models.foundation import PlanDefinition

    now = now or datetime.now(timezone.utc)
    queued = 0
    trials = (
        db.query(SubscriptionLifecycle)
        .join(PlanDefinition, PlanDefinition.id == SubscriptionLifecycle.plan_id)
        .filter(PlanDefinition.code == FREE_TRIAL_PLAN)
        .all()
    )
    for row in trials:
        remaining = row.expires_at - now
        if remaining <= timedelta(0):
            stage = "ENDED" if -remaining <= timedelta(days=7) else None
        elif remaining <= timedelta(days=1):
            stage = "1_DAY"
        elif remaining <= timedelta(days=7):
            stage = "7_DAY"
        else:
            stage = None
        if stage is None:
            continue
        exists = (
            db.query(OutboxEvent.id)
            .filter(
                OutboxEvent.tenant_id == row.tenant_id,
                OutboxEvent.event_name == "TRIAL_REMINDER",
                OutboxEvent.payload["subscription_id"].as_string() == str(row.id),
                OutboxEvent.payload["stage"].as_string() == stage,
            )
            .first()
        )
        if exists:
            continue
        db.add(
            OutboxEvent(
                tenant_id=row.tenant_id,
                event_name="TRIAL_REMINDER",
                aggregate_type="SubscriptionLifecycle",
                aggregate_id=row.id,
                payload={"subscription_id": str(row.id), "stage": stage},
                occurred_at=now,
            )
        )
        queued += 1
    return queued
