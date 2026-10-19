"""Free-trial team: the trial owner invites colleagues, up to the trial's user limit, and looks after them.

Only the person whose request created the trial (the trial owner) can invite. Colleagues join that one workspace as
workspace users (never administrators) with a single-use invitation, exactly like the owner. A trial has no admin
console, so the owner also removes a colleague (the account is offboarded, never deleted: their work stays theirs,
and the seat is free again) and resets a colleague's MFA after they lost their authenticator and recovery codes. The
owner's own MFA is never reset here: they replace their authenticator in My Account, or MDARIX support resets it.
"""

from __future__ import annotations

import re
import secrets
import uuid
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy.orm import Session

from auth.service import _hash
from backend.app.access.authz import platform_account_clause
from backend.app.db.models.foundation import AuditEvent, AuthUser, TenantMembership
from backend.app.db.models.stage2 import OnboardingRequest, UserInvitation
from backend.app.trial.service import TRIAL_USER_LIMIT, TRIAL_USER_ROLE, _send_invitation

SEATED_STATUSES = ("ACTIVE", "INVITED")
# A removed colleague: refused at sign-in and by any invitation link (backend/app/auth_router.py); holds no seat.
REMOVED_STATUS = "OFFBOARDED"
SOURCE = "TRIAL_OWNER"
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _error(status: int, code: str, message: str) -> HTTPException:
    return HTTPException(status, detail={"code": code, "message": message})


def trial_request(db: Session, tenant_id) -> OnboardingRequest | None:
    return db.query(OnboardingRequest).filter(OnboardingRequest.tenant_id == tenant_id).first()


def is_trial_owner(db: Session, tenant_id, user: AuthUser) -> bool:
    row = trial_request(db, tenant_id)
    return row is not None and row.email.strip().lower() == (user.username or "").strip().lower()


def require_owner(db: Session, tenant_id, user: AuthUser, message: str) -> None:
    if not is_trial_owner(db, tenant_id, user):
        raise _error(403, "TRIAL_OWNER_REQUIRED", message)


def team(db: Session, tenant_id, viewer: AuthUser) -> dict:
    request = trial_request(db, tenant_id)
    owner_email = (request.email if request else "").strip().lower()
    users = (
        db.query(AuthUser)
        .filter(AuthUser.tenant_id == tenant_id, AuthUser.status.in_(SEATED_STATUSES), ~platform_account_clause())
        .order_by(AuthUser.created_at)
        .all()
    )
    owner = is_trial_owner(db, tenant_id, viewer)
    return {
        "can_invite": owner,
        # Remove colleagues, reset their MFA, decide on support access: the trial owner only.
        "can_manage": owner,
        "limit": TRIAL_USER_LIMIT,
        "seats_used": len(users),
        "members": [
            {
                "id": str(user.id),
                "business_id": user.business_id,
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
    require_owner(db, tenant_id, inviter, "Only the person who started this trial can invite colleagues")
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
    _limit_invitations(tenant_id, inviter, "invite")
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
        "business_id": user.business_id,
        "email": email,
        "display_name": name,
        **_send_invitation(db, user, inviter.company, inviter.id, invited_by=_owner_name(inviter)),
    }


def resend_colleague_invitation(db: Session, tenant_id, inviter: AuthUser, user_id: uuid.UUID) -> dict:
    require_owner(db, tenant_id, inviter, "Only the person who started this trial can resend invitations")
    user = db.query(AuthUser).filter(AuthUser.id == user_id, AuthUser.tenant_id == tenant_id).first()
    if user is None or user.status != "INVITED":
        raise _error(409, "NOT_AN_OPEN_INVITATION", "This person has already activated their account")
    _limit_invitations(tenant_id, inviter, "invite-resend", address=user.username)
    return {
        "id": str(user.id),
        "business_id": user.business_id,
        "email": user.username,
        **_send_invitation(db, user, inviter.company, inviter.id, invited_by=_owner_name(inviter)),
    }


def _limit_invitations(tenant_id, actor: AuthUser, kind: str, *, address: str | None = None) -> None:
    """Count one invitation email (``kind`` "invite" or "invite-resend") against the limits in rate_limit.LIMITS:
    per person and per organization for new invitations, per address and per organization for resent ones. Raises
    429 with a plain message once a limit is reached; the email is not sent."""
    from backend.app.rate_limit import enforce, invitation_message

    if kind == "invite":
        enforce("invite:user", str(actor.id), invitation_message("invite:user"))
        enforce("invite:org", str(tenant_id), invitation_message("invite:org"))
    else:
        enforce("invite-resend:address", address, invitation_message("invite-resend:address"))
        enforce("invite-resend:org", str(tenant_id), invitation_message("invite-resend:org"))


def _owner_name(owner: AuthUser) -> str:
    """How a colleague's invitation names the trial's owner: their name, else their email."""
    return (owner.display_name or "").strip() or owner.username


def _colleague(db: Session, tenant_id, owner: AuthUser, user_id: uuid.UUID, *, own: str) -> AuthUser:
    """A person of this trial the owner acts on: never the owner themself (``own`` says what to do instead), an
    MDARIX staff account or the sample author (an account nobody signs in with)."""
    if user_id == owner.id:
        raise _error(409, "SELF_CHANGE_NOT_ALLOWED", own)
    user = (
        db.query(AuthUser)
        .filter(AuthUser.id == user_id, AuthUser.tenant_id == tenant_id, ~platform_account_clause())
        .with_for_update()
        .first()
    )
    if user is None or str(user.username or "").startswith("sample-author+"):
        raise _error(404, "USER_NOT_FOUND", "This person is not on your trial team")
    return user


def remove_colleague(db: Session, tenant_id, owner: AuthUser, user_id: uuid.UUID, request=None) -> dict:
    """Take a colleague off the trial, or withdraw an invitation not yet accepted. The account is offboarded (it
    cannot sign in, and an open invitation link no longer works), every session of theirs ends, and the seat is free
    for someone else. Nothing they did is deleted: it stays attributed to them. Audited as TRIAL_COLLEAGUE_REMOVED."""
    from auth.durable import revoke_user_sessions
    from backend.app.enterprise_audit import make_audit_event

    require_owner(db, tenant_id, owner, "Only the person who started this trial can remove colleagues")
    user = _colleague(db, tenant_id, owner, user_id, own="You cannot remove yourself from your own trial")
    previous = user.status
    if previous not in SEATED_STATUSES:
        raise _error(409, "NOT_ON_THE_TEAM", "This person is no longer on your trial team")
    # Removing frees a seat for another invitation: limited too, so remove-and-invite cannot loop without end.
    from backend.app.rate_limit import enforce

    enforce(
        "team-remove:org",
        str(tenant_id),
        "You have removed as many colleagues as MDARIX allows in one day. Please try again tomorrow, or write to "
        "support if you need to.",
    )
    now = datetime.now(timezone.utc)
    user.status = REMOVED_STATUS
    user.updated_at = now
    db.query(TenantMembership).filter(
        TenantMembership.tenant_id == tenant_id, TenantMembership.user_id == user.id
    ).update({"status": REMOVED_STATUS, "updated_at": now}, synchronize_session=False)
    # An invitation not yet accepted is withdrawn: its link stops working at once.
    db.query(UserInvitation).filter(
        UserInvitation.tenant_id == tenant_id, UserInvitation.user_id == user.id, UserInvitation.used_at.is_(None)
    ).update({"used_at": now}, synchronize_session=False)
    revoked = revoke_user_sessions(db, user.id, tenant_id)
    db.add(
        make_audit_event(
            tenant_id=tenant_id,
            actor_ref=str(owner.id),
            action="TRIAL_COLLEAGUE_REMOVED",
            entity_type="AuthUser",
            entity_id=user.id,
            details={
                "removed_user_id": str(user.id),
                "invitation_withdrawn": previous == "INVITED",
                "sessions_revoked": revoked,
                "source": SOURCE,
            },
            old_values={"status": previous},
            new_values={"status": user.status},
            request=request,
            created_at=now,
        )
    )
    db.commit()
    return {
        "id": str(user.id),
        "business_id": user.business_id,
        "email": user.username,
        "status": "REMOVED",
        "invitation_withdrawn": previous == "INVITED",
        "sessions_revoked": revoked,
    }


def reset_colleague_mfa(db: Session, tenant_id, owner: AuthUser, user_id: uuid.UUID, reason: str, request=None) -> dict:
    """Remove a colleague's authenticator after they lost it with their recovery codes (backend/app/mfa.py reset):
    they are signed out and set up a new one at their next sign-in. Audited as USER_MFA_RESET, like an
    administrator's reset."""
    from backend.app import mfa
    from backend.app.enterprise_audit import make_audit_event

    require_owner(db, tenant_id, owner, "Only the person who started this trial can reset a colleague's MFA")
    user = _colleague(
        db, tenant_id, owner, user_id, own="Replace your own authenticator app in My Account › Security instead"
    )
    if user.status != "ACTIVE":
        raise _error(409, "USER_NOT_ACTIVE", "Only a colleague who has activated their account has MFA to reset")
    now = datetime.now(timezone.utc)
    revoked = mfa.reset(db, user, now)
    db.add(
        make_audit_event(
            tenant_id=tenant_id,
            actor_ref=str(owner.id),
            action="USER_MFA_RESET",
            entity_type="AuthUser",
            entity_id=user.id,
            details={"reason": reason.strip(), "sessions_revoked": revoked, "source": SOURCE},
            request=request,
            created_at=now,
        )
    )
    db.commit()
    return {"id": str(user.id), "business_id": user.business_id, "status": "MFA_RESET", "sessions_revoked": revoked}
