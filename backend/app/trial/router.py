"""Free-trial API: the Platform Admin request queue, and the trial workspace's status, templates, import and insights.

Trial endpoints take the tenant only from the signed-in session and refuse tenants that are not on the Free Trial
plan, so the CSV import path never exists for paying customers.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.app.access.authz import _require_platform_admin
from backend.app.db.data_plane import get_data_plane_db
from backend.app.db.models.foundation import AuditEvent, AuthUser, Complaint, LotBatch, Product
from backend.app.db.models.stage2 import OnboardingRequest
from backend.app.db.session import get_db
from backend.app.request_context import AuthenticatedRequestContext, get_request_context
from backend.app.trial import imports
from backend.app.trial.sample_data import SAMPLE_SOURCE
from backend.app.trial.service import (
    TRIAL_FILE_LIMIT_BYTES,
    TRIAL_ROW_LIMIT,
    TRIAL_USER_LIMIT,
    approve_request,
    decline_request,
    resend_invitation,
    serialize_request,
    trial_subscription,
)

router = APIRouter(prefix="/api/v1", tags=["Free trial"])


class DeclineRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=500)


# ------------------------------------------------------------------------------------------- Platform Admin queue


@router.get("/platform-admin/trial-requests")
def list_trial_requests(request: Request, db: Session = Depends(get_db)):
    _require_platform_admin(request, db)
    rows = db.query(OnboardingRequest).order_by(OnboardingRequest.created_at.desc()).limit(500).all()
    items = [serialize_request(db, row) for row in rows]
    return {
        "items": items,
        "counts": {
            status: sum(1 for item in items if item["status"] == status)
            for status in ("PENDING_REVIEW", "APPROVED", "DECLINED")
        },
    }


@router.post("/platform-admin/trial-requests/{request_id}/approve")
def approve_trial_request(request_id: uuid.UUID, request: Request, db: Session = Depends(get_db)):
    admin = _require_platform_admin(request, db)
    return approve_request(db, request_id, admin)


@router.post("/platform-admin/trial-requests/{request_id}/decline")
def decline_trial_request(
    request_id: uuid.UUID, payload: DeclineRequest, request: Request, db: Session = Depends(get_db)
):
    admin = _require_platform_admin(request, db)
    return decline_request(db, request_id, admin, payload.reason.strip())


@router.post("/platform-admin/trial-requests/{request_id}/resend-invitation")
def resend_trial_invitation(request_id: uuid.UUID, request: Request, db: Session = Depends(get_db)):
    admin = _require_platform_admin(request, db)
    return resend_invitation(db, request_id, admin)


# ------------------------------------------------------------------------------------------- Trial workspace


def _require_trial(db: Session, ctx: AuthenticatedRequestContext):
    subscription = trial_subscription(db, uuid.UUID(str(ctx.tenant_id)))
    if subscription is None:
        raise HTTPException(
            404, detail={"code": "NOT_A_TRIAL_WORKSPACE", "message": "This workspace is not on the free trial"}
        )
    return subscription


def _count(db: Session, model, tenant_id, source: str) -> int:
    return int(
        db.query(func.count(model.id)).filter(model.tenant_id == tenant_id, model.source_system == source).scalar() or 0
    )


@router.get("/trial/status")
def trial_status(
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
    db: Session = Depends(get_db),
    data: Session = Depends(get_data_plane_db),
):
    tenant_id = uuid.UUID(str(ctx.tenant_id))
    subscription = trial_subscription(db, tenant_id)
    if subscription is None:
        return {"is_trial": False}
    now = datetime.now(timezone.utc)
    seconds_left = (subscription.expires_at - now).total_seconds()
    users = (
        db.query(func.count(AuthUser.id))
        .filter(AuthUser.tenant_id == tenant_id, AuthUser.status.in_(["ACTIVE", "INVITED"]))
        .scalar()
    )
    return {
        "is_trial": True,
        "plan": "Free Trial",
        "starts_at": subscription.starts_at.isoformat(),
        "expires_at": subscription.expires_at.isoformat(),
        "days_left": max(0, int(-(-seconds_left // 86400))),
        "limits": {"users": TRIAL_USER_LIMIT, "rows": TRIAL_ROW_LIMIT, "file_bytes": TRIAL_FILE_LIMIT_BYTES},
        "usage": {"users": int(users or 0), "rows": imports.uploaded_rows(data, tenant_id)},
        "sample": {"products": _count(data, Product, tenant_id, SAMPLE_SOURCE)},
        "own_data": {
            "products": _count(data, Product, tenant_id, imports.UPLOAD_SOURCE),
            "lots": _count(data, LotBatch, tenant_id, imports.UPLOAD_SOURCE),
            "complaints": _count(data, Complaint, tenant_id, imports.UPLOAD_SOURCE),
        },
        "templates": [
            {
                "entity": entity,
                "title": spec["title"],
                "required": spec["required"],
                "optional": spec["optional"],
                "download": f"/api/v1/trial/templates/{entity}.csv",
            }
            for entity, spec in imports.TEMPLATES.items()
        ],
    }


@router.get("/trial/templates/{entity}.csv")
def trial_template(
    entity: str, ctx: AuthenticatedRequestContext = Depends(get_request_context), db: Session = Depends(get_db)
):
    _require_trial(db, ctx)
    if entity not in imports.TEMPLATES:
        raise HTTPException(404, detail={"code": "TEMPLATE_NOT_FOUND", "message": "Unknown template"})
    return Response(
        imports.template_csv(entity),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="mdarix-{entity}-template.csv"'},
    )


async def _body(request: Request) -> bytes:
    raw = await request.body()
    if len(raw) > TRIAL_FILE_LIMIT_BYTES:
        raise HTTPException(
            413, detail={"code": "FILE_TOO_LARGE", "message": "Files can be up to 2 MB during the free trial"}
        )
    return raw


@router.post("/trial/imports/{entity}/check")
async def check_trial_import(
    entity: str,
    request: Request,
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
    db: Session = Depends(get_db),
    data: Session = Depends(get_data_plane_db),
):
    _require_trial(db, ctx)
    return imports.check_file(data, uuid.UUID(str(ctx.tenant_id)), entity, await _body(request))


@router.post("/trial/imports/{entity}")
async def run_trial_import(
    entity: str,
    request: Request,
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
    db: Session = Depends(get_db),
    data: Session = Depends(get_data_plane_db),
):
    _require_trial(db, ctx)
    tenant_id = uuid.UUID(str(ctx.tenant_id))
    raw = await _body(request)
    try:
        result = imports.import_file(data, tenant_id, entity, raw)
        db.add(
            AuditEvent(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                actor_ref=str(ctx.user_id),
                action="TRIAL_DATA_IMPORTED",
                entity_type="TrialImport",
                details=result,
                created_at=datetime.now(timezone.utc),
            )
        )
        data.commit()
        if db is not data:
            db.commit()
    except HTTPException:
        data.rollback()
        raise
    except Exception as exc:
        data.rollback()
        raise HTTPException(
            500, detail={"code": "TRIAL_IMPORT_FAILED", "message": "The import failed; nothing was saved"}
        ) from exc
    return {**result, "insights": imports.insights(data, tenant_id)}


@router.get("/trial/insights")
def trial_insights(
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
    db: Session = Depends(get_db),
    data: Session = Depends(get_data_plane_db),
):
    _require_trial(db, ctx)
    return imports.insights(data, uuid.UUID(str(ctx.tenant_id)))
