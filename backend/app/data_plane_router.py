"""Tenant business-data API backed by the registered customer data plane."""

from __future__ import annotations

import io
from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.app.downloads import attachment
from backend.app import csv_safe
from backend.app.business_ids import business_id_map
from backend.app.db.data_plane import get_data_plane_db
from backend.app.db.models.foundation import Investigation
from backend.app.db.session import get_db
from backend.app.request_context import get_request_context
from backend.app.access.permissions import DATA_EXPORT, require_permission

router = APIRouter(prefix="/api/v1/data-plane", tags=["Tenant Data Plane"])


def _rows(db: Session, table: str, tenant_id: str, limit: int):
    # Table names are constants selected by this module, never request input.
    return [
        dict(row)
        for row in db.execute(
            text(f"SELECT * FROM {table} WHERE tenant_id = :tenant_id ORDER BY created_at DESC LIMIT :limit"),
            {"tenant_id": tenant_id, "limit": limit},
        ).mappings()
    ]


def _deps(ctx=Depends(get_request_context), control_db=Depends(get_db), db=Depends(get_data_plane_db)):
    return ctx, db


@router.get("/products")
def products(limit: int = Query(100, ge=1, le=500), deps=Depends(_deps)):
    ctx, db = deps
    return {"tenant_id": ctx.tenant_id, "records": _rows(db, "products", ctx.tenant_id, limit)}


@router.get("/investigations")
def investigations(limit: int = Query(100, ge=1, le=500), deps=Depends(_deps), control_db=Depends(get_db)):
    ctx, db = deps
    from backend.app.case_workflow.states import effective_state, state_label, with_owner_names

    records = _rows(db, "investigations", ctx.tenant_id, limit)
    # Each case's workflow state as people read it (the columns themselves come with every row).
    for row in records:
        if "workflow_state" in row:
            row["workflow_state"] = effective_state(row["workflow_state"], row.get("status"))
            row["workflow_state_label"] = state_label(row["workflow_state"])
    # The owner's name (display name, else sign-in name) next to owner_ref.
    with_owner_names(control_db, ctx.tenant_id, records)
    return {"tenant_id": ctx.tenant_id, "records": records}


@router.get("/evidence")
def evidence(limit: int = Query(100, ge=1, le=500), deps=Depends(_deps)):
    ctx, db = deps
    return {"tenant_id": ctx.tenant_id, "records": _rows(db, "evidence", ctx.tenant_id, limit)}


@router.get("/suppliers")
def suppliers(limit: int = Query(200, ge=1, le=500), deps=Depends(_deps)):
    ctx, db = deps
    return {"tenant_id": ctx.tenant_id, "records": _rows(db, "suppliers", ctx.tenant_id, limit)}


@router.get("/capas")
def capas(limit: int = Query(200, ge=1, le=500), deps=Depends(_deps)):
    ctx, db = deps
    records = _rows(db, "capas", ctx.tenant_id, limit)
    # The investigation each CAPA came from, by its business id (the screen never shows the UUID).
    investigations = business_id_map(db, Investigation, (row.get("investigation_id") for row in records))
    for row in records:
        row["investigation_business_id"] = investigations.get(str(row.get("investigation_id")))
    return {"tenant_id": ctx.tenant_id, "records": records}


@router.get("/search")
def search(
    q: str = Query(..., min_length=1, max_length=120), limit: int = Query(100, ge=1, le=500), deps=Depends(_deps)
):
    ctx, db = deps
    pattern = f"%{q}%"
    result = []
    # The MDARIX ID (business_id, e.g. PRD000001) finds a record as well as its source number and its title.
    for table, fields in (
        ("products", ("business_id", "product_identifier", "name")),
        ("investigations", ("business_id", "investigation_identifier", "investigation_question")),
        ("evidence", ("business_id", "evidence_identifier", "title")),
    ):
        where = " OR ".join(f"{field} ILIKE :pattern" for field in fields)
        result.extend(
            dict(row) | {"record_type": table[:-1]}
            for row in db.execute(
                text(f"SELECT * FROM {table} WHERE tenant_id = :tenant_id AND ({where}) LIMIT :limit"),
                {"tenant_id": ctx.tenant_id, "pattern": pattern, "limit": limit},
            ).mappings()
        )
    return {"tenant_id": ctx.tenant_id, "records": result[:limit]}


@router.get("/export.csv", dependencies=[Depends(require_permission(DATA_EXPORT))])
def export_csv(deps=Depends(_deps)):
    ctx, db = deps
    records = _rows(db, "products", ctx.tenant_id, 5000)
    output = io.StringIO()
    writer = csv_safe.writer(
        output, fieldnames=["id", "business_id", "tenant_id", "product_identifier", "name", "lifecycle_status"]
    )
    writer.writeheader()
    for row in records:
        writer.writerow({key: row.get(key) for key in writer.fieldnames})
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": attachment("tenant-products.csv")},
    )
