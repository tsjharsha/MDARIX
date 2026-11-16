"""Trial organizations: the Platform Administrator's per-user AI switch (TO-1 spec 3.6.1).

Every route checks the Platform Administrator first (``_require_platform_admin``). The acting person comes only from
the signed-in session; the body carries ``{active, reason}``, never an actor. The trial is the path's tenant,
re-checked to be a free trial. Each changed value is audited ``TRIAL_USER_AI_ACCESS_CHANGED`` in the trial's own
trail (a bulk change adds ``bulk: true`` and one ``TRIAL_AI_ACCESS_BULK_CHANGED`` summary row); a refused change
(not a trial, a user of another trial, a reason under 10 characters) is audited ``TRIAL_ACTION_REFUSED``.

AI for a trial user needs both the organization switch (the trial's administrator) and this switch; enforcement is
in ``genai/governance.py`` on every model call. New users are Active. Paid organizations are not affected.
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
from genai import governance

router = APIRouter(prefix="/api/v1", tags=["Trial organizations"])

BASE = "/platform-admin/trial-organizations"
MIN_REASON = 10


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
    rows = db.query(AuthUser).filter(AuthUser.tenant_id == tenant_id).order_by(AuthUser.display_name).all()
    return {
        # Both must agree (3.6.1): while the trial has not switched AI on, no user has AI.
        "organization_on": bool(tenant.ai_processing_allowed),
        "trial_chain_on": bool(trial_chain_names()),
        "items": [
            {
                "user_id": str(row.id),
                "display_name": row.display_name,
                "active": (row.ai_access or governance.USER_AI_ACTIVE) == governance.USER_AI_ACTIVE,
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
                    key: value
                    for key, value in (event.details or {}).items()
                    if key in ("feature", "bulk", "count", "value", "source")
                },
            }
            for event in events
        ],
    }


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
