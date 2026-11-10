"""B7 step 5 (spec 3.2): the "Cases" import template, call logs from a call centre or a CRM, on the import engine
(backend/app/trial/imports.py reads, masks, sets aside, keeps lineage and the quality report; this module checks and
writes the Case rows).

Each row becomes a Case "To check", unsigned: an import never classifies, signs or escalates (BK-13). Contacts and the
ten answers are never read (OD-1, B7-D14): a person answers at the Case check. The words and what was tried are masked
by default. The key is ``source_system = CASE_IMPORT`` + ``source_identifier = case_id``: a re-upload fills only empty
facts, and a row that would change the words or the received time is set aside with the reason. A Case received more
than ``backlog_days`` before its import is imported backlog (RT-30): no overdue alarms, with a note.
"""

from __future__ import annotations

import re
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from backend.app.db.models.foundation import Product
from backend.app.db.models.intake import FirstContactCheck, IntakeEvent
from backend.app.intake import case_rules, rules

SOURCE = "CASE_IMPORT"
MAX_ROWS = 5_000  # spec 3.2: each row runs flags and duplicate checks
BACKLOG_NOTE = "Imported: check what was decided in your source system"

TEMPLATE = {
    "title": "Cases (call logs)",
    "required": ["case_id", "received_at", "words"],
    "optional": [
        "received_zone",
        "channel",
        "channel_ref",
        "reporter_type",
        "site",
        "reporter_country",
        "country",
        "product_id",
        "product_name",
        "version",
        "lot_id",
        "serial_number",
        "udi",
        "software_version",
        "hardware_revision",
        "firmware_version",
        "event_date",
        "first_knowledge_at",
        "first_knowledge_party",
        "first_knowledge_basis",
        "requested",
        "troubleshooting",
        "service_ticket",
        "issue_category",
        "patients",
        "qms_ref",
    ],
    "identity": ["case_id"],
    "example": [
        [
            "CC-2026-00412",
            "2026-11-02 09:40",
            "Caller said the pump showed an occlusion alarm with a clear line; restarted and it ran normally.",
            "Asia/Kolkata",
            "PHONE",
            "CTI-88121",
            "Healthcare professional",
            "City Hospital ICU",
            "IN",
            "IN",
            "PUMP-200",
            "AquaFlow 200 Infusion Pump",
            "Rev D",
            "L24-0815",
            "SN-200D-004471",
            "",
            "",
            "",
            "",
            "2026-11-02",
            "",
            "",
            "",
            "INFORMATION",
            "Line checked, pump restarted",
            "",
            "",
            "NONE",
            "",
        ]
    ],
}
HELP = {
    "case_id": "Your call centre's or CRM's own ID for the call: a re-upload of the same ID fills only empty facts.",
    "received_at": "When the call or message was received (YYYY-MM-DD HH:MM). Awareness starts here, never at the "
    "import.",
    "words": "What the reporter said. Names, phone numbers and e-mail addresses are masked before anything is saved.",
    "received_zone": "The time zone of the times (Asia/Kolkata, America/Chicago). Blank: your organization's zone.",
    "first_knowledge_at": "When someone acting for you knew first (a distributor), if earlier: with a first knowledge "
    "basis that counts, awareness starts there.",
    "troubleshooting": "What was tried on the call. Masked like the words.",
}
# Headers a call log has that are contacts: never read (OD-1).
_CONTACT = re.compile(r"(^|_)(name|caller|phone|mobile|tel|telephone|email|e_mail|mail|contact|address|whatsapp)(_|$)")
_THING = re.compile(r"product|device|site|hospital|facility|item|trade|file")
CONTACT_NOTE = "Contacts stay in your source system"


def contact_headers(headers: list[str]) -> list[str]:
    """The not-used headers of a Cases file that name a contact ("Caller name", "Phone", "E-mail")."""
    found = []
    for header in headers:
        plain = re.sub(r"[^a-z0-9]+", "_", header.lower()).strip("_")
        if _CONTACT.search(plain) and not _THING.search(plain):
            found.append(header)
    return found


_TIME = re.compile(r"^(.+?)[ T](\d{1,2}):(\d{2})(?::(\d{2})(?:\.\d+)?)?\s*([AaPp])?\.?[Mm]?\.?$")


def iso_time(value: str, date_format: str = "ISO") -> str | None:
    """A date and time as typed ("2026-11-02 09:40", "02/11/2026 9:40 PM", "2026-11-02T09:40:00+05:30") as ISO 8601,
    its offset kept when it has one; a date alone is the start of that day. None when it is not one."""
    from backend.app.trial.imports import iso_date

    text = value.strip()
    try:
        read = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return read.isoformat()
    except ValueError:
        pass
    match = _TIME.match(text)
    day = iso_date(match.group(1) if match else text, date_format)
    if day is None:
        return None
    if not match:
        return f"{day}T00:00:00"
    hour, minute, second = int(match.group(2)), int(match.group(3)), int(match.group(4) or 0)
    half = (match.group(5) or "").lower()
    if half:
        if not 1 <= hour <= 12:
            return None
        hour = hour % 12 + (12 if half == "p" else 0)
    if hour > 23 or minute > 59 or second > 59:
        return None
    return f"{day}T{hour:02d}:{minute:02d}:{second:02d}"


def _zone(row: dict, org_zone: str) -> str | None:
    from backend.app.oversight.rules import canonical_zone, zone_names

    zone = canonical_zone(row.get("received_zone") or "") or org_zone
    return zone if zone in zone_names() else None


def _at(value: str | None, zone: str) -> datetime | None:
    from backend.app.oversight.rules import zone_info

    if not value:
        return None
    moment = datetime.fromisoformat(value)
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=zone_info(zone))
    return rules.utc(moment)


_CHOICES = {
    "channel": {code for code in case_rules.CHANNELS if code != "SERVICE_RECORD_IMPORT"},
    "requested": set(rules.REQUESTS),
    "first_knowledge_party": set(rules.FIRST_KNOWLEDGE_PARTIES),
    "first_knowledge_basis": set(rules.FIRST_KNOWLEDGE_BASES),
    "patients": set(case_rules.PATIENTS),
    "issue_category": set(case_rules.ISSUE_CATEGORIES),
}


def _code(value: str) -> str:
    return re.sub(r"[^A-Z0-9]+", "_", value.strip().upper()).strip("_")


def values(row: dict, lookup, org_zone: str, now: datetime) -> tuple[dict, list[tuple[str, str]], list[str]]:
    """The Case fields of one row, the problems that refuse it ``(column, message)``, and its flags (kept, said back)."""
    problems: list[tuple[str, str]] = []
    flags: list[str] = []
    zone = _zone(row, org_zone)
    if zone is None:
        problems.append(("received_zone", f"'{row.get('received_zone')}' is not a time zone (Asia/Kolkata, UTC)."))
        zone = org_zone
    received = _at(row.get("received_at"), zone)
    if received is not None and received > now + timedelta(minutes=5):
        problems.append(("received_at", "A call cannot be received in the future."))
    first_at = _at(row.get("first_knowledge_at"), zone)
    if first_at is not None and first_at > now + timedelta(minutes=5):
        problems.append(("first_knowledge_at", "First knowledge cannot be in the future."))
    choice = {}
    for column, allowed in _CHOICES.items():
        if row.get(column):
            code = _code(row[column])
            if code not in allowed:
                problems.append((column, f"'{row[column][:40]}': use one of {', '.join(sorted(allowed))}."))
            choice[column] = code if code in allowed else None
    product = lookup.product(row["product_id"]) if row.get("product_id") else None
    if product is None and row.get("product_name"):
        product = (
            lookup.db.query(Product)
            .filter(Product.tenant_id == lookup.tenant_id, Product.name == row["product_name"])
            .first()
        )
    product_text = None
    if product is None and (row.get("product_id") or row.get("product_name")):
        product_text = (row.get("product_name") or row.get("product_id"))[:200]
        flags.append(f"Product '{product_text}' is not in your products: kept as typed.")
    version = None
    if row.get("version") and product is not None:
        version = lookup.version(product, row["version"])
        if version is None:
            problems.append(("version", f"Version '{row['version']}' of '{product.product_identifier}' is not loaded."))
    lot = lookup.lot(row["lot_id"]) if row.get("lot_id") else None
    lot_text = None
    if row.get("lot_id") and lot is None:
        lot_text = row["lot_id"]
        flags.append(f"Lot '{lot_text}' is not in your lots: kept as typed.")
    if lot is not None and lot.product_version_id is not None:
        lot_version = lookup.version_by_id(lot.product_version_id)
        if product is None and lot_version is not None:
            product = lookup.db.get(Product, lot_version.product_id)
            product_text = None
        elif lot_version is not None and lot_version.product_id != product.id:
            problems.append(("lot_id", f"Lot '{row['lot_id']}' belongs to another product."))
        version = version or lot_version
    country = (row.get("reporter_country") or "").strip().upper()
    if country and not re.fullmatch(r"[A-Z]{2}", country):
        problems.append(("reporter_country", "Use the two-letter country code (IN, US, DE)."))
    event_at = _at(f"{row['event_date']}T12:00:00", zone) if row.get("event_date") else None
    basis = choice.get("first_knowledge_basis")
    found = {
        "reporter_words": row.get("words") or "",
        "reporter_type": rules.clean(row.get("reporter_type"), 40) or None,
        "reporter_site": rules.clean(row.get("site"), 120) or None,
        "reporter_country": country or None,
        "country": rules.clean(row.get("country"), 80) or None,
        "product_id": product.id if product is not None else None,
        "product_version_id": version.id if version is not None else None,
        "lot_batch_id": lot.id if lot is not None else None,
        "product_text": product_text,
        "lot_text": lot_text,
        "serial_number": rules.clean(row.get("serial_number"), 120) or None,
        "udi": rules.clean(row.get("udi"), 120) or None,
        "software_version": rules.clean(row.get("software_version"), 60) or None,
        "hardware_revision": rules.clean(row.get("hardware_revision"), 60) or None,
        "firmware_version": rules.clean(row.get("firmware_version"), 60) or None,
        "event_at": event_at,
        "event_zone": zone if event_at else None,
        "first_knowledge_at": first_at,
        "first_knowledge_zone": zone if first_at else None,
        "first_knowledge_party": choice.get("first_knowledge_party"),
        "first_knowledge_basis": basis,
        "received_at": received,
        "received_zone": zone,
        "awareness_at": case_rules.case_awareness(received, first_at, basis) if received else None,
        "requested": choice.get("requested") or "NONE",
        "troubleshooting": row.get("troubleshooting") or None,
        "service_ticket": rules.clean(row.get("service_ticket"), 120) or None,
        "issue_category": choice.get("issue_category"),
        "patients": choice.get("patients"),
        "channel": choice.get("channel"),
        "channel_ref": rules.clean(row.get("channel_ref"), 200) or None,
        "qms_ref": rules.clean(row.get("qms_ref"), 120) or None,
    }
    found["awareness_zone"] = zone if found["awareness_at"] else None  # first knowledge shares the row's zone
    return found, problems, flags


def held(db: Session, tenant_id, case_ids) -> dict[str, IntakeEvent]:
    wanted = list(dict.fromkeys(case_ids))
    found: dict[str, IntakeEvent] = {}
    for start in range(0, len(wanted), 1000):
        for event in db.query(IntakeEvent).filter(
            IntakeEvent.tenant_id == tenant_id,
            IntakeEvent.source_system == SOURCE,
            IntakeEvent.source_identifier.in_(wanted[start : start + 1000]),
        ):
            found[event.source_identifier] = event
    return found


def _org_zone(db: Session, tenant_id) -> str:
    from backend.app.reportability.deadlines import org_zone

    return org_zone(db, tenant_id) or "UTC"


def check(rows, lookup, report) -> int:
    """Check each row's values and references; returns the rows that add a Case (``report.new_rows`` too). A row whose
    Case is already here and whose words or received time differ is set aside: an import never changes them."""
    now = datetime.now(timezone.utc)
    zone = _org_zone(lookup.db, lookup.tenant_id)
    if any(not row.get("received_zone") for _, row in rows):
        report.notes.append(f"Times without a time zone are read in your organization's zone, {zone}.")
    stored = held(lookup.db, lookup.tenant_id, [row["case_id"] for _, row in rows])
    new = flagged = kept_as_typed = 0
    for line, row in rows:
        found, problems, flags = values(row, lookup, zone, now)
        for column, message in problems:
            report.add(line, column, message)
        if flags and kept_as_typed < 20:
            report.notes.extend(f"Row {line}: {flag}" for flag in flags)
        kept_as_typed += bool(flags)
        flagged += bool(rules.harm_words(found["reporter_words"]))
        event = stored.get(row["case_id"])
        if event is None:
            new += 1
            continue
        if found["reporter_words"] != event.reporter_words:
            report.add(line, "words", f"Case {event.reference} has other words: a re-upload never changes them.")
        if found["received_at"] is not None and found["received_at"] != rules.utc(event.received_at):
            report.add(
                line,
                "received_at",
                f"Case {event.reference} was received at another time: a re-upload never changes it.",
            )
    if flagged:
        report.notes.append(
            f"{flagged:,} {'row has' if flagged == 1 else 'rows have'} harm words: a recent one goes on the triage list "
            "at once, before its Case check."
        )
    report.new_rows = new
    return new


# Facts a re-upload may fill when the Case has none (never the words, the received time or anything signed).
FILLABLE = (
    "reporter_type",
    "reporter_site",
    "reporter_country",
    "country",
    "product_id",
    "product_version_id",
    "lot_batch_id",
    "product_text",
    "lot_text",
    "serial_number",
    "udi",
    "software_version",
    "hardware_revision",
    "firmware_version",
    "event_at",
    "event_zone",
    "troubleshooting",
    "service_ticket",
    "issue_category",
    "patients",
    "channel",
    "channel_ref",
    "qms_ref",
)
_IDENTIFIER_FIELDS = {
    "product": ("product_id", "product_text"),
    "version": ("product_version_id",),
    "lot": ("lot_batch_id", "lot_text"),
    "serial": ("serial_number",),
    "udi": ("udi",),
    "software_version": ("software_version",),
    "hardware_revision": ("hardware_revision",),
    "firmware_version": ("firmware_version",),
}


def _identifiers(event_values: dict, before: dict | None = None) -> dict:
    """ID-1: each identifier given is "unconfirmed, source: Imported"; one already recorded keeps its entry."""
    given = {key: any(event_values.get(field) for field in fields) for key, fields in _IDENTIFIER_FIELDS.items()}
    raw = {key: {"source": "IMPORTED"} for key in given}
    return case_rules.clean_identifiers(raw, given) | (before or {})


def is_backlog(event, backlog_days: int) -> bool:
    """RT-30: an imported Case received (aware) more than ``backlog_days`` before its import."""
    if event.source_system != SOURCE or event.awareness_at is None or event.created_at is None:
        return False
    return rules.utc(event.awareness_at) < rules.utc(event.created_at) - timedelta(days=backlog_days)


def write(db: Session, tenant_id, rows, lookup, now: datetime, actor: str | None) -> dict:
    """Write the checked rows: a new Case "To check" (unsigned, its Case check opened with no answer), or the empty
    facts of the Case already here. Returns the counts (created, updated, flagged, backlog) and the field changes."""
    from backend.app.intake import service

    backlog_days = service.backlog_settings(db, tenant_id)[0]
    flagged = backlog = 0
    zone = _org_zone(db, tenant_id)
    stored = held(db, tenant_id, [row["case_id"] for _, row in rows])
    actor = actor or "system:case-import"
    created = updated = 0
    changes: list[dict] = []
    late = f"Imported from a Cases file on {now:%d %b %Y}"
    checks: list[FirstContactCheck] = []
    for _, row in rows:
        found, _problems, _flags = values(row, lookup, zone, now)
        event = stored.get(row["case_id"])
        if event is not None:
            changed = False
            for field in FILLABLE:
                if found[field] is not None and getattr(event, field) in (None, ""):
                    changes.append(
                        {
                            "entity": "cases",
                            "record_id": event.id,
                            "record_key": row["case_id"],
                            "field": field,
                            "before": None,
                            "after": str(found[field]),
                        }
                    )
                    setattr(event, field, found[field])
                    changed = True
            if changed:
                event.identifiers = _identifiers({f: getattr(event, f) for f in FILLABLE}, event.identifiers)
                event.updated_at = now
                event.version = (event.version or 1) + 1
                updated += 1
            continue
        event = IntakeEvent(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            reference=service.make_reference(db, tenant_id, "CONTACT"),
            kind="CONTACT",
            source_system=SOURCE,
            source_identifier=row["case_id"],
            late_entry_reason=late,
            identifiers=_identifiers(found),
            created_by=actor,
            created_at=now,
            updated_at=now,
            last_synced_at=now,
            **found,
        )
        db.add(event)
        stored[row["case_id"]] = event
        answers: dict = {}
        suggestion = case_rules.case_outcome(answers, event.requested)
        checks.append(
            FirstContactCheck(
                tenant_id=tenant_id,
                intake_event_id=event.id,
                version=1,
                guide_version=case_rules.GUIDE_VERSION,
                answers=answers,
                suggestion=suggestion,
                history=[case_rules.recalculation(None, answers, None, suggestion, actor, now)],
                created_by=actor,
                created_at=now,
                updated_at=now,
            )
        )
        created += 1
        flagged += bool(rules.harm_words(event.reporter_words))
        backlog += is_backlog(event, backlog_days)
        if created % 500 == 0:
            db.flush()  # written in batches of 500 (db-audit section 7); the route commits the run once
    db.flush()  # the Cases before their checks (composite foreign key, no relationship to order them)
    db.add_all(checks)
    return {"created": created, "updated": updated, "flagged": flagged, "backlog": backlog, "_changes": changes}
