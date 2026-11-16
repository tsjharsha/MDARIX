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
