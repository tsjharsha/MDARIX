"""Reminders and escalation (T-G25) and the oversight view's items (T-G9), read from the records that carry a date.

``due_items`` reads every dated item of the organization from its own record, never a copy:

- **Triage:** each open triage item's target (24 clock hours from availability in MDARIX, or the reopening), with
  its triage owner and backup; for an urgent intake not yet a complaint, its earliest provisional reporting deadline;
- **Reporting deadlines:** a market assessment that says reportable or pending, with its deadline, whose report is
  not started; the reportability decision tasks;
- **Report obligations:** each obligation not yet met, with the deadline it was given;
- **Communications:** each open request's reply due date (its owner's task);
- **Approvals:** a report snapshot or guide version waiting for its second person: the approver's task (workflow/
  approvals.py), due at the end of the next working day (a report's sooner deadline first); a guide version asked
  before 0.10.64, without a task, from the version itself;
- **CAPA:** the effectiveness check tasks, and the CAPAs imported from the QMS with a due date (on the view only:
  the QMS owns them, so they raise no alert);
- every other open My Work task with a due date.

``sweep`` turns the items that are due soon or overdue into alerts for the people their chain names (rules.py): new
ones are raised, ones whose item is done or no longer due are resolved, read state is kept. Escalations are audited.
The scheduler sweeps every organization every 15 minutes, and a person opening their reminders or the oversight view
sweeps their organization when the last sweep is older than five minutes. Nothing here changes the item itself.
"""

from __future__ import annotations

from backend.app.trial.sample_source import is_sample
from backend.app import links
import logging
import uuid
from datetime import date, datetime, timedelta, timezone

from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.app.db.models.oversight import DueAlert, OversightSettings, UserAbsence
from backend.app.oversight import rules
from backend.app.standards import version_words

logger = logging.getLogger("mdarix.oversight")
ACTOR = "system:reminders"
SWEEP_EVERY = timedelta(minutes=5)
READ_LIMIT = 2000
TASK_CATEGORIES = {
    "EXTERNAL_REPLY_DUE": "COMMUNICATION",
    "EFFECTIVENESS_CHECK": "CAPA",
    "REPORTABILITY_DECISION": "REPORTING",
    "FIRST_CONTACT_FOLLOW_UP": "TRIAGE",
    "QMS_COMPLAINT": "TRIAGE",
    "SERVICE_ONLY_REVIEW": "TRIAGE",
    "SIGNAL_TRIAGE": "TRIAGE",
}
CLOSED_CAPA = ("closed", "cancelled", "canceled", "completed", "done", "verified")


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value) -> str | None:
    return value.isoformat() if value is not None else None


# --------------------------------------------------------------------------------------------- settings and absences


def settings_row(db: Session, tenant_id) -> OversightSettings | None:
    return db.query(OversightSettings).filter(OversightSettings.tenant_id == tenant_id).one_or_none()


def settings_view(row: OversightSettings | None) -> dict:
    if row is None:
        return {
            "time_zone": rules.DEFAULT_ZONE,
            "work_days": list(rules.DEFAULT_DAYS),
            "holidays": [],
            "reminder_hours": rules.DEFAULT_HOURS,
            "escalation_role": rules.DEFAULT_ROLE,
            "urgent_email": False,
            "attachment_quota_mb": 100,
            "updated_at": None,
        }
    return {
        "time_zone": rules.canonical_zone(row.time_zone),
        "work_days": list(row.work_days or []),
        "holidays": list(row.holidays or []),
        "reminder_hours": row.reminder_hours,
        "escalation_role": row.escalation_role,
        # B7: the opt-in urgent e-mail alert and the organization's attachment storage (B7-D12, D16).
        "urgent_email": bool(row.urgent_email),
        "attachment_quota_mb": row.attachment_quota_mb or 100,
        "updated_at": _iso(row.updated_at) if row.updated_by else None,
    }


def calendar_from(view: dict) -> rules.Calendar:
    holidays = set()
    for item in view["holidays"]:
        try:
            holidays.add(date.fromisoformat(item["date"]))
        except (KeyError, TypeError, ValueError):
            continue
    return rules.Calendar(view["time_zone"], tuple(view["work_days"]) or rules.DEFAULT_DAYS, frozenset(holidays))


def calendar_of(db: Session, tenant_id) -> rules.Calendar:
    """The organization's working calendar; the default one when it cannot be read (an older database)."""
    try:
        with db.begin_nested():
            row = settings_row(db, tenant_id)
    except Exception:
        logger.warning("The working calendar of %s could not be read; the default applies", tenant_id, exc_info=True)
        return rules.Calendar()
    return calendar_from(settings_view(row))


def absences(db: Session, tenant_id, today: date | None = None) -> list[dict]:
    """Absences not cancelled that have not ended (``today`` given), soonest first."""
    query = db.query(UserAbsence).filter(UserAbsence.tenant_id == tenant_id, UserAbsence.cancelled_at.is_(None))
    if today is not None:
        query = query.filter(UserAbsence.ends_on >= today)
    return [
        {
            "id": str(row.id),
            "user_id": row.user_id,
            "backup_id": row.backup_id,
            "starts_on": row.starts_on,
            "ends_on": row.ends_on,
            "note": row.note,
            "sample": is_sample(row.source_system),
        }
        for row in query.order_by(UserAbsence.starts_on).limit(READ_LIMIT)
    ]


def people(control_db: Session | None, tenant_id) -> list[dict]:
    """The organization's people who can sign in (never an administrator account or MDARIX staff), with their
    roles: the owners, backups and escalation recipients alerts may go to."""
    from backend.app.db.models.foundation import AuthUser
    from backend.app.role_codes import is_administrator_role, role_code
    from backend.app.workflow.people import display_name, roles_of

    if control_db is None:
        return []
    found = []
    for user in (
        control_db.query(AuthUser)
        .filter(AuthUser.tenant_id == tenant_id, AuthUser.status == "ACTIVE")
        .order_by(AuthUser.display_name)
        .limit(500)
    ):
        if is_administrator_role(user.role):
            continue
        found.append(
            {
                "id": str(user.id),
                "name": display_name(user),
                "roles": [role_code(role) for role in roles_of(control_db, user)],
            }
        )
    return found


# --------------------------------------------------------------------------------------------- the dated items


def _item(
    key,
    category,
    title,
    due_at,
    *,
    ref=None,
    complaint_id=None,
    owner_id=None,
    backup_id=None,
    queue=None,
    market=None,
    product=None,
    opens=None,
    alerts=True,
) -> dict:
    return {
        "key": key,
        "category": category,
        "title": title[:400],
        "ref": ref,
        "complaint_id": str(complaint_id) if complaint_id else None,
        "owner_id": str(owner_id) if owner_id else None,
        "backup_id": str(backup_id) if backup_id else None,
        "queue": queue,
        "market": market,
        "product": product,
        "due_at": due_at,
        "opens": opens or links.target("My Work"),
        "alerts": alerts,
    }


def _legal_end(day: date, market: str | None, zone: str) -> datetime:
    """The end of a legal deadline's day by its market's counting rule (reportability/deadlines.py), as every other
    screen shows it."""
    from backend.app.reportability.deadlines import end_of

    return end_of(day, market, zone).at


def _task_items(db: Session, tenant_id) -> list[dict]:
    from backend.app.communications.service import TASK_TYPE as REPLY_TASK
    from backend.app.db.models.workflow import OPEN_TASK_STATUSES, WorkflowTask
    from backend.app.workflow.labels import role_label

    found = []
    for task in (
        db.query(WorkflowTask)
        .filter(
            WorkflowTask.tenant_id == tenant_id,
            WorkflowTask.status.in_(list(OPEN_TASK_STATUSES)),
            WorkflowTask.due_at.isnot(None),
        )
        .order_by(WorkflowTask.due_at)
        .limit(READ_LIMIT)
    ):
        details = task.details or {}
        complaint_id = details.get("complaint_id") or (
            task.source_entity_id if task.source_entity_type == "Complaint" else None
        )
        # An approval task (workflow/approvals.py) names its own category and the screen it opens.
        opens = details.get("opens") or links.target("My Work")
        # A reply due opens its request in the log, a step sent from a complaint's page opens that complaint
        # (0.10.68: one click from the reminder to the record, not to a list).
        if task.task_type == REPLY_TASK and task.source_entity_type == "CommunicationEntry":
            opens = links.target("Complaints", "Communications", record=("communication", task.source_entity_id))
        elif task.task_type == REPLY_TASK and complaint_id:
            opens = links.target("Complaints", "Communications", record=("complaint", complaint_id))
        elif task.task_type == "COMPLAINT_STEP" and complaint_id:
            opens = links.target(record=("complaint", complaint_id))
        found.append(
            _item(
                f"task:{task.id}",
                details.get("category") or TASK_CATEGORIES.get(task.task_type, "TASK"),
                task.title,
                task.due_at,
                ref=details.get("complaint_business_id") or details.get("reference") or task.business_id,
                complaint_id=complaint_id,
                owner_id=task.assigned_user_id,
                queue=None if task.assigned_user_id else role_label(task.assigned_role),
                opens=opens,
            )
        )
    return found


def _triage_items(db: Session, control_db, tenant_id, now: datetime) -> list[dict]:
    from backend.app.intake import service as intake

    found = []
    for item in intake.triage(db, control_db, tenant_id, "open", now)["items"]:
        # shortcut: the sample's SAMPLE-CASE-11 is SAMPLE-RV-11's own call (Getting started, B2 step 7): while the two
        # are apart, RV-11's triage item already alerts for the event, so day 0 stays calm; once attached they are one
        # item and it alerts. Drop this if the sample ever links the two at seeding.
        if item.get("sample") and item["ref"] == "SAMPLE-CASE-11" and not item.get("linked"):
            continue
        if item.get("backlog"):  # OD-12 + 3a: Imported backlog work, in its own view, raises no alert
            continue
        record = item.get("record") or {}
        owner = record.get("triage_owner") or record.get("event_owner")
        complaint_id = item["id"] if item["kind"] == intake.COMPLAINT else None
        common = {
            "ref": item["ref"],
            "complaint_id": complaint_id,
            "owner_id": owner,
            "backup_id": record.get("backup_owner"),
            "queue": None if owner else "Triage",
            "product": item.get("product_name"),
            # A call that is not a complaint yet opens its own triage card by its reference (0.10.82, navigation
            # M5), as the triage screen reads ref=; it opened the bare list before.
            "opens": links.target("Complaints", "Triage", record=("complaint", complaint_id))
            if complaint_id
            else links.target("Complaints", "Triage", record=("intake", item["id"]))
            if item["kind"] == intake.INTAKE
            else links.target("Complaints", "Triage"),
        }
        found.append(
            _item(
                f"triage:{item['key']}",
                "TRIAGE",
                f"Triage not done yet ({item['tier_label'].lower()})",
                datetime.fromisoformat(item["triage_clock"]["due_at"]),
                **common,
            )
        )
        # A1 (B2): a fast-track item waits for a named owner's acknowledgement; overdue, the sweep escalates it to the
        # backup and the escalation role (the next authorised role).
        ack = item.get("acknowledgement") or {}
        # shortcut: the sample's fast items (the story's triage steps) raise no acknowledgement alert, so day 0 stays
        # calm (0.10.64); revisit with Getting started Part 1 (B2 step 7).
        if ack.get("required") and not ack.get("done") and not item.get("sample"):
            found.append(
                _item(
                    f"ack:{item['key']}",
                    "TRIAGE",
                    f"Acknowledge the fast-track triage of {item['ref']}",
                    datetime.fromisoformat(ack["due_at"]),
                    **common,
                )
            )
        # T-D7 (B2): an automatic reopening is due at once, so the next sweep tells the owners, the backup and the
        # escalation role (one alert per reopening: the key carries its moment).
        if record.get("reopened_at") and record.get("reopen_trigger") and not item.get("sample"):
            why = record["reopen_trigger"].replace("_", " ").lower()
            found.append(
                _item(
                    f"reopened:{item['key']}:{record['reopened_at']}",
                    "TRIAGE",
                    f"Triage of {item['ref']} reopened on the fast track ({why})",
                    datetime.fromisoformat(record["reopened_at"]),
                    **common,
                )
            )
        # An urgent intake is not a complaint yet: its provisional deadline is on no other list.
        if item["kind"] == intake.INTAKE and item["deadlines"] and item["deadlines"][0]["due_at"]:
            first = item["deadlines"][0]
            found.append(
                _item(
                    f"provisional:{item['key']}:{first['market']}",
                    "REPORTING",
                    f"Provisional {first['label']} deadline for {item['ref']} ({first.get('earliest_note') or first['basis']})",
                    datetime.fromisoformat(first["due_at"]),
                    market=first["market"],
                    **common,
                )
            )
    return found


def _watch_items(db: Session, control_db, tenant_id, now: datetime) -> list[dict]:
    """The reportability watch's provisional clock of a market not assessed yet (SAMPLE-RV-06: FDA), so Oversight
    says what Reporting and the complaint page say (stage 8; it listed a market's clock only once its assessment was
    started)."""
    from backend.app.reportability import markets
    from backend.app.reportability import service as reportability

    from backend.app.reportability import facts

    found = []
    for item in reportability.watch(db, control_db, tenant_id, show="open", page_size=10_000, today=now)["items"]:
        binding = item.get("binding")
        needs = item.get("needs") or []
        if not binding or not binding.get("due_at"):
            continue
        # OD-12 + 3a: Imported backlog work raises no market clock; a missing fact is still asked for (its backlog target).
        if binding.get("backlog") and not needs:
            continue
        market = binding.get("market")
        found.append(
            _item(
                # A complaint that needs a fact is one line, kept beside its markets' own (0.10.81, F3, F4).
                f"watch:{item['id']}:{'facts' if needs else market}",
                "REPORTING",
                f"Enter {facts.labels(needs)}: needed for the reporting clocks (provisional deadline)"
                if needs
                else f"{markets.MARKET_LABELS.get(market, market)}: not assessed yet, provisional deadline",
                datetime.fromisoformat(binding["due_at"]),
                complaint_id=item["id"],
                market=None if needs else market,
                opens=links.target("Complaints", "Reportability", record=("complaint", item["id"])),
            )
        )
    return found


def _report_items(db: Session, tenant_id, zone: str) -> list[dict]:
    from backend.app.authority_reports import forms
    from backend.app.authority_reports import rules as report_rules
    from backend.app.authority_reports.router import _candidates
    from backend.app.db.models.authority_reports import ReportObligation
    from backend.app.reportability import markets

    found = []
    # Not capped (0.10.86): an unordered cap could drop an overdue report, or an initial report that was started (its
    # assessment then read "the report is not started"). Only the open ones and the initial reports are read.
    obligations = (
        db.query(ReportObligation)
        .filter(
            ReportObligation.tenant_id == tenant_id,
            (ReportObligation.kind == "INITIAL")
            | (ReportObligation.due_on.isnot(None) & ReportObligation.state.notin_(list(report_rules.CLOSED))),
        )
        .all()
    )
    started = {(row.complaint_id, row.market) for row in obligations if row.kind == "INITIAL"}
    for row in obligations:
        if row.due_on is None or row.state in report_rules.CLOSED:
            continue
        form = forms.FORMS.get(row.form_code)
        found.append(
            _item(
                f"obligation:{row.id}",
                "OBLIGATION",
                f"{form.title if form else 'Report'}: {report_rules.STATE_LABELS.get(row.state, row.state).lower()}",
                _legal_end(row.due_on, row.market, zone),
                complaint_id=row.complaint_id,
                owner_id=row.created_by,
                market=row.market,
                # The report itself (0.10.76): its page on the new navigation, its panel on the classic one.
                opens=links.target("Complaints", "Reports", record=("report", row.id)),
            )
        )
    for row in _candidates(db, tenant_id):
        if row.due_on is None or row.filed_on or (row.complaint_id, row.market) in started:
            continue
        label = markets.MARKET_LABELS.get(row.market, row.market)
        pending = row.conclusion is None
        found.append(
            _item(
                f"assessment:{row.complaint_id}:{row.market}",
                "REPORTING",
                f"{label}: market assessment not signed, provisional deadline"
                if pending
                else f"{label}: reportable, the report is not started",
                _legal_end(row.due_on, row.market, zone),
                complaint_id=row.complaint_id,
                owner_id=row.signed_by or row.created_by,
                market=row.market,
                opens=links.target("Complaints", "Reportability", record=("complaint", row.complaint_id))
                if pending
                else links.target("Complaints", "Reports", record=("complaint", row.complaint_id)),
            )
        )
    return found


def _guide_items(db: Session, tenant_id, calendar: rules.Calendar) -> list[dict]:
    """A guide version waiting for approval with no approver's task (one asked before 0.10.64): the task stands for
    it otherwise, so it shows once."""
    from backend.app.db.models.guides_communications import DecisionGuideVersion
    from backend.app.db.models.workflow import OPEN_TASK_STATUSES, WorkflowTask

    asked = {
        row.source_entity_id
        for row in db.query(WorkflowTask.source_entity_id).filter(
            WorkflowTask.tenant_id == tenant_id,
            WorkflowTask.source_entity_type == "DecisionGuideVersion",
            WorkflowTask.status.in_(list(OPEN_TASK_STATUSES)),
        )
    }
    return [
        _item(
            f"guide:{row.id}",
            "GUIDE",
            f"Approve the decision guide ({version_words(row.code)}): a second person approves it",
            calendar.working_day_end(row.requested_at or row.updated_at, 1),
            ref=row.code,
            queue="Approvers",
            opens=links.target("Complaints", "Decision guides"),
        )
        for row in db.query(DecisionGuideVersion).filter(
            DecisionGuideVersion.tenant_id == tenant_id, DecisionGuideVersion.state == "AWAITING_APPROVAL"
        )
        if row.id not in asked
    ]


def _capa_items(db: Session, tenant_id) -> list[dict]:
    from backend.app.db.models.foundation import Capa, Product
    from backend.app.decision_followups.rules import capa_qms_words

    names = {row.id: row.name for row in db.query(Product.id, Product.name).filter(Product.tenant_id == tenant_id)}
    return [
        _item(
            f"capa:{row.id}",
            "CAPA",
            f"CAPA {row.business_id or row.capa_identifier}: {row.title} ({capa_qms_words(row) or 'in your QMS'})",
            row.due_at,
            ref=row.business_id or row.capa_identifier,
            queue="Your QMS",
            product=names.get(row.product_id),
            opens=links.target("Records", "Effectiveness checks", record=("capa", row.id)),
            alerts=False,
        )
        # The closed ones are left out in the query, not after a cap (0.10.86): every open dated CAPA is listed.
        for row in db.query(Capa).filter(
            Capa.tenant_id == tenant_id,
            Capa.due_at.isnot(None),
            func.lower(func.coalesce(Capa.status, "")).notin_(CLOSED_CAPA),
        )
    ]


def _with_complaints(db: Session, tenant_id, items: list[dict]) -> None:
    """Each item about a complaint gets its reference, product and (where it has none) its market."""
    from backend.app.db.models.foundation import Complaint, Product
    from backend.app.reportability import markets

    ids = {uuid.UUID(item["complaint_id"]) for item in items if item["complaint_id"]}
    if not ids:
        return
    complaints = {
        str(row.id): row
        for row in db.query(
            Complaint.id, Complaint.business_id, Complaint.complaint_identifier, Complaint.product_id, Complaint.country
        ).filter(Complaint.tenant_id == tenant_id, Complaint.id.in_(list(ids)))
    }
    names = {row.id: row.name for row in db.query(Product.id, Product.name).filter(Product.tenant_id == tenant_id)}
    for item in items:
        row = complaints.get(item["complaint_id"] or "")
        if row is None:
            continue
        item["ref"] = row.complaint_identifier
        item["product"] = item["product"] or names.get(row.product_id)
        # A complaint that needs a fact runs no market's real clock yet (0.10.81, ":facts"): it names none.
        if not item["key"].endswith(":facts"):
            item["market"] = item["market"] or markets.market_of(row.country)


def due_items(db: Session, control_db: Session | None, tenant_id, now: datetime | None = None) -> list[dict]:
    """Every dated item of the organization (see the module docstring), soonest first. A source that cannot be read
    (an older database) is left out and logged; the others still show."""
    now = now or now_utc()
    calendar = calendar_of(db, tenant_id)
    sources = (
        ("tasks", lambda: _task_items(db, tenant_id)),
        ("triage", lambda: _triage_items(db, control_db, tenant_id, now)),
        ("reports", lambda: _report_items(db, tenant_id, calendar.zone)),
        ("watch", lambda: _watch_items(db, control_db, tenant_id, now)),
        ("guides", lambda: _guide_items(db, tenant_id, calendar)),
        ("capas", lambda: _capa_items(db, tenant_id)),
    )
    items: list[dict] = []
    for name, read in sources:
        try:
            with db.begin_nested():
                items += read()
        except Exception:
            logger.exception("The %s of %s could not be read for the oversight view", name, tenant_id)
    for item in items:
        if item["due_at"].tzinfo is None:
            item["due_at"] = item["due_at"].replace(tzinfo=timezone.utc)
    # A reporting reminder task stands for a complaint's reporting clock, which a report or market item already shows:
    # one line per complaint (J31; RV-07, RV-08 and RV-10 showed twice).
    reported = {item["complaint_id"] for item in items if item["key"].startswith(("obligation:", "assessment:"))}
    items = [
        item
        for item in items
        if not (
            item["key"].startswith("task:") and item["category"] == "REPORTING" and item["complaint_id"] in reported
        )
    ]
    # The watch's provisional clock stands only for a market no assessment or report of the complaint dates yet.
    dated = {
        (item["complaint_id"], item["market"])
        for item in items
        if item["key"].startswith(("obligation:", "assessment:"))
    }
    items = [
        item
        for item in items
        if not (item["key"].startswith("watch:") and (item["complaint_id"], item["market"]) in dated)
    ]
    _with_complaints(db, tenant_id, items)
    items.sort(key=lambda item: (item["due_at"], item["key"]))
    return items


# --------------------------------------------------------------------------------------------- the sweep


def escalation_people(everyone: list[dict], role: str) -> list[str]:
    from backend.app.role_codes import role_code

    wanted = role_code(role)
    return [person["id"] for person in everyone if wanted in person["roles"]]


def _trial_owner(control_db: Session | None, tenant_id) -> str | None:
    """The id of the person who started the trial, or None (not a trial, or no control plane at hand)."""
    if control_db is None:
        return None
    from backend.app.db.models.foundation import AuthUser
    from backend.app.trial.team import trial_request

    request = trial_request(control_db, tenant_id)
    if request is None:
        return None
    found = (
        control_db.query(AuthUser.id)
        .filter(AuthUser.tenant_id == tenant_id, AuthUser.username == request.email.strip().lower())
        .scalar()
    )
    return str(found) if found else None


DELIVERED, FAILED, RETRYING = "DELIVERED", "FAILED", "RETRYING"
# shortcut: a fixed number of delivery attempts per alert; a setting when out-of-app channels arrive (B7).
MAX_ATTEMPTS = 5


def deliver(alert: DueAlert, now: datetime) -> None:
    """Deliver one alert on its channel. In-app the alert row is the message, so it cannot fail here; the opt-in
    e-mail and SMS channels (B7) raise on failure."""


def attempt(db: Session, tenant_id, alert: DueAlert, now: datetime, first: bool = False) -> None:
    """A2: one delivery attempt, recorded on the alert (channel, attempts, time, result). A failure is kept and shown,
    is audited, and never resolves or cancels the alert or its escalation."""
    from backend.app.enterprise_audit import make_audit_event

    alert.channel = alert.channel or "IN_APP"
    alert.attempts = 1 if first else (alert.attempts or 1) + 1
    alert.last_attempt_at = now
    try:
        deliver(alert, now)
    except Exception as exc:  # any channel failure: keep the alert, show the failure, retry on the next sweep
        alert.delivery = FAILED if alert.attempts >= MAX_ATTEMPTS else RETRYING
        alert.delivery_error = f"{type(exc).__name__}: {exc}"[:500]
        db.add(
            make_audit_event(
                tenant_id=tenant_id,
                actor_ref=ACTOR,
                action="ALERT_DELIVERY_FAILED",
                entity_type="DueAlert",
                entity_id=alert.id,
                details={
                    "item": alert.item_key,
                    "recipient": alert.recipient_id,
                    "channel": alert.channel,
                    "attempt": alert.attempts,
                    "error": alert.delivery_error,
                },
                created_at=now,
            )
        )
        return
    alert.delivery, alert.delivery_error = DELIVERED, None


def sweep(db: Session, control_db: Session | None, tenant_id, now: datetime | None = None) -> dict:
    """Raise and resolve the organization's alerts (see the module docstring). Flushes; the caller commits."""
    from backend.app.enterprise_audit import make_audit_event

    now = now or now_utc()
    row = settings_row(db, tenant_id)
    view = settings_view(row)
    calendar = calendar_from(view)
    today = calendar.local_day(now)
    everyone = people(control_db, tenant_id)
    active = {person["id"] for person in everyone}
    escalating = escalation_people(everyone, view["escalation_role"])
    # The sample story's escalations go to the person who started the trial, not to every Leader: an invited colleague
    # does not inherit them (J2).
    owner = _trial_owner(control_db, tenant_id)
    away = absences(db, tenant_id, today)
    wanted: dict[tuple, tuple[dict, str]] = {}
    for item in due_items(db, control_db, tenant_id, now):
        if not item["alerts"]:
            continue
        state = rules.state_of(item["due_at"], now, view["reminder_hours"])
        # shortcut: the sample's records are known by their SAMPLE- references; a source_system per item if that changes.
        sample = owner is not None and (item["ref"] or "").startswith("SAMPLE-")
        for tier, person, reason in rules.recipients(
            item, state, active, away, [owner] if sample else escalating, today
        ):
            wanted[(item["key"], tier, person)] = (item, reason)
    existing = {
        (alert.item_key, alert.tier, alert.recipient_id): alert
        for alert in db.query(DueAlert).filter(DueAlert.tenant_id == tenant_id).limit(10 * READ_LIMIT)
    }
    raised = resolved = 0
    for key, (item, reason) in wanted.items():
        alert = existing.get(key)
        fields = {
            "reason": reason,
            "category": item["category"],
            "title": item["title"],
            "ref": (item["ref"] or "")[:120] or None,
            "complaint_id": uuid.UUID(item["complaint_id"]) if item["complaint_id"] else None,
            "owner_id": item["owner_id"],
            "due_at": item["due_at"],
            "opens": item["opens"],
        }
        if alert is None:
            alert = DueAlert(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                item_key=key[0],
                tier=key[1],
                recipient_id=key[2],
                raised_at=now,
                **fields,
            )
            try:
                with db.begin_nested():
                    db.add(alert)
                    db.flush()
            except IntegrityError:  # a sweep running at the same moment raised it
                continue
        elif alert.resolved_at is not None:
            for name, value in fields.items():
                setattr(alert, name, value)
            alert.raised_at, alert.resolved_at, alert.read_at = now, None, None
        else:
            for name, value in fields.items():
                setattr(alert, name, value)
            # A2: a failed delivery is retried on the next sweep, on the same alert (never a second one).
            if alert.delivery != DELIVERED and (alert.attempts or 1) < MAX_ATTEMPTS:
                attempt(db, tenant_id, alert, now)
            continue
        attempt(db, tenant_id, alert, now, first=True)
        raised += 1
        if alert.tier == rules.ESCALATION:
            db.add(
                make_audit_event(
                    tenant_id=tenant_id,
                    actor_ref=ACTOR,
                    action="DUE_ITEM_ESCALATED",
                    entity_type="DueAlert",
                    entity_id=alert.id,
                    details={"item": key[0], "recipient": key[2], "reason": reason, "due_at": _iso(item["due_at"])},
                    created_at=now,
                )
            )
    for key, alert in existing.items():
        if key not in wanted and alert.resolved_at is None:
            alert.resolved_at = now
            resolved += 1
    if row is None:
        row = OversightSettings(id=uuid.uuid4(), tenant_id=tenant_id, updated_at=now)
        db.add(row)
    row.swept_at = now
    from backend.app.oversight import urgent_alert

    urgent_alert.remind_overdue(db, control_db, tenant_id, now)  # B7 (UA-04): one reminder e-mail, when opted in
    db.flush()
    return {"raised": raised, "resolved": resolved}


def sweep_if_stale(db: Session, control_db: Session | None, tenant_id, now: datetime | None = None) -> None:
    """Sweep when the last sweep is older than ``SWEEP_EVERY`` (opening a list brings it up to date); commits. A
    failing sweep is logged and the list shows the alerts as they were."""
    now = now or now_utc()
    row = settings_row(db, tenant_id)
    if row is not None and row.swept_at is not None and now - row.swept_at < SWEEP_EVERY:
        return
    try:
        sweep(db, control_db, tenant_id, now)
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("The reminders of %s could not be brought up to date", tenant_id)


def run_for_all_tenants(control_db: Session) -> dict:
    """The scheduler job: the sweep for every active organization, on the shared plane or its own database, each
    committed on its own; a failing organization is logged and the job then fails so the scheduler alerts."""
    from backend.app.reportability.reminders import active_tenant_ids
    from backend.app.db.data_plane import open_tenant_data_session
    from backend.app.intake import service as intake
    from backend.app.intake.service import now_utc

    totals = {"tenants": 0, "raised": 0, "resolved": 0}
    failed = []
    for tenant_id in active_tenant_ids(control_db):
        try:
            with open_tenant_data_session(tenant_id) as data:
                try:
                    done = sweep(data, control_db, tenant_id)
                    # OD-1 (B2): contacts past their retention are erased on the same 15-minute pass.
                    totals["contacts_erased"] = totals.get("contacts_erased", 0) + intake.erase_expired_contacts(
                        data, tenant_id, now_utc()
                    )
                    data.commit()
                except Exception:
                    data.rollback()
                    raise
        except Exception as exc:
            logger.exception("The reminders failed for organization %s", tenant_id)
            failed.append({"tenant_id": str(tenant_id), "error": type(exc).__name__})
            continue
        totals["tenants"] += 1
        totals["raised"] += done["raised"]
        totals["resolved"] += done["resolved"]
    if failed:
        raise RuntimeError(f"Reminders failed for {len(failed)} organization(s): {failed}")
    return {**totals, "failed": failed}
