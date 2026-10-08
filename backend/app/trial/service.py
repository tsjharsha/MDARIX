"""Free-trial lifecycle: a Platform Admin approves a public request into a private 30-day trial workspace.

Approval is one transaction: customer and tenant, Free Trial plan, 30-day subscription clock, data-plane routing,
sample data, the requester's invited account, and an audit event. The invitation is issued only after that commit,
so a failure never leaves a half-built workspace with a live activation link.
"""

from __future__ import annotations

import logging
import re
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from auth.durable import INVITATION_SECONDS, issue_invitation
from auth.emailer import EmailDeliveryError, send_trial_invitation
from auth.service import _hash
from backend.app.customer_lifecycle import build_customer_tenant
from backend.app.db.data_plane import TRIAL_SHARED_DATA_PLANE
from backend.app.db.models.customer_lifecycle import TenantDataPlane, TenantEnvironment
from backend.app.db.models.foundation import (
    AuditEvent,
    AuthUser,
    FeatureEntitlement,
    PlanDefinition,
    Tenant,
    TenantMembership,
    TenantPlanAssignment,
)
from backend.app.db.models.stage2 import OnboardingRequest, SubscriptionLifecycle
from backend.app.trial.sample_data import seed_sample_workspace
from backend.app.runtime_env import is_development

FREE_TRIAL_PLAN = "FREE_TRIAL"
TRIAL_DAYS = 30
TRIAL_USER_LIMIT = 3
TRIAL_ROW_LIMIT = 5000
TRIAL_FILE_LIMIT_BYTES = 2 * 1024 * 1024
TRIAL_INVITATION_TTL_SECONDS = INVITATION_SECONDS
# The requester works in the workspace (not the admin console), so they get a workspace role.
TRIAL_USER_ROLE = "Leader"
TRIAL_LIMITS = {
    "licensed_users_limit": TRIAL_USER_LIMIT,
    "customer_admin_limit": 0,
    "trial_days": TRIAL_DAYS,
    "upload_row_limit": TRIAL_ROW_LIMIT,
}


def _error(status: int, code: str, message: str) -> HTTPException:
    return HTTPException(status, detail={"code": code, "message": message})


def trial_subscription(db: Session, tenant_id) -> SubscriptionLifecycle | None:
    """The tenant's Free Trial subscription, or None when the tenant is not on the Free Trial plan."""
    return (
        db.query(SubscriptionLifecycle)
        .join(PlanDefinition, PlanDefinition.id == SubscriptionLifecycle.plan_id)
        .filter(SubscriptionLifecycle.tenant_id == tenant_id, PlanDefinition.code == FREE_TRIAL_PLAN)
        .order_by(SubscriptionLifecycle.created_at.desc())
        .first()
    )


def trial_has_ended(db: Session, tenant_id, now: datetime | None = None) -> bool:
    """True when the tenant is on the Free Trial plan and its end date (and any grace period) has passed.

    Runs on every authenticated request, so it is one indexed query; a converted tenant's subscription no longer
    points at the Free Trial plan and is never treated as ended here.
    """
    free_trial = select(PlanDefinition.id).where(PlanDefinition.code == FREE_TRIAL_PLAN).scalar_subquery()
    row = (
        db.query(SubscriptionLifecycle)
        .filter(SubscriptionLifecycle.tenant_id == tenant_id, SubscriptionLifecycle.plan_id.in_(free_trial))
        .first()
    )
    expires_at = getattr(row, "expires_at", None)
    if not isinstance(expires_at, datetime):
        return False
    now = now or datetime.now(timezone.utc)
    grace = getattr(row, "grace_ends_at", None)
    return expires_at <= now and not (isinstance(grace, datetime) and grace > now)


def trial_end_dates(db: Session, tenant_id) -> tuple[str | None, str | None]:
    """When a Free Trial ended and when its data is deleted (long dates), for the trial-ended page."""
    from backend.app.trial.retention import RETENTION_DAYS

    free_trial = select(PlanDefinition.id).where(PlanDefinition.code == FREE_TRIAL_PLAN).scalar_subquery()
    row = (
        db.query(SubscriptionLifecycle)
        .filter(SubscriptionLifecycle.tenant_id == tenant_id, SubscriptionLifecycle.plan_id.in_(free_trial))
        .first()
    )
    if row is None or not isinstance(row.expires_at, datetime):
        return None, None
    ended = max(row.expires_at, row.grace_ends_at or row.expires_at)
    return long_date(ended), long_date(ended + timedelta(days=RETENTION_DAYS))


def _free_trial_plan(db: Session, now: datetime) -> PlanDefinition:
    plan = (
        db.query(PlanDefinition)
        .filter(PlanDefinition.code == FREE_TRIAL_PLAN, PlanDefinition.status == "ACTIVE")
        .first()
    )
    if plan is not None:
        return plan
    plan = PlanDefinition(
        id=uuid.uuid4(),
        code=FREE_TRIAL_PLAN,
        name="Free Trial",
        description=f"{TRIAL_DAYS}-day evaluation: sample data, CSV templates, up to {TRIAL_USER_LIMIT} users.",
        version="v1",
        status="ACTIVE",
        effective_from=now,
        created_at=now,
        updated_at=now,
    )
    db.add(plan)
    db.flush()
    for feature in ("ADMIN_CONTROL_PLANE", "TRIAL_WORKSPACE"):
        db.add(
            FeatureEntitlement(
                id=uuid.uuid4(),
                plan_id=plan.id,
                feature_code=feature,
                enabled=True,
                limits=dict(TRIAL_LIMITS),
                status="ACTIVE",
                created_at=now,
                updated_at=now,
            )
        )
    return plan


def _trial_tenant_key(organization: str) -> str:
    stem = re.sub(r"[^A-Z0-9]+", "_", organization.upper()).strip("_")[:40] or "ORG"
    return f"TRIAL_{stem}_{secrets.token_hex(3).upper()}"


def _owner_status(db: Session, row: OnboardingRequest) -> str | None:
    """The requester's account status once approved: INVITED until they activate, then ACTIVE."""
    if row.tenant_id is None:
        return None
    status = (
        db.query(AuthUser.status)
        .filter(AuthUser.tenant_id == row.tenant_id, AuthUser.username == row.email.strip().lower())
        .scalar()
    )
    return status


def serialize_request(db: Session, row: OnboardingRequest) -> dict:
    tenant = db.query(Tenant).filter(Tenant.id == row.tenant_id).first() if row.tenant_id else None
    subscription = trial_subscription(db, row.tenant_id) if row.tenant_id else None
    return {
        "id": str(row.id),
        "business_id": row.business_id,
        "email": row.email,
        "display_name": row.display_name,
        "organization": row.organization,
        "status": row.status,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "reviewed_at": row.reviewed_at.isoformat() if row.reviewed_at else None,
        "decision_reason": row.decision_reason,
        "tenant_id": str(row.tenant_id) if row.tenant_id else None,
        "tenant_business_id": tenant.business_id if tenant else None,
        "tenant_key": tenant.tenant_key if tenant else None,
        "tenant_identifier": tenant.tenant_identifier if tenant else None,
        "trial_expires_at": subscription.expires_at.isoformat() if subscription else None,
        # Closed trials keep their data for 30 days (trial.retention), then it is deleted and the workspace archived.
        "data_delete_after": (subscription.expires_at + timedelta(days=30)).isoformat() if subscription else None,
        "data_deleted": bool(tenant and tenant.status == "ARCHIVED"),
        "owner_status": _owner_status(db, row),
    }


def long_date(value: datetime) -> str:
    """An unambiguous date for people in any country, e.g. 3 November 2026 (UTC)."""
    return f"{value.day} {value:%B %Y}"


def _send_invitation(db: Session, user: AuthUser, organization: str, admin_id) -> dict:
    token = issue_invitation(db, user.id, user.tenant_id, admin_id, ttl=TRIAL_INVITATION_TTL_SECONDS)
    subscription = trial_subscription(db, user.tenant_id)
    ends_on = long_date(subscription.expires_at) if subscription else f"{TRIAL_DAYS} days after activation"
    result: dict = {}
    try:
        delivery = send_trial_invitation(
            user.username, token, organization, ends_on=ends_on, users=TRIAL_USER_LIMIT, rows=TRIAL_ROW_LIMIT
        )
    except EmailDeliveryError as exc:
        delivery = "FAILED"
        result["email_error"] = str(exc)
    result["email_delivery"] = delivery
    # Without working email, a development host shows the link so the admin can pass it on by hand.
    if delivery != "SENT" and is_development():
        result["activation_path"] = f"/activate-account?token={token}"
    return result


def approve_request(db: Session, request_id: uuid.UUID, admin: AuthUser) -> dict:
    now = datetime.now(timezone.utc)
    row = db.query(OnboardingRequest).filter(OnboardingRequest.id == request_id).with_for_update().first()
    if row is None:
        raise _error(404, "TRIAL_REQUEST_NOT_FOUND", "Trial request not found")
    if row.status != "PENDING_REVIEW":
        raise _error(409, "TRIAL_REQUEST_ALREADY_REVIEWED", f"This request is already {row.status.lower()}")
    email = row.email.strip().lower()
    if db.query(AuthUser.id).filter(AuthUser.username == email).first() is not None:
        raise _error(409, "ACCOUNT_EXISTS", "An account with this email already exists")

    try:
        customer, tenant = build_customer_tenant(
            db=db, tenant_key=_trial_tenant_key(row.organization), name=row.organization, status="ACTIVE", now=now
        )
        db.add(customer)
        db.add(tenant)
        db.flush()
        plan = _free_trial_plan(db, now)
        db.add(
            TenantPlanAssignment(
                id=uuid.uuid4(),
                tenant_id=tenant.id,
                plan_id=plan.id,
                status="ACTIVE",
                effective_from=now,
                reason="Free trial approved",
                created_at=now,
                updated_at=now,
            )
        )
        subscription = SubscriptionLifecycle(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            plan_id=plan.id,
            plan_version=plan.version,
            starts_at=now,
            expires_at=now + timedelta(days=TRIAL_DAYS),
            status="ACTIVE",
            created_at=now,
            updated_at=now,
        )
        db.add(subscription)
        db.add(
            TenantEnvironment(
                id=uuid.uuid4(),
                tenant_id=tenant.id,
                environment_identifier=f"sandbox-{tenant.tenant_key.lower()}",
                environment_type="SANDBOX",
                region="UNSPECIFIED",
                residency_region="UNSPECIFIED",
                status="ACTIVE",
                provisioned_at=now,
                activated_at=now,
                created_at=now,
                updated_at=now,
            )
        )
        db.add(
            TenantDataPlane(
                id=uuid.uuid4(),
                tenant_id=tenant.id,
                database_ref=f"trial-shared:{tenant.tenant_key}",
                connection_secret_ref=TRIAL_SHARED_DATA_PLANE,
                region="UNSPECIFIED",
                residency_region="UNSPECIFIED",
                schema_version="control-plane",
                status="ACTIVE",
                created_at=now,
                updated_at=now,
            )
        )
        sample = seed_sample_workspace(db, tenant.id, now)
        user = AuthUser(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            username=email,
            display_name=row.display_name,
            company=row.organization,
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
                tenant_id=tenant.id,
                user_id=user.id,
                status="ACTIVE",
                is_default=True,
                created_at=now,
                updated_at=now,
            )
        )
        row.status = "APPROVED"
        row.tenant_id = tenant.id
        row.reviewed_by = admin.id
        row.reviewed_at = now
        row.updated_at = now
        db.add(
            AuditEvent(
                id=uuid.uuid4(),
                tenant_id=admin.tenant_id,
                actor_ref=str(admin.id),
                action="TRIAL_REQUEST_APPROVED",
                entity_type="Tenant",
                entity_id=tenant.id,
                details={
                    "request_id": str(row.id),
                    "tenant_key": tenant.tenant_key,
                    "trial_user_id": str(user.id),
                    "expires_at": subscription.expires_at.isoformat(),
                    "sample_data": sample,
                },
                created_at=now,
            )
        )
        db.commit()
    except HTTPException:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        raise _error(
            500, "TRIAL_APPROVAL_FAILED", "The trial workspace could not be created; nothing was saved"
        ) from exc

    invitation = _send_invitation(db, user, row.organization, admin.id)
    return {**serialize_request(db, row), **invitation}


def decline_request(db: Session, request_id: uuid.UUID, admin: AuthUser, reason: str) -> dict:
    now = datetime.now(timezone.utc)
    row = db.query(OnboardingRequest).filter(OnboardingRequest.id == request_id).with_for_update().first()
    if row is None:
        raise _error(404, "TRIAL_REQUEST_NOT_FOUND", "Trial request not found")
    if row.status != "PENDING_REVIEW":
        raise _error(409, "TRIAL_REQUEST_ALREADY_REVIEWED", f"This request is already {row.status.lower()}")
    row.status = "DECLINED"
    row.reviewed_by = admin.id
    row.reviewed_at = now
    row.decision_reason = reason
    row.updated_at = now
    db.add(
        AuditEvent(
            id=uuid.uuid4(),
            tenant_id=admin.tenant_id,
            actor_ref=str(admin.id),
            action="TRIAL_REQUEST_DECLINED",
            entity_type="OnboardingRequest",
            entity_id=row.id,
            details={"request_id": str(row.id), "reason": reason},
            created_at=now,
        )
    )
    # The requester hears back politely (never the internal reason). Queued with the decision and sent by the
    # outbox worker, so a slow or failing mail provider never fails or delays the decline, and delivery is retried.
    from backend.app.notifications import notify_trial_request_declined

    notify_trial_request_declined(db, admin.tenant_id, request_id=row.id)
    db.commit()
    return serialize_request(db, row)


def acknowledge_trial_request(organization: str, display_name: str, email: str) -> None:
    """Confirm to a requester that their free-trial request arrived (a background task after sign-up's response).

    Never raises: the request is already stored and the visitor already has their answer, so a mail failure is only
    logged (without the address).
    """
    from auth.emailer import send_trial_request_acknowledgement

    try:
        send_trial_request_acknowledgement(email, display_name=display_name, organization=organization)
    except Exception as exc:
        logging.getLogger(__name__).warning("Trial request acknowledgement failed: %s", type(exc).__name__)


def resend_invitation(db: Session, request_id: uuid.UUID, admin: AuthUser) -> dict:
    row = db.query(OnboardingRequest).filter(OnboardingRequest.id == request_id).first()
    if row is None or row.status != "APPROVED" or row.tenant_id is None:
        raise _error(409, "TRIAL_NOT_APPROVED", "Only an approved trial request has an invitation")
    user = (
        db.query(AuthUser)
        .filter(AuthUser.tenant_id == row.tenant_id, AuthUser.username == row.email.strip().lower())
        .first()
    )
    if user is None or user.status != "INVITED":
        raise _error(409, "TRIAL_USER_ALREADY_ACTIVE", "This user has already activated their account")
    return {**serialize_request(db, row), **_send_invitation(db, user, row.organization, admin.id)}
