"""Free-trial API: the Platform Admin request queue, and the trial workspace's status, templates, import and insights.

Trial endpoints take the tenant only from the signed-in session and refuse tenants that are not on the Free Trial
plan. Every organization (trial or not) imports through /api/v1/data/import (backend/app/data_import_router.py),
Getting started too; the trial's /trial/imports routes here are thin aliases of it (stage 4). Inviting colleagues is a trial
feature too: in a paying organization its Customer Administrators invite users (/api/v1/admin/identity/users), and a
converted trial's owner becomes one (backend/app/access/platform_subscriptions.py). With no admin console in a trial,
its owner also removes colleagues, resets their MFA and decides on support access (/trial/team, /trial/support-access).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel, Field
from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.app.downloads import attachment
from backend.app.access.authz import _require_platform_admin
from backend.app.db.data_plane import get_data_plane_db
from backend.app.db.models.foundation import (
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
from backend.app import data_import_router, support_access_api
from backend.app.request_context import AuthenticatedRequestContext, get_request_context
from backend.app.trial import imports, retention, team
from backend.app.trial.sample_data import SAMPLE_SOURCE
from backend.app.trial.service import (
    REQUEST_STATUSES,
    TRIAL_FILE_LIMIT_BYTES,
    TRIAL_ROW_LIMIT,
    trial_user_cap,
    approve_request,
    decline_request,
    request_queue,
    resend_invitation,
    trial_subscription,
)

router = APIRouter(prefix="/api/v1", tags=["Free trial"])


class DeclineRequest(BaseModel):
    reason: str = Field(min_length=3, max_length=500)


class ColleagueInvite(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    display_name: str = Field(min_length=1, max_length=120)
    # The colleague's persona, which sets their real role (0.10.73); none named: the Quality Leader (Leader).
    persona: str | None = Field(default=None, max_length=40)
    # Several personas (0.10.82, D1.9): each one's role; ``persona`` alone still works (one persona).
    personas: list[str] | None = Field(default=None, max_length=7)


class ColleaguePersona(BaseModel):
    persona: str | None = Field(default=None, min_length=1, max_length=40)
    personas: list[str] | None = Field(default=None, max_length=7)


# ------------------------------------------------------------------------------------------- Platform Admin queue


@router.get("/platform-admin/trial-requests")
def list_trial_requests(
    request: Request,
    status: str = "",
    q: str = "",
    page: int = 1,
    page_size: int = 50,
    sort: str = "",
    order: str = "",
    db: Session = Depends(get_db),
):
    """One page (``page_size`` up to 200) of the trial requests, newest first: ``status`` keeps one status, ``q``
    searches company, requester, email and MDARIX ID, ``sort``/``order`` order every page; ``counts`` per status."""
    _require_platform_admin(request, db)
    if status.strip() and status.strip().upper() not in REQUEST_STATUSES:
        raise HTTPException(
            422,
            detail={"code": "INVALID_REQUEST_STATUS", "message": "status is PENDING_REVIEW, APPROVED or DECLINED"},
        )
    return request_queue(db, status=status, q=q, page=page, page_size=page_size, sort=sort, order=order)


class ApproveRequest(BaseModel):
    # An event or judge trial (0.10.72, Addendum 2): the sample only, set at creation and audited with the approval.
    sample_only: bool = False


@router.post("/platform-admin/trial-requests/{request_id}/approve")
def approve_trial_request(
    request_id: uuid.UUID,
    request: Request,
    background_tasks: BackgroundTasks,
    payload: ApproveRequest | None = None,
    background: bool = False,
    db: Session = Depends(get_db),
):
    """Approve a trial request: the organization, its owner, the sample story and the invitation, all or nothing.

    ``background=true`` (review P6): the answer comes at once (202, ``APPROVING``) and the approval runs right after
    it, in its own session, exactly as the click would run it; the request list shows APPROVED when it is done, and a
    failure leaves the request waiting for review with nothing saved (the reason is logged). Without it, the answer
    waits for the whole approval (several seconds: the sample story is about a thousand rows)."""
    admin = _require_platform_admin(request, db)
    sample_only = bool(payload and payload.sample_only)
    if background:
        row = db.query(OnboardingRequest).filter(OnboardingRequest.id == request_id).first()
        if row is None:
            raise HTTPException(404, detail={"code": "TRIAL_REQUEST_NOT_FOUND", "message": "Trial request not found"})
        if row.status != "PENDING_REVIEW":
            raise HTTPException(
                409,
                detail={
                    "code": "TRIAL_REQUEST_ALREADY_REVIEWED",
                    "message": f"This request is already {row.status.lower()}",
                },
            )
        background_tasks.add_task(_approve_after_response, request_id, admin.id, sample_only)
        return JSONResponse(
            status_code=202, content={"id": str(request_id), "status": "APPROVING", "sample_only": sample_only}
        )
    # The approval also detects the sample's signals (service.approve_request).
    return approve_request(db, request_id, admin, sample_only=sample_only)


def _approve_after_response(request_id: uuid.UUID, admin_id, sample_only: bool) -> None:
    """The approval of ``approve_trial_request(background=true)``, in its own session; never raises."""
    import logging

    from backend.app.db.session import SessionLocal
    from backend.app.db.tenant_scope import bind_system

    with SessionLocal() as db:
        try:
            bind_system(db, "trial approval after the response")
            admin = db.get(AuthUser, admin_id)
            approve_request(db, request_id, admin, sample_only=sample_only)
        except Exception as exc:  # nothing was saved: the request still waits for review
            db.rollback()
            detail = exc.detail if isinstance(exc, HTTPException) else type(exc).__name__
            logging.getLogger(__name__).warning("Trial approval %s did not complete: %s", request_id, detail)


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


# The records Getting started counts: the sample's, and the organization's own imported ones.
SAMPLE_COUNTED = {
    "products": Product,
    "lots": LotBatch,
    "complaints": Complaint,
    "investigations": Investigation,
    "capas": Capa,
    "risks": Risk,
}
OWN_COUNTED = {"products": Product, "lots": LotBatch, "complaints": Complaint}


def _data_counts(data: Session, tenant_id) -> tuple[dict, dict, int]:
    """The sample's records, the organization's imported ones and its uploaded rows (``imports.uploaded_rows``), in
    one statement: they were 24 round trips, which right after an import, with the server busy with its follow-up
    work, made the status take seconds (0.10.44)."""
    from sqlalchemy import select

    def count(model, source: str):
        return (
            select(func.count(model.id))
            .where(model.tenant_id == tenant_id, model.source_system == source)
            .scalar_subquery()
        )

    uploads = imports.upload_counts(tenant_id)
    values = data.execute(
        select(
            *(count(model, SAMPLE_SOURCE) for model in SAMPLE_COUNTED.values()),
            *(count(model, imports.UPLOAD_SOURCE) for model in OWN_COUNTED.values()),
            *uploads,
        )
    ).one()
    numbers = [int(value or 0) for value in values]
    sample = dict(zip(SAMPLE_COUNTED, numbers[: len(SAMPLE_COUNTED)]))
    own = dict(zip(OWN_COUNTED, numbers[len(SAMPLE_COUNTED) : len(SAMPLE_COUNTED) + len(OWN_COUNTED)]))
    return sample, own, sum(numbers[len(SAMPLE_COUNTED) + len(OWN_COUNTED) :])


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
    viewer = _current_user(db, ctx)
    sample, own_data, uploaded = _data_counts(data, tenant_id)
    return {
        "is_trial": True,
        "is_owner": team.is_trial_owner(db, tenant_id, viewer),
        # When this person first signed in and who invited them: the feedback prompt waits until the person has had
        # MDARIX for 2 days, and an invited colleague is greeted with the owner's name (UX-26).
        "me": team.person(db, tenant_id, viewer),
        "plan": "Free Trial",
        "starts_at": subscription.starts_at.isoformat(),
        "expires_at": subscription.expires_at.isoformat(),
        # When the trial's data is deleted at the earliest unless the organization continues: counting a grace
        # extension and an open request to move the data into the MVP; none under a legal hold, with the hold
        # (backend/app/trial/retention.py, the one projection every screen and e-mail reads).
        **_retention_fields(retention.projection(db, data, subscription, now)),
        "days_left": max(0, int(-(-seconds_left // 86400))),
        "limits": {"users": trial_user_cap(), "rows": TRIAL_ROW_LIMIT, "file_bytes": TRIAL_FILE_LIMIT_BYTES},
        "usage": {"users": int(users or 0), "rows": uploaded},
        # The sample dataset's records (Getting started explains what each part is for).
        "sample": sample,
        "own_data": own_data,
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
        headers={"Content-Disposition": attachment(f"mdarix-{entity}-template.csv")},
    )


def _trial_only(ctx: AuthenticatedRequestContext = Depends(get_request_context), db: Session = Depends(get_db)):
    """The trial's old import routes answer only a free trial, as they did."""
    _require_trial(db, ctx)


# Thin aliases of the one upload path (backend/app/data_import_router.py, stage 4): the same handlers, so the same
# limits, checks, quarantine, audit record and data-quality report. Kept because the tests, the validation package's
# scripts and older links still post here; every screen posts to /api/v1/data/import.
for _path, _handler in (
    ("/trial/imports/{entity}/check", data_import_router.check_import),
    ("/trial/imports/{entity}", data_import_router.run_import),
):
    router.add_api_route(
        _path,
        _handler,
        methods=["POST"],
        dependencies=[*data_import_router.IMPORTING, Depends(_trial_only)],
        name=f"trial_alias_{_handler.__name__}",
    )


@router.get("/trial/insights")
def trial_insights(
    # The data to read (0.10.80): MDARIX_SAMPLE or TRIAL_UPLOAD; any other value, or none, reads as before.
    source: str = Query("", max_length=40),
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
    db: Session = Depends(get_db),
    data: Session = Depends(get_data_plane_db),
):
    _require_trial(db, ctx)
    # Answered as it is: the insights hold only strings, numbers, booleans, lists and dicts, and for an import of 5,000
    # complaints FastAPI's generic conversion of its 100,000 values took longer than working them out (0.10.44). The
    # same bytes as before.
    return JSONResponse(imports.insights(data, uuid.UUID(str(ctx.tenant_id)), source=source or None))


@router.get("/trial/story")
def trial_story_chapters(
    findings: bool = True,
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
    db: Session = Depends(get_db),
    data: Session = Depends(get_data_plane_db),
):
    """The quality loop chapter by chapter: what the trial's records show in each and whether it acted on it. Right
    after an import, while its signals are still being found, ``signals_pending`` is true and the trend chapter says
    so (Getting started reads the story again until it is false). ``findings=false``: which chapters were tried and
    the next one only, without what the records show (the workspace's "Chapter done" notice)."""
    from backend.app.ai_settings import ai_ready
    from backend.app.signals.hooks import detection_pending
    from backend.app.trial import citations, story

    _require_trial(db, ctx)
    tenant_id = uuid.UUID(str(ctx.tenant_id))
    request = team.trial_request(db, tenant_id)
    profile = request.profile if request else None
    cited = citations.chapters_for((profile or {}).get("citations"))
    return story.story(
        data,
        tenant_id,
        ai_ready=ai_ready(db, tenant_id),
        cited=tuple(cited),
        tried_before=story.remembered(profile),
        signals_pending=detection_pending(db, data, tenant_id),
        with_findings=findings,
    )


class SampleRemoval(BaseModel):
    confirm: bool = False


@router.get("/trial/sample-data/removal")
def sample_removal_preview(
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
    db: Session = Depends(get_db),
    data: Session = Depends(get_data_plane_db),
):
    """What removing the sample data would delete (backend/app/trial/sample_removal.py), and whether the viewer may
    do it (the person who started the trial)."""
    from backend.app.trial import sample_clock, sample_removal

    _require_trial(db, ctx)
    tenant_id = uuid.UUID(str(ctx.tenant_id))
    request = team.trial_request(db, tenant_id)
    dated = sample_clock.anchor_of(request)
    return {
        **sample_removal.preview(data, tenant_id),
        "is_owner": team.is_trial_owner(db, tenant_id, _current_user(db, ctx)),
        # "Restart the sample story" (sample_clock.restart): the own records "also remove my practice work" removes,
        # when the sample was last dated, and whether its clock has stopped because a person worked on it.
        "own_records": sample_clock.own_records(data, tenant_id),
        "sample_dated_at": dated.isoformat() if dated else None,
        "clock_stopped": sample_clock.worked_on(data, tenant_id),
    }


@router.post("/trial/sample-data/removal")
def remove_sample_data(
    payload: SampleRemoval,
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
    db: Session = Depends(get_db),
    data: Session = Depends(get_data_plane_db),
):
    """Remove the sample data and everything done with it; the organization's own data stays and the chapters
    already tried stay counted. The trial owner only, after confirming; audited as TRIAL_SAMPLE_REMOVED."""
    from backend.app.enterprise_audit import make_audit_event
    from backend.app.trial import sample_removal, story

    _require_trial(db, ctx)
    tenant_id = uuid.UUID(str(ctx.tenant_id))
    user = _current_user(db, ctx)
    if not team.is_trial_owner(db, tenant_id, user):
        raise HTTPException(
            403, detail={"code": "TRIAL_OWNER_ONLY", "message": "Only the person who started the trial can remove it"}
        )
    if not payload.confirm:
        raise HTTPException(422, detail={"code": "CONFIRMATION_REQUIRED", "message": "Confirm the removal first"})
    request = team.trial_request(db, tenant_id)
    if request is None:
        raise HTTPException(
            404, detail={"code": "NOT_A_TRIAL_WORKSPACE", "message": "This workspace is not on the free trial"}
        )
    before = story.progress(data, tenant_id, story.remembered(request.profile))
    try:
        result = sample_removal.remove(data, tenant_id, before["acted"])
    except RuntimeError as exc:
        raise HTTPException(
            409,
            detail={
                "code": "SAMPLE_REMOVAL_INCOMPLETE",
                "message": "The sample data could not be removed; nothing was changed",
            },
        ) from exc
    data.commit()
    request.profile = {**(request.profile or {}), story.REMEMBERED: before["acted"]}
    db.add(
        make_audit_event(
            tenant_id=tenant_id,
            actor_ref=str(user.id),
            action="TRIAL_SAMPLE_REMOVED",
            entity_type="Tenant",
            entity_id=tenant_id,
            details={"deleted": result["deleted"], "chapters_kept": before["acted"]},
            correlation_id=ctx.correlation_id,
        )
    )
    db.commit()
    return {"status": "SAMPLE_REMOVED", "deleted": result["deleted"], "chapters_kept": before["acted"]}


class SampleRestart(BaseModel):
    confirm: bool = False
    # "Also remove my practice work": the organization's own uploaded records and what was done with them.
    own: bool = False


@router.post("/trial/sample-data/restart")
def restart_sample_story(
    payload: SampleRestart,
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
    db: Session = Depends(get_db),
    data: Session = Depends(get_data_plane_db),
):
    """Restart the sample story: remove the sample and everything done with it, and seed it again dated now
    (backend/app/trial/sample_clock.py); with ``own`` the organization's own uploads and what was done with them go
    too. The trial owner only, after confirming; audited as TRIAL_SAMPLE_RESTARTED."""
    from backend.app.trial import sample_clock

    _require_trial(db, ctx)
    tenant_id = uuid.UUID(str(ctx.tenant_id))
    user = _current_user(db, ctx)
    if not team.is_trial_owner(db, tenant_id, user):
        raise HTTPException(
            403,
            detail={
                "code": "TRIAL_OWNER_ONLY",
                "message": "Only the person who started the trial can restart the story",
            },
        )
    if not payload.confirm:
        raise HTTPException(422, detail={"code": "CONFIRMATION_REQUIRED", "message": "Confirm the restart first"})
    if team.trial_request(db, tenant_id) is None:
        raise HTTPException(
            404, detail={"code": "NOT_A_TRIAL_WORKSPACE", "message": "This workspace is not on the free trial"}
        )
    try:
        return sample_clock.restart(db, data, tenant_id, user, own=payload.own, correlation_id=ctx.correlation_id)
    except RuntimeError as exc:
        data.rollback()
        raise HTTPException(
            409,
            detail={
                "code": "SAMPLE_RESTART_INCOMPLETE",
                "message": "The sample story could not be restarted; nothing was changed",
            },
        ) from exc


# ------------------------------------------------------------------------------------------- The short story (A4)


@router.get("/trial/short-story")
def short_story(
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
    db: Session = Depends(get_db),
    data: Session = Depends(get_data_plane_db),
):
    """The short story on SAMPLE-RV-11 for this person (0.10.71, A4): its four steps, done from what was saved on the
    record, and what the screens show at each (backend/app/trial/short_story.py)."""
    from backend.app.trial import short_story as story

    _require_trial(db, ctx)
    tenant_id = uuid.UUID(str(ctx.tenant_id))
    return story.progress(data, db, tenant_id, str(ctx.user_id), team.trial_request(db, tenant_id))


class ShortStoryMark(BaseModel):
    step: str = Field(pattern="^(read|question|summary)$")
    # Step 3 (0.10.72, F2): the request that asks the consequence question, kept with the story.
    request_id: uuid.UUID | None = None


@router.post("/trial/short-story/marks")
def mark_short_story(
    payload: ShortStoryMark,
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
    db: Session = Depends(get_db),
    data: Session = Depends(get_data_plane_db),
):
    """The person's own marks (0.10.71, A4): the call read, and the intake decision summary seen once the route and the
    open question are recorded. Kept per person on the trial's request; no business record changes."""
    from backend.app.trial import short_story as story

    _require_trial(db, ctx)
    tenant_id, me = uuid.UUID(str(ctx.tenant_id)), str(ctx.user_id)
    request = db.query(OnboardingRequest).filter(OnboardingRequest.tenant_id == tenant_id).with_for_update().first()
    complaint = story.flagship(data, tenant_id)
    if request is None or complaint is None:
        raise HTTPException(
            404, detail={"code": "NO_SAMPLE_EVENT", "message": "The sample event is not in this workspace"}
        )
    if payload.step == "question":
        asked = story.asked_request(data, tenant_id, complaint, payload.request_id) if payload.request_id else None
        if asked is None:
            raise HTTPException(
                409,
                detail={
                    "code": "NOT_THE_QUESTION",
                    "message": "Record the question to the hospital, with its owner and reply date, first.",
                },
            )
        story.bind_question(request, complaint.id, asked.id)
        db.commit()
        return story.progress(data, db, tenant_id, me, request)
    if payload.step == "summary":
        current = story.progress(data, db, tenant_id, me, request)
        if not all(step["done"] for step in current["steps"][1:3]):
            raise HTTPException(
                409,
                detail={
                    "code": "SUMMARY_NOT_READY",
                    "message": "Decide the route and name the open question first: the summary rests on them.",
                },
            )
    story.record_mark(request, me, complaint.id, payload.step, story.now_utc())
    db.commit()
    return story.progress(data, db, tenant_id, me, request)


# ------------------------------------------------------------------------- One story, ten steps (0.10.82, D1)


@router.get("/trial/one-story")
def one_story(
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
    db: Session = Depends(get_db),
    data: Session = Depends(get_data_plane_db),
):
    """The ten-step story, on the sample and on the trial's own most urgent imported complaint, each step done from
    what was saved on the record; one story for the whole team (backend/app/trial/one_story.py)."""
    from backend.app.trial import one_story as story

    _require_trial(db, ctx)
    tenant_id = uuid.UUID(str(ctx.tenant_id))
    request = team.trial_request(db, tenant_id)
    if request is None:
        return {"sample": None, "yours": None, "flagship": None}
    return story.progress(data, db, ctx, tenant_id, request)


class OneStoryMark(BaseModel):
    run: str = Field(pattern="^(sample|yours|flagship)$")
    # 0.10.93: steps 1 and 2 read the Case's records; the "call" mark is no longer kept. W1: the flagship story's
    # first three steps (signal, product, evidence) are marks too.
    step: str = Field(pattern="^(form|records|trends|signal|product|evidence)$")
    # The complaint the person's screen showed: the story's complaint can move (a new urgent import), and a mark
    # must never land on a complaint the person did not open. For the flagship run, the investigation's id.
    complaint_id: uuid.UUID


@router.post("/trial/one-story/marks")
def mark_one_story(
    payload: OneStoryMark,
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
    db: Session = Depends(get_db),
    data: Session = Depends(get_data_plane_db),
):
    """The person opened a step's screen from the story (the report, Records, Trends): kept on the trial's
    request under their name, and counted for the whole team. No business record changes."""
    from backend.app.trial import flagship
    from backend.app.trial import one_story as story

    _require_trial(db, ctx)
    tenant_id = uuid.UUID(str(ctx.tenant_id))
    index = story.mark_index(payload.run, payload.step)
    if index is None:
        raise HTTPException(422, detail={"code": "NOT_A_STORY_STEP", "message": "This story has no such step to open"})
    request = db.query(OnboardingRequest).filter(OnboardingRequest.tenant_id == tenant_id).with_for_update().first()
    if payload.run == flagship.RUN:
        case = flagship.find_case(data, tenant_id) if request is not None else None
        subject, ref = (case.id, flagship.CASE) if case is not None else (None, None)
    else:
        complaint = story.subject(data, db, tenant_id, payload.run, request) if request is not None else None
        subject, ref = (complaint.id, complaint.complaint_identifier) if complaint is not None else (None, None)
    if request is None or subject is None:
        raise HTTPException(404, detail={"code": "NO_STORY_COMPLAINT", "message": "This story has no complaint yet"})
    if subject != payload.complaint_id:
        raise HTTPException(
            409,
            detail={
                "code": "STORY_MOVED",
                "message": f"The story now follows {ref}. Open Getting started again.",
            },
        )
    # A mark counts only at its place in the story: Records or Trends opened before the steps ahead of it are done is
    # not credited later.
    run = (
        flagship.run_progress(data, db, tenant_id, request)
        if payload.run == flagship.RUN
        else story.run_progress(data, db, ctx, tenant_id, request, payload.run)
    )
    if run["current"] < index:
        raise HTTPException(
            409,
            detail={
                "code": "STEP_NOT_YET",
                "message": f"Step {index + 1} counts once steps 1 to {index} are done; "
                f"step {run['current'] + 1} is next.",
            },
        )
    story.record_mark(request, str(ctx.user_id), payload.run, subject, payload.step, datetime.now(timezone.utc))
    db.commit()
    return story.progress(data, db, ctx, tenant_id, request)


class TrialFocus(BaseModel):
    """What the organization was cited for (backend/app/trial/citations.py codes)."""

    citations: list[str] = Field(default_factory=list, max_length=20)


@router.get("/trial/focus")
def trial_focus(ctx: AuthenticatedRequestContext = Depends(get_request_context), db: Session = Depends(get_db)):
    """The themes offered, and those the organization said it was cited for."""
    from backend.app.trial import citations

    _require_trial(db, ctx)
    request = team.trial_request(db, uuid.UUID(str(ctx.tenant_id)))
    chosen = citations.clean((request.profile or {}).get("citations") if request else ())
    return {"citations": chosen, "options": citations.options()}


@router.put("/trial/focus")
def set_trial_focus(
    payload: TrialFocus,
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
    db: Session = Depends(get_db),
):
    """Record what the organization was cited for: the story marks those chapters and starts with them. Any person
    of the trial may set it; audited."""
    from backend.app.enterprise_audit import make_audit_event
    from backend.app.trial import citations

    _require_trial(db, ctx)
    tenant_id = uuid.UUID(str(ctx.tenant_id))
    unknown = [code for code in payload.citations if code not in citations.CITATIONS]
    if unknown:
        raise HTTPException(422, detail={"code": "TRIAL_FOCUS_UNKNOWN", "message": "Choose from the listed themes"})
    request = team.trial_request(db, tenant_id)
    if request is None:
        raise HTTPException(
            404, detail={"code": "NOT_A_TRIAL_WORKSPACE", "message": "This workspace is not on the free trial"}
        )
    chosen = citations.clean(payload.citations)
    request.profile = {**(request.profile or {}), "citations": chosen}
    db.add(
        make_audit_event(
            tenant_id=tenant_id,
            actor_ref=str(_current_user(db, ctx).id),
            action="TRIAL_FOCUS_SET",
            entity_type="OnboardingRequest",
            entity_id=request.id,
            details={"citations": chosen},
            correlation_id=ctx.correlation_id,
        )
    )
    db.commit()
    return {"citations": chosen, "options": citations.options()}


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
    request_row = team.trial_request(db, tenant_id)
    reached = story.progress(data, tenant_id, story.remembered(request_row.profile if request_row else None))
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
                f"{context['days_left']} day{'' if context['days_left'] == 1 else 's'} left"
                + (", own data uploaded" if context["own_data"] else ""),
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


# ------------------------------------------------------------------------------------------- The MVP conversation


class TrialMvpAsk(BaseModel):
    """A request for an MVP conversation (Next steps): what the MVP should do, what is in scope, how to reach the
    person, and whether to move the trial data into the MVP (allowed only once the sample is removed and own data is
    in; backend/app/trial/mvp_request.py)."""

    expectations: str = Field(default="", max_length=2000)
    scope: str | None = Field(default=None, max_length=2000)
    phone: str | None = Field(default=None, max_length=30)
    contact_preference: str | None = Field(default=None, max_length=200)
    move_trial_data: bool = False


class TrialMvpStatusChange(BaseModel):
    status: str = Field(min_length=3, max_length=40)
    note: str | None = Field(default=None, max_length=500)


@router.get("/trial/mvp-request")
def trial_mvp_request_status(
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
    db: Session = Depends(get_db),
    data: Session = Depends(get_data_plane_db),
):
    """The organization's latest MVP request, or null, and whether it may ask to move its trial data into the MVP."""
    from backend.app.trial import mvp_request

    _require_trial(db, ctx)
    tenant_id = uuid.UUID(str(ctx.tenant_id))
    return {
        "request": mvp_request.view(mvp_request.latest(db, tenant_id)),
        "data_move": mvp_request.data_move(data, tenant_id),
    }


@router.post("/trial/mvp-request")
def ask_for_an_mvp(
    payload: TrialMvpAsk,
    background: BackgroundTasks,
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
    db: Session = Depends(get_db),
    data: Session = Depends(get_data_plane_db),
):
    """Ask for an MVP conversation from inside the trial, or update the organization's open request. The MDARIX team
    gets it in Platform Admin (Identity & Access > Onboarding) and by email."""
    import os

    from backend.app.trial import mvp_request

    subscription = _require_trial(db, ctx)
    tenant_id = uuid.UUID(str(ctx.tenant_id))
    user = _current_user(db, ctx)
    seconds_left = (subscription.expires_at - datetime.now(timezone.utc)).total_seconds()
    days_left = max(0, int(-(-seconds_left // 86400)))
    row, outcome = mvp_request.submit(
        db,
        data,
        tenant_id,
        user,
        expectations=payload.expectations,
        scope=payload.scope,
        phone=payload.phone,
        contact_preference=payload.contact_preference,
        move_trial_data=payload.move_trial_data,
        days_left=days_left,
    )
    recipient = (os.getenv("MDARIX_DEMO_ALERT_EMAIL") or os.getenv("MDARIX_TRIAL_ALERT_EMAIL") or "").strip()
    if recipient:
        background.add_task(
            _alert_mvp_request,
            recipient,
            {
                "display_name": row.display_name,
                "email": row.email,
                "organization": row.organization,
                "expectations": row.expectations,
                "scope": row.scope or "",
                "phone": row.phone or "",
                "contact_preference": row.contact_preference or "",
                "move_trial_data": row.move_trial_data,
                "days_left": days_left,
                "updated": outcome == "UPDATED",
            },
        )
    return {"status": outcome, "request": mvp_request.view(row)}


def _alert_mvp_request(recipient: str, details: dict) -> None:
    """Email the MDARIX team after the response; a failure is only logged (the request is saved)."""
    import logging

    from auth.emailer import send_trial_mvp_request_alert

    try:
        send_trial_mvp_request_alert(recipient, **details)
    except Exception as exc:
        logging.getLogger(__name__).warning("Trial MVP request alert failed: %s", type(exc).__name__)


@router.get("/platform-admin/mvp-requests")
def list_mvp_requests(request: Request, db: Session = Depends(get_db)):
    from backend.app.trial import mvp_request

    _require_platform_admin(request, db)
    return mvp_request.overview(db)


@router.post("/platform-admin/mvp-requests/{request_id}/status")
def change_mvp_request_status(
    request_id: uuid.UUID, payload: TrialMvpStatusChange, request: Request, db: Session = Depends(get_db)
):
    """Mark an MVP request contacted or closed (or new again), with an optional internal note."""
    from backend.app.trial import mvp_request

    admin = _require_platform_admin(request, db)
    row = mvp_request.change_status(db, request_id, admin, payload.status, payload.note)
    return {**(mvp_request.view(row) or {}), "note": row.note}


# ------------------------------------------------------------------------------------------- Ending a trial early


class TrialExitAsk(BaseModel):
    """The owner's request to end the trial early: why (optional) and whether to delete the data."""

    reason_code: str | None = Field(default=None, max_length=40)
    reason: str | None = Field(default=None, max_length=1000)
    delete_data: bool = True


class TrialExitApproval(BaseModel):
    delete_data: bool = True
    note: str | None = Field(default=None, max_length=500)


class TrialExitDecline(BaseModel):
    note: str = Field(default="", max_length=500)


def _send_quietly(send, *args, **kwargs) -> None:
    """Send an email after the response; a failure is only logged (the decision is saved)."""
    import logging

    try:
        send(*args, **kwargs)
    except Exception as exc:
        logging.getLogger(__name__).warning("Trial early-end email failed: %s", type(exc).__name__)


@router.get("/trial/exit-request")
def trial_exit_request_status(
    ctx: AuthenticatedRequestContext = Depends(get_request_context), db: Session = Depends(get_db)
):
    """The trial's latest request to end early, whether the viewer may ask (the owner), and the reasons offered."""
    from backend.app.trial import early_exit

    _require_trial(db, ctx)
    tenant_id = uuid.UUID(str(ctx.tenant_id))
    return {
        "request": early_exit.view(early_exit.latest(db, tenant_id)),
        "is_owner": team.is_trial_owner(db, tenant_id, _current_user(db, ctx)),
        "reasons": early_exit.EXIT_REASONS,
    }


@router.post("/trial/exit-request")
def ask_to_end_trial(
    payload: TrialExitAsk,
    background: BackgroundTasks,
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
    db: Session = Depends(get_db),
):
    """The trial owner asks to end the trial early. The MDARIX team approves or declines it in Platform Admin
    (Customers & Tenants > Trials) and is told by email. A pending request is returned unchanged."""
    import os

    from auth.emailer import send_trial_exit_request_alert
    from backend.app.trial import early_exit

    _require_trial(db, ctx)
    tenant_id = uuid.UUID(str(ctx.tenant_id))
    user = _current_user(db, ctx)
    row, created = early_exit.request_exit(
        db,
        tenant_id,
        user,
        reason_code=payload.reason_code,
        reason=payload.reason,
        delete_data=payload.delete_data,
    )
    recipient = (os.getenv("MDARIX_TRIAL_ALERT_EMAIL") or "").strip()
    if created and recipient:
        label = early_exit.EXIT_REASONS.get(row.reason_code or "")
        why = "; ".join(part for part in (label, row.reason) if part)
        background.add_task(
            _send_quietly,
            send_trial_exit_request_alert,
            recipient,
            organization=row.organization,
            requested_by=f"{user.display_name or user.username} ({user.username})",
            reason=why,
            delete_data=row.delete_data,
            days_left=early_exit.days_left(db, tenant_id),
        )
    return {"status": "REQUESTED" if created else "ALREADY_REQUESTED", "request": early_exit.view(row)}


@router.post("/trial/exit-request/withdraw")
def withdraw_trial_exit(ctx: AuthenticatedRequestContext = Depends(get_request_context), db: Session = Depends(get_db)):
    """The owner withdraws a pending request; the trial continues."""
    from backend.app.trial import early_exit

    _require_trial(db, ctx)
    row = early_exit.withdraw(db, uuid.UUID(str(ctx.tenant_id)), _current_user(db, ctx))
    return {"status": row.status, "request": early_exit.view(row)}


@router.get("/platform-admin/trial-exit-requests")
def list_trial_exit_requests(request: Request, db: Session = Depends(get_db)):
    from backend.app.trial import early_exit

    _require_platform_admin(request, db)
    items = early_exit.overview(db)
    return {"items": items, "pending": sum(1 for item in items if item["status"] == "PENDING")}


@router.post("/platform-admin/trial-exit-requests/{request_id}/approve")
def approve_trial_exit(
    request_id: uuid.UUID,
    payload: TrialExitApproval,
    background: BackgroundTasks,
    request: Request,
    db: Session = Depends(get_db),
):
    """End the trial now and, with ``delete_data``, delete its data at once. The owner is emailed and asked why."""
    from auth.emailer import send_trial_ended_early
    from backend.app.trial import early_exit

    admin = _require_platform_admin(request, db)
    outcome = early_exit.approve(db, request_id, admin, delete_data=payload.delete_data, note=payload.note)
    notify = outcome.pop("notify", None)
    if notify:
        background.add_task(
            _send_quietly, send_trial_ended_early, notify["recipient"], notify["organization"], data_deleted=True
        )
    return outcome


@router.post("/platform-admin/trial-exit-requests/{request_id}/delete-data")
def delete_ended_trial_data(
    request_id: uuid.UUID, background: BackgroundTasks, request: Request, db: Session = Depends(get_db)
):
    """Delete the data of a trial ended early whose data was kept, now rather than after 30 days."""
    from auth.emailer import send_trial_ended_early
    from backend.app.trial import early_exit

    admin = _require_platform_admin(request, db)
    outcome = early_exit.delete_data_now(db, request_id, admin)
    notify = outcome.pop("notify", None)
    if notify:
        background.add_task(
            _send_quietly, send_trial_ended_early, notify["recipient"], notify["organization"], data_deleted=True
        )
    return outcome


@router.post("/platform-admin/trial-exit-requests/{request_id}/decline")
def decline_trial_exit(
    request_id: uuid.UUID,
    payload: TrialExitDecline,
    background: BackgroundTasks,
    request: Request,
    db: Session = Depends(get_db),
):
    """Keep the trial running; the note is emailed to the owner and shown in Getting started."""
    from auth.emailer import send_trial_exit_declined
    from backend.app.trial import early_exit

    admin = _require_platform_admin(request, db)
    outcome = early_exit.decline(db, request_id, admin, note=payload.note)
    notify = outcome.pop("notify", None)
    if notify:
        background.add_task(
            _send_quietly, send_trial_exit_declined, notify["recipient"], notify["organization"], note=notify["note"]
        )
    return outcome


@router.get("/platform-admin/trials")
def platform_trial_overview(
    request: Request,
    page: int = 1,
    page_size: int = 50,
    sort: str = "",
    order: str = "",
    state: str = "",
    q: str = "",
    db: Session = Depends(get_db),
):
    """Every free trial still holding data: dates, usage, how far into the story it went, and its feedback. The
    figures cover every trial; ``items`` is one page (``page_size`` up to 200) of those in ``state`` (ACTIVE,
    ENDING_SOON or ENDED) matching ``q`` (name, tenant key, MDARIX ID or owner's email), sorted by ``sort``/``order``
    or, by default, with the trials that need attention first."""
    from backend.app.trial import story

    _require_platform_admin(request, db)
    if state.strip() and state.strip().upper() not in story.OVERVIEW_STATES:
        raise HTTPException(
            422,
            detail={"code": "INVALID_TRIAL_STATE", "message": "state is ACTIVE, ENDING_SOON or ENDED"},
        )
    return story.trial_overview(db, page=page, page_size=page_size, sort=sort, order=order, state=state, q=q)


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
    return team.invite_colleague(
        db, tenant_id, _current_user(db, ctx), payload.email, payload.display_name, payload.persona, payload.personas
    )


@router.post("/trial/team/{user_id}/persona")
def change_trial_colleague_persona(
    user_id: uuid.UUID,
    payload: ColleaguePersona,
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
    db: Session = Depends(get_db),
):
    """The trial owner gives a colleague another persona, and with it the persona's role (backend/app/trial/team.py)."""
    _require_trial(db, ctx)
    tenant_id = uuid.UUID(str(ctx.tenant_id))
    return team.change_colleague_persona(
        db, tenant_id, _current_user(db, ctx), user_id, payload.persona, payload.personas
    )


@router.post("/trial/team/{user_id}/resend-invitation")
def resend_trial_colleague_invitation(
    user_id: uuid.UUID,
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
    db: Session = Depends(get_db),
):
    _require_trial(db, ctx)
    return team.resend_colleague_invitation(db, uuid.UUID(str(ctx.tenant_id)), _current_user(db, ctx), user_id)


@router.post("/trial/team/{user_id}/remove")
def remove_trial_colleague(
    user_id: uuid.UUID,
    request: Request,
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
    db: Session = Depends(get_db),
):
    """The trial owner takes a colleague off the trial (or withdraws an invitation): the seat is free again, the
    account can no longer sign in, and what they did stays (backend/app/trial/team.py). The colleague, the owner and
    the MDARIX team are emailed through the outbox (backend/app/team_notices.py)."""
    _require_trial(db, ctx)
    return team.remove_colleague(db, uuid.UUID(str(ctx.tenant_id)), _current_user(db, ctx), user_id, request)


class ColleagueMfaReset(BaseModel):
    # Why the authenticator is being removed; kept in the audit trail (as MfaResetRequest).
    reason: str = Field(min_length=5, max_length=500)


@router.post("/trial/team/{user_id}/mfa-reset")
def reset_trial_colleague_mfa(
    user_id: uuid.UUID,
    payload: ColleagueMfaReset,
    request: Request,
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
    db: Session = Depends(get_db),
):
    """The trial owner resets the MFA of a colleague who lost their authenticator and recovery codes. The colleague,
    the owner and the MDARIX team are emailed through the outbox (without the reason, which stays in the audit)."""
    _require_trial(db, ctx)
    tenant_id = uuid.UUID(str(ctx.tenant_id))
    return team.reset_colleague_mfa(db, tenant_id, _current_user(db, ctx), user_id, payload.reason, request)


# ------------------------------------------------------------------------------------------- Support access
# A trial has no Customer Administrators: its owner decides on the support access MDARIX asks for, with the same
# functions and rules as a customer's administrators (backend/app/support_access_api.py).


def _trial_owner(db: Session, ctx: AuthenticatedRequestContext) -> AuthUser:
    _require_trial(db, ctx)
    user = _current_user(db, ctx)
    team.require_owner(
        db, uuid.UUID(str(ctx.tenant_id)), user, "Only the person who started this trial decides on support access"
    )
    return user


@router.get("/trial/support-access")
def trial_support_access(
    ctx: AuthenticatedRequestContext = Depends(get_request_context), db: Session = Depends(get_db)
):
    """Every request MDARIX approved on its side for this trial, newest first, and how many waits for a decision."""
    _trial_owner(db, ctx)
    return support_access_api.grants_of(db, uuid.UUID(str(ctx.tenant_id)))


@router.post("/trial/support-access/{grant_id}/approve")
def approve_trial_support_access(
    grant_id: uuid.UUID,
    payload: support_access_api.CustomerApproval,
    request: Request,
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
    db: Session = Depends(get_db),
):
    """Approve with a current authenticator code; audited as SUPPORT_ACCESS_CUSTOMER_APPROVED."""
    owner = _trial_owner(db, ctx)
    return support_access_api.approve_grant(db, owner, grant_id, payload.reason, payload.mfa_code, request, team.SOURCE)


@router.post("/trial/support-access/{grant_id}/deny")
def deny_trial_support_access(
    grant_id: uuid.UUID,
    payload: support_access_api.CustomerDecision,
    request: Request,
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
    db: Session = Depends(get_db),
):
    owner = _trial_owner(db, ctx)
    return support_access_api.deny_grant(db, owner, grant_id, payload.reason, request, team.SOURCE)


@router.post("/trial/support-access/{grant_id}/revoke")
def revoke_trial_support_access(
    grant_id: uuid.UUID,
    payload: support_access_api.CustomerDecision,
    request: Request,
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
    db: Session = Depends(get_db),
):
    """End a request or an approved access at once."""
    owner = _trial_owner(db, ctx)
    return support_access_api.revoke_grant(db, owner, grant_id, payload.reason, request, team.SOURCE)


@router.get("/trial/support-access/{grant_id}/activity")
def trial_support_access_activity(
    grant_id: uuid.UUID,
    ctx: AuthenticatedRequestContext = Depends(get_request_context),
    db: Session = Depends(get_db),
):
    """The life of one request in the trial's own audit trail: who asked, the owner's decision, every page MDARIX
    support read and every export, and how it ended."""
    owner = _trial_owner(db, ctx)
    return support_access_api.grant_activity(db, owner, grant_id)


# ------------------------------------------------------------------------------------------- Data retention


def _retention_fields(plan: dict) -> dict:
    """The status's deletion date and hold (no date under a legal hold)."""
    return {
        "data_deleted_at": plan["earliest_deletion"].isoformat() if plan["earliest_deletion"] else None,
        "data_hold": plan["hold"],
        "data_hold_reason": retention.HOLD_REASONS.get(plan["hold"]),
    }


@router.get("/platform-admin/trial-retention")
def trial_retention_preview(request: Request, db: Session = Depends(get_db)):
    _require_platform_admin(request, db)
    return {
        "retention_days": retention.RETENTION_DAYS,
        # A request to move the trial data into the MVP holds it (backend/app/trial/retention.py).
        "mvp_hold": {
            "max_days": retention.MVP_HOLD_MAX_DAYS,
            "grace_days": retention.MVP_HOLD_GRACE_DAYS,
            "alert_days": retention.MVP_HOLD_ALERT_DAYS,
        },
        "due": retention.trials_due(db),
    }


@router.post("/platform-admin/trial-retention/run")
def run_trial_retention(request: Request, db: Session = Depends(get_db)):
    admin = _require_platform_admin(request, db)
    return retention.run_retention(db, str(admin.id))
