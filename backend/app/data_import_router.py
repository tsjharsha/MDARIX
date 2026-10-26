"""Workspace data import: products, lots and complaints from CSV into the tenant's own records (Product 360).

The same validated import the free trial uses (backend/app/trial/imports.py): the whole file is checked first and
nothing is written unless every row passes. Open to every organization: it needs only the permission to change
records. Free-trial workspaces keep their row and file limits; other workspaces use the workspace policy. Each
import is audited.

The file is sent as bytes, either as the raw body (``text/csv``) or as the ``file`` field of a multipart form, and
must be UTF-8; ``?date_format=DMY`` or ``MDY`` declares the order of day and month in dates that are not YYYY-MM-DD.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, BackgroundTasks, Body, Depends, HTTPException, Query, Request
from fastapi.responses import Response
from starlette.concurrency import run_in_threadpool
from sqlalchemy.orm import Session

from backend.app import import_lineage, import_quarantine
from backend.app.access.permissions import RECORDS_WRITE, require_permission
from backend.app.db.data_plane import get_data_plane_db
from backend.app.db.models.foundation import AuditEvent
from backend.app.db.session import get_db
from backend.app.request_context import AuthenticatedRequestContext, get_request_context
from backend.app.trial import imports
from backend.app.trial.service import trial_subscription

router = APIRouter(prefix="/api/v1/data/import", tags=["Data import"])


def _policy(db: Session, ctx: AuthenticatedRequestContext) -> imports.ImportPolicy:
    is_trial = trial_subscription(db, uuid.UUID(str(ctx.tenant_id))) is not None
    return imports.TRIAL_POLICY if is_trial else imports.WORKSPACE_POLICY


async def _body(request: Request, policy: imports.ImportPolicy) -> bytes:
    return await imports.read_upload(request, policy.file_limit_bytes, policy.file_too_large)


@router.get("/templates")
def import_templates(ctx: AuthenticatedRequestContext = Depends(get_request_context), db: Session = Depends(get_db)):
    policy = _policy(db, ctx)
    return {
        "row_limit": policy.row_limit,
        "file_limit_bytes": policy.file_limit_bytes,
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
        ],
    }


@router.get("/templates/{entity}.csv")
def import_template(entity: str, ctx: AuthenticatedRequestContext = Depends(get_request_context)):
    if entity not in imports.TEMPLATES:
        raise HTTPException(404, detail={"code": "TEMPLATE_NOT_FOUND", "message": "Unknown template"})
    return Response(
        imports.template_csv(entity),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="mdarix-{entity}-template.csv"'},
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
) -> dict:
    """The import (all or nothing, unless the uploader chose to set problem rows aside), then its audit record (runs
    in the thread pool). ``options`` is (skip_problem_rows, mask_personal_data)."""
    try:
        result = imports.import_file(data, tenant_id, entity, raw, policy, date_format, *options)
        data.commit()
    except HTTPException:
        data.rollback()
        raise
    except Exception as exc:
        data.rollback()
        raise HTTPException(
            500, detail={"code": "IMPORT_FAILED", "message": "The import failed; nothing was saved"}
        ) from exc
    db.add(
        AuditEvent(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            actor_ref=str(ctx.user_id),
            action="DATA_IMPORTED",
            entity_type="DataImport",
            # Counts only: the rejects file holds the uploader's own rows, personal data included.
            details={**{k: v for k, v in result.items() if k != "rejects_csv"}, "source": policy.source},
            created_at=datetime.now(timezone.utc),
        )
    )
    db.commit()
    return result


@router.post("/{entity}/check", dependencies=[Depends(require_permission(RECORDS_WRITE))])
async def check_import(
    entity: str,
    request: Request,
    date_format: str = Query(default="ISO", max_length=8),
    on_problems: str = Query(default="refuse", max_length=8),
    personal_data: str = Query(default="refuse", max_length=8),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
    db: Session = Depends(get_db),
    data: Session = Depends(get_data_plane_db),
):
    order = imports.date_format_or_422(date_format)
    options = imports.import_options(on_problems, personal_data)
    policy = await run_in_threadpool(_policy, db, ctx)
    raw = await _body(request, policy)
    # Parsing and checking query the database: off the event loop, so other requests are not held up.
    return await run_in_threadpool(
        imports.check_file, data, uuid.UUID(str(ctx.tenant_id)), entity, raw, policy, order, *options
    )


@router.post("/{entity}", dependencies=[Depends(require_permission(RECORDS_WRITE))])
async def run_import(
    entity: str,
    request: Request,
    background: BackgroundTasks,
    date_format: str = Query(default="ISO", max_length=8),
    on_problems: str = Query(default="refuse", max_length=8),
    personal_data: str = Query(default="refuse", max_length=8),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
    db: Session = Depends(get_db),
    data: Session = Depends(get_data_plane_db),
):
    order = imports.date_format_or_422(date_format)
    options = imports.import_options(on_problems, personal_data)
    policy = await run_in_threadpool(_policy, db, ctx)
    tenant_id = uuid.UUID(str(ctx.tenant_id))
    raw = await _body(request, policy)
    result = await run_in_threadpool(_import_and_audit, db, data, ctx, tenant_id, entity, raw, policy, order, options)
    return imports.after_import(background, tenant_id, result, source="CSV import")


@router.get("/quarantine", dependencies=[Depends(require_permission(RECORDS_WRITE))])
def quarantine_list(
    status: str = Query(default=import_quarantine.OPEN, pattern="^(OPEN|REPROCESSED)$"),
    import_ref: uuid.UUID | None = None,
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
    data: Session = Depends(get_data_plane_db),
):
    """Rows imports set aside (R14), those suggesting harm first, with the counts for the reconciliation."""
    return import_quarantine.listing(data, uuid.UUID(str(ctx.tenant_id)), status, import_ref)


@router.post("/quarantine/{row_id}/reprocess", dependencies=[Depends(require_permission(RECORDS_WRITE))])
def quarantine_reprocess(
    row_id: uuid.UUID,
    corrected: dict[str, str] = Body(..., embed=True, alias="row"),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
    db: Session = Depends(get_db),
    data: Session = Depends(get_data_plane_db),
):
    """Import a corrected quarantined row through the usual checks; the row closes only if it passes."""
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
