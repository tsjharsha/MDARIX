"""Platform-controlled customer and tenant lifecycle records."""

import uuid

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    ForeignKey,
    ForeignKeyConstraint,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base
from backend.app.db.business_id import business_id_column
from backend.app.db.models.foundation import tenant_fk, tz, uuid_pk


class Customer(Base):
    __tablename__ = "customers"
    business_id: Mapped[str] = business_id_column()
    id = uuid_pk()
    customer_identifier: Mapped[str] = mapped_column(String(40), nullable=False, unique=True)
    legal_name: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    trading_name: Mapped[str | None] = mapped_column(String(255))
    customer_type: Mapped[str] = mapped_column(String(80), nullable=False)
    industry: Mapped[str | None] = mapped_column(String(120))
    company_size: Mapped[str | None] = mapped_column(String(80))
    country: Mapped[str] = mapped_column(String(80), nullable=False)
    state_province: Mapped[str | None] = mapped_column(String(120))
    headquarters: Mapped[str | None] = mapped_column(String(255))
    website: Mapped[str | None] = mapped_column(String(500))
    crm_reference: Mapped[str | None] = mapped_column(String(160))
    primary_business_contact: Mapped[dict | None] = mapped_column(JSONB)
    billing_contact: Mapped[dict | None] = mapped_column(JSONB)
    internal_account_owner: Mapped[str | None] = mapped_column(String(160))
    implementation_manager: Mapped[str | None] = mapped_column(String(160))
    lifecycle_status: Mapped[str] = mapped_column(String(40), nullable=False, server_default="DRAFT")
    lock_version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    updated_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    created_at = tz(False)
    updated_at = tz(False)
    __table_args__ = (
        CheckConstraint(
            "lifecycle_status in ('DRAFT','PENDING_APPROVAL','PROVISIONING','PROVISIONED','PENDING_CUSTOMER_ACTIVATION','ACTIVE','EXPIRING_SOON','EXPIRED','SUSPENDED','TERMINATED','ARCHIVED')",
            name="customer_lifecycle_status_allowed",
        ),
    )


class TenantEnvironment(Base):
    __tablename__ = "tenant_environments"
    id = uuid_pk()
    tenant_id = tenant_fk()
    environment_identifier: Mapped[str] = mapped_column(String(120), nullable=False)
    environment_type: Mapped[str] = mapped_column(String(30), nullable=False)
    region: Mapped[str] = mapped_column(String(80), nullable=False)
    residency_region: Mapped[str] = mapped_column(String(80), nullable=False)
    application_version: Mapped[str | None] = mapped_column(String(80))
    schema_version: Mapped[str | None] = mapped_column(String(80))
    configuration_version: Mapped[str | None] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(30), nullable=False, server_default="DRAFT")
    provisioned_at = tz()
    activated_at = tz()
    clone_source_environment_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    created_at = tz(False)
    updated_at = tz(False)
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "clone_source_environment_id"], ["tenant_environments.tenant_id", "tenant_environments.id"]
        ),
        UniqueConstraint("tenant_id", "environment_identifier", name="uq_tenant_environment_identifier"),
        UniqueConstraint("tenant_id", "environment_type", name="uq_tenant_environment_type"),
        UniqueConstraint("tenant_id", "id", name="uq_tenant_environment_tenant_id"),
        CheckConstraint(
            "environment_type in ('PRODUCTION','SANDBOX','VALIDATION','UAT','DEMO')",
            name="tenant_environment_type_allowed",
        ),
        CheckConstraint(
            "status in ('DRAFT','PROVISIONING','ACTIVE','SUSPENDED','ARCHIVED','FAILED')",
            name="tenant_environment_status_allowed",
        ),
    )


class TenantDataPlane(Base):
    """Server-side routing metadata for the isolated customer data plane.

    Secrets are deliberately not stored here. ``credential_ref`` points to a
    deployment secret, while ``database_ref`` identifies the approved data
    plane. The browser can never select or override these values.
    """

    __tablename__ = "tenant_data_planes"
    id = uuid_pk()
    # Removed with its organization (migration md22).
    tenant_id = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False)
    database_ref: Mapped[str] = mapped_column(String(160), nullable=False)
    connection_secret_ref: Mapped[str] = mapped_column(String(160), nullable=False)
    region: Mapped[str] = mapped_column(String(80), nullable=False)
    residency_region: Mapped[str] = mapped_column(String(80), nullable=False)
    schema_version: Mapped[str | None] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(30), nullable=False, server_default="PROVISIONING")
    created_at = tz(False)
    updated_at = tz(False)
    __table_args__ = (
        UniqueConstraint("tenant_id", name="uq_tenant_data_plane_tenant"),
        UniqueConstraint("database_ref", name="uq_tenant_data_plane_database_ref"),
        CheckConstraint(
            "status in ('PROVISIONING','ACTIVE','SUSPENDED','FAILED','RETIRED')",
            name="tenant_data_plane_status_allowed",
        ),
    )


class CustomerContact(Base):
    __tablename__ = "customer_contacts"
    id = uuid_pk()
    customer_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("customers.id"), nullable=False)
    contact_type: Mapped[str] = mapped_column(String(40), nullable=False)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    email: Mapped[str] = mapped_column(String(254), nullable=False)
    phone: Mapped[str | None] = mapped_column(String(60))
    status: Mapped[str] = mapped_column(String(30), nullable=False, server_default="ACTIVE")
    created_at = tz(False)
    updated_at = tz(False)
    __table_args__ = (UniqueConstraint("customer_id", "contact_type", "email", name="uq_customer_contact_type_email"),)


class CustomerDomain(Base):
    __tablename__ = "customer_domains"
    id = uuid_pk()
    customer_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("customers.id"), nullable=False)
    domain: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, server_default="PENDING")
    created_at = tz(False)
    updated_at = tz(False)
    __table_args__ = (UniqueConstraint("customer_id", "domain", name="uq_customer_domain"),)


class DomainVerification(Base):
    __tablename__ = "domain_verifications"
    id = uuid_pk()
    customer_domain_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("customer_domains.id"), nullable=False
    )
    verification_method: Mapped[str] = mapped_column(String(40), nullable=False)
    verification_token_hash: Mapped[str | None] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(30), nullable=False, server_default="PENDING")
    verified_at = tz()
    expires_at = tz()
    created_at = tz(False)


class IdentityProviderConfiguration(Base):
    __tablename__ = "identity_provider_configurations"
    id = uuid_pk()
    tenant_id = tenant_fk()
    provider_type: Mapped[str] = mapped_column(String(40), nullable=False)
    issuer: Mapped[str | None] = mapped_column(String(500))
    client_reference: Mapped[str | None] = mapped_column(String(255))
    login_mode: Mapped[str] = mapped_column(String(30), nullable=False, server_default="PASSWORD_MFA")
    configuration: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    status: Mapped[str] = mapped_column(String(30), nullable=False, server_default="PENDING")
    verified_at = tz()
    created_at = tz(False)
    updated_at = tz(False)
    __table_args__ = (
        UniqueConstraint("tenant_id", "provider_type", name="uq_tenant_identity_provider"),
        UniqueConstraint("tenant_id", "id", name="uq_identity_provider_tenant_id"),
    )


class SupportAccessGrant(Base):
    __tablename__ = "support_access_grants"
    id = uuid_pk()
    tenant_id = tenant_fk()
    platform_user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    scope: Mapped[dict] = mapped_column(JSONB, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, server_default="PENDING")
    # Who asked (md35): approval refuses the requester as well as the person who would receive the access.
    requested_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    approved_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    starts_at = tz(False)
    expires_at = tz(False)
    revoked_at = tz()
    created_at = tz(False)
    updated_at = tz(False)
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_support_access_grant_tenant_id"),
        CheckConstraint("expires_at > starts_at", name="support_access_expiry_after_start"),
    )


class Cell(Base):
    """A customer's tenant cell as the platform knows it (ADR-014, md36): where it runs and what it last reported.
    The platform never holds a credential for the cell's database; the cell calls in."""

    __tablename__ = "cells"
    id = uuid_pk()
    tenant_id = tenant_fk()
    hosting_mode: Mapped[str] = mapped_column(String(40), nullable=False)
    public_endpoint: Mapped[str | None] = mapped_column(String(500))
    enrollment_token_hash: Mapped[str | None] = mapped_column(String(64))
    enrolled_at = tz()
    client_certificate_fingerprint: Mapped[str | None] = mapped_column(String(128))
    software_version: Mapped[str | None] = mapped_column(String(80))
    schema_version: Mapped[str | None] = mapped_column(String(80))
    last_heartbeat_at = tz()
    health: Mapped[str | None] = mapped_column(String(30))
    status: Mapped[str] = mapped_column(String(30), nullable=False, server_default="PROVISIONING")
    # md37 (the platform-cell link): the cell's credential (hashed), the licence the platform last issued it, and
    # what its last heartbeat said (metadata only).
    credential_hash: Mapped[str | None] = mapped_column(String(64))
    licence_envelope: Mapped[dict | None] = mapped_column(JSONB)
    last_heartbeat: Mapped[dict | None] = mapped_column(JSONB)
    created_at = tz(False)
    updated_at = tz(False)
    __table_args__ = (
        UniqueConstraint("tenant_id", name="uq_cells_tenant"),
        UniqueConstraint("tenant_id", "id", name="uq_cells_tenant_id"),
        CheckConstraint(
            "hosting_mode in ('MDARIX_MANAGED','CUSTOMER_CLOUD','CUSTOMER_ON_PREM')", name="cell_hosting_mode_allowed"
        ),
        CheckConstraint("status in ('PROVISIONING','ACTIVE','SUSPENDED','RETIRED')", name="cell_status_allowed"),
    )


class CellHeartbeat(Base):
    """One heartbeat a cell sent the platform (md37): versions, health, job outcomes and counts. Never record
    content: the schema that accepts a heartbeat refuses free text (backend/app/cell_link_api.py)."""

    __tablename__ = "cell_heartbeats"
    id = uuid_pk()
    tenant_id = tenant_fk()
    cell_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("cells.id"), nullable=False)
    received_at = tz(False)
    software_version: Mapped[str | None] = mapped_column(String(80))
    schema_version: Mapped[str | None] = mapped_column(String(80))
    health: Mapped[str | None] = mapped_column(String(30))
    metrics: Mapped[dict] = mapped_column(JSONB, nullable=False)
    __table_args__ = (UniqueConstraint("tenant_id", "id", name="uq_cell_heartbeats_tenant_id"),)


class Package(Base):
    """A signed package the platform offers to cells (md37, ADR-014): reference data, mapping templates, policies.
    Stored as the signed envelope it was uploaded as; the platform never re-signs. Global, like plan definitions."""

    __tablename__ = "packages"
    id = uuid_pk()
    kind: Mapped[str] = mapped_column(String(40), nullable=False)
    code: Mapped[str] = mapped_column(String(120), nullable=False)
    version: Mapped[str] = mapped_column(String(40), nullable=False)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    key_id: Mapped[str] = mapped_column(String(80), nullable=False)
    envelope: Mapped[dict] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, server_default="RELEASED")
    released_at = tz()
    released_by: Mapped[str | None] = mapped_column(String(255))
    created_at = tz(False)
    updated_at = tz(False)
    __table_args__ = (
        UniqueConstraint("kind", "code", "version", name="uq_packages_kind_code_version"),
        CheckConstraint("status in ('RELEASED','WITHDRAWN')", name="package_status_allowed"),
    )


class CellPackageState(Base):
    """What a cell last reported about a package (md37): received, applied, failed or rejected."""

    __tablename__ = "cell_package_states"
    id = uuid_pk()
    tenant_id = tenant_fk()
    package_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("packages.id"), nullable=False)
    state: Mapped[str] = mapped_column(String(30), nullable=False)
    reported_at = tz(False)
    detail: Mapped[dict | None] = mapped_column(JSONB)
    __table_args__ = (
        UniqueConstraint("tenant_id", "package_id", name="uq_cell_package_states_tenant_package"),
        UniqueConstraint("tenant_id", "id", name="uq_cell_package_states_tenant_id"),
    )


class ReceivedPackage(Base):
    """A package a cell fetched from the platform (md37), as received and verified against the pinned key: its
    status says whether it was applied (licences, automatically), offered to the administrator, failed or rejected."""

    __tablename__ = "received_packages"
    id = uuid_pk()
    tenant_id = tenant_fk()
    kind: Mapped[str] = mapped_column(String(40), nullable=False)
    code: Mapped[str] = mapped_column(String(120), nullable=False)
    version: Mapped[str] = mapped_column(String(40), nullable=False)
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    key_id: Mapped[str] = mapped_column(String(80), nullable=False)
    envelope: Mapped[dict] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    received_at = tz(False)
    applied_at = tz()
    detail: Mapped[dict | None] = mapped_column(JSONB)
    __table_args__ = (UniqueConstraint("tenant_id", "id", name="uq_received_packages_tenant_id"),)


class CellLicence(Base):
    """A licence applied in a cell (backend/app/cell_licence.py): the signed document as received, so what the
    organization runs under can always be shown and re-verified."""

    __tablename__ = "cell_licences"
    id = uuid_pk()
    tenant_id = tenant_fk()
    content_sha256: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    key_id: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    issued_at = tz(False)
    valid_until = tz()
    applied_at = tz(False)
    envelope: Mapped[dict] = mapped_column(JSONB, nullable=False)
    __table_args__ = (UniqueConstraint("tenant_id", "id", name="uq_cell_licences_tenant_id"),)


class SubscriptionVersion(Base):
    __tablename__ = "subscription_versions"
    id = uuid_pk()
    tenant_id = tenant_fk()
    subscription_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    snapshot: Mapped[dict] = mapped_column(JSONB, nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    created_at = tz(False)
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "subscription_id"], ["subscription_lifecycles.tenant_id", "subscription_lifecycles.id"]
        ),
        UniqueConstraint("tenant_id", "subscription_id", "version", name="uq_subscription_version"),
        UniqueConstraint("tenant_id", "id", name="uq_subscription_version_tenant_id"),
    )


class LicenseTransition(Base):
    __tablename__ = "license_transitions"
    id = uuid_pk()
    tenant_id = tenant_fk()
    subscription_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    from_status: Mapped[str | None] = mapped_column(String(40))
    to_status: Mapped[str] = mapped_column(String(40), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    effective_at = tz(False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    created_at = tz(False)
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "subscription_id"], ["subscription_lifecycles.tenant_id", "subscription_lifecycles.id"]
        ),
        UniqueConstraint("tenant_id", "id", name="uq_license_transition_tenant_id"),
    )


class GracePeriodException(Base):
    __tablename__ = "grace_period_exceptions"
    id = uuid_pk()
    tenant_id = tenant_fk()
    subscription_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    starts_at = tz(False)
    expires_at = tz(False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    approved_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, server_default="ACTIVE")
    created_at = tz(False)
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "subscription_id"], ["subscription_lifecycles.tenant_id", "subscription_lifecycles.id"]
        ),
        CheckConstraint("expires_at > starts_at", name="grace_exception_expiry_after_start"),
        UniqueConstraint("tenant_id", "id", name="uq_grace_period_exception_tenant_id"),
    )


class PlanVersionAssignment(Base):
    __tablename__ = "plan_version_assignments"
    id = uuid_pk()
    tenant_id = tenant_fk()
    plan_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("plan_definitions.id"), nullable=False)
    plan_version: Mapped[str] = mapped_column(String(40), nullable=False)
    effective_from = tz(False)
    effective_to = tz()
    status: Mapped[str] = mapped_column(String(30), nullable=False, server_default="ACTIVE")
    created_at = tz(False)
    updated_at = tz(False)
    __table_args__ = (
        UniqueConstraint("tenant_id", "plan_id", "plan_version", name="uq_plan_version_assignment"),
        UniqueConstraint("tenant_id", "id", name="uq_plan_version_assignment_tenant_id"),
    )


class EntitlementSnapshot(Base):
    __tablename__ = "entitlement_snapshots"
    id = uuid_pk()
    tenant_id = tenant_fk()
    plan_version_assignment_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    version: Mapped[str] = mapped_column(String(40), nullable=False)
    entitlements: Mapped[dict] = mapped_column(JSONB, nullable=False)
    effective_at = tz(False)
    created_at = tz(False)
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "plan_version_assignment_id"],
            ["plan_version_assignments.tenant_id", "plan_version_assignments.id"],
        ),
        UniqueConstraint("tenant_id", "version", name="uq_entitlement_snapshot_version"),
        UniqueConstraint("tenant_id", "id", name="uq_entitlement_snapshot_tenant_id"),
    )


class UsageQuotaSnapshot(Base):
    __tablename__ = "usage_quota_snapshots"
    id = uuid_pk()
    tenant_id = tenant_fk()
    captured_at = tz(False)
    active_users: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    storage_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    api_requests: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    ai_tokens: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    quota: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    created_at = tz(False)
    __table_args__ = (
        UniqueConstraint("tenant_id", "captured_at", name="uq_usage_quota_snapshot_time"),
        UniqueConstraint("tenant_id", "id", name="uq_usage_quota_snapshot_tenant_id"),
    )


class RenewalRequest(Base):
    __tablename__ = "renewal_requests"
    id = uuid_pk()
    tenant_id = tenant_fk()
    subscription_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    requested_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    request_details: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    status: Mapped[str] = mapped_column(String(30), nullable=False, server_default="REQUESTED")
    resolved_at = tz()
    created_at = tz(False)
    updated_at = tz(False)
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "subscription_id"], ["subscription_lifecycles.tenant_id", "subscription_lifecycles.id"]
        ),
        UniqueConstraint("tenant_id", "id", name="uq_renewal_request_tenant_id"),
    )


class ReminderPolicyRecipient(Base):
    __tablename__ = "reminder_policy_recipients"
    id = uuid_pk()
    tenant_id = tenant_fk()
    reminder_policy_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    recipient_type: Mapped[str] = mapped_column(String(60), nullable=False)
    contact_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("customer_contacts.id"))
    status: Mapped[str] = mapped_column(String(30), nullable=False, server_default="ACTIVE")
    created_at = tz(False)
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "reminder_policy_id"],
            ["subscription_reminder_policies.tenant_id", "subscription_reminder_policies.id"],
        ),
        UniqueConstraint(
            "tenant_id", "reminder_policy_id", "recipient_type", "contact_id", name="uq_reminder_policy_recipient"
        ),
        UniqueConstraint("tenant_id", "id", name="uq_reminder_policy_recipient_tenant_id"),
    )


class CustomerOnboardingDraft(Base):
    __tablename__ = "customer_onboarding_drafts"
    id = uuid_pk()
    customer_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("customers.id"))
    idempotency_key: Mapped[str] = mapped_column(String(160), nullable=False, unique=True)
    current_step: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    draft_data: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    status: Mapped[str] = mapped_column(String(30), nullable=False, server_default="DRAFT")
    failure_details: Mapped[dict | None] = mapped_column(JSONB)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    created_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    created_at = tz(False)
    updated_at = tz(False)


class ProvisioningJob(Base):
    __tablename__ = "provisioning_jobs"
    id = uuid_pk()
    customer_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("customers.id"), nullable=False)
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id"))
    job_identifier: Mapped[str] = mapped_column(String(60), nullable=False, unique=True)
    idempotency_key: Mapped[str] = mapped_column(String(160), nullable=False, unique=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, server_default="QUEUED")
    failure_details: Mapped[dict | None] = mapped_column(JSONB)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    started_at = tz()
    completed_at = tz()
    created_at = tz(False)
    updated_at = tz(False)


class ProvisioningJobStep(Base):
    __tablename__ = "provisioning_job_steps"
    id = uuid_pk()
    provisioning_job_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("provisioning_jobs.id"), nullable=False
    )
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id"))
    step_code: Mapped[str] = mapped_column(String(80), nullable=False)
    sequence: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, server_default="PENDING")
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    failure_details: Mapped[dict | None] = mapped_column(JSONB)
    started_at = tz()
    completed_at = tz()
    created_at = tz(False)
    updated_at = tz(False)
    __table_args__ = (UniqueConstraint("provisioning_job_id", "step_code", name="uq_provisioning_job_step"),)


class ConfigurationBaseline(Base):
    __tablename__ = "configuration_baselines"
    id = uuid_pk()
    code: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, server_default="ACTIVE")
    created_at = tz(False)
    updated_at = tz(False)


class ConfigurationBaselineVersion(Base):
    __tablename__ = "configuration_baseline_versions"
    id = uuid_pk()
    baseline_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("configuration_baselines.id"), nullable=False
    )
    version: Mapped[str] = mapped_column(String(40), nullable=False)
    definition: Mapped[dict] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, server_default="DRAFT")
    released_at = tz()
    created_at = tz(False)
    updated_at = tz(False)
    __table_args__ = (UniqueConstraint("baseline_id", "version", name="uq_configuration_baseline_version"),)


class TenantBaselineAdoption(Base):
    __tablename__ = "tenant_baseline_adoptions"
    id = uuid_pk()
    tenant_id = tenant_fk()
    baseline_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("configuration_baseline_versions.id"), nullable=False
    )
    status: Mapped[str] = mapped_column(String(30), nullable=False, server_default="PENDING_REVIEW")
    adopted_at = tz()
    deferred_until = tz()
    created_at = tz(False)
    updated_at = tz(False)
    __table_args__ = (
        UniqueConstraint("tenant_id", "baseline_version_id", name="uq_tenant_baseline_adoption"),
        UniqueConstraint("tenant_id", "id", name="uq_tenant_baseline_adoption_tenant_id"),
    )


class BaselineDifference(Base):
    __tablename__ = "baseline_differences"
    id = uuid_pk()
    from_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("configuration_baseline_versions.id"), nullable=False
    )
    to_version_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("configuration_baseline_versions.id"), nullable=False
    )
    differences: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_at = tz(False)
    __table_args__ = (UniqueConstraint("from_version_id", "to_version_id", name="uq_baseline_difference_versions"),)


class BaselineAdoptionDecision(Base):
    __tablename__ = "baseline_adoption_decisions"
    id = uuid_pk()
    tenant_id = tenant_fk()
    adoption_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    decision: Mapped[str] = mapped_column(String(30), nullable=False)
    selected_changes: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    decided_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    decided_at = tz(False)
    created_at = tz(False)
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "adoption_id"], ["tenant_baseline_adoptions.tenant_id", "tenant_baseline_adoptions.id"]
        ),
        UniqueConstraint("tenant_id", "id", name="uq_baseline_adoption_decision_tenant_id"),
    )


class TenantHealthRun(Base):
    __tablename__ = "tenant_health_runs"
    id = uuid_pk()
    tenant_id = tenant_fk()
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    started_at = tz(False)
    completed_at = tz()
    summary: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    created_at = tz(False)
    __table_args__ = (UniqueConstraint("tenant_id", "id", name="uq_tenant_health_run_tenant_id"),)


class TenantServiceHealthCheck(Base):
    __tablename__ = "tenant_service_health_checks"
    id = uuid_pk()
    tenant_id = tenant_fk()
    health_run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    service: Mapped[str] = mapped_column(String(60), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    evidence: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    checked_at = tz(False)
    created_at = tz(False)
    __table_args__ = (
        ForeignKeyConstraint(["tenant_id", "health_run_id"], ["tenant_health_runs.tenant_id", "tenant_health_runs.id"]),
        UniqueConstraint("tenant_id", "health_run_id", "service", name="uq_tenant_service_health_check"),
        UniqueConstraint("tenant_id", "id", name="uq_tenant_service_health_check_tenant_id"),
    )


class TenantIsolationEvidence(Base):
    __tablename__ = "tenant_isolation_evidence"
    id = uuid_pk()
    tenant_id = tenant_fk()
    health_run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    boundary: Mapped[str] = mapped_column(String(60), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    evidence_reference: Mapped[str | None] = mapped_column(String(500))
    details: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    checked_at = tz(False)
    created_at = tz(False)
    __table_args__ = (
        ForeignKeyConstraint(["tenant_id", "health_run_id"], ["tenant_health_runs.tenant_id", "tenant_health_runs.id"]),
        UniqueConstraint("tenant_id", "health_run_id", "boundary", name="uq_tenant_isolation_evidence"),
        UniqueConstraint("tenant_id", "id", name="uq_tenant_isolation_evidence_tenant_id"),
    )


class PlatformIncident(Base):
    __tablename__ = "platform_incidents"
    business_id: Mapped[str] = business_id_column()
    id = uuid_pk()
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id"))
    incident_identifier: Mapped[str] = mapped_column(String(60), nullable=False, unique=True)
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    details: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    opened_at = tz(False)
    resolved_at = tz()
    created_at = tz(False)
    updated_at = tz(False)


class TenantAccessTransition(Base):
    __tablename__ = "tenant_access_transitions"
    id = uuid_pk()
    tenant_id = tenant_fk()
    transition_type: Mapped[str] = mapped_column(String(30), nullable=False)
    suspension_type: Mapped[str | None] = mapped_column(String(30))
    from_status: Mapped[str] = mapped_column(String(30), nullable=False)
    to_status: Mapped[str] = mapped_column(String(30), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    remarks: Mapped[str] = mapped_column(Text, nullable=False)
    effective_at = tz(False)
    notify_customer_admin: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    performed_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    created_at = tz(False)
    __table_args__ = (UniqueConstraint("tenant_id", "id", name="uq_tenant_access_transition_tenant_id"),)
