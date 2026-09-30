"""Customer Administrator tenant settings: identity provider, notifications, lifecycle requests."""

import uuid
from datetime import datetime, timezone
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from backend.app.db.models.customer_lifecycle import (
    CustomerContact,
    IdentityProviderConfiguration,
    ReminderPolicyRecipient,
    RenewalRequest,
)
from backend.app.db.models.foundation import (
    AuditEvent,
    Tenant,
)
from backend.app.db.models.stage2 import (
    ReminderPolicy,
    SubscriptionLifecycle,
)
from backend.app.db.session import get_db
from backend.app.access.schemas import (
    CustomerIdentityProviderRequest,
    NotificationPreferencesRequest,
    NotificationRecipientRequest,
    RenewalRequestPayload,
)
from backend.app.access.authz import _admin_tenant
from backend.app.access.common import _audit_configuration

router = APIRouter(prefix="/api/v1", tags=["Access Control"])


@router.get("/admin/security/identity-provider")
def get_customer_identity_provider(request: Request, db: Session = Depends(get_db)):
    """Return tenant identity configuration without exposing credentials or secrets."""
    admin = _admin_tenant(request, db)
    rows = (
        db.query(IdentityProviderConfiguration)
        .filter(IdentityProviderConfiguration.tenant_id == admin.tenant_id)
        .order_by(IdentityProviderConfiguration.created_at.desc())
        .all()
    )
    return {
        "tenant_id": str(admin.tenant_id),
        "providers": [
            {
                "id": str(row.id),
                "provider_type": row.provider_type,
                "issuer": row.issuer,
                "client_reference": row.client_reference,
                "login_mode": row.login_mode,
                "status": row.status,
                "verified_at": row.verified_at,
            }
            for row in rows
        ],
    }


@router.put("/admin/security/identity-provider")
def save_customer_identity_provider(
    payload: CustomerIdentityProviderRequest, request: Request, db: Session = Depends(get_db)
):
    """Store an SSO configuration as PENDING; verification remains a separate controlled operation."""
    admin = _admin_tenant(request, db)
    parsed = urlparse(payload.issuer)
    if parsed.scheme != "https" or not parsed.netloc:
        raise HTTPException(
            422, detail={"code": "IDENTITY_ISSUER_MUST_BE_HTTPS", "message": "Identity provider issuer must use HTTPS"}
        )
    now = datetime.now(timezone.utc)
    row = (
        db.query(IdentityProviderConfiguration)
        .filter(
            IdentityProviderConfiguration.tenant_id == admin.tenant_id,
            IdentityProviderConfiguration.provider_type == payload.provider_type,
        )
        .first()
    )
    before = (
        {
            "issuer": row.issuer,
            "client_reference": row.client_reference,
            "login_mode": row.login_mode,
            "status": row.status,
        }
        if row
        else None
    )
    if row is None:
        row = IdentityProviderConfiguration(
            id=uuid.uuid4(),
            tenant_id=admin.tenant_id,
            provider_type=payload.provider_type,
            created_at=now,
            updated_at=now,
            configuration={},
            status="PENDING",
        )
        db.add(row)
    row.issuer = payload.issuer
    row.client_reference = payload.client_reference
    row.login_mode = payload.login_mode
    row.status = "PENDING"
    row.verified_at = None
    row.updated_at = now
    after = {
        "issuer": row.issuer,
        "client_reference": row.client_reference,
        "login_mode": row.login_mode,
        "status": row.status,
    }
    _audit_configuration(
        db,
        admin,
        "CUSTOMER_IDP_CONFIGURED",
        "IdentityProviderConfiguration",
        row.id,
        "v1",
        request=request,
        before=before,
        after=after,
        reason=payload.reason,
    )
    db.commit()
    return {
        "id": str(row.id),
        "tenant_id": str(row.tenant_id),
        "provider_type": row.provider_type,
        "status": row.status,
        "verification_required": True,
    }


@router.get("/admin/notifications/preferences")
def get_customer_notification_preferences(request: Request, db: Session = Depends(get_db)):
    admin = _admin_tenant(request, db)
    policies = (
        db.query(ReminderPolicy)
        .filter(ReminderPolicy.tenant_id == admin.tenant_id)
        .order_by(ReminderPolicy.updated_at.desc())
        .all()
    )
    recipients = db.query(ReminderPolicyRecipient).filter(ReminderPolicyRecipient.tenant_id == admin.tenant_id).all()
    return {
        "tenant_id": str(admin.tenant_id),
        "policies": [
            {
                "id": str(row.id),
                "name": row.name,
                "thresholds": row.thresholds,
                "timezone": row.timezone,
                "recipient_types": row.recipient_types,
                "version": row.version,
                "status": row.status,
            }
            for row in policies
        ],
        "recipients": [
            {
                "id": str(row.id),
                "policy_id": str(row.reminder_policy_id),
                "recipient_type": row.recipient_type,
                "contact_id": str(row.contact_id) if row.contact_id else None,
                "status": row.status,
            }
            for row in recipients
        ],
    }


@router.put("/admin/notifications/preferences")
def save_customer_notification_preferences(
    payload: NotificationPreferencesRequest, request: Request, db: Session = Depends(get_db)
):
    admin = _admin_tenant(request, db)
    if payload.thresholds != sorted(set(payload.thresholds), reverse=True) or any(
        value < 0 for value in payload.thresholds
    ):
        raise HTTPException(
            422,
            detail={
                "code": "INVALID_REMINDER_THRESHOLDS",
                "message": "Thresholds must be unique, non-negative, and descending",
            },
        )
    allowed = {"CUSTOMER_ADMIN", "BILLING_CONTACT", "BUSINESS_CONTACT", "ACCOUNT_OWNER"}
    if set(payload.recipient_types) - allowed:
        raise HTTPException(
            422, detail={"code": "INVALID_RECIPIENT_TYPE", "message": "Recipient type is not supported"}
        )
    now = datetime.now(timezone.utc)
    row = (
        db.query(ReminderPolicy)
        .filter(ReminderPolicy.tenant_id == admin.tenant_id, ReminderPolicy.status == "ACTIVE")
        .order_by(ReminderPolicy.updated_at.desc())
        .first()
    )
    before = (
        {"thresholds": row.thresholds, "timezone": row.timezone, "recipient_types": row.recipient_types}
        if row
        else None
    )
    if row is None:
        row = ReminderPolicy(
            id=uuid.uuid4(),
            tenant_id=admin.tenant_id,
            name="Customer notification policy",
            version="v1",
            created_at=now,
            updated_at=now,
        )
        db.add(row)
    row.thresholds = payload.thresholds
    row.timezone = payload.timezone
    row.recipient_types = payload.recipient_types
    row.updated_at = now
    _audit_configuration(
        db,
        admin,
        "CUSTOMER_NOTIFICATION_PREFERENCES_UPDATED",
        "ReminderPolicy",
        row.id,
        row.version,
        request=request,
        before=before,
        after={"thresholds": row.thresholds, "timezone": row.timezone, "recipient_types": row.recipient_types},
        reason=payload.reason,
    )
    db.commit()
    return {
        "id": str(row.id),
        "tenant_id": str(row.tenant_id),
        "status": row.status,
        "thresholds": row.thresholds,
        "timezone": row.timezone,
        "recipient_types": row.recipient_types,
    }


@router.post("/admin/notifications/recipients")
def add_customer_notification_recipient(
    payload: NotificationRecipientRequest, request: Request, db: Session = Depends(get_db)
):
    admin = _admin_tenant(request, db)
    tenant = db.query(Tenant).filter(Tenant.id == admin.tenant_id).first()
    if tenant is None or tenant.customer_id is None:
        raise HTTPException(
            409, detail={"code": "CUSTOMER_CONTEXT_REQUIRED", "message": "Tenant is not linked to a customer"}
        )
    policy = (
        db.query(ReminderPolicy)
        .filter(ReminderPolicy.tenant_id == admin.tenant_id, ReminderPolicy.status == "ACTIVE")
        .order_by(ReminderPolicy.updated_at.desc())
        .first()
    )
    if policy is None:
        raise HTTPException(
            409,
            detail={
                "code": "NOTIFICATION_POLICY_REQUIRED",
                "message": "Create notification preferences before recipients",
            },
        )
    now = datetime.now(timezone.utc)
    contact = (
        db.query(CustomerContact)
        .filter(CustomerContact.customer_id == tenant.customer_id, CustomerContact.email == payload.email)
        .first()
    )
    if contact is None:
        contact = CustomerContact(
            id=uuid.uuid4(),
            customer_id=tenant.customer_id,
            contact_type=payload.contact_type,
            name=payload.name,
            email=payload.email,
            status="ACTIVE",
            created_at=now,
            updated_at=now,
        )
        db.add(contact)
        db.flush()
    row = (
        db.query(ReminderPolicyRecipient)
        .filter(
            ReminderPolicyRecipient.tenant_id == admin.tenant_id,
            ReminderPolicyRecipient.reminder_policy_id == policy.id,
            ReminderPolicyRecipient.recipient_type == payload.recipient_type,
            ReminderPolicyRecipient.contact_id == contact.id,
        )
        .first()
    )
    if row is None:
        row = ReminderPolicyRecipient(
            id=uuid.uuid4(),
            tenant_id=admin.tenant_id,
            reminder_policy_id=policy.id,
            recipient_type=payload.recipient_type,
            contact_id=contact.id,
            status="ACTIVE",
            created_at=now,
        )
        db.add(row)
    _audit_configuration(
        db,
        admin,
        "CUSTOMER_NOTIFICATION_RECIPIENT_ADDED",
        "ReminderPolicyRecipient",
        row.id,
        policy.version,
        request=request,
        after={"email": payload.email, "recipient_type": payload.recipient_type},
        reason=payload.reason,
    )
    db.commit()
    return {
        "id": str(row.id),
        "policy_id": str(policy.id),
        "contact_id": str(contact.id),
        "recipient_type": row.recipient_type,
        "status": row.status,
    }


@router.get("/admin/tenant/lifecycle")
def get_customer_lifecycle(request: Request, db: Session = Depends(get_db)):
    admin = _admin_tenant(request, db)
    tenant = db.query(Tenant).filter(Tenant.id == admin.tenant_id).first()
    if tenant is None:
        raise HTTPException(404, detail={"code": "TENANT_NOT_FOUND", "message": "Tenant is not available"})
    return {
        "tenant_id": str(tenant.id),
        "status": tenant.status,
        "lifecycle_status": tenant.lifecycle_status,
        "lock_version": tenant.lock_version,
        "customer_admin_actions": ["REQUEST_RENEWAL"],
        "platform_controlled_actions": ["SUSPEND", "REACTIVATE", "TERMINATE", "ARCHIVE"],
    }


@router.post("/admin/tenant/lifecycle/renewal-request")
def request_customer_renewal(payload: RenewalRequestPayload, request: Request, db: Session = Depends(get_db)):
    admin = _admin_tenant(request, db)
    subscription = (
        db.query(SubscriptionLifecycle)
        .filter(SubscriptionLifecycle.tenant_id == admin.tenant_id)
        .order_by(SubscriptionLifecycle.expires_at.desc())
        .first()
    )
    if subscription is None:
        raise HTTPException(
            409, detail={"code": "SUBSCRIPTION_NOT_FOUND", "message": "No subscription is available for renewal"}
        )
    existing = (
        db.query(RenewalRequest)
        .filter(
            RenewalRequest.tenant_id == admin.tenant_id,
            RenewalRequest.subscription_id == subscription.id,
            RenewalRequest.status == "REQUESTED",
        )
        .first()
    )
    if existing:
        return {"id": str(existing.id), "status": existing.status, "idempotent": True}
    now = datetime.now(timezone.utc)
    row = RenewalRequest(
        id=uuid.uuid4(),
        tenant_id=admin.tenant_id,
        subscription_id=subscription.id,
        requested_by=admin.id,
        request_details={**payload.details, "reason": payload.reason},
        status="REQUESTED",
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    db.add(
        AuditEvent(
            id=uuid.uuid4(),
            tenant_id=admin.tenant_id,
            actor_ref=str(admin.id),
            action="RENEWAL_REQUESTED",
            entity_type="RenewalRequest",
            entity_id=row.id,
            details={"subscription_id": str(subscription.id)},
            created_at=now,
        )
    )
    db.commit()
    return {"id": str(row.id), "status": row.status, "subscription_id": str(subscription.id), "idempotent": False}
