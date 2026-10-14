"""The weekly readiness email: the quality loop, what changed since last week, and the weakest link.

Once a week (the first scheduler run of each ISO week from Monday 06:00 UTC), for every active organization, the
scheduler job ``readiness-digest`` reads the inspection checks (service.readiness) and queues one outbox event
(``READINESS_DIGEST``) holding the week, a snapshot of each check (state and number) and the email's content; the
outbox worker sends it to the organization's quality leads (Leader and Quality Reviewer roles) who have not switched it
off (``auth_users.email_preferences`` ``weekly_readiness: false``, under My Account). Addresses are never stored in the
queue: they are resolved when the email is sent. "What changed" compares with the organization's previous digest
event. Rules only; nothing is changed.
"""

from __future__ import annotations

import logging
import uuid
from datetime import date, datetime, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

logger = logging.getLogger("mdarix.readiness.digest")

EVENT = "READINESS_DIGEST"
PREFERENCE = "weekly_readiness"
SEND_FROM_HOUR = 6  # UTC, Monday
QUALITY_LEAD_ROLES = frozenset({"LEADER", "REVIEWER"})

# The loop in the order a complaint travels (frontend: features/workspace/qualityLoop.ts LOOP_ORDER).
LOOP = (
    ("COMPLAINTS_TO_RECHECK", "Hidden complaints found"),
    ("COMPLAINTS_PAST_TARGET", "Handled on time"),
    ("REPORTING_CLOCKS", "Reported in window"),
    ("HARM_CLOSED_WITHOUT_CASE", "Harm investigated"),
    ("TRIAGE_OVERDUE", "Signals triaged"),
    ("TRENDS_WITHOUT_ACTION", "Trends acted on"),
    ("CAPA_EFFECTIVENESS", "CAPAs proven"),
    ("RISK_FILE_INPUT", "Risk file fed"),
)
STATE_LABELS = {"CLEAR": "Clear", "ATTENTION": "Needs attention", "CRITICAL": "Critical", "NOT_SET": "Not set up"}
STATE_RANK = {"CRITICAL": 0, "NOT_SET": 1, "ATTENTION": 2, "CLEAR": 3}


def iso_week(day: date) -> str:
    year, week, _ = day.isocalendar()
    return f"{year}-W{week:02d}"


def due(now: datetime) -> bool:
    """Whether this week's digest may go: any time from Monday 06:00 UTC."""
    return not (now.weekday() == 0 and now.hour < SEND_FROM_HOUR)


def snapshot(readiness: dict) -> dict:
    """``{code: {"state", "value"}}`` of every check."""
    return {
        check["code"]: {"state": check.get("state"), "value": check.get("value")}
        for check in readiness.get("checks", [])
        if check.get("code")
    }


def _label(code: str, checks: dict) -> str:
    known = dict(LOOP)
    return known.get(code) or (checks.get(code) or {}).get("title") or code


def _value(value) -> str:
    return "unknown" if value is None else str(value)


def changes(previous: dict | None, current: dict, checks: dict) -> list[str]:
    """What changed since the previous digest, in loop order, one line each; empty when nothing did."""
    if not previous:
        return []
    order = [code for code, _ in LOOP] + sorted(code for code in current if code not in dict(LOOP))
    lines = []
    for code in order:
        now, before = current.get(code), previous.get(code)
        if now is None or before is None:
            continue
        label = _label(code, checks)
        if now.get("state") != before.get("state"):
            lines.append(
                f"{label}: {STATE_LABELS.get(before.get('state'), before.get('state'))} to "
                f"{STATE_LABELS.get(now.get('state'), now.get('state'))} ({_value(before.get('value'))} to "
                f"{_value(now.get('value'))})"
            )
        elif now.get("value") != before.get("value"):
            lines.append(f"{label}: {_value(before.get('value'))} to {_value(now.get('value'))}")
    return lines


def compose(readiness: dict, previous: dict | None) -> dict:
    """The email's content: the loop, the weakest link, what changed, the headline."""
    checks = {check["code"]: check for check in readiness.get("checks", []) if check.get("code")}
    order = [code for code, _ in LOOP if code in checks] + sorted(code for code in checks if code not in dict(LOOP))
    stations = [
        {
            "code": code,
            "label": _label(code, checks),
            "state": checks[code].get("state"),
            "value": checks[code].get("value"),
        }
        for code in order
    ]
    clear = sum(1 for station in stations if station["state"] == "CLEAR")
    open_stations = [station for station in stations if station["state"] != "CLEAR"]
    weakest = (
        sorted(open_stations, key=lambda station: (STATE_RANK.get(station["state"], 9), order.index(station["code"])))[
            0
        ]
        if open_stations
        else None
    )
    weakest_view = None
    if weakest:
        check = checks[weakest["code"]]
        weakest_view = {
            "code": weakest["code"],
            "label": weakest["label"],
            "state": weakest["state"],
            "value": weakest["value"],
            "detail": check.get("detail"),
            "why": check.get("why"),
        }
    return {
        "clear": clear,
        "total": len(stations),
        "stations": stations,
        "weakest": weakest_view,
        "changes": changes(previous, snapshot(readiness), checks),
        "first": previous is None,
    }


def _previous_snapshot(control_db: Session, tenant_id: uuid.UUID, week: str) -> dict | None:
    from backend.app.db.models.stage2 import OutboxEvent

    row = (
        control_db.query(OutboxEvent.payload)
        .filter(
            OutboxEvent.tenant_id == tenant_id,
            OutboxEvent.event_name == EVENT,
            OutboxEvent.payload["week"].as_string() < week,
        )
        .order_by(OutboxEvent.occurred_at.desc())
        .first()
    )
    payload = row[0] if row else None
    return payload.get("snapshot") if isinstance(payload, dict) else None


def _already_queued(control_db: Session, tenant_id: uuid.UUID, week: str) -> bool:
    from backend.app.db.models.stage2 import OutboxEvent

    return (
        control_db.query(OutboxEvent.id)
        .filter(
            OutboxEvent.tenant_id == tenant_id,
            OutboxEvent.event_name == EVENT,
            OutboxEvent.payload["week"].as_string() == week,
        )
        .first()
        is not None
    )


def queue_for_tenant(control_db: Session, data_db: Session, tenant_id: uuid.UUID, now: datetime) -> bool:
    """Queue this week's digest for one organization (control-plane session; the caller commits). False when it was
    already queued this week."""
    from backend.app.db.models.stage2 import OutboxEvent
    from backend.app.readiness_home.service import readiness

    week = iso_week(now.date())
    if _already_queued(control_db, tenant_id, week):
        return False
    found = readiness(data_db, tenant_id, now.date())
    content = compose(found, _previous_snapshot(control_db, tenant_id, week))
    control_db.add(
        OutboxEvent(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            event_name=EVENT,
            aggregate_type="Tenant",
            aggregate_id=tenant_id,
            payload={
                "tenant_id": str(tenant_id),
                "week": week,
                "as_of": found.get("as_of"),
                "snapshot": snapshot(found),
                "content": content,
            },
            occurred_at=now,
        )
    )
    control_db.flush()
    return True


def run_for_all_tenants(control_db: Session, now: datetime | None = None) -> dict:
    """The scheduler job: this week's digest for every active organization, each committed on its own. A failing
    organization is logged and reported; the others still run, and the job then fails so the scheduler alerts."""
    from backend.app.customer_lifecycle import customer_allows_access_clause
    from backend.app.db.data_plane import open_tenant_data_session
    from backend.app.db.models.customer_lifecycle import TenantDataPlane
    from backend.app.db.models.foundation import Tenant
    from backend.app.deployment_role import served_tenants_clause

    now = now or datetime.now(timezone.utc)
    week = iso_week(now.date())
    if not due(now):
        return {"week": week, "queued": 0, "skipped": "before Monday 06:00 UTC"}
    tenant_ids = [
        row.id
        for row in control_db.query(Tenant.id)
        .join(TenantDataPlane, TenantDataPlane.tenant_id == Tenant.id)
        .filter(
            Tenant.status.in_(["ACTIVE", "active"]),
            TenantDataPlane.status == "ACTIVE",
            customer_allows_access_clause(),
            served_tenants_clause(Tenant.id),
        )
        .order_by(Tenant.id)
        .all()
    ]
    queued, failed = 0, []
    for tenant_id in tenant_ids:
        try:
            with open_tenant_data_session(tenant_id) as data:
                made = queue_for_tenant(control_db, data, tenant_id, now)
            control_db.commit()
            queued += int(made)
        except Exception as exc:
            control_db.rollback()
            logger.exception("The weekly readiness digest failed for organization %s", tenant_id)
            failed.append({"tenant_id": str(tenant_id), "error": type(exc).__name__})
    if failed:
        raise RuntimeError(f"The weekly readiness digest failed for {len(failed)} organization(s): {failed}")
    return {"week": week, "organizations": len(tenant_ids), "queued": queued, "failed": failed}


# ------------------------------------------------------------------------------------------- delivery


def wants_digest(user) -> bool:
    preferences = user.email_preferences if isinstance(getattr(user, "email_preferences", None), dict) else {}
    return preferences.get(PREFERENCE) is not False


def recipients(control_db: Session, tenant_id: uuid.UUID) -> list[str]:
    """The organization's active quality leads (Leader or Quality Reviewer, by any of their roles) who have not switched
    the weekly readiness email off."""
    from backend.app.access.permissions import roles_of_user
    from backend.app.db.models.foundation import AuthUser
    from backend.app.role_codes import role_code

    users = (
        control_db.query(AuthUser)
        .filter(AuthUser.tenant_id == tenant_id, func.upper(AuthUser.status) == "ACTIVE")
        .all()
    )
    return sorted(
        {
            user.username
            for user in users
            if user.username
            and wants_digest(user)
            and any(role_code(role) in QUALITY_LEAD_ROLES for role in roles_of_user(control_db, user))
        }
    )


def deliver(control_db: Session, payload: dict) -> None:
    """Send one queued digest to the organization's quality leads (outbox worker)."""
    from auth import emailer
    from backend.app.notifications import _deliver, _organization

    tenant_id = uuid.UUID(str(payload["tenant_id"]))
    content = payload.get("content") or {}
    _deliver(
        lambda recipient, **details: emailer.send_readiness_digest(recipient, **details),
        recipients(control_db, tenant_id),
        organization=_organization(control_db, tenant_id),
        week=str(payload.get("week") or ""),
        content=content,
    )
