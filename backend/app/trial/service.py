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
    Investigation,
    PlanDefinition,
    Tenant,
    TenantMembership,
    TenantPlanAssignment,
)
from backend.app.db.models.stage2 import OnboardingRequest, SubscriptionLifecycle
from backend.app.trial.request_profile import describe as describe_profile
from backend.app.trial.sample_data import (
    SAMPLE_SOURCE,
    seed_lot_quantities,
    seed_sample_workspace,
    seed_story_examples,
)
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


def trial_tenant_ids(db: Session) -> set:
    """The tenants on the Free Trial plan (each one ``trial_subscription`` finds), in one query."""
    return {
        tenant_id
        for (tenant_id,) in db.query(SubscriptionLifecycle.tenant_id)
        .join(PlanDefinition, PlanDefinition.id == SubscriptionLifecycle.plan_id)
        .filter(PlanDefinition.code == FREE_TRIAL_PLAN)
        .distinct()
    }


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


def serialize_request(db: Session, row: OnboardingRequest) -> dict:
    return serialize_requests(db, [row])[0]


def serialize_requests(db: Session, rows: list[OnboardingRequest]) -> list[dict]:
    """The queue's view of each request, with its trial workspace, the trial's end and whether the requester has
    activated their account (INVITED until they do, then ACTIVE): three statements for any number of requests."""
    tenant_ids = list({row.tenant_id for row in rows if row.tenant_id})
    tenants, subscriptions, owner_status = {}, {}, {}
    if tenant_ids:
        tenants = {
            tenant.id: tenant
            for tenant in db.query(
                Tenant.id, Tenant.business_id, Tenant.tenant_key, Tenant.tenant_identifier, Tenant.status
            ).filter(Tenant.id.in_(tenant_ids))
        }
        # Each tenant's latest Free Trial subscription (trial_subscription); a converted tenant has none.
        for subscription in (
            db.query(SubscriptionLifecycle.tenant_id, SubscriptionLifecycle.expires_at)
            .join(PlanDefinition, PlanDefinition.id == SubscriptionLifecycle.plan_id)
            .filter(SubscriptionLifecycle.tenant_id.in_(tenant_ids), PlanDefinition.code == FREE_TRIAL_PLAN)
            .order_by(SubscriptionLifecycle.created_at.desc(), SubscriptionLifecycle.id)
        ):
            subscriptions.setdefault(subscription.tenant_id, subscription)
        emails = list({row.email.strip().lower() for row in rows if row.tenant_id})
        owner_status = {
            (user.tenant_id, user.username): user.status
            for user in db.query(AuthUser.tenant_id, AuthUser.username, AuthUser.status).filter(
                AuthUser.tenant_id.in_(tenant_ids), AuthUser.username.in_(emails)
            )
        }
    return [
        _request_view(
            row,
            tenants.get(row.tenant_id),
            subscriptions.get(row.tenant_id),
            owner_status.get((row.tenant_id, row.email.strip().lower())) if row.tenant_id else None,
        )
        for row in rows
    ]


def _request_view(row: OnboardingRequest, tenant, subscription, owner_status: str | None) -> dict:
    return {
        "id": str(row.id),
        "business_id": row.business_id,
        "email": row.email,
        "display_name": row.display_name,
        "organization": row.organization,
        "status": row.status,
        # What the requester told MDARIX (the codes, and the same as readable lines for the review screen).
        "profile": dict(row.profile or {}),
        "profile_lines": [{"label": label, "value": words} for label, words in describe_profile(row.profile)],
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
        "owner_status": owner_status,
        # The latest invitation email (SENT, FAILED or NOT_CONFIGURED; None before md47) and when it was tried.
        "invitation_delivery": row.invitation_delivery,
        "invitation_attempted_at": row.invitation_attempted_at.isoformat() if row.invitation_attempted_at else None,
    }


REQUEST_STATUSES = ("PENDING_REVIEW", "APPROVED", "DECLINED")
REQUEST_PAGE_SIZE = 50
REQUEST_PAGE_SIZE_MAX = 200


def request_queue(
    db: Session,
    *,
    status: str = "",
    q: str = "",
    page: int = 1,
    page_size: int = REQUEST_PAGE_SIZE,
    sort: str = "",
    order: str = "",
) -> dict:
    """One page of the Platform Admin trial request queue, newest first unless ``sort``/``order`` says otherwise.

    ``status`` keeps one status (PENDING_REVIEW, APPROVED or DECLINED; all by default); ``q`` keeps the requests whose
    company, requester, email or MDARIX ID contains it. ``counts`` are per status over every request matching ``q``
    (the tabs), ``total`` and ``pages`` over the ones listed."""
    from sqlalchemy import func, or_

    from backend.app.sorting import order_query

    page_size = min(REQUEST_PAGE_SIZE_MAX, max(1, int(page_size)))
    query = db.query(OnboardingRequest)
    if q.strip():
        like = f"%{q.strip().lower()}%"
        query = query.filter(
            or_(
                func.lower(OnboardingRequest.organization).like(like),
                func.lower(OnboardingRequest.display_name).like(like),
                func.lower(OnboardingRequest.email).like(like),
                func.lower(OnboardingRequest.business_id).like(like),
            )
        )
    counts = dict.fromkeys(REQUEST_STATUSES, 0)
    for value, number in query.with_entities(OnboardingRequest.status, func.count(OnboardingRequest.id)).group_by(
        OnboardingRequest.status
    ):
        counts[value] = int(number)
    if status.strip():
        query = query.filter(OnboardingRequest.status == status.strip().upper())
    total = query.count()
    pages = max(1, -(-total // page_size))
    page = min(max(1, int(page)), pages)
    query = order_query(
        query,
        sort,
        order,
        columns={
            "business_id": [OnboardingRequest.business_id],
            "organization": [OnboardingRequest.organization],
            "requester": [OnboardingRequest.display_name, OnboardingRequest.email],
            "email": [OnboardingRequest.email],
            "requested": [OnboardingRequest.created_at],
            "created_at": [OnboardingRequest.created_at],
            "reviewed_at": [OnboardingRequest.reviewed_at],
            "status": [OnboardingRequest.status],
        },
        default=[OnboardingRequest.created_at.desc()],
        tiebreak=[OnboardingRequest.id],
    )
    rows = query.offset((page - 1) * page_size).limit(page_size).all()
    return {
        "items": serialize_requests(db, rows),
        "counts": counts,
        "page": page,
        "page_size": page_size,
        "total": total,
        "pages": pages,
    }


def long_date(value: datetime) -> str:
    """An unambiguous date for people in any country, e.g. 3 November 2026 (UTC)."""
    return f"{value.day} {value:%B %Y}"


def has_sample_investigation(db: Session, tenant_id) -> bool:
    """Whether the trial still has its sample investigation (the owner may have removed the sample data). A trial's
    records are on the shared control plane, as seed_sample_workspace wrote them in approve_request."""
    return (
        db.query(Investigation.id)
        .filter(Investigation.tenant_id == tenant_id, Investigation.source_system == SAMPLE_SOURCE)
        .first()
        is not None
    )


def _send_invitation(
    db: Session, user: AuthUser, organization: str, admin_id, *, invited_by: str | None = None
) -> dict:
    """Invite ``user`` to the trial: the requester's own invitation, or with ``invited_by`` (the trial owner's name)
    a colleague's."""
    token = issue_invitation(db, user.id, user.tenant_id, admin_id, ttl=TRIAL_INVITATION_TTL_SECONDS)
    subscription = trial_subscription(db, user.tenant_id)
    ends_on = long_date(subscription.expires_at) if subscription else f"{TRIAL_DAYS} days after activation"
    colleague = (
        {"invited_by": invited_by, "sample_data": has_sample_investigation(db, user.tenant_id)} if invited_by else {}
    )
    result: dict = {}
    try:
        delivery = send_trial_invitation(
            user.username,
            token,
            organization,
            ends_on=ends_on,
            users=TRIAL_USER_LIMIT,
            rows=TRIAL_ROW_LIMIT,
            **colleague,
        )
    except EmailDeliveryError as exc:
        delivery = "FAILED"
        result["email_error"] = str(exc)
    result["email_delivery"] = delivery
    # Without working email, a development host shows the link so the admin can pass it on by hand.
    if delivery != "SENT" and is_development():
        result["activation_path"] = f"/activate-account?token={token}"
    return result


def record_invitation(
    db: Session, row: OnboardingRequest, result: dict, actor_ref: str, *, source: str, retry: bool = False
) -> None:
    """Keep what became of an approved request's invitation email on the request (the queue shows it) and in the audit
    trail, without the address. With ``retry`` a failed one is queued to be sent again: the outbox retries it with its
    usual back-off (about five hours in all), then dead-letters it and alerts the operators. Commits."""
    now = datetime.now(timezone.utc)
    delivery = str(result.get("email_delivery") or "FAILED")
    row.invitation_delivery = delivery
    row.invitation_attempted_at = now
    row.updated_at = now
    # In the reviewer's (the platform's) trail, next to TRIAL_REQUEST_APPROVED.
    trail = _actor_tenant(db, row.reviewed_by) or row.tenant_id
    db.add(
        AuditEvent(
            id=uuid.uuid4(),
            tenant_id=trail,
            actor_ref=actor_ref,
            action="TRIAL_INVITATION_SENT" if delivery == "SENT" else "TRIAL_INVITATION_NOT_DELIVERED",
            entity_type="OnboardingRequest",
            entity_id=row.id,
            details={
                "request_id": str(row.id),
                "delivery": delivery,
                "error": result.get("email_error"),
                "source": source,
                "retry_queued": bool(retry and delivery == "FAILED"),
            },
            created_at=now,
        )
    )
    if retry and delivery == "FAILED":
        from backend.app.notifications import TRIAL_INVITATION_RETRY, _queue

        _queue(
            db,
            trail,
            TRIAL_INVITATION_RETRY,
            "OnboardingRequest",
            row.id,
            {"request_id": str(row.id)},
        )
    db.commit()


def _actor_tenant(db: Session, user_id):
    return db.query(AuthUser.tenant_id).filter(AuthUser.id == user_id).scalar() if user_id else None


def retry_invitation(db: Session, request_id) -> str:
    """Send a failed trial invitation again (the outbox's TRIAL_INVITATION_RETRY event). SKIPPED when it is no longer
    needed: the request was declined or purged, an invitation went out meanwhile (a resend), or the owner has
    activated. Returns SENT or FAILED otherwise; the caller raises on FAILED so the outbox tries again later."""
    row = db.get(OnboardingRequest, uuid.UUID(str(request_id)))
    if row is None or row.status != "APPROVED" or row.tenant_id is None or row.invitation_delivery == "SENT":
        return "SKIPPED"
    user = (
        db.query(AuthUser)
        .filter(AuthUser.tenant_id == row.tenant_id, AuthUser.username == row.email.strip().lower())
        .first()
    )
    if user is None or user.status != "INVITED":
        return "SKIPPED"
    result = _send_invitation(db, user, row.organization, row.reviewed_by)
    delivery = str(result.get("email_delivery") or "FAILED")
    if delivery == "SENT":
        record_invitation(db, row, result, "system:invitation-retry", source="RETRY")
    else:
        # Each failed attempt is on the request; the trail records the first failure and the eventual delivery.
        row.invitation_delivery = delivery
        row.invitation_attempted_at = datetime.now(timezone.utc)
        db.commit()
    return delivery


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
        # The rest of the story: hidden complaints, reporting clocks, CAPAs, the risk register and sample reporting
        # windows, so Complaints, Records and Readiness show findings from the first minute.
        sample["story"] = seed_story_examples(db, tenant.id, now)
        # Units per sample lot (md43), so the trend check counts per device in the field.
        sample["lot_quantities"] = seed_lot_quantities(db, tenant.id)
        # The guided investigation arrives with its Decision Brief written by a sample author and submitted for quality
        # review, so one trial user can review it and sign the decision (backend/app/trial/sample_decision.py).
        from backend.app.trial.sample_decision import stage_sample_decision

        sample["decision"] = stage_sample_decision(db, tenant.id, now)
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

    # The sample's signals now, for both approvals (a Platform Administrator's and the automatic one), rather than at
    # the scheduler's next run, and before the invitation, so the signal inbox has work when the person first signs
    # in. In a session of its own: a failure is logged and never fails the approval, which is committed above.
    from backend.app.signals.hooks import seed_demo_signals

    seed_demo_signals(db, user.tenant_id)
    invitation = _send_invitation(db, user, row.organization, admin.id)
    # The approval stands whatever happens to the email; a failed one is on the request and retried. Recording it can
    # never undo the committed approval either: a failure there is logged.
    try:
        record_invitation(db, row, invitation, str(admin.id), source="APPROVAL", retry=True)
    except Exception:
        db.rollback()
        logging.getLogger(__name__).exception("The outcome of a trial invitation could not be recorded")
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
    invitation = _send_invitation(db, user, row.organization, admin.id)
    record_invitation(db, row, invitation, str(admin.id), source="RESEND")
    return {**serialize_request(db, row), **invitation}
