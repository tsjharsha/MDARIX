"""Platform administration of Customer Administrators across every customer.

A Customer Administrator belongs to one tenant, not to the customer as a whole: a customer with three tenants
has administrators for each, and an administrator manages only the users of their own tenant.

A platform administrator can list every Customer Administrator, add one to a tenant (activation email),
resend an activation, send a password-reset email, and suspend or reactivate one. A tenant is never left
without an active Customer Administrator: suspending the last one is refused (add or replace one first, or
suspend the tenant instead). Every change is audited in the administrator's tenant with the reason given.

Adding, suspending or restoring a Customer Administrator and resetting an account's MFA are told by email as an
administrator's own changes are (backend/app/team_notices.py): the person changed and the organization's other active
Customer Administrators, with "MDARIX support" as the one who made the change. In a free trial only the person whose
MFA was reset is told (0.10.43). Nothing for an erasure (an erased person has no address); the platform administrator
sees the result on screen.

When an invitation email does not arrive, MDARIX support issues a fresh activation link for any account still
waiting to be activated (``POST /platform-admin/users/{id}/activation-link``) and hands it over.
"""

from __future__ import annotations

import secrets
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from auth.durable import hash_token, issue_invitation, issue_reset, revoke_user_sessions
from auth.emailer import (
    TEAM_INVITED,
    TEAM_MFA_RESET,
    EmailDeliveryError,
    company,
    send_activation_email,
    send_password_reset_email,
)
from auth.service import _hash
from backend.app.access.authz import _require_platform_admin
from backend.app import support_access, team_notices
from backend.app.access.common import _development_token, _enforce_invite_limits, erasure_refused
from backend.app.access.schemas import (
    CustomerAdminActionRequest,
    CustomerAdminCreateRequest,
    CustomerAdminStatusRequest,
)
from backend.app.db.models.customer_lifecycle import Customer
from backend.app.db.models.foundation import AuditEvent, AuthUser, Tenant, TenantMembership
from backend.app.db.models.stage2 import UserInvitation
from backend.app.db.session import get_db

router = APIRouter(prefix="/api/v1", tags=["Access Control"])

ROLE = "CUSTOMER_ADMIN"


def _is_customer_admin():
    return func.upper(AuthUser.role) == ROLE


def _active_admins(db: Session, tenant_id) -> int:
    return (
        db.query(AuthUser)
        .filter(AuthUser.tenant_id == tenant_id, _is_customer_admin(), func.upper(AuthUser.status) == "ACTIVE")
        .count()
    )


def _row(user: AuthUser, tenant: Tenant | None, customer: Customer | None, active_in_tenant: int) -> dict:
    status = (user.status or "").upper()
    return {
        "id": str(user.id),
        "business_id": user.business_id,
        "email": user.username,
        "display_name": user.display_name,
        "status": status,
        "email_verified": bool(user.email_verified),
        "tenant_id": str(user.tenant_id),
        "tenant_business_id": tenant.business_id if tenant else None,
        "tenant_key": tenant.tenant_key if tenant else None,
        "tenant_name": (tenant.display_name or tenant.name) if tenant else None,
        "tenant_status": (tenant.status or "").upper() if tenant else None,
        "customer_id": str(customer.id) if customer else None,
        "customer_business_id": customer.business_id if customer else None,
        "customer_name": (customer.display_name or customer.legal_name) if customer else None,
        "last_login_at": user.last_login_at.isoformat() if getattr(user, "last_login_at", None) else None,
        "created_at": user.created_at.isoformat() if user.created_at else None,
        # What the platform administrator can do next, so the interface offers only valid actions.
        "can_suspend": status == "ACTIVE" and active_in_tenant > 1,
        "is_last_active_admin": status == "ACTIVE" and active_in_tenant <= 1,
        "can_reactivate": status == "SUSPENDED",
        "can_resend_invitation": status == "INVITED",
        "can_reset_password": status == "ACTIVE",
    }


def _admin_or_404(db: Session, user_id: uuid.UUID) -> AuthUser:
    user = db.query(AuthUser).filter(AuthUser.id == user_id, _is_customer_admin()).first()
    if user is None:
        raise HTTPException(
            404, detail={"code": "CUSTOMER_ADMIN_NOT_FOUND", "message": "Customer Administrator is not available"}
        )
    return user


def _audit(db: Session, tenant_id, actor, action: str, user_id, details: dict, now: datetime, old=None, new=None):
    db.add(
        AuditEvent(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            actor_ref=str(actor.id),
            action=action,
            entity_type="AuthUser",
            entity_id=user_id,
            details={**details, "source": "PLATFORM_ADMIN"},
            old_values=old,
            new_values=new,
            created_at=now,
        )
    )


@router.get("/platform-admin/customer-admins")
def list_customer_admins(
    request: Request,
    q: str | None = None,
    status: str | None = None,
    customer_id: uuid.UUID | None = None,
    tenant_id: uuid.UUID | None = None,
    db: Session = Depends(get_db),
):
    """Every Customer Administrator of every customer, with what can be done for each."""
    _require_platform_admin(request, db)
    query = (
        db.query(AuthUser, Tenant, Customer)
        .join(Tenant, Tenant.id == AuthUser.tenant_id)
        .outerjoin(Customer, Customer.id == Tenant.customer_id)
        .filter(_is_customer_admin())
    )
    if q and q.strip():
        like = f"%{q.strip().lower()}%"
        query = query.filter(
            or_(
                func.lower(AuthUser.username).like(like),
                func.lower(AuthUser.display_name).like(like),
                func.lower(Tenant.tenant_key).like(like),
                func.lower(Tenant.display_name).like(like),
                func.lower(Customer.display_name).like(like),
                func.lower(AuthUser.business_id).like(like),
                func.lower(Tenant.business_id).like(like),
                func.lower(Customer.business_id).like(like),
            )
        )
    if status:
        query = query.filter(func.upper(AuthUser.status) == status.strip().upper())
    else:
        # Retired and offboarded accounts are history, not people to manage; ask for them by status to see them.
        query = query.filter(func.upper(AuthUser.status).notin_(["INACTIVE", "OFFBOARDED"]))
    if customer_id:
        query = query.filter(Tenant.customer_id == customer_id)
    if tenant_id:
        query = query.filter(AuthUser.tenant_id == tenant_id)
    rows = query.order_by(Customer.display_name, Tenant.tenant_key, AuthUser.username).limit(500).all()
    active = dict(
        db.query(AuthUser.tenant_id, func.count(AuthUser.id))
        .filter(_is_customer_admin(), func.upper(AuthUser.status) == "ACTIVE")
        .group_by(AuthUser.tenant_id)
        .all()
    )
    items = [_row(user, tenant, customer, active.get(user.tenant_id, 0)) for user, tenant, customer in rows]
    return {"items": items, "total": len(items)}


@router.get("/platform-admin/customer-admin-tenants")
def customer_admin_tenant_options(request: Request, db: Session = Depends(get_db)):
    """The tenants an administrator can be added to (active ones), for a picker: one light query, and one more for
    which are free trials (``is_trial``: a picker may leave them out)."""
    from backend.app.trial.service import trial_tenant_ids

    _require_platform_admin(request, db)
    rows = (
        db.query(
            Tenant.id,
            Tenant.tenant_key,
            Tenant.display_name,
            Customer.display_name,
            Tenant.business_id,
            Customer.business_id,
        )
        .outerjoin(Customer, Customer.id == Tenant.customer_id)
        .filter(func.upper(Tenant.status).in_(["ACTIVE", "PROVISIONED"]))
        .order_by(func.lower(func.coalesce(Customer.display_name, Tenant.display_name)), Tenant.tenant_key)
        .all()
    )
    trials = trial_tenant_ids(db) if rows else set()
    return {
        "items": [
            {
                "id": str(row[0]),
                "business_id": row[4],
                "tenant_key": row[1],
                "display_name": row[3] or row[2],
                "tenant_name": row[2],
                "customer_name": row[3],
                "customer_business_id": row[5],
                "is_trial": row[0] in trials,
            }
            for row in rows
        ]
    }


def ensure_email_is_free(db: Session, email: str, tenant_id=None) -> None:
    """One account per email in each organization. The same person may administer several organizations (a
    separate account in each); sign-in asks which one."""
    query = db.query(AuthUser.id).filter(func.lower(AuthUser.username) == email)
    if tenant_id is not None:
        query = query.filter(AuthUser.tenant_id == tenant_id)
    if query.first() is not None:
        raise HTTPException(
            409,
            detail={"code": "ACCOUNT_EXISTS", "message": "An account with this email already exists in this tenant."},
        )


def create_customer_admin(
    db: Session,
    *,
    tenant: Tenant,
    customer: Customer | None,
    email: str,
    display_name: str,
    reason: str,
    platform_admin: AuthUser,
    now: datetime,
) -> tuple[AuthUser, str, str]:
    """Create an invited Customer Administrator of one tenant and email the activation link (not committed).

    Returns the account, the invitation token and the email delivery result. On a delivery failure the
    transaction is rolled back, so nothing is left half-created.
    """
    ensure_email_is_free(db, email, tenant.id)
    _enforce_invite_limits(db, tenant.id, ROLE)
    company = (customer.display_name if customer else None) or tenant.name
    tenant_id = tenant.id
    user = AuthUser(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        username=email,
        display_name=display_name.strip(),
        company=company,
        password_hash=_hash(secrets.token_urlsafe(48)),
        role=ROLE,
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
            status="INVITED",
            is_default=True,
            created_at=now,
            updated_at=now,
        )
    )
    token = issue_invitation(db, user.id, tenant_id, platform_admin.id)
    try:
        delivery = send_activation_email(email, token, company)
    except EmailDeliveryError as exc:
        db.rollback()
        raise HTTPException(502, detail={"code": "SMTP_DELIVERY_FAILED", "message": str(exc)}) from exc
    _audit(
        db,
        tenant_id,
        platform_admin,
        "CUSTOMER_ADMIN_ADDED",
        user.id,
        {"reason": reason, "email_delivery": delivery},
        now,
    )
    # The organization's other administrators are told; the invitation above is the new administrator's email.
    team_notices.queue_support_change(db, user, TEAM_INVITED, now=now, tell_person=False)
    return user, token, delivery


@router.post("/platform-admin/tenants/{tenant_id}/customer-admins")
def add_customer_admin(
    tenant_id: uuid.UUID, payload: CustomerAdminCreateRequest, request: Request, db: Session = Depends(get_db)
):
    """Add a Customer Administrator to one tenant; they are invited by email to set their password."""
    platform_admin = _require_platform_admin(request, db)
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if tenant is None or (tenant.status or "").upper() not in {"ACTIVE", "PROVISIONED"}:
        raise HTTPException(
            404, detail={"code": "TENANT_NOT_ACTIVE", "message": "Administrators can be added only to an active tenant"}
        )
    customer = db.query(Customer).filter(Customer.id == tenant.customer_id).first()
    user, token, delivery = create_customer_admin(
        db,
        tenant=tenant,
        customer=customer,
        email=payload.email.strip().lower(),
        display_name=payload.display_name,
        reason=payload.reason,
        platform_admin=platform_admin,
        now=datetime.now(timezone.utc),
    )
    db.commit()
    return {
        **_row(user, tenant, customer, _active_admins(db, tenant_id)),
        "email_delivery": delivery,
        "development_token": _development_token(token) if delivery == "NOT_CONFIGURED" else None,
    }


@router.post("/platform-admin/customer-admins/{user_id}/resend-invitation")
def resend_customer_admin_invitation(
    user_id: uuid.UUID, payload: CustomerAdminActionRequest, request: Request, db: Session = Depends(get_db)
):
    platform_admin = _require_platform_admin(request, db)
    user = _admin_or_404(db, user_id)
    if (user.status or "").upper() != "INVITED":
        raise HTTPException(
            409,
            detail={"code": "NOT_INVITED", "message": "Only an administrator who has not activated can be re-invited"},
        )
    now = datetime.now(timezone.utc)
    token = issue_invitation(db, user.id, user.tenant_id, platform_admin.id)
    try:
        delivery = send_activation_email(user.username, token, user.company or "")
    except EmailDeliveryError as exc:
        db.rollback()
        raise HTTPException(502, detail={"code": "SMTP_DELIVERY_FAILED", "message": str(exc)}) from exc
    _audit(
        db,
        user.tenant_id,
        platform_admin,
        "CUSTOMER_ADMIN_INVITATION_RESENT",
        user.id,
        {"reason": payload.reason, "email_delivery": delivery},
        now,
    )
    db.commit()
    return {
        "id": str(user.id),
        "business_id": user.business_id,
        "status": "INVITED",
        "email_delivery": delivery,
        "development_token": _development_token(token) if delivery == "NOT_CONFIGURED" else None,
    }


@router.post("/platform-admin/customer-admins/{user_id}/password-reset")
def reset_customer_admin_password(
    user_id: uuid.UUID, payload: CustomerAdminActionRequest, request: Request, db: Session = Depends(get_db)
):
    """Email the administrator a single-use reset link. Their current password keeps working until they use it."""
    platform_admin = _require_platform_admin(request, db)
    user = _admin_or_404(db, user_id)
    if (user.status or "").upper() != "ACTIVE":
        raise HTTPException(
            409,
            detail={
                "code": "NOT_ACTIVE",
                "message": "Password reset is for active administrators; resend the invitation instead",
            },
        )
    now = datetime.now(timezone.utc)
    token = issue_reset(db, user.id, user.tenant_id, platform_admin.id)
    try:
        delivery = send_password_reset_email(user.username, token)
    except EmailDeliveryError as exc:
        db.rollback()
        raise HTTPException(502, detail={"code": "SMTP_DELIVERY_FAILED", "message": str(exc)}) from exc
    _audit(
        db,
        user.tenant_id,
        platform_admin,
        "CUSTOMER_ADMIN_PASSWORD_RESET_SENT",
        user.id,
        {"reason": payload.reason, "email_delivery": delivery},
        now,
    )
    db.commit()
    return {
        "id": str(user.id),
        "business_id": user.business_id,
        "status": "RESET_EMAIL_SENT" if delivery != "NOT_CONFIGURED" else "RESET_LINK_CREATED",
        "email_delivery": delivery,
        "development_token": _development_token(token) if delivery == "NOT_CONFIGURED" else None,
    }


@router.post("/platform-admin/users/{user_id}/activation-link")
def issue_activation_link(user_id: uuid.UUID, request: Request, response: Response, db: Session = Depends(get_db)):
    """A fresh single-use activation link for a person who has not activated their account yet, for MDARIX support
    to pass on when the invitation email did not arrive (or was deleted).

    The link is the same kind an invitation emails (48 hours, single use) and replaces any earlier unused one, so
    only the link handed over works. Whoever holds it sets the account's password, so it is issued only to a
    platform administrator whose own session passed multi-factor authentication, and only for an account that is
    still waiting to be activated: an active account recovers through a password reset, which reaches its owner's
    mailbox, not a link in someone else's hands. Audited ``ACTIVATION_LINK_ISSUED`` in the person's organization,
    naming the account only (never the link or the email address).
    """
    from backend.app import mfa
    from backend.app.enterprise_audit import make_audit_event

    platform_admin = _require_platform_admin(request, db)
    # The request context already refuses a session that still owes its second factor; an administrator without
    # an authenticator never passed one at all.
    if not mfa.is_enrolled(platform_admin):
        raise HTTPException(
            403,
            detail={
                "code": "MFA_REQUIRED",
                "message": "Set up multi-factor authentication before issuing activation links",
            },
        )
    user = db.query(AuthUser).filter(AuthUser.id == user_id).first()
    if user is None:
        raise HTTPException(404, detail={"code": "USER_NOT_FOUND", "message": "User is not available"})
    # MDARIX activates a Customer Administrator only while the organization has no active one (continuity);
    # anyone else of the organization only under the People access its administrators approved.
    support_access.require_people_access(db, platform_admin, user, continuity=True, request=request)
    status = (user.status or "").upper()
    if status == "ACTIVE":
        raise HTTPException(
            409,
            detail={
                "code": "ACCOUNT_ALREADY_ACTIVE",
                "message": "This account is already active; send a password reset instead",
            },
        )
    if status != "INVITED" or not user.username:
        raise HTTPException(
            409,
            detail={
                "code": "ACCOUNT_NOT_INVITED",
                "message": "Only an account waiting for activation can get an activation link; re-invite it first",
            },
        )
    now = datetime.now(timezone.utc)
    # Added before the link is issued: issue_invitation commits both together.
    db.add(
        make_audit_event(
            tenant_id=user.tenant_id,
            actor_ref=str(platform_admin.id),
            action="ACTIVATION_LINK_ISSUED",
            entity_type="AuthUser",
            entity_id=user.id,
            details={"user_id": str(user.id), "source": "PLATFORM_ADMIN"},
            request=request,
            created_at=now,
        )
    )
    token = issue_invitation(db, user.id, user.tenant_id, platform_admin.id)
    expires_at = db.query(UserInvitation.expires_at).filter(UserInvitation.token_hash == hash_token(token)).scalar()
    # The answer holds a credential: no cache may keep it.
    response.headers["Cache-Control"] = "no-store"
    return {"url": f"{company().app_url}/activate-account?token={token}", "expires_at": expires_at.isoformat()}


@router.post("/platform-admin/users/{user_id}/erase")
def erase_user_personal_data(
    user_id: uuid.UUID, payload: CustomerAdminActionRequest, request: Request, db: Session = Depends(get_db)
):
    """Erase an offboarded person's personal data on their request (irreversible; docs/runbooks/DATA_REQUESTS.md)."""
    from backend.app.tenant_purge import PurgeFailed, erase_person

    platform_admin = _require_platform_admin(request, db)
    user = db.query(AuthUser).filter(AuthUser.id == user_id).first()
    if user is None:
        raise HTTPException(404, detail={"code": "USER_NOT_FOUND", "message": "User is not available"})
    if user_id == platform_admin.id:
        raise HTTPException(409, detail={"code": "SELF_CHANGE_NOT_ALLOWED", "message": "You cannot erase yourself"})
    # Erasure is the organization's decision: its administrators do it, or approve People access for MDARIX.
    support_access.require_people_access(db, platform_admin, user, continuity=False, request=request)
    try:
        result = erase_person(db, user, str(platform_admin.id), payload.reason.strip())
    except PurgeFailed as exc:
        raise erasure_refused(str(exc)) from exc
    db.commit()
    return {**result, "status": "ERASED"}


@router.post("/platform-admin/users/{user_id}/mfa-reset")
def reset_user_mfa(
    user_id: uuid.UUID, payload: CustomerAdminActionRequest, request: Request, db: Session = Depends(get_db)
):
    """Remove any account's authenticator after it was lost with its recovery codes (for example a customer
    administrator, a free trial's owner, or a colleague on the platform team). Not one's own: another administrator
    must do that."""
    from backend.app import mfa
    from backend.app.trial.service import trial_subscription

    platform_admin = _require_platform_admin(request, db)
    if user_id == platform_admin.id:
        raise HTTPException(
            409, detail={"code": "SELF_CHANGE_NOT_ALLOWED", "message": "Another administrator must reset your MFA"}
        )
    user = db.query(AuthUser).filter(AuthUser.id == user_id).first()
    if user is None:
        raise HTTPException(404, detail={"code": "USER_NOT_FOUND", "message": "User is not available"})
    # A free trial's people are MDARIX's to recover: a trial has no administrator, and its owner's own MFA nobody
    # inside it can reset. Elsewhere, colleagues on the platform team and an organization's only active Customer
    # Administrator are MDARIX's to recover; anyone else, under the People access the organization's administrators
    # approved.
    trial_user = trial_subscription(db, user.tenant_id) is not None
    if not trial_user:
        support_access.require_people_access(db, platform_admin, user, continuity=True, request=request)
    now = datetime.now(timezone.utc)
    revoked = mfa.reset(db, user, now)
    _audit(
        db,
        user.tenant_id,
        platform_admin,
        "USER_MFA_RESET",
        user.id,
        {"reason": payload.reason, "sessions_revoked": revoked, **({"trial_user": True} if trial_user else {})},
        now,
    )
    # Never the reason in an email: it stays in the audit trail.
    team_notices.queue_support_change(db, user, TEAM_MFA_RESET, now=now)
    db.commit()
    return {"id": str(user.id), "business_id": user.business_id, "status": "MFA_RESET", "sessions_revoked": revoked}


@router.post("/platform-admin/customer-admins/{user_id}/status")
def change_customer_admin_status(
    user_id: uuid.UUID, payload: CustomerAdminStatusRequest, request: Request, db: Session = Depends(get_db)
):
    platform_admin = _require_platform_admin(request, db)
    user = _admin_or_404(db, user_id)
    current = (user.status or "").upper()
    target = payload.status
    allowed = {("ACTIVE", "SUSPENDED"), ("SUSPENDED", "ACTIVE")}
    if (current, target) not in allowed:
        raise HTTPException(
            409,
            detail={
                "code": "INVALID_STATUS_CHANGE",
                "message": f"A {current.lower()} administrator cannot become {target.lower()}",
            },
        )
    if target == "SUSPENDED" and _active_admins(db, user.tenant_id) <= 1:
        raise HTTPException(
            409,
            detail={
                "code": "LAST_ACTIVE_CUSTOMER_ADMIN",
                "message": "This is the tenant's only active administrator. Add or replace an administrator first, "
                "or suspend the tenant.",
            },
        )
    now = datetime.now(timezone.utc)
    user.status = target
    user.updated_at = now
    membership = (
        db.query(TenantMembership)
        .filter(TenantMembership.tenant_id == user.tenant_id, TenantMembership.user_id == user.id)
        .first()
    )
    if membership is not None:
        membership.status, membership.updated_at = target, now
    revoked = revoke_user_sessions(db, user.id, user.tenant_id) if target == "SUSPENDED" else 0
    _audit(
        db,
        user.tenant_id,
        platform_admin,
        "CUSTOMER_ADMIN_SUSPENDED" if target == "SUSPENDED" else "CUSTOMER_ADMIN_REACTIVATED",
        user.id,
        {"reason": payload.reason, "sessions_revoked": revoked},
        now,
        old={"status": current},
        new={"status": target},
    )
    team_notices.queue_support_change(db, user, team_notices.status_change(current, target), now=now)
    db.commit()
    tenant = db.query(Tenant).filter(Tenant.id == user.tenant_id).first()
    customer = db.query(Customer).filter(Customer.id == tenant.customer_id).first() if tenant else None
    return _row(user, tenant, customer, _active_admins(db, user.tenant_id))
