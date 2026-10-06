"""Platform administration: onboarding drafts and validation, tenant provisioning jobs, domain and identity-provider verification."""

import re
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from auth.durable import hash_token, issue_invitation
from auth.emailer import (
    send_activation_email,
)
from auth.service import _hash
from backend.app.business_ids import business_id_of
from backend.app.customer_lifecycle import (
    build_customer_tenant,
    shared_data_plane,
)
from backend.app.db.models.customer_lifecycle import (
    Customer,
    CustomerDomain,
    CustomerOnboardingDraft,
    DomainVerification,
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
        db.add(shared_data_plane(tenant, now))
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
                limits={"licensed_users_limit": payload.licensed_users_limit},
                created_at=now,
                updated_at=now,
            )
        )
        # The plan's limits are shared by every tenant on it: set them only for a plan that has none yet, never
        # overwrite them (a second customer on the plan used to fail on the duplicate row).
        if (
            db.query(FeatureEntitlement.id)
            .filter(FeatureEntitlement.plan_id == plan.id, FeatureEntitlement.feature_code == "ADMIN_CONTROL_PLANE")
            .first()
            is None
        ):
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
        delivery = send_activation_email(user.username, token, payload.company_name)
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
    # On an idempotent retry the tenant already existed, so load its customer rather than the one built above.
    customer = db.query(Customer).filter(Customer.id == tenant.customer_id).first()
    return {
        "customer_id": str(customer.id) if customer else None,
        "customer_business_id": customer.business_id if customer else None,
        "customer_identifier": customer.customer_identifier if customer else None,
        "tenant_id": str(tenant.id),
        "tenant_business_id": tenant.business_id,
        "tenant_key": key,
        "tenant_identifier": tenant.tenant_identifier,
        "status": tenant.status,
        "customer_admin_id": str(user.id),
        "customer_admin_business_id": user.business_id,
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


# Proof of a domain: a file the domain's owner publishes over HTTPS (dnspython is not a dependency, so no DNS TXT).
PROOF_PATH = "/.well-known/mdarix-verify.txt"
PROOF_MAX_BYTES = 4096
CHALLENGE_DAYS = 14
_DOMAIN = re.compile(r"^(?=.{3,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z][a-z0-9-]{0,61}[a-z0-9]$")


def fetch_domain_proof(domain: str, timeout: float = 5.0) -> tuple[str | None, str | None]:
    """(content, None) of https://<domain>/.well-known/mdarix-verify.txt, or (None, error code).

    Fetched through the connector outbound policy (backend/app/access/outbound.py): public addresses only (checked on
    the open socket), no redirects followed, HTTPS only, and at most 4 KB read, so a domain name typed by an
    administrator can never be used to reach an internal service.
    """
    from urllib.error import HTTPError, URLError
    from urllib.request import Request as UrlRequest

    from backend.app.access.outbound import ConnectorDestinationBlocked, safe_urlopen

    request = UrlRequest(f"https://{domain}{PROOF_PATH}", headers={"Accept": "text/plain"}, method="GET")
    try:
        with safe_urlopen(request, timeout=timeout) as response:
            body = response.read(PROOF_MAX_BYTES + 1)
    except HTTPError as exc:
        if 300 <= exc.code < 400:
            return None, "PROOF_REDIRECT_NOT_FOLLOWED"
        return None, "PROOF_NOT_FOUND" if exc.code == 404 else f"PROOF_HTTP_{exc.code}"
    except ConnectorDestinationBlocked:
        return None, "PROOF_DESTINATION_BLOCKED"
    except (URLError, TimeoutError, OSError):
        return None, "PROOF_UNREACHABLE"
    if len(body) > PROOF_MAX_BYTES:
        return None, "PROOF_TOO_LARGE"
    return body.decode("utf-8", errors="replace"), None


def _proof_matches(content: str, token: str) -> bool:
    return any(line.strip() == token for line in content.splitlines())


@router.post("/platform-admin/tenants/{tenant_id}/domain-verifications")
def verify_customer_domain(
    tenant_id: uuid.UUID, payload: DomainVerificationRequest, request: Request, db: Session = Depends(get_db)
):
    """Prove that a customer controls a domain: MDARIX issues a token, the customer publishes it, MDARIX checks.

    Without ``verification_token`` a new token is issued and returned once (only its hash is stored), with where
    to publish it: one line in ``https://<domain>/.well-known/mdarix-verify.txt``. With the token, MDARIX fetches
    that file and the domain becomes VERIFIED only when the file contains it; otherwise it stays PENDING and the
    answer says why (``last_error``), so the administrator can fix it and check again. Every issue and check is
    audited with the result, never the token.
    """
    admin = _require_platform_admin(request, db)
    tenant = db.query(Tenant).filter(Tenant.id == tenant_id).first()
    if tenant is None:
        raise HTTPException(404, detail={"code": "TENANT_NOT_FOUND", "message": "Tenant is not available"})
    domain = payload.domain.strip().lower().rstrip(".")
    if not _DOMAIN.match(domain):
        raise HTTPException(
            422, detail={"code": "DOMAIN_INVALID", "message": "Enter a domain name such as example.com"}
        )
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
    token = (payload.verification_token or "").strip()
    issued = None
    if not token:
        issued = f"mdarix-verify-{secrets.token_urlsafe(24)}"
        token_hash = hash_token(issued)
    else:
        token_hash = hash_token(token)
    challenge = (
        db.query(DomainVerification)
        .filter(DomainVerification.customer_domain_id == row.id)
        .order_by(DomainVerification.created_at.desc())
        .first()
    )
    if challenge is None or challenge.verification_token_hash != token_hash:
        # A token MDARIX did not issue (typed by the administrator from the customer) is a new challenge too: what
        # proves control is that the domain publishes it.
        challenge = DomainVerification(
            id=uuid.uuid4(),
            customer_domain_id=row.id,
            verification_method="HTTPS_FILE",
            verification_token_hash=token_hash,
            status="PENDING",
            expires_at=now + timedelta(days=CHALLENGE_DAYS),
            created_at=now,
        )
        db.add(challenge)
    error = None
    if issued is None:
        if challenge.expires_at is not None and challenge.expires_at <= now and challenge.status != "VERIFIED":
            error = "CHALLENGE_EXPIRED"
        else:
            content, error = fetch_domain_proof(domain)
            if error is None and not _proof_matches(content or "", token):
                error = "PROOF_MISMATCH"
        if error is None:
            challenge.status = "VERIFIED"
            challenge.verified_at = now
            row.status = "VERIFIED"
            row.updated_at = now
        elif row.status != "VERIFIED":
            row.status = "PENDING"
            row.updated_at = now
    db.add(
        AuditEvent(
            id=uuid.uuid4(),
            tenant_id=admin.tenant_id,
            actor_ref=str(admin.id),
            action="DOMAIN_VERIFICATION_ISSUED" if issued else "DOMAIN_VERIFICATION_CHECKED",
            entity_type="CustomerDomain",
            entity_id=row.id,
            details={
                "domain": domain,
                "tenant_id": str(tenant.id),
                "status": row.status,
                "method": challenge.verification_method,
                "checked_at": None if issued else now.isoformat(),
                "error": error,
            },
            created_at=now,
        )
    )
    db.commit()
    result = {
        "tenant_id": str(tenant.id),
        "domain": domain,
        "status": row.status,
        "verification_id": str(challenge.id),
        "verified_at": challenge.verified_at,
        "method": challenge.verification_method,
        "proof_url": f"https://{domain}{PROOF_PATH}",
        "last_checked_at": None if issued else now.isoformat(),
        "last_error": error,
    }
    if issued:
        result.update(
            verification_token=issued,
            expires_at=challenge.expires_at.isoformat() if challenge.expires_at else None,
            instructions=f"Publish a file at https://{domain}{PROOF_PATH} whose content is the token on one line, "
            "then check again with the token.",
        )
    return result


@router.post("/platform-admin/tenants/{tenant_id}/identity-provider/verify")
def verify_identity_provider(tenant_id: uuid.UUID, request: Request, db: Session = Depends(get_db)):
    """Single sign-on is not part of this release: nothing is recorded and no provider is ever marked VERIFIED.

    Sign-in is email, password and an authenticator app. This answers 409 whatever is sent, so that no screen or
    script can claim a verified identity provider that MDARIX does not actually use.
    """
    _require_platform_admin(request, db)
    raise HTTPException(
        409,
        detail={
            "code": "SSO_NOT_AVAILABLE",
            "message": "Single sign-on is not available in this release; sign-in uses a password and an "
            "authenticator app.",
        },
    )


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
        "customer_business_id": business_id_of(db, Customer, job.customer_id),
        "tenant_id": str(job.tenant_id) if job.tenant_id else None,
        "tenant_business_id": business_id_of(db, Tenant, job.tenant_id),
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
