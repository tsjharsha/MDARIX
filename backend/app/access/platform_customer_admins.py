"""Platform administration of Customer Administrators across every customer.

A platform administrator can list every Customer Administrator, add one to a customer tenant (activation email),
resend an activation, send a password-reset email, and suspend or reactivate one. A customer is never left
without an active Customer Administrator: suspending the last one is refused (add or replace one first, or
suspend the whole customer instead). Every change is audited in the customer's tenant with the reason given.
"""

from __future__ import annotations

import secrets
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from auth.durable import issue_invitation, issue_reset, revoke_user_sessions
from auth.emailer import EmailDeliveryError, send_activation_email, send_password_reset_email
from auth.service import _hash
from backend.app.access.authz import _require_platform_admin
from backend.app.access.common import _development_token, _enforce_invite_limits
from backend.app.access.schemas import (
    CustomerAdminActionRequest,
    CustomerAdminCreateRequest,
    CustomerAdminStatusRequest,
)
from backend.app.db.models.customer_lifecycle import Customer
from backend.app.db.models.foundation import AuditEvent, AuthUser, Tenant, TenantMembership
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
        "email": user.username,
        "display_name": user.display_name,
        "status": status,
        "email_verified": bool(user.email_verified),
        "tenant_id": str(user.tenant_id),
        "tenant_key": tenant.tenant_key if tenant else None,
        "tenant_status": (tenant.status or "").upper() if tenant else None,
        "customer_id": str(customer.id) if customer else None,
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
                func.lower(Customer.display_name).like(like),
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
    rows = query.order_by(Customer.display_name, AuthUser.username).limit(500).all()
    active = dict(
        db.query(AuthUser.tenant_id, func.count(AuthUser.id))
        .filter(_is_customer_admin(), func.upper(AuthUser.status) == "ACTIVE")
        .group_by(AuthUser.tenant_id)
        .all()
    )
    items = [_row(user, tenant, customer, active.get(user.tenant_id, 0)) for user, tenant, customer in rows]
    return {"items": items, "total": len(items)}


@router.post("/platform-admin/tenants/{tenant_id}/customer-admins")
def add_customer_admin(
    tenant_id: uuid.UUID, payload: CustomerAdminCreateRequest, request: Request, db: Session = Depends(get_db)
):
    platform_admin = _require_platform_admin(request, db)
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if tenant is None or (tenant.status or "").upper() not in {"ACTIVE", "PROVISIONED"}:
        raise HTTPException(
            404, detail={"code": "TENANT_NOT_ACTIVE", "message": "Administrators can be added only to an active tenant"}
        )
    email = payload.email.strip().lower()
    existing = db.query(AuthUser).filter(func.lower(AuthUser.username) == email).first()
    if existing is not None:
        raise HTTPException(
            409, detail={"code": "ACCOUNT_EXISTS", "message": "An account with this email already exists"}
        )
    _enforce_invite_limits(db, tenant_id, ROLE)
    customer = db.query(Customer).filter(Customer.id == tenant.customer_id).first()
    company = (customer.display_name if customer else None) or tenant.name
    now = datetime.now(timezone.utc)
    user = AuthUser(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        username=email,
        display_name=payload.display_name.strip(),
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
        {"reason": payload.reason, "email_delivery": delivery},
        now,
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
        "status": "RESET_EMAIL_SENT" if delivery != "NOT_CONFIGURED" else "RESET_LINK_CREATED",
        "email_delivery": delivery,
        "development_token": _development_token(token) if delivery == "NOT_CONFIGURED" else None,
    }


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
                "message": "This is the customer's only active administrator. Add or replace an administrator first, "
                "or suspend the whole customer.",
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
    db.commit()
    tenant = db.query(Tenant).filter(Tenant.id == user.tenant_id).first()
    customer = db.query(Customer).filter(Customer.id == tenant.customer_id).first() if tenant else None
    return _row(user, tenant, customer, _active_admins(db, user.tenant_id))
