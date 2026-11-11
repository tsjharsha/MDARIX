"""The signed-in person's email choices (``auth_users.email_preferences``, md44).

- ``GET /api/v1/me/email-preferences``: the weekly readiness email (on unless switched off) and whether the person
  receives it at all (only quality leads do: the Leader and Quality Reviewer roles); the daily deadline list (B6a G18a:
  regulatory approvers, Leaders and customer administrators) and whether the person may switch it off.
- ``PUT /api/v1/me/email-preferences``: switch either on or off, for oneself only; audited. The last person who
  receives the daily deadline list cannot switch it off (409 LAST_DEADLINE_RECIPIENT).
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.app.access.authz import _authenticated_user
from backend.app.db.session import get_db
from backend.app.enterprise_audit import make_audit_event

router = APIRouter(prefix="/api/v1/me", tags=["My account"])


class EmailPreferences(BaseModel):
    weekly_readiness: bool | None = None
    daily_deadlines: bool | None = None


def _view(db: Session, user) -> dict:
    from backend.app.access.permissions import roles_of_user
    from backend.app.oversight import deadline_list
    from backend.app.readiness_home.digest import PREFERENCE, QUALITY_LEAD_ROLES, wants_digest
    from backend.app.role_codes import role_code

    lead = any(role_code(role) in QUALITY_LEAD_ROLES for role in roles_of_user(db, user))
    daily = deadline_list.switched_on() and deadline_list.eligible(db, user)
    trial = deadline_list.in_trial(db, user.tenant_id)
    on = deadline_list.wants_list(user, trial)
    last = daily and on and deadline_list.last_recipient(db, user)
    return {
        PREFERENCE: wants_digest(user),
        "weekly_readiness_eligible": lead,
        "weekly_readiness_about": (
            "Every Monday: your organization's quality loop, what changed since last week and the weakest link."
            if lead
            else "Sent to quality leads (Leader and Quality Reviewer roles); your role does not receive it."
        ),
        deadline_list.PREFERENCE: on,
        "daily_deadlines_eligible": daily,
        "daily_deadlines_locked": last,
        # Owner, 11 Nov: off by default in a free trial; the screen offers "Try the daily list".
        "daily_deadlines_trial": trial,
        "daily_deadlines_about": (
            "Every day from 06:00 your organization's time: the open reporting deadlines, your copy if MDARIX is "
            "unavailable. Sent also when nothing is due."
            + (" In a free trial it is off until you try it; the downloads are always there." if trial else "")
            + (" You are the last person who receives it, so it stays on." if last else "")
            if daily
            else "Sent to regulatory approvers, Leaders and customer administrators; your role does not receive it."
        ),
    }


def _changed(db: Session, request: Request, user, key: str, before: bool, after: bool, now) -> None:
    preferences = dict(user.email_preferences or {})
    preferences[key] = after
    user.email_preferences = preferences
    user.updated_at = now
    db.add(
        make_audit_event(
            tenant_id=user.tenant_id,
            actor_ref=str(user.id),
            action="EMAIL_PREFERENCES_CHANGED",
            entity_type="AuthUser",
            entity_id=user.id,
            request=request,
            old_values={key: before},
            new_values={key: after},
            created_at=now,
        )
    )


@router.get("/email-preferences")
def get_email_preferences(request: Request, db: Session = Depends(get_db)):
    return _view(db, _authenticated_user(request, db))


@router.put("/email-preferences")
def update_email_preferences(payload: EmailPreferences, request: Request, db: Session = Depends(get_db)):
    from backend.app.oversight import deadline_list
    from backend.app.readiness_home.digest import PREFERENCE, wants_digest

    user = _authenticated_user(request, db)
    now = datetime.now(timezone.utc)
    changed = False
    if payload.weekly_readiness is not None and wants_digest(user) != payload.weekly_readiness:
        _changed(db, request, user, PREFERENCE, wants_digest(user), payload.weekly_readiness, now)
        changed = True
    before = deadline_list.wants_list(user, deadline_list.in_trial(db, user.tenant_id))
    if payload.daily_deadlines is not None and before != payload.daily_deadlines:
        if not payload.daily_deadlines and deadline_list.eligible(db, user) and deadline_list.last_recipient(db, user):
            db.rollback()
            raise HTTPException(
                409,
                detail={
                    "code": "LAST_DEADLINE_RECIPIENT",
                    "message": "You are the last person who receives the daily deadline list: it stays on until a "
                    "colleague receives it too.",
                },
            )
        _changed(db, request, user, deadline_list.PREFERENCE, before, payload.daily_deadlines, now)
        changed = True
    if changed:
        db.commit()
    return _view(db, user)
