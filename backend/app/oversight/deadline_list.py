"""The daily deadline list (B6a G18a): an offline copy of the organization's open reporting deadlines, so legal clocks
survive an outage of MDARIX.

- **What it lists:** every open reporting item, from Oversight's own reads (``service.due_items``, categories
  ``REPORTING`` and ``OBLIGATION``: a market's clock being assessed, a report owed and not yet submitted, the watch's
  provisional clock), plus a country outside the five markets (B9b) whose conclusion is not signed yet or whose
  report has no date in Oversight. Overdue first, then soonest. Per line: complaint reference, market, what is owed,
  due time with its zone, state, owner. Never patient, reporter or description text.
- **The e-mail:** the scheduler job ``deadline-list`` queues one outbox event ``DEADLINE_LIST`` per organization and
  local day, from 06:00 in the organization's time zone (the oversight calendar), every day including weekends; an
  empty list is still sent, so silence means a problem, not "nothing due" (B6a-D1). The queue holds references, dates
  and owner ids only: names and addresses are resolved when the e-mail is sent.
- **Who gets it:** active regulatory approvers, Leaders and customer administrators who have not switched it off
  (``email_preferences`` ``daily_deadlines: false``); the last recipient left on cannot switch it off.
- **The download:** CSV and PDF on Oversight (``data.export``), audited.

Switch ``MDARIX_B6_DEADLINE_LIST`` (on): off, nothing is queued and the downloads answer 404.
"""

from __future__ import annotations

import io
import logging
import uuid
from datetime import datetime, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.app import feature_set
from backend.app.oversight import rules, service

logger = logging.getLogger("mdarix.oversight.deadline_list")

SWITCH = "MDARIX_B6_DEADLINE_LIST"
EVENT = "DEADLINE_LIST"
PREFERENCE = "daily_deadlines"
SEND_FROM_HOUR = 6  # organization time, every day
PDF_LINES_PER_PAGE = 40
CATEGORIES = ("REPORTING", "OBLIGATION")
NO_DATE = "NO_DATE"
STATE_LABELS = {**rules.STATE_LABELS, NO_DATE: "No due date entered"}
OUTAGE_NOTE = "Printed copy for an outage: check MDARIX when it is back."
CSV_FIELDS = ("ref", "market", "owed", "due_at", "due_label", "state", "owner")


def switched_on() -> bool:
    return feature_set.switched_on(SWITCH)


def _market_label(market: str | None, country: str | None) -> str:
    from backend.app.reportability import markets, other_countries

    if market == other_countries.OTHER:
        return other_countries.label(country) if country else "Other country"
    return markets.MARKET_LABELS.get(market, market or "Market not known yet")


def _other_lines(db: Session, tenant_id, now: datetime, zone: str, listed: set[str]) -> list[dict]:
    """B9b: a country outside the five markets, not signed yet or with a report Oversight has no date for."""
    from backend.app.db.models.foundation import Complaint
    from backend.app.db.models.market_assessment import ComplaintMarketAssessment
    from backend.app.reportability import other_countries
    from backend.app.reportability.deadlines import end_of

    ids = [
        row[0]
        for row in db.query(ComplaintMarketAssessment.complaint_id)
        .filter(
            ComplaintMarketAssessment.tenant_id == tenant_id,
            ComplaintMarketAssessment.market == other_countries.OTHER,
        )
        .distinct()
    ]
    found = other_countries.open_lines(db, tenant_id, ids, now.date())
    if not found:
        return []
    refs = {
        row.id: row.complaint_identifier
        for row in db.query(Complaint.id, Complaint.complaint_identifier).filter(
            Complaint.tenant_id == tenant_id, Complaint.id.in_(list(found))
        )
    }
    lines = []
    for complaint_id, entries in found.items():
        for entry in entries:
            if entry["report_id"] and f"obligation:{entry['report_id']}" in listed:
                continue  # Oversight already dates this report
            due_at = (
                end_of(datetime.fromisoformat(entry["due_on"]).date(), other_countries.OTHER, zone).at
                if entry["due_on"]
                else None
            )
            lines.append(
                {
                    "key": f"other:{complaint_id}:{entry['country']}",
                    "complaint_id": str(complaint_id),
                    "ref": refs.get(complaint_id),
                    "market": other_countries.OTHER,
                    "country": entry["country"],
                    "owed": f"{entry['label']}: {entry['state_label']}",
                    "due_at": due_at,
                    "owner_id": None,
                }
            )
    return lines


def lines(db: Session, control_db: Session | None, tenant_id, now: datetime | None = None) -> dict:
    """``{"as_of", "zone", "day", "lines"}``: the open reporting deadlines, overdue first then soonest (no date last).
    Each line holds ids, references, dates and states only."""
    from backend.app.db.models.authority_reports import ReportObligation
    from backend.app.reportability.deadlines import due_label

    now = now or service.now_utc()
    view = service.settings_view(service.settings_row(db, tenant_id))
    calendar = service.calendar_from(view)
    items = [item for item in service.due_items(db, control_db, tenant_id, now) if item["category"] in CATEGORIES]
    obligation_ids = [
        uuid.UUID(item["key"].split(":", 1)[1]) for item in items if item["key"].startswith("obligation:")
    ]
    countries = (
        {
            str(row.id): row.country
            for row in db.query(ReportObligation.id, ReportObligation.country).filter(
                ReportObligation.tenant_id == tenant_id, ReportObligation.id.in_(obligation_ids)
            )
        }
        if obligation_ids
        else {}
    )
    found = [
        {
            "key": item["key"],
            "complaint_id": item["complaint_id"],
            "ref": item["ref"],
            "market": item["market"],
            "country": countries.get(item["key"].split(":", 1)[1]) if item["key"].startswith("obligation:") else None,
            "owed": item["title"],
            "due_at": item["due_at"],
            "owner_id": item["owner_id"],
        }
        for item in items
    ]
    try:
        with db.begin_nested():
            found += _other_lines(db, tenant_id, now, calendar.zone, {item["key"] for item in items})
    except Exception:
        logger.exception("The other-country deadlines of %s could not be read for the deadline list", tenant_id)
    out = []
    for item in found:
        due_at = item["due_at"]
        state = rules.state_of(due_at, now, view["reminder_hours"]) if due_at else NO_DATE
        out.append(
            {
                "key": item["key"],
                "complaint_id": item["complaint_id"],
                "ref": item["ref"] or "",
                "market": _market_label(item["market"], item["country"]),
                "owed": item["owed"],
                "due_at": due_at.isoformat() if due_at else None,
                "due_label": due_label(due_at, item["market"], calendar.zone) if due_at else "Due date not entered",
                "state": state,
                "state_label": STATE_LABELS[state],
                "owner_id": item["owner_id"],
            }
        )
    # Overdue first, then soonest; a line with no date last (an attached-only report waiting for the customer's date).
    out.sort(
        key=lambda line: (line["state"] != rules.OVERDUE, line["due_at"] is None, line["due_at"] or "", line["key"])
    )
    return {"as_of": now.isoformat(), "zone": calendar.zone, "day": calendar.local_day(now).isoformat(), "lines": out}


def with_owners(control_db: Session | None, tenant_id, found: dict) -> list[dict]:
    """The lines with each owner's name (resolved now, never stored in the queue)."""
    from backend.app.complaint_review.service import people

    names = {
        "system:trial-sample": "MDARIX sample data",
        **people(control_db, tenant_id, [line["owner_id"] for line in found["lines"] if line["owner_id"]]),
    }
    return [
        {**line, "owner": names.get(line["owner_id"] or "", "") if line["owner_id"] else ""} for line in found["lines"]
    ]


def headline(count: int) -> str:
    return f"{count} open reporting deadline{'' if count == 1 else 's'} today"


# --------------------------------------------------------------------------------------------- downloads


def as_csv(rows: list[dict]) -> bytes:
    from backend.app import csv_safe

    stream = io.StringIO()
    writer = csv_safe.writer(stream, fieldnames=list(CSV_FIELDS))
    writer.writeheader()
    for line in rows:
        writer.writerow(
            {
                "ref": line["ref"],
                "market": line["market"],
                "owed": line["owed"],
                "due_at": line["due_at"] or "",
                "due_label": line["due_label"],
                "state": line["state_label"],
                "owner": line["owner"],
            }
        )
    return stream.getvalue().encode("utf-8-sig")


def as_pdf(found: dict, rows: list[dict], organization: str | None) -> bytes:
    """One printable page per 40 lines, dated, with the outage note."""
    from reports import pdf

    body: list[tuple[str, str]] = [] if rows else [(headline(0) + ".", "body")]
    for index, line in enumerate(rows):
        if index and index % PDF_LINES_PER_PAGE == 0:
            body.append(("", pdf.PAGE_BREAK))
        owner = f" | {line['owner']}" if line["owner"] else ""
        body.append(
            (
                f"{line['state_label']} | {line['due_label']} | {line['ref'] or '-'} | {line['market']} | "
                f"{line['owed']}{owner}",
                "body",
            )
        )
    return pdf.render(
        f"MDARIX open reporting deadlines, {found['day']}",
        [
            f"Organization: {organization or '-'}",
            f"As of {found['as_of'][:16].replace('T', ' ')} UTC; times in {found['zone']}. {headline(len(rows))}.",
            OUTAGE_NOTE,
        ],
        body,
        watermark="DEADLINE LIST",
        footer=f"Deadline list {found['day']} - {OUTAGE_NOTE}",
    )


# --------------------------------------------------------------------------------------------- the daily e-mail


def _already_queued(control_db: Session, tenant_id: uuid.UUID, day: str) -> bool:
    from backend.app.db.models.stage2 import OutboxEvent

    return (
        control_db.query(OutboxEvent.id)
        .filter(
            OutboxEvent.tenant_id == tenant_id,
            OutboxEvent.event_name == EVENT,
            OutboxEvent.payload["day"].as_string() == day,
        )
        .first()
        is not None
    )


def queue_for_tenant(control_db: Session, data_db: Session, tenant_id: uuid.UUID, now: datetime) -> bool:
    """Queue today's list for one organization (control-plane session; the caller commits). False before 06:00 local
    time, when it is already queued today, or when the switch is off."""
    from backend.app.db.models.stage2 import OutboxEvent

    if not switched_on():
        return False
    calendar = service.calendar_of(data_db, tenant_id)
    if now.astimezone(calendar.tz).hour < SEND_FROM_HOUR:
        return False
    day = calendar.local_day(now).isoformat()
    if _already_queued(control_db, tenant_id, day):
        return False
    found = lines(data_db, control_db, tenant_id, now)
    keep = ("ref", "market", "owed", "due_at", "due_label", "state", "state_label", "owner_id")
    control_db.add(
        OutboxEvent(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            event_name=EVENT,
            aggregate_type="Tenant",
            aggregate_id=tenant_id,
            payload={
                "tenant_id": str(tenant_id),
                "day": day,
                "as_of": found["as_of"],
                "zone": found["zone"],
                "lines": [{key: line[key] for key in keep} for line in found["lines"]],
            },
            occurred_at=now,
        )
    )
    control_db.flush()
    return True


def run_for_all_tenants(control_db: Session, now: datetime | None = None) -> dict:
    """The scheduler job: today's list for every active organization whose 06:00 has come, each committed on its own.
    A failing organization is logged; the others still run, and the job then fails so the scheduler alerts."""
    from backend.app.db.data_plane import open_tenant_data_session
    from backend.app.reportability.reminders import active_tenant_ids

    now = now or datetime.now(timezone.utc)
    if not switched_on():
        return {"queued": 0, "skipped": f"{SWITCH} is off"}
    tenant_ids = active_tenant_ids(control_db)
    queued, failed = 0, []
    for tenant_id in tenant_ids:
        try:
            with open_tenant_data_session(tenant_id) as data:
                made = queue_for_tenant(control_db, data, tenant_id, now)
            control_db.commit()
            queued += int(made)
        except Exception as exc:
            control_db.rollback()
            logger.exception("The daily deadline list failed for organization %s", tenant_id)
            failed.append({"tenant_id": str(tenant_id), "error": type(exc).__name__})
    if failed:
        raise RuntimeError(f"The daily deadline list failed for {len(failed)} organization(s): {failed}")
    return {"organizations": len(tenant_ids), "queued": queued, "failed": failed}


# --------------------------------------------------------------------------------------------- recipients


def wants_list(user) -> bool:
    preferences = user.email_preferences if isinstance(getattr(user, "email_preferences", None), dict) else {}
    return preferences.get(PREFERENCE) is not False


def eligible(control_db: Session, user) -> bool:
    """A regulatory approver, a Leader or a customer administrator (B6a-D1), by any of their roles."""
    from backend.app.access.permissions import REGULATORY_APPROVE, permissions_for_roles, roles_of_user
    from backend.app.role_codes import CUSTOMER_ADMIN_ALIASES, role_code

    roles = roles_of_user(control_db, user)
    codes = {role_code(role) for role in roles}
    return (
        "LEADER" in codes or bool(codes & CUSTOMER_ADMIN_ALIASES) or REGULATORY_APPROVE in permissions_for_roles(roles)
    )


def eligible_users(control_db: Session, tenant_id) -> list:
    from backend.app.db.models.foundation import AuthUser

    return [
        user
        for user in control_db.query(AuthUser)
        .filter(AuthUser.tenant_id == tenant_id, func.upper(AuthUser.status) == "ACTIVE")
        .order_by(AuthUser.id)
        .all()
        if user.username and eligible(control_db, user)
    ]


def recipients(control_db: Session, tenant_id) -> list[str]:
    """The eligible people who have it on. Should none be left on (the last one lost the role meanwhile), every
    eligible person gets it: the list is never sent to nobody."""
    everyone = eligible_users(control_db, tenant_id)
    wanted = [user.username for user in everyone if wants_list(user)]
    return sorted(set(wanted or [user.username for user in everyone]))


def last_recipient(control_db: Session, user) -> bool:
    """Whether ``user`` is the only eligible person of their organization who still has the list on."""
    others = [
        other for other in eligible_users(control_db, user.tenant_id) if other.id != user.id and wants_list(other)
    ]
    return not others


def deliver(control_db: Session, payload: dict) -> None:
    """Send one queued list to its recipients (outbox worker)."""
    from auth import emailer
    from backend.app.notifications import _deliver, _organization

    tenant_id = uuid.UUID(str(payload["tenant_id"]))
    found = {"lines": [line for line in payload.get("lines") or [] if isinstance(line, dict)]}
    rows = with_owners(control_db, tenant_id, found)
    _deliver(
        lambda recipient, **details: emailer.send_deadline_list(recipient, **details),
        recipients(control_db, tenant_id),
        organization=_organization(control_db, tenant_id),
        day=str(payload.get("day") or ""),
        zone=str(payload.get("zone") or "UTC"),
        lines=rows,
    )
