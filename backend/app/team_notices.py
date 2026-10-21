"""Team-change emails: a change to an organization's team, told to the people it concerns through the outbox.

Two kinds of organization change their team:

* A free trial (backend/app/trial/team.py): its owner removes a colleague, withdraws an invitation or resets a
  colleague's MFA. The person changed is told, the owner gets a confirmation (also a security notice) and the MDARIX
  team an alert, when an alert address is configured.
* A paying organization, a pilot run by its Customer Administrators (backend/app/access/identity.py and the user
  edit in backend/app/access/configuration.py): an administrator removes, suspends or restores a user, withdraws an
  invitation, changes a role or resets MFA. The person changed is told what changed and by whom. When the change
  concerns an administrator account (the person is a Customer Administrator, becomes one or stops being one), the
  organization's other active Customer Administrators are told too; inviting a Customer Administrator is told to
  them as well (the invitation itself is its own email, sent at once with its link).

Each recipient's email is one ``TEAM_CHANGE_NOTICE`` outbox event, queued in the same transaction as the change, so
the worker retries a failed address alone (outbox/worker.py: one event, one commit) and nobody gets the same email
twice. Like every notification event (backend/app/notifications.py) it holds identifiers and codes only, never an
address: people are looked up when the email is sent. The person changed still gets the email about their own
removal or suspension; an erased account gets nothing, and neither does an owner or administrator who has lost their
account or role meanwhile.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from auth import emailer
from backend.app.db.models.foundation import AuthUser, RoleDefinition, Tenant
from backend.app.db.models.stage2 import OutboxEvent
from backend.app.notifications import TEAM_CHANGE_NOTICE as EVENT_NAME
from backend.app.role_codes import is_customer_admin_role, is_platform_admin_role, role_label

logger = logging.getLogger("mdarix.notifications")

TRIAL = "TRIAL"
ORGANIZATION = "ORGANIZATION"
# Who one event's email is for.
PERSON = "PERSON"  # the person changed
OWNER = "OWNER"  # a trial's owner, who made the change: the confirmation
ADMIN = "ADMIN"  # another Customer Administrator of the organization (``recipient_user_id``)
MDARIX_TEAM = "MDARIX_TEAM"  # the team running MDARIX (trial team changes)

TRIAL_CHANGES = frozenset({emailer.TEAM_REMOVED, emailer.TEAM_INVITATION_WITHDRAWN, emailer.TEAM_MFA_RESET})
ORGANIZATION_CHANGES = frozenset(
    {
        emailer.TEAM_INVITED,
        emailer.TEAM_REMOVED,
        emailer.TEAM_INVITATION_WITHDRAWN,
        emailer.TEAM_SUSPENDED,
        emailer.TEAM_RESTORED,
        emailer.TEAM_ROLE_CHANGED,
        emailer.TEAM_MFA_RESET,
    }
)
# An erased account (backend/app/tenant_purge.py) is never written to.
ERASED_STATUSES = frozenset({"REMOVED"})


def _queue(db: Session, tenant_id, person_id, audience: str, payload: dict, now: datetime) -> OutboxEvent:
    event = OutboxEvent(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        event_name=EVENT_NAME,
        aggregate_type="AuthUser",
        aggregate_id=person_id,
        payload={**payload, "tenant_id": str(tenant_id), "audience": audience},
        occurred_at=now,
    )
    db.add(event)
    return event


# ------------------------------------------------------------------------------------------- queueing (producers)


def queue_trial_change(db: Session, tenant_id, owner: AuthUser, person: AuthUser, change: str, now: datetime) -> int:
    """Queue a trial team change's emails (the caller commits, with the change): the person changed, the owner and,
    when an alert address is configured, the MDARIX team. Returns how many were queued."""
    from backend.app.trial.team import team_alert_recipient

    if change not in TRIAL_CHANGES:
        raise ValueError(f"Unknown trial team change {change}")
    base = {
        "kind": TRIAL,
        "change": change,
        "user_id": str(person.id),
        "actor_user_id": str(owner.id),
        "occurred_at": now.isoformat(),
    }
    audiences = [PERSON, OWNER] + ([MDARIX_TEAM] if team_alert_recipient() else [])
    for audience in audiences:
        _queue(db, tenant_id, person.id, audience, base, now)
    return len(audiences)


def concerns_administrator(person: AuthUser, role_before: str | None = None, role_now: str | None = None) -> bool:
    """Whether a change concerns an administrator account: the person is, was or becomes a Customer Administrator."""
    return any(is_customer_admin_role(role) for role in (person.role, role_before, role_now) if role)


def customer_admin_ids(db: Session, tenant_id, exclude: tuple = ()) -> list[uuid.UUID]:
    """The organization's active Customer Administrators (never an MDARIX staff account), less ``exclude``."""
    left_out = {str(value) for value in exclude if value}
    rows = (
        db.query(AuthUser.id, AuthUser.role)
        .filter(AuthUser.tenant_id == tenant_id, func.upper(AuthUser.status) == "ACTIVE")
        .all()
    )
    return sorted((row.id for row in rows if is_customer_admin_role(row.role) and str(row.id) not in left_out), key=str)


def queue_organization_change(
    db: Session,
    admin: AuthUser,
    person: AuthUser,
    change: str,
    *,
    now: datetime | None = None,
    role_before: str | None = None,
    role_now: str | None = None,
    roles_added: tuple[str, ...] = (),
    roles_removed: tuple[str, ...] = (),
    custom_roles_added: tuple = (),
    custom_roles_removed: tuple = (),
    tell_person: bool = True,
) -> int:
    """Queue a Customer Administrator's change to a paying organization's team (the caller commits, with the change):
    the person changed (unless ``tell_person`` is false: an invitation is its own email) and, when it concerns an
    administrator account, every other active Customer Administrator. Nothing for a free trial (its owner's changes
    are ``queue_trial_change``) or for a change made by or to an MDARIX staff account. Roles are given as codes
    (``role_before``/``role_now``: the account role; ``roles_added``/``roles_removed``: workflow roles) or, for the
    organization's own roles, as their ids. Returns how many emails were queued."""
    from backend.app.trial.service import trial_subscription

    if change not in ORGANIZATION_CHANGES:
        raise ValueError(f"Unknown team change {change}")
    tenant_id = person.tenant_id
    if is_platform_admin_role(admin.role) or is_platform_admin_role(person.role) or admin.tenant_id != tenant_id:
        return 0
    if trial_subscription(db, tenant_id) is not None:
        return 0
    now = now or datetime.now(timezone.utc)
    base = {
        "kind": ORGANIZATION,
        "change": change,
        "user_id": str(person.id),
        "actor_user_id": str(admin.id),
        "occurred_at": now.isoformat(),
        "role_before": role_before,
        "role_now": role_now,
        "roles_added": list(roles_added),
        "roles_removed": list(roles_removed),
        "custom_roles_added": [str(value) for value in custom_roles_added],
        "custom_roles_removed": [str(value) for value in custom_roles_removed],
    }
    queued = 0
    if tell_person:
        _queue(db, tenant_id, person.id, PERSON, base, now)
        queued += 1
    if concerns_administrator(person, role_before, role_now):
        for admin_id in customer_admin_ids(db, tenant_id, exclude=(admin.id, person.id)):
            _queue(db, tenant_id, person.id, ADMIN, {**base, "recipient_user_id": str(admin_id)}, now)
            queued += 1
    return queued


def status_change(previous: str | None, status: str | None) -> str | None:
    """The team change an account status change is (None when there is nothing to tell): OFFBOARDED removes a user,
    or withdraws an invitation not yet accepted; SUSPENDED suspends; ACTIVE again after a suspension or a removal
    restores."""
    before, after = str(previous or "").upper(), str(status or "").upper()
    if before == after:
        return None
    if after == "OFFBOARDED":
        return emailer.TEAM_INVITATION_WITHDRAWN if before == "INVITED" else emailer.TEAM_REMOVED
    if after == "SUSPENDED":
        return emailer.TEAM_SUSPENDED
    if after == "ACTIVE" and before in ("SUSPENDED", "OFFBOARDED"):
        return emailer.TEAM_RESTORED
    return None


# ------------------------------------------------------------------------------------------- delivery (worker)


def _uuid(value) -> uuid.UUID | None:
    try:
        return uuid.UUID(str(value)) if value else None
    except ValueError:
        return None


def _account(db: Session, tenant_id, user_id) -> AuthUser | None:
    if not user_id:
        return None
    return db.query(AuthUser).filter(AuthUser.id == _uuid(user_id), AuthUser.tenant_id == tenant_id).first()


def _active(user: AuthUser | None) -> bool:
    return user is not None and bool(user.username) and str(user.status or "").upper() == "ACTIVE"


def _writable(user: AuthUser | None) -> bool:
    """The person changed may be removed or suspended (that is what they are told), but never erased."""
    from backend.app.tenant_purge import REMOVED_DOMAIN

    return (
        user is not None
        and bool(user.username)
        and str(user.status or "").upper() not in ERASED_STATUSES
        and not user.username.endswith(REMOVED_DOMAIN)
    )


def _name(user: AuthUser | None, fallback: str) -> str:
    if user is None:
        return fallback
    return (user.display_name or "").strip() or user.username or fallback


def _trial_email(db: Session, payload: dict, tenant_id, person: AuthUser | None, owner: AuthUser | None):
    """(address, send, details) of one trial team email, or None when it has nobody to go to."""
    from auth.security_notices import _when
    from backend.app.trial import team

    change, audience = payload["change"], payload["audience"]
    organization = team.organization_name(db, tenant_id, owner)
    owner_name = _name(owner, "The person who runs the trial")
    when = _when(datetime.fromisoformat(str(payload["occurred_at"])))
    if person is None:
        return None
    if audience == PERSON:
        if not _writable(person):
            return None
        if change == emailer.TEAM_REMOVED:
            return (
                person.username,
                emailer.send_trial_colleague_removed,
                {"owner": owner_name, "organization": organization},
            )
        if change == emailer.TEAM_INVITATION_WITHDRAWN:
            return (
                person.username,
                emailer.send_trial_invitation_withdrawn,
                {"owner": owner_name, "organization": organization},
            )
        return (
            person.username,
            emailer.send_trial_mfa_reset_notice,
            {"owner": owner_name, "organization": organization, "when": when},
        )
    details = {"change": change, "organization": organization, "when": when}
    if audience == OWNER:
        if not _active(owner) or not team.is_trial_owner(db, tenant_id, owner):
            return None
        return (
            owner.username,
            emailer.send_trial_team_change_confirmation,
            {**details, "person": _name(person, person.username), "person_email": person.username},
        )
    address = team.team_alert_recipient()
    if not address:
        return None
    tenant = db.query(Tenant.tenant_key).filter(Tenant.id == tenant_id).first()
    return (
        address,
        emailer.send_trial_team_change_alert,
        {
            **details,
            "tenant_key": tenant.tenant_key if tenant else "",
            "owner": owner_name,
            "owner_email": owner.username if owner else "",
            "person_email": person.username,
        },
    )


def _custom_roles(db: Session, tenant_id, ids) -> tuple[str, ...]:
    wanted = [value for value in (_uuid(item) for item in ids or ()) if value]
    if not wanted:
        return ()
    rows = db.query(RoleDefinition.name).filter(RoleDefinition.tenant_id == tenant_id, RoleDefinition.id.in_(wanted))
    return tuple(sorted(row.name for row in rows if row.name))


def _organization_email(db: Session, payload: dict, tenant_id, person: AuthUser | None, actor: AuthUser | None):
    """(address, send, details) of one pilot organization's team email, or None when it has nobody to go to."""
    from auth.security_notices import _when
    from backend.app.notifications import _organization

    change, audience = payload["change"], payload["audience"]
    if person is None:
        return None
    organization = _organization(db, tenant_id)
    actor_name = _name(actor, f"An administrator of {organization}")
    when = _when(datetime.fromisoformat(str(payload["occurred_at"])))
    before, now = payload.get("role_before"), payload.get("role_now")
    roles = {
        "role_before": role_label(before) if before else None,
        "role_now": role_label(now) if now else None,
    }
    if audience == PERSON:
        if not _writable(person):
            return None
        return (
            person.username,
            emailer.send_team_change_notice,
            {
                "change": change,
                "actor": actor_name,
                "organization": organization,
                "when": when,
                **roles,
                "roles_added": tuple(role_label(code) for code in payload.get("roles_added") or ())
                + _custom_roles(db, tenant_id, payload.get("custom_roles_added")),
                "roles_removed": tuple(role_label(code) for code in payload.get("roles_removed") or ())
                + _custom_roles(db, tenant_id, payload.get("custom_roles_removed")),
            },
        )
    recipient = _account(db, tenant_id, payload.get("recipient_user_id"))
    if not _active(recipient) or not is_customer_admin_role(recipient.role) or recipient.id == person.id:
        return None
    return (
        recipient.username,
        emailer.send_team_admin_change_notice,
        {
            "change": change,
            "actor": actor_name,
            "actor_email": actor.username if actor else "",
            "person": _name(person, person.username),
            "person_email": person.username,
            "organization": organization,
            "when": when,
            **roles,
        },
    )


def deliver(db: Session, payload: dict) -> None:
    """Send one TEAM_CHANGE_NOTICE event's email. Raises ``backend.app.notifications.NotificationFailed`` when it could
    not be delivered, so the outbox retries this one email; an email with nobody to go to any more is done."""
    from backend.app.notifications import NotificationFailed

    tenant_id = _uuid(payload.get("tenant_id"))
    person = _account(db, tenant_id, payload.get("user_id"))
    actor = _account(db, tenant_id, payload.get("actor_user_id"))
    build = _trial_email if payload.get("kind") == TRIAL else _organization_email
    email = build(db, payload, tenant_id, person, actor)
    if email is None:
        return
    address, send, details = email
    try:
        outcome = send(address, **details)
    except emailer.EmailDeliveryError as exc:
        raise NotificationFailed(f"the team change email ({payload.get('change')}) could not be delivered") from exc
    if outcome == "NOT_CONFIGURED":
        logger.warning("Email is not configured; team change notice not sent")
