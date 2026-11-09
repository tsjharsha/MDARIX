"""Supplier 360 (W1): the supplier list, one supplier's page, its complaints (paged) and its lots. Reads only, open to
every member of the organization like Product 360; another organization's supplier is not found (404)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from backend.app.db.data_plane import get_data_plane_db
from backend.app.paging import Page
from backend.app.product360 import supplier_service
from backend.app.request_context import AuthenticatedRequestContext, get_request_context

router = APIRouter(prefix="/api/v1/suppliers", tags=["Supplier 360"])


def _not_found() -> HTTPException:
    return HTTPException(404, detail={"code": "SUPPLIER_NOT_FOUND", "message": "Supplier not found"})


def _headers(response: Response, page: Page, total: int) -> None:
    response.headers["X-Total-Count"] = str(total)
    following = page.offset + page.limit
    response.headers["X-Next-Offset"] = str(following) if following < total else ""


@router.get("")
def list_suppliers(
    response: Response,
    page: Page = Depends(),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
    db: Session = Depends(get_data_plane_db),
) -> list[dict]:
    rows, total = supplier_service.supplier_list(db, ctx.tenant_id, page.limit, page.offset)
    _headers(response, page, total)
    return rows


@router.get("/{supplier_id}")
def get_supplier(
    supplier_id: str,
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
    db: Session = Depends(get_data_plane_db),
) -> dict:
    try:
        return supplier_service.page(db, ctx.tenant_id, supplier_id)
    except supplier_service.SupplierNotFound as exc:
        raise _not_found() from exc


@router.get("/{supplier_id}/complaints")
def supplier_complaints(
    supplier_id: str,
    response: Response,
    page: Page = Depends(),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
    db: Session = Depends(get_data_plane_db),
) -> list[dict]:
    try:
        rows, total = supplier_service.complaint_page(db, ctx.tenant_id, supplier_id, page.limit, page.offset)
    except supplier_service.SupplierNotFound as exc:
        raise _not_found() from exc
    _headers(response, page, total)
    return rows


@router.get("/{supplier_id}/lots")
def supplier_lots(
    supplier_id: str,
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
    db: Session = Depends(get_data_plane_db),
) -> dict:
    try:
        return supplier_service.lots(db, ctx.tenant_id, supplier_id)
    except supplier_service.SupplierNotFound as exc:
        raise _not_found() from exc
