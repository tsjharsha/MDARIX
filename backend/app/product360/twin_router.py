"""The Product Lifecycle Twin's reads (W5), a free trial only (a pilot gets 404 NOT_A_TRIAL_WORKSPACE, D1):

- ``GET /api/v1/products/{ref}/twin?version=``: the connected view of one version (U1);
- ``GET /api/v1/products/{ref}/change-impact?change=`` or ``?component=[&supplier=]``: what to re-check if a recorded
  change holds, or a preview of one (U2; nothing is saved, D10);
- ``GET /api/v1/field-scope?kind=COMPONENT_LOT&ref=&lot=``: the field-action scope, every lot of the organization that
  shares the factor (U3; not signable here, D5: it is signed on an investigation's Lot impact);
- ``GET /api/v1/field-scope.csv``: the same list as CSV, one row per shipment (data.export; audited, D6).

Reading is open to every signed-in member, as Product 360 is. Reads only (the export writes its audit record). MDARIX
lists; it recommends no recall and decides no notification.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from sqlalchemy.orm import Session

from backend.app.access.permissions import DATA_EXPORT, require_permission
from backend.app.db.data_plane import get_data_plane_db
from backend.app.db.session import get_db
from backend.app.downloads import attachment
from backend.app.enterprise_audit import make_audit_event
from backend.app.product360 import twin
from backend.app.product360.service import Product360Error
from backend.app.request_context import AuthenticatedRequestContext, get_request_context

router = APIRouter(prefix="/api/v1", tags=["Product Lifecycle Twin"])


def _error(status: int, code: str, message: str) -> HTTPException:
    return HTTPException(status, detail={"code": code, "message": message})


def _trial_only(control_db: Session, ctx: AuthenticatedRequestContext) -> uuid.UUID:
    from backend.app.signer_training.router import is_trial

    tenant_id = uuid.UUID(str(ctx.tenant_id))
    if not is_trial(control_db, tenant_id):
        raise _error(404, "NOT_A_TRIAL_WORKSPACE", "This workspace is not on the free trial")
    return tenant_id


def _failed(exc: Product360Error) -> HTTPException:
    return _error(404 if exc.code.endswith("NOT_FOUND") else 400, exc.code, exc.message)


@router.get("/products/{product_ref}/twin")
def product_twin(
    product_ref: str,
    version: str | None = Query(default=None, max_length=120),
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    tenant_id = _trial_only(control_db, ctx)
    try:
        return twin.twin(db, str(tenant_id), product_ref, version)
    except Product360Error as exc:
        raise _failed(exc) from exc


@router.get("/products/{product_ref}/change-impact")
def change_impact(
    product_ref: str,
    change: str | None = Query(default=None, max_length=120),
    component: str | None = Query(default=None, max_length=120),
    supplier: str | None = Query(default=None, max_length=120),
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    tenant_id = _trial_only(control_db, ctx)
    try:
        return twin.change_impact(db, str(tenant_id), product_ref, change, component, supplier)
    except Product360Error as exc:
        raise _failed(exc) from exc


def _scope(db: Session, tenant_id, kind: str, ref: str, lot: str | None) -> dict:
    factor = twin.factor_of(db, tenant_id, kind, ref, lot)
    if factor is None:
        raise _error(404, "FACTOR_NOT_FOUND", "No such component lot, supplier or product version")
    return twin.field_scope(db, tenant_id, factor)


@router.get("/field-scope")
def field_scope(
    kind: str = Query(max_length=20),
    ref: str = Query(max_length=120),
    lot: str | None = Query(default=None, max_length=120),
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    from backend.app.reportability.markets import PRACTICE_LABEL

    tenant_id = _trial_only(control_db, ctx)
    return {**_scope(db, tenant_id, kind, ref, lot), "practice_label": PRACTICE_LABEL}


@router.get("/field-scope.csv", dependencies=[Depends(require_permission(DATA_EXPORT))])
def field_scope_csv(
    kind: str = Query(max_length=20),
    ref: str = Query(max_length=120),
    lot: str | None = Query(default=None, max_length=120),
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    from backend.app.lot_impact import render
    from backend.app.reportability.markets import PRACTICE_LABEL

    tenant_id = _trial_only(control_db, ctx)
    scope = _scope(db, tenant_id, kind, ref, lot)
    body = render.render_csv({"practice_label": PRACTICE_LABEL, "list": scope})
    factor = scope["factor"]
    db.add(
        make_audit_event(
            tenant_id=tenant_id,
            actor_ref=ctx.user_id,
            action="FIELD_ACTION_SCOPE_EXPORTED",
            entity_type=factor["kind_label"].replace(" ", ""),
            entity_id=uuid.UUID(factor["id"]),
            correlation_id=ctx.correlation_id,
            details={
                "format": "CSV",
                "factor": {key: factor[key] for key in ("kind", "id", "lot", "label")},
                "lots": scope["totals"]["lots"],
                "fingerprint": scope["fingerprint"],
            },
        )
    )
    db.commit()
    name = factor["lot"] or factor["label"]
    return Response(
        content=body,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": attachment(f"mdarix-field-scope-{name}.csv")},
    )
