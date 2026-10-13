"""Post-market data and the risk file API (read only, open to every signed-in member):

- ``GET /api/v1/post-market/risk-file``: every product with post-market data or risks, the most urgent first;
- ``GET /api/v1/post-market/risk-file/{product_id}``: one product with each risk and the risk reviews that assessed it.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from backend.app.db.data_plane import get_data_plane_db
from backend.app.post_market import risk_file
from backend.app.request_context import AuthenticatedRequestContext, get_request_context

router = APIRouter(prefix="/api/v1/post-market", tags=["Post-market and the risk file"])


@router.get("/risk-file")
def risk_file_board(
    period_days: int = Query(risk_file.PERIOD_DEFAULT, ge=risk_file.PERIOD_MIN, le=risk_file.PERIOD_MAX),
    db: Session = Depends(get_data_plane_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    return risk_file.board(db, uuid.UUID(str(ctx.tenant_id)), period_days=period_days)


@router.get("/risk-file/{product_id}")
def risk_file_product(
    product_id: uuid.UUID,
    period_days: int = Query(risk_file.PERIOD_DEFAULT, ge=risk_file.PERIOD_MIN, le=risk_file.PERIOD_MAX),
    db: Session = Depends(get_data_plane_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    found = risk_file.detail(db, uuid.UUID(str(ctx.tenant_id)), product_id, period_days=period_days)
    if found is None:
        raise HTTPException(404, detail={"code": "PRODUCT_NOT_FOUND", "message": "Not found in your organization"})
    return found
