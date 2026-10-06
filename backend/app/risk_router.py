"""Risk & Traceability: the organization's real risk register and its ISO 14971 traceability.

Everything is read from the tenant's own data plane (risks, failure_modes, controls, requirements and the
relationships the quality-system import wrote; see backend/app/risk/service.py). Reading needs only a signed-in
workspace session; the CSV export needs the export permission and a review request the permission to change
records. Each export and review request is audited.
"""

from __future__ import annotations

import io
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query, Response
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from backend.app.access.permissions import DATA_EXPORT, RECORDS_WRITE, require_permission
from backend.app.csv_safe import safe_cell
from backend.app.db.data_plane import get_data_plane_db
from backend.app.db.models.foundation import Risk
from backend.app.db.session import get_db
from backend.app.enterprise_audit import make_audit_event
from backend.app.paging import Page
from backend.app.request_context import AuthenticatedRequestContext, get_request_context
from backend.app.risk.service import register, register_csv_rows, risk_query, traceability

router = APIRouter(prefix="/api/v1/risk", tags=["Risk & Traceability"])


class ReviewRequest(BaseModel):
    reason: str = Field(min_length=10, max_length=2000)

    @field_validator("reason")
    @classmethod
    def _reason(cls, value: str) -> str:
        if len(value.strip()) < 10:
            raise ValueError("Say in at least 10 characters why the risk needs review")
        return value.strip()


def _tenant(ctx: AuthenticatedRequestContext) -> uuid.UUID:
    return uuid.UUID(str(ctx.tenant_id))


@router.get("/register")
def risk_register(
    response: Response,
    product_id: uuid.UUID | None = None,
    status: str | None = Query(default=None, max_length=40),
    page: Page = Depends(),
    db: Session = Depends(get_data_plane_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """One page of the risk register: each risk with hazard, harm, severity, probability and risk level (reported as
    not captured when the imported records do not carry them), the residual-risk state, linked failure modes,
    controls with their verification evidence, requirements and the product. ``X-Total-Count`` / ``total`` give
    the size of the whole register."""
    tenant_id = _tenant(ctx)
    rows = page.apply(risk_query(db, tenant_id, product_id=product_id, status=status), response)
    data = register(db, tenant_id, risks=rows)
    total = int(response.headers["X-Total-Count"])
    return {
        "tenant_id": ctx.tenant_id,
        "items": data["items"],
        "total": total,
        "limit": page.limit,
        "offset": page.offset,
        "next_offset": int(response.headers["X-Next-Offset"]) if response.headers["X-Next-Offset"] else None,
        "fields_not_captured": data["fields_not_captured"],
        "data_notice": data["data_notice"],
        "human_review_required": True,
    }


@router.get("/traceability")
def risk_traceability(
    db: Session = Depends(get_data_plane_db), ctx: AuthenticatedRequestContext = Depends(get_request_context)
):
    """Requirement -> risk -> failure mode -> control -> verification evidence for every risk, with the counts and
    identifiers of records that are not linked into that chain."""
    return {"tenant_id": ctx.tenant_id, **traceability(db, _tenant(ctx)), "human_review_required": True}


@router.get("/export.csv", dependencies=[Depends(require_permission(DATA_EXPORT))])
def export_risk_register(
    product_id: uuid.UUID | None = None,
    status: str | None = Query(default=None, max_length=40),
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """The whole register as CSV (one row per risk, linked records joined with ';'); formula-safe cells. Audited."""
    import csv

    data = register(db, _tenant(ctx), product_id=product_id, status=status)
    out = io.StringIO()
    writer = csv.writer(out)
    for row in register_csv_rows(data["items"]):
        writer.writerow([safe_cell(cell) for cell in row])
    now = datetime.now(timezone.utc)
    control_db.add(
        make_audit_event(
            tenant_id=ctx.tenant_id,
            actor_ref=str(ctx.user_id),
            action="RISK_REGISTER_EXPORTED",
            entity_type="RiskRegister",
            correlation_id=ctx.correlation_id,
            details={"risks": len(data["items"]), "format": "CSV"},
            created_at=now,
        )
    )
    control_db.commit()
    return Response(
        content=out.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="mdarix-risk-register-{now:%Y-%m-%d}.csv"'},
    )


@router.post("/{risk_id}/review-request", dependencies=[Depends(require_permission(RECORDS_WRITE))])
def request_risk_review(
    risk_id: uuid.UUID,
    payload: ReviewRequest,
    db: Session = Depends(get_data_plane_db),
    control_db: Session = Depends(get_db),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
):
    """Ask the organization's approvers to review one risk, with the reason. Audited ``RISK_REVIEW_REQUESTED``; the
    approvers are notified by email when the notification helper is available (the audit event records whether)."""
    tenant_id = _tenant(ctx)
    risk = db.query(Risk).filter(Risk.id == risk_id, Risk.tenant_id == tenant_id).first()
    if risk is None:
        raise HTTPException(404, detail={"code": "RISK_NOT_FOUND", "message": "Risk is not available"})
    from backend.app.governance_router import _notify

    notified = _notify(
        "notify_risk_review_requested",
        control_db,
        tenant_id=tenant_id,
        risk_id=risk.id,
        risk_identifier=risk.business_id,
        requested_by=str(ctx.user_id),
        reason=payload.reason,
    )
    event = make_audit_event(
        tenant_id=ctx.tenant_id,
        actor_ref=str(ctx.user_id),
        action="RISK_REVIEW_REQUESTED",
        entity_type="Risk",
        entity_id=risk.id,
        correlation_id=ctx.correlation_id,
        reason=payload.reason,
        details={"risk_identifier": risk.risk_identifier, "status": risk.status, "approvers_notified": notified},
    )
    control_db.add(event)
    control_db.commit()
    result = {
        "risk_id": str(risk.id),
        "risk_business_id": risk.business_id,
        "risk_identifier": risk.risk_identifier,
        "status": "REVIEW_REQUESTED",
        "approvers_notified": notified,
        "audit_event_id": str(event.id),
    }
    # The request waits in the risk reviewers' queue as a task. Saved after the request; never undoes it.
    from backend.app.workflow.hooks import on_risk_review_requested

    on_risk_review_requested(db, control_db, risk, actor_user_id=ctx.user_id)
    return result
