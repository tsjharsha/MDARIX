"""G20 "Trace this value" (B6a 6.1): for one value on a report, where it came from (the record behind it and the
import row that brought that record: file, line, mapping version), who entered or changed it and when (the field
changes and the audit events of that record, in both databases on a dedicated plane, and the report's own entry of
the field), and the snapshot it was frozen in (who approved, when, SHA-256). Read only: nothing here writes.

Switch ``MDARIX_B6_TRACE`` (on): off, the route answers 404 and the links are hidden.
"""

from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from backend.app import feature_set
from backend.app.db.models.foundation import AuditEvent
from backend.app.db.models.intake import RecordFieldChange
from backend.app.signed_reviews.audit_review import sessions

SWITCH = "MDARIX_B6_TRACE"
LIMIT = 200  # newest events per record; a value's history is short, the limit only bounds a pathological record

# The complaint columns (and the names its audit events and field changes use) behind a worksheet source: a trace
# shows only these values of the record's events. A source not listed shows who and when, without values.
COMPLAINT_FIELDS: dict[str, tuple[str, ...]] = {
    "description": ("description",),
    "event_date": ("event_timestamp", "event_date", "event date"),
    "aware_date": (
        "awareness_timestamp",
        "complaint_timestamp",
        "awareness_date",
        "received_date",
        "awareness date",
        "received date",
    ),
    "incident_country": ("country",),
    "serial": ("serial_number",),
    "udi": ("udi",),
    "complaint_ref": ("complaint_identifier",),
    "event_type": ("death", "serious_injury", "malfunction"),
    "lot_serial": ("lot_batch_id", "serial_number", "lot"),
}
# The import templates whose rows carry lineage (import_lineage.key_of), by the worksheet source's record type.
LINEAGE = {"Complaint": "complaints", "Product": "products", "Lot": "lots"}


def enabled() -> bool:
    return feature_set.switched_on(SWITCH)


def _values(row: AuditEvent, keys: tuple[str, ...]) -> dict | None:
    """The event's before and after of the traced field only (never the record's other values)."""
    old = {key: value for key, value in (row.old_values or {}).items() if key in keys}
    new = {key: value for key, value in (row.new_values or {}).items() if key in keys}
    return {"before": old, "after": new} if old or new else None


def events_of(planes: list[tuple[str, Session]], tenant_id, entity_id: uuid.UUID) -> list[AuditEvent]:
    """A record's audit events, newest first, from every database holding the organization's trail (the read D12
    measures: ``tenant_id`` and ``entity_id``)."""
    found = []
    for _, session in planes:
        found += (
            session.query(AuditEvent)
            .filter(AuditEvent.tenant_id == tenant_id, AuditEvent.entity_id == entity_id)
            .order_by(AuditEvent.created_at.desc())
            .limit(LIMIT)
            .all()
        )
    return sorted(found, key=lambda row: row.created_at, reverse=True)[:LIMIT]


def _frozen(snapshot, field_id: str) -> dict | None:
    for section in (snapshot.fields or {}).get("sections") or []:
        for item in section.get("fields") or []:
            if item.get("id") == field_id:
                return item
    return None


def build(
    db: Session, control_db: Session, tenant_id, obligation, form_field, row: dict, snapshots: list, names
) -> dict:
    """The trace of ``row`` (the worksheet field as the report shows it now). ``names(refs)`` resolves people."""
    planes = sessions(control_db, db)
    keys = COMPLAINT_FIELDS.get(form_field.source or "", ())
    # The snapshot the value is frozen in: the approved one, else the one waiting for approval.
    snapshot = next((item for item in reversed(snapshots) if item.state == "APPROVED"), None) or next(
        (item for item in snapshots if item.state == "PENDING"), None
    )
    frozen = _frozen(snapshot, form_field.id) if snapshot else None
    source = row.get("source") or (frozen or {}).get("source")

    # Typed or confirmed on this report: the report's own audit events for this field.
    entered = [
        event
        for event in events_of(planes, tenant_id, obligation.id)
        if (event.details or {}).get("field") == form_field.id
        or form_field.id in ((event.details or {}).get("fields") or [])
    ]
    record_events, changes, imports = [], [], []
    if source and source.get("id"):
        record_id = uuid.UUID(source["id"])
        record_events = events_of(planes, tenant_id, record_id)
        query = db.query(RecordFieldChange).filter(
            RecordFieldChange.tenant_id == tenant_id, RecordFieldChange.record_id == record_id
        )
        # Only the traced field's own changes; a source not mapped to columns lists none (review finding 7).
        query = query.filter(RecordFieldChange.field.in_(keys))
        changes = query.order_by(RecordFieldChange.changed_at.desc()).limit(LIMIT).all() if keys else []
        if source.get("type") in LINEAGE:
            imports = origin(db, control_db, tenant_id, LINEAGE[source["type"]], record_id)

    people = names({event.actor_ref for event in entered + record_events} | _snapshot_refs(snapshot))
    return {
        "report": {"id": str(obligation.id), "market": obligation.market, "form": obligation.form_code},
        "field": {
            "id": form_field.id,
            "number": row.get("number"),
            "label": row.get("label"),
            "value": row.get("value"),
            "status_label": row.get("status_label"),
        },
        "origin": source,
        "entered_on_report": [_entered(event, people, form_field.id) for event in entered],
        "field_changes": [
            {
                "field": item.field,
                "before": item.before,
                "after": item.after,
                "source": item.source,
                "import_ref": str(item.import_ref) if item.import_ref else None,
                "at": item.changed_at.isoformat(),
            }
            for item in changes
        ],
        "record_events": [_event(event, people, keys) for event in record_events],
        "imports": imports,
        "snapshot": {
            "id": str(snapshot.id),
            "version": snapshot.version,
            "state": snapshot.state,
            "requested_by": people.get(snapshot.requested_by) or "A colleague",
            "requested_at": snapshot.requested_at.isoformat(),
            "approved_by": (people.get(snapshot.approved_by) or "A colleague") if snapshot.approved_by else None,
            "approved_at": snapshot.approved_at.isoformat() if snapshot.approved_at else None,
            "sha256": snapshot.content_fingerprint,
            "frozen_value": (frozen or {}).get("value"),
        }
        if snapshot
        else None,
    }


def _snapshot_refs(snapshot) -> set:
    return {snapshot.requested_by, snapshot.approved_by} if snapshot else set()


def _event(event: AuditEvent, people: dict, keys) -> dict:
    return {
        "action": event.action,
        "by": people.get(event.actor_ref) or ("MDARIX" if not event.actor_ref else "A colleague"),
        "at": event.created_at.isoformat(),
        "reason": event.reason,
        "values": _values(event, tuple(keys)) if keys else None,
    }


def _entered(event: AuditEvent, people: dict, field_id: str) -> dict:
    """A REPORT_FIELD_SET event keeps the field's entry under its id (``{field_id: {value, ...}}``): its value before
    and after (review finding 2)."""
    keys = ("value", "confirmed", "code_state")

    def entry(values) -> dict:
        found = (values or {}).get(field_id) or {}
        return {key: found[key] for key in keys if isinstance(found, dict) and key in found}

    before, after = entry(event.old_values), entry(event.new_values)
    return {**_event(event, people, ()), "values": {"before": before, "after": after} if before or after else None}


def origin(db: Session, control_db: Session, tenant_id, entity: str, record_id: uuid.UUID) -> list[dict]:
    """The import rows that brought the record in (file, line, mapping version, who and when); none for a record
    entered on screen. Shared with ``GET /api/v1/data/origin`` (R16)."""
    from fastapi import HTTPException

    from backend.app.data_import_router import imports_of

    try:
        return imports_of(control_db, db, tenant_id, entity, record_id)["imports"]
    except HTTPException:  # a complaint without a product has no lineage key
        return []
