"""Populate the four local validation tenants with production-shaped synthetic data.

This command writes only to the deterministic R1 validation tenants.  It is
idempotent and refuses to run unless ``--apply`` is supplied.  Identity,
commercial, configuration and health records stay in the control plane;
product, complaint, investigation, evidence and intelligence records are
written through the registered tenant data-plane resolver.
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from backend.app.db.data_plane import open_tenant_data_session  # noqa: E402
from backend.app.db.models.customer_lifecycle import (  # noqa: E402
    Customer,
    CustomerContact,
    CustomerDomain,
    DomainVerification,
    EntitlementSnapshot,
    IdentityProviderConfiguration,
    PlanVersionAssignment,
    ReminderPolicyRecipient,
    TenantEnvironment,
    TenantHealthRun,
    TenantIsolationEvidence,
    TenantServiceHealthCheck,
    UsageQuotaSnapshot,
)
from backend.app.db.models.enterprise import (  # noqa: E402
    ConnectorRun,
    ConnectorSourceRecord,
    ReconciliationRecord,
)
from backend.app.db.models.foundation import (  # noqa: E402
    AIExecution,
    AuthUser,
    Capa,
    ConnectorConfiguration,
    Control,
    Decision,
    Evidence,
    FailureChain,
    FailureChainEdge,
    FailureChainNode,
    FailureMode,
    FeatureEntitlement,
    HumanReview,
    Hypothesis,
    HypothesisEvidence,
    Investigation,
    MappingConfiguration,
    PlanDefinition,
    Product,
    ProductVersion,
    Risk,
    Scenario,
    Tenant,
    TenantPlanAssignment,
    Unknown,
)
from backend.app.db.models.reporting import ReportJob  # noqa: E402
from backend.app.db.models.stage2 import EmailTemplate, ReminderPolicy, SubscriptionLifecycle  # noqa: E402
from backend.app.db.session import SessionLocal  # noqa: E402
from backend.app.db.tenant_scope import bind_system  # noqa: E402
from backend.app.enterprise_audit import make_audit_event  # noqa: E402
from backend.app.role_codes import is_administrator_role  # noqa: E402
from backend.app.trial.sample_data import seed_sample_workspace  # noqa: E402

NOW = datetime(2026, 10, 5, 9, 0, tzinfo=timezone.utc)
PLAN_CODE = "MVP_VALIDATION"

TENANT_PROFILES = {
    "R1_TENANT_1": {
        "domain": "northstar-quality.synthetic.invalid",
        "region": "US-EAST",
        "sources": ("TRACKWISE", "TEAMCENTER", "ORACLE_ERP", "COUPA"),
    },
    "R1_TENANT_2": {
        "domain": "aster-medical.synthetic.invalid",
        "region": "EU-WEST",
        "sources": ("VEEVA_VAULT_QMS", "TEAMCENTER", "ORACLE_ERP", "COUPA"),
    },
    "R1_TENANT_3": {
        "domain": "nimbus-health.synthetic.invalid",
        "region": "US-CENTRAL",
        "sources": ("TRACKWISE", "PLM_SIMULATOR", "ERP_SIMULATOR", "SUPPLIER_SIMULATOR"),
    },
    "R1_TENANT_4": {
        "domain": "orbit-devices.synthetic.invalid",
        "region": "AP-SOUTH",
        "sources": ("VEEVA_VAULT_QMS", "TEAMCENTER", "ORACLE_ERP", "COUPA"),
    },
}

FEATURES = {
    "PRODUCT_360": {"enabled": True},
    "INVESTIGATIONS": {"enabled": True},
    "EVIDENCE_INTELLIGENCE": {"enabled": True},
    "ASK_MDARIX": {"enabled": True, "monthly_tokens": 500_000},
    "MAPPING_STUDIO": {"enabled": True},
    "REPORTS": {"enabled": True},
}


def _ensure_data_plane_identity(data, customer: Customer, tenant: Tenant) -> dict[str, int]:
    """Create only the identity rows required by data-plane foreign keys.

    Customer administration, memberships, credentials and commercial records
    remain in the control plane.  These two synchronized identity rows let the
    isolated business schema enforce its existing tenant foreign keys.
    """

    counts = {"customer_identity": 0, "tenant_identity": 0}
    local_customer = data.get(Customer, customer.id)
    if local_customer is None:
        identifier_owner = (
            data.query(Customer)
            .filter(Customer.customer_identifier == customer.customer_identifier)
            .first()
        )
        if identifier_owner is not None:
            raise RuntimeError(
                f"DATA_PLANE_CUSTOMER_IDENTITY_CONFLICT:{customer.customer_identifier}"
            )
        data.add(
            Customer(
                id=customer.id,
                customer_identifier=customer.customer_identifier,
                legal_name=customer.legal_name,
                display_name=customer.display_name,
                trading_name=customer.trading_name,
                customer_type=customer.customer_type,
                industry=customer.industry,
                company_size=customer.company_size,
                country=customer.country,
                state_province=customer.state_province,
                headquarters=customer.headquarters,
                website=customer.website,
                crm_reference=customer.crm_reference,
                primary_business_contact=None,
                billing_contact=None,
                internal_account_owner=None,
                implementation_manager=None,
                lifecycle_status=customer.lifecycle_status,
                lock_version=customer.lock_version,
                created_by=None,
                updated_by=None,
                created_at=customer.created_at or NOW,
                updated_at=customer.updated_at or NOW,
            )
        )
        data.flush()
        counts["customer_identity"] = 1

    local_tenant = data.get(Tenant, tenant.id)
    if local_tenant is None:
        key_owner = data.query(Tenant).filter(Tenant.tenant_key == tenant.tenant_key).first()
        if key_owner is not None:
            raise RuntimeError(f"DATA_PLANE_TENANT_IDENTITY_CONFLICT:{tenant.tenant_key}")
        data.add(
            Tenant(
                id=tenant.id,
                customer_id=customer.id,
                tenant_key=tenant.tenant_key,
                tenant_identifier=tenant.tenant_identifier,
                name=tenant.name,
                display_name=tenant.display_name,
                tenant_slug=tenant.tenant_slug,
                tenant_type=tenant.tenant_type,
                deployment_model=tenant.deployment_model,
                primary_region=tenant.primary_region,
                residency_region=tenant.residency_region,
                database_region=tenant.database_region,
                backup_region=tenant.backup_region,
                storage_region=tenant.storage_region,
                ai_processing_region=tenant.ai_processing_region,
                disaster_recovery_region=tenant.disaster_recovery_region,
                cross_border_processing_allowed=tenant.cross_border_processing_allowed,
                ai_processing_allowed=tenant.ai_processing_allowed,
                ai_monthly_token_budget=tenant.ai_monthly_token_budget,
                legal_hold=tenant.legal_hold,
                legal_hold_reason=None,
                legal_hold_set_at=None,
                legal_hold_set_by=None,
                application_version=tenant.application_version,
                schema_version=tenant.schema_version,
                configuration_version=tenant.configuration_version,
                provisioning_status=tenant.provisioning_status,
                status=tenant.status,
                activated_at=tenant.activated_at,
                suspended_at=tenant.suspended_at,
                terminated_at=tenant.terminated_at,
                lock_version=tenant.lock_version,
                created_at=tenant.created_at or NOW,
                updated_at=tenant.updated_at or NOW,
            )
        )
        data.flush()
        counts["tenant_identity"] = 1
    return counts


def _owned(tenant_id, source_identifier: str, days_ago: int = 10) -> dict:
    timestamp = NOW - timedelta(days=days_ago)
    return {
        "tenant_id": tenant_id,
        "source_system": "MVP_VALIDATION_SEED",
        "source_identifier": source_identifier,
        "source_timestamp": timestamp,
        "effective_timestamp": timestamp,
        "recorded_timestamp": timestamp,
        "ingestion_timestamp": NOW,
        "created_at": timestamp,
        "updated_at": NOW,
    }


def _shared_plan(db) -> PlanDefinition:
    plan = db.query(PlanDefinition).filter(PlanDefinition.code == PLAN_CODE).first()
    if plan is None:
        plan = PlanDefinition(
            id=uuid.uuid4(),
            code=PLAN_CODE,
            name="MVP Validation",
            description="Synthetic multi-tenant validation plan; not a commercial offer.",
            version="1.0",
            status="ACTIVE",
            effective_from=NOW - timedelta(days=30),
            created_at=NOW,
            updated_at=NOW,
        )
        db.add(plan)
        db.flush()
    for feature_code, limits in FEATURES.items():
        row = (
            db.query(FeatureEntitlement)
            .filter(FeatureEntitlement.plan_id == plan.id, FeatureEntitlement.feature_code == feature_code)
            .first()
        )
        if row is None:
            db.add(
                FeatureEntitlement(
                    id=uuid.uuid4(),
                    plan_id=plan.id,
                    feature_code=feature_code,
                    enabled=True,
                    limits=limits,
                    status="ACTIVE",
                    created_at=NOW,
                    updated_at=NOW,
                )
            )
    return plan


def _seed_customer_metadata(db, tenant: Tenant, profile: dict, plan: PlanDefinition) -> dict[str, int]:
    counts: dict[str, int] = {}
    users = db.query(AuthUser).filter(AuthUser.tenant_id == tenant.id).order_by(AuthUser.username).all()
    admin = next((row for row in users if is_administrator_role(row.role)), None) or (users[0] if users else None)
    if admin is None:
        raise RuntimeError(f"VALIDATION_TENANT_HAS_NO_USER:{tenant.tenant_key}")

    contact = (
        db.query(CustomerContact)
        .filter(CustomerContact.customer_id == tenant.customer_id, CustomerContact.contact_type == "PRIMARY_ADMIN")
        .first()
    )
    if contact is None:
        contact = CustomerContact(
            id=uuid.uuid4(),
            customer_id=tenant.customer_id,
            contact_type="PRIMARY_ADMIN",
            name=admin.display_name,
            email=admin.username,
            phone="+1-555-0100",
            status="ACTIVE",
            created_at=NOW,
            updated_at=NOW,
        )
        db.add(contact)
        counts["customer_contacts"] = 1
    else:
        counts["customer_contacts"] = 0

    domain = (
        db.query(CustomerDomain)
        .filter(CustomerDomain.customer_id == tenant.customer_id, CustomerDomain.domain == profile["domain"])
        .first()
    )
    if domain is None:
        domain = CustomerDomain(
            id=uuid.uuid4(),
            customer_id=tenant.customer_id,
            domain=profile["domain"],
            status="VERIFIED",
            created_at=NOW,
            updated_at=NOW,
        )
        db.add(domain)
        db.flush()
        counts["customer_domains"] = 1
    else:
        counts["customer_domains"] = 0
    verification = (
        db.query(DomainVerification).filter(DomainVerification.customer_domain_id == domain.id).first()
    )
    if verification is None:
        db.add(
            DomainVerification(
                id=uuid.uuid4(),
                customer_domain_id=domain.id,
                verification_method="SYNTHETIC_DNS",
                status="VERIFIED",
                verified_at=NOW,
                expires_at=NOW + timedelta(days=365),
                created_at=NOW,
            )
        )
        counts["domain_verifications"] = 1
    else:
        counts["domain_verifications"] = 0

    environments = 0
    for sequence, kind in enumerate(("PRODUCTION", "VALIDATION", "DEMO"), 1):
        row = (
            db.query(TenantEnvironment)
            .filter(TenantEnvironment.tenant_id == tenant.id, TenantEnvironment.environment_type == kind)
            .first()
        )
        if row is None:
            db.add(
                TenantEnvironment(
                    id=uuid.uuid4(),
                    tenant_id=tenant.id,
                    environment_identifier=f"{tenant.tenant_key}-ENV-{sequence:02d}",
                    environment_type=kind,
                    region=profile["region"],
                    residency_region=profile["region"],
                    application_version="1.0.0-mvp",
                    schema_version="md24schemadrift",
                    configuration_version="mvp-validation-1",
                    status="ACTIVE",
                    provisioned_at=NOW - timedelta(days=20 - sequence),
                    activated_at=NOW - timedelta(days=18 - sequence),
                    created_at=NOW,
                    updated_at=NOW,
                )
            )
            environments += 1
    counts["tenant_environments"] = environments

    identity = (
        db.query(IdentityProviderConfiguration)
        .filter(
            IdentityProviderConfiguration.tenant_id == tenant.id,
            IdentityProviderConfiguration.provider_type == "OIDC_SIMULATOR",
        )
        .first()
    )
    if identity is None:
        db.add(
            IdentityProviderConfiguration(
                id=uuid.uuid4(),
                tenant_id=tenant.id,
                provider_type="OIDC_SIMULATOR",
                issuer=f"https://idp.synthetic.invalid/{tenant.tenant_slug}",
                client_reference=f"synthetic-{tenant.tenant_slug}",
                login_mode="PASSWORD_MFA",
                configuration={"discovery": "simulated", "mfa_required": True},
                status="VERIFIED",
                verified_at=NOW,
                created_at=NOW,
                updated_at=NOW,
            )
        )
        counts["identity_provider_configurations"] = 1
    else:
        counts["identity_provider_configurations"] = 0

    assignment = (
        db.query(TenantPlanAssignment)
        .filter(TenantPlanAssignment.tenant_id == tenant.id, TenantPlanAssignment.status == "ACTIVE")
        .first()
    )
    if assignment is None:
        assignment = TenantPlanAssignment(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            plan_id=plan.id,
            status="ACTIVE",
            effective_from=NOW - timedelta(days=30),
            reason="Synthetic MVP validation coverage",
            limits={"licensed_users_limit": 25, "environment_limit": 3, "connector_limit": 8},
            created_at=NOW,
            updated_at=NOW,
        )
        db.add(assignment)
        counts["tenant_plan_assignments"] = 1
    else:
        counts["tenant_plan_assignments"] = 0

    version_assignment = (
        db.query(PlanVersionAssignment)
        .filter(
            PlanVersionAssignment.tenant_id == tenant.id,
            PlanVersionAssignment.plan_id == plan.id,
            PlanVersionAssignment.plan_version == plan.version,
        )
        .first()
    )
    if version_assignment is None:
        version_assignment = PlanVersionAssignment(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            plan_id=plan.id,
            plan_version=plan.version,
            effective_from=NOW - timedelta(days=30),
            status="ACTIVE",
            created_at=NOW,
            updated_at=NOW,
        )
        db.add(version_assignment)
        db.flush()
        counts["plan_version_assignments"] = 1
    else:
        counts["plan_version_assignments"] = 0

    entitlement = (
        db.query(EntitlementSnapshot)
        .filter(EntitlementSnapshot.tenant_id == tenant.id, EntitlementSnapshot.version == "mvp-validation-1")
        .first()
    )
    if entitlement is None:
        db.add(
            EntitlementSnapshot(
                id=uuid.uuid4(),
                tenant_id=tenant.id,
                plan_version_assignment_id=version_assignment.id,
                version="mvp-validation-1",
                entitlements=FEATURES,
                effective_at=NOW - timedelta(days=30),
                created_at=NOW,
            )
        )
        counts["entitlement_snapshots"] = 1
    else:
        counts["entitlement_snapshots"] = 0

    subscription = (
        db.query(SubscriptionLifecycle)
        .filter(SubscriptionLifecycle.tenant_id == tenant.id, SubscriptionLifecycle.status == "ACTIVE")
        .first()
    )
    if subscription is None:
        subscription = SubscriptionLifecycle(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            plan_id=plan.id,
            plan_version=plan.version,
            starts_at=NOW - timedelta(days=30),
            expires_at=NOW + timedelta(days=335),
            grace_ends_at=NOW + timedelta(days=365),
            status="ACTIVE",
            renewal_state="NOT_REQUESTED",
            created_at=NOW,
            updated_at=NOW,
        )
        db.add(subscription)
        counts["subscription_lifecycles"] = 1
    else:
        counts["subscription_lifecycles"] = 0

    reminder = (
        db.query(ReminderPolicy)
        .filter(ReminderPolicy.tenant_id == tenant.id, ReminderPolicy.name == "MVP renewal reminders")
        .first()
    )
    if reminder is None:
        reminder = ReminderPolicy(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            name="MVP renewal reminders",
            thresholds=[60, 30, 7],
            timezone="UTC",
            recipient_types=["CUSTOMER_ADMIN", "PRIMARY_CONTACT"],
            version="v1",
            status="ACTIVE",
            created_at=NOW,
            updated_at=NOW,
        )
        db.add(reminder)
        db.flush()
        counts["reminder_policies"] = 1
    else:
        counts["reminder_policies"] = 0
    recipient = (
        db.query(ReminderPolicyRecipient)
        .filter(
            ReminderPolicyRecipient.tenant_id == tenant.id,
            ReminderPolicyRecipient.reminder_policy_id == reminder.id,
            ReminderPolicyRecipient.contact_id == contact.id,
        )
        .first()
    )
    if recipient is None:
        db.add(
            ReminderPolicyRecipient(
                id=uuid.uuid4(),
                tenant_id=tenant.id,
                reminder_policy_id=reminder.id,
                recipient_type="PRIMARY_CONTACT",
                contact_id=contact.id,
                status="ACTIVE",
                created_at=NOW,
            )
        )
        counts["reminder_recipients"] = 1
    else:
        counts["reminder_recipients"] = 0
    template = (
        db.query(EmailTemplate)
        .filter(EmailTemplate.tenant_id == tenant.id, EmailTemplate.stage == "30_DAY", EmailTemplate.version == "v1")
        .first()
    )
    if template is None:
        db.add(
            EmailTemplate(
                id=uuid.uuid4(),
                tenant_id=tenant.id,
                stage="30_DAY",
                version="v1",
                subject="MDARIX validation subscription renewal reminder",
                body="Synthetic reminder for {{tenant_name}}; expires {{expires_at}}.",
                allowed_variables=["tenant_name", "expires_at"],
                status="ACTIVE",
                created_at=NOW,
                updated_at=NOW,
            )
        )
        counts["email_templates"] = 1
    else:
        counts["email_templates"] = 0

    snapshots = 0
    active_users = db.query(AuthUser).filter(AuthUser.tenant_id == tenant.id, AuthUser.status == "ACTIVE").count()
    for offset, api_requests, tokens in ((21, 3200, 12000), (14, 5100, 22000), (7, 7400, 36000)):
        captured_at = NOW - timedelta(days=offset)
        row = (
            db.query(UsageQuotaSnapshot)
            .filter(UsageQuotaSnapshot.tenant_id == tenant.id, UsageQuotaSnapshot.captured_at == captured_at)
            .first()
        )
        if row is None:
            db.add(
                UsageQuotaSnapshot(
                    id=uuid.uuid4(),
                    tenant_id=tenant.id,
                    captured_at=captured_at,
                    active_users=active_users,
                    storage_bytes=25_000_000 + offset * 100_000,
                    api_requests=api_requests,
                    ai_tokens=tokens,
                    quota={"users": 25, "storage_bytes": 1_000_000_000, "ai_tokens": 500_000},
                    created_at=NOW,
                )
            )
            snapshots += 1
    counts["usage_quota_snapshots"] = snapshots

    connectors = mappings = 0
    for source in profile["sources"]:
        connector_code = f"MVP-{source}"
        connector = (
            db.query(ConnectorConfiguration)
            .filter(
                ConnectorConfiguration.tenant_id == tenant.id,
                ConnectorConfiguration.code == connector_code,
                ConnectorConfiguration.version == "v1",
            )
            .first()
        )
        if connector is None:
            db.add(
                ConnectorConfiguration(
                    id=uuid.uuid4(),
                    tenant_id=tenant.id,
                    code=connector_code,
                    connector_type=source,
                    configuration={
                        "endpoint_mode": "LOCAL_SIMULATOR",
                        "pagination": "CURSOR",
                        "retry": {"attempts": 3, "backoff": "EXPONENTIAL"},
                        "schema_version": "mvp-1",
                    },
                    version="v1",
                    status="ACTIVE",
                    created_at=NOW,
                    updated_at=NOW,
                )
            )
            connectors += 1
        mapping_code = f"MVP-{source}-COMPLAINT"
        mapping = (
            db.query(MappingConfiguration)
            .filter(
                MappingConfiguration.tenant_id == tenant.id,
                MappingConfiguration.code == mapping_code,
                MappingConfiguration.version == "v1",
            )
            .first()
        )
        if mapping is None:
            db.add(
                MappingConfiguration(
                    id=uuid.uuid4(),
                    tenant_id=tenant.id,
                    code=mapping_code,
                    source_system=source,
                    target_entity="Complaint",
                    mapping_rules={
                        "source_id": "complaint_identifier",
                        "description": "description",
                        "status": "status",
                        "reported_at": "complaint_timestamp",
                    },
                    version="v1",
                    status="ACTIVE",
                    created_at=NOW,
                    updated_at=NOW,
                )
            )
            mappings += 1
    counts["connector_configurations"] = connectors
    counts["mapping_configurations"] = mappings

    health = db.query(TenantHealthRun).filter(TenantHealthRun.tenant_id == tenant.id).first()
    if health is None:
        health = TenantHealthRun(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            status="HEALTHY",
            started_at=NOW - timedelta(minutes=2),
            completed_at=NOW,
            summary={"checks": 6, "passed": 6, "scope": "synthetic MVP validation"},
            created_at=NOW,
        )
        db.add(health)
        db.flush()
        for service in ("DATABASE", "STORAGE", "IDENTITY", "INTEGRATIONS", "AI", "AUDIT"):
            db.add(
                TenantServiceHealthCheck(
                    id=uuid.uuid4(),
                    tenant_id=tenant.id,
                    health_run_id=health.id,
                    service=service,
                    status="PASS",
                    evidence={"mode": "LOCAL_SYNTHETIC", "checked": True},
                    checked_at=NOW,
                    created_at=NOW,
                )
            )
        for boundary in ("API", "SEARCH", "EXPORT", "ATTACHMENT", "AI_CONTEXT", "INGESTION"):
            db.add(
                TenantIsolationEvidence(
                    id=uuid.uuid4(),
                    tenant_id=tenant.id,
                    health_run_id=health.id,
                    boundary=boundary,
                    status="PASS",
                    evidence_reference=f"local://validation/{tenant.tenant_key}/{boundary.lower()}",
                    details={"synthetic": True, "cross_tenant_access": "DENIED"},
                    checked_at=NOW,
                    created_at=NOW,
                )
            )
        counts["tenant_health_runs"] = 1
        counts["tenant_service_health_checks"] = 6
        counts["tenant_isolation_evidence"] = 6
    else:
        counts["tenant_health_runs"] = 0
        counts["tenant_service_health_checks"] = 0
        counts["tenant_isolation_evidence"] = 0

    audit = make_audit_event(
        tenant_id=tenant.id,
        actor_ref="mvp-validation-seed",
        action="MVP_VALIDATION_DATASET_READY",
        entity_type="Tenant",
        entity_id=tenant.id,
        correlation_id=f"MVP-SEED-{tenant.tenant_key}",
        details={"synthetic": True, "sources": list(profile["sources"])},
        reason="Populate deterministic local data for tenant-isolation and workflow validation",
        new_values={"validation_dataset": "READY"},
        created_at=NOW,
    )
    from backend.app.db.models.foundation import AuditEvent

    existing_audit = (
        db.query(AuditEvent)
        .filter(AuditEvent.tenant_id == tenant.id, AuditEvent.correlation_id == f"MVP-SEED-{tenant.tenant_key}")
        .first()
    )
    if existing_audit is None:
        db.add(audit)
        counts["audit_events"] = 1
    else:
        counts["audit_events"] = 0

    tenant.ai_processing_allowed = True
    tenant.ai_monthly_token_budget = 500_000
    tenant.application_version = "1.0.0-mvp"
    tenant.configuration_version = "mvp-validation-1"
    tenant.primary_region = profile["region"]
    tenant.residency_region = profile["region"]
    tenant.updated_at = NOW
    return counts


def _seed_investigation_intelligence(
    data,
    customer: Customer,
    tenant: Tenant,
    sources: tuple[str, ...],
) -> dict[str, int]:
    counts = _ensure_data_plane_identity(data, customer, tenant)
    sample = seed_sample_workspace(data, tenant.id, NOW)
    counts.update({f"sample_{key}": int(value) for key, value in sample.items() if key != "created"})
    investigation = (
        data.query(Investigation)
        .filter(
            Investigation.tenant_id == tenant.id,
            Investigation.investigation_identifier == "SAMPLE-INV-001",
        )
        .one()
    )
    product = data.query(Product).filter(Product.tenant_id == tenant.id, Product.id == investigation.product_id).one()
    version = (
        data.query(ProductVersion)
        .filter(ProductVersion.tenant_id == tenant.id, ProductVersion.product_id == product.id)
        .order_by(ProductVersion.release_timestamp.desc())
        .first()
    )
    evidence = (
        data.query(Evidence)
        .filter(Evidence.tenant_id == tenant.id, Evidence.investigation_id == investigation.id)
        .order_by(Evidence.evidence_identifier)
        .all()
    )

    hypotheses: list[Hypothesis] = []
    hypothesis_specs = (
        ("The Rev B pressure sensor supplier change may be associated with the alarm trend.", "under_review"),
        ("Reduced incoming inspection sampling may have allowed out-of-range sensors into production.", "proposed"),
        ("Software alarm thresholds may interact with upper-range sensor variance.", "proposed"),
    )
    created = 0
    for index, (statement, status) in enumerate(hypothesis_specs, 1):
        source_id = f"MVP-HYP-{index:03d}"
        row = (
            data.query(Hypothesis)
            .filter(Hypothesis.tenant_id == tenant.id, Hypothesis.source_identifier == source_id)
            .first()
        )
        if row is None:
            row = Hypothesis(
                id=uuid.uuid4(),
                investigation_id=investigation.id,
                statement=statement,
                status=status,
                origin="human" if index == 1 else "ai",
                reviewer_disposition="REVIEW_REQUIRED",
                **_owned(tenant.id, source_id, 8 - index),
            )
            data.add(row)
            data.flush()
            created += 1
        hypotheses.append(row)
        if evidence:
            relation = (
                data.query(HypothesisEvidence)
                .filter(
                    HypothesisEvidence.tenant_id == tenant.id,
                    HypothesisEvidence.hypothesis_id == row.id,
                    HypothesisEvidence.evidence_id == evidence[(index - 1) % len(evidence)].id,
                )
                .first()
            )
            if relation is None:
                data.add(
                    HypothesisEvidence(
                        id=uuid.uuid4(),
                        tenant_id=tenant.id,
                        hypothesis_id=row.id,
                        evidence_id=evidence[(index - 1) % len(evidence)].id,
                        relation_type="support" if index < 3 else "contradict",
                        rationale="Synthetic relationship for evidence-review validation.",
                        created_by_type="system",
                        created_at=NOW,
                    )
                )
    counts["hypotheses"] = created

    unknowns = 0
    for index, (category, description, needed) in enumerate(
        (
            ("SUPPLIER", "Supplier process capability for the affected sensor lots is not confirmed.", "Supplier capability study"),
            ("DESIGN", "Upper-range alarm tolerance across temperature extremes is not confirmed.", "Environmental bench test"),
            ("LOT", "The full serial-number distribution across affected lots is incomplete.", "Returned-device serial reconciliation"),
        ),
        1,
    ):
        if (
            data.query(Unknown)
            .filter(Unknown.tenant_id == tenant.id, Unknown.description == description)
            .first()
            is None
        ):
            data.add(
                Unknown(
                    id=uuid.uuid4(),
                    tenant_id=tenant.id,
                    investigation_id=investigation.id,
                    hypothesis_id=hypotheses[(index - 1) % len(hypotheses)].id,
                    category=category,
                    description=description,
                    evidence_needed=needed,
                    status="open",
                    created_at=NOW - timedelta(days=5 - index),
                    updated_at=NOW,
                )
            )
            unknowns += 1
    counts["unknowns"] = unknowns

    chain = (
        data.query(FailureChain)
        .filter(FailureChain.tenant_id == tenant.id, FailureChain.name == "MVP validation failure chain")
        .first()
    )
    if chain is None:
        chain = FailureChain(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            investigation_id=investigation.id,
            name="MVP validation failure chain",
            status="under_review",
            created_at=NOW,
            updated_at=NOW,
        )
        data.add(chain)
        data.flush()
        nodes = []
        for sequence, (kind, label) in enumerate(
            (
                ("CHANGE", "Pressure-sensor supplier changed for Rev B"),
                ("COMPONENT", "Upper-range sensor output variance observed"),
                ("SIGNAL", "Pressure-alarm complaint rate increased"),
            ),
            1,
        ):
            node = FailureChainNode(
                id=uuid.uuid4(),
                tenant_id=tenant.id,
                failure_chain_id=chain.id,
                sequence_number=sequence,
                node_type=kind,
                label=label,
                evidence_id=evidence[min(sequence - 1, len(evidence) - 1)].id if evidence else None,
                created_at=NOW,
            )
            data.add(node)
            nodes.append(node)
        data.flush()
        for index in range(len(nodes) - 1):
            data.add(
                FailureChainEdge(
                    id=uuid.uuid4(),
                    tenant_id=tenant.id,
                    failure_chain_id=chain.id,
                    from_node_id=nodes[index].id,
                    to_node_id=nodes[index + 1].id,
                    edge_status="hypothesized" if index == 0 else "established_fact",
                    evidence_id=evidence[min(index, len(evidence) - 1)].id if evidence else None,
                    rationale="Synthetic, evidence-linked sequence for workflow validation.",
                    created_at=NOW,
                )
            )
        counts.update({"failure_chains": 1, "failure_chain_nodes": 3, "failure_chain_edges": 2})
    else:
        counts.update({"failure_chains": 0, "failure_chain_nodes": 0, "failure_chain_edges": 0})

    scenarios = 0
    for index, question in enumerate(
        (
            "Would the complaint trend remain if the previous sensor supplier were used?",
            "Would restored incoming inspection sampling detect the observed variance?",
        ),
        1,
    ):
        identifier = f"MVP-VAL-SCENARIO-{index:02d}"
        if (
            data.query(Scenario)
            .filter(Scenario.tenant_id == tenant.id, Scenario.scenario_identifier == identifier)
            .first()
            is None
        ):
            data.add(
                Scenario(
                    id=uuid.uuid4(),
                    investigation_id=investigation.id,
                    scenario_identifier=identifier,
                    question=question,
                    assumptions={"synthetic": True, "causality": "NOT_ESTABLISHED"},
                    uncertainty="Requires human review and additional evidence.",
                    status="draft",
                    **_owned(tenant.id, identifier, 3),
                )
            )
            scenarios += 1
    counts["scenarios"] = scenarios

    risk = data.query(Risk).filter(Risk.tenant_id == tenant.id, Risk.risk_identifier == "MVP-VAL-RISK-001").first()
    if risk is None:
        data.add(
            Risk(
                id=uuid.uuid4(),
                risk_identifier="MVP-VAL-RISK-001",
                product_id=product.id,
                product_version_id=version.id if version else None,
                description="Potential delayed or interrupted infusion following a false pressure alarm.",
                status="active",
                **_owned(tenant.id, "MVP-VAL-RISK-001", 7),
            )
        )
        counts["risks"] = 1
    else:
        counts["risks"] = 0
    failure = (
        data.query(FailureMode)
        .filter(FailureMode.tenant_id == tenant.id, FailureMode.failure_mode_identifier == "MVP-VAL-FM-001")
        .first()
    )
    if failure is None:
        data.add(
            FailureMode(
                id=uuid.uuid4(),
                failure_mode_identifier="MVP-VAL-FM-001",
                name="Pressure sensor output drifts high",
                description="Synthetic ISO 14971 workflow record.",
                **_owned(tenant.id, "MVP-VAL-FM-001", 7),
            )
        )
        counts["failure_modes"] = 1
    else:
        counts["failure_modes"] = 0
    control = (
        data.query(Control)
        .filter(Control.tenant_id == tenant.id, Control.control_identifier == "MVP-VAL-CTRL-001")
        .first()
    )
    if control is None:
        data.add(
            Control(
                id=uuid.uuid4(),
                control_identifier="MVP-VAL-CTRL-001",
                control_type="DETECTION",
                description="Incoming inspection verifies sensor output at upper pressure range.",
                status="active",
                **_owned(tenant.id, "MVP-VAL-CTRL-001", 7),
            )
        )
        counts["controls"] = 1
    else:
        counts["controls"] = 0
    capa = data.query(Capa).filter(Capa.tenant_id == tenant.id, Capa.capa_identifier == "MVP-VAL-CAPA-001").first()
    if capa is None:
        data.add(
            Capa(
                id=uuid.uuid4(),
                capa_identifier="MVP-VAL-CAPA-001",
                title="Restore enhanced sensor incoming inspection",
                action_type="CORRECTIVE",
                source_type="INVESTIGATION",
                source_reference=investigation.investigation_identifier,
                product_id=product.id,
                investigation_id=investigation.id,
                status="open",
                opened_at=NOW - timedelta(days=2),
                due_at=NOW + timedelta(days=30),
                **_owned(tenant.id, "MVP-VAL-CAPA-001", 2),
            )
        )
        counts["capas"] = 1
    else:
        counts["capas"] = 0

    execution = (
        data.query(AIExecution)
        .filter(
            AIExecution.tenant_id == tenant.id,
            AIExecution.requestor_ref == "mvp-validation-seed",
            AIExecution.investigation_id == investigation.id,
        )
        .first()
    )
    if execution is None:
        execution = AIExecution(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            investigation_id=investigation.id,
            requestor_ref="mvp-validation-seed",
            provider="controlled",
            model_name="synthetic-advisory",
            model_version="mvp-validation-v1",
            prompt_template_version="investigation-review-v1",
            orchestration_version="mvp-1",
            context_refs={"product_id": str(product.id), "investigation_id": str(investigation.id)},
            evidence_refs=[str(row.id) for row in evidence],
            tools_invoked=["authorized_context", "evidence_retrieval"],
            structured_input={"question": investigation.investigation_question},
            structured_output={
                "known": ["Complaint rate increased after Rev B"],
                "unknowns": ["Supplier process capability is not confirmed"],
                "causality_state": "NOT_ESTABLISHED",
            },
            rationale_summary="Synthetic advisory output; human review required.",
            confidence_label="MODERATE_EVIDENCE_COVERAGE",
            validation_status="READY_FOR_REVIEW",
            execution_timestamp=NOW,
            latency_ms=125,
        )
        data.add(execution)
        data.flush()
        counts["ai_executions"] = 1
    else:
        counts["ai_executions"] = 0

    decision = (
        data.query(Decision)
        .filter(Decision.tenant_id == tenant.id, Decision.decision_identifier == "MVP-VAL-DEC-001")
        .first()
    )
    if decision is None:
        decision = Decision(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            investigation_id=investigation.id,
            decision_identifier="MVP-VAL-DEC-001",
            decision_type="INVESTIGATION_DISPOSITION",
            disposition="CONTINUE_INVESTIGATION",
            rationale="Evidence supports continued investigation; causality is not established.",
            product_id=product.id,
            product_version_id=version.id if version else None,
            decision_status="READY_FOR_APPROVAL",
            decision_readiness="ADDITIONAL_EVIDENCE_REQUIRED",
            selected_action="COLLECT_SUPPLIER_CAPABILITY_DATA",
            human_decision="Continue investigation and collect the identified missing evidence.",
            limitations={"causality": "NOT_ESTABLISHED", "human_review_required": True},
            temporal_context={"mode": "CURRENT", "as_of": NOW.isoformat()},
            context_snapshot={"evidence_ids": [str(row.id) for row in evidence]},
            advisory_execution_id=execution.id,
            updated_at=NOW,
            decision_timestamp=NOW,
            authorized_by_ref="mvp.approver@synthetic.invalid",
            created_at=NOW,
        )
        data.add(decision)
        data.flush()
        counts["decisions"] = 1
    else:
        counts["decisions"] = 0
    review = (
        data.query(HumanReview)
        .filter(HumanReview.tenant_id == tenant.id, HumanReview.decision_id == decision.id)
        .first()
    )
    if review is None:
        data.add(
            HumanReview(
                id=uuid.uuid4(),
                tenant_id=tenant.id,
                investigation_id=investigation.id,
                ai_execution_id=execution.id,
                decision_id=decision.id,
                reviewer_ref="mvp.reviewer@synthetic.invalid",
                disposition="CHANGES_REQUESTED",
                comments="Obtain supplier capability evidence before final approval.",
                review_timestamp=NOW,
            )
        )
        counts["human_reviews"] = 1
    else:
        counts["human_reviews"] = 0

    runs = records = reconciliations = 0
    for index, source in enumerate(sources, 1):
        connection_id = f"mvp-validation-{source.lower()}"
        run = (
            data.query(ConnectorRun)
            .filter(ConnectorRun.tenant_id == tenant.id, ConnectorRun.connection_id == connection_id)
            .first()
        )
        if run is None:
            run = ConnectorRun(
                id=uuid.uuid4(),
                tenant_id=tenant.id,
                connection_id=connection_id,
                source_system=source,
                run_type="FULL",
                status="COMPLETED",
                records_received=3,
                records_accepted=2,
                records_rejected=0,
                records_quarantined=0,
                records_duplicate=1,
                retry_attempt=0,
                reconciliation_status="RECONCILED",
                schema_drift_status="MATCH",
                correlation_id=f"MVP-{tenant.tenant_key}-{source}",
                started_at=NOW - timedelta(minutes=10 + index),
                completed_at=NOW - timedelta(minutes=index),
                created_at=NOW,
            )
            data.add(run)
            data.flush()
            runs += 1
            for record_index in range(1, 3):
                data.add(
                    ConnectorSourceRecord(
                        id=uuid.uuid4(),
                        tenant_id=tenant.id,
                        connector_run_id=run.id,
                        source_system=source,
                        source_record_id=f"{tenant.tenant_key}-{source}-{record_index:03d}",
                        source_record_version="1",
                        fingerprint=uuid.uuid5(
                            uuid.NAMESPACE_URL, f"{tenant.tenant_key}:{source}:{record_index}"
                        ).hex,
                        processing_status="ACCEPTED",
                        effective_at=NOW - timedelta(days=record_index),
                        ingested_at=NOW,
                        created_at=NOW,
                    )
                )
                records += 1
            data.add(
                ReconciliationRecord(
                    id=uuid.uuid4(),
                    tenant_id=tenant.id,
                    connector_run_id=run.id,
                    expected_count=3,
                    received_count=3,
                    accepted_count=2,
                    rejected_count=0,
                    quarantined_count=0,
                    duplicate_count=1,
                    unresolved_count=0,
                    status="RECONCILED",
                    details={"synthetic": True, "source": source},
                    reconciled_at=NOW,
                    created_at=NOW,
                )
            )
            reconciliations += 1
    counts["connector_runs"] = runs
    counts["connector_source_records"] = records
    counts["connector_reconciliations"] = reconciliations

    reports = 0
    for report_code, output_format in (
        ("INVESTIGATION", "pdf"),
        ("EVIDENCE_PROVENANCE", "csv"),
        ("DECISION_BRIEF", "json"),
    ):
        row = (
            data.query(ReportJob)
            .filter(
                ReportJob.tenant_id == tenant.id,
                ReportJob.actor_id == "mvp-validation-seed",
                ReportJob.report_code == report_code,
                ReportJob.output_format == output_format,
            )
            .first()
        )
        if row is None:
            data.add(
                ReportJob(
                    id=uuid.uuid4(),
                    tenant_id=tenant.id,
                    actor_id="mvp-validation-seed",
                    report_code=report_code,
                    output_format=output_format,
                    context={
                        "investigation_id": str(investigation.id),
                        "product_id": str(product.id),
                        "synthetic": True,
                    },
                    hidden_fields=[],
                    status="QUEUED",
                    attempts=0,
                    report_version="1.0",
                    created_at=NOW,
                    updated_at=NOW,
                )
            )
            reports += 1
    counts["report_jobs"] = reports
    return counts


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--apply", action="store_true", help="write the synthetic validation dataset")
    args = parser.parse_args()
    if not args.apply:
        print("Dry run only. Re-run with --apply to populate the four synthetic validation tenants.")
        return 0

    report: dict[str, object] = {"scope": "synthetic MVP validation only", "tenants": {}}
    with SessionLocal() as control:
        bind_system(control, "seed local synthetic validation dataset")
        tenants = (
            control.query(Tenant)
            .filter(Tenant.tenant_key.in_(TENANT_PROFILES))
            .order_by(Tenant.tenant_key)
            .all()
        )
        found = {tenant.tenant_key for tenant in tenants}
        missing = sorted(set(TENANT_PROFILES) - found)
        if missing:
            raise RuntimeError(f"VALIDATION_TENANTS_MISSING:{','.join(missing)}")
        plan = _shared_plan(control)
        for tenant in tenants:
            profile = TENANT_PROFILES[tenant.tenant_key]
            customer = control.get(Customer, tenant.customer_id)
            if customer is None:
                raise RuntimeError(f"VALIDATION_CUSTOMER_MISSING:{tenant.tenant_key}")
            control_counts = _seed_customer_metadata(control, tenant, profile, plan)
            control.commit()
            try:
                with open_tenant_data_session(tenant.id) as data:
                    data_counts = _seed_investigation_intelligence(
                        data,
                        customer,
                        tenant,
                        profile["sources"],
                    )
                    data.commit()
            except Exception:
                control.rollback()
                raise
            report["tenants"][tenant.tenant_key] = {
                "display_name": tenant.display_name,
                "control_plane_added": control_counts,
                "data_plane_added": data_counts,
            }
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
