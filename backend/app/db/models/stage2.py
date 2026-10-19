"""Stage 2 durable platform primitives."""

import uuid

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base
from backend.app.db.business_id import business_id_column


def _id():
    return mapped_column(
        UUID(as_uuid=True), primary_key=True, server_default=__import__("sqlalchemy").text("gen_random_uuid()")
    )


def _tenant():
    return mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)


def _ts(nullable=True):
    return mapped_column(DateTime(timezone=True), nullable=nullable)


class AuthSession(Base):
    __tablename__ = "auth_sessions"
    id = _id()
    session_hash: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    tenant_id = _tenant()
    expires_at = _ts(False)
    revoked_at = _ts()
    created_at = _ts(False)
    last_seen_at = _ts(False)
    # None once fully signed in; VERIFY when an authenticator code is still due; ENROLL when MFA must be set up first.
    mfa_state: Mapped[str | None] = mapped_column(String(16))
    __table_args__ = (UniqueConstraint("tenant_id", "id", name="uq_auth_sessions_tenant_id"),)


class PasswordHistory(Base):
    __tablename__ = "password_history"
    id = _id()
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    tenant_id = _tenant()
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    created_at = _ts(False)
    __table_args__ = (Index("ix_password_history_user", "tenant_id", "user_id", "created_at"),)


class MfaChallenge(Base):
    """Durable, single-use MFA challenge state shared by all app instances."""

    __tablename__ = "mfa_challenges"
    id = _id()
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    tenant_id = _tenant()
    code_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    purpose: Mapped[str] = mapped_column(String(60), nullable=False, server_default="SIGNATURE")
    expires_at = _ts(False)
    used_at = _ts()
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    created_at = _ts(False)
    __table_args__ = (Index("ix_mfa_challenge_user", "tenant_id", "user_id", "purpose", "expires_at"),)


class LoginThrottle(Base):
    """Durable per-identifier lockout state shared by all app instances."""

    __tablename__ = "login_throttles"
    identifier: Mapped[str] = mapped_column(String(254), primary_key=True)
    failure_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    locked_until = _ts()
    last_failure_at = _ts()
    updated_at = _ts(False)


class SchedulerRun(Base):
    """The last run of one scheduled job (scripts/run_scheduler.py); platform-level, no tenant data."""

    __tablename__ = "scheduler_runs"
    job: Mapped[str] = mapped_column(String(80), primary_key=True)
    last_started_at = _ts()
    last_finished_at = _ts()
    last_status: Mapped[str | None] = mapped_column(String(20))
    last_result = mapped_column(JSONB)
    last_error: Mapped[str | None] = mapped_column(Text)
    consecutive_failures: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    state = mapped_column(JSONB, nullable=False, server_default="{}")


class RateLimitCounter(Base):
    """Attempts in one fixed window for one hashed key (backend/app/rate_limit.py); platform-level, no tenant data."""

    __tablename__ = "rate_limit_counters"
    scope: Mapped[str] = mapped_column(String(40), primary_key=True)
    key_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    window_start = mapped_column(DateTime(timezone=True), primary_key=True)
    count: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    __table_args__ = (Index("ix_rate_limit_counters_window", "window_start"),)


class AiUsageMonthly(Base):
    """AI tokens, requests and estimated cost per organization and calendar month (genai/governance.py)."""

    __tablename__ = "ai_usage_monthly"
    tenant_id = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id"), primary_key=True)
    month = mapped_column(Date, primary_key=True)
    requests: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    refused: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    input_tokens: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    output_tokens: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    estimated_cost = mapped_column(Numeric(12, 4), nullable=False, server_default="0")
    updated_at = mapped_column(DateTime(timezone=True), nullable=False)


class GenAIProviderRest(Base):
    """A provider every process skips until rest_until (rate-limited or down); platform-level, no tenant data."""

    __tablename__ = "genai_provider_rest"
    provider: Mapped[str] = mapped_column(String(40), primary_key=True)
    rest_until = mapped_column(DateTime(timezone=True), nullable=False)
    reason: Mapped[str] = mapped_column(String(40), nullable=False)
    updated_at = mapped_column(DateTime(timezone=True), nullable=False)


class TenantExport(Base):
    """One full data export of an organization: a zip in object storage, downloadable until expires_at."""

    __tablename__ = "tenant_exports"
    business_id: Mapped[str] = business_id_column()
    id = _id()
    tenant_id = _tenant()
    requested_by: Mapped[str] = mapped_column(String(255), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="QUEUED")
    object_key: Mapped[str | None] = mapped_column(Text)
    size_bytes: Mapped[int | None] = mapped_column(BigInteger)
    sha256: Mapped[str | None] = mapped_column(String(64))
    summary = mapped_column(JSONB)
    error: Mapped[str | None] = mapped_column(String(200))
    created_at = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at = mapped_column(DateTime(timezone=True))
    expires_at = mapped_column(DateTime(timezone=True))
    __table_args__ = (Index("ix_tenant_exports_tenant_created", "tenant_id", "created_at"),)


class UserInvitation(Base):
    __tablename__ = "user_invitations"
    id = _id()
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    tenant_id = _tenant()
    token_hash: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    expires_at = _ts(False)
    used_at = _ts()
    created_at = _ts(False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    __table_args__ = (Index("ix_user_invitations_user", "tenant_id", "user_id"),)


class PasswordResetRequest(Base):
    __tablename__ = "password_reset_requests"
    id = _id()
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    tenant_id = _tenant()
    token_hash: Mapped[str] = mapped_column(String(128), unique=True, nullable=False)
    expires_at = _ts(False)
    used_at = _ts()
    created_at = _ts(False)
    created_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    __table_args__ = (Index("ix_password_reset_user", "tenant_id", "user_id"),)


class OnboardingRequest(Base):
    """Public free-trial request; it never creates a tenant or identity until a Platform Admin approves it."""

    __tablename__ = "onboarding_requests"
    business_id: Mapped[str] = business_id_column()
    id = _id()
    email: Mapped[str] = mapped_column(String(254), nullable=False, unique=True)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    organization: Mapped[str] = mapped_column(String(160), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False, server_default="PENDING_REVIEW")
    # What the requester told MDARIX about their company and trial (md39, backend/app/trial/request_profile.py).
    profile = mapped_column(JSONB, nullable=False, server_default="{}")
    created_at = _ts(False)
    updated_at = _ts(False)
    # Review outcome (md04): who decided, when, why, and the trial workspace an approval created.
    tenant_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    reviewed_at = _ts()
    decision_reason: Mapped[str | None] = mapped_column(Text)
    # The latest invitation email of an approved request (md47): SENT, FAILED or NOT_CONFIGURED, and when it was tried.
    invitation_delivery: Mapped[str | None] = mapped_column(String(20))
    invitation_attempted_at = _ts()
    # Which legal texts the requester accepted by sending the request, and when (md48): {"accepted_at": ...,
    # "documents": {"terms" | "trial-agreement" | "privacy": {"available", "last_updated", "sha256"}}}. Names nobody,
    # so it stays when the request's personal data is erased. Empty for requests sent before md48.
    legal_acceptance = mapped_column(JSONB)


class DemoRequest(Base):
    """Public demo request from the website: who to contact. MDARIX staff follow up; nothing else is created."""

    __tablename__ = "demo_requests"
    business_id: Mapped[str] = business_id_column()
    id = _id()
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    email: Mapped[str] = mapped_column(String(254), nullable=False)
    phone: Mapped[str] = mapped_column(String(30), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False, server_default="NEW")
    # A one-way hash of the sender's address, kept only to limit how many requests one address can send.
    source_hash: Mapped[str | None] = mapped_column(String(64))
    created_at = _ts(False)
    updated_at = _ts(False)
    handled_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    handled_at = _ts()
    note: Mapped[str | None] = mapped_column(Text)
    # md44: a request made inside a free trial (source TRIAL) names the trial organization (not ``tenant_id``: this is
    # MDARIX's sales record, not the organization's business data), the times that suit and the trial's progress.
    source: Mapped[str] = mapped_column(String(20), nullable=False, server_default="WEBSITE")
    trial_tenant_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    organization: Mapped[str | None] = mapped_column(String(160))
    preferred_time: Mapped[str | None] = mapped_column(String(200))
    context: Mapped[dict | None] = mapped_column(JSONB)
    __table_args__ = (
        Index("ix_demo_requests_created", "created_at"),
        Index("ix_demo_requests_email", "email"),
        Index("ix_demo_requests_source", "source_hash", "created_at"),
        Index("ix_demo_requests_trial_tenant", "trial_tenant_id", "created_at"),
        CheckConstraint("source IN ('WEBSITE', 'TRIAL')", name="ck_demo_requests_source_known"),
    )


class TrialExitRequest(Base):
    """A free trial's request to end early (md45; backend/app/trial/early_exit.py). The organization is
    ``trial_tenant_id`` (not ``tenant_id``), so the request and its reason outlive a purge of the trial's data; it holds
    no name or email address."""

    __tablename__ = "trial_exit_requests"
    id = _id()
    trial_tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    organization: Mapped[str] = mapped_column(String(160), nullable=False)
    requested_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    reason_code: Mapped[str | None] = mapped_column(String(40))
    reason: Mapped[str | None] = mapped_column(String(1000))
    # What the owner asked for; the administrator decides when approving.
    delete_data: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="true")
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="PENDING")
    data_deleted: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    decided_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    decided_at = _ts()
    decision_note: Mapped[str | None] = mapped_column(String(500))
    created_at = _ts(False)
    updated_at = _ts(False)
    __table_args__ = (
        Index("ix_trial_exit_requests_trial", "trial_tenant_id", "created_at"),
        Index("ix_trial_exit_requests_status", "status", "created_at"),
        CheckConstraint(
            "status IN ('PENDING', 'APPROVED', 'DECLINED', 'WITHDRAWN')", name="ck_trial_exit_requests_status"
        ),
    )


class TrialMvpRequest(Base):
    """A free trial's request for an MVP conversation (md46; backend/app/trial/mvp_request.py): what the organization
    expects from the MVP, the products, sites and systems it has in mind, how to reach the person who asked, and whether
    to move its trial data into the MVP. A tenant table under row-level security, like ``trial_feedback``: the
    organization sees only its own request, Platform Administrators read every one through the system scope, and it is
    deleted with the trial's data. One open request (NEW or CONTACTED) per organization."""

    __tablename__ = "trial_mvp_requests"
    id = _id()
    tenant_id = _tenant()
    requested_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    email: Mapped[str] = mapped_column(String(254), nullable=False)
    organization: Mapped[str] = mapped_column(String(160), nullable=False)
    expectations: Mapped[str] = mapped_column(String(2000), nullable=False)
    scope: Mapped[str | None] = mapped_column(String(2000))
    phone: Mapped[str | None] = mapped_column(String(30))
    contact_preference: Mapped[str | None] = mapped_column(String(200))
    # Asked for only when the organization had removed the sample data and imported its own (the server checks).
    move_trial_data: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="NEW")
    # The trial when it asked: days left, and its sample and own records (backend/app/trial/mvp_request.py).
    context = mapped_column(JSONB)
    handled_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    handled_at = _ts()
    note: Mapped[str | None] = mapped_column(String(500))
    created_at = _ts(False)
    updated_at = _ts(False)
    __table_args__ = (
        Index("ix_trial_mvp_requests_tenant", "tenant_id", "created_at"),
        Index("ix_trial_mvp_requests_status", "status", "created_at"),
        Index(
            "ux_trial_mvp_requests_open",
            "tenant_id",
            unique=True,
            postgresql_where=text("status IN ('NEW', 'CONTACTED')"),
        ),
        CheckConstraint("status IN ('NEW', 'CONTACTED', 'CLOSED')", name="ck_trial_mvp_requests_status"),
    )


class TrialFeedback(Base):
    """A free-trial user's feedback on MDARIX, with their consent for showing it on the website.

    publish_consent is what the person agreed to (NAMED, ANONYMOUS or PRIVATE) and consent_text the exact words they
    saw; nothing is shown publicly until a Platform Administrator publishes it, and withdrawing consent unpublishes it.
    """

    __tablename__ = "trial_feedback"
    business_id: Mapped[str] = business_id_column()
    id = _id()
    tenant_id = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=False)
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    organization_name: Mapped[str] = mapped_column(String(160), nullable=False)
    role_area: Mapped[str | None] = mapped_column(String(40))
    job_title: Mapped[str | None] = mapped_column(String(120))
    rating_overall: Mapped[int] = mapped_column(Integer, nullable=False)
    rating_ease: Mapped[int | None] = mapped_column(Integer)
    rating_usefulness: Mapped[int | None] = mapped_column(Integer)
    rating_ai_trust: Mapped[int | None] = mapped_column(Integer)
    rating_speed: Mapped[int | None] = mapped_column(Integer)
    rating_import: Mapped[int | None] = mapped_column(Integer)
    recommend_score: Mapped[int | None] = mapped_column(Integer)
    features_used = mapped_column(JSONB, nullable=False, server_default="[]")
    liked: Mapped[str | None] = mapped_column(Text)
    improve: Mapped[str | None] = mapped_column(Text)
    missing: Mapped[str | None] = mapped_column(Text)
    adoption: Mapped[str | None] = mapped_column(String(40))
    quote: Mapped[str | None] = mapped_column(Text)
    publish_consent: Mapped[str] = mapped_column(String(20), nullable=False, server_default="PRIVATE")
    consent_text: Mapped[str] = mapped_column(Text, nullable=False)
    consent_at = _ts(False)
    contact_ok: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    publication_status: Mapped[str] = mapped_column(String(20), nullable=False, server_default="NOT_REQUESTED")
    reviewed_by: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    reviewed_at = _ts()
    created_at = _ts(False)
    updated_at = _ts(False)
    __table_args__ = (
        Index("ix_trial_feedback_tenant_user", "tenant_id", "user_id"),
        Index("ix_trial_feedback_publication", "publication_status"),
    )


class AuthenticationEvent(Base):
    __tablename__ = "authentication_events"
    id = _id()
    tenant_id = mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id"))
    user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    event_type: Mapped[str] = mapped_column(String(80), nullable=False)
    outcome: Mapped[str] = mapped_column(String(40), nullable=False)
    correlation_id: Mapped[str | None] = mapped_column(String(120))
    metadata_json: Mapped[dict | None] = mapped_column("metadata", JSONB)
    created_at = _ts(False)


class MDARIXCaseContext(Base):
    __tablename__ = "case_contexts"
    id = _id()
    tenant_id = _tenant()
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    membership_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    product_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    product_version_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    signal_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    complaint_cluster_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    investigation_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    temporal_mode: Mapped[str] = mapped_column(String(30), nullable=False, server_default="CURRENT")
    temporal_cutoff = _ts()
    decision_brief_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    decision_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    context_version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    last_page: Mapped[str | None] = mapped_column(String(160))
    created_at = _ts(False)
    updated_at = _ts(False)
    __table_args__ = (UniqueConstraint("tenant_id", "user_id", name="uq_case_context_tenant_user"),)


class OutboxEvent(Base):
    __tablename__ = "event_outbox"
    id = _id()
    tenant_id = _tenant()
    event_name: Mapped[str] = mapped_column(String(120), nullable=False)
    aggregate_type: Mapped[str] = mapped_column(String(120), nullable=False)
    aggregate_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    payload: Mapped[dict] = mapped_column(JSONB, nullable=False)
    occurred_at = _ts(False)
    published_at = _ts()
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    next_attempt_at = _ts()
    dead_lettered_at = _ts()
    last_error: Mapped[str | None] = mapped_column(Text)
    claimed_by: Mapped[str | None] = mapped_column(String(120))
    claimed_at = _ts()
    __table_args__ = (Index("ix_event_outbox_pending", "published_at", "occurred_at"),)


class WorkerHeartbeat(Base):
    """The last sign of life of each background service, written every cycle (platform-level: no tenant data)."""

    __tablename__ = "worker_heartbeats"
    service: Mapped[str] = mapped_column(String(80), primary_key=True)
    instance_id: Mapped[str] = mapped_column(String(120), primary_key=True)
    started_at = _ts(False)
    updated_at = _ts(False)
    metrics: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)


class SubscriptionLifecycle(Base):
    __tablename__ = "subscription_lifecycles"
    business_id: Mapped[str] = business_id_column()
    id = _id()
    tenant_id = _tenant()
    plan_id = mapped_column(UUID(as_uuid=True), ForeignKey("plan_definitions.id"), nullable=False)
    plan_version: Mapped[str] = mapped_column(String(40), nullable=False)
    starts_at = _ts(False)
    expires_at = _ts(False)
    grace_ends_at = _ts()
    expiry_version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    status: Mapped[str] = mapped_column(String(40), nullable=False, server_default="ACTIVE")
    renewal_state: Mapped[str] = mapped_column(String(40), nullable=False, server_default="NOT_REQUESTED")
    exception_expires_at = _ts()
    created_at = _ts(False)
    updated_at = _ts(False)
    __table_args__ = (UniqueConstraint("tenant_id", "id", name="uq_subscription_lifecycle_tenant_id"),)


class ReminderPolicy(Base):
    __tablename__ = "subscription_reminder_policies"
    id = _id()
    tenant_id = _tenant()
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    thresholds = mapped_column(JSONB, nullable=False, server_default="[60,30,7]")
    timezone: Mapped[str] = mapped_column(String(80), nullable=False, server_default="UTC")
    recipient_types = mapped_column(JSONB, nullable=False, server_default='["CUSTOMER_ADMIN"]')
    version: Mapped[str] = mapped_column(String(40), nullable=False, server_default="v1")
    status: Mapped[str] = mapped_column(String(30), nullable=False, server_default="ACTIVE")
    created_at = _ts(False)
    updated_at = _ts(False)
    __table_args__ = (UniqueConstraint("tenant_id", "id", name="uq_subscription_reminder_policy_tenant_id"),)


class EmailTemplate(Base):
    __tablename__ = "subscription_email_templates"
    id = _id()
    tenant_id = _tenant()
    stage: Mapped[str] = mapped_column(String(40), nullable=False)
    version: Mapped[str] = mapped_column(String(40), nullable=False)
    subject: Mapped[str] = mapped_column(String(255), nullable=False)
    body = mapped_column(Text, nullable=False)
    allowed_variables = mapped_column(JSONB, nullable=False, server_default="[]")
    status: Mapped[str] = mapped_column(String(30), nullable=False, server_default="DRAFT")
    created_at = _ts(False)
    updated_at = _ts(False)
    __table_args__ = (UniqueConstraint("tenant_id", "stage", "version", name="uq_subscription_email_template"),)
