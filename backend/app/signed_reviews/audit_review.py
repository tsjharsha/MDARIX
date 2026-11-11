"""G1 audit trail review (B6a 5.2, owner D4): red flags first, then every event of the period.

Reads the control database AND, on a dedicated plane, the plane's own database (data-plane routes write their audit
events there; ``access/observability.py`` reads the control database only). On the shared plane the two are one
session and are read once.

Flags (each with a count and the events):
1. ``EDIT_WITHOUT_REASON``: an edit (an event carrying old values) with no reason;
2. ``EDIT_AFTER_SIGNATURE``: an edit of a record that already had a signature event (``*_SIGNED``) before it;
3. ``ADMIN_CHANGE``: an edit by an administrator account or by MDARIX staff ("MDARIX platform administrator");
4. ``BULK_CHANGE`` (one person, more than 50 edits within 10 minutes) and ``OUTSIDE_CALENDAR`` (an edit on a day
   that is not a working day of the organization's calendar, or on one of its holidays);
5. ``FAILED_SIGN_IN_SPIKE``: 10 or more ``SIGN_IN_FAILED`` for one account in one day (UTC);
6. the chain check (``verify_tenant_chain``) of each database read.
"""

from __future__ import annotations

import json
import uuid
from collections import defaultdict
from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.app.db.models.foundation import AuditEvent, AuthUser

BULK_COUNT, BULK_MINUTES, FAILED_SIGN_INS = 50, 10, 10
DUE_DAYS = 30  # monthly by default (D4)
# How often the review falls due: 1-12 months (monthly by default), set by a Leader with a reason. Kept as the latest
# audit event of this action (no migration): the setting and its history are the audit trail itself.
FREQUENCY_SET = "AUDIT_TRAIL_REVIEW_FREQUENCY_SET"
MONTHS_MIN, MONTHS_MAX, MONTHS_DEFAULT = 1, 12, 1


def frequency(control_db: Session, tenant_id) -> int:
    row = (
        control_db.query(AuditEvent.new_values)
        .filter(AuditEvent.tenant_id == tenant_id, AuditEvent.action == FREQUENCY_SET)
        .order_by(AuditEvent.created_at.desc(), AuditEvent.chain_seq.desc())
        .first()
    )
    months = ((row[0] if row else None) or {}).get("months")
    return months if isinstance(months, int) and MONTHS_MIN <= months <= MONTHS_MAX else MONTHS_DEFAULT


def add_months(day: date, months: int) -> date:
    """The same day ``months`` later, or that month's last day (31 Jan + 1 month = 28 or 29 Feb)."""
    import calendar

    index = day.month - 1 + months
    year, month = day.year + index // 12, index % 12 + 1
    return date(year, month, min(day.day, calendar.monthrange(year, month)[1]))


def started(control_db: Session, tenant_id) -> datetime | None:
    """When the organization started (activated, else created): a review never signed falls due from here."""
    from backend.app.db.models.foundation import Tenant

    row = control_db.query(Tenant.activated_at, Tenant.created_at).filter(Tenant.id == tenant_id).first()
    return (row[0] or row[1]) if row else None


def next_due(since: datetime | None, months: int, today: date) -> date:
    """Due ``months`` after ``since`` (the last signed review, else the organization's start); today without either."""
    return add_months(since.date(), months) if since else today


READ_CAP = 20_000  # per database and period; above it the review says "incomplete" (never a silent cut)
LISTED_PER_FLAG = 500
FLAG_LABELS = {
    "EDIT_WITHOUT_REASON": "Edits without a reason",
    "EDIT_AFTER_SIGNATURE": "Edits after a signature",
    "ADMIN_CHANGE": "Data changed by administrator accounts or MDARIX staff",
    "BULK_CHANGE": f"Bulk changes (one person, more than {BULK_COUNT} in {BULK_MINUTES} minutes)",
    "OUTSIDE_CALENDAR": "Changes outside the working calendar",
    "FAILED_SIGN_IN_SPIKE": f"Failed sign-in spikes ({FAILED_SIGN_INS} or more for one account in a day)",
}
# The review's own records are not flagged (a review is not an edit of business data).
REVIEW_ACTIONS = ("AUDIT_TRAIL_REVIEW_SIGNED", "AUDIT_TRAIL_REVIEW_CONFIRMED")


def sessions(control_db: Session, data_db: Session) -> list[tuple[str, Session]]:
    """The databases holding this organization's audit trail: one on the shared plane, two on a dedicated one."""
    return [("control", control_db)] if data_db is control_db else [("control", control_db), ("data", data_db)]


def default_period(last_signed: dict | None, now: datetime) -> tuple[date, date]:
    """From the end of the last signed review's period (else one month back) to today, both days included."""
    today = now.date()
    if last_signed:
        end = ((last_signed.get("content") or {}).get("period") or {}).get("to")
        if end:
            start = date.fromisoformat(end) + timedelta(days=1)
            return min(start, today), today
    return today - timedelta(days=DUE_DAYS), today


def is_edit(row: AuditEvent) -> bool:
    return bool(row.old_values) and row.action not in REVIEW_ACTIONS


def _line(plane: str, row: AuditEvent) -> dict:
    return {
        "id": str(row.id),
        "plane": plane,
        "chain_seq": row.chain_seq,
        "at": row.created_at.isoformat(),
        "actor": row.actor_ref,
        "action": row.action,
        "entity_type": row.entity_type,
        "entity_id": str(row.entity_id) if row.entity_id else None,
        "reason": row.reason,
        "old_values": row.old_values,
        "new_values": row.new_values,
    }


def _bounds(start: date, end: date) -> tuple[datetime, datetime]:
    return datetime.combine(start, time.min, timezone.utc), datetime.combine(
        end + timedelta(days=1), time.min, timezone.utc
    )


def _period_rows(session: Session, tenant_id, start: date, end: date) -> list[AuditEvent]:
    low, high = _bounds(start, end)
    return (
        session.query(AuditEvent)
        .filter(AuditEvent.tenant_id == tenant_id, AuditEvent.created_at >= low, AuditEvent.created_at < high)
        .order_by(AuditEvent.created_at.asc(), AuditEvent.chain_seq.asc())
        .limit(READ_CAP + 1)
        .all()
    )


def _first_signatures(planes, tenant_id, entity_ids: set) -> dict[tuple[str, str], datetime]:
    """(entity type, entity id) -> the first signature event on it, over the whole trail of every database."""
    found: dict[tuple[str, str], datetime] = {}
    if not entity_ids:
        return found
    for _plane, session in planes:
        rows = (
            session.query(AuditEvent.entity_type, AuditEvent.entity_id, func.min(AuditEvent.created_at))
            .filter(
                AuditEvent.tenant_id == tenant_id,
                AuditEvent.entity_id.in_(sorted(entity_ids, key=str)),
                AuditEvent.action.like("%\\_SIGNED"),
                AuditEvent.action.notin_(REVIEW_ACTIONS),
            )
            .group_by(AuditEvent.entity_type, AuditEvent.entity_id)
        )
        for entity_type, entity_id, first in rows:
            key = (entity_type, str(entity_id))
            found[key] = min(first, found.get(key, first))
    return found


def _administrators(control_db: Session, tenant_id, actors: set[str]) -> set[str]:
    from backend.app.access.authz import staff_accounts
    from backend.app.role_codes import is_administrator_role

    ids = set()
    for actor in actors:
        try:
            ids.add(uuid.UUID(str(actor)))
        except (TypeError, ValueError):
            continue
    if not ids:
        return set()
    admins = {
        str(row.id)
        for row in control_db.query(AuthUser.id, AuthUser.role).filter(
            AuthUser.tenant_id == tenant_id, AuthUser.id.in_(ids)
        )
        if is_administrator_role(row.role)
    }
    return admins | set(staff_accounts(ids))


def _bulk(edits: list[dict]) -> set[str]:
    """Ids of edits inside any 10-minute window in which one person made more than 50 edits."""
    by_actor: dict[str, list[dict]] = defaultdict(list)
    for line in edits:
        by_actor[str(line["actor"])].append(line)
    flagged: set[str] = set()
    span = timedelta(minutes=BULK_MINUTES)
    for lines in by_actor.values():
        lines.sort(key=lambda line: line["at"])
        times = [datetime.fromisoformat(line["at"]) for line in lines]
        left = 0
        for right in range(len(lines)):
            while times[right] - times[left] > span:
                left += 1
            if right - left + 1 > BULK_COUNT:
                flagged.update(line["id"] for line in lines[left : right + 1])
    return flagged


def _outside_calendar(edits: list[dict], calendar: dict) -> set[str]:
    from backend.app.oversight.rules import zone_info

    zone = zone_info(calendar.get("time_zone") or "UTC") or timezone.utc
    work_days = set(calendar.get("work_days") or [])
    holidays = {str(item.get("date")) for item in calendar.get("holidays") or []}
    flagged = set()
    for line in edits:
        local = datetime.fromisoformat(line["at"]).astimezone(zone).date()
        if local.weekday() not in work_days or local.isoformat() in holidays:
            flagged.add(line["id"])
    return flagged


def build(control_db: Session, data_db: Session, tenant_id, start: date, end: date) -> dict:
    """The review's content for the period: the flags (counts, events, actors), the chain checks and the event
    counts per database. Nothing here is written."""
    from backend.app.audit_chain import verify_tenant_chain
    from backend.app.oversight import service as oversight

    planes = sessions(control_db, data_db)
    lines: list[dict] = []
    reads, incomplete = [], []
    for plane, session in planes:
        rows = _period_rows(session, tenant_id, start, end)
        if len(rows) > READ_CAP:
            rows = rows[:READ_CAP]
            incomplete.append(plane)
        lines.extend(_line(plane, row) for row in rows)
        # The chain from the event before the period (its stored hash as the anchor) to the newest event: the period
        # and everything after it, without re-hashing years of history on every read (review finding 2).
        anchor = (
            session.query(AuditEvent.chain_seq, AuditEvent.event_hash)
            .filter(AuditEvent.tenant_id == tenant_id, AuditEvent.chain_seq < rows[0].chain_seq)
            .order_by(AuditEvent.chain_seq.desc())
            .first()
            if rows
            else None
        )
        chain = (
            verify_tenant_chain(session, tenant_id, anchor.chain_seq, anchor.event_hash)
            if anchor
            else verify_tenant_chain(session, tenant_id)
        )
        reads.append(
            {
                "plane": plane,
                "events": len(rows),
                "first_seq": rows[0].chain_seq if rows else None,
                "last_seq": rows[-1].chain_seq if rows else None,
                "chain_valid": chain["valid"],
                "chain_checked": chain["checked"],
                "first_broken_seq": chain["first_broken_seq"],
            }
        )
    lines.sort(key=lambda line: line["at"])
    edits = [line for line in lines if line["old_values"] and line["action"] not in REVIEW_ACTIONS]
    signed = _first_signatures(planes, tenant_id, {uuid.UUID(line["entity_id"]) for line in edits if line["entity_id"]})
    admins = _administrators(control_db, tenant_id, {str(line["actor"]) for line in edits})
    calendar = oversight.settings_view(oversight.settings_row(data_db, tenant_id))
    flagged: dict[str, set[str]] = {
        "EDIT_WITHOUT_REASON": {line["id"] for line in edits if not (line["reason"] or "").strip()},
        "EDIT_AFTER_SIGNATURE": {
            line["id"]
            for line in edits
            if line["entity_id"]
            and (first := signed.get((line["entity_type"], line["entity_id"])))
            and first < datetime.fromisoformat(line["at"])
        },
        "ADMIN_CHANGE": {line["id"] for line in edits if str(line["actor"]) in admins},
        "BULK_CHANGE": _bulk(edits),
        "OUTSIDE_CALENDAR": _outside_calendar(edits, calendar),
        "FAILED_SIGN_IN_SPIKE": set(),
    }
    failures: dict[tuple[str, str], list[str]] = defaultdict(list)
    for line in lines:
        if line["action"] == "SIGN_IN_FAILED":
            failures[(str(line["entity_id"] or line["actor"]), line["at"][:10])].append(line["id"])
    for ids in failures.values():
        if len(ids) >= FAILED_SIGN_INS:
            flagged["FAILED_SIGN_IN_SPIKE"].update(ids)
    by_id = {line["id"]: line for line in lines}
    flags = []
    for code, ids in flagged.items():
        listed = sorted((by_id[i] for i in ids), key=lambda line: line["at"])
        flags.append(
            {
                "code": code,
                "label": FLAG_LABELS[code],
                "count": len(ids),
                "actors": sorted({str(line["actor"]) for line in listed}),
                "events": listed[:LISTED_PER_FLAG],
            }
        )
    return {
        "period": {"from": start.isoformat(), "to": end.isoformat()},
        "planes": reads,
        "chain_valid": all(read["chain_valid"] for read in reads),
        "events": len(lines),
        "edits": len(edits),
        "incomplete": incomplete,
        "flags": flags,
    }


def for_signing(content: dict) -> dict:
    """What a signed review keeps: events read from a dedicated plane keep a reference and a hash of their values,
    never the values (the review is stored in the control database; the plane's data stays in the plane)."""
    from backend.app.human_decision.rules import fingerprint

    def kept(line: dict) -> dict:
        if line["plane"] != "data":
            return line
        values = {key: line[key] for key in ("reason", "old_values", "new_values")}
        return {
            **{key: value for key, value in line.items() if key not in values},
            "values_sha256": fingerprint(json.loads(json.dumps(values, default=str))),
        }

    return {
        **content,
        "flags": [{**flag, "events": [kept(line) for line in flag["events"]]} for flag in content["flags"]],
    }


def own_flags(content: dict, user_id) -> list[str]:
    """The flags naming the given person among their actors (D4: those need a second reviewer)."""
    return [flag["code"] for flag in content["flags"] if str(user_id) in flag["actors"]]


def page(control_db: Session, data_db: Session, tenant_id, start: date, end: date, offset: int, limit: int) -> dict:
    """Every event of the period, oldest first, with old and new values (both databases merged by time)."""
    wanted = offset + limit
    low, high = _bounds(start, end)
    lines, total = [], 0
    for plane, session in sessions(control_db, data_db):
        base = session.query(AuditEvent).filter(
            AuditEvent.tenant_id == tenant_id, AuditEvent.created_at >= low, AuditEvent.created_at < high
        )
        total += base.count()
        rows = base.order_by(AuditEvent.created_at.asc(), AuditEvent.chain_seq.asc()).limit(wanted).all()
        lines.extend(_line(plane, row) for row in rows)
    lines.sort(key=lambda line: line["at"])
    return {"total": total, "offset": offset, "limit": limit, "events": lines[offset:wanted]}
