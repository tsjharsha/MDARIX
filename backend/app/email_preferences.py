"""The signed-in person's email choices (``auth_users.email_preferences``, md44).

- ``GET /api/v1/me/email-preferences``: the weekly readiness email (on unless switched off) and whether the person
  receives it at all (only quality leads do: the Leader and Quality Reviewer roles).
- ``PUT /api/v1/me/email-preferences``: switch it on or off, for oneself only; audited.
"""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.app.access.authz import _authenticated_user
from backend.app.db.session import get_db
from backend.app.enterprise_audit import make_audit_event

router = APIRouter(prefix="/api/v1/me", tags=["My account"])


class EmailPreferences(BaseModel):
    weekly_readiness: bool


def _view(db: Session, user) -> dict:
    from backend.app.access.permissions import roles_of_user
    from backend.app.readiness_home.digest import PREFERENCE, QUALITY_LEAD_ROLES, wants_digest
    from backend.app.role_codes import role_code

    lead = any(role_code(role) in QUALITY_LEAD_ROLES for role in roles_of_user(db, user))
    return {
        PREFERENCE: wants_digest(user),
        "weekly_readiness_eligible": lead,
        "weekly_readiness_about": (
            "Every Monday: your organization's quality loop, what changed since last week and the weakest link."
            if lead
            else "Sent to quality leads (Leader and Quality Reviewer roles); your role does not receive it."
        ),
    }


@router.get("/email-preferences")
def get_email_preferences(request: Request, db: Session = Depends(get_db)):
    return _view(db, _authenticated_user(request, db))


@router.put("/email-preferences")
def update_email_preferences(payload: EmailPreferences, request: Request, db: Session = Depends(get_db)):
    from backend.app.readiness_home.digest import PREFERENCE, wants_digest

    user = _authenticated_user(request, db)
    before = wants_digest(user)
    if before != payload.weekly_readiness:
        preferences = dict(user.email_preferences or {})
        preferences[PREFERENCE] = payload.weekly_readiness
        user.email_preferences = preferences
        now = datetime.now(timezone.utc)
        user.updated_at = now
        db.add(
            make_audit_event(
                tenant_id=user.tenant_id,
                actor_ref=str(user.id),
                action="EMAIL_PREFERENCES_CHANGED",
                entity_type="AuthUser",
                entity_id=user.id,
                request=request,
                old_values={PREFERENCE: before},
                new_values={PREFERENCE: payload.weekly_readiness},
                created_at=now,
            )
        )
        db.commit()
    return _view(db, user)
