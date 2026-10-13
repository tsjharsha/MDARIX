"""Free-trial API: the Platform Admin request queue, and the trial workspace's status, templates, import and insights.

Trial endpoints take the tenant only from the signed-in session and refuse tenants that are not on the Free Trial
plan. Every organization (trial or not) imports through /api/v1/data/import (backend/app/data_import_router.py);
the trial routes here keep the trial's own limits and the Getting started page. Inviting colleagues is a trial
feature too: in a paying organization its Customer Administrators invite users (/api/v1/admin/identity/users), and a
converted trial's owner becomes one (backend/app/access/platform_subscriptions.py).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
from fastapi.responses import Response
from starlette.concurrency import run_in_threadpool
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.app.access.authz import _require_platform_admin
from backend.app.db.data_plane import get_data_plane_db, open_tenant_data_session
from retrieval.record_evidence import embed_tenant_evidence
from backend.app.db.models.foundation import AuditEvent, AuthUser, Complaint, LotBatch, Product
from backend.app.db.models.stage2 import OnboardingRequest
from backend.app.db.session import get_db
from backend.app.request_context import AuthenticatedRequestContext, get_request_context
from backend.app.trial import imports, retention, team
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
from backend.app.access.permissions import RECORDS_WRITE, require_permission

router = APIRouter(prefix="/api/v1", tags=["Free trial"])


class DeclineRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=500)


class ColleagueInvite(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    display_name: str = Field(min_length=1, max_length=120)


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
        "is_owner": team.is_trial_owner(db, tenant_id, _current_user(db, ctx)),
        "plan": "Free Trial",
        "starts_at": subscription.starts_at.isoformat(),
        "expires_at": subscription.expires_at.isoformat(),
        # When the trial's data is deleted unless the organization continues (backend/app/trial/retention.py).
        "data_deleted_at": (subscription.expires_at + timedelta(days=retention.RETENTION_DAYS)).isoformat(),
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
    return await imports.read_upload(request, TRIAL_FILE_LIMIT_BYTES, "Files can be up to 2 MB during the free trial")


def _trial_import_and_audit(
    db,
    data,
    ctx,
    tenant_id,
    entity: str,
    raw: bytes,
    date_format: str = "ISO",
    options: tuple[bool, bool] = (False, False),
) -> dict:
    """The trial import (all or nothing, unless problem rows are set aside) with its audit record (runs in the thread
    pool). ``options`` is (skip_problem_rows, mask_personal_data)."""
    try:
        result = imports.import_file(data, tenant_id, entity, raw, imports.TRIAL_POLICY, date_format, *options)
        db.add(
            AuditEvent(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                actor_ref=str(ctx.user_id),
                action="TRIAL_DATA_IMPORTED",
                entity_type="TrialImport",
                # Counts only: the rejects file holds the uploader's own rows, personal data included.
                details={k: v for k, v in result.items() if k != "rejects_csv"},
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
    from backend.app.signals import hooks as signal_hooks

    if signal_hooks.imported_complaints(result):
        # Signals from the new complaints (backend/app/signals/detection.py); never fails or undoes the import.
        signal_hooks.after_complaints_saved(data, tenant_id, source="trial import")
    return result


@router.post("/trial/imports/{entity}/check", dependencies=[Depends(require_permission(RECORDS_WRITE))])
async def check_trial_import(
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
    await run_in_threadpool(_require_trial, db, ctx)
    raw = await _body(request)
    return await run_in_threadpool(
        imports.check_file, data, uuid.UUID(str(ctx.tenant_id)), entity, raw, imports.TRIAL_POLICY, order, *options
    )


@router.post("/trial/imports/{entity}", dependencies=[Depends(require_permission(RECORDS_WRITE))])
async def run_trial_import(
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
    await run_in_threadpool(_require_trial, db, ctx)
    tenant_id = uuid.UUID(str(ctx.tenant_id))
    raw = await _body(request)
    result = await run_in_threadpool(_trial_import_and_audit, db, data, ctx, tenant_id, entity, raw, order, options)
    if result.get("rows"):
        # Semantic search over the imported records, after the response (their text is already searchable).
        background.add_task(embed_tenant_evidence, open_tenant_data_session, tenant_id)
    insights = await run_in_threadpool(imports.insights, data, tenant_id)
    return {**result, "insights": insights}


@router.get("/trial/insights")
def trial_insights(
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
    db: Session = Depends(get_db),
    data: Session = Depends(get_data_plane_db),
):
    _require_trial(db, ctx)
    return imports.insights(data, uuid.UUID(str(ctx.tenant_id)))


@router.get("/trial/story")
def trial_story_chapters(
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
    db: Session = Depends(get_db),
    data: Session = Depends(get_data_plane_db),
):
    """The quality loop chapter by chapter: what the trial's records show in each and whether it acted on it."""
    from backend.app.trial import story

    _require_trial(db, ctx)
    return story.story(data, uuid.UUID(str(ctx.tenant_id)))


@router.get("/platform-admin/trials")
def platform_trial_overview(request: Request, db: Session = Depends(get_db)):
    """Every free trial still holding data: dates, usage, how far into the story it went, and its feedback."""
    from backend.app.trial import story

    _require_platform_admin(request, db)
    return story.trial_overview(db)


# ------------------------------------------------------------------------------------------- Trial team


def _current_user(db: Session, ctx: AuthenticatedRequestContext) -> AuthUser:
    user = db.query(AuthUser).filter(AuthUser.id == uuid.UUID(str(ctx.user_id))).first()
    if user is None:
        raise HTTPException(401, detail={"code": "UNAUTHENTICATED", "message": "Authentication required"})
    return user


@router.get("/trial/team")
def trial_team(ctx: AuthenticatedRequestContext = Depends(get_request_context), db: Session = Depends(get_db)):
    _require_trial(db, ctx)
    return team.team(db, uuid.UUID(str(ctx.tenant_id)), _current_user(db, ctx))


@router.post("/trial/team")
def invite_trial_colleague(
    payload: ColleagueInvite,
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
    db: Session = Depends(get_db),
):
    _require_trial(db, ctx)
    tenant_id = uuid.UUID(str(ctx.tenant_id))
    return team.invite_colleague(db, tenant_id, _current_user(db, ctx), payload.email, payload.display_name)


@router.post("/trial/team/{user_id}/resend-invitation")
def resend_trial_colleague_invitation(
    user_id: uuid.UUID,
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
    db: Session = Depends(get_db),
):
    _require_trial(db, ctx)
    return team.resend_colleague_invitation(db, uuid.UUID(str(ctx.tenant_id)), _current_user(db, ctx), user_id)


# ------------------------------------------------------------------------------------------- Data retention


@router.get("/platform-admin/trial-retention")
def trial_retention_preview(request: Request, db: Session = Depends(get_db)):
    _require_platform_admin(request, db)
    return {"retention_days": retention.RETENTION_DAYS, "due": retention.trials_due(db)}


@router.post("/platform-admin/trial-retention/run")
def run_trial_retention(request: Request, db: Session = Depends(get_db)):
    admin = _require_platform_admin(request, db)
    return retention.run_retention(db, str(admin.id))
