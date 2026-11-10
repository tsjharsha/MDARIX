"""Customer notifications delivered by the background worker from outbox events.

Producers call one ``notify_*`` function in the same transaction as the change it reports (the caller commits). It
adds an outbox event that holds identifiers only: never an email address, a password, a token or customer text.
People are looked up when the email is sent, so an account that was deactivated or erased meanwhile gets nothing and
the queue holds no personal data. The worker calls ``handle_event``, which emails the right people and raises when an
email could not be sent, so the outbox retries (and finally dead-letters and alerts). Events:

* ``SUBSCRIPTION_REMINDER`` (scheduler, subscription lifecycle): the customer administrators and the contacts the
  organization's notification settings name, in the organization's own wording when a reminder email is saved.
* ``TENANT_LIFECYCLE_NOTIFICATION`` (scheduled tenant status change): the organization's customer administrators.
* ``TRIAL_REMINDER`` (scheduler, trial reminders): the person who requested the trial.
* ``TRIAL_REQUEST_DECLINED`` (``notify_trial_request_declined``): the person who requested the trial.
* ``INVESTIGATION_ASSIGNED`` (``notify_assignment``): the new assignee.
* ``DECISION_REVIEW_PENDING`` (``notify_review_pending``): the named approver, else every approver but the submitter.
* ``SIGNOFF_COMPLETED`` (``notify_signoff_completed``): the case owner.
* ``RISK_REVIEW_REQUESTED`` (``notify_risk_review_requested``): the named reviewer, else every approver.
* ``CONNECTOR_SYNC_FAILED`` (``notify_connector_sync_failed``): the organization's customer administrators.
* ``AI_BUDGET_THRESHOLD`` (``notify_ai_budget_threshold``): the customer administrators, once per month at 80% and at 100%.
* ``MAIL_INTAKE_LIMIT_REACHED`` (``notify_mail_intake_limit``, the mail-in receiver): the customer administrators, at
  most once a day, when the organization's e-mail intake address reached its daily limit.
* ``FEEDBACK_SUBMITTED`` (``notify_feedback_submitted``): the MDARIX team (``MDARIX_TRIAL_ALERT_EMAIL``, else
  ``MDARIX_SUPPORT_EMAIL``).
* ``SECURITY_NOTICE`` (``notify_security_notice``): the account's owner (auth/security_notices.py builds it).
* ``SUPPORT_PROBLEM_REPORTED`` (backend/app/support_api.py): the support team.
* ``SUPPORT_ACCESS_AWAITING_CUSTOMER``, ``SUPPORT_ACCESS_GRANTED`` and ``SUPPORT_ACCESS_ENDED`` (support access,
  backend/app/support_access.py): the organization's decision makers (``support_decision_maker_emails``: its customer
  administrators, or a free trial's owner), when MDARIX asks, when they approve, and when an approved access ends;
  a free trial's other active members are also told when it is approved and when it ends, without a way to decide.
  One event per recipient (``recipient_user_id``), so a retry after one address failed sends that one email only.
* ``TEAM_CHANGE_NOTICE`` (backend/app/team_notices.py): one email about a change to an organization's team, to one
  person: a free trial's colleague, owner or the MDARIX team; a paying organization's user, or its other Customer
  Administrators when the change concerns an administrator account.
* ``READINESS_DIGEST`` (scheduler, backend/app/readiness_home/digest.py): the organization's quality leads (Leader and
  Quality Reviewer) who have not switched the weekly readiness email off; once per ISO week.
"""

from __future__ import annotations

import contextvars
import hashlib
import logging
import os
import re
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, func, or_
from sqlalchemy.orm import Session

from backend.app.db.models.foundation import AuthUser, Tenant
from backend.app.db.models.stage2 import OutboxEvent, SubscriptionLifecycle
from backend.app.role_codes import CUSTOMER_ADMIN_ALIASES, role_code

logger = logging.getLogger("mdarix.notifications")
TRIAL_STAGES = ("7_DAY", "1_DAY", "ENDED")

INVESTIGATION_ASSIGNED = "INVESTIGATION_ASSIGNED"
DECISION_REVIEW_PENDING = "DECISION_REVIEW_PENDING"
SIGNOFF_COMPLETED = "SIGNOFF_COMPLETED"
RISK_REVIEW_REQUESTED = "RISK_REVIEW_REQUESTED"
CONNECTOR_SYNC_FAILED = "CONNECTOR_SYNC_FAILED"
AI_BUDGET_THRESHOLD = "AI_BUDGET_THRESHOLD"
MAIL_INTAKE_LIMIT_REACHED = "MAIL_INTAKE_LIMIT_REACHED"
FEEDBACK_SUBMITTED = "FEEDBACK_SUBMITTED"
TRIAL_REQUEST_DECLINED = "TRIAL_REQUEST_DECLINED"
# A trial invitation the mail provider refused, sent again (backend/app/trial/service.py retry_invitation).
TRIAL_INVITATION_RETRY = "TRIAL_INVITATION_RETRY"
# One email about a change to an organization's team, to one person (backend/app/team_notices.py).
TEAM_CHANGE_NOTICE = "TEAM_CHANGE_NOTICE"
AI_BUDGET_THRESHOLDS = (80, 100)
# Roles whose holders approve decisions and review risks (backend/app/access/permissions.py).
APPROVER_ROLES = frozenset({"APPROVER", "LEADER"})
# The values a saved reminder email may use (Platform Admin > Plans & Licensing > Reminders).
TEMPLATE_VARIABLES = ("customer_name", "expiry_date", "days_remaining", "activation_link")
_TEMPLATE_VARIABLE = re.compile(r"\{\{\s*([a-zA-Z_]+)\s*\}\}")
# What a failed connector run means, for the administrator who reads the email.
SYNC_FAILURES = {
    "PROVIDER_READ_FAILED": "The system did not answer, or answered with an error.",
    "PROVIDER_RESPONSE_TOO_LARGE": "The system returned more data than one sync may read.",
    "PROVIDER_TENANT_SCOPE_INVALID": "The system returned records for a different organization.",
    "PROVIDER_NEXT_LINK_REFUSED": "The system's paging pointed to another address.",
    "PROVIDER_TOO_MANY_PAGES": "The system returned more pages than one sync may read.",
    "MAPPING_NOT_USABLE": "The released field mapping no longer fits the records.",
    "IMPORT_BLOCKED": "The records did not pass the import checks.",
}


class NotificationFailed(RuntimeError):
    """An email could not be delivered; the outbox retries the event."""


def _long_date(value: datetime) -> str:
    return f"{value.day} {value:%B %Y}"


def _organization(db: Session, tenant_id) -> str:
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    return (tenant.display_name or tenant.name) if tenant else "your organization"


def _uuid(value) -> uuid.UUID | None:
    if value is None or value == "":
        return None
    return value if isinstance(value, uuid.UUID) else uuid.UUID(str(value))


def _id(value) -> str | None:
    parsed = _uuid(value)
    return str(parsed) if parsed else None


def customer_admin_emails(db: Session, tenant_id) -> list[str]:
    normalized = func.upper(func.replace(func.trim(func.coalesce(AuthUser.role, "")), " ", "_"))
    rows = (
        db.query(AuthUser.username)
        .filter(
            AuthUser.tenant_id == tenant_id,
            normalized.in_(sorted(CUSTOMER_ADMIN_ALIASES)),
            func.upper(AuthUser.status) == "ACTIVE",
        )
        .all()
    )
    return sorted({row.username for row in rows if row.username})


def subscription_reminder_emails(db: Session, tenant_id) -> list[str]:
    """Who gets the organization's renewal reminders, as its notification settings say.

    The newest active reminder policy names the recipient types (Customer Administration > Notifications); the
    customer administrators are included when CUSTOMER_ADMIN is one of them, and every active contact saved with one
    of those types is added. An organization without a policy, or whose settings resolve to nobody, still reaches
    its customer administrators: a renewal reminder must never go to no one.
    """
    from backend.app.db.models.customer_lifecycle import CustomerContact, ReminderPolicyRecipient
    from backend.app.db.models.stage2 import ReminderPolicy

    policy = (
        db.query(ReminderPolicy)
        .filter(ReminderPolicy.tenant_id == tenant_id, func.upper(ReminderPolicy.status) == "ACTIVE")
        .order_by(ReminderPolicy.updated_at.desc())
        .first()
    )
    types = {str(value).upper() for value in ((policy.recipient_types if policy else None) or ["CUSTOMER_ADMIN"])}
    emails: set[str] = set()
    if "CUSTOMER_ADMIN" in types:
        emails.update(customer_admin_emails(db, tenant_id))
    contacts = (
        db.query(CustomerContact.email)
        .join(ReminderPolicyRecipient, ReminderPolicyRecipient.contact_id == CustomerContact.id)
        .filter(
            ReminderPolicyRecipient.tenant_id == tenant_id,
            func.upper(ReminderPolicyRecipient.status) == "ACTIVE",
            func.upper(ReminderPolicyRecipient.recipient_type).in_(sorted(types)),
            func.upper(CustomerContact.status) == "ACTIVE",
        )
        .all()
    )
    emails.update(row.email.strip().lower() for row in contacts if row.email and "@" in row.email)
    return sorted(emails) or customer_admin_emails(db, tenant_id)


def _fill(text: str, values: dict[str, str]) -> str | None:
    """A saved template with its values filled in; None when it uses a value MDARIX does not know."""
    if any(name not in values for name in _TEMPLATE_VARIABLE.findall(text)):
        return None
    return _TEMPLATE_VARIABLE.sub(lambda match: values[match.group(1)], text)


def reminder_template(
    db: Session, row: SubscriptionLifecycle, stage: str | None, values: dict[str, str]
) -> tuple[str, str] | None:
    """The organization's own reminder email for this reminder, filled in, or None for the standard wording.

    The newest saved email for the reminder's exact stage (for example ``30_DAY``) wins, then the one for the
    subscription's phase: EXPIRING before the end date, GRACE and EXPIRED after it. Superseded and retired versions
    are never used. A template that names a value MDARIX cannot fill falls back to the standard wording rather than
    sending a customer a raw ``{{placeholder}}``.
    """
    from backend.app.db.models.stage2 import EmailTemplate

    phase = {"GRACE": "GRACE", "EXPIRED": "EXPIRED"}.get(str(row.status or "").upper(), "EXPIRING")
    for wanted in [value for value in (stage, phase) if value]:
        template = (
            db.query(EmailTemplate)
            .filter(
                EmailTemplate.tenant_id == row.tenant_id,
                EmailTemplate.stage == wanted,
                func.upper(EmailTemplate.status).in_(["ACTIVE", "DRAFT"]),
            )
            .order_by(EmailTemplate.created_at.desc())
            .first()
        )
        if template is None:
            continue
        subject, body = _fill(template.subject or "", values), _fill(template.body or "", values)
        if subject and body and subject.strip() and body.strip():
            return " ".join(subject.split())[:200], body.strip()
        logger.warning("Reminder template %s uses an unknown value; the standard wording is used", template.id)
        return None
    return None


# The emails an event already sent, kept in its payload (``SENT``) so a retry after one refused address does not
# email everyone again (code audit 14). Each mark is a hash of the email's place in the event and the address, so the
# queue still holds no address.
SENT = "sent"
_sent: contextvars.ContextVar[dict | None] = contextvars.ContextVar("notifications_sent", default=None)


def _deliver(send, recipients: list[str], **details) -> None:
    from auth.emailer import EmailDeliveryError

    sent = _sent.get()
    call = 0
    if sent is not None:
        sent["call"] += 1
        call = sent["call"]
    failures = 0
    for recipient in recipients:
        mark = hashlib.sha256(f"{call}|{recipient.strip().lower()}".encode()).hexdigest()[:16]
        if sent is not None and mark in sent["marks"]:
            continue
        try:
            outcome = send(recipient, **details)
        except EmailDeliveryError:
            failures += 1
            continue
        if sent is not None:
            sent["marks"].append(mark)
        if outcome == "NOT_CONFIGURED":
            logger.warning("Email is not configured; notification not sent")
    if failures:
        raise NotificationFailed(f"{failures} of {len(recipients)} emails could not be delivered")


# ------------------------------------------------------------------------------------------- queueing (producers)
#
# Every producer takes ``(db, tenant_id, **ids)`` and adds one outbox event to ``db`` (the control-plane session; the
# caller commits). People may be given as an account id or, where a record only stores it, as the account's email
# (for example a case's ``owner_ref``): it is resolved to the account id here, inside the organization, so the
# queue never holds an address. Identifiers a producer does not need (for example ``investigation_id`` on a
# decision) are accepted and ignored, so callers can pass what they have.


def _queue(db: Session, tenant_id, event_name: str, aggregate_type: str, aggregate_id, payload: dict) -> OutboxEvent:
    tenant = _uuid(tenant_id)
    event = OutboxEvent(
        id=uuid.uuid4(),
        tenant_id=tenant,
        event_name=event_name,
        aggregate_type=aggregate_type,
        aggregate_id=_uuid(aggregate_id),
        payload={"tenant_id": str(tenant), **payload},
        occurred_at=datetime.now(timezone.utc),
    )
    db.add(event)
    return event


def _user_id(db: Session, tenant_id, value) -> str | None:
    """An account of the organization given by id or by email, as an id (None when there is no such account)."""
    if value is None or str(value).strip() == "":
        return None
    text = str(value).strip()
    try:
        candidate = AuthUser.id == uuid.UUID(text)
    except ValueError:
        candidate = func.lower(AuthUser.username) == text.lower()
    row = db.query(AuthUser.id).filter(AuthUser.tenant_id == _uuid(tenant_id), candidate).first()
    return str(row[0]) if row else None


def _first(refs: dict, *names: str):
    return next((refs[name] for name in names if refs.get(name) not in (None, "")), None)


def _label(value) -> str | None:
    """A record's human reference (case or risk number) for the email; never longer than a reference is."""
    text = " ".join(str(value or "").split())
    return text[:120] or None


_CASE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,39}")


def _case(refs: dict) -> dict:
    """``{"investigation_business_id": ...}`` when the producer named the case (INV000147), so the email can open
    it (/app/<view>?case=...); otherwise nothing, and the event is queued exactly as before."""
    value = str(refs.get("investigation_business_id") or "").strip()
    return {"investigation_business_id": value} if _CASE_ID.fullmatch(value) else {}


def notify_assignment(db: Session, tenant_id, *, investigation_id, **refs) -> OutboxEvent | None:
    """Tell a person an investigation was assigned to them (nothing when they assigned it to themselves).

    ``assignee_user_id`` (or ``assignee_ref``/``assignee``: id or email), optional ``assigned_by_user_id`` (or
    ``assigned_by``) and ``reference`` (the case number shown in the email).
    """
    assignee = _user_id(db, tenant_id, _first(refs, "assignee_user_id", "assignee_ref", "assignee"))
    actor = _user_id(db, tenant_id, _first(refs, "assigned_by_user_id", "assigned_by", "actor_user_id"))
    if assignee is None or assignee == actor:
        return None
    return _queue(
        db,
        tenant_id,
        INVESTIGATION_ASSIGNED,
        "Investigation",
        investigation_id,
        {
            "investigation_id": _id(investigation_id),
            "assignee_user_id": assignee,
            "assigned_by_user_id": actor,
            "reference": _label(_first(refs, "reference", "investigation_identifier")),
            **_case(refs),
        },
    )


def notify_review_pending(db: Session, tenant_id, *, decision_id, **refs) -> OutboxEvent:
    """Tell the approver (``approver_user_id``) or, when none is named, every approver except the person who asked
    (``submitted_by_user_id`` or ``requested_by``) that a decision awaits their approval."""
    return _queue(
        db,
        tenant_id,
        DECISION_REVIEW_PENDING,
        "Decision",
        decision_id,
        {
            "decision_id": _id(decision_id),
            "submitted_by_user_id": _user_id(db, tenant_id, _first(refs, "submitted_by_user_id", "requested_by")),
            "approver_user_id": _user_id(db, tenant_id, _first(refs, "approver_user_id", "approver_ref")),
            "reference": _label(_first(refs, "reference", "investigation_identifier")),
            **_case(refs),
        },
    )


def notify_signoff_completed(db: Session, tenant_id, *, decision_id, **refs) -> OutboxEvent | None:
    """Tell the case owner (``owner_user_id``, or ``owner_ref``: id or email) that the decision on their case was
    signed (``decision``: APPROVE or REJECT), unless they signed it themselves (``signed_by_user_id``/
    ``signer_user_id``)."""
    owner = _user_id(db, tenant_id, _first(refs, "owner_user_id", "owner_ref", "owner"))
    signer = _user_id(db, tenant_id, _first(refs, "signed_by_user_id", "signer_user_id", "signed_by"))
    if owner is None or owner == signer:
        return None
    outcome = str(refs.get("decision") or "").upper()
    return _queue(
        db,
        tenant_id,
        SIGNOFF_COMPLETED,
        "Decision",
        decision_id,
        {
            "decision_id": _id(decision_id),
            "owner_user_id": owner,
            "signed_by_user_id": signer,
            "decision": outcome if outcome in {"APPROVE", "REJECT"} else None,
            "reference": _label(_first(refs, "reference", "investigation_identifier")),
            **_case(refs),
        },
    )


def notify_risk_review_requested(db: Session, tenant_id, *, risk_id, **refs) -> OutboxEvent:
    """Tell the named reviewer (``reviewer_user_id``) or, when none is named, every approver except the requester
    (``requested_by_user_id``/``requested_by``) that a risk (``risk_identifier`` or ``reference``) needs review.
    The requester's free-text reason stays in the audit trail; it is not copied into the queue."""
    return _queue(
        db,
        tenant_id,
        RISK_REVIEW_REQUESTED,
        "Risk",
        risk_id,
        {
            "risk_id": _id(risk_id),
            "requested_by_user_id": _user_id(db, tenant_id, _first(refs, "requested_by_user_id", "requested_by")),
            "reviewer_user_id": _user_id(db, tenant_id, _first(refs, "reviewer_user_id", "reviewer_ref")),
            "reference": _label(_first(refs, "reference", "risk_identifier")),
        },
    )


def notify_connector_sync_failed(db: Session, tenant_id, *, connector_id, failure: str, **_refs) -> OutboxEvent:
    """Tell the customer administrators a scheduled connector sync failed (``failure`` is a code, never a message
    from the customer's system)."""
    return _queue(
        db,
        tenant_id,
        CONNECTOR_SYNC_FAILED,
        "ConnectorConfiguration",
        connector_id,
        {"connector_id": _id(connector_id), "failure": re.sub(r"[^A-Z0-9_]", "", str(failure).upper())[:80]},
    )


def notify_ai_budget_threshold(
    db: Session, tenant_id, *, percent: int, month: str | None = None, tokens_used=None, budget=None, **_refs
) -> OutboxEvent | None:
    """Tell the customer administrators the organization reached 80% or 100% of its monthly AI budget.

    Idempotent: one email per organization, month (``YYYY-MM``, default the current one) and threshold, however
    often the caller reports the same crossing. Returns None when it was already queued.
    """
    percent = int(percent)
    if percent not in AI_BUDGET_THRESHOLDS:
        raise ValueError(f"AI budget alerts are sent at {AI_BUDGET_THRESHOLDS} percent")
    month = month or datetime.now(timezone.utc).strftime("%Y-%m")
    if not re.fullmatch(r"\d{4}-\d{2}", month):
        raise ValueError("month must be YYYY-MM")
    already = (
        db.query(OutboxEvent.id)
        .filter(
            OutboxEvent.tenant_id == _uuid(tenant_id),
            OutboxEvent.event_name == AI_BUDGET_THRESHOLD,
            OutboxEvent.payload["month"].as_string() == month,
            OutboxEvent.payload["percent"].as_integer() == percent,
        )
        .first()
    )
    if already:
        return None
    return _queue(
        db,
        tenant_id,
        AI_BUDGET_THRESHOLD,
        "Tenant",
        tenant_id,
        {
            "percent": percent,
            "month": month,
            "tokens_used": int(tokens_used) if tokens_used is not None else None,
            "budget": int(budget) if budget is not None else None,
        },
    )


notify_ai_budget = notify_ai_budget_threshold  # shorter name, same function


def notify_mail_intake_limit(
    db: Session, tenant_id, *, limit: int, day: str | None = None, **_refs
) -> OutboxEvent | None:
    """Tell the customer administrators the organization's e-mail intake address reached its daily limit (B7b, spec
    4.5): senders get a temporary refusal and retry. At most once a day (UTC, ``YYYY-MM-DD``) per organization; None
    when already queued. The event's id comes from the organization and the day, so two receivers refusing at the same
    moment cannot both queue it (the second insert fails)."""
    tenant = _uuid(tenant_id)
    day = day or datetime.now(timezone.utc).date().isoformat()
    already = (
        db.query(OutboxEvent.id)
        .filter(
            OutboxEvent.tenant_id == tenant,
            OutboxEvent.event_name == MAIL_INTAKE_LIMIT_REACHED,
            OutboxEvent.payload["day"].as_string() == day,
        )
        .first()
    )
    if already:
        return None
    event = _queue(db, tenant, MAIL_INTAKE_LIMIT_REACHED, "Tenant", tenant, {"day": day, "limit": int(limit)})
    event.id = uuid.uuid5(tenant, f"{MAIL_INTAKE_LIMIT_REACHED}|{day}")
    return event


def notify_feedback_submitted(db: Session, tenant_id, *, feedback_id, **_refs) -> OutboxEvent:
    """Tell the MDARIX team a customer sent feedback (the worker reads the response itself)."""
    return _queue(db, tenant_id, FEEDBACK_SUBMITTED, "TrialFeedback", feedback_id, {"feedback_id": _id(feedback_id)})


def notify_trial_request_declined(db: Session, tenant_id, *, request_id, **_refs) -> OutboxEvent:
    """Tell a trial requester, politely, that the request was declined (``tenant_id``: the reviewing admin's)."""
    return _queue(
        db, tenant_id, TRIAL_REQUEST_DECLINED, "OnboardingRequest", request_id, {"request_id": _id(request_id)}
    )


SUPPORT_ACCESS_AWAITING_CUSTOMER = "SUPPORT_ACCESS_AWAITING_CUSTOMER"


SUPPORT_ACCESS_GRANTED = "SUPPORT_ACCESS_GRANTED"
SUPPORT_ACCESS_ENDED = "SUPPORT_ACCESS_ENDED"
# How an approved support access ended, as SUPPORT_ACCESS_ENDED carries it.
SUPPORT_ACCESS_ENDINGS = frozenset({"EXPIRED", "REVOKED_BY_CUSTOMER", "REVOKED_BY_MDARIX"})


# Who one support access event's email is for (``audience``, with ``recipient_user_id``): a decision maker, or a free
# trial's colleague, told for information only.
SUPPORT_DECIDER = "DECIDER"
SUPPORT_COLLEAGUE = "COLLEAGUE"


def _queue_support_access(
    db: Session, tenant_id, event_name: str, grant_id, payload: dict, *, colleagues: bool = False
) -> list[OutboxEvent]:
    """One event per recipient (0.10.40): the worker retries a failed address alone, and a retry never sends anyone
    else's email again. The recipients are the decision makers (and, with ``colleagues``, a free trial's other active
    members) now, as account ids; each is checked again when its email is sent."""
    tenant = _uuid(tenant_id)
    deciders, trial = support_decision_maker_emails(db, tenant)
    targets = [(SUPPORT_DECIDER, address) for address in deciders]
    if colleagues and trial:
        targets += [(SUPPORT_COLLEAGUE, address) for address in trial_colleague_emails(db, tenant, deciders)]
    events = []
    for audience, address in targets:
        user_id = _user_id(db, tenant, address)
        if user_id:
            events.append(
                _queue(
                    db,
                    tenant,
                    event_name,
                    "SupportAccessGrant",
                    grant_id,
                    {**payload, "grant_id": _id(grant_id), "audience": audience, "recipient_user_id": user_id},
                )
            )
    return events


def notify_support_access_awaiting_customer(db: Session, tenant_id, *, grant_id, **_refs) -> list[OutboxEvent]:
    """Tell the organization's decision makers that MDARIX asks for support access (backend/app/support_access.py)."""
    return _queue_support_access(db, tenant_id, SUPPORT_ACCESS_AWAITING_CUSTOMER, grant_id, {})


def notify_support_access_granted(db: Session, tenant_id, *, grant_id, **_refs) -> list[OutboxEvent]:
    """Confirm to the decision makers that support access was approved, and until when (also a security notice); a
    free trial's colleagues are told too."""
    return _queue_support_access(db, tenant_id, SUPPORT_ACCESS_GRANTED, grant_id, {}, colleagues=True)


def notify_support_access_ended(db: Session, tenant_id, *, grant_id, ended: str, **_refs) -> list[OutboxEvent]:
    """Tell the decision makers that an approved support access ended: on its own, or revoked by them or MDARIX; a
    free trial's colleagues are told too."""
    if ended not in SUPPORT_ACCESS_ENDINGS:
        raise ValueError(f"Unknown end of support access: {ended}")
    return _queue_support_access(db, tenant_id, SUPPORT_ACCESS_ENDED, grant_id, {"ended": ended}, colleagues=True)


def _one_recipient(db: Session, tenant_id, payload: dict, deciders: list[str], colleagues: list[str]):
    """The decision makers and colleagues one event's email goes to: its one recipient while they still are one (an
    account deactivated, or no longer a decision maker, gets nothing). An event queued before 0.10.40 names no
    recipient and goes to everyone, as it did then."""
    if not payload.get("recipient_user_id"):
        return deciders, colleagues
    user = _active_user(db, tenant_id, payload["recipient_user_id"])
    address = user.username if user else None
    if payload.get("audience") == SUPPORT_COLLEAGUE:
        return [], [address] if address in colleagues else []
    return ([address] if address in deciders else []), []


def support_decision_maker_emails(db: Session, tenant_id) -> tuple[list[str], bool]:
    """Who decides on support access to the organization, and whether it is a free trial: a trial's owner (its only
    decision maker, backend/app/support_access_api.py require_decision_maker) while their account is active, else the
    organization's active customer administrators."""
    from backend.app.trial.service import trial_subscription
    from backend.app.trial.team import trial_request

    if trial_subscription(db, tenant_id) is None:
        return customer_admin_emails(db, tenant_id), False
    request = trial_request(db, tenant_id)
    email = (request.email if request else "").strip().lower()
    owner = (
        db.query(AuthUser.username)
        .filter(
            AuthUser.tenant_id == tenant_id,
            func.lower(AuthUser.username) == email,
            func.upper(AuthUser.status) == "ACTIVE",
        )
        .first()
        if email
        else None
    )
    return ([owner.username] if owner else []), True


def _utc_moment(value: datetime) -> str:
    """A grant's time as its emails write it: the day and time in UTC, so no reader takes it for another day."""
    moment = (value if value.tzinfo else value.replace(tzinfo=timezone.utc)).astimezone(timezone.utc)
    return f"{_long_date(moment)}, {moment:%H:%M} UTC"


def _support_access_request(db: Session, payload: dict, emailer) -> None:
    from backend.app.support_access import AWAITING_CUSTOMER, SupportScope

    tenant_id = _uuid(payload.get("tenant_id"))
    grant = _support_grant(db, payload)
    if grant is None or grant.status != AWAITING_CUSTOMER:
        return  # decided, revoked or expired before the email went out: nothing to ask any more
    person = db.query(AuthUser).filter(AuthUser.id == grant.platform_user_id).first()
    scope = SupportScope.stored(grant.scope)
    recipients, trial = support_decision_maker_emails(db, tenant_id)
    recipients, _ = _one_recipient(db, tenant_id, payload, recipients, [])
    _deliver(
        emailer.send_support_access_request,
        recipients,
        organization=_organization(db, tenant_id),
        person=(person.display_name or person.username) if person else "An MDARIX support colleague",
        areas=[item["label"] for item in scope.describe()],
        write=scope.write,
        expires=_utc_moment(grant.expires_at),
        reason=grant.reason,
        trial=trial,
    )


def _support_grant(db: Session, payload: dict):
    from backend.app.db.models.customer_lifecycle import SupportAccessGrant

    return (
        db.query(SupportAccessGrant)
        .filter(
            SupportAccessGrant.id == _uuid(payload.get("grant_id")),
            SupportAccessGrant.tenant_id == _uuid(payload.get("tenant_id")),
        )
        .first()
    )


def _support_access_notice(db: Session, event_name: str, payload: dict, emailer) -> None:
    """The confirmation of an approval, or the notice that an approved access ended. An approval revoked before the
    email goes out sends no confirmation (the ended notice follows instead)."""
    from backend.app.support_access import APPROVED, SupportScope

    grant = _support_grant(db, payload)
    if grant is None:
        return
    tenant_id = grant.tenant_id
    person = db.query(AuthUser).filter(AuthUser.id == grant.platform_user_id).first()
    who = (person.display_name or person.username) if person else "An MDARIX support colleague"
    recipients, trial = support_decision_maker_emails(db, tenant_id)
    scope = SupportScope.stored(grant.scope)
    common = {"organization": _organization(db, tenant_id), "person": who, "trial": trial}
    # A free trial's other members are told too, without a way to decide (only the owner decides).
    colleagues = trial_colleague_emails(db, tenant_id, recipients) if trial else []
    recipients, colleagues = _one_recipient(db, tenant_id, payload, recipients, colleagues)
    organization = common["organization"]
    if event_name == SUPPORT_ACCESS_GRANTED:
        if grant.status != APPROVED:
            return
        decider = db.query(AuthUser).filter(AuthUser.id == grant.customer_decided_by).first()
        details = {
            "areas": [item["label"] for item in scope.describe()],
            "write": scope.write,
            "expires": _utc_moment(grant.expires_at),
            "approved_by": (decider.display_name or decider.username) if decider else "Your organization",
        }
        _deliver(emailer.send_support_access_granted, recipients, **details, **common)
        _deliver(
            emailer.send_support_access_colleague_granted, colleagues, organization=organization, person=who, **details
        )
        return
    ended = str(payload.get("ended") or "EXPIRED")
    at = grant.revoked_at if ended != "EXPIRED" and grant.revoked_at else grant.expires_at
    _deliver(emailer.send_support_access_ended, recipients, ended=ended, when=_utc_moment(at), **common)
    _deliver(
        emailer.send_support_access_colleague_ended,
        colleagues,
        organization=organization,
        person=who,
        ended=ended,
        when=_utc_moment(at),
    )


def trial_colleague_emails(db: Session, tenant_id, exclude: list[str]) -> list[str]:
    """The other active people of a free trial: its colleagues, never the owner (in ``exclude``), MDARIX staff
    accounts or the sample author (an account nobody signs in with)."""
    from backend.app.access.authz import platform_account_clause

    left_out = {address.strip().lower() for address in exclude}
    rows = (
        db.query(AuthUser.username)
        .filter(
            AuthUser.tenant_id == tenant_id,
            func.upper(AuthUser.status) == "ACTIVE",
            ~platform_account_clause(),
        )
        .all()
    )
    return sorted(
        {
            row.username
            for row in rows
            if row.username
            and row.username.strip().lower() not in left_out
            and not row.username.startswith("sample-author+")
        }
    )


def notify_security_notice(db: Session, tenant_id, *, user_id, kind: str, **_refs) -> OutboxEvent | None:
    """Tell a person the way they sign in changed (auth/security_notices.py: kinds, wording, delivery)."""
    from auth.security_notices import queue_security_notice

    user = db.query(AuthUser).filter(AuthUser.id == _uuid(user_id), AuthUser.tenant_id == _uuid(tenant_id)).first()
    if user is None:
        return None
    return queue_security_notice(db, user, kind)


# ------------------------------------------------------------------------------------------- delivery (worker)


def _active_user(db: Session, tenant_id, user_id) -> AuthUser | None:
    if not user_id:
        return None
    return (
        db.query(AuthUser)
        .filter(
            AuthUser.id == _uuid(user_id),
            AuthUser.tenant_id == _uuid(tenant_id),
            func.upper(AuthUser.status) == "ACTIVE",
        )
        .first()
    )


def _name(db: Session, tenant_id, user_id) -> str | None:
    """A colleague's display name (never their address) for the email body."""
    if not user_id:
        return None
    user = db.query(AuthUser).filter(AuthUser.id == _uuid(user_id), AuthUser.tenant_id == _uuid(tenant_id)).first()
    if user is None:
        return None
    return (user.display_name or "").strip() or None


def approver_emails(db: Session, tenant_id, *, exclude_user_id=None) -> list[str]:
    """Active approvers and leaders of the organization: any of their roles (the role assignment, else the account
    role, and their additional workflow roles) is Approver or Leader."""
    from backend.app.access.permissions import roles_of_user

    users = (
        db.query(AuthUser).filter(AuthUser.tenant_id == _uuid(tenant_id), func.upper(AuthUser.status) == "ACTIVE").all()
    )
    excluded = _id(exclude_user_id)
    return sorted(
        {
            user.username
            for user in users
            if user.username
            and str(user.id) != excluded
            and any(role_code(role) in APPROVER_ROLES for role in roles_of_user(db, user))
        }
    )


def _one_or_approvers(db: Session, tenant_id, named_user_id, actor_user_id) -> list[str]:
    if named_user_id:
        user = _active_user(db, tenant_id, named_user_id)
        return [user.username] if user and user.username else []
    return approver_emails(db, tenant_id, exclude_user_id=actor_user_id)


def _reference(payload: dict, key: str) -> str:
    """How an email names the record: the reference the producer gave (its business id, e.g. INV000012), else the
    record's business id in the event, else plain words. Never a UUID or part of one: people do not see UUIDs."""
    business_key = f"{key[: -len('_id')]}_business_id" if key.endswith("_id") else f"{key}_business_id"
    return payload.get("reference") or payload.get(business_key) or "the record (open MDARIX to see it)"


def _staff_alert_address() -> str:
    return (os.getenv("MDARIX_TRIAL_ALERT_EMAIL") or os.getenv("MDARIX_SUPPORT_EMAIL") or "").strip()


def _days_left(expires_at: datetime) -> int:
    """Whole days left until ``expires_at``, rounded up as on every screen (trial status, early exit); 0 once passed.
    A floor said "ends today" the day before the end and "in 6 days" in the 7-day reminder (FUN-03)."""
    return max(0, int(-(-(expires_at - datetime.now(timezone.utc)).total_seconds() // 86400)))


def _subscription_reminder(db: Session, payload: dict, emailer) -> None:
    row = db.get(SubscriptionLifecycle, uuid.UUID(str(payload["subscription_id"])))
    if row is None:
        return
    organization = _organization(db, row.tenant_id)
    days_left = _days_left(row.expires_at)
    expires_on = _long_date(row.expires_at)
    from auth.emailer import company

    template = reminder_template(
        db,
        row,
        payload.get("stage"),
        {
            "customer_name": organization,
            "expiry_date": expires_on,
            "days_remaining": str(days_left),
            "activation_link": f"{company().app_url}/app",
        },
    )
    _deliver(
        lambda recipient, **kw: emailer.send_subscription_reminder(recipient, **kw),
        subscription_reminder_emails(db, row.tenant_id),
        organization=organization,
        expires_on=expires_on,
        days_left=days_left,
        template=template,
    )


def _trial_reminder(db: Session, payload: dict, emailer) -> None:
    from backend.app.trial.service import long_moment
    from backend.app.trial.team import trial_request

    row = db.get(SubscriptionLifecycle, uuid.UUID(str(payload["subscription_id"])))
    request = trial_request(db, row.tenant_id) if row is not None else None
    if row is None or request is None:
        return
    organization = _organization(db, row.tenant_id)
    from backend.app.trial import retention

    # 30 days after the trial ends, counting a grace extension and an open request to move the data into the MVP;
    # the emails say "at the earliest", since the date can still move later, and give no date under a legal hold
    # (backend/app/trial/retention.py, the one projection). Both dates carry the time and "UTC", so no reader takes
    # them for a day earlier or later (FUN-15).
    delete_on = retention.deletion_words(retention.projection(db, db, row))
    if payload.get("stage") == "ENDED" and payload.get("early"):
        # Ended early at the owner's request, data kept until the usual date (backend/app/trial/early_exit.py).
        _deliver(
            lambda recipient, **kw: emailer.send_trial_ended_early(recipient, **kw),
            [request.email],
            organization=organization,
            data_deleted=False,
            delete_on=delete_on,
        )
        return
    if payload.get("stage") == "ENDED":
        _deliver(
            lambda recipient, **kw: emailer.send_trial_ended(recipient, **kw),
            [request.email],
            organization=organization,
            delete_on=delete_on,
        )
        return
    _deliver(
        lambda recipient, **kw: emailer.send_trial_reminder(recipient, **kw),
        [request.email],
        organization=organization,
        days_left=_days_left(row.expires_at),
        ends_on=long_moment(row.expires_at),
        delete_on=delete_on,
    )


def _trial_declined(db: Session, payload: dict, emailer) -> None:
    from backend.app.db.models.stage2 import OnboardingRequest

    row = db.get(OnboardingRequest, uuid.UUID(str(payload["request_id"])))
    if row is None or row.status != "DECLINED":  # withdrawn or reconsidered meanwhile
        return
    _deliver(
        lambda recipient, **kw: emailer.send_trial_request_declined(recipient, **kw),
        [row.email],
        display_name=row.display_name,
        organization=row.organization,
    )


def _feedback(db: Session, payload: dict, emailer) -> None:
    from backend.app.db.models.stage2 import TrialFeedback

    recipient = _staff_alert_address()
    row = db.get(TrialFeedback, uuid.UUID(str(payload["feedback_id"])))
    if row is None:
        return
    if not recipient:
        logger.warning(
            "No MDARIX_TRIAL_ALERT_EMAIL or MDARIX_SUPPORT_EMAIL; feedback %s was stored unannounced", row.id
        )
        return
    _deliver(
        lambda to, **kw: emailer.send_feedback_alert(to, **kw),
        [recipient],
        organization=row.organization_name,
        rating=row.rating_overall,
        recommend_score=row.recommend_score,
        consent=row.publish_consent,
        contact_ok=bool(row.contact_ok),
    )


def _connector_failed(db: Session, payload: dict, emailer) -> None:
    from backend.app.db.models.foundation import ConnectorConfiguration

    tenant_id = _uuid(payload["tenant_id"])
    row = (
        db.query(ConnectorConfiguration)
        .filter(
            ConnectorConfiguration.id == _uuid(payload["connector_id"]), ConnectorConfiguration.tenant_id == tenant_id
        )
        .first()
    )
    if row is None:
        return
    code = str(payload.get("failure") or "")
    _deliver(
        lambda recipient, **kw: emailer.send_connector_sync_failed_notice(recipient, **kw),
        customer_admin_emails(db, tenant_id),
        organization=_organization(db, tenant_id),
        connection=row.code,
        failure=SYNC_FAILURES.get(code, f"The sync stopped ({code or 'unknown reason'})."),
    )


def _ai_budget(db: Session, payload: dict, emailer) -> None:
    tenant_id = _uuid(payload["tenant_id"])
    month = datetime.strptime(str(payload["month"]), "%Y-%m")
    _deliver(
        lambda recipient, **kw: emailer.send_ai_budget_notice(recipient, **kw),
        customer_admin_emails(db, tenant_id),
        organization=_organization(db, tenant_id),
        percent=int(payload["percent"]),
        month=f"{month:%B %Y}",
        tokens_used=payload.get("tokens_used"),
        budget=payload.get("budget"),
    )


def _mail_intake_limit(db: Session, payload: dict, emailer) -> None:
    tenant_id = _uuid(payload["tenant_id"])
    _deliver(
        lambda recipient, **kw: emailer.send_mail_intake_limit_notice(recipient, **kw),
        customer_admin_emails(db, tenant_id),
        organization=_organization(db, tenant_id),
        limit=int(payload["limit"]),
        day=_long_date(datetime.strptime(str(payload["day"]), "%Y-%m-%d")),
    )


def _personal(db: Session, tenant_id, user_id) -> list[str]:
    user = _active_user(db, tenant_id, user_id)
    return [user.username] if user and user.username else []


def _work_notice(db: Session, event_name: str, payload: dict, emailer) -> None:
    """Assignment, review, sign-off and risk-review emails: who gets them and what they say about whom."""
    tenant_id = _uuid(payload["tenant_id"])
    get = payload.get
    if event_name == INVESTIGATION_ASSIGNED:
        recipients = _personal(db, tenant_id, get("assignee_user_id"))
        send = emailer.send_assignment_notice
        details = {"reference": _reference(payload, "investigation_id"), "assigned_by": get("assigned_by_user_id")}
    elif event_name == DECISION_REVIEW_PENDING:
        recipients = _one_or_approvers(db, tenant_id, get("approver_user_id"), get("submitted_by_user_id"))
        send = emailer.send_review_pending_notice
        details = {"reference": _reference(payload, "decision_id"), "submitted_by": get("submitted_by_user_id")}
    elif event_name == SIGNOFF_COMPLETED:
        recipients = _personal(db, tenant_id, get("owner_user_id"))
        send = emailer.send_signoff_completed_notice
        details = {"reference": _reference(payload, "decision_id"), "signed_by": get("signed_by_user_id")}
        details["decision"] = get("decision")
    else:  # RISK_REVIEW_REQUESTED
        recipients = _one_or_approvers(db, tenant_id, get("reviewer_user_id"), get("requested_by_user_id"))
        send = emailer.send_risk_review_requested_notice
        details = {"reference": _reference(payload, "risk_id"), "requested_by": get("requested_by_user_id")}
    # The colleague who acted is named by display name, looked up now (the payload has their id only).
    names = {"assigned_by", "submitted_by", "signed_by", "requested_by"}
    details = {key: (_name(db, tenant_id, value) if key in names else value) for key, value in details.items()}
    if get("investigation_business_id") and event_name != RISK_REVIEW_REQUESTED:
        # The case the email is about: its button opens it (/app/investigations or /app/decision ?case=INV000147).
        details["case"] = get("investigation_business_id")
    _deliver(
        lambda recipient, **kw: send(recipient, **kw),
        recipients,
        organization=_organization(db, tenant_id),
        **details,
    )


WORK_EVENTS = (INVESTIGATION_ASSIGNED, DECISION_REVIEW_PENDING, SIGNOFF_COMPLETED, RISK_REVIEW_REQUESTED)


def handle_event(db: Session, event_name: str, payload: dict) -> bool:
    """Send the notification for one outbox event. False when the event is not a notification. The emails sent are
    marked in ``payload[SENT]``; the worker keeps the payload of a failed event, so its retry skips them."""
    token = _sent.set({"marks": payload.setdefault(SENT, []), "call": 0})
    try:
        return _handle_event(db, event_name, payload)
    finally:
        _sent.reset(token)


def _handle_event(db: Session, event_name: str, payload: dict) -> bool:
    from auth import emailer

    if event_name == "SUBSCRIPTION_REMINDER":
        _subscription_reminder(db, payload, emailer)
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
        _trial_reminder(db, payload, emailer)
        return True
    if event_name == TRIAL_REQUEST_DECLINED:
        _trial_declined(db, payload, emailer)
        return True
    if event_name == TRIAL_INVITATION_RETRY:
        from backend.app.trial.service import retry_invitation

        if retry_invitation(db, payload["request_id"]) not in ("SENT", "SKIPPED", "NOT_CONFIGURED"):
            raise NotificationFailed("the trial invitation could not be delivered")
        return True
    if event_name in WORK_EVENTS:
        _work_notice(db, event_name, payload, emailer)
        return True
    from backend.app.oversight import urgent_alert

    if event_name in urgent_alert.EVENTS:
        urgent_alert.deliver(db, event_name, payload, emailer)
        return True
    if event_name == CONNECTOR_SYNC_FAILED:
        _connector_failed(db, payload, emailer)
        return True
    if event_name == AI_BUDGET_THRESHOLD:
        _ai_budget(db, payload, emailer)
        return True
    if event_name == MAIL_INTAKE_LIMIT_REACHED:
        _mail_intake_limit(db, payload, emailer)
        return True
    if event_name == FEEDBACK_SUBMITTED:
        _feedback(db, payload, emailer)
        return True
    if event_name == SUPPORT_ACCESS_AWAITING_CUSTOMER:
        _support_access_request(db, payload, emailer)
        return True
    if event_name in (SUPPORT_ACCESS_GRANTED, SUPPORT_ACCESS_ENDED):
        _support_access_notice(db, event_name, payload, emailer)
        return True
    if event_name == TEAM_CHANGE_NOTICE:
        from backend.app.team_notices import deliver

        deliver(db, payload)
        return True
    if event_name == "READINESS_DIGEST":
        from backend.app.readiness_home.digest import deliver

        deliver(db, payload)
        return True
    from auth.security_notices import handle_security_notice

    if handle_security_notice(db, event_name, payload):
        return True
    if event_name == "SUPPORT_PROBLEM_REPORTED":
        # scripts/run_outbox_worker.py hands this event to support_api directly; any other worker path ends here.
        from backend.app.support_api import deliver_problem_report

        try:
            deliver_problem_report(db, payload)
        except emailer.EmailDeliveryError as exc:
            raise NotificationFailed("problem report could not be delivered") from exc
        return True
    return False


# How far before (or after) the end each trial reminder's window opens.
_STAGE_OPENS = {"7_DAY": timedelta(days=7), "1_DAY": timedelta(days=1), "ENDED": timedelta(0)}


def trial_reminder_end(expires_at: datetime) -> str:
    """The end date a trial reminder is sent for, as kept in its outbox payload (``expires_at``): UTC ISO, so the
    same end always reads the same whatever the database session's time zone."""
    return expires_at.astimezone(timezone.utc).isoformat()


def _trial_reminder_sent(db: Session, row: SubscriptionLifecycle, stage: str) -> bool:
    """Whether this stage's reminder was already queued for the trial's current end date. An extension moves the end
    date, so the 7-day, 1-day and ended emails come again for the new date, once each (FUN-04). A reminder queued
    before 0.10.36 has no ``expires_at``; it counts for the current end when it was queued inside this stage's window
    for that end, which an extension moves past."""
    sent_for = OutboxEvent.payload["expires_at"].as_string()
    return (
        db.query(OutboxEvent.id)
        .filter(
            OutboxEvent.tenant_id == row.tenant_id,
            OutboxEvent.event_name == "TRIAL_REMINDER",
            OutboxEvent.payload["subscription_id"].as_string() == str(row.id),
            OutboxEvent.payload["stage"].as_string() == stage,
            or_(
                sent_for == trial_reminder_end(row.expires_at),
                and_(sent_for.is_(None), OutboxEvent.occurred_at >= row.expires_at - _STAGE_OPENS[stage]),
            ),
        )
        .first()
        is not None
    )


def queue_trial_reminders(db: Session, now: datetime | None = None) -> int:
    """Queue each trial's reminders once per end date: 7 days and 1 day before it ends, and when it has ended (caller
    commits). An extended trial gets them again for its new end date (FUN-04)."""
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
        # A trial whose data has been deleted (ended early, or purged) gets no more reminders: its people are gone.
        tenant = db.get(Tenant, row.tenant_id)
        if tenant is not None and str(tenant.status).upper() in ("ARCHIVED", "PURGING"):
            continue
        remaining = row.expires_at - now
        if remaining <= timedelta(0):
            stage = "ENDED" if -remaining <= timedelta(days=7) else None
        elif remaining <= timedelta(days=1):
            stage = "1_DAY"
        elif remaining <= timedelta(days=7):
            stage = "7_DAY"
        else:
            stage = None
        if stage is None or _trial_reminder_sent(db, row, stage):
            continue
        db.add(
            OutboxEvent(
                tenant_id=row.tenant_id,
                event_name="TRIAL_REMINDER",
                aggregate_type="SubscriptionLifecycle",
                aggregate_id=row.id,
                payload={
                    "subscription_id": str(row.id),
                    "stage": stage,
                    "expires_at": trial_reminder_end(row.expires_at),
                },
                occurred_at=now,
            )
        )
        queued += 1
    return queued
