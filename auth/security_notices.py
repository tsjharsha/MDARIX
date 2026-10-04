"""Security notices: the email a person gets when the way they sign in changed.

A new authenticator, new recovery codes, a changed or reset password: whoever did it, the account's owner is told,
so that a change they did not make is noticed within minutes rather than at the next audit. The notice names what
happened and when, never the new value (no codes, no links, no passwords), and says what to do if it was not them.

Notices are queued as ``SECURITY_NOTICE`` outbox events in the same transaction as the change they report, and
the outbox worker delivers them (backend/app/notifications.py hands the event to ``handle_security_notice``), so
a slow or failing mail provider never delays or fails the change itself, and delivery is retried.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from backend.app.db.models.foundation import AuthUser, Tenant
from backend.app.db.models.stage2 import OutboxEvent

EVENT_NAME = "SECURITY_NOTICE"

# kind -> (subject, what happened)
KINDS: dict[str, tuple[str, str]] = {
    "MFA_ENROLLED": (
        "An authenticator app was set up for your MDARIX account",
        "An authenticator app was set up for your account. From now on, signing in needs a code from it.",
    ),
    "MFA_REPLACED": (
        "The authenticator app for your MDARIX account was replaced",
        "The authenticator app for your account was replaced with a new one. Codes from the old app no longer work.",
    ),
    "MFA_RECOVERY_CODES_REGENERATED": (
        "New recovery codes were issued for your MDARIX account",
        "New one-time recovery codes were issued for your account. The earlier codes no longer work.",
    ),
    "PASSWORD_CHANGED": (
        "Your MDARIX password was changed",
        "The password of your account was changed, and every other session was signed out.",
    ),
    "PASSWORD_RESET": (
        "Your MDARIX password was reset",
        "The password of your account was reset with a reset link, and every session was signed out.",
    ),
}


def _when(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%d %B %Y at %H:%M UTC")


def queue_security_notice(db: Session, user: AuthUser, kind: str, now: datetime | None = None) -> OutboxEvent:
    """Queue the notice for ``user`` (the caller commits, together with the change being reported)."""
    if kind not in KINDS:
        raise ValueError(f"Unknown security notice {kind}")
    now = now or datetime.now(timezone.utc)
    event = OutboxEvent(
        id=uuid.uuid4(),
        tenant_id=user.tenant_id,
        event_name=EVENT_NAME,
        aggregate_type="AuthUser",
        aggregate_id=user.id,
        # The person is looked up at delivery time, so the payload holds no email address.
        payload={"user_id": str(user.id), "kind": kind, "occurred_at": now.isoformat()},
        occurred_at=now,
    )
    db.add(event)
    return event


def send_security_notice(recipient: str, *, kind: str, organization: str, occurred_at: datetime) -> str:
    """Email one notice; returns the delivery result of auth/emailer.py ("SENT" or "NOT_CONFIGURED")."""
    from auth.emailer import Message, _send, company

    subject, happened = KINDS[kind]
    support = company().support_email
    return _send(
        recipient,
        Message(
            subject=subject,
            heading=subject,
            paragraphs=(f"{happened} This concerns your account for {organization}.",),
            details=(("When", _when(occurred_at)),),
            closing=(
                "If this was you, there is nothing to do.",
                "If it was not you, sign in and change your password now"
                + (f", then tell {support}." if support else ", then tell your administrator."),
            ),
            reason="You are receiving this email because the sign-in settings of your MDARIX account changed.",
        ),
    )


def handle_security_notice(db: Session, event_name: str, payload: dict) -> bool:
    """Deliver one SECURITY_NOTICE outbox event; False when the event is something else.

    Raises ``backend.app.notifications.NotificationFailed`` when the email could not be delivered, so the outbox
    retries it. An account that no longer exists (erased, purged) gets no email, and the event is done.
    """
    if event_name != EVENT_NAME:
        return False
    from auth.emailer import EmailDeliveryError
    from backend.app.notifications import NotificationFailed

    user = db.query(AuthUser).filter(AuthUser.id == uuid.UUID(str(payload["user_id"]))).first()
    if user is None or not user.username:
        return True
    tenant = db.query(Tenant).filter(Tenant.id == user.tenant_id).first()
    organization = (tenant.display_name or tenant.name) if tenant else "your organization"
    occurred_at = datetime.fromisoformat(str(payload["occurred_at"]))
    try:
        send_security_notice(
            user.username, kind=str(payload["kind"]), organization=organization, occurred_at=occurred_at
        )
    except EmailDeliveryError as exc:
        raise NotificationFailed("security notice could not be delivered") from exc
    return True
