"""Request models for the access, administration and platform API."""

import uuid

from pydantic import BaseModel, Field


class RoleSwitch(BaseModel):
    role: str


class MembershipRequest(BaseModel):
    user_id: uuid.UUID
    is_default: bool = False


class PersonaRequest(BaseModel):
    user_id: uuid.UUID
    persona_code: str


class PermissionSetRequest(BaseModel):
    code: str = Field(min_length=1, max_length=100)
    object_permissions: dict = {}
    field_permissions: dict = {}
    action_permissions: dict = {}
    version: str = "v1"


class RoleRequest(BaseModel):
    code: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=120)
    version: str = "v1"


class RoleAssignmentRequest(BaseModel):
    user_id: uuid.UUID
    role_id: uuid.UUID


class RolePermissionRequest(BaseModel):
    role_id: uuid.UUID
    permission_set_id: uuid.UUID


class TenantSwitchRequest(BaseModel):
    tenant_id: uuid.UUID


class UserStatusRequest(BaseModel):
    status: str = Field(pattern="^(ACTIVE|SUSPENDED|OFFBOARDED)$")


class AuthorityRequest(BaseModel):
    role_name: str
    object_type: str
    decision_type: str
    authority: str = "AUTHORIZED"
    version: str = "v1"


class SodRequest(BaseModel):
    name: str
    object_type: str
    decision_type: str
    creator_cannot_approve: bool = True
    last_material_editor_cannot_approve: bool = True
    version: str = "v1"


class ConnectorRequest(BaseModel):
    code: str
    connector_type: str
    configuration: dict = {}
    version: str = "v1"


class MappingRequest(BaseModel):
    code: str
    source_system: str
    target_entity: str
    mapping_rules: dict = {}
    version: str = "v1"
    source_database: str | None = None
    source_schema: str | None = None
    source_table: str | None = None
    target_schema: str = "public"
    target_table: str | None = None


class UserCreateRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)
    display_name: str = Field(min_length=1, max_length=120)
    company: str = Field(min_length=1, max_length=160)
    role: str = "Viewer"
    target_tenant_id: uuid.UUID | None = None


class CustomerCreateRequest(BaseModel):
    company_name: str = Field(min_length=1, max_length=255)
    tenant_code: str = Field(min_length=1, max_length=80)
    plan_code: str = "ENTERPRISE_TEST"
    licensed_users_limit: int = Field(default=25, ge=1)
    customer_admin_limit: int = Field(default=2, ge=1)
    connector_limit: int = Field(default=5, ge=0)
    status: str = "active"
    notes: str | None = None


class CustomerImportRequest(BaseModel):
    rows: list[CustomerCreateRequest] = Field(min_length=1, max_length=100)
    dry_run: bool = False


class CustomerProvisionRequest(BaseModel):
    company_name: str = Field(min_length=1, max_length=255)
    tenant_code: str = Field(min_length=1, max_length=80)
    region: str = Field(default="default", min_length=1, max_length=80)
    residency: str = Field(default="default", min_length=1, max_length=80)
    plan_code: str = "ENTERPRISE_TEST"
    licensed_users_limit: int = Field(default=25, ge=1)
    customer_admin_email: str = Field(min_length=3, max_length=254)
    customer_admin_display_name: str = Field(min_length=1, max_length=120)
    customer_admin_company: str = Field(default="Customer", min_length=1, max_length=160)
    invitation_required: bool = True
    environment_type: str = Field(default="PRODUCTION", pattern="^(PRODUCTION|SANDBOX|VALIDATION|UAT|DEMO)$")


class OnboardingDraftRequest(BaseModel):
    idempotency_key: str = Field(min_length=8, max_length=160)
    current_step: int = Field(default=1, ge=1, le=9)
    draft_data: dict = {}


class DomainVerificationRequest(BaseModel):
    domain: str = Field(min_length=3, max_length=255)
    verification_method: str = Field(default="DNS", pattern="^(DNS|FILE)$")
    verification_token: str | None = Field(default=None, min_length=8, max_length=255)


class IdentityProviderVerificationRequest(BaseModel):
    provider_type: str = Field(min_length=2, max_length=40)
    issuer: str = Field(min_length=8, max_length=500)
    client_reference: str = Field(min_length=2, max_length=255)


class ScheduledLifecycleRequest(BaseModel):
    target_status: str = Field(min_length=3, max_length=40)
    effective_at: str
    reason: str = Field(min_length=1, max_length=500)
    notify_customer_admin: bool = True


class SupportAccessRequest(BaseModel):
    tenant_id: uuid.UUID
    platform_user_id: uuid.UUID
    scope: dict = Field(default_factory=dict)
    reason: str = Field(min_length=10, max_length=1000)
    starts_at: str
    expires_at: str


class SupportAccessDecisionRequest(BaseModel):
    reason: str = Field(min_length=10, max_length=1000)


class CustomerAdminReplacementRequest(BaseModel):
    replacement_email: str = Field(min_length=3, max_length=254)
    replacement_display_name: str = Field(min_length=1, max_length=120)
    company: str = Field(min_length=1, max_length=160)
    reason: str = Field(min_length=10, max_length=1000)


class SubscriptionRequest(BaseModel):
    plan_id: uuid.UUID
    starts_at: str
    expires_at: str
    grace_ends_at: str | None = None
    reason: str = Field(min_length=1)


class ReminderPolicyRequest(BaseModel):
    name: str
    thresholds: list[int] = [60, 30, 7]
    timezone: str = "UTC"
    recipient_types: list[str] = ["CUSTOMER_ADMIN"]
    version: str = "v1"


class EmailTemplateRequest(BaseModel):
    stage: str
    version: str = "v1"
    subject: str
    body: str
    allowed_variables: list[str] = []


class PlanCreateRequest(BaseModel):
    code: str = Field(min_length=1, max_length=80)
    name: str = Field(min_length=1, max_length=120)
    description: str | None = None
    version: str = "v1"
    capabilities: dict = {}
    limits: dict = {}


class PasswordActionRequest(BaseModel):
    email: str = Field(min_length=3, max_length=254)


class AdminUpdateRequest(BaseModel):
    values: dict


class ProductRequest(BaseModel):
    product_identifier: str
    name: str
    description: str | None = None
    product_family: str | None = None
    manufacturer_context: str | None = None


class ProductVersionRequest(BaseModel):
    product_id: uuid.UUID
    version_identifier: str
    description: str | None = None
    release_timestamp: str | None = None


class PlatformProductRequest(BaseModel):
    tenant_id: uuid.UUID
    product_identifier: str
    name: str
    description: str | None = None
    product_family: str | None = None
    manufacturer_context: str | None = None


class PlatformProductVersionRequest(BaseModel):
    tenant_id: uuid.UUID
    product_id: uuid.UUID
    version_identifier: str
    description: str | None = None
    release_timestamp: str | None = None


class MasterMappingRequest(BaseModel):
    code: str
    source_system: str
    target_entity: str
    definition: dict = {}


class MappingVersionRequest(BaseModel):
    master_mapping_id: uuid.UUID
    version: str
    rules: dict = {}
    effective_from: str | None = None


class MappingOverrideRequest(BaseModel):
    mapping_version_id: uuid.UUID
    field_name: str
    override_rule: dict = {}


class LifecycleRequest(BaseModel):
    lifecycle_status: str = Field(pattern="^(active|retired|archived)$")


class ConnectorRunRequest(BaseModel):
    records: list[dict] = []
    source_system: str = "SIMULATED"
    required_fields: list[str] = []


class MappingPreviewRequest(BaseModel):
    records: list[dict]
    rules: dict
    source_object: str
    target_entity: str
    mapping_version: str


class StatusRequest(BaseModel):
    status: str = Field(pattern="^(DRAFT|VALIDATION|READY_FOR_APPROVAL|APPROVED|ACTIVE|RELEASED|SUPERSEDED|RETIRED)$")


class ReleaseActionRequest(BaseModel):
    action: str = Field(pattern="^(REQUEST_APPROVAL|PROMOTE|ROLLBACK)$")
    reason: str = Field(min_length=10, max_length=1000)
    expected_status: str | None = None


class CustomerIdentityProviderRequest(BaseModel):
    provider_type: str = Field(min_length=2, max_length=40)
    issuer: str = Field(min_length=8, max_length=500)
    client_reference: str | None = Field(default=None, max_length=255)
    login_mode: str = Field(default="SSO_MFA", pattern="^(SSO|SSO_MFA|PASSWORD_MFA)$")
    reason: str = Field(min_length=10, max_length=500)


class NotificationPreferencesRequest(BaseModel):
    thresholds: list[int] = Field(default_factory=lambda: [60, 30, 7], min_length=1, max_length=10)
    timezone: str = Field(default="UTC", min_length=1, max_length=80)
    recipient_types: list[str] = Field(default_factory=lambda: ["CUSTOMER_ADMIN"], min_length=1, max_length=10)
    reason: str = Field(min_length=10, max_length=500)


class NotificationRecipientRequest(BaseModel):
    recipient_type: str = Field(min_length=2, max_length=60)
    email: str = Field(min_length=3, max_length=254)
    name: str = Field(min_length=1, max_length=160)
    contact_type: str = Field(default="NOTIFICATION", min_length=2, max_length=40)
    reason: str = Field(min_length=10, max_length=500)


class RenewalRequestPayload(BaseModel):
    details: dict = Field(default_factory=dict)
    reason: str = Field(min_length=10, max_length=500)
