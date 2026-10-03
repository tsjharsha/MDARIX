"""Verify an organization's tamper-evident audit trail on request (backend/app/audit_chain.py)."""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from backend.app.access.authz import _admin_tenant, _require_platform_admin
from backend.app.audit_chain import verify_tenant_chain
from backend.app.db.models.foundation import Tenant
from backend.app.db.session import get_db

router = APIRouter(prefix="/api/v1", tags=["Audit"])


@router.get("/admin/audit-chain")
def verify_own_audit_chain(request: Request, db: Session = Depends(get_db)):
    """Recompute this organization's whole audit hash chain now."""
    admin = _admin_tenant(request, db)
    return verify_tenant_chain(db, admin.tenant_id)


@router.get("/platform-admin/tenants/{tenant_id}/audit-chain")
def verify_tenant_audit_chain(tenant_id: uuid.UUID, request: Request, db: Session = Depends(get_db)):
    _require_platform_admin(request, db)
    if db.get(Tenant, tenant_id) is None:
        raise HTTPException(404, detail={"code": "TENANT_NOT_FOUND", "message": "Organization is not available"})
    return verify_tenant_chain(db, tenant_id)
