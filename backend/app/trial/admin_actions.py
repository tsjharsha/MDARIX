"""Trial organizations for the Platform Administrator (TO-1): the figures, the list, one trial's details and the
actions on it (extend, end early, convert, delete data now).

The routes are in backend/app/access/platform_trials.py; every one checks the Platform Administrator first, and the
acting person always comes from the signed-in session. The trial is the path's tenant, re-checked here to be a trial
organization (backend/app/trial/scope.py). Each action writes its events in the trial's own audit trail; a refusal by
a Platform Administrator is audited ``TRIAL_ACTION_REFUSED`` with its code (TO-D10).

Rules (spec TO-1, owner approval 14 Nov 2026):
- **Extend** (TO-D2): 1 to 30 days at a time, with a reason; the latest end is the original end + 30 days, where the
  original end is the subscription's creation + ``TRIAL_DAYS``. A trial that ended normally can be reopened while its
  data is kept; never after an early end, deletion or conversion, nor while an exit request is pending.
- **End early** (TO-D3): MDARIX raises an exit request "Ended by MDARIX" and approves it in the same confirmed step;
  the data is kept for the usual 30 days and the owner is emailed. A pending owner request is decided in its own flow.
- **Convert** (TO-D4): to any active plan except Free Trial, through the shared subscription change; the kind (pilot
  or paid) is kept in the audit event and as the customer type.
- **Delete data now** (TO-D5): only when the retention rules say the trial is due, with the organization's name typed.
"""

from __future__ import annotations

import math
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.app.db.models.customer_lifecycle import Customer
from backend.app.db.models.foundation import AuditEvent, AuthUser, PlanDefinition, Tenant, TenantPlanAssignment
from backend.app.db.models.stage2 import OnboardingRequest, SubscriptionLifecycle, TrialExitRequest
from backend.app.enterprise_audit import make_audit_event
from backend.app.trial import early_exit, scope
from backend.app.trial.service import FREE_TRIAL_PLAN, TRIAL_DAYS, long_moment

EXTENSION_DAYS_MAX = 30
REASON_MIN = 10
ENDING_SOON_DAYS = 7
ENDED_BY_MDARIX = "ENDED_BY_MDARIX"
CONVERT_KINDS = {"PILOT": "PILOT", "PAID": "CUSTOMER"}
# The states the list filters by. ACTIVE, ENDING_SOON and ENDED come from the trials overview (story.py).
LIST_STATES = ("ACTIVE", "ENDING_SOON", "ENDED", "ENDED_EARLY", "DATA_DELETED", "CONVERTED")
GONE_STATUSES = ("ARCHIVED", "PURGING")
AI_LINE = "AI is off for free trials (trial terms)."


class TrialRefused(HTTPException):
    """A refusal with a code and one plain sentence; the route audits it as ``TRIAL_ACTION_REFUSED``."""

    def __init__(self, status: int, code: str, message: str, **extra):
        super().__init__(status, detail={"code": code, "message": message, **extra})
        self.code = code


def _days(seconds: float) -> int:
    return max(0, math.ceil(seconds / 86400))


# --------------------------------------------------------------------------------------------- the trial and its end


def subscription_of(db: Session, tenant_id: uuid.UUID) -> SubscriptionLifecycle | None:
    from backend.app.trial.service import trial_subscription

    return trial_subscription(db, tenant_id)


def original_end(subscription: SubscriptionLifecycle) -> datetime:
    """The end the trial was approved with: its subscription's creation (which never changes) + ``TRIAL_DAYS``."""
    return subscription.created_at + timedelta(days=TRIAL_DAYS)


def latest_end(subscription: SubscriptionLifecycle) -> datetime:
    return original_end(subscription) + timedelta(days=EXTENSION_DAYS_MAX)


def extension_used(subscription: SubscriptionLifecycle) -> int:
    """Whole days the trial runs past its original end (0 when it ends on or before it)."""
    return _days((subscription.expires_at - original_end(subscription)).total_seconds())


def extension_left(subscription: SubscriptionLifecycle) -> int:
    return max(0, math.floor((latest_end(subscription) - subscription.expires_at).total_seconds() / 86400))


def check_trial_end(subscription: SubscriptionLifecycle, starts_at: datetime, expires_at: datetime, grace) -> None:
    """The cap every route that changes a trial's subscription applies (the trial page and Plans & Licensing ›
    Subscriptions): the start never moves, and neither the end nor a grace end goes past original end + 30 days.
    A moment without a time zone is read as UTC. A screen that sends only the start's date (midnight) is accepted: the
    start is refused only when it moves by a day or more."""

    def aware(moment):
        return moment.replace(tzinfo=timezone.utc) if moment is not None and moment.tzinfo is None else moment

    if abs(aware(starts_at) - subscription.starts_at) >= timedelta(days=1):
        raise TrialRefused(
            409, "TRIAL_START_FIXED", "A free trial's start date cannot be changed; extend its end instead"
        )
    limit = latest_end(subscription)
    for moment in (aware(expires_at), aware(grace)):
        if moment is not None and moment > limit + timedelta(seconds=1):
            left = extension_left(subscription)
            raise TrialRefused(
                409,
                "TRIAL_EXTENSION_LIMIT",
                f"This trial can be extended by {left} more days at most ({EXTENSION_DAYS_MAX} in total)",
                days_left=left,
                latest_end=limit.isoformat(),
            )


def check_trial_change(db: Session, tenant: Tenant, subscription, *, converting: bool, now: datetime) -> None:
    """What the trial page refuses, refused on Plans & Licensing › Subscriptions too: no change after the data was
    deleted or while an exit request is pending; no reopening after an early end (a conversion is allowed then)."""
    if str(tenant.status or "").upper() in GONE_STATUSES:
        raise TrialRefused(409, "TRIAL_DATA_DELETED", "The trial's data has been deleted")
    requests = _exit_requests(db, tenant.id)
    if _pending_exit(requests) is not None:
        raise TrialRefused(409, "TRIAL_EXIT_PENDING", "The trial owner asked to end the trial: decide on that first")
    if not converting and _ended_early(requests) is not None and subscription.expires_at <= now:
        raise TrialRefused(409, "TRIAL_ENDED_EARLY", "A trial ended early cannot be extended")


def _exit_requests(db: Session, tenant_id: uuid.UUID) -> list[TrialExitRequest]:
    return (
        db.query(TrialExitRequest)
        .filter(TrialExitRequest.trial_tenant_id == tenant_id)
        .order_by(TrialExitRequest.created_at.desc())
        .all()
    )


def _ended_early(requests: list[TrialExitRequest]) -> TrialExitRequest | None:
    return next((row for row in requests if row.status == "APPROVED"), None)


def _pending_exit(requests: list[TrialExitRequest]) -> TrialExitRequest | None:
    return next((row for row in requests if row.status == early_exit.PENDING), None)


def _tenant(db: Session, tenant_id: uuid.UUID) -> Tenant:
    tenant = db.get(Tenant, tenant_id)
    if tenant is None:
        raise HTTPException(404, detail={"code": "NOT_A_TRIAL", "message": "This organization is not a free trial"})
    return tenant


def require_trial(db: Session, tenant_id: uuid.UUID, *, lock: bool = False) -> tuple[Tenant, SubscriptionLifecycle]:
    """The trial organization in the path and its subscription (row-locked with ``lock``). A converted trial is
    refused ``TRIAL_ALREADY_CONVERTED``; any other tenant is not found (``NOT_A_TRIAL``)."""
    tenant = _tenant(db, tenant_id)
    if not scope.is_trial(db, tenant_id):
        if scope.was_trial(db, tenant_id):
            raise TrialRefused(409, "TRIAL_ALREADY_CONVERTED", "This trial has been converted: it is a customer now")
        raise HTTPException(404, detail={"code": "NOT_A_TRIAL", "message": "This organization is not a free trial"})
    query = db.query(SubscriptionLifecycle).filter(SubscriptionLifecycle.id == subscription_of(db, tenant_id).id)
    subscription = (query.with_for_update() if lock else query).one()
    return tenant, subscription


def _reason(text: str | None) -> str:
    cleaned = " ".join((text or "").split())
    if len(cleaned) < REASON_MIN:
        raise TrialRefused(422, "TRIAL_REASON_REQUIRED", f"Give a reason of {REASON_MIN} characters or more")
    return cleaned[:1000]


def audit_refusal(db: Session, tenant_id: uuid.UUID, admin: AuthUser, action: str, refusal: TrialRefused) -> None:
    """A refused action by a Platform Administrator, in the trial's own trail (TO-D10). Commits."""
    db.rollback()
    if db.get(Tenant, tenant_id) is None:
        return
    db.add(
        make_audit_event(
            tenant_id=tenant_id,
            actor_ref=str(admin.id),
            action="TRIAL_ACTION_REFUSED",
            entity_type="Tenant",
            entity_id=tenant_id,
            details={"attempted": action, "code": refusal.code},
        )
    )
    db.commit()


def _audit(db: Session, tenant_id, admin: AuthUser, action: str, *, reason=None, details=None, old=None, new=None):
    db.add(
        make_audit_event(
            tenant_id=tenant_id,
            actor_ref=str(admin.id),
            action=action,
            entity_type="Tenant",
            entity_id=tenant_id,
            reason=reason,
            details=details or {},
            old_values=old,
            new_values=new,
        )
    )


# --------------------------------------------------------------------------------------------- figures and state


def summary(db: Session, now: datetime | None = None) -> dict:
    """The header strip and the dashboard's Free trials tile, one statement per figure."""
    now = now or datetime.now(timezone.utc)
    trials = scope.trial_tenant_ids()
    live = (
        db.query(SubscriptionLifecycle.tenant_id)
        .join(PlanDefinition, PlanDefinition.id == SubscriptionLifecycle.plan_id)
        .join(Tenant, Tenant.id == SubscriptionLifecycle.tenant_id)
        .filter(
            PlanDefinition.code == FREE_TRIAL_PLAN,
            SubscriptionLifecycle.tenant_id.in_(trials),
            Tenant.status.notin_(GONE_STATUSES),
        )
    )
    active = live.filter(SubscriptionLifecycle.expires_at > now).distinct().count()
    ending = (
        live.filter(
            SubscriptionLifecycle.expires_at > now,
            SubscriptionLifecycle.expires_at <= now + timedelta(days=ENDING_SOON_DAYS),
        )
        .distinct()
        .count()
    )
    ended_kept = live.filter(SubscriptionLifecycle.expires_at <= now).distinct().count()
    waiting = db.query(func.count(OnboardingRequest.id)).filter(OnboardingRequest.status == "PENDING_REVIEW").scalar()
    exits = (
        db.query(func.count(TrialExitRequest.id)).filter(TrialExitRequest.status == early_exit.PENDING).scalar() or 0
    )
    month = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    converted = (
        db.query(func.count(func.distinct(TenantPlanAssignment.tenant_id)))
        .join(PlanDefinition, PlanDefinition.id == TenantPlanAssignment.plan_id)
        .filter(
            PlanDefinition.code == FREE_TRIAL_PLAN,
            TenantPlanAssignment.status == "SUPERSEDED",
            TenantPlanAssignment.effective_to >= month,
            TenantPlanAssignment.tenant_id.in_(scope.converted_tenant_ids()),
        )
        .scalar()
        or 0
    )
    return {
        "waiting_for_review": int(waiting or 0),
        "active": active,
        "ending_soon": ending,
        "ended_data_kept": ended_kept,
        "exit_requests_waiting": int(exits),
        "converted_this_month": int(converted),
    }


def state_of(tenant: Tenant, subscription, requests, converted: bool, now: datetime) -> str:
    if converted:
        return "CONVERTED"
    if str(tenant.status or "").upper() in GONE_STATUSES:
        return "DATA_DELETED"
    if _ended_early(requests) is not None and subscription.expires_at <= now:
        return "ENDED_EARLY"
    if subscription.expires_at <= now:
        return "ENDED"
    if subscription.expires_at - now <= timedelta(days=ENDING_SOON_DAYS):
        return "ENDING_SOON"
    return "ACTIVE"


# --------------------------------------------------------------------------------------------- the list


def _sample_status(db: Session, tenants: list[Tenant]) -> dict:
    """``{tenant id: {status, at}}``: Loaded, Removed by the owner or Restarted (latest event), or Sample only."""
    ids = [tenant.id for tenant in tenants]
    latest: dict = {}
    if ids:
        for tenant_id, action, at in (
            db.query(AuditEvent.tenant_id, AuditEvent.action, AuditEvent.created_at)
            .filter(
                AuditEvent.tenant_id.in_(ids),
                AuditEvent.action.in_(("TRIAL_SAMPLE_REMOVED", "TRIAL_SAMPLE_RESTARTED")),
            )
            .order_by(AuditEvent.created_at)
        ):
            latest[tenant_id] = (action, at)
    found = {}
    for tenant in tenants:
        action, at = latest.get(tenant.id, (None, None))
        status = "REMOVED" if action == "TRIAL_SAMPLE_REMOVED" else "RESTARTED" if action else "LOADED"
        found[tenant.id] = {
            "status": status,
            "at": at.isoformat() if at else None,
            "sample_only": bool(tenant.sample_only),
        }
    return found


def trial_list(db: Session, *, page=1, page_size=50, sort="", order="", state="", q="", now=None) -> dict:
    """The Trials list: the trials overview (running and ended trials still holding data) with the extension used,
    the sample status and an early end; ``ENDED_EARLY`` narrows the ended ones; ``DATA_DELETED`` and ``CONVERTED``
    list those trials (read-only)."""
    from backend.app.trial import story

    now = now or datetime.now(timezone.utc)
    wanted = (state or "").strip().upper()
    if wanted in ("DATA_DELETED", "CONVERTED"):
        return _former_trials(db, wanted, page=page, page_size=page_size, q=q)
    overview_state = "ENDED" if wanted == "ENDED_EARLY" else wanted
    if wanted == "ENDED_EARLY":
        early_ids = {
            row.trial_tenant_id for row in db.query(TrialExitRequest.trial_tenant_id).filter_by(status="APPROVED")
        }
        result = story.trial_overview(db, now, page=1, page_size=story.OVERVIEW_PAGE_SIZE_MAX, state="ENDED", q=q)
        items = [item for item in result["items"] if uuid.UUID(item["tenant_id"]) in early_ids]
        size = min(story.OVERVIEW_PAGE_SIZE_MAX, max(1, int(page_size)))
        result.update(items=items[:size], total=len(items), page=1, pages=1)
    else:
        result = story.trial_overview(
            db, now, page=page, page_size=page_size, sort=sort, order=order, state=overview_state, q=q
        )
    _decorate(db, result["items"], now)
    result["counts"] = summary(db, now)
    return result


def _decorate(db: Session, items: list[dict], now: datetime) -> None:
    """Add the extension used, the sample status and an early end to the overview's rows, in three statements."""
    if not items:
        return
    ids = [uuid.UUID(item["tenant_id"]) for item in items]
    subscriptions = {}
    for row in (
        db.query(SubscriptionLifecycle)
        .join(PlanDefinition, PlanDefinition.id == SubscriptionLifecycle.plan_id)
        .filter(SubscriptionLifecycle.tenant_id.in_(ids), PlanDefinition.code == FREE_TRIAL_PLAN)
        .order_by(SubscriptionLifecycle.created_at)
    ):
        subscriptions[row.tenant_id] = row
    tenants = db.query(Tenant).filter(Tenant.id.in_(ids)).all()
    samples = _sample_status(db, tenants)
    early = {
        row.trial_tenant_id
        for row in db.query(TrialExitRequest.trial_tenant_id).filter(
            TrialExitRequest.trial_tenant_id.in_(ids), TrialExitRequest.status == "APPROVED"
        )
    }
    for item, tenant_id in zip(items, ids):
        subscription = subscriptions.get(tenant_id)
        if subscription is not None:
            item["original_ends_at"] = original_end(subscription).isoformat()
            item["extension"] = {"used": extension_used(subscription), "max": EXTENSION_DAYS_MAX}
        item["sample"] = samples.get(tenant_id)
        item["ended_early"] = tenant_id in early
        if item["ended_early"] and item["state"] == "ENDED":
            item["state"] = "ENDED_EARLY"


def _former_trials(db: Session, wanted: str, *, page: int, page_size: int, q: str) -> dict:
    """Trials whose data was deleted, or converted ones (read-only rows)."""
    if wanted == "CONVERTED":
        query = db.query(Tenant).filter(Tenant.id.in_(scope.converted_tenant_ids()))
    else:
        query = db.query(Tenant).filter(scope.trial_tenant_clause(Tenant.id), Tenant.status.in_(GONE_STATUSES))
    if q.strip():
        like = f"%{q.strip().lower()}%"
        query = query.filter(
            func.lower(Tenant.name).like(like)
            | func.lower(Tenant.business_id).like(like)
            | func.lower(Tenant.tenant_key).like(like)
        )
    size = min(200, max(1, int(page_size)))
    total = query.count()
    pages = max(1, -(-total // size))
    page = min(max(1, int(page)), pages)
    rows = query.order_by(Tenant.updated_at.desc(), Tenant.id).offset((page - 1) * size).limit(size).all()
    conversions = _conversions(db, [row.id for row in rows]) if wanted == "CONVERTED" else {}
    items = [
        {
            "tenant_id": str(row.id),
            "tenant_business_id": row.business_id,
            "tenant_key": row.tenant_key,
            "name": row.name,
            "state": wanted,
            "conversion": conversions.get(row.id),
            "updated_at": row.updated_at.isoformat() if row.updated_at else None,
        }
        for row in rows
    ]
    return {
        "items": items,
        "attention": [],
        "page": page,
        "page_size": size,
        "total": total,
        "pages": pages,
        "counts": summary(db),
    }


def _conversions(db: Session, tenant_ids: list) -> dict:
    """``{tenant id: {kind, plan_code, at, by}}`` from each converted trial's latest ``TRIAL_CONVERTED`` event, or the
    plan change when it was converted on Plans & Licensing."""
    found: dict = {}
    if not tenant_ids:
        return found
    for event in (
        db.query(AuditEvent)
        .filter(
            AuditEvent.tenant_id.in_(tenant_ids),
            AuditEvent.action.in_(("TRIAL_CONVERTED", "SUBSCRIPTION_CHANGED")),
        )
        .order_by(AuditEvent.created_at)
    ):
        details = event.details or {}
        if event.action == "SUBSCRIPTION_CHANGED" and details.get("previous_plan_code") != FREE_TRIAL_PLAN:
            continue
        current = found.get(event.tenant_id)
        if current is not None and current.get("kind") and event.action != "TRIAL_CONVERTED":
            continue
        found[event.tenant_id] = {
            "kind": details.get("kind"),
            "plan_code": details.get("plan_code"),
            "at": event.created_at.isoformat() if event.created_at else None,
            "by": event.actor_ref,
        }
    return found


# --------------------------------------------------------------------------------------------- one trial


def detail(db: Session, tenant_id: uuid.UUID, now: datetime | None = None) -> dict:
    """Everything about one trial (or a converted one, read-only): dates, people, sample data, activity, the exit
    request, what can be done now (with the reason when not) and the AI line."""
    from backend.app.db.tenant_scope import bind_system
    from backend.app.trial import retention, story
    from backend.app.trial.router import _data_counts
    from backend.app.trial.team import trial_request

    now = now or datetime.now(timezone.utc)
    tenant = _tenant(db, tenant_id)
    converted = scope.is_converted(db, tenant_id)
    if not converted and not scope.is_trial(db, tenant_id):
        raise HTTPException(404, detail={"code": "NOT_A_TRIAL", "message": "This organization is not a free trial"})
    requests = _exit_requests(db, tenant_id)
    subscription = (
        subscription_of(db, tenant_id)
        if not converted
        else db.query(SubscriptionLifecycle)
        .filter(SubscriptionLifecycle.tenant_id == tenant_id)
        .order_by(SubscriptionLifecycle.created_at.desc())
        .first()
    )
    state = state_of(tenant, subscription, requests, converted, now)
    request = trial_request(db, tenant_id)
    seats, owner, people = story._people_by_tenant(db, [tenant_id]).get(tenant_id, (0, None, []))
    gone = state == "DATA_DELETED"
    with Session(bind=db.get_bind(), autoflush=False) as data:
        bind_system(data, "platform administrator: trial detail")
        counts = story.acted_counts_by_tenant(data, [tenant_id]).get(tenant_id) or dict.fromkeys(story.CODES, 0)
        moment = story.last_activity_by_tenant(data, [tenant_id]).get(tenant_id)
        sample, own, uploaded = ({}, {}, 0) if gone else _data_counts(data, tenant_id)
    reached = story._reached(counts, story.remembered(request.profile if request else None), moment)
    deletion = None
    if not converted and not gone and subscription.expires_at <= now:
        deletion = retention.plan_view(retention.projection(db, db, subscription, now))
    dates = {
        "starts_at": subscription.starts_at.isoformat() if subscription and subscription.starts_at else None,
        "ends_at": subscription.expires_at.isoformat() if subscription else None,
        "ends_words": long_moment(subscription.expires_at) if subscription else None,
        "days_left": _days((subscription.expires_at - now).total_seconds()) if subscription else 0,
    }
    if not converted and subscription is not None:
        dates.update(
            original_ends_at=original_end(subscription).isoformat(),
            latest_end=latest_end(subscription).isoformat(),
            extension_used=extension_used(subscription),
            extension_left=extension_left(subscription),
            extension_max=EXTENSION_DAYS_MAX,
            deletion=deletion,
        )
    feedback = story._feedback_by_tenant(db, [tenant_id]).get(tenant_id)
    demo = story._demos_by_tenant(db, [tenant_id]).get(tenant_id)
    pending = _pending_exit(requests)
    return {
        "tenant_id": str(tenant.id),
        "tenant_business_id": tenant.business_id,
        "tenant_key": tenant.tenant_key,
        "name": tenant.name,
        "status": tenant.status,
        "state": state,
        "legal_hold": bool(tenant.legal_hold),
        "plan": "Free Trial" if not converted else None,
        "dates": dates,
        "people": {
            "used": seats,
            "owner": owner,
            "people": people,
            "request_email": request.email if request else None,
        },
        "sample": {
            **_sample_status(db, [tenant])[tenant.id],
            "sample_counts": sample,
            "own_counts": own,
            "uploaded_rows": uploaded,
        },
        "activity": {"story": reached, "feedback": feedback, "demo_request": demo},
        "exit_request": early_exit.view(pending or (requests[0] if requests else None)),
        "conversion": _conversions(db, [tenant_id]).get(tenant_id) if converted else None,
        "next_step": _next_step(state, dates, reached, pending),
        "actions": actions_allowed(db, tenant, subscription, requests, state, now),
        "ai": {"enabled": False, "line": AI_LINE},
    }


def _next_step(state: str, dates: dict, reached: dict, pending) -> str:
    if state == "CONVERTED":
        return "Converted: this organization is a customer now. Open it in Customers."
    if state == "DATA_DELETED":
        return "The trial's data has been deleted. Nothing more to do."
    if pending is not None:
        return "The trial owner asked to end the trial early: decide on the request."
    if state in ("ENDED", "ENDED_EARLY"):
        return "The trial has ended and its data is kept for 30 days: offer a pilot or let it close."
    acted = reached.get("acted_count", 0)
    days = dates.get("days_left", 0)
    if state == "ENDING_SOON" and acted < 4:
        return f"Ends in {days} days and has tried {acted} of the chapters: offer a demo."
    if acted == 0:
        return "Has not acted in the workspace yet: send a welcome note or offer a walk-through."
    return "Running well: keep in touch and offer a pilot near the end."


def actions_allowed(db: Session, tenant, subscription, requests, state: str, now: datetime) -> dict:
    """Which actions the server would accept now, each with the reason when not (the screen shows one or the other)."""

    def allowed(reason: str | None) -> dict:
        return {"allowed": reason is None, "reason": reason}

    if state == "CONVERTED":
        closed = "This trial has been converted: it is a customer now"
        return {name: allowed(closed) for name in ("extend", "end", "convert", "delete_data")}
    if state == "DATA_DELETED":
        gone = "The trial's data has been deleted"
        return {name: allowed(gone) for name in ("extend", "end", "convert", "delete_data")}
    pending = _pending_exit(requests)
    early = _ended_early(requests)
    extend = None
    if pending is not None:
        extend = "The trial owner asked to end the trial: decide on that request first"
    elif early is not None and subscription.expires_at <= now:
        extend = "A trial ended early cannot be extended"
    elif extension_left(subscription) < 1:
        extend = f"All {EXTENSION_DAYS_MAX} extension days have been used"
    end = None
    if subscription.expires_at <= now:
        end = "The trial has already ended"
    convert = "The trial owner asked to end the trial: decide on that request first" if pending is not None else None
    from backend.app.trial import retention

    due = retention._due(retention.plans(db, now, [tenant.id]), now)
    delete = None
    if not due:
        delete = "Not due yet: the data is deleted 30 days after the trial ends"
    elif due[0]["legal_hold"]:
        delete = "Under a legal hold: nothing is deleted until the hold is lifted"
    elif due[0].get("held_for_mvp_request"):
        delete = "Kept while a request to move the data into the pilot is open"
    return {
        "extend": {**allowed(extend), "days_left": extension_left(subscription)},
        "end": {**allowed(end), "pending_request_id": str(pending.id) if pending is not None else None},
        "convert": allowed(convert),
        "delete_data": allowed(delete),
    }


# --------------------------------------------------------------------------------------------- actions


def extend(db: Session, tenant_id: uuid.UUID, admin: AuthUser, *, days: int, reason: str, now=None) -> dict:
    """Move the trial's end by ``days`` (1 to 30), up to its original end + 30 days. Commits."""
    now = now or datetime.now(timezone.utc)
    reason = _reason(reason)
    if not 1 <= int(days) <= EXTENSION_DAYS_MAX:
        raise TrialRefused(422, "TRIAL_EXTENSION_DAYS", f"Extend by 1 to {EXTENSION_DAYS_MAX} days at a time")
    tenant, subscription = require_trial(db, tenant_id, lock=True)
    if str(tenant.status or "").upper() in GONE_STATUSES:
        raise TrialRefused(409, "TRIAL_DATA_DELETED", "The trial's data has been deleted: it cannot be extended")
    requests = _exit_requests(db, tenant_id)
    if _pending_exit(requests) is not None:
        raise TrialRefused(409, "TRIAL_EXIT_PENDING", "The trial owner asked to end the trial: decide on that first")
    if _ended_early(requests) is not None and subscription.expires_at <= now:
        raise TrialRefused(409, "TRIAL_ENDED_EARLY", "A trial ended early cannot be extended")
    old_end = subscription.expires_at
    new_end = old_end + timedelta(days=int(days))
    check_trial_end(subscription, subscription.starts_at, new_end, None)
    if new_end <= now:
        raise TrialRefused(
            409, "TRIAL_EXTENSION_TOO_SHORT", "The new end would still be in the past: extend by more days"
        )
    reopened = subscription.expires_at <= now
    subscription.expires_at = new_end
    subscription.grace_ends_at = None
    subscription.status = "ACTIVE"
    subscription.expiry_version += 1
    subscription.updated_at = now
    if reopened and str(tenant.status or "").upper() == "SUSPENDED":
        tenant.status, tenant.updated_at = "ACTIVE", now
    used = extension_used(subscription)
    _audit(
        db,
        tenant_id,
        admin,
        "TRIAL_EXTENDED",
        reason=reason,
        details={"days": int(days), "total_used": used, "reopened": reopened, "reason": reason},
        old={"expires_at": old_end.isoformat()},
        new={"expires_at": new_end.isoformat()},
    )
    db.commit()
    return {
        "tenant_id": str(tenant_id),
        "ends_at": new_end.isoformat(),
        "ends_words": long_moment(new_end),
        "extension_used": used,
        "extension_left": extension_left(subscription),
        "reopened": reopened,
    }


def end_early(db: Session, tenant_id: uuid.UUID, admin: AuthUser, *, reason: str, now=None) -> dict:
    """MDARIX ends the trial now (TO-D3): an exit request "Ended by MDARIX" raised and approved in one step; the data
    is kept for the usual 30 days and the owner is emailed. With a pending owner request, that request is decided in
    its own flow instead (``TRIAL_EXIT_PENDING`` names it). Commits."""
    now = now or datetime.now(timezone.utc)
    reason = _reason(reason)
    tenant, subscription = require_trial(db, tenant_id, lock=True)
    if str(tenant.status or "").upper() in GONE_STATUSES:
        raise TrialRefused(409, "TRIAL_DATA_DELETED", "The trial's data has been deleted")
    pending = _pending_exit(_exit_requests(db, tenant_id))
    if pending is not None:
        raise TrialRefused(
            409,
            "TRIAL_EXIT_PENDING",
            "The trial owner has already asked to end the trial: approve or decline that request",
            request_id=str(pending.id),
        )
    if subscription.expires_at <= now:
        raise TrialRefused(409, "TRIAL_ALREADY_ENDED", "The trial has already ended")
    row = TrialExitRequest(
        id=uuid.uuid4(),
        trial_tenant_id=tenant_id,
        organization=(tenant.name or "Trial organization")[:160],
        requested_by=admin.id,
        reason_code=ENDED_BY_MDARIX,
        reason=reason,
        delete_data=False,
        status=early_exit.PENDING,
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    _audit(
        db,
        tenant_id,
        admin,
        "TRIAL_EXIT_RAISED_BY_MDARIX",
        reason=reason,
        details={"trial_exit_request": str(row.id), "reason": reason},
    )
    db.flush()
    outcome = early_exit.approve(db, row.id, admin, delete_data=False, note=reason, now=now)
    return {**outcome, "tenant_id": str(tenant_id)}


def convert(
    db: Session,
    tenant_id: uuid.UUID,
    admin: AuthUser,
    *,
    kind: str,
    plan_id: uuid.UUID,
    starts_at: datetime,
    expires_at: datetime,
    reason: str,
    now=None,
) -> dict:
    """Move the trial to a pilot or paid plan through the shared subscription change (plan history kept, owner
    promoted). The organization then leaves the trial lists and appears in the main lists. Commits."""
    from backend.app.access.platform_subscriptions import change_subscription

    now = now or datetime.now(timezone.utc)
    reason = _reason(reason)
    wanted = (kind or "").strip().upper()
    if wanted not in CONVERT_KINDS:
        raise TrialRefused(422, "TRIAL_CONVERT_KIND", "Choose Pilot or Paid")
    tenant, subscription = require_trial(db, tenant_id, lock=True)
    if str(tenant.status or "").upper() in GONE_STATUSES:
        raise TrialRefused(409, "TRIAL_DATA_DELETED", "The trial's data has been deleted: it cannot be converted")
    if _pending_exit(_exit_requests(db, tenant_id)) is not None:
        raise TrialRefused(409, "TRIAL_EXIT_PENDING", "The trial owner asked to end the trial: decide on that first")
    plan = db.query(PlanDefinition).filter(PlanDefinition.id == plan_id, PlanDefinition.status == "ACTIVE").first()
    if plan is None:
        raise TrialRefused(404, "SUBSCRIPTION_TARGET_NOT_FOUND", "Choose an active plan")
    if plan.code == FREE_TRIAL_PLAN:
        raise TrialRefused(422, "TRIAL_PLAN_NOT_ASSIGNABLE", "Choose a pilot or paid plan, not the Free Trial")
    if expires_at <= starts_at:
        raise TrialRefused(422, "INVALID_SUBSCRIPTION_WINDOW", "Expiry must be after start")
    outcome = change_subscription(db, tenant, plan, starts_at, expires_at, None, reason, admin, now)
    customer = db.get(Customer, tenant.customer_id)
    previous_type = customer.customer_type if customer is not None else None
    if customer is not None:
        customer.customer_type = CONVERT_KINDS[wanted]
        customer.updated_at = now
    _audit(
        db,
        tenant_id,
        admin,
        "TRIAL_CONVERTED",
        reason=reason,
        details={
            "kind": wanted,
            "plan_code": plan.code,
            "starts_at": starts_at.isoformat(),
            "expires_at": expires_at.isoformat(),
            "reason": reason,
        },
        old={"plan_code": FREE_TRIAL_PLAN, "customer_type": previous_type},
        new={"plan_code": plan.code, "customer_type": CONVERT_KINDS[wanted]},
    )
    db.commit()
    return {**outcome, "kind": wanted}


def delete_data(db: Session, tenant_id: uuid.UUID, admin: AuthUser, *, confirm_name: str, now=None) -> dict:
    """Delete one due trial's data now (TO-D5): only when the retention rules say it is due (ended 30+ days ago, no
    legal hold, no open request to move the data), re-checked just before deleting, with the name typed. Commits."""
    from backend.app.tenant_purge import PurgeFailed
    from backend.app.trial import retention

    now = now or datetime.now(timezone.utc)
    tenant, _subscription = require_trial(db, tenant_id, lock=True)
    if str(tenant.status or "").upper() in GONE_STATUSES:
        raise TrialRefused(409, "TRIAL_DATA_DELETED", "The trial's data has already been deleted")
    typed = " ".join((confirm_name or "").split()).casefold()
    if not typed or typed != " ".join((tenant.name or "").split()).casefold():
        raise TrialRefused(422, "TRIAL_NAME_MISMATCH", "Type the organization's name exactly to confirm")
    due = retention._due(retention.plans(db, now, [tenant_id]), now)
    if not due:
        raise TrialRefused(409, "TRIAL_NOT_DUE", "Not due yet: the data is deleted 30 days after the trial ends")
    if due[0]["legal_hold"]:
        raise TrialRefused(409, "TRIAL_LEGAL_HOLD", "This organization is under a legal hold: nothing is deleted")
    if due[0].get("held_for_mvp_request"):
        raise TrialRefused(
            409, "TRIAL_MOVE_REQUEST_OPEN", "An open request to move the data into the pilot keeps it for now"
        )
    # No commit before the purge: the row lock taken above is held until the purge commits, so a concurrent extend or
    # a second deletion waits and then sees the archived trial.
    try:
        outcome = retention.purge_trial(db, tenant_id, str(admin.id), now)
    except PurgeFailed as exc:
        db.rollback()
        raise TrialRefused(409, "TRIAL_DELETE_FAILED", f"The data could not be deleted ({exc}); nothing was changed")
    _audit(
        db,
        tenant_id,
        admin,
        "TRIAL_DATA_DELETED_BY_ADMIN",
        details={"status": outcome.get("status"), "trial_ended_at": due[0]["trial_ended_at"]},
    )
    db.commit()
    return {"tenant_id": str(tenant_id), **{key: value for key, value in outcome.items() if key != "tenant"}}
