"""B7 step 6 (spec 3.3): the Cases export and the export for QMS entry, as CSV.

- ``GET /api/v1/intake/cases/export.csv``: one row per Case, filtered like the Cases list (view and search) and by
  received dates, channel, product, state and flagged. Contacts are masked ("Contact held: yes", OD-1); unmasked only
  with ``unmask_reason`` by a person with ``data.export``, never in a free trial. The raw e-mail is never exported.
- ``GET /api/v1/intake/qms-entry/export.csv`` (MDARIX Connect): the complaints made from Cases with no QMS ID yet, in
  the complaints template's column order plus ``mdarix_ref``. The QMS enters them; the next complaints import with
  ``mdarix_ref`` merges each row into its complaint and records the QMS ID (backend/app/trial/imports.py).

Both: UTF-8 with BOM, formula cells escaped (csv_safe), at most 20,000 rows ("narrow the filter"), permission
``data.export``, audited ``CASES_EXPORTED`` / ``QMS_ENTRY_EXPORTED`` with the filter, the row count and the file's
SHA-256. The file name carries the export ID.
"""

from __future__ import annotations

import hashlib
import io
import uuid
from datetime import date, datetime, time

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from sqlalchemy.orm import Session

from backend.app import csv_safe
from backend.app.access.permissions import DATA_EXPORT, require_permission
from backend.app.db.data_plane import get_data_plane_db
from backend.app.db.models.foundation import Complaint, LotBatch, Product, ProductVersion
from backend.app.db.models.intake import IntakeEvent, TriageRecord
from backend.app.db.session import get_db
from backend.app.downloads import attachment
from backend.app.enterprise_audit import make_audit_event
from backend.app.intake import case_rules as C
from backend.app.intake import case_import, cases_list, rules, service
from backend.app.request_context import AuthenticatedRequestContext, get_request_context
from backend.app.signer_training.router import is_trial
from backend.app.tenant_export import CONTACT_HELD

router = APIRouter(prefix="/api/v1/intake", tags=["Intake"])
EXPORTERS = [Depends(require_permission(DATA_EXPORT))]
MAX_ROWS = 20_000

CASE_FIELDS = (
    "reference",
    "received_at",
    "received_zone",
    "awareness_at",
    "awareness_source",
    "channel",
    "words",
    "product",
    "version",
    "lot",
    "not_in_master_data",
    "identifiers",
    "state",
    "owner",
    "due_at",
    "classification",
    "signed_by",
    "signed_at",
    "override_reason",
    "qa_review",
    "complaint",
    "qms_id",
    "triage_speed",
    "triage_severity",
    "issue_category",
    "flagged",
    "contact",
    "original_email_held",
)


def _csv(fields, rows, name: str) -> tuple[bytes, str, str]:
    stream = io.StringIO()
    writer = csv_safe.writer(stream, fieldnames=list(fields))
    writer.writeheader()
    writer.writerows(rows)
    body = stream.getvalue().encode("utf-8-sig")
    export_id = uuid.uuid4().hex[:12]
    return body, hashlib.sha256(body).hexdigest(), f"mdarix-{name}-{export_id}.csv"


def _audit(db: Session, ctx, action: str, **details) -> None:
    db.add(
        make_audit_event(
            tenant_id=uuid.UUID(str(ctx.tenant_id)),
            actor_ref=ctx.user_id,
            action=action,
            entity_type="IntakeEvent",
            entity_id=None,
            correlation_id=ctx.correlation_id,
            details=details,
        )
    )


def _too_many(count: int) -> None:
    if count > MAX_ROWS:
        raise HTTPException(
            422,
            detail={
                "code": "EXPORT_TOO_LARGE",
                "message": f"{count:,} rows match; one file holds up to {MAX_ROWS:,}. Narrow the filter.",
            },
        )


def _iso(value) -> str:
    return service._iso(value) or ""


def _contacts(db: Session, tenant_id, ids, unmasked: bool) -> dict:
    from backend.app.db.models.guides_communications import ExternalParty

    rows = (
        db.query(ExternalParty)
        .filter(
            ExternalParty.tenant_id == tenant_id,
            ExternalParty.intake_event_id.in_(ids or [uuid.uuid4()]),
            ExternalParty.party_type == "REPORTER",
            ExternalParty.contact_erased_at.is_(None),
        )
        .all()
    )
    if not unmasked:
        return {row.intake_event_id: CONTACT_HELD for row in rows}
    return {
        row.intake_event_id: "; ".join(
            filter(None, [row.name, row.primary_name, row.contact_role, row.contact_phone, row.contact_email])
        )
        for row in rows
    }


@router.get("/cases/export.csv", dependencies=EXPORTERS)
def export_cases(
    view: str = Query(default="all", max_length=30),
    q: str = Query(default="", max_length=80),
    received_from: date | None = None,
    received_to: date | None = None,
    channel: str | None = Query(default=None, max_length=30),
    product_id: uuid.UUID | None = None,
    state: str | None = Query(default=None, max_length=20),
    flagged: bool | None = None,
    unmask_reason: str = Query(default="", max_length=500),
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """The Cases as CSV (BK-10, BK-11): contacts masked unless a reason is given, and never in a free trial."""
    tenant_id = uuid.UUID(str(ctx.tenant_id))
    now = service.now_utc()
    reason = rules.clean(unmask_reason, 500)
    if reason and len(reason) < rules.REASON_MIN:
        raise HTTPException(422, detail={"code": "REASON_TOO_SHORT", "message": "Say why the contacts are needed"})
    unmasked = bool(reason) and not is_trial(control_db, tenant_id)
    E = IntakeEvent
    query = db.query(E).filter(E.tenant_id == tenant_id)
    if q.strip():
        query = query.filter(cases_list._search(rules.clean(q, 80)))
    condition = cases_list._condition(view, str(ctx.user_id), now, service.backlog_settings(db, tenant_id)[0])
    if condition is not None:
        query = query.filter(condition)
    calendar = service.calendar(db, tenant_id)
    if received_from:
        query = query.filter(E.received_at >= datetime.combine(received_from, time.min, tzinfo=_tz(db, tenant_id)))
    if received_to:
        query = query.filter(E.received_at <= datetime.combine(received_to, time.max, tzinfo=_tz(db, tenant_id)))
    if channel:
        query = query.filter(E.channel == channel.upper())
    if product_id:
        query = query.filter(E.product_id == product_id)
    if state:
        query = query.filter(E.status == state.upper())
    _too_many(query.order_by(None).count())
    events = query.order_by(E.received_at.desc().nullslast(), E.id).all()
    ids = [event.id for event in events]
    checks = service.checks_of(db, tenant_id, ids)
    records = {
        row.subject_id: row
        for row in db.query(TriageRecord).filter(
            TriageRecord.tenant_id == tenant_id,
            TriageRecord.subject_kind == service.INTAKE,
            TriageRecord.subject_id.in_(ids or [uuid.uuid4()]),
        )
    }
    products = cases_list._by_id(db, Product, tenant_id, {e.product_id for e in events})
    versions = cases_list._by_id(db, ProductVersion, tenant_id, {e.product_version_id for e in events})
    lots = cases_list._by_id(db, LotBatch, tenant_id, {e.lot_batch_id for e in events})
    complaints = cases_list._by_id(db, Complaint, tenant_id, {e.complaint_id for e in events})
    names = service.names_of(control_db, tenant_id, {e.owner_id for e in events} | _signers(checks))
    contacts = _contacts(db, tenant_id, ids, unmasked)
    tasks = service.tasks_of(db, tenant_id, ids)
    backlog_days = service.backlog_settings(db, tenant_id)[0]
    rows = []
    for event in events:
        versions_of = checks.get(event.id, [])
        latest = versions_of[-1] if versions_of else None
        signed = service.current_signed(versions_of)
        is_flagged = bool(rules.intake_flags(event.kind, event.reporter_words, latest.answers if latest else {}))
        if flagged is not None and is_flagged != flagged:
            continue
        product, version, lot = (
            products.get(event.product_id),
            versions.get(event.product_version_id),
            lots.get(event.lot_batch_id),
        )
        complaint, record = complaints.get(event.complaint_id), records.get(event.id)
        backlog = case_import.is_backlog(event, backlog_days)
        check_due = (
            service.working_day_end(rules.utc(event.created_at), 0, calendar)
            if signed is None and not backlog
            else None
        )
        header = cases_list.header(
            event, signed, latest.answers if latest else {}, tasks.get(event.id, []), None, None, record, check_due, now
        )
        awareness = service.event_awareness(event, record)
        rows.append(
            {
                "reference": event.reference,
                "received_at": _iso(event.received_at or event.created_at),
                "received_zone": event.received_zone or "",
                "awareness_at": _iso(awareness.get("at")),
                "awareness_source": awareness.get("source") or "",
                "channel": C.CHANNELS.get(event.channel or "", ""),
                "words": event.reporter_words,
                "product": product.name if product else (event.product_text or ""),
                "version": version.version_identifier if version else "",
                "lot": lot.lot_identifier if lot else (event.lot_text or ""),
                "not_in_master_data": "; ".join(
                    k for k, typed in (("product", event.product_text), ("lot", event.lot_text)) if typed
                ),
                "identifiers": "; ".join(
                    f"{key}: {item.get('status', '').lower()}"
                    + (f" ({item['source'].lower()})" if item.get("source") else "")
                    for key, item in (event.identifiers or {}).items()
                ),
                "state": C.STATE_LABELS.get(event.status, event.status),
                "owner": names.get(event.owner_id, "") if event.owner_id else "",
                "due_at": header["due_at"] or "",
                "classification": C.OUTCOME_LABELS.get(signed.classification, "") if signed else "",
                "signed_by": names.get(signed.signed_by, signed.signed_by or "") if signed else "",
                "signed_at": _iso(signed.signed_at) if signed else "",
                "override_reason": (signed.override_reason or "") if signed else "",
                "qa_review": (signed.review_outcome or "") if signed else "",
                "complaint": (complaint.complaint_identifier or complaint.business_id or "") if complaint else "",
                "qms_id": (complaint.qms_ref if complaint else None) or event.qms_ref or "",
                "triage_speed": (record.speed or "") if record else "",
                "triage_severity": (record.severity or "") if record else "",
                "issue_category": C.ISSUE_CATEGORIES.get(event.issue_category or "", ""),
                "flagged": "yes" if is_flagged else "no",
                "contact": contacts.get(event.id, ""),
                "original_email_held": "",  # B7b: "yes" when the Case came from an e-mail (never its content)
            }
        )
    body, digest, name = _csv(CASE_FIELDS, rows, "cases")
    _audit(
        db,
        ctx,
        "CASES_EXPORTED",
        filter={
            "view": view,
            "q": bool(q.strip()),
            "received_from": received_from.isoformat() if received_from else None,
            "received_to": received_to.isoformat() if received_to else None,
            "channel": channel,
            "product_id": str(product_id) if product_id else None,
            "state": state,
            "flagged": flagged,
        },
        rows=len(rows),
        sha256=digest,
        file_name=name,
        contacts="UNMASKED" if unmasked else "MASKED",
        unmask_reason=reason if unmasked else None,
    )
    db.commit()
    return Response(
        content=body, media_type="text/csv; charset=utf-8", headers={"Content-Disposition": attachment(name)}
    )


def _signers(checks: dict) -> set:
    return {check.signed_by for versions in checks.values() for check in versions if check.signed_by}


def _tz(db: Session, tenant_id):
    from backend.app.oversight.rules import zone_info
    from backend.app.reportability.deadlines import org_zone

    return zone_info(org_zone(db, tenant_id) or "UTC")


def _day(value) -> str:
    return rules.utc(value).date().isoformat() if value else ""


def _flag(value) -> str:
    return "" if value is None else ("Y" if value else "N")


@router.get("/qms-entry/export.csv", dependencies=EXPORTERS)
def export_for_qms_entry(
    db: Session = Depends(get_data_plane_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """Connect (BK-12): the complaints MDARIX made from Cases that the QMS does not hold yet, ready to enter there."""
    from backend.app.trial.imports import TEMPLATES

    tenant_id = uuid.UUID(str(ctx.tenant_id))
    query = db.query(Complaint).filter(
        Complaint.tenant_id == tenant_id, Complaint.source_system == "MDARIX_CASE", Complaint.qms_ref.is_(None)
    )
    _too_many(query.order_by(None).count())
    complaints = query.order_by(Complaint.created_at, Complaint.id).all()
    products = cases_list._by_id(db, Product, tenant_id, {c.product_id for c in complaints})
    versions = cases_list._by_id(db, ProductVersion, tenant_id, {c.product_version_id for c in complaints})
    lots = cases_list._by_id(db, LotBatch, tenant_id, {c.lot_batch_id for c in complaints})
    spec = TEMPLATES["complaints"]
    fields = [*spec["required"], *spec["optional"]]
    rows = []
    for complaint in complaints:
        product = products.get(complaint.product_id)
        version, lot = versions.get(complaint.product_version_id), lots.get(complaint.lot_batch_id)
        known = {
            "complaint_id": "",  # the QMS gives its own ID; the import then merges by mdarix_ref
            "product_id": product.product_identifier if product else "",
            "product_name": product.name if product else "",
            "description": complaint.description or "",
            "version": version.version_identifier if version else "",
            "lot_id": lot.lot_identifier if lot else "",
            "event_date": _day(complaint.event_timestamp),
            "received_date": _day(complaint.complaint_timestamp),
            "awareness_date": _day(complaint.awareness_timestamp),
            "country": complaint.country or "",
            "serial_number": complaint.serial_number or "",
            "udi": complaint.udi or "",
            "patient_involved": _flag(complaint.patient_involved),
            "serious_injury": _flag(complaint.serious_injury),
            "death": _flag(complaint.death),
            "malfunction": _flag(complaint.malfunction),
            "mdarix_ref": complaint.business_id or "",
        }
        rows.append({field: known.get(field, "") for field in fields})
    body, digest, name = _csv(fields, rows, "qms-entry")
    _audit(db, ctx, "QMS_ENTRY_EXPORTED", rows=len(rows), sha256=digest, file_name=name)
    db.commit()
    return Response(
        content=body, media_type="text/csv; charset=utf-8", headers={"Content-Disposition": attachment(name)}
    )
