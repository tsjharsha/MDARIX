"""Request and download full data exports of an organization (backend/app/tenant_export.py)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.app.access.authz import _admin_tenant, _require_platform_admin
from backend.app.db.models.foundation import AuditEvent, Tenant
from backend.app.db.models.stage2 import TenantExport
from backend.app.db.session import get_db
from backend.app.tenant_export import ExportInProgress, describe, read_export, request_export

router = APIRouter(prefix="/api/v1", tags=["Data export"])


class ExportRequest(BaseModel):
    reason: str = Field(min_length=10, max_length=1000)


def _queue(db: Session, tenant_id, actor_ref: str, reason: str) -> dict:
    try:
        row = request_export(db, tenant_id, actor_ref, reason.strip())
    except ExportInProgress:
        raise HTTPException(
            409, detail={"code": "EXPORT_IN_PROGRESS", "message": "An export is already being prepared"}
        )
    db.commit()
    return describe(row)


def _list(db: Session, tenant_id) -> dict:
    rows = (
        db.query(TenantExport)
        .filter(TenantExport.tenant_id == tenant_id)
        .order_by(TenantExport.created_at.desc())
        .limit(20)
        .all()
    )
    return {"exports": [describe(row) for row in rows]}


def _download(db: Session, tenant_id, export_id: uuid.UUID, actor_ref: str) -> Response:
    try:
        row, content = read_export(db, tenant_id, export_id)
    except (LookupError, FileNotFoundError):
        raise HTTPException(404, detail={"code": "EXPORT_NOT_AVAILABLE", "message": "This export is not available"})
    db.add(
        AuditEvent(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            actor_ref=actor_ref,
            action="TENANT_EXPORT_DOWNLOADED",
            entity_type="TenantExport",
            entity_id=row.id,
            details={"size_bytes": row.size_bytes, "sha256": row.sha256},
            created_at=datetime.now(timezone.utc),
        )
    )
    db.commit()
    stamp = row.created_at.strftime("%Y%m%d")
    return Response(
        content=content,
        media_type="application/zip",
        headers={
            "Content-Disposition": f'attachment; filename="mdarix-export-{stamp}-{str(row.id)[:8]}.zip"',
            "Cache-Control": "no-store",
        },
    )


@router.post("/admin/exports", status_code=202)
def request_own_export(payload: ExportRequest, request: Request, db: Session = Depends(get_db)):
    admin = _admin_tenant(request, db)
    return _queue(db, admin.tenant_id, str(admin.id), payload.reason)


@router.get("/admin/exports")
def list_own_exports(request: Request, db: Session = Depends(get_db)):
    admin = _admin_tenant(request, db)
    return _list(db, admin.tenant_id)


@router.get("/admin/exports/{export_id}/download")
def download_own_export(export_id: uuid.UUID, request: Request, db: Session = Depends(get_db)):
    admin = _admin_tenant(request, db)
    return _download(db, admin.tenant_id, export_id, str(admin.id))


def _tenant(db: Session, tenant_id: uuid.UUID) -> uuid.UUID:
    if db.get(Tenant, tenant_id) is None:
        raise HTTPException(404, detail={"code": "TENANT_NOT_FOUND", "message": "Organization is not available"})
    return tenant_id


@router.post("/platform-admin/tenants/{tenant_id}/exports", status_code=202)
def request_tenant_export(
    tenant_id: uuid.UUID, payload: ExportRequest, request: Request, db: Session = Depends(get_db)
):
    platform_admin = _require_platform_admin(request, db)
    return _queue(db, _tenant(db, tenant_id), str(platform_admin.id), payload.reason)


@router.get("/platform-admin/tenants/{tenant_id}/exports")
def list_tenant_exports(tenant_id: uuid.UUID, request: Request, db: Session = Depends(get_db)):
    _require_platform_admin(request, db)
    return _list(db, _tenant(db, tenant_id))


@router.get("/platform-admin/tenants/{tenant_id}/exports/{export_id}/download")
def download_tenant_export(tenant_id: uuid.UUID, export_id: uuid.UUID, request: Request, db: Session = Depends(get_db)):
    platform_admin = _require_platform_admin(request, db)
    return _download(db, _tenant(db, tenant_id), export_id, str(platform_admin.id))


class PurgeRequest(BaseModel):
    reason: str = Field(min_length=10, max_length=1000)
    password: str = Field(min_length=1, max_length=128)
    # The organization's key typed back, so the wrong organization is never deleted by a slip.
    confirm_tenant_key: str = Field(min_length=1, max_length=80)


@router.post("/platform-admin/tenants/{tenant_id}/purge")
def purge_tenant_data(tenant_id: uuid.UUID, payload: PurgeRequest, request: Request, db: Session = Depends(get_db)):
    """Delete everything an organization stored and archive it (end of a pilot, or an erasure request).

    Irreversible. The organization must be suspended or terminated first, the administrator re-enters their password and types the
    organization's key, and gives the reason (docs/runbooks/DATA_REQUESTS.md). Export the data first if it is to be
    returned."""
    from auth.service import _verify
    from backend.app.db.models.foundation import AuthUser
    from backend.app.tenant_purge import PurgeFailed, purge_tenant

    platform_admin = _require_platform_admin(request, db)
    tenant = db.get(Tenant, tenant_id)
    if tenant is None:
        raise HTTPException(404, detail={"code": "TENANT_NOT_FOUND", "message": "Organization is not available"})
    if tenant.id == platform_admin.tenant_id:
        raise HTTPException(
            409, detail={"code": "OWN_ORGANIZATION", "message": "The operator organization cannot be deleted"}
        )
    if str(tenant.status).upper() not in {"SUSPENDED", "TERMINATED"}:
        raise HTTPException(
            409,
            detail={
                "code": "TENANT_NOT_SUSPENDED",
                "message": "Suspend or terminate the organization before deleting its data",
            },
        )
    if payload.confirm_tenant_key.strip() != tenant.tenant_key:
        raise HTTPException(
            422, detail={"code": "CONFIRMATION_MISMATCH", "message": "Type the organization's key exactly to confirm"}
        )
    actor = db.query(AuthUser).filter(AuthUser.id == platform_admin.id).first()
    if actor is None or not _verify(payload.password, actor.password_hash):
        raise HTTPException(
            403, detail={"code": "INVALID_REAUTHENTICATION", "message": "Your current password is required"}
        )
    busy = (
        db.query(TenantExport)
        .filter(TenantExport.tenant_id == tenant_id, TenantExport.status.in_(["QUEUED", "RUNNING"]))
        .first()
    )
    if busy is not None:
        raise HTTPException(409, detail={"code": "EXPORT_IN_PROGRESS", "message": "Wait for the export to finish"})
    try:
        result = purge_tenant(db, tenant_id, str(platform_admin.id), reason=payload.reason.strip())
    except PurgeFailed as exc:
        raise HTTPException(
            409,
            detail={"code": "PURGE_INCOMPLETE", "message": f"Nothing was deleted: {exc}. See the server log."},
        )
    return {"tenant_id": str(tenant_id), "status": "ARCHIVED", **result}
