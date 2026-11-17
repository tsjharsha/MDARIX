"""Trial organizations (TO-1): the Platform Administrator's one page for free trials, with the per-user AI switch
(TO-1 spec 3.6.1) and the trial's AI metrics.

Every route checks the Platform Administrator first (``_require_platform_admin``: PLATFORM_ADMIN or
MDARIX_ADMINISTRATOR only). The acting person comes only from the signed-in session; the body carries reasons, days,
plan, dates and ``{active, reason}``, never an actor. The trial is the path's tenant, re-checked to be a trial
organization. The lifecycle work is in backend/app/trial/admin_actions.py.

AI switch: each changed value is audited ``TRIAL_USER_AI_ACCESS_CHANGED`` in the trial's own trail (a bulk change adds
``bulk: true`` and one ``TRIAL_AI_ACCESS_BULK_CHANGED`` summary row); a refused change (not a trial, a user of another
trial, a reason under 10 characters) is audited ``TRIAL_ACTION_REFUSED``. AI for a trial user needs both the
organization switch (the trial's administrator) and this switch; enforcement is in ``genai/governance.py`` on every
model call. New users are Active. Paid organizations are not affected.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.app.access.authz import _require_platform_admin
from backend.app.db.models.foundation import AuthUser, Tenant
from backend.app.db.session import get_db
from backend.app.enterprise_audit import make_audit_event
from backend.app.trial import admin_actions
from genai import governance

router = APIRouter(prefix="/api/v1", tags=["Trial organizations"])

BASE = "/platform-admin/trial-organizations"
MIN_REASON = 10


class ExtendRequest(BaseModel):
    days: int
    reason: str = Field(max_length=1000)


class EndRequest(BaseModel):
    reason: str = Field(max_length=1000)


class ConvertRequest(BaseModel):
    kind: str = Field(max_length=10)
    plan_id: uuid.UUID
    starts_at: str = Field(max_length=40)
    expires_at: str = Field(max_length=40)
    reason: str = Field(max_length=1000)


class DeleteDataRequest(BaseModel):
    confirm_name: str = Field(max_length=200)


def _moment(value: str, field: str) -> datetime:
    try:
        moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise admin_actions.TrialRefused(422, "INVALID_DATE", f"{field} must be an ISO date and time")
    if moment.tzinfo is None:
        raise admin_actions.TrialRefused(422, "INVALID_DATE", f"{field} must carry its time zone")
    return moment


def _audited(db: Session, tenant_id: uuid.UUID, admin, action: str, work):
    """Run ``work``; a refusal is audited ``TRIAL_ACTION_REFUSED`` in the trial's trail, then raised."""
    try:
        return work()
    except admin_actions.TrialRefused as refusal:
        admin_actions.audit_refusal(db, tenant_id, admin, action, refusal)
        raise


@router.get(f"{BASE}/summary")
def trial_organizations_summary(request: Request, db: Session = Depends(get_db)):
    """The header strip: waiting for review, active, ending within 7 days, ended with data kept, exit requests
    waiting, converted this month."""
    _require_platform_admin(request, db)
    return admin_actions.summary(db)


@router.get(BASE)
def trial_organizations(
    request: Request,
    page: int = 1,
    page_size: int = 50,
    sort: str = "",
    order: str = "",
    state: str = "",
    q: str = "",
    db: Session = Depends(get_db),
):
    """The Trials list, one page, filtered on the server by ``state`` (ACTIVE, ENDING_SOON, ENDED, ENDED_EARLY,
    DATA_DELETED, CONVERTED) and ``q``; by default the trials that need attention first."""
    _require_platform_admin(request, db)
    if state.strip() and state.strip().upper() not in admin_actions.LIST_STATES:
        raise HTTPException(
            422,
            detail={
                "code": "INVALID_TRIAL_STATE",
                "message": "state is one of " + ", ".join(admin_actions.LIST_STATES),
            },
        )
    return admin_actions.trial_list(db, page=page, page_size=page_size, sort=sort, order=order, state=state, q=q)


@router.get(BASE + "/{tenant_id}")
def trial_organization(tenant_id: uuid.UUID, request: Request, db: Session = Depends(get_db)):
    """One trial (or a converted one, read-only) with what can be done now."""
    _require_platform_admin(request, db)
    return admin_actions.detail(db, tenant_id)


@router.post(BASE + "/{tenant_id}/extend")
def extend_trial(tenant_id: uuid.UUID, payload: ExtendRequest, request: Request, db: Session = Depends(get_db)):
    admin = _require_platform_admin(request, db)
    return _audited(
        db,
        tenant_id,
        admin,
        "EXTEND",
        lambda: admin_actions.extend(db, tenant_id, admin, days=payload.days, reason=payload.reason),
    )


@router.post(BASE + "/{tenant_id}/end")
def end_trial(
    tenant_id: uuid.UUID,
    payload: EndRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    """MDARIX ends the trial now: an exit request "Ended by MDARIX", approved in the same step; data kept 30 days."""
    admin = _require_platform_admin(request, db)
    outcome = _audited(
        db, tenant_id, admin, "END", lambda: admin_actions.end_early(db, tenant_id, admin, reason=payload.reason)
    )
    outcome.pop("notify", None)
    return outcome


@router.post(BASE + "/{tenant_id}/convert")
def convert_trial(tenant_id: uuid.UUID, payload: ConvertRequest, request: Request, db: Session = Depends(get_db)):
    admin = _require_platform_admin(request, db)
    return _audited(
        db,
        tenant_id,
        admin,
        "CONVERT",
        lambda: admin_actions.convert(
            db,
            tenant_id,
            admin,
            kind=payload.kind,
            plan_id=payload.plan_id,
            starts_at=_moment(payload.starts_at, "starts_at"),
            expires_at=_moment(payload.expires_at, "expires_at"),
            reason=payload.reason,
        ),
    )


@router.post(BASE + "/{tenant_id}/delete-data")
def delete_trial_data(
    tenant_id: uuid.UUID, payload: DeleteDataRequest, request: Request, db: Session = Depends(get_db)
):
    """Delete a due trial's data now (30+ days after its end, no hold), with the organization's name typed."""
    admin = _require_platform_admin(request, db)
    return _audited(
        db,
        tenant_id,
        admin,
        "DELETE_DATA",
        lambda: admin_actions.delete_data(db, tenant_id, admin, confirm_name=payload.confirm_name),
    )


class AiAccessChange(BaseModel):
    active: bool
    # Checked in the route (at least 10 characters) so a short reason is audited as a refusal.
    reason: str = Field(max_length=1000)


def _value(active: bool) -> str:
    return governance.USER_AI_ACTIVE if active else "INACTIVE"


def _refuse(db: Session, tenant_id: uuid.UUID, admin, attempted: str, status: int, code: str, message: str):
    """Audit a refused change in the trial's own trail (when the organization exists), then raise."""
    db.rollback()
    if db.get(Tenant, tenant_id) is not None:
        db.add(
            make_audit_event(
                tenant_id=tenant_id,
                actor_ref=str(admin.id),
                action="TRIAL_ACTION_REFUSED",
                entity_type="Tenant",
                entity_id=tenant_id,
                details={"attempted": attempted, "code": code},
            )
        )
        db.commit()
    raise HTTPException(status, detail={"code": code, "message": message})


def _trial(db: Session, tenant_id: uuid.UUID, admin, attempted: str, reason: str | None = None) -> Tenant:
    tenant = db.get(Tenant, tenant_id)
    if tenant is None:
        raise HTTPException(404, detail={"code": "TENANT_NOT_FOUND", "message": "Organization is not available"})
    if not governance.is_free_trial(db, tenant_id):
        _refuse(
            db,
            tenant_id,
            admin,
            attempted,
            409,
            "AI_USER_FLAG_TRIAL_ONLY",
            "The per-user AI switch applies to free trials only.",
        )
    if reason is not None and len(reason.strip()) < MIN_REASON:
        _refuse(db, tenant_id, admin, attempted, 422, "REASON_TOO_SHORT", "Give a reason of at least 10 characters.")
    return tenant


def _apply(db: Session, admin, tenant_id: uuid.UUID, people, active: bool, reason: str, request: Request, bulk: bool):
    value, now, changed = _value(active), datetime.now(timezone.utc), 0
    for person in people:
        before = person.ai_access or governance.USER_AI_ACTIVE
        if before == value:
            continue
        person.ai_access = value
        person.updated_at = now
        changed += 1
        db.add(
            make_audit_event(
                tenant_id=tenant_id,
                actor_ref=str(admin.id),
                action="TRIAL_USER_AI_ACCESS_CHANGED",
                entity_type="AuthUser",
                entity_id=person.id,
                details={"source": "PLATFORM_ADMIN", **({"bulk": True} if bulk else {})},
                request=request,
                reason=reason,
                old_values={"ai_access": before == governance.USER_AI_ACTIVE},
                new_values={"ai_access": active},
                created_at=now,
            )
        )
    return changed


@router.get(BASE + "/{tenant_id}/users/ai-access")
def trial_users_ai_access(tenant_id: uuid.UUID, request: Request, db: Session = Depends(get_db)):
    """Each user of a free trial with their AI switch, and whether the organization has switched AI on."""
    from genai.provider import trial_chain_names

    admin = _require_platform_admin(request, db)
    tenant = _trial(db, tenant_id, admin, "AI_ACCESS_LIST")
    from backend.app.trial.sample_decision import _author_email

    rows = db.query(AuthUser).filter(AuthUser.tenant_id == tenant_id).order_by(AuthUser.display_name).all()
    author, chain_on = _author_email(tenant_id), bool(trial_chain_names())
    organization_on = bool(tenant.ai_processing_allowed)

    def active(row) -> bool:
        return (row.ai_access or governance.USER_AI_ACTIVE) == governance.USER_AI_ACTIVE

    switched_on = _organization_switched_on(db, tenant) if tenant.ai_processing_allowed else None
    by = _names(db, {switched_on.actor_ref}) if switched_on else {}
    return {
        # Both must agree (3.6.1): while the trial has not switched AI on, no user has AI.
        "organization_on": bool(tenant.ai_processing_allowed),
        # Who switched it on, and when (the latest switch-on in the trial's audit trail); None while it is off.
        "organization_on_by": by.get(str(switched_on.actor_ref), "MDARIX") if switched_on else None,
        "organization_on_at": switched_on.created_at.isoformat() if switched_on and switched_on.created_at else None,
        "trial_chain_on": chain_on,
        "items": [
            {
                "user_id": str(row.id),
                "display_name": row.display_name,
                "active": active(row),
                # The sample's author account (signs the sample's finished examples; never signs in): not a person.
                "system_user": row.username == author,
                # Whether this person gets AI now: their switch, the organization's and the trial chain together.
                "effective": active(row) and organization_on and chain_on and row.status == "ACTIVE",
            }
            for row in rows
        ],
    }


@router.put(BASE + "/{tenant_id}/users/{user_id}/ai-access")
def set_trial_user_ai_access(
    tenant_id: uuid.UUID, user_id: uuid.UUID, payload: AiAccessChange, request: Request, db: Session = Depends(get_db)
):
    """One user's AI switch; no change (and nothing audited) when already at that value."""
    admin = _require_platform_admin(request, db)
    _trial(db, tenant_id, admin, "USER_AI_ACCESS", payload.reason)
    person = db.query(AuthUser).filter(AuthUser.tenant_id == tenant_id, AuthUser.id == user_id).one_or_none()
    if person is None:
        _refuse(db, tenant_id, admin, "USER_AI_ACCESS", 404, "USER_NOT_FOUND", "This user is not in this trial.")
    changed = _apply(db, admin, tenant_id, [person], payload.active, payload.reason, request, bulk=False)
    db.commit()
    return {"user_id": str(user_id), "active": payload.active, "changed": bool(changed)}


@router.put(BASE + "/{tenant_id}/ai-access")
def set_trial_ai_access(tenant_id: uuid.UUID, payload: AiAccessChange, request: Request, db: Session = Depends(get_db)):
    """Every user of the trial (active and invited) to Active or Inactive in one transaction."""
    admin = _require_platform_admin(request, db)
    _trial(db, tenant_id, admin, "BULK_AI_ACCESS", payload.reason)
    people = db.query(AuthUser).filter(AuthUser.tenant_id == tenant_id).all()
    changed = _apply(db, admin, tenant_id, people, payload.active, payload.reason, request, bulk=True)
    db.add(
        make_audit_event(
            tenant_id=tenant_id,
            actor_ref=str(admin.id),
            action="TRIAL_AI_ACCESS_BULK_CHANGED",
            entity_type="Tenant",
            entity_id=tenant_id,
            details={"count": changed, "value": payload.active},
            request=request,
            reason=payload.reason,
        )
    )
    db.commit()
    return {"active": payload.active, "changed": changed, "total": len(people)}


# The changes the Platform Administrator sees on the trial's AI metrics (story step 9: each switch change).
AI_SWITCH_ACTIONS = (
    "AI_PROCESSING_SETTING_CHANGED",
    "AI_FEATURE_SETTING_CHANGED",
    "TRIAL_USER_AI_ACCESS_CHANGED",
    "TRIAL_AI_ACCESS_BULK_CHANGED",
)
METRIC_EVENTS = 20


@router.get(BASE + "/{tenant_id}/ai-metrics")
def trial_ai_metrics(tenant_id: uuid.UUID, request: Request, db: Session = Depends(get_db)):
    """A trial's AI this month: use against its own (lower) limit, model calls by outcome and feature, the trial
    provider chain (configured, resting), and the latest switch changes. Counts and metadata only: no record text."""
    import time

    from sqlalchemy import func

    from backend.app.db.models.ai_records import AiCall
    from backend.app.db.models.foundation import AuditEvent
    from genai.provider import GenAIProvider, _resting_until, trial_chain, trial_chain_names

    admin = _require_platform_admin(request, db)
    tenant = _trial(db, tenant_id, admin, "AI_METRICS")
    state = governance.usage(db, tenant_id)
    limit = governance.trial_monthly_budget(None if state["budget_is_default"] else state["monthly_token_budget"])
    month_start = datetime.fromisoformat(state["month"]).replace(tzinfo=timezone.utc)
    calls = (
        db.query(AiCall.outcome, AiCall.feature, func.count(), func.max(AiCall.created_at))
        .filter(AiCall.tenant_id == tenant_id, AiCall.created_at >= month_start)
        .group_by(AiCall.outcome, AiCall.feature)
        .all()
    )
    by_outcome: dict[str, int] = {}
    by_feature: dict[str, int] = {}
    for outcome, feature, count, _ in calls:
        by_outcome[outcome] = by_outcome.get(outcome, 0) + count
        by_feature[feature] = by_feature.get(feature, 0) + count
    last = max((at for *_, at in calls if at is not None), default=None)
    usable = {item.provider_name for item in trial_chain(GenAIProvider())}
    resting, now = _resting_until(), time.time()
    chain = []
    for position, name in enumerate(trial_chain_names(), start=1):
        until = resting.get(name, 0.0)
        state_word = "RESTING" if until > now else ("READY" if name in usable else "NOT_USABLE")
        chain.append(
            {
                "position": position,
                "name": name,
                "state": state_word,
                "resting_until": datetime.fromtimestamp(until, timezone.utc).isoformat() if until > now else None,
            }
        )
    events = (
        db.query(AuditEvent)
        .filter(AuditEvent.tenant_id == tenant_id, AuditEvent.action.in_(AI_SWITCH_ACTIONS))
        .order_by(AuditEvent.created_at.desc())
        .limit(METRIC_EVENTS)
        .all()
    )
    actors = _names(db, {event.actor_ref for event in events})
    # The person a per-user switch changed, by name (entity_id is their account).
    people = _names(db, {event.entity_id for event in events if event.action == "TRIAL_USER_AI_ACCESS_CHANGED"})
    return {
        "organization_on": bool(tenant.ai_processing_allowed),
        "usage": {
            "month": state["month"],
            "tokens_used": state["tokens_used"],
            "limit": limit,
            "percent": round(100 * state["tokens_used"] / limit) if limit else 0,
            "requests": state["requests"],
            "refused": state["refused"],
        },
        "calls": {
            "total": sum(by_outcome.values()),
            "by_outcome": by_outcome,
            "by_feature": by_feature,
            "last_at": last.isoformat() if last else None,
        },
        "chain": chain,
        "switch_events": [
            {
                "action": event.action,
                "at": event.created_at.isoformat() if event.created_at else None,
                "actor": actors.get(str(event.actor_ref), "MDARIX"),
                "reason": event.reason,
                "old_values": event.old_values,
                "new_values": event.new_values,
                "details": {
                    **{
                        key: value
                        for key, value in (event.details or {}).items()
                        if key in ("feature", "bulk", "count", "value", "source")
                    },
                    **(
                        {"user_name": people.get(str(event.entity_id))}
                        if event.action == "TRIAL_USER_AI_ACCESS_CHANGED"
                        else {}
                    ),
                },
            }
            for event in events
        ],
    }


def _organization_switched_on(db: Session, tenant: Tenant):
    """The latest audit event that switched the organization's AI on."""
    from backend.app.db.models.foundation import AuditEvent

    events = (
        db.query(AuditEvent)
        .filter(AuditEvent.tenant_id == tenant.id, AuditEvent.action == "AI_PROCESSING_SETTING_CHANGED")
        .order_by(AuditEvent.created_at.desc())
        .limit(20)
    )
    return next((event for event in events if (event.new_values or {}).get("ai_processing_allowed") is True), None)


def _names(db: Session, refs) -> dict[str, str]:
    ids = []
    for ref in refs:
        try:
            ids.append(uuid.UUID(str(ref)))
        except ValueError:
            continue
    if not ids:
        return {}
    rows = db.query(AuthUser.id, AuthUser.display_name, AuthUser.username).filter(AuthUser.id.in_(ids)).all()
    return {str(row.id): row.display_name or row.username for row in rows}
