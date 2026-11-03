"""Free-trial team: the trial owner invites colleagues, up to the trial's safety cap, and looks after them.

Each colleague gets a persona (0.10.73, C1), and the persona is their real role (access_control/personas.py): a
Regulatory Leader is a Regulatory Reviewer, a Decision Maker an Approver. Only the owner gives or changes it, each time
audited as TRIAL_PERSONA_ASSIGNED; the colleague cannot change it (POST /api/v1/me/persona answers 403). Colleagues
invited before 0.10.73 keep the role Leader (the Quality Leader persona) until the owner changes it. Since 0.10.82
(D1.9) the owner may tick several personas: the first one's role is the account role, the others' additional roles,
so the rights add up; the colleague switches "Viewing as" between their own personas only.

Only the person whose request created the trial (the trial owner) can invite. Colleagues join that one workspace as
workspace users (never administrators) with a single-use invitation, exactly like the owner. A trial has no admin
console, so the owner also removes a colleague (the account is offboarded, never deleted: their work stays theirs,
and the seat is free again) and resets a colleague's MFA after they lost their authenticator and recovery codes. The
owner's own MFA is never reset here: they replace their authenticator in My Account, or MDARIX support resets it.

Each removal, withdrawn invitation and MFA reset is emailed to the person changed, to the owner as a confirmation,
and to the MDARIX team: one outbox event per email, queued with the change (backend/app/team_notices.py), so a slow
or failing mail provider never delays or undoes the change, and the worker retries each failed email on its own.
"""

from __future__ import annotations

import os
import re
import secrets
import uuid
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy.orm import Session

from auth import emailer
from auth.service import _hash
from backend.app import team_notices
from backend.app.access.authz import platform_account_clause
from backend.app.db.models.foundation import AuditEvent, AuthUser, Tenant, TenantMembership
from backend.app.db.models.stage2 import OnboardingRequest, UserInvitation
from access_control.personas import COLLEAGUE_PERSONAS, workspace_persona
from backend.app.trial.service import trial_user_cap, _send_invitation

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
    expired = _expired_invitations(db, tenant_id, users)
    return {
        "can_invite": owner,
        # Remove colleagues, reset their MFA, decide on support access: the trial owner only.
        "can_manage": owner,
        "limit": trial_user_cap(),
        "seats_used": len(users),
        # The personas the owner may give a colleague, in the order the invite form lists them.
        "personas": [
            {"code": code, "label": workspace_persona(code).label, "sub": workspace_persona(code).sub}
            for code in COLLEAGUE_PERSONAS
        ],
        "members": [
            {
                "id": str(user.id),
                "business_id": user.business_id,
                "display_name": user.display_name,
                "email": user.username,
                "status": user.status,
                "is_owner": user.username.strip().lower() == owner_email,
                "is_you": user.id == viewer.id,
                # An invitation whose link no longer works: shown as Expired, with Resend (J37).
                "invitation_expired": user.id in expired,
                **_persona_view(db, user, user.username.strip().lower() == owner_email),
            }
            for user in users
        ],
    }


def _persona_view(db: Session, user: AuthUser, owner: bool) -> dict:
    """A person's personas as the team list shows them; a colleague's are locked (only the owner changes them)."""
    from backend.app.access.session import colleague_personas, persona_of

    persona = workspace_persona(persona_of(db, user, owner))
    mine = [persona.code] if owner else colleague_personas(db, user)
    return {
        "persona": persona.code,
        "persona_label": persona.label,
        "persona_locked": not owner,
        # Every persona the owner gave the colleague (0.10.82, D1.9).
        "personas": [{"code": code, "label": workspace_persona(code).label} for code in mine],
    }


def _colleague_personas(codes) -> list:
    """The personas the owner gives a colleague (one or more, in the catalog's order): any but Admin, which is the
    owner's own; none named is the Quality Leader (the role Leader, as every trial colleague had before 0.10.73)."""
    chosen = []
    for code in codes or ["quality"]:
        try:
            persona = workspace_persona(code)
        except ValueError:
            raise _error(422, "UNKNOWN_PERSONA", "Choose one of the personas listed")
        if persona.code not in COLLEAGUE_PERSONAS:
            raise _error(422, "PERSONA_NOT_FOR_COLLEAGUE", "Admin is the trial owner's own: choose another persona")
        chosen.append(persona.code)
    return [workspace_persona(code) for code in COLLEAGUE_PERSONAS if code in chosen]


def _assign_personas(db: Session, tenant_id, owner: AuthUser, user: AuthUser, personas: list, now) -> None:
    """The colleague's roles follow their personas (0.10.82, D1.9): the first persona's role is the account role, each
    other's an additional role (user_additional_roles, revoked rows kept), so their rights add up; the persona shown
    stays the one they view as while it is still theirs. Separation of duties is per person, so nobody approves what
    they prepared, whatever roles they hold. The caller audits and commits."""
    from backend.app.db.models.workflow import UserAdditionalRole

    user.role = personas[0].role
    if user.view_persona not in [persona.code for persona in personas]:
        user.view_persona = personas[0].code
    user.updated_at = now
    wanted = {persona.role for persona in personas[1:]} - {personas[0].role}
    rows = {
        row.role_code: row
        for row in db.query(UserAdditionalRole).filter(
            UserAdditionalRole.tenant_id == tenant_id, UserAdditionalRole.user_id == user.id
        )
    }
    for role in wanted:
        row = rows.get(role)
        if row is None:
            db.add(
                UserAdditionalRole(
                    id=uuid.uuid4(),
                    tenant_id=tenant_id,
                    user_id=user.id,
                    role_code=role,
                    status="ACTIVE",
                    reason="Persona given by the trial owner",
                    granted_by=str(owner.id),
                    granted_at=now,
                )
            )
        elif row.status != "ACTIVE":
            row.status, row.granted_by, row.granted_at, row.revoked_by, row.revoked_at = (
                "ACTIVE",
                str(owner.id),
                now,
                None,
                None,
            )
    for role, row in rows.items():
        if row.status == "ACTIVE" and role not in wanted:
            row.status, row.revoked_by, row.revoked_at = "REVOKED", str(owner.id), now


def _audit_persona(db: Session, tenant_id, owner: AuthUser, user: AuthUser, personas, before: dict, now, how: str):
    """TRIAL_PERSONA_ASSIGNED, with the personas and roles before and after."""
    from backend.app.enterprise_audit import make_audit_event

    after = {"personas": [persona.code for persona in personas], "roles": [persona.role for persona in personas]}
    db.add(
        make_audit_event(
            tenant_id=tenant_id,
            actor_ref=str(owner.id),
            action="TRIAL_PERSONA_ASSIGNED",
            entity_type="AuthUser",
            entity_id=user.id,
            details={
                "user_id": str(user.id),
                "persona": personas[0].code,
                "role": personas[0].role,
                **after,
                "previous_persona": before.get("persona"),
                "previous_role": before.get("role"),
                "previous_personas": before.get("personas"),
                "how": how,
                "source": SOURCE,
            },
            old_values={
                "role": before.get("role"),
                "view_persona": before.get("persona"),
                "personas": before.get("personas"),
            },
            new_values={"role": personas[0].role, "view_persona": user.view_persona, **after},
            created_at=now,
        )
    )


def _expired_invitations(db: Session, tenant_id, users) -> set:
    """The invited people whose newest invitation link has expired (or who hold none that still works)."""
    from sqlalchemy import func

    invited = [user.id for user in users if user.status == "INVITED"]
    if not invited:
        return set()
    open_until = dict(
        db.query(UserInvitation.user_id, func.max(UserInvitation.expires_at))
        .filter(
            UserInvitation.tenant_id == tenant_id,
            UserInvitation.user_id.in_(invited),
            UserInvitation.used_at.is_(None),
        )
        .group_by(UserInvitation.user_id)
        .all()
    )
    now = datetime.now(timezone.utc)
    return {user_id for user_id in invited if open_until.get(user_id) is None or open_until[user_id] <= now}


CANNOT_INVITE = (
    "This email cannot be invited to your trial. Invite your colleague with another work email, or ask them to write "
    "to MDARIX support."
)


def _invitable(db: Session, tenant_id, email: str) -> AuthUser | None:
    """Who already has this email: nobody (None), or a colleague removed from this trial, who may be invited again.
    The trial's own cases are refused with what they are (J37): an invitation waiting, a colleague on the team. An
    account in another organization gets one neutral answer that does not say so (0.10.81, the security review's F1:
    the answer told anyone whether an address has an MDARIX account)."""
    existing = db.query(AuthUser).filter(AuthUser.username == email).first()
    if existing is None:
        # The organization's own session reads only its own accounts: an account elsewhere is looked up apart, and
        # only whether it exists is read.
        from backend.app.db.session import SessionLocal
        from backend.app.db.tenant_scope import bind_system

        with SessionLocal() as lookup:
            bind_system(lookup, "trial invitation: is this email an account in another organization")
            elsewhere = lookup.query(AuthUser.id).filter(AuthUser.username == email).first() is not None
        if not elsewhere:
            return None
    if existing is None or existing.tenant_id != tenant_id:
        raise _error(409, "CANNOT_INVITE", CANNOT_INVITE)
    if existing.status == "INVITED":
        raise _error(
            409,
            "INVITATION_PENDING",
            "You have already invited this person. Their invitation is in your team list: use Resend invitation there.",
        )
    if existing.status != REMOVED_STATUS:
        raise _error(409, "ALREADY_ON_THE_TEAM", "This person is already on your trial team.")
    return existing


def invite_colleague(
    db: Session,
    tenant_id,
    inviter: AuthUser,
    email: str,
    display_name: str,
    persona_code: str | None = None,
    persona_codes: list[str] | None = None,
) -> dict:
    require_owner(db, tenant_id, inviter, "Only the person who started this trial can invite colleagues")
    personas = _colleague_personas(persona_codes or ([persona_code] if persona_code else None))
    persona = personas[0]
    email = email.strip().lower()
    name = display_name.strip()
    if not _EMAIL.match(email) or len(email) > 254:
        raise _error(422, "INVALID_EMAIL", "Enter a valid work email address")
    if not name or len(name) > 120:
        raise _error(422, "INVALID_NAME", "Enter the colleague's name")
    from backend.app.plain_names import looks_like_link

    # The name goes into the invitation email to the colleague: never a link (SEC-04).
    if looks_like_link(name):
        raise _error(422, "NAME_HAS_LINK", "Write the colleague's name without a web or email address")
    # The invitation limits first (0.10.81, security F1): nobody learns anything about an address past them.
    _limit_invitations(tenant_id, inviter, "invite")
    returning = _invitable(db, tenant_id, email)
    # Lock the trial's request row so two simultaneous invites cannot both take the last seat.
    db.query(OnboardingRequest).filter(OnboardingRequest.tenant_id == tenant_id).with_for_update().first()
    seated = db.query(AuthUser.id).filter(AuthUser.tenant_id == tenant_id, AuthUser.status.in_(SEATED_STATUSES)).count()
    cap = trial_user_cap()
    if seated >= cap:
        raise _error(
            409,
            "TRIAL_USER_LIMIT_REACHED",
            f"Your trial has {cap} people, its safety limit. Remove someone to invite another, or write to MDARIX "
            "support to raise it.",
        )
    now = datetime.now(timezone.utc)
    if returning is not None:
        # A removed colleague invited again: the same account (their earlier work stays theirs), a new password set
        # through the new invitation, and their membership active again.
        from backend.app import mfa

        user = returning
        before = {"persona": user.view_persona, "role": user.role}
        user.display_name, user.status, user.updated_at = name, "INVITED", now
        user.view_persona = None  # they start on their first persona
        user.password_hash = _hash(secrets.token_urlsafe(24))
        mfa.reset(db, user, now)  # they set up their authenticator again, as a new colleague does
        db.query(TenantMembership).filter(
            TenantMembership.tenant_id == tenant_id, TenantMembership.user_id == user.id
        ).update({"status": "ACTIVE", "updated_at": now}, synchronize_session=False)
    else:
        user = AuthUser(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            username=email,
            display_name=name,
            company=inviter.company,
            password_hash=_hash(secrets.token_urlsafe(24)),
            # The colleague's real role follows the persona the owner chose (0.10.73; it was Leader for everyone).
            role=persona.role,
            view_persona=persona.code,
            status="INVITED",
            email_verified=False,
            created_at=now,
            updated_at=now,
        )
        before = {}
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
            details={
                "invited_user_id": str(user.id),
                "invited_again": returning is not None,
                "persona": persona.code,
                "role": persona.role,
                "personas": [item.code for item in personas],
            },
            created_at=now,
        )
    )
    _assign_personas(db, tenant_id, inviter, user, personas, now)
    _audit_persona(db, tenant_id, inviter, user, personas, before, now, "invited")
    db.commit()
    return {
        "id": str(user.id),
        "business_id": user.business_id,
        "email": email,
        "display_name": name,
        "persona": persona.code,
        "role": persona.role,
        "personas": [item.code for item in personas],
        **_send_invitation(db, user, inviter.company, inviter.id, invited_by=_owner_name(inviter)),
    }


def change_colleague_persona(
    db: Session,
    tenant_id,
    owner: AuthUser,
    user_id: uuid.UUID,
    persona_code: str | None,
    persona_codes: list[str] | None = None,
) -> dict:
    """The owner gives a colleague another persona, and with it its role (a colleague invited before 0.10.73 keeps
    Leader until then). The owner's own is changed with "Viewing as" (POST /api/v1/me/persona), never here. Audited as
    TRIAL_PERSONA_ASSIGNED; every route reads the new role at the colleague's next request."""
    require_owner(db, tenant_id, owner, "Only the person who started this trial can change a colleague's persona")
    if not persona_code and not persona_codes:
        raise _error(422, "PERSONA_REQUIRED", "Tick at least one persona")
    personas = _colleague_personas(persona_codes or [persona_code])
    user = _colleague(db, tenant_id, owner, user_id, own="Change your own view with Viewing as, at the top")
    if user.status not in SEATED_STATUSES:
        raise _error(409, "NOT_ON_THE_TEAM", "This person is no longer on your trial team")
    from backend.app.access.session import colleague_personas, persona_of

    held = colleague_personas(db, user)
    before = {"persona": persona_of(db, user, False), "role": user.role, "personas": held}
    if held != [item.code for item in personas] or user.role != personas[0].role:
        now = datetime.now(timezone.utc)
        _assign_personas(db, tenant_id, owner, user, personas, now)
        _audit_persona(db, tenant_id, owner, user, personas, before, now, "changed")
        db.commit()
    return {
        "id": str(user.id),
        "business_id": user.business_id,
        "persona": persona_of(db, user, False),
        "role": personas[0].role,
        "personas": [item.code for item in personas],
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


def person(db: Session, tenant_id, user: AuthUser) -> dict:
    """The signed-in person in their trial, for Getting started and the feedback prompt (UX-26): when they first
    signed in (their first session; their account's creation if none is recorded), and, for a colleague, who invited
    them and to which organization. In a trial only the owner invites (``require_owner``), so the owner is the
    inviter."""
    from sqlalchemy import func

    from backend.app.db.models.stage2 import AuthSession

    first = (
        db.query(func.min(AuthSession.created_at))
        .filter(AuthSession.tenant_id == tenant_id, AuthSession.user_id == user.id)
        .scalar()
    )
    joined = first or user.created_at
    invited_by = None
    if not is_trial_owner(db, tenant_id, user):
        request = trial_request(db, tenant_id)
        owner_email = (request.email if request else "").strip().lower()
        owner = (
            db.query(AuthUser)
            .filter(AuthUser.tenant_id == tenant_id, AuthUser.username == owner_email, AuthUser.status == "ACTIVE")
            .first()
            if owner_email
            else None
        )
        invited_by = _owner_name(owner) if owner is not None else None
    tenant = db.get(Tenant, tenant_id)
    return {
        "joined_at": joined.isoformat() if joined else None,
        "invited_by": invited_by,
        "organization": ((tenant.display_name or tenant.name) if tenant else None),
    }


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
    change = emailer.TEAM_INVITATION_WITHDRAWN if previous == "INVITED" else emailer.TEAM_REMOVED
    team_notices.queue_trial_change(db, tenant_id, owner, user, change, now)
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
    # Each reset emails the colleague, the owner and MDARIX: limited, so resets cannot send mail without end.
    from backend.app.rate_limit import enforce

    enforce(
        "team-mfa-reset:org",
        str(tenant_id),
        "You have reset as many authenticators as MDARIX allows in one day. Please try again tomorrow, or write to "
        "support if you need to.",
    )
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
    team_notices.queue_trial_change(db, tenant_id, owner, user, emailer.TEAM_MFA_RESET, now)
    db.commit()
    return {
        "id": str(user.id),
        "business_id": user.business_id,
        "status": "MFA_RESET",
        "sessions_revoked": revoked,
    }


# ------------------------------------------------------------------------------------------- Team change emails


def organization_name(db: Session, tenant_id, owner: AuthUser | None) -> str:
    """How the team change emails name the organization: as the invitations name it (the owner's company), else as
    the trial was requested, else the tenant's name."""
    request = trial_request(db, tenant_id)
    tenant = db.query(Tenant.name).filter(Tenant.id == tenant_id).first()
    return (
        ((owner.company if owner else "") or "").strip()
        or (request.organization if request else "")
        or (tenant.name if tenant else "your organization")
    )


def team_alert_recipient() -> str:
    """Where the MDARIX team hears of trial team changes: the same address as the pilot-request alert
    (backend/app/trial/router.py), or nobody when none is configured."""
    return (os.getenv("MDARIX_DEMO_ALERT_EMAIL") or os.getenv("MDARIX_TRIAL_ALERT_EMAIL") or "").strip()
