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
from backend.app.db.models.foundation import (
    AuditEvent,
    AuthUser,
    Capa,
    Complaint,
    Investigation,
    LotBatch,
    Product,
    Risk,
)
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
    approved = approve_request(db, request_id, admin)
    # The sample's signals now, rather than at the scheduler's next run: the count rule over the sample complaints, in
    # a session of its own (a failure is logged and never fails the approval, which is committed).
    if approved.get("tenant_id"):
        from backend.app.signals.hooks import seed_demo_signals

        seed_demo_signals(db, uuid.UUID(str(approved["tenant_id"])))
    return approved


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
        # The sample dataset's records (Getting started explains what each part is for).
        "sample": {
            "products": _count(data, Product, tenant_id, SAMPLE_SOURCE),
            "lots": _count(data, LotBatch, tenant_id, SAMPLE_SOURCE),
            "complaints": _count(data, Complaint, tenant_id, SAMPLE_SOURCE),
            "investigations": _count(data, Investigation, tenant_id, SAMPLE_SOURCE),
            "capas": _count(data, Capa, tenant_id, SAMPLE_SOURCE),
            "risks": _count(data, Risk, tenant_id, SAMPLE_SOURCE),
        },
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
                "help": imports.column_help(entity),
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


class TrialDemoRequest(BaseModel):
    """A one-to-one demo booked from inside the trial: when suits, what to focus on, anything else."""

    preferred_time: str | None = Field(default=None, max_length=200)
    phone: str | None = Field(default=None, max_length=30)
    focus: list[str] = Field(default_factory=list, max_length=9)
    note: str | None = Field(default=None, max_length=1000)


DEMO_REPEAT_DAYS = 14


def _demo_view(row) -> dict | None:
    if row is None:
        return None
    return {
        "id": str(row.id),
        "business_id": row.business_id,
        "status": row.status,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "preferred_time": row.preferred_time,
    }


def _latest_trial_demo(db: Session, tenant_id: uuid.UUID):
    from backend.app.db.models.stage2 import DemoRequest

    return (
        db.query(DemoRequest)
        .filter(DemoRequest.trial_tenant_id == tenant_id, DemoRequest.source == "TRIAL")
        .order_by(DemoRequest.created_at.desc())
        .first()
    )


@router.get("/trial/demo-request")
def trial_demo_request_status(
    ctx: AuthenticatedRequestContext = Depends(get_request_context), db: Session = Depends(get_db)
):
    """The trial's latest one-to-one demo request, or null."""
    _require_trial(db, ctx)
    return {"request": _demo_view(_latest_trial_demo(db, uuid.UUID(str(ctx.tenant_id))))}


@router.post("/trial/demo-request")
def book_trial_demo(
    payload: TrialDemoRequest,
    background: BackgroundTasks,
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
    db: Session = Depends(get_db),
    data: Session = Depends(get_data_plane_db),
):
    """Book a one-to-one demo from inside the trial. The MDARIX team gets it in Platform Admin (Onboarding, marked as
    from a trial, with the organization and how far into the story it went) and by email. One open request per trial
    at a time: asking again within 14 days while it is open returns that request."""
    import os
    import re

    from backend.app.db.models.foundation import Tenant
    from backend.app.db.models.stage2 import DemoRequest
    from backend.app.enterprise_audit import make_audit_event
    from backend.app.trial import story

    subscription = _require_trial(db, ctx)
    tenant_id = uuid.UUID(str(ctx.tenant_id))
    user = _current_user(db, ctx)
    now = datetime.now(timezone.utc)
    latest = _latest_trial_demo(db, tenant_id)
    if latest is not None and latest.status == "NEW" and latest.created_at >= now - timedelta(days=DEMO_REPEAT_DAYS):
        return {"status": "ALREADY_REQUESTED", "request": _demo_view(latest)}
    phone = " ".join((payload.phone or "").split())
    if phone and (not re.fullmatch(r"\+?[0-9 ()\-.]{7,30}", phone) or len(re.sub(r"\D", "", phone)) < 7):
        raise HTTPException(
            422, detail={"code": "DEMO_REQUEST_INVALID", "field": "phone", "message": "Enter a valid phone number"}
        )
    titles = {code: title for code, title, *_ in story.CHAPTERS}
    focus = [titles[code] for code in dict.fromkeys(payload.focus) if code in titles]
    reached = story.progress(data, tenant_id)
    tenant = db.get(Tenant, tenant_id)
    organization = (tenant.name if tenant else None) or user.company or "Trial organization"
    seconds_left = (subscription.expires_at - now).total_seconds()
    context = {
        "chapters_tried": reached["acted_count"],
        "chapters_total": reached["total"],
        "acted": reached["acted"],
        "own_data": bool(reached["counts"].get("YOUR_DATA")),
        "days_left": max(0, int(-(-seconds_left // 86400))),
        "focus": focus,
    }
    row = DemoRequest(
        id=uuid.uuid4(),
        display_name=(user.display_name or user.username)[:120],
        email=user.username,
        phone=phone,
        status="NEW",
        source="TRIAL",
        trial_tenant_id=tenant_id,
        organization=organization[:160],
        preferred_time=" ".join((payload.preferred_time or "").split())[:200] or None,
        note=" ".join((payload.note or "").split())[:1000] or None,
        context=context,
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    db.add(
        make_audit_event(
            tenant_id=tenant_id,
            actor_ref=str(user.id),
            action="TRIAL_DEMO_REQUESTED",
            entity_type="DemoRequest",
            entity_id=row.id,
            correlation_id=ctx.correlation_id,
            details={"chapters_tried": reached["acted_count"], "focus": focus},
            created_at=now,
        )
    )
    db.commit()
    db.refresh(row)
    recipient = (os.getenv("MDARIX_DEMO_ALERT_EMAIL") or os.getenv("MDARIX_TRIAL_ALERT_EMAIL") or "").strip()
    if recipient:
        background.add_task(
            _alert_trial_demo,
            recipient,
            {
                "display_name": row.display_name,
                "email": row.email,
                "organization": organization,
                "phone": phone,
                "preferred_time": row.preferred_time or "",
                "progress": f"{reached['acted_count']} of {reached['total']} story chapters tried, "
                f"{context['days_left']} days left" + (", own data uploaded" if context["own_data"] else ""),
                "focus": tuple(focus),
                "note": row.note or "",
            },
        )
    return {"status": "DEMO_REQUESTED", "request": _demo_view(row)}


def _alert_trial_demo(recipient: str, details: dict) -> None:
    """Email the MDARIX team after the response; a failure is only logged (the request is saved)."""
    import logging

    from auth.emailer import send_trial_demo_request_alert

    try:
        send_trial_demo_request_alert(recipient, **details)
    except Exception as exc:
        logging.getLogger(__name__).warning("Trial demo request alert failed: %s", type(exc).__name__)


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
