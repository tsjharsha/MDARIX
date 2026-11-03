"""Data import, the one upload path (stage 4): products, lots, complaints and the other templates from an Excel
workbook or a CSV file into the organization's own records.

Every upload screen posts here, Getting started in a free trial as Import data everywhere (the trial's old
/api/v1/trial/imports routes are thin aliases of these, kept for links and scripts: backend/app/trial/router.py). The
validated import is backend/app/trial/imports.py: the whole file is checked first and nothing is written unless every
row passes, or the uploader chose to set problem rows aside. It needs only the permission to change records.
Free-trial workspaces keep their row and file limits (TRIAL_POLICY); other workspaces use the workspace policy. Each
import is audited (TRIAL_DATA_IMPORTED in a trial, DATA_IMPORTED elsewhere, as before). A sample-only trial
(tenants.sample_only, 0.10.71) imports nothing: every route that brings records in (the check, the import, a set-aside
row's fix and re-process; the trial's aliases too) answers 403 SAMPLE_ONLY_TRIAL (``refuse_sample_only``).

The file is sent as bytes, either as the raw body (``text/csv``) or as the ``file`` field of a multipart form.
``date_format`` is ISO (the default), DMY, MDY or AUTO (found from the file, else the organization's usual order);
``number_format`` GROUP or DECIMAL_COMMA; ``sheet`` names the workbook sheet to read; ``date_column`` names the column
that holds a complaint's date in a file without a date column MDARIX knows ("none": the import day).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Body, Depends, HTTPException, Query, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool
from sqlalchemy.orm import Session

from backend.app.downloads import attachment
from backend.app import import_lineage, import_quarantine
from backend.app.access.permissions import RECORDS_WRITE, require_permission
from backend.app.db.data_plane import get_data_plane_db
from backend.app.db.models.foundation import AuditEvent, Tenant
from backend.app.db.session import get_db
from backend.app.request_context import AuthenticatedRequestContext, get_request_context
from backend.app.business_ids import as_uuid
from backend.app.signals.hooks import IMPORT_AUDIT_ACTIONS
from backend.app.trial import imports
from backend.app.trial.service import trial_subscription

router = APIRouter(prefix="/api/v1/data/import", tags=["Data import"])

SAMPLE_ONLY_TRIAL = "SAMPLE_ONLY_TRIAL"
SAMPLE_ONLY_MESSAGE = "This evaluation uses the sample only. To try your own data, discuss a pilot."


def refuse_sample_only(
    ctx: AuthenticatedRequestContext = Depends(get_request_context), db: Session = Depends(get_db)
) -> None:
    """A sample-only trial (an event or judge trial, set in Tenant 360) brings no records in: 403, in plain words."""
    if db.query(Tenant.sample_only).filter(Tenant.id == uuid.UUID(str(ctx.tenant_id))).scalar():
        raise HTTPException(403, detail={"code": SAMPLE_ONLY_TRIAL, "message": SAMPLE_ONLY_MESSAGE})


# Every route that brings records in: the permission to change records, and never in a sample-only trial.
IMPORTING = [Depends(require_permission(RECORDS_WRITE)), Depends(refuse_sample_only)]


def _policy(db: Session, ctx: AuthenticatedRequestContext) -> imports.ImportPolicy:
    is_trial = trial_subscription(db, uuid.UUID(str(ctx.tenant_id))) is not None
    return imports.TRIAL_POLICY if is_trial else imports.WORKSPACE_POLICY


def _usual(data: Session, tenant_id: uuid.UUID) -> dict:
    """The organization's usual date order and number format, from its time zone (Settings)."""
    from backend.app.reportability.deadlines import org_zone

    return imports.usual_formats(org_zone(data, tenant_id))


def _reading(data: Session, tenant_id, sheet: str | None, number_format: str, date_column: str | None):
    """How to read the file beyond its date order (imports.FileReading)."""
    return imports.FileReading(
        sheet=(sheet or "").strip() or None,
        numbers=imports.number_format_or_422(number_format),
        date_column=(date_column or "").strip() or None,
        usual_order=_usual(data, tenant_id)["date_order"],
    )


async def _body(request: Request, policy: imports.ImportPolicy) -> bytes:
    return await imports.read_upload(request, policy.file_limit_bytes, policy.file_too_large)


@router.get("/templates")
def import_templates(
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
    db: Session = Depends(get_db),
    data: Session = Depends(get_data_plane_db),
):
    policy = _policy(db, ctx)
    return {
        "row_limit": policy.row_limit,
        "file_limit_bytes": policy.file_limit_bytes,
        # What the upload screen starts with, and what "find it from the file" falls back on (DD/MM/YYYY in India).
        "usual": _usual(data, uuid.UUID(str(ctx.tenant_id))),
        # A free trial may start from one complaints export: the products, versions and lots it names are added.
        "creates_references": policy.create_references,
        "templates": [
            {
                "entity": entity,
                "title": spec["title"],
                "required": spec["required"],
                "optional": spec["optional"],
                "help": imports.column_help(entity),
                "download": f"/api/v1/data/import/templates/{entity}.csv",
            }
            for entity, spec in imports.TEMPLATES.items()
            if imports.offered(entity, policy)
        ],
    }


@router.get("/templates/{entity}.csv")
def import_template(
    entity: str, ctx: AuthenticatedRequestContext = Depends(get_request_context), db: Session = Depends(get_db)
):
    if entity not in imports.TEMPLATES or not imports.offered(entity, _policy(db, ctx)):
        raise HTTPException(404, detail={"code": "TEMPLATE_NOT_FOUND", "message": "Unknown template"})
    return Response(
        imports.template_csv(entity),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": attachment(f"mdarix-{entity}-template.csv")},
    )


def _import_and_audit(
    db,
    data,
    ctx,
    tenant_id,
    entity: str,
    raw: bytes,
    policy: imports.ImportPolicy,
    date_format: str = "ISO",
    options: tuple[bool, bool] = (False, False),
    file_name: str | None = None,
    reading: imports.FileReading | None = None,
) -> dict:
    """The import (all or nothing, unless the uploader chose to set problem rows aside), then its audit record (runs
    in the thread pool). ``options`` is (skip_problem_rows, mask_personal_data); ``file_name`` is the uploaded file's
    name, recorded for its run report (``imports.file_label``). A free trial's import is recorded as
    TRIAL_DATA_IMPORTED with its data, in one transaction, as its own route did; any other as DATA_IMPORTED after it,
    as before (one path, the same audit records)."""
    trial = policy.source == imports.UPLOAD_SOURCE
    failure = ("TRIAL_IMPORT_FAILED" if trial else "IMPORT_FAILED", "The import failed; nothing was saved")
    try:
        result = imports.import_file(
            data, tenant_id, entity, raw, policy, date_format, *options, reading=reading, actor=str(ctx.user_id)
        )
        # Counts only: the rejects file holds the uploader's own rows, personal data included.
        details = {k: v for k, v in result.items() if k != "rejects_csv"}
        event = AuditEvent(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            actor_ref=str(ctx.user_id),
            action="TRIAL_DATA_IMPORTED" if trial else "DATA_IMPORTED",
            entity_type="TrialImport" if trial else "DataImport",
            details={**details, "file_name": imports.file_label(file_name)}
            if trial
            else {**details, "source": policy.source, "file_name": imports.file_label(file_name)},
            created_at=datetime.now(timezone.utc),
        )
        if trial:
            db.add(event)
        data.commit()
        if trial and db is not data:
            db.commit()
    except HTTPException:
        data.rollback()
        raise
    except Exception as exc:
        data.rollback()
        raise HTTPException(500, detail={"code": failure[0], "message": failure[1]}) from exc
    if not trial:
        db.add(event)
        db.commit()
    return result


@router.post("/detect", dependencies=IMPORTING)
async def detect_import(
    request: Request,
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
    db: Session = Depends(get_db),
):
    """Which of the templates a file is (0.10.82, D1.10): one drop zone for every object. Reads the file's column names
    only; nothing is checked or saved here (the check and the import follow, for the template named)."""
    policy = await run_in_threadpool(_policy, db, ctx)
    raw = await _body(request, policy)
    return await run_in_threadpool(imports.detect, raw, policy)


@router.post("/{entity}/check", dependencies=IMPORTING)
async def check_import(
    entity: str,
    request: Request,
    date_format: str = Query(default="ISO", max_length=8),
    on_problems: str = Query(default="refuse", max_length=8),
    personal_data: str = Query(default="refuse", max_length=8),
    sheet: str | None = Query(default=None, max_length=64),
    number_format: str = Query(default="GROUP", max_length=16),
    date_column: str | None = Query(default=None, max_length=255),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
    db: Session = Depends(get_db),
    data: Session = Depends(get_data_plane_db),
):
    order = imports.date_format_or_422(date_format)
    options = imports.import_options(on_problems, personal_data)
    tenant_id = uuid.UUID(str(ctx.tenant_id))
    policy = await run_in_threadpool(_policy, db, ctx)
    reading = await run_in_threadpool(_reading, data, tenant_id, sheet, number_format, date_column)
    raw = await _body(request, policy)
    # Parsing and checking query the database: off the event loop, so other requests are not held up.
    return await run_in_threadpool(
        lambda: imports.check_file(data, tenant_id, entity, raw, policy, order, *options, reading=reading)
    )


@router.post("/{entity}", dependencies=IMPORTING)
async def run_import(
    entity: str,
    request: Request,
    background: BackgroundTasks,
    date_format: str = Query(default="ISO", max_length=8),
    on_problems: str = Query(default="refuse", max_length=8),
    personal_data: str = Query(default="refuse", max_length=8),
    file_name: str | None = Query(default=None, max_length=255),
    sheet: str | None = Query(default=None, max_length=64),
    number_format: str = Query(default="GROUP", max_length=16),
    date_column: str | None = Query(default=None, max_length=255),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
    db: Session = Depends(get_db),
    data: Session = Depends(get_data_plane_db),
):
    order = imports.date_format_or_422(date_format)
    options = imports.import_options(on_problems, personal_data)
    policy = await run_in_threadpool(_policy, db, ctx)
    tenant_id = uuid.UUID(str(ctx.tenant_id))
    reading = await run_in_threadpool(_reading, data, tenant_id, sheet, number_format, date_column)
    raw = await _body(request, policy)
    result = await run_in_threadpool(
        _import_and_audit, db, data, ctx, tenant_id, entity, raw, policy, order, options, file_name, reading
    )
    source = "trial import" if policy.source == imports.UPLOAD_SOURCE else "CSV import"
    return imports.after_import(background, tenant_id, result, source=source)


@router.get("/quarantine", dependencies=[Depends(require_permission(RECORDS_WRITE))])
def quarantine_list(
    status: str = Query(default=import_quarantine.OPEN, pattern="^(OPEN|REPROCESSED|DISMISSED)$"),
    import_ref: uuid.UUID | None = None,
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
    data: Session = Depends(get_data_plane_db),
):
    """Rows imports set aside (R14), those suggesting harm first, with the counts for the reconciliation."""
    return import_quarantine.listing(data, uuid.UUID(str(ctx.tenant_id)), status, import_ref)


@router.post("/quarantine/{row_id}/reprocess", dependencies=IMPORTING)
def quarantine_reprocess(
    row_id: uuid.UUID,
    corrected: dict[str, str] = Body(..., embed=True, alias="row"),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
    db: Session = Depends(get_db),
    data: Session = Depends(get_data_plane_db),
):
    """Import a corrected quarantined row through the usual checks; the row closes only if it passes. ``row`` holds
    the corrected columns (the others keep their stored values, personal details masked)."""
    tenant_id = uuid.UUID(str(ctx.tenant_id))
    policy = _policy(db, ctx)
    try:
        result = import_quarantine.reprocess(
            data, tenant_id, row_id, corrected, imports.import_records, policy, str(ctx.user_id)
        )
        data.commit()
    except HTTPException:
        data.rollback()
        raise
    db.add(
        AuditEvent(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            actor_ref=str(ctx.user_id),
            action="QUARANTINE_ROW_REPROCESSED",
            entity_type="DataImport",
            # The row's reference only: its values are the organization's records.
            details={"quarantine_row": str(row_id), "entity": result["quarantine_row"]["entity"]},
            created_at=datetime.now(timezone.utc),
        )
    )
    db.commit()
    return result


class Dismissal(BaseModel):
    reason: str = Field(min_length=1, max_length=2000)


@router.post("/quarantine/{row_id}/dismiss", dependencies=[Depends(require_permission(RECORDS_WRITE))])
def quarantine_dismiss(
    row_id: uuid.UUID,
    body: Dismissal,
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
    db: Session = Depends(get_db),
    data: Session = Depends(get_data_plane_db),
):
    """Dismiss a set-aside row with a reason (J11): it leaves the open rows and Triage; audited."""
    tenant_id = uuid.UUID(str(ctx.tenant_id))
    try:
        row = import_quarantine.dismiss(data, tenant_id, row_id, body.reason, str(ctx.user_id), imports.stored_value)
        data.commit()
    except HTTPException:
        data.rollback()
        raise
    db.add(
        AuditEvent(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            actor_ref=str(ctx.user_id),
            action="QUARANTINE_ROW_DISMISSED",
            entity_type="DataImport",
            # The row's reference and the masked reason only: its values are the organization's records.
            details={"quarantine_row": str(row_id), "entity": row["entity"], "reason": row["resolution_note"]},
            created_at=datetime.now(timezone.utc),
        )
    )
    db.commit()
    return {"quarantine_row": row}


@router.get("/lineage/{entity}", dependencies=[Depends(require_permission(RECORDS_WRITE))])
def record_lineage(
    entity: str,
    key: str = Query(..., max_length=400),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
    data: Session = Depends(get_data_plane_db),
):
    """The imports that brought a record in, with their mapping versions (R16). ``key`` is the record's identifier
    columns joined with ':' (for a lot: lot_id:product_id:version)."""
    if entity not in imports.TEMPLATES:
        raise HTTPException(404, detail={"code": "TEMPLATE_NOT_FOUND", "message": "Unknown template"})
    return {
        "entity": entity,
        "key": key,
        "imports": import_lineage.of_record(data, uuid.UUID(str(ctx.tenant_id)), entity, key),
    }


def _run_view(event: AuditEvent, names: dict[str, str]) -> dict:
    details = event.details or {}
    return {
        "import_ref": details.get("import_ref"),
        "entity": details.get("entity"),
        "file_name": details.get("file_name"),
        "imported_at": event.created_at.isoformat(),
        "imported_by": names.get(event.actor_ref) or event.actor_ref,
        "mapping_version": details.get("mapping_version"),
        "masked_values": details.get("masked_values") or 0,
        "sample": bool(details.get("sample")),
        "report": details["quality_report"],
    }


def _actor_names(db: Session, tenant_id: uuid.UUID, events: list[AuditEvent]) -> dict[str, str]:
    """The names people read for the uploaders (an actor_ref is an account id), and the sample's own author."""
    from backend.app.case_workflow.states import SAMPLE_OWNER_NAME
    from backend.app.db.models.foundation import AuthUser

    ids = {as_uuid(event.actor_ref) for event in events} - {None}
    rows = (
        db.query(AuthUser.id, AuthUser.display_name, AuthUser.username)
        .filter(AuthUser.tenant_id == tenant_id, AuthUser.id.in_(ids))
        .all()
        if ids
        else []
    )
    return {"system:trial-sample": SAMPLE_OWNER_NAME, **{str(i): (name or user) for i, name, user in rows}}


def _runs_query(db: Session, tenant_id: uuid.UUID):
    """The governed import runs (R17): a workspace's or a free trial's imports whose audit record carries a
    data-quality report."""
    return db.query(AuditEvent).filter(
        AuditEvent.tenant_id == tenant_id,
        AuditEvent.action.in_(IMPORT_AUDIT_ACTIONS),
        AuditEvent.details.has_key("quality_report"),
    )


@router.get("/runs", dependencies=[Depends(require_permission(RECORDS_WRITE))])
def import_runs(
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
    db: Session = Depends(get_db),
    data: Session = Depends(get_data_plane_db),
):
    """The latest import runs, newest first, each with its data-quality report (R17). The sample's run is left out
    once the sample data, and its rows, are removed."""
    tenant_id = uuid.UUID(str(ctx.tenant_id))
    events = _runs_query(db, tenant_id).order_by(AuditEvent.created_at.desc()).limit(20).all()
    samples = [event.details["import_ref"] for event in events if event.details.get("sample")]
    kept = import_lineage.present(data, tenant_id, samples)
    events = [event for event in events if not event.details.get("sample") or event.details["import_ref"] in kept]
    names = _actor_names(db, tenant_id, events)
    return {"runs": [_run_view(event, names) for event in events]}


@router.get("/runs/{import_ref}", dependencies=[Depends(require_permission(RECORDS_WRITE))])
def import_run_report(
    import_ref: uuid.UUID,
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
    db: Session = Depends(get_db),
    data: Session = Depends(get_data_plane_db),
):
    """The data-quality report of one import run (R17), as recorded when it ran, with its quarantined rows' state now."""
    tenant_id = uuid.UUID(str(ctx.tenant_id))
    event = (
        _runs_query(db, tenant_id)
        .filter(AuditEvent.details["import_ref"].astext == str(import_ref))
        .order_by(AuditEvent.created_at)
        .first()
    )
    if event is None:
        raise HTTPException(404, detail={"code": "IMPORT_RUN_NOT_FOUND", "message": "No such import run"})
    return {
        **_run_view(event, _actor_names(db, tenant_id, [event])),
        "quarantine_now": import_quarantine.counts(data, tenant_id, import_ref),
    }


@router.get("/origin/{entity}/{record_id}", dependencies=[Depends(require_permission(RECORDS_WRITE))])
def record_origin(
    entity: str,
    record_id: uuid.UUID,
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
    db: Session = Depends(get_db),
    data: Session = Depends(get_data_plane_db),
):
    """Where a product, lot or complaint came from (R16), by its MDARIX id: the imports behind it, each with its file,
    who imported it and the row it was read from."""
    tenant_id = uuid.UUID(str(ctx.tenant_id))
    key, source = import_lineage.key_of(data, tenant_id, entity, record_id)
    imported = import_lineage.of_record(data, tenant_id, entity, key)
    refs = sorted({item["import_ref"] for item in imported})
    events = _runs_query(db, tenant_id).filter(AuditEvent.details["import_ref"].astext.in_(refs)).all() if refs else []
    names = _actor_names(db, tenant_id, events)
    runs = {event.details["import_ref"]: _run_view(event, names) for event in events}
    return {
        "entity": entity,
        "key": key,
        "source_system": source,
        "imports": [
            {
                **item,
                "file_name": runs.get(item["import_ref"], {}).get("file_name"),
                "imported_by": runs.get(item["import_ref"], {}).get("imported_by"),
                "has_report": item["import_ref"] in runs,
            }
            for item in imported
        ],
    }
