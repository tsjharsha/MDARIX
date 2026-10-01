"""Free-trial team: the trial owner invites colleagues, up to the trial's user limit.

Only the person whose request created the trial can invite. Colleagues join that one workspace as workspace users
(never administrators) with a single-use invitation, exactly like the owner.
"""

from __future__ import annotations

import re
import secrets
import uuid
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy.orm import Session

from auth.service import _hash
from backend.app.db.models.foundation import AuditEvent, AuthUser, TenantMembership
from backend.app.db.models.stage2 import OnboardingRequest
from backend.app.trial.service import TRIAL_USER_LIMIT, TRIAL_USER_ROLE, _send_invitation

SEATED_STATUSES = ("ACTIVE", "INVITED")
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _error(status: int, code: str, message: str) -> HTTPException:
    return HTTPException(status, detail={"code": code, "message": message})


def trial_request(db: Session, tenant_id) -> OnboardingRequest | None:
    return db.query(OnboardingRequest).filter(OnboardingRequest.tenant_id == tenant_id).first()


def is_trial_owner(db: Session, tenant_id, user: AuthUser) -> bool:
    row = trial_request(db, tenant_id)
    return row is not None and row.email.strip().lower() == (user.username or "").strip().lower()


def team(db: Session, tenant_id, viewer: AuthUser) -> dict:
    request = trial_request(db, tenant_id)
    owner_email = (request.email if request else "").strip().lower()
    users = (
        db.query(AuthUser)
        .filter(AuthUser.tenant_id == tenant_id, AuthUser.status.in_(SEATED_STATUSES))
        .order_by(AuthUser.created_at)
        .all()
    )
    return {
        "can_invite": is_trial_owner(db, tenant_id, viewer),
        "limit": TRIAL_USER_LIMIT,
        "seats_used": len(users),
        "members": [
            {
                "id": str(user.id),
                "display_name": user.display_name,
                "email": user.username,
                "status": user.status,
                "is_owner": user.username.strip().lower() == owner_email,
                "is_you": user.id == viewer.id,
            }
            for user in users
        ],
    }


def invite_colleague(db: Session, tenant_id, inviter: AuthUser, email: str, display_name: str) -> dict:
    if not is_trial_owner(db, tenant_id, inviter):
        raise _error(403, "TRIAL_OWNER_REQUIRED", "Only the person who started this trial can invite colleagues")
    email = email.strip().lower()
    name = display_name.strip()
    if not _EMAIL.match(email) or len(email) > 254:
        raise _error(422, "INVALID_EMAIL", "Enter a valid work email address")
    if not name or len(name) > 120:
        raise _error(422, "INVALID_NAME", "Enter the colleague's name")
    if db.query(AuthUser.id).filter(AuthUser.username == email).first() is not None:
        raise _error(409, "ACCOUNT_EXISTS", "This person already has an MDARIX account")
    # Lock the trial's request row so two simultaneous invites cannot both take the last seat.
    db.query(OnboardingRequest).filter(OnboardingRequest.tenant_id == tenant_id).with_for_update().first()
    seated = db.query(AuthUser.id).filter(AuthUser.tenant_id == tenant_id, AuthUser.status.in_(SEATED_STATUSES)).count()
    if seated >= TRIAL_USER_LIMIT:
        raise _error(
            409, "TRIAL_USER_LIMIT_REACHED", f"Your free trial includes up to {TRIAL_USER_LIMIT} users, all in use"
        )
    now = datetime.now(timezone.utc)
    user = AuthUser(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        username=email,
        display_name=name,
        company=inviter.company,
        password_hash=_hash(secrets.token_urlsafe(24)),
        role=TRIAL_USER_ROLE,
        status="INVITED",
        email_verified=False,
        created_at=now,
        updated_at=now,
    )
    db.add(user)
    db.flush()
    db.add(
        TenantMembership(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            user_id=user.id,
            status="ACTIVE",
            is_default=True,
            created_at=now,
            updated_at=now,
        )
    )
    db.add(
        AuditEvent(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            actor_ref=str(inviter.id),
            action="TRIAL_COLLEAGUE_INVITED",
            entity_type="AuthUser",
            entity_id=user.id,
            details={"invited_user_id": str(user.id)},
            created_at=now,
        )
    )
    db.commit()
    return {
        "id": str(user.id),
        "email": email,
        "display_name": name,
        **_send_invitation(db, user, inviter.company, inviter.id),
    }


def resend_colleague_invitation(db: Session, tenant_id, inviter: AuthUser, user_id: uuid.UUID) -> dict:
    if not is_trial_owner(db, tenant_id, inviter):
        raise _error(403, "TRIAL_OWNER_REQUIRED", "Only the person who started this trial can resend invitations")
    user = db.query(AuthUser).filter(AuthUser.id == user_id, AuthUser.tenant_id == tenant_id).first()
    if user is None or user.status != "INVITED":
        raise _error(409, "NOT_AN_OPEN_INVITATION", "This person has already activated their account")
    return {"id": str(user.id), "email": user.username, **_send_invitation(db, user, inviter.company, inviter.id)}
