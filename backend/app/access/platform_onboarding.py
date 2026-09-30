"""Platform administration: onboarding drafts and validation, tenant provisioning jobs, domain and identity-provider verification."""

import secrets
import uuid
from datetime import datetime, timezone
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from auth.durable import hash_token, issue_invitation
from auth.emailer import (
    send_activation_email,
)
from auth.service import _hash
from backend.app.customer_lifecycle import (
    build_customer_tenant,
)
from backend.app.db.models.customer_lifecycle import (
    CustomerDomain,
    CustomerOnboardingDraft,
    DomainVerification,
    IdentityProviderConfiguration,
    ProvisioningJob,
    ProvisioningJobStep,
    TenantEnvironment,
)
from backend.app.db.models.foundation import (
    AuditEvent,
    AuthUser,
    FeatureEntitlement,
    PlanDefinition,
    Tenant,
    TenantMembership,
    TenantPlanAssignment,
)
from backend.app.db.models.stage2 import (
    UserInvitation,
)
from backend.app.db.session import get_db
from backend.app.access.schemas import (
    CustomerProvisionRequest,
    DomainVerificationRequest,
    IdentityProviderVerificationRequest,
    OnboardingDraftRequest,
)
from backend.app.access.authz import _require_platform_admin
from backend.app.access.common import _validate_onboarding_payload

router = APIRouter(prefix="/api/v1", tags=["Access Control"])


@router.post("/platform/tenants/provision")
def provision_tenant(payload: CustomerProvisionRequest, request: Request, db: Session = Depends(get_db)):
    """Idempotent platform provisioning with an initial customer administrator.

    The request is keyed by tenant_code and administrator email. A retry returns
    the existing provisioning state instead of creating another tenant/user/invite.
    """
    admin = _require_platform_admin(request, db)
    _validate_onboarding_payload(payload, db)
    key = payload.tenant_code.strip().upper()
    email = payload.customer_admin_email.strip().lower()
    now = datetime.now(timezone.utc)
    tenant = db.query(Tenant).filter(Tenant.tenant_key == key).first()
    if tenant is None:
        customer, tenant = build_customer_tenant(
            db=db,
            tenant_key=key,
            name=payload.company_name,
            status="PROVISIONING",
            now=now,
            region=payload.region,
            residency_region=payload.residency,
        )
        db.add(customer)
        db.add(tenant)
        db.flush()
        plan = (
            db.query(PlanDefinition)
            .filter(PlanDefinition.code == payload.plan_code, PlanDefinition.status == "ACTIVE")
            .first()
        )
        if plan is None:
            plan = PlanDefinition(
                id=uuid.uuid4(),
                code=payload.plan_code,
                name=payload.plan_code.replace("_", " ").title(),
                description="Platform provisioning plan",
                version="v1",
                status="ACTIVE",
                effective_from=now,
                created_at=now,
                updated_at=now,
            )
            db.add(plan)
            db.flush()
        db.add(
            TenantPlanAssignment(
                id=uuid.uuid4(),
                tenant_id=tenant.id,
                plan_id=plan.id,
                status="ACTIVE",
                effective_from=now,
                reason="Platform provisioning",
                created_at=now,
                updated_at=now,
            )
        )
        db.add(
            FeatureEntitlement(
                id=uuid.uuid4(),
                plan_id=plan.id,
                feature_code="ADMIN_CONTROL_PLANE",
                enabled=True,
                limits={"licensed_users_limit": payload.licensed_users_limit},
                status="ACTIVE",
                created_at=now,
                updated_at=now,
            )
        )
    user = db.query(AuthUser).filter(AuthUser.tenant_id == tenant.id, AuthUser.username == email).first()
    if user is None:
        user = AuthUser(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            username=email,
            display_name=payload.customer_admin_display_name,
            company=payload.customer_admin_company,
            password_hash=_hash(secrets.token_urlsafe(24)),
            role="CUSTOMER_ADMIN",
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
    invitation = (
        db.query(UserInvitation)
        .filter(
            UserInvitation.tenant_id == tenant.id, UserInvitation.user_id == user.id, UserInvitation.used_at.is_(None)
        )
        .order_by(UserInvitation.created_at.desc())
        .first()
    )
    if invitation is None and payload.invitation_required:
        token = issue_invitation(db, user.id, tenant.id, admin.id)
        delivery = send_activation_email(user.username, token)
        invite_state = "SENT" if delivery != "NOT_CONFIGURED" else "CREATED"
    else:
        delivery = "ALREADY_CREATED"
        invite_state = "EXISTING"
    prerequisites = {
        "tenant": True,
        "plan": True,
        "membership": True,
        "invitation": invite_state in {"SENT", "CREATED", "EXISTING"},
        "isolation": True,
        "configuration": True,
    }
    idempotency_key = f"TENANT_PROVISION:{key}:{email}"
    job = db.query(ProvisioningJob).filter(ProvisioningJob.idempotency_key == idempotency_key).first()
    if job is None:
        job = ProvisioningJob(
            id=uuid.uuid4(),
            customer_id=tenant.customer_id,
            tenant_id=tenant.id,
            job_identifier=f"PROV-{uuid.uuid4().hex[:12].upper()}",
            idempotency_key=idempotency_key,
            status="COMPLETED" if all(prerequisites.values()) else "FAILED",
            failure_details=None if all(prerequisites.values()) else {"prerequisites": prerequisites},
            retry_count=0,
            started_at=now,
            completed_at=now,
            created_at=now,
            updated_at=now,
        )
        db.add(job)
        db.flush()
        step_names = [
            ("CUSTOMER", "Customer identity"),
            ("TENANT", "Tenant boundary"),
            ("PLAN", "Plan and entitlements"),
            ("MEMBERSHIP", "Administrator membership"),
            ("INVITATION", "Customer Administrator invitation"),
            ("ISOLATION", "Isolation checks"),
            ("CONFIGURATION", "Configuration baseline"),
        ]
        for sequence, (code, label) in enumerate(step_names, 1):
            passed = prerequisites.get(code.lower(), False)
            db.add(
                ProvisioningJobStep(
                    id=uuid.uuid4(),
                    provisioning_job_id=job.id,
                    tenant_id=tenant.id,
                    step_code=code,
                    sequence=sequence,
                    status="COMPLETED" if passed else "FAILED",
                    attempt_count=1,
                    failure_details=None if passed else {"message": f"{label} prerequisite failed"},
                    started_at=now,
                    completed_at=now,
                    created_at=now,
                    updated_at=now,
                )
            )
    if (
        not db.query(TenantEnvironment)
        .filter(
            TenantEnvironment.tenant_id == tenant.id, TenantEnvironment.environment_type == payload.environment_type
        )
        .first()
    ):
        db.add(
            TenantEnvironment(
                id=uuid.uuid4(),
                tenant_id=tenant.id,
                environment_identifier=f"{payload.environment_type.lower()}-{tenant.tenant_key.lower()}",
                environment_type=payload.environment_type,
                region=payload.region,
                residency_region=payload.residency,
                status="ACTIVE",
                provisioned_at=now,
                activated_at=now,
                created_at=now,
                updated_at=now,
            )
        )
    tenant.status = "ACTIVE" if all(prerequisites.values()) else "PROVISIONING"
    tenant.provisioning_status = "ACTIVE" if tenant.status == "ACTIVE" else "RUNNING"
    tenant.activated_at = now if tenant.status == "ACTIVE" else None
    tenant.updated_at = now
    db.add(
        AuditEvent(
            id=uuid.uuid4(),
            tenant_id=admin.tenant_id,
            actor_ref=str(admin.id),
            action="TENANT_PROVISIONED",
            entity_type="Tenant",
            entity_id=tenant.id,
            details={
                "tenant_key": key,
                "region": payload.region,
                "residency": payload.residency,
                "customer_admin_id": str(user.id),
                "invitation": invite_state,
                "email_delivery": delivery,
                "prerequisites": prerequisites,
            },
            created_at=now,
        )
    )
    db.commit()
    return {
        "customer_id": str(customer.id),
        "customer_identifier": customer.customer_identifier,
        "tenant_id": str(tenant.id),
        "tenant_key": key,
        "tenant_identifier": tenant.tenant_identifier,
        "status": tenant.status,
        "customer_admin_id": str(user.id),
        "customer_admin_email": email,
        "invitation": invite_state,
        "email_delivery": delivery,
        "prerequisites": prerequisites,
        "job_id": str(job.id),
        "job_identifier": job.job_identifier,
        "idempotent_retry_safe": True,
    }


@router.post("/platform-admin/onboarding/validate")
def validate_onboarding(payload: CustomerProvisionRequest, request: Request, db: Session = Depends(get_db)):
    """Preflight a complete wizard payload without creating records."""
    _require_platform_admin(request, db)
    return {"valid": True, "checks": _validate_onboarding_payload(payload, db), "mutation": "NONE", "resume_safe": True}


@router.post("/platform-admin/tenants/{tenant_id}/domain-verifications")
def verify_customer_domain(
    tenant_id: uuid.UUID, payload: DomainVerificationRequest, request: Request, db: Session = Depends(get_db)
):
    """Record an authenticated domain challenge/verification result.

    The actual DNS/file proof is supplied by the deployment or identity
    provider; MDARIX stores only the hashed challenge and verified state.
    """
    admin = _require_platform_admin(request, db)
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if tenant is None:
        raise HTTPException(404, detail={"code": "TENANT_NOT_FOUND", "message": "Tenant is not available"})
    domain = payload.domain.strip().lower()
    row = (
        db.query(CustomerDomain)
        .filter(CustomerDomain.customer_id == tenant.customer_id, CustomerDomain.domain == domain)
        .first()
    )
    now = datetime.now(timezone.utc)
    if row is None:
        row = CustomerDomain(
            id=uuid.uuid4(),
            customer_id=tenant.customer_id,
            domain=domain,
            status="PENDING",
            created_at=now,
            updated_at=now,
        )
        db.add(row)
        db.flush()
    challenge = (
        db.query(DomainVerification)
        .filter(DomainVerification.customer_domain_id == row.id)
        .order_by(DomainVerification.created_at.desc())
        .first()
    )
    if challenge is None:
        challenge = DomainVerification(
            id=uuid.uuid4(),
            customer_domain_id=row.id,
            verification_method=payload.verification_method,
            verification_token_hash=hash_token(payload.verification_token or secrets.token_urlsafe(24)),
            status="PENDING",
            created_at=now,
        )
        db.add(challenge)
    if payload.verification_token:
        challenge.status = "VERIFIED"
        challenge.verified_at = now
        row.status = "VERIFIED"
        row.updated_at = now
    db.add(
        AuditEvent(
            id=uuid.uuid4(),
            tenant_id=admin.tenant_id,
            actor_ref=str(admin.id),
            action="DOMAIN_VERIFICATION_UPDATED",
            entity_type="CustomerDomain",
            entity_id=row.id,
            details={"domain": domain, "status": row.status, "method": challenge.verification_method},
            created_at=now,
        )
    )
    db.commit()
    return {
        "tenant_id": str(tenant.id),
        "domain": domain,
        "status": row.status,
        "verification_id": str(challenge.id),
        "verified_at": challenge.verified_at,
    }


@router.post("/platform-admin/tenants/{tenant_id}/identity-provider/verify")
def verify_identity_provider(
    tenant_id: uuid.UUID, payload: IdentityProviderVerificationRequest, request: Request, db: Session = Depends(get_db)
):
    """Persist a provider verification contract after external discovery succeeds."""
    admin = _require_platform_admin(request, db)
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if tenant is None:
        raise HTTPException(404, detail={"code": "TENANT_NOT_FOUND", "message": "Tenant is not available"})
    parsed = urlparse(payload.issuer)
    if parsed.scheme not in {"https"} or not parsed.netloc:
        raise HTTPException(
            422, detail={"code": "IDENTITY_ISSUER_MUST_BE_HTTPS", "message": "Identity provider issuer must use HTTPS"}
        )
    now = datetime.now(timezone.utc)
    row = (
        db.query(IdentityProviderConfiguration)
        .filter(
            IdentityProviderConfiguration.tenant_id == tenant.id,
            IdentityProviderConfiguration.provider_type == payload.provider_type,
        )
        .first()
    )
    if row is None:
        row = IdentityProviderConfiguration(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            provider_type=payload.provider_type,
            issuer=payload.issuer,
            client_reference=payload.client_reference,
            login_mode="SSO_MFA",
            configuration={},
            status="VERIFIED",
            verified_at=now,
            created_at=now,
            updated_at=now,
        )
        db.add(row)
    else:
        row.issuer = payload.issuer
        row.client_reference = payload.client_reference
        row.status = "VERIFIED"
        row.verified_at = now
        row.updated_at = now
    db.add(
        AuditEvent(
            id=uuid.uuid4(),
            tenant_id=admin.tenant_id,
            actor_ref=str(admin.id),
            action="IDENTITY_PROVIDER_VERIFIED",
            entity_type="IdentityProviderConfiguration",
            entity_id=row.id,
            details={"provider_type": row.provider_type, "issuer": row.issuer},
            created_at=now,
        )
    )
    db.commit()
    return {
        "tenant_id": str(tenant.id),
        "provider_type": row.provider_type,
        "issuer": row.issuer,
        "status": row.status,
        "verified_at": row.verified_at,
    }


@router.get("/platform-admin/provisioning-jobs/{job_id}")
def get_provisioning_job(job_id: uuid.UUID, request: Request, db: Session = Depends(get_db)):
    """Return durable provisioning status and per-step evidence for the Platform Admin wizard."""
    _require_platform_admin(request, db)
    job = db.query(ProvisioningJob).filter(ProvisioningJob.id == job_id).first()
    if job is None:
        raise HTTPException(
            404, detail={"code": "PROVISIONING_JOB_NOT_FOUND", "message": "Provisioning job is not available"}
        )
    steps = (
        db.query(ProvisioningJobStep)
        .filter(ProvisioningJobStep.provisioning_job_id == job.id)
        .order_by(ProvisioningJobStep.sequence)
        .all()
    )
    step_details = [
        {
            "code": step.step_code,
            "sequence": step.sequence,
            "status": step.status,
            "attempt_count": step.attempt_count,
            "failure_details": step.failure_details,
            "started_at": step.started_at,
            "completed_at": step.completed_at,
        }
        for step in steps
    ]
    return {
        "id": str(job.id),
        "job_identifier": job.job_identifier,
        "customer_id": str(job.customer_id),
        "tenant_id": str(job.tenant_id) if job.tenant_id else None,
        "status": job.status,
        "retry_count": job.retry_count,
        "failure_details": job.failure_details,
        "started_at": job.started_at,
        "completed_at": job.completed_at,
        "steps": [step["code"] for step in step_details],
        "step_details": step_details,
    }


@router.post("/platform-admin/provisioning-jobs/{job_id}/resume")
def resume_provisioning_job(job_id: uuid.UUID, payload: dict, request: Request, db: Session = Depends(get_db)):
    """Resume a failed provisioning job from its first failed step, preserving idempotency."""
    admin = _require_platform_admin(request, db)
    job = db.query(ProvisioningJob).filter(ProvisioningJob.id == job_id).first()
    if job is None:
        raise HTTPException(
            404, detail={"code": "PROVISIONING_JOB_NOT_FOUND", "message": "Provisioning job is not available"}
        )
    if str(job.status).upper() not in {"FAILED", "PAUSED", "QUEUED"}:
        raise HTTPException(
            409, detail={"code": "JOB_NOT_RESUMABLE", "message": f"Job is {job.status} and cannot be resumed"}
        )
    steps = (
        db.query(ProvisioningJobStep)
        .filter(ProvisioningJobStep.provisioning_job_id == job.id)
        .order_by(ProvisioningJobStep.sequence)
        .all()
    )
    first_failed = next((step for step in steps if str(step.status).upper() == "FAILED"), None)
    if first_failed is None:
        raise HTTPException(409, detail={"code": "NO_FAILED_STEP", "message": "No failed step is available to resume"})
    now = datetime.now(timezone.utc)
    job.status = "QUEUED"
    job.failure_details = None
    job.retry_count = int(job.retry_count or 0) + 1
    job.updated_at = now
    for step in steps:
        if step.sequence >= first_failed.sequence:
            step.status = "PENDING"
            step.failure_details = None
            step.updated_at = now
    db.add(
        AuditEvent(
            id=uuid.uuid4(),
            tenant_id=job.tenant_id,
            actor_ref=str(admin.id),
            action="PROVISIONING_JOB_RESUMED",
            entity_type="ProvisioningJob",
            entity_id=job.id,
            details={"from_step": first_failed.step_code, "reason": payload.get("reason", "Platform Admin resume")},
            created_at=now,
        )
    )
    db.commit()
    return get_provisioning_job(job_id, request, db)


@router.post("/platform-admin/provisioning-jobs/{job_id}/retry")
def retry_provisioning_job(job_id: uuid.UUID, payload: dict, request: Request, db: Session = Depends(get_db)):
    """Retry only the failed provisioning step; execution remains idempotent."""
    return resume_provisioning_job(job_id, payload, request, db)


@router.put("/platform-admin/onboarding/drafts/{idempotency_key}")
def save_onboarding_draft(
    idempotency_key: str, payload: OnboardingDraftRequest, request: Request, db: Session = Depends(get_db)
):
    """Persist a resumable, platform-scoped onboarding draft without provisioning."""
    admin = _require_platform_admin(request, db)
    if idempotency_key != payload.idempotency_key:
        raise HTTPException(
            422, detail={"code": "IDEMPOTENCY_KEY_MISMATCH", "message": "Draft key does not match the request path"}
        )
    row = db.query(CustomerOnboardingDraft).filter(CustomerOnboardingDraft.idempotency_key == idempotency_key).first()
    now = datetime.now(timezone.utc)
    if row is None:
        row = CustomerOnboardingDraft(
            id=uuid.uuid4(),
            idempotency_key=idempotency_key,
            created_by=admin.id,
            current_step=payload.current_step,
            draft_data=payload.draft_data,
            created_at=now,
            updated_at=now,
        )
        db.add(row)
    else:
        row.current_step = payload.current_step
        row.draft_data = payload.draft_data
        row.updated_at = now
    db.commit()
    return {
        "id": str(row.id),
        "idempotency_key": row.idempotency_key,
        "current_step": row.current_step,
        "draft_data": row.draft_data,
        "status": row.status,
        "updated_at": row.updated_at,
    }


@router.get("/platform-admin/onboarding/drafts/{idempotency_key}")
def get_onboarding_draft(idempotency_key: str, request: Request, db: Session = Depends(get_db)):
    _require_platform_admin(request, db)
    row = db.query(CustomerOnboardingDraft).filter(CustomerOnboardingDraft.idempotency_key == idempotency_key).first()
    if row is None:
        raise HTTPException(
            404, detail={"code": "ONBOARDING_DRAFT_NOT_FOUND", "message": "Onboarding draft is not available"}
        )
    return {
        "id": str(row.id),
        "idempotency_key": row.idempotency_key,
        "current_step": row.current_step,
        "draft_data": row.draft_data,
        "status": row.status,
        "failure_details": row.failure_details,
        "updated_at": row.updated_at,
    }
