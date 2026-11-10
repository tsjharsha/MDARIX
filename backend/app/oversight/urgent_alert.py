"""B7 step 11 (spec 5, B7-D12): the opt-in urgent e-mail alert.

"An urgent case (URG-...) was received at 14:20 Asia/Kolkata. Open MDARIX to see it." Off by default (Settings ›
Oversight, ``urgent_email``). Queued at once through the notifications outbox (SMTP, retries and dead-letter exist
there; the outbox is its delivery record and holds identifiers only), to the people holding the organization's
escalation role and the Triage Leads, once per item per person. No product, words or patient data. A person without an
address is skipped and recorded in the audit; a deactivated one is skipped at sending. A failed e-mail never cancels
the in-app escalation. One reminder when the acknowledgement of the fast track is overdue.

What sends it: an urgent Case, a Case escalated with a death or serious injury, and a triage that reopens on a death or
serious injury (RT-26). B7b adds an e-mail with those words.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy.orm import Session

ALERT = "URGENT_CASE_ALERT"
REMINDER = "URGENT_CASE_REMINDER"
EVENTS = (ALERT, REMINDER)
DSI_TRIGGERS = ("DEATH", "SERIOUS_INJURY")


def _recipients(db: Session, control_db: Session, tenant_id) -> tuple[list[str], list[str]]:
    """(account ids with an e-mail address, account ids without one) among the escalation role and Triage Leads."""
    from backend.app.db.models.foundation import AuthUser
    from backend.app.oversight import service

    view = service.settings_view(service.settings_row(db, tenant_id))
    everyone = service.people(control_db, tenant_id)
    wanted = set(service.escalation_people(everyone, view["escalation_role"]))
    wanted |= {person["id"] for person in everyone if "TRIAGE_LEAD" in person["roles"]}
    if not wanted:
        return [], []
    rows = control_db.query(AuthUser.id, AuthUser.username).filter(
        AuthUser.tenant_id == tenant_id, AuthUser.id.in_([uuid.UUID(value) for value in wanted])
    )
    addresses = {str(user_id): bool(name and "@" in name) for user_id, name in rows}
    return sorted(k for k, v in addresses.items() if v), sorted(k for k, v in addresses.items() if not v)


def queue(
    db: Session,
    control_db: Session | None,
    tenant_id,
    *,
    reference: str,
    subject_id,
    received_at: datetime | None,
    actor,
    reminder: bool = False,
    correlation_id=None,
) -> int:
    """Queue the alert (or the reminder) for one urgent item when the organization opted in; returns how many e-mails
    were queued. Flushes nothing itself; the caller commits both sessions."""
    from backend.app.db.models.stage2 import OutboxEvent
    from backend.app.enterprise_audit import make_audit_event
    from backend.app.notifications import _queue
    from backend.app.oversight import service
    from backend.app.reportability.deadlines import org_zone

    if control_db is None:
        return 0
    settings = service.settings_row(db, tenant_id)
    if settings is None or not settings.urgent_email:
        return 0
    name = REMINDER if reminder else ALERT
    already = {
        str(payload.get("user_id"))
        for (payload,) in control_db.query(OutboxEvent.payload).filter(
            OutboxEvent.tenant_id == tenant_id, OutboxEvent.event_name == name, OutboxEvent.aggregate_id == subject_id
        )
    }
    reachable, skipped = _recipients(db, control_db, tenant_id)
    zone = org_zone(db, tenant_id) or "UTC"
    queued = [user_id for user_id in reachable if user_id not in already]
    for user_id in queued:
        _queue(
            control_db,
            tenant_id,
            name,
            "UrgentItem",
            subject_id,
            {
                "user_id": user_id,
                "reference": reference,
                "received_at": received_at.isoformat() if received_at else None,
                "zone": zone,
            },
        )
    db.add(
        make_audit_event(
            tenant_id=tenant_id,
            actor_ref=actor,
            action="URGENT_EMAIL_QUEUED",
            entity_type="UrgentItem",
            entity_id=subject_id,
            correlation_id=correlation_id,
            details={"reference": reference, "reminder": reminder, "queued": len(queued), "no_address": skipped},
        )
    )
    return len(queued)


def remind_overdue(db: Session, control_db: Session | None, tenant_id, now: datetime) -> int:
    """UA-04: one reminder per urgent item whose fast-track acknowledgement is overdue (called by the sweep)."""
    from backend.app.intake import service as intake
    from backend.app.oversight import service

    settings = service.settings_row(db, tenant_id)
    if control_db is None or settings is None or not settings.urgent_email:
        return 0
    sent = 0
    for item in intake.triage(db, control_db, tenant_id, "open", now)["items"]:
        if not (item.get("acknowledgement") or {}).get("overdue"):
            continue
        member_id = item["members"][0].split(":")[1]
        sent += queue(
            db,
            control_db,
            tenant_id,
            reference=item["ref"],
            subject_id=uuid.UUID(member_id),
            received_at=None,
            actor="system:oversight",
            reminder=True,
        )
    return sent


def deliver(db: Session, event_name: str, payload: dict, emailer) -> None:
    """The outbox worker's step: the e-mail to one person, if the account is still active."""
    from backend.app.notifications import _deliver, _organization, _personal, _uuid
    from backend.app.oversight.rules import zone_info

    tenant_id = _uuid(payload["tenant_id"])
    received = payload.get("received_at")
    zone = payload.get("zone") or "UTC"
    when = f"{datetime.fromisoformat(received).astimezone(zone_info(zone)):%d %b %Y %H:%M} {zone}" if received else None
    _deliver(
        lambda recipient, **kw: emailer.send_urgent_case_alert(recipient, **kw),
        _personal(db, tenant_id, payload.get("user_id")),
        organization=_organization(db, tenant_id),
        reference=str(payload.get("reference") or ""),
        received=when,
        reminder=event_name == REMINDER,
    )
