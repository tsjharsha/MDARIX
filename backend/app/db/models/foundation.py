import uuid

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, validates
from sqlalchemy.types import UserDefinedType

from backend.app.db.base import Base
from backend.app.db.business_id import business_id_column
from backend.app.role_codes import canonical_stored_role


class Vector(UserDefinedType):
    cache_ok = True

    def __init__(self, dimensions: int | None = None):
        self.dimensions = dimensions

    def get_col_spec(self, **kw: object) -> str:
        # No dimension: the column holds vectors of several embedding models (each row records its model).
        return "vector" if self.dimensions is None else f"vector({self.dimensions})"


def uuid_pk() -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))


def tenant_fk(nullable: bool = False) -> Mapped[uuid.UUID]:
    return mapped_column(UUID(as_uuid=True), ForeignKey("tenants.id"), nullable=nullable)


def tz(nullable: bool = True) -> Mapped[object]:
    return mapped_column(DateTime(timezone=True), nullable=nullable)


class Tenant(Base):
    __tablename__ = "tenants"
    business_id: Mapped[str] = business_id_column()
    id = uuid_pk()
    customer_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("customers.id"), nullable=False)
    tenant_key: Mapped[str] = mapped_column(String(80), nullable=False, unique=True)
    tenant_identifier: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    tenant_slug: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)
    tenant_type: Mapped[str] = mapped_column(String(40), nullable=False, server_default="STANDARD")
    deployment_model: Mapped[str] = mapped_column(String(60), nullable=False, server_default="SHARED")
    primary_region: Mapped[str] = mapped_column(String(80), nullable=False, server_default="UNSPECIFIED")
    residency_region: Mapped[str] = mapped_column(String(80), nullable=False, server_default="UNSPECIFIED")
    database_region: Mapped[str | None] = mapped_column(String(80))
    backup_region: Mapped[str | None] = mapped_column(String(80))
    storage_region: Mapped[str | None] = mapped_column(String(80))
    ai_processing_region: Mapped[str | None] = mapped_column(String(80))
    disaster_recovery_region: Mapped[str | None] = mapped_column(String(80))
    cross_border_processing_allowed: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    # Whether this organization's content may be sent to an AI model, and its monthly token budget (genai/governance.py).
    # Off for new organizations (md23): an administrator switches it on with a recorded reason (ai_settings.py).
    ai_processing_allowed: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    ai_monthly_token_budget: Mapped[int | None] = mapped_column(BigInteger)
    # While a legal hold is set, nothing of this organization is purged or retired (tenant_purge.py, trial/retention.py).
    legal_hold: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    legal_hold_reason: Mapped[str | None] = mapped_column(Text)
    legal_hold_set_at = tz()
    legal_hold_set_by: Mapped[str | None] = mapped_column(String(255))
    # Which navigation the organization's workspace shows: classic (today's menu) or new (stage 7, built behind it).
    # Set by a platform administrator in Tenant 360 (migration tr11navigation); the session context names it.
    navigation: Mapped[str] = mapped_column(String(10), nullable=False, server_default="classic")
    # An evaluation on the sample only (an event or judge trial, 0.10.71, tr12): every import route refuses it and the
    # screens offer "Discuss a pilot" instead of an upload. Set by a platform administrator in Tenant 360.
    sample_only: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default="false")
    application_version: Mapped[str | None] = mapped_column(String(80))
    schema_version: Mapped[str | None] = mapped_column(String(80))
    configuration_version: Mapped[str | None] = mapped_column(String(80))
    provisioning_status: Mapped[str] = mapped_column(String(40), nullable=False, server_default="PROVISIONED")
    status: Mapped[str] = mapped_column(String(40), nullable=False, server_default="ACTIVE")
    activated_at = tz()
    suspended_at = tz()
    terminated_at = tz()
    lock_version: Mapped[int] = mapped_column(Integer, nullable=False, server_default="1")
    created_at = tz(False)
    updated_at = tz(False)
    __table_args__ = (
        UniqueConstraint("customer_id", "id", name="uq_tenants_customer_id_id"),
        CheckConstraint(
            "status in ('DRAFT','PENDING_APPROVAL','PROVISIONING','PROVISIONED','PENDING_CUSTOMER_ACTIVATION','ACTIVE','EXPIRING_SOON','EXPIRED','SUSPENDED','TERMINATED','ARCHIVED','PURGING')",
            name="tenant_lifecycle_status_allowed",
        ),
        CheckConstraint(
            "provisioning_status in ('DRAFT','QUEUED','RUNNING','FAILED','PROVISIONED','ACTIVE')",
            name="tenant_provisioning_status_allowed",
        ),
        CheckConstraint("tenant_type in ('STANDARD','ENTERPRISE','PRIVATE_DEPLOYMENT')", name="tenant_type_allowed"),
        CheckConstraint("navigation in ('classic','new')", name="tenant_navigation_allowed"),
    )


class SourceRecord(Base):
    __tablename__ = "source_records"
    id = uuid_pk()
    tenant_id = tenant_fk()
    source_system: Mapped[str] = mapped_column(String(120), nullable=False)
    source_record_id: Mapped[str] = mapped_column(String(255), nullable=False)
    source_record_version: Mapped[str | None] = mapped_column(String(120))
    raw_payload_ref: Mapped[str | None] = mapped_column(Text)
    source_timestamp = tz()
    effective_timestamp = tz()
    ingestion_timestamp = tz(False)
    checksum: Mapped[str | None] = mapped_column(String(128))
    data_quality_status: Mapped[str] = mapped_column(String(40), nullable=False, server_default="unreviewed")
    created_at = tz(False)
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "source_system", "source_record_id", "source_record_version", name="uq_source_record_identity"
        ),
        UniqueConstraint("tenant_id", "id", name="uq_source_records_tenant_id_id"),
    )


class TenantOwned:
    id = uuid_pk()
    tenant_id = tenant_fk()
    # DB-1 (tr23): the source record is the organization's own, so the reference is composite (added below).
    source_record_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    source_system: Mapped[str | None] = mapped_column(String(120))
    source_identifier: Mapped[str | None] = mapped_column(String(255))
    source_timestamp = tz()
    effective_timestamp = tz()
    recorded_timestamp = tz()
    ingestion_timestamp = tz()
    created_at = tz(False)
    updated_at = tz(False)

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        cls.__table__.append_constraint(
            ForeignKeyConstraint(
                ["tenant_id", "source_record_id"],
                ["source_records.tenant_id", "source_records.id"],
                name=f"fk_{cls.__tablename__}_source_record_id_tenant",
            )
        )


class Product(TenantOwned, Base):
    __tablename__ = "products"
    business_id: Mapped[str] = business_id_column()
    product_identifier: Mapped[str] = mapped_column(String(120), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    lifecycle_status: Mapped[str] = mapped_column(String(40), nullable=False, server_default="active")
    product_family: Mapped[str | None] = mapped_column(String(120))
    manufacturer_context: Mapped[str | None] = mapped_column(String(255))
    # Regulatory identity (G2a): the device identifier and the GMDN term, the same in every market.
    udi_di: Mapped[str | None] = mapped_column(String(80))
    gmdn_code: Mapped[str | None] = mapped_column(String(10))
    gmdn_term: Mapped[str | None] = mapped_column(String(300))
    # tr16: the Basic UDI-DI (EU) and the EMDN code; GMDN stays the organization's own code (GMDN is licensed).
    basic_udi_di: Mapped[str | None] = mapped_column(String(120))
    emdn_code: Mapped[str | None] = mapped_column(String(30))
    # tr09: IMPLANT, SINGLE_USE, REUSABLE, SOFTWARE, IVD or KIT (backend/app/product_facts.py); null when not known.
    device_category: Mapped[str | None] = mapped_column(String(40))
    # tr09: a single-use product, and the days a unit stays in use after its lot's release (signals/trend_rules.py).
    single_use: Mapped[bool | None] = mapped_column(Boolean)
    use_period_days: Mapped[int | None] = mapped_column(Integer)
    __table_args__ = (
        UniqueConstraint("tenant_id", "product_identifier", name="uq_products_tenant_product_identifier"),
        UniqueConstraint("tenant_id", "id", name="uq_products_tenant_id_id"),
    )


class ProductVersion(TenantOwned, Base):
    __tablename__ = "product_versions"
    business_id: Mapped[str] = business_id_column()
    product_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    version_identifier: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    lifecycle_status: Mapped[str] = mapped_column(String(40), nullable=False, server_default="active")
    release_timestamp = tz()
    __table_args__ = (
        # DB-1 (tr23).
        UniqueConstraint("tenant_id", "product_id", "id", name="uq_product_versions_tenant_product_id"),
        ForeignKeyConstraint(["tenant_id", "product_id"], ["products.tenant_id", "products.id"]),
        UniqueConstraint(
            "tenant_id", "product_id", "version_identifier", name="uq_product_versions_tenant_product_version"
        ),
        UniqueConstraint("tenant_id", "id", name="uq_product_versions_tenant_id_id"),
    )


class Component(TenantOwned, Base):
    __tablename__ = "components"
    business_id: Mapped[str] = business_id_column()
    component_identifier: Mapped[str] = mapped_column(String(120), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    revision: Mapped[str | None] = mapped_column(String(80))
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(40), nullable=False, server_default="active")
    __table_args__ = (
        UniqueConstraint(
            "tenant_id", "component_identifier", "revision", name="uq_components_tenant_identifier_revision"
        ),
        UniqueConstraint("tenant_id", "id", name="uq_components_tenant_id_id"),
    )


class Supplier(TenantOwned, Base):
    __tablename__ = "suppliers"
    business_id: Mapped[str] = business_id_column()
    supplier_identifier: Mapped[str] = mapped_column(String(120), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False, server_default="active")
    __table_args__ = (
        UniqueConstraint("tenant_id", "supplier_identifier", name="uq_suppliers_tenant_supplier_identifier"),
        UniqueConstraint("tenant_id", "id", name="uq_suppliers_tenant_id_id"),
    )


class ManufacturingSite(TenantOwned, Base):
    __tablename__ = "manufacturing_sites"
    business_id: Mapped[str] = business_id_column()
    site_identifier: Mapped[str] = mapped_column(String(120), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    location: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(40), nullable=False, server_default="active")
    __table_args__ = (
        UniqueConstraint("tenant_id", "site_identifier", name="uq_sites_tenant_site_identifier"),
        UniqueConstraint("tenant_id", "id", name="uq_manufacturing_sites_tenant_id_id"),
    )


class LotBatch(TenantOwned, Base):
    __tablename__ = "lot_batches"
    business_id: Mapped[str] = business_id_column()
    lot_identifier: Mapped[str] = mapped_column(String(120), nullable=False)
    product_version_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    manufacturing_site_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    status: Mapped[str] = mapped_column(String(40), nullable=False, server_default="active")
    # md43: devices the lot released (the trend check's denominator, signals/trend_rules.py); null when not known.
    quantity: Mapped[int | None] = mapped_column(Integer)
    # tr09: the lot's expiry (use-by) date, when it has one.
    expiry_date = mapped_column(Date)
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "product_version_id"], ["product_versions.tenant_id", "product_versions.id"]
        ),
        ForeignKeyConstraint(
            ["tenant_id", "manufacturing_site_id"], ["manufacturing_sites.tenant_id", "manufacturing_sites.id"]
        ),
        UniqueConstraint("tenant_id", "lot_identifier", name="uq_lots_tenant_lot_identifier"),
        UniqueConstraint("tenant_id", "id", name="uq_lot_batches_tenant_id_id"),
    )


class Requirement(TenantOwned, Base):
    __tablename__ = "requirements"
    business_id: Mapped[str] = business_id_column()
    product_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    product_version_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    requirement_identifier: Mapped[str] = mapped_column(String(120), nullable=False)
    requirement_type: Mapped[str | None] = mapped_column(String(80))
    text: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False, server_default="active")
    __table_args__ = (
        # DB-1 (tr23).
        ForeignKeyConstraint(
            ["tenant_id", "product_id", "product_version_id"],
            ["product_versions.tenant_id", "product_versions.product_id", "product_versions.id"],
            name="fk_requirements_version_of_product",
        ),
        CheckConstraint("product_version_id IS NULL OR product_id IS NOT NULL", name="version_needs_product"),
        ForeignKeyConstraint(["tenant_id", "product_id"], ["products.tenant_id", "products.id"]),
        ForeignKeyConstraint(
            ["tenant_id", "product_version_id"], ["product_versions.tenant_id", "product_versions.id"]
        ),
        UniqueConstraint("tenant_id", "requirement_identifier", name="uq_requirements_tenant_identifier"),
        UniqueConstraint("tenant_id", "id", name="uq_requirements_tenant_id_id"),
    )


class Change(TenantOwned, Base):
    __tablename__ = "changes"
    business_id: Mapped[str] = business_id_column()
    change_identifier: Mapped[str] = mapped_column(String(120), nullable=False)
    change_type: Mapped[str] = mapped_column(String(80), nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    event_timestamp = tz()
    __table_args__ = (
        UniqueConstraint("tenant_id", "change_identifier", name="uq_changes_tenant_identifier"),
        UniqueConstraint("tenant_id", "id", name="uq_changes_tenant_id_id"),
    )


class Complaint(TenantOwned, Base):
    __tablename__ = "complaints"
    business_id: Mapped[str] = business_id_column()
    complaint_identifier: Mapped[str] = mapped_column(String(120), nullable=False)
    product_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    product_version_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    lot_batch_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    event_timestamp = tz()
    complaint_timestamp = tz()
    description: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False, server_default="open")
    # Regulatory details as the quality system records them (none identifies a person).
    severity: Mapped[str | None] = mapped_column(String(40))
    country: Mapped[str | None] = mapped_column(String(80))
    reporter_type: Mapped[str | None] = mapped_column(String(80))
    complaint_type: Mapped[str | None] = mapped_column(String(80))
    problem_code: Mapped[str | None] = mapped_column(String(120))
    serial_number: Mapped[str | None] = mapped_column(String(120))
    udi: Mapped[str | None] = mapped_column(String(120))
    awareness_timestamp = tz()
    device_returned: Mapped[bool | None] = mapped_column(Boolean)
    patient_involved: Mapped[bool | None] = mapped_column(Boolean)
    serious_injury: Mapped[bool | None] = mapped_column(Boolean)
    death: Mapped[bool | None] = mapped_column(Boolean)
    malfunction: Mapped[bool | None] = mapped_column(Boolean)
    # tr09: the lot identifiers beyond lot_batch_id's of a complaint that names several (a kit's lots), in file order.
    other_lots = mapped_column(JSONB)
    # tr12 (0.10.71): the service work linked to the complaint: the customer's service ticket (free text), its owner,
    # its status (OPEN, IN_PROGRESS, COMPLETE) and when that was recorded. It never closes or advances the complaint.
    service_reference: Mapped[str | None] = mapped_column(String(120))
    service_owner: Mapped[str | None] = mapped_column(String(255))
    service_status: Mapped[str | None] = mapped_column(String(20))
    service_status_at = tz()
    # tr19 (0.10.93, B2): the QMS complaint ID (unique per organization when set), the product and lot as typed, the
    # software version, the last sync from the QMS and who owns the record (MDARIX or EXTERNAL).
    qms_ref: Mapped[str | None] = mapped_column(String(120))
    product_text: Mapped[str | None] = mapped_column(String(200))
    lot_text: Mapped[str | None] = mapped_column(String(120))
    software_version: Mapped[str | None] = mapped_column(String(60))
    last_synced_at = tz()
    record_owner: Mapped[str | None] = mapped_column(String(10))
    __table_args__ = (
        # DB-1 (tr23).
        ForeignKeyConstraint(
            ["tenant_id", "product_id", "product_version_id"],
            ["product_versions.tenant_id", "product_versions.product_id", "product_versions.id"],
            name="fk_complaints_version_of_product",
        ),
        CheckConstraint("product_version_id IS NULL OR product_id IS NOT NULL", name="version_needs_product"),
        CheckConstraint(
            "service_status IS NULL OR service_status IN ('OPEN','IN_PROGRESS','COMPLETE')",
            name="complaint_service_status_known",
        ),
        CheckConstraint("record_owner IS NULL OR record_owner IN ('MDARIX', 'EXTERNAL')", name="record_owner_known"),
        Index(
            "ix_complaints_tenant_qms_ref",
            "tenant_id",
            "qms_ref",
            unique=True,
            postgresql_where=text("qms_ref IS NOT NULL"),
        ),
        ForeignKeyConstraint(["tenant_id", "product_id"], ["products.tenant_id", "products.id"]),
        ForeignKeyConstraint(
            ["tenant_id", "product_version_id"], ["product_versions.tenant_id", "product_versions.id"]
        ),
        ForeignKeyConstraint(["tenant_id", "lot_batch_id"], ["lot_batches.tenant_id", "lot_batches.id"]),
        UniqueConstraint("tenant_id", "complaint_identifier", name="uq_complaints_tenant_identifier"),
        UniqueConstraint("tenant_id", "id", name="uq_complaints_tenant_id_id"),
    )


class Investigation(TenantOwned, Base):
    __tablename__ = "investigations"
    business_id: Mapped[str] = business_id_column()
    investigation_identifier: Mapped[str] = mapped_column(String(120), nullable=False)
    product_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    investigation_question: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False, server_default="open")
    opened_at = tz()
    closed_at = tz()
    owner_ref: Mapped[str | None] = mapped_column(String(255))
    # Where the case is in the workflow (md29). ``status`` stays "open"/"closed" for everything that reads it today;
    # CLOSED and CANCELLED keep it "closed", every other state "open".
    workflow_state: Mapped[str] = mapped_column(String(30), nullable=False, server_default="OPEN")
    priority: Mapped[str] = mapped_column(String(20), nullable=False, server_default="MEDIUM")
    due_at = tz()
    state_changed_at = tz()
    __table_args__ = (
        ForeignKeyConstraint(["tenant_id", "product_id"], ["products.tenant_id", "products.id"]),
        UniqueConstraint("tenant_id", "investigation_identifier", name="uq_investigations_tenant_identifier"),
        UniqueConstraint("tenant_id", "id", name="uq_investigations_tenant_id_id"),
        CheckConstraint(
            "workflow_state IN ('OPEN', 'IN_PROGRESS', 'ON_HOLD', 'BRIEF_IN_REVIEW', 'READY_FOR_DECISION', 'DECIDED', 'CLOSED', 'CANCELLED')",
            name="workflow_state_known",
        ),
        CheckConstraint("priority IN ('LOW', 'MEDIUM', 'HIGH', 'CRITICAL')", name="priority_known"),
    )


class Capa(TenantOwned, Base):
    """A corrective or preventive action from the customer's quality system."""

    __tablename__ = "capas"
    business_id: Mapped[str] = business_id_column()
    capa_identifier: Mapped[str] = mapped_column(String(120), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    action_type: Mapped[str | None] = mapped_column(String(40))
    source_type: Mapped[str | None] = mapped_column(String(80))
    source_reference: Mapped[str | None] = mapped_column(String(120))
    product_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    investigation_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    status: Mapped[str] = mapped_column(String(40), nullable=False, server_default="open")
    opened_at = tz()
    due_at = tz()
    effectiveness_check_at = tz()
    # tr09: the number the customer's QMS gave a CAPA MDARIX recorded for raising there (J22); null until known.
    qms_reference: Mapped[str | None] = mapped_column(String(120))
    __table_args__ = (
        ForeignKeyConstraint(["tenant_id", "product_id"], ["products.tenant_id", "products.id"]),
        ForeignKeyConstraint(["tenant_id", "investigation_id"], ["investigations.tenant_id", "investigations.id"]),
        UniqueConstraint("tenant_id", "capa_identifier", name="uq_capas_tenant_identifier"),
        UniqueConstraint("tenant_id", "id", name="uq_capas_tenant_id_id"),
    )


class Risk(TenantOwned, Base):
    __tablename__ = "risks"
    business_id: Mapped[str] = business_id_column()
    risk_identifier: Mapped[str] = mapped_column(String(120), nullable=False)
    product_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    product_version_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    description: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False, server_default="active")
    __table_args__ = (
        # DB-1 (tr23).
        ForeignKeyConstraint(
            ["tenant_id", "product_id", "product_version_id"],
            ["product_versions.tenant_id", "product_versions.product_id", "product_versions.id"],
            name="fk_risks_version_of_product",
        ),
        CheckConstraint("product_version_id IS NULL OR product_id IS NOT NULL", name="version_needs_product"),
        ForeignKeyConstraint(["tenant_id", "product_id"], ["products.tenant_id", "products.id"]),
        ForeignKeyConstraint(
            ["tenant_id", "product_version_id"], ["product_versions.tenant_id", "product_versions.id"]
        ),
        UniqueConstraint("tenant_id", "risk_identifier", name="uq_risks_tenant_identifier"),
        UniqueConstraint("tenant_id", "id", name="uq_risks_tenant_id_id"),
    )


class FailureMode(TenantOwned, Base):
    __tablename__ = "failure_modes"
    business_id: Mapped[str] = business_id_column()
    failure_mode_identifier: Mapped[str] = mapped_column(String(120), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    __table_args__ = (
        UniqueConstraint("tenant_id", "failure_mode_identifier", name="uq_failure_modes_tenant_identifier"),
        UniqueConstraint("tenant_id", "id", name="uq_failure_modes_tenant_id_id"),
    )


class Control(TenantOwned, Base):
    __tablename__ = "controls"
    business_id: Mapped[str] = business_id_column()
    control_identifier: Mapped[str] = mapped_column(String(120), nullable=False)
    control_type: Mapped[str | None] = mapped_column(String(80))
    description: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False, server_default="active")
    __table_args__ = (
        UniqueConstraint("tenant_id", "control_identifier", name="uq_controls_tenant_identifier"),
        UniqueConstraint("tenant_id", "id", name="uq_controls_tenant_id_id"),
    )


class Evidence(TenantOwned, Base):
    __tablename__ = "evidence"
    business_id: Mapped[str] = business_id_column()
    evidence_identifier: Mapped[str] = mapped_column(String(120), nullable=False)
    investigation_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    evidence_type: Mapped[str] = mapped_column(String(80), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    source_reference: Mapped[str | None] = mapped_column(Text)
    document_ref: Mapped[str | None] = mapped_column(Text)
    extracted_text_ref: Mapped[str | None] = mapped_column(Text)
    reliability_status: Mapped[str] = mapped_column(String(40), nullable=False, server_default="unreviewed")
    fact_type: Mapped[str] = mapped_column(String(40), nullable=False, server_default="source_fact")
    content: Mapped[str | None] = mapped_column(Text)
    __table_args__ = (
        ForeignKeyConstraint(["tenant_id", "investigation_id"], ["investigations.tenant_id", "investigations.id"]),
        CheckConstraint(
            "fact_type in ('source_fact','derived_fact','ai_inference')", name="evidence_fact_type_allowed"
        ),
        UniqueConstraint("tenant_id", "evidence_identifier", name="uq_evidence_tenant_identifier"),
        UniqueConstraint("tenant_id", "id", name="uq_evidence_tenant_id_id"),
    )


class Hypothesis(TenantOwned, Base):
    __tablename__ = "hypotheses"
    business_id: Mapped[str] = business_id_column()
    investigation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    statement: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False, server_default="proposed")
    origin: Mapped[str] = mapped_column(String(20), nullable=False)
    reviewer_disposition: Mapped[str | None] = mapped_column(String(80))
    # A person's judgement of the hypothesis (md30), kept apart from the AI's own status: PROPOSED, HYPOTHESIZED,
    # PARTIALLY_SUPPORTED, STRONGLY_SUPPORTED, WEAKLY_SUPPORTED, CONTRADICTED or RETIRED, with the reason.
    human_status: Mapped[str | None] = mapped_column(String(30))
    status_reason: Mapped[str | None] = mapped_column(Text)
    status_changed_by: Mapped[str | None] = mapped_column(String(255))
    status_changed_at = tz()
    created_by: Mapped[str | None] = mapped_column(String(255))
    __table_args__ = (
        ForeignKeyConstraint(["tenant_id", "investigation_id"], ["investigations.tenant_id", "investigations.id"]),
        CheckConstraint("origin in ('ai','human','system')", name="hypothesis_origin_allowed"),
        UniqueConstraint("tenant_id", "id", name="uq_hypotheses_tenant_id_id"),
    )


class Unknown(Base):
    __tablename__ = "unknowns"
    business_id: Mapped[str] = business_id_column()
    id = uuid_pk()
    tenant_id = tenant_fk()
    investigation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    hypothesis_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    category: Mapped[str | None] = mapped_column(String(80))
    description: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_needed: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(40), nullable=False, server_default="open")
    resolution: Mapped[str | None] = mapped_column(Text)
    created_at = tz(False)
    updated_at = tz(False)
    # md30: where the unknown came from (system/ai or a person) and who last changed its status. Statuses: open,
    # in_progress, resolved, accepted_limitation, superseded.
    origin: Mapped[str] = mapped_column(String(20), nullable=False, server_default="system")
    created_by: Mapped[str | None] = mapped_column(String(255))
    status_changed_by: Mapped[str | None] = mapped_column(String(255))
    status_changed_at = tz()
    __table_args__ = (
        ForeignKeyConstraint(["tenant_id", "investigation_id"], ["investigations.tenant_id", "investigations.id"]),
        ForeignKeyConstraint(["tenant_id", "hypothesis_id"], ["hypotheses.tenant_id", "hypotheses.id"]),
        UniqueConstraint("tenant_id", "id", name="uq_unknowns_tenant_id_id"),
    )


class FailureChain(Base):
    __tablename__ = "failure_chains"
    business_id: Mapped[str] = business_id_column()
    id = uuid_pk()
    tenant_id = tenant_fk()
    investigation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False, server_default="draft")
    created_at = tz(False)
    updated_at = tz(False)
    # md30: a chain a person built or adopted from an AI run (source_ai_execution_id), and who last changed it.
    origin: Mapped[str] = mapped_column(String(20), nullable=False, server_default="system")
    created_by: Mapped[str | None] = mapped_column(String(255))
    source_ai_execution_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    __table_args__ = (
        ForeignKeyConstraint(["tenant_id", "investigation_id"], ["investigations.tenant_id", "investigations.id"]),
        UniqueConstraint("tenant_id", "id", name="uq_failure_chains_tenant_id_id"),
    )


class Scenario(TenantOwned, Base):
    __tablename__ = "scenarios"
    business_id: Mapped[str] = business_id_column()
    investigation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    scenario_identifier: Mapped[str] = mapped_column(String(120), nullable=False)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    assumptions: Mapped[dict | None] = mapped_column(JSONB)
    uncertainty: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(40), nullable=False, server_default="draft")
    __table_args__ = (
        ForeignKeyConstraint(["tenant_id", "investigation_id"], ["investigations.tenant_id", "investigations.id"]),
        UniqueConstraint("tenant_id", "scenario_identifier", name="uq_scenarios_tenant_identifier"),
        UniqueConstraint("tenant_id", "id", name="uq_scenarios_tenant_id_id"),
    )


class AIExecution(Base):
    __tablename__ = "ai_executions"
    business_id: Mapped[str] = business_id_column()
    id = uuid_pk()
    tenant_id = tenant_fk()
    investigation_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    requestor_ref: Mapped[str | None] = mapped_column(String(255))
    provider: Mapped[str] = mapped_column(String(80), nullable=False)
    model_name: Mapped[str] = mapped_column(String(120), nullable=False)
    model_version: Mapped[str | None] = mapped_column(String(120))
    prompt_template_version: Mapped[str | None] = mapped_column(String(120))
    orchestration_version: Mapped[str | None] = mapped_column(String(120))
    context_refs: Mapped[dict | None] = mapped_column(JSONB)
    evidence_refs: Mapped[dict | None] = mapped_column(JSONB)
    tools_invoked: Mapped[dict | None] = mapped_column(JSONB)
    structured_input: Mapped[dict | None] = mapped_column(JSONB)
    structured_output: Mapped[dict | None] = mapped_column(JSONB)
    rationale_summary: Mapped[str | None] = mapped_column(Text)
    confidence_label: Mapped[str | None] = mapped_column(String(80))
    validation_status: Mapped[str | None] = mapped_column(String(80))
    execution_timestamp = tz(False)
    latency_ms: Mapped[int | None] = mapped_column()
    error_state: Mapped[str | None] = mapped_column(Text)
    __table_args__ = (
        ForeignKeyConstraint(["tenant_id", "investigation_id"], ["investigations.tenant_id", "investigations.id"]),
        UniqueConstraint("tenant_id", "id", name="uq_ai_executions_tenant_id_id"),
    )


class Decision(Base):
    __tablename__ = "decisions"
    business_id: Mapped[str] = business_id_column()
    id = uuid_pk()
    tenant_id = tenant_fk()
    investigation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    decision_identifier: Mapped[str] = mapped_column(String(120), nullable=False)
    decision_type: Mapped[str] = mapped_column(String(80), nullable=False)
    disposition: Mapped[str] = mapped_column(String(80), nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    product_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    product_version_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    decision_status: Mapped[str] = mapped_column(String(50), nullable=False, server_default="DRAFT")
    decision_readiness: Mapped[str | None] = mapped_column(String(80))
    selected_action: Mapped[str | None] = mapped_column(String(120))
    human_decision: Mapped[str | None] = mapped_column(Text)
    limitations: Mapped[dict | None] = mapped_column(JSONB)
    temporal_context: Mapped[dict | None] = mapped_column(JSONB)
    context_snapshot: Mapped[dict | None] = mapped_column(JSONB)
    advisory_execution_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    updated_at = tz(False)
    decision_timestamp = tz(False)
    authorized_by_ref: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at = tz(False)
    # md33: the signed human decision on an approved Decision Brief version (decision_kind BRIEF; earlier decisions
    # are LEGACY). The outcome and follow-ups are chosen while signing; the decision is bound to the brief version's
    # content hash, the evidence set and a context snapshot, and is never edited: a correction is a new decision that
    # supersedes it.
    decision_kind: Mapped[str] = mapped_column(String(20), nullable=False, server_default="LEGACY")
    brief_version_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    outcome: Mapped[str | None] = mapped_column(String(40))
    conditions: Mapped[str | None] = mapped_column(Text)
    follow_up_actions: Mapped[list] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    residual_unknowns: Mapped[list] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    decided_by_user_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    decided_under_role: Mapped[str | None] = mapped_column(String(60))
    approval_authority_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    decided_at = tz()
    brief_content_hash: Mapped[str | None] = mapped_column(String(64))
    evidence_set_hash: Mapped[str | None] = mapped_column(String(64))
    context_snapshot_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    ai_execution_refs: Mapped[list] = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    supersedes_decision_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    superseded_by_decision_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    superseded_at = tz()
    supersede_reason: Mapped[str | None] = mapped_column(Text)
    # tr02: the root-cause attribution the decision maker signs (DEVICE_RELATED, USE_RELATED, ENVIRONMENT_RELATED or
    # UNDETERMINED with a reason); required for new signatures, empty on decisions signed before 0.10.53.
    root_cause_attribution: Mapped[str | None] = mapped_column(String(30))
    attribution_reason: Mapped[str | None] = mapped_column(Text)
    __table_args__ = (
        # DB-1 (tr23).
        ForeignKeyConstraint(
            ["tenant_id", "product_id", "product_version_id"],
            ["product_versions.tenant_id", "product_versions.product_id", "product_versions.id"],
            name="fk_decisions_version_of_product",
        ),
        # DB-1 (tr24a).
        ForeignKeyConstraint(
            ["tenant_id", "product_id"], ["products.tenant_id", "products.id"], name="fk_decisions_product_id_tenant"
        ),
        CheckConstraint("product_version_id IS NULL OR product_id IS NOT NULL", name="version_needs_product"),
        ForeignKeyConstraint(["tenant_id", "investigation_id"], ["investigations.tenant_id", "investigations.id"]),
        UniqueConstraint("tenant_id", "decision_identifier", name="uq_decisions_tenant_identifier"),
        UniqueConstraint("tenant_id", "id", name="uq_decisions_tenant_id_id"),
        CheckConstraint("decision_kind IN ('LEGACY', 'BRIEF')", name="decision_kind_known"),
        CheckConstraint(
            "outcome IS NULL OR outcome IN ('ACCEPT_CONCLUSION', 'ACCEPT_WITH_CONDITIONS', 'REJECT_CONCLUSION', "
            "'CLOSE_NO_FURTHER_ACTION')",
            name="outcome_known",
        ),
    )


class HumanReview(Base):
    __tablename__ = "human_reviews"
    id = uuid_pk()
    tenant_id = tenant_fk()
    investigation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    ai_execution_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    decision_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    reviewer_ref: Mapped[str] = mapped_column(String(255), nullable=False)
    disposition: Mapped[str] = mapped_column(String(80), nullable=False)
    comments: Mapped[str | None] = mapped_column(Text)
    review_timestamp = tz(False)
    __table_args__ = (
        ForeignKeyConstraint(["tenant_id", "investigation_id"], ["investigations.tenant_id", "investigations.id"]),
        ForeignKeyConstraint(["tenant_id", "ai_execution_id"], ["ai_executions.tenant_id", "ai_executions.id"]),
        ForeignKeyConstraint(["tenant_id", "decision_id"], ["decisions.tenant_id", "decisions.id"]),
        UniqueConstraint("tenant_id", "id", name="uq_human_reviews_tenant_id_id"),
    )


class AuditEvent(Base):
    __tablename__ = "audit_events"
    id = uuid_pk()
    tenant_id = tenant_fk()
    actor_ref: Mapped[str | None] = mapped_column(String(255))
    action: Mapped[str] = mapped_column(String(120), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(120), nullable=False)
    entity_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    correlation_id: Mapped[str | None] = mapped_column(String(120))
    details: Mapped[dict | None] = mapped_column(JSONB)
    source_ip: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(512))
    reason: Mapped[str | None] = mapped_column(Text)
    old_values: Mapped[dict | None] = mapped_column(JSONB)
    new_values: Mapped[dict | None] = mapped_column(JSONB)
    # Set by the database when the row is inserted (migration md18); anything the application sets is replaced.
    chain_seq: Mapped[int] = mapped_column(BigInteger, nullable=False)
    previous_hash: Mapped[str | None] = mapped_column(String(64))
    event_hash: Mapped[str | None] = mapped_column(String(64))
    retention_until = tz(True)
    created_at = tz(False)


class InvestigationBrief(Base):
    """Immutable, versioned investigation brief snapshot."""

    __tablename__ = "investigation_briefs"
    business_id: Mapped[str] = business_id_column()
    id = uuid_pk()
    tenant_id = tenant_fk()
    investigation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    product_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    product_version_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    brief_version: Mapped[int] = mapped_column(nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False, server_default="GENERATED")
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    generated_by: Mapped[str] = mapped_column(String(255), nullable=False)
    temporal_mode: Mapped[str] = mapped_column(String(20), nullable=False)
    temporal_cutoff = tz(True)
    ai_execution_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    human_review_state: Mapped[str] = mapped_column(String(40), nullable=False, server_default="NOT_REVIEWED")
    decision_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    limitations: Mapped[dict | None] = mapped_column(JSONB)
    content: Mapped[dict] = mapped_column(JSONB, nullable=False)
    provenance: Mapped[dict] = mapped_column(JSONB, nullable=False)
    created_at = tz(False)
    updated_at = tz(False)
    __table_args__ = (
        # DB-1 (tr23).
        ForeignKeyConstraint(
            ["tenant_id", "product_id", "product_version_id"],
            ["product_versions.tenant_id", "product_versions.product_id", "product_versions.id"],
            name="fk_investigation_briefs_version_of_product",
        ),
        # DB-1 (tr24a).
        ForeignKeyConstraint(
            ["tenant_id", "product_id"],
            ["products.tenant_id", "products.id"],
            name="fk_investigation_briefs_product_id_tenant",
        ),
        CheckConstraint("product_version_id IS NULL OR product_id IS NOT NULL", name="version_needs_product"),
        ForeignKeyConstraint(["tenant_id", "investigation_id"], ["investigations.tenant_id", "investigations.id"]),
        UniqueConstraint(
            "tenant_id", "investigation_id", "brief_version", name="uq_briefs_tenant_investigation_version"
        ),
        UniqueConstraint("tenant_id", "id", name="uq_briefs_tenant_id_id"),
    )


class AssuranceResult(Base):
    __tablename__ = "assurance_results"
    id = uuid_pk()
    tenant_id = tenant_fk()
    investigation_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    ai_execution_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    output_type: Mapped[str] = mapped_column(String(80), nullable=False)
    output_id: Mapped[str | None] = mapped_column(String(255))
    assurance_version: Mapped[int] = mapped_column(nullable=False, server_default="1")
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    generated_at = tz(False)
    trust_policy_version: Mapped[str] = mapped_column(String(120), nullable=False)
    product_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    product_version_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    temporal_mode: Mapped[str | None] = mapped_column(String(20))
    temporal_cutoff = tz(True)
    human_review_required: Mapped[bool] = mapped_column(nullable=False, server_default="true")
    revalidation_required: Mapped[bool] = mapped_column(nullable=False, server_default="false")
    limitations: Mapped[dict | None] = mapped_column(JSONB)
    configuration_hash: Mapped[str | None] = mapped_column(String(64))
    created_at = tz(False)
    __table_args__ = (
        # DB-1 (tr23).
        ForeignKeyConstraint(
            ["tenant_id", "product_id", "product_version_id"],
            ["product_versions.tenant_id", "product_versions.product_id", "product_versions.id"],
            name="fk_assurance_results_version_of_product",
        ),
        # DB-1 (tr24a).
        ForeignKeyConstraint(
            ["tenant_id", "product_id"],
            ["products.tenant_id", "products.id"],
            name="fk_assurance_results_product_id_tenant",
        ),
        CheckConstraint("product_version_id IS NULL OR product_id IS NOT NULL", name="version_needs_product"),
        ForeignKeyConstraint(["tenant_id", "ai_execution_id"], ["ai_executions.tenant_id", "ai_executions.id"]),
        UniqueConstraint("tenant_id", "id", name="uq_assurance_results_tenant_id_id"),
    )


class AssuranceCheck(Base):
    __tablename__ = "assurance_checks"
    id = uuid_pk()
    tenant_id = tenant_fk()
    assurance_result_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    check_type: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    severity: Mapped[str] = mapped_column(String(20), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_reference: Mapped[dict | None] = mapped_column(JSONB)
    details: Mapped[dict | None] = mapped_column(JSONB)
    created_at = tz(False)
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "assurance_result_id"], ["assurance_results.tenant_id", "assurance_results.id"]
        ),
        UniqueConstraint("tenant_id", "id", name="uq_assurance_checks_tenant_id_id"),
    )


class EvaluationRun(Base):
    __tablename__ = "evaluation_runs"
    business_id: Mapped[str] = business_id_column()
    id = uuid_pk()
    tenant_id = tenant_fk()
    suite_version: Mapped[str] = mapped_column(String(120), nullable=False)
    dataset_version: Mapped[str] = mapped_column(String(120), nullable=False)
    release_version: Mapped[str] = mapped_column(String(120), nullable=False)
    configuration_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    results: Mapped[dict] = mapped_column(JSONB, nullable=False)
    started_at = tz(False)
    completed_at = tz()
    created_at = tz(False)
    __table_args__ = (UniqueConstraint("tenant_id", "id", name="uq_evaluation_runs_tenant_id_id"),)


class ReleaseAssuranceResult(Base):
    __tablename__ = "release_assurance_results"
    id = uuid_pk()
    tenant_id = tenant_fk()
    evaluation_run_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    release_version: Mapped[str] = mapped_column(String(120), nullable=False)
    suite_version: Mapped[str] = mapped_column(String(120), nullable=False)
    dataset_version: Mapped[str] = mapped_column(String(120), nullable=False)
    configuration_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(40), nullable=False)
    critical_failures: Mapped[dict | None] = mapped_column(JSONB)
    limitations: Mapped[dict | None] = mapped_column(JSONB)
    revalidation_required: Mapped[bool] = mapped_column(nullable=False, server_default="false")
    review_status: Mapped[str] = mapped_column(String(40), nullable=False, server_default="REQUIRES_HUMAN_REVIEW")
    generated_at = tz(False)
    created_at = tz(False)
    __table_args__ = (
        ForeignKeyConstraint(["tenant_id", "evaluation_run_id"], ["evaluation_runs.tenant_id", "evaluation_runs.id"]),
        UniqueConstraint("tenant_id", "id", name="uq_release_assurance_tenant_id_id"),
    )


class AuthUser(Base):
    __tablename__ = "auth_users"
    business_id: Mapped[str] = business_id_column()
    id = uuid_pk()
    tenant_id = tenant_fk()
    username: Mapped[str] = mapped_column(String(254), nullable=False)
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    company: Mapped[str] = mapped_column(String(160), nullable=False)
    password_hash: Mapped[str] = mapped_column(Text, nullable=False)
    role: Mapped[str] = mapped_column(String(120), nullable=False, server_default="Viewer")
    status: Mapped[str] = mapped_column(String(40), nullable=False, server_default="PENDING_VERIFICATION")
    email_verified: Mapped[bool] = mapped_column(nullable=False, server_default="false")
    mfa_required: Mapped[bool] = mapped_column(nullable=False, server_default="false")
    mfa_enrolled_at = tz(True)
    # Authenticator-app MFA (auth/totp.py): the secret is encrypted; the last used time step stops code replay;
    # recovery codes are stored as hashes only.
    mfa_secret_encrypted: Mapped[str | None] = mapped_column(Text)
    mfa_pending_secret_encrypted: Mapped[str | None] = mapped_column(Text)
    mfa_last_step: Mapped[int | None] = mapped_column(BigInteger)
    mfa_recovery_hashes: Mapped[list | None] = mapped_column(JSONB)
    # md44: the person's email choices; {"weekly_readiness": false} stops the weekly readiness email.
    email_preferences: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    # tr13: the workspace persona ("Viewing as", access_control/personas.py WORKSPACE_PERSONAS); a view, never a
    # permission. Empty: it follows the role.
    view_persona: Mapped[str | None] = mapped_column(String(40))
    password_changed_at = tz(True)
    password_expires_at = tz(True)
    created_at = tz(False)
    updated_at = tz(False)
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_auth_users_tenant_id_id"),
        CheckConstraint(
            "upper(replace(replace(btrim(role), ' ', '_'), '-', '_')) not in "
            "('PLATFORM_ADMIN','MDARIX_ADMINISTRATOR','ADMINISTRATOR','ADMIN','CUSTOMER_ADMIN',"
            "'CUSTOMER_ADMINISTRATOR') or role in ('PLATFORM_ADMIN','CUSTOMER_ADMIN')",
            name="auth_user_administrator_role_canonical",
        ),
    )

    @validates("role")
    def _canonicalize_role(self, _key: str, value: str) -> str:
        return canonical_stored_role(value)


class TenantMembership(Base):
    __tablename__ = "tenant_memberships"
    id = uuid_pk()
    tenant_id = tenant_fk()
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, server_default="ACTIVE")
    is_default: Mapped[bool] = mapped_column(nullable=False, server_default="false")
    created_at = tz(False)
    updated_at = tz(False)
    __table_args__ = (
        ForeignKeyConstraint(["tenant_id", "user_id"], ["auth_users.tenant_id", "auth_users.id"]),
        UniqueConstraint("tenant_id", "user_id", name="uq_tenant_membership"),
        UniqueConstraint("tenant_id", "id", name="uq_tenant_membership_tenant_id"),
    )


class PersonaAssignment(Base):
    __tablename__ = "persona_assignments"
    id = uuid_pk()
    tenant_id = tenant_fk()
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    persona_code: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, server_default="ACTIVE")
    created_at = tz(False)
    updated_at = tz(False)
    __table_args__ = (
        ForeignKeyConstraint(["tenant_id", "user_id"], ["auth_users.tenant_id", "auth_users.id"]),
        UniqueConstraint("tenant_id", "user_id", "persona_code", name="uq_persona_assignment"),
        UniqueConstraint("tenant_id", "id", name="uq_persona_assignment_tenant_id"),
    )


class PermissionSetDefinition(Base):
    __tablename__ = "permission_set_definitions"
    id = uuid_pk()
    tenant_id = tenant_fk()
    code: Mapped[str] = mapped_column(String(100), nullable=False)
    object_permissions: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    field_permissions: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    action_permissions: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    version: Mapped[str] = mapped_column(String(40), nullable=False, server_default="v1")
    status: Mapped[str] = mapped_column(String(30), nullable=False, server_default="DRAFT")
    created_at = tz(False)
    updated_at = tz(False)
    __table_args__ = (
        UniqueConstraint("tenant_id", "code", "version", name="uq_permission_set_definition"),
        UniqueConstraint("tenant_id", "id", name="uq_permission_set_definition_tenant_id"),
    )


class RoleDefinition(Base):
    __tablename__ = "role_definitions"
    id = uuid_pk()
    tenant_id = tenant_fk()
    code: Mapped[str] = mapped_column(String(100), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    version: Mapped[str] = mapped_column(String(40), nullable=False, server_default="v1")
    status: Mapped[str] = mapped_column(String(30), nullable=False, server_default="DRAFT")
    created_at = tz(False)
    updated_at = tz(False)
    __table_args__ = (
        UniqueConstraint("tenant_id", "code", "version", name="uq_role_definition"),
        UniqueConstraint("tenant_id", "id", name="uq_role_definition_tenant_id"),
    )


class RolePermissionSet(Base):
    __tablename__ = "role_permission_sets"
    id = uuid_pk()
    tenant_id = tenant_fk()
    role_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    permission_set_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    created_at = tz(False)
    __table_args__ = (
        ForeignKeyConstraint(["tenant_id", "role_id"], ["role_definitions.tenant_id", "role_definitions.id"]),
        ForeignKeyConstraint(
            ["tenant_id", "permission_set_id"],
            ["permission_set_definitions.tenant_id", "permission_set_definitions.id"],
        ),
        UniqueConstraint("tenant_id", "role_id", "permission_set_id", name="uq_role_permission_set"),
    )


class RoleAssignment(Base):
    __tablename__ = "role_assignments"
    id = uuid_pk()
    tenant_id = tenant_fk()
    user_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    role_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False, server_default="ACTIVE")
    created_at = tz(False)
    updated_at = tz(False)
    __table_args__ = (
        ForeignKeyConstraint(["tenant_id", "user_id"], ["auth_users.tenant_id", "auth_users.id"]),
        ForeignKeyConstraint(["tenant_id", "role_id"], ["role_definitions.tenant_id", "role_definitions.id"]),
        UniqueConstraint("tenant_id", "user_id", "role_id", name="uq_role_assignment"),
        UniqueConstraint("tenant_id", "id", name="uq_role_assignment_tenant_id"),
    )


class PlanDefinition(Base):
    __tablename__ = "plan_definitions"
    business_id: Mapped[str] = business_id_column()
    id = uuid_pk()
    code: Mapped[str] = mapped_column(String(80), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    version: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    effective_from = tz(False)
    effective_to = tz()
    created_at = tz(False)
    updated_at = tz(False)


class FeatureEntitlement(Base):
    __tablename__ = "feature_entitlements"
    id = uuid_pk()
    plan_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("plan_definitions.id"), nullable=False)
    feature_code: Mapped[str] = mapped_column(String(120), nullable=False)
    enabled: Mapped[bool] = mapped_column(nullable=False)
    limits: Mapped[dict | None] = mapped_column(JSONB)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    created_at = tz(False)
    updated_at = tz(False)
    __table_args__ = (UniqueConstraint("plan_id", "feature_code", name="uq_plan_feature_entitlement"),)


class TenantPlanAssignment(Base):
    __tablename__ = "tenant_plan_assignments"
    id = uuid_pk()
    tenant_id = tenant_fk()
    plan_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("plan_definitions.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    effective_from = tz(False)
    effective_to = tz()
    reason: Mapped[str | None] = mapped_column(Text)
    # This tenant's own limits (licensed_users_limit, customer_admin_limit, connector_limit); they take precedence
    # over the plan's, which are shared by every tenant on the plan.
    limits: Mapped[dict | None] = mapped_column(JSONB)
    created_at = tz(False)
    updated_at = tz(False)


class ApprovalAuthority(Base):
    __tablename__ = "approval_authorities"
    id = uuid_pk()
    tenant_id = tenant_fk()
    role_name: Mapped[str] = mapped_column(String(120), nullable=False)
    object_type: Mapped[str] = mapped_column(String(120), nullable=False)
    decision_type: Mapped[str] = mapped_column(String(120), nullable=False)
    scope: Mapped[dict | None] = mapped_column(JSONB)
    authority: Mapped[str] = mapped_column(String(30), nullable=False)
    version: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    effective_from = tz(False)
    effective_to = tz()
    created_at = tz(False)
    updated_at = tz(False)


class SegregationOfDutiesPolicy(Base):
    __tablename__ = "segregation_of_duties_policies"
    id = uuid_pk()
    tenant_id = tenant_fk()
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    object_type: Mapped[str] = mapped_column(String(120), nullable=False)
    decision_type: Mapped[str] = mapped_column(String(120), nullable=False)
    creator_cannot_approve: Mapped[bool] = mapped_column(nullable=False)
    last_material_editor_cannot_approve: Mapped[bool] = mapped_column(nullable=False)
    version: Mapped[str] = mapped_column(String(40), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    effective_from = tz(False)
    effective_to = tz()
    created_at = tz(False)
    updated_at = tz(False)


class SignedApprovalRecord(Base):
    __tablename__ = "signed_approval_records"
    business_id: Mapped[str] = business_id_column()
    id = uuid_pk()
    tenant_id = tenant_fk()
    object_type: Mapped[str] = mapped_column(String(120), nullable=False)
    object_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    object_version: Mapped[str] = mapped_column(String(80), nullable=False)
    decision_type: Mapped[str] = mapped_column(String(120), nullable=False)
    decision: Mapped[str] = mapped_column(String(12), nullable=False)
    remarks: Mapped[str] = mapped_column(Text, nullable=False)
    signer_user_id: Mapped[str] = mapped_column(String(254), nullable=False)
    signer_role: Mapped[str] = mapped_column(String(120), nullable=False)
    signature_meaning: Mapped[str] = mapped_column(Text, nullable=False)
    content_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    signature_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(30), nullable=False)
    signed_at = tz(False)
    invalidated_at = tz()
    invalidation_reason: Mapped[str | None] = mapped_column(Text)
    created_at = tz(False)
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "object_type",
            "object_id",
            "object_version",
            "decision_type",
            name="uq_signed_approval_version",
        ),
    )


class ProductComponent(Base):
    __tablename__ = "product_components"
    id = uuid_pk()
    tenant_id = tenant_fk()
    product_version_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    component_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    relationship_status: Mapped[str] = mapped_column(String(40), nullable=False, server_default="active")
    effective_timestamp = tz()
    evidence_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    created_at = tz(False)
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "product_version_id"], ["product_versions.tenant_id", "product_versions.id"]
        ),
        ForeignKeyConstraint(["tenant_id", "component_id"], ["components.tenant_id", "components.id"]),
        ForeignKeyConstraint(["tenant_id", "evidence_id"], ["evidence.tenant_id", "evidence.id"]),
        UniqueConstraint(
            "tenant_id", "product_version_id", "component_id", name="uq_product_components_version_component"
        ),
    )


class ProductSupplier(Base):
    __tablename__ = "product_suppliers"
    id = uuid_pk()
    tenant_id = tenant_fk()
    product_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    supplier_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    effective_timestamp = tz()
    evidence_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    created_at = tz(False)
    __table_args__ = (
        ForeignKeyConstraint(["tenant_id", "product_id"], ["products.tenant_id", "products.id"]),
        ForeignKeyConstraint(["tenant_id", "supplier_id"], ["suppliers.tenant_id", "suppliers.id"]),
        ForeignKeyConstraint(["tenant_id", "evidence_id"], ["evidence.tenant_id", "evidence.id"]),
    )


class ComponentSupplier(Base):
    __tablename__ = "component_suppliers"
    id = uuid_pk()
    tenant_id = tenant_fk()
    component_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    supplier_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    effective_timestamp = tz()
    evidence_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    created_at = tz(False)
    __table_args__ = (
        ForeignKeyConstraint(["tenant_id", "component_id"], ["components.tenant_id", "components.id"]),
        ForeignKeyConstraint(["tenant_id", "supplier_id"], ["suppliers.tenant_id", "suppliers.id"]),
        ForeignKeyConstraint(["tenant_id", "evidence_id"], ["evidence.tenant_id", "evidence.id"]),
        UniqueConstraint("tenant_id", "component_id", "supplier_id", name="uq_component_suppliers_component_supplier"),
    )


class LotComponent(Base):
    __tablename__ = "lot_components"
    id = uuid_pk()
    tenant_id = tenant_fk()
    lot_batch_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    component_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    # The component's own lot that went into this lot (genealogy), when the source records it.
    component_lot_identifier: Mapped[str | None] = mapped_column(String(120))
    evidence_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    created_at = tz(False)
    __table_args__ = (
        ForeignKeyConstraint(["tenant_id", "lot_batch_id"], ["lot_batches.tenant_id", "lot_batches.id"]),
        ForeignKeyConstraint(["tenant_id", "component_id"], ["components.tenant_id", "components.id"]),
        ForeignKeyConstraint(["tenant_id", "evidence_id"], ["evidence.tenant_id", "evidence.id"]),
    )


class InvestigationComplaint(Base):
    __tablename__ = "investigation_complaints"
    id = uuid_pk()
    tenant_id = tenant_fk()
    investigation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    complaint_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    created_at = tz(False)
    __table_args__ = (
        ForeignKeyConstraint(["tenant_id", "investigation_id"], ["investigations.tenant_id", "investigations.id"]),
        ForeignKeyConstraint(["tenant_id", "complaint_id"], ["complaints.tenant_id", "complaints.id"]),
        UniqueConstraint("tenant_id", "investigation_id", "complaint_id", name="uq_investigation_complaints_pair"),
    )


class InvestigationEvidence(Base):
    __tablename__ = "investigation_evidence"
    id = uuid_pk()
    tenant_id = tenant_fk()
    investigation_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    evidence_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    relevance: Mapped[str | None] = mapped_column(Text)
    created_at = tz(False)
    # The case's review of this evidence (md29): its quality (review_status) and what it means for the case
    # (relationship) are separate judgements. Every change is kept in evidence_review_events.
    review_status: Mapped[str] = mapped_column(String(30), nullable=False, server_default="UNREVIEWED")
    relationship: Mapped[str] = mapped_column(String(30), nullable=False, server_default="UNREVIEWED")
    review_reason: Mapped[str | None] = mapped_column(Text)
    limitation: Mapped[str | None] = mapped_column(Text)
    reviewed_by: Mapped[str | None] = mapped_column(String(255))
    reviewed_at = tz()
    linked_by: Mapped[str | None] = mapped_column(String(255))
    __table_args__ = (
        ForeignKeyConstraint(["tenant_id", "investigation_id"], ["investigations.tenant_id", "investigations.id"]),
        ForeignKeyConstraint(["tenant_id", "evidence_id"], ["evidence.tenant_id", "evidence.id"]),
        UniqueConstraint("tenant_id", "investigation_id", "evidence_id", name="uq_investigation_evidence_pair"),
        CheckConstraint(
            "review_status IN ('UNREVIEWED', 'ACCEPTED', 'ACCEPTED_WITH_LIMITATION', 'REJECTED', 'QUARANTINED', "
            "'SUPERSEDED')",
            name="review_status_known",
        ),
        CheckConstraint(
            "relationship IN ('SUPPORTING', 'CONTRADICTING', 'CONTEXTUAL', 'UNRESOLVED', 'UNRELATED', 'UNREVIEWED')",
            name="relationship_known",
        ),
    )


class HypothesisEvidence(Base):
    __tablename__ = "hypothesis_evidence"
    id = uuid_pk()
    tenant_id = tenant_fk()
    hypothesis_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    evidence_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    relation_type: Mapped[str] = mapped_column(String(20), nullable=False)
    rationale: Mapped[str | None] = mapped_column(Text)
    created_by_type: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at = tz(False)
    # md30: who linked it (a person, or the system for AI links), and a withdrawal instead of a deletion.
    created_by: Mapped[str | None] = mapped_column(String(255))
    retracted_at = tz()
    retracted_by: Mapped[str | None] = mapped_column(String(255))
    retraction_reason: Mapped[str | None] = mapped_column(Text)
    __table_args__ = (
        ForeignKeyConstraint(["tenant_id", "hypothesis_id"], ["hypotheses.tenant_id", "hypotheses.id"]),
        ForeignKeyConstraint(["tenant_id", "evidence_id"], ["evidence.tenant_id", "evidence.id"]),
        CheckConstraint(
            "relation_type in ('support','contradict','contextual','unresolved')",
            name="hypothesis_evidence_relation_allowed",
        ),
        CheckConstraint("created_by_type in ('ai','human','system')", name="hypothesis_evidence_creator_allowed"),
    )


class FailureChainNode(Base):
    __tablename__ = "failure_chain_nodes"
    id = uuid_pk()
    tenant_id = tenant_fk()
    failure_chain_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    sequence_number: Mapped[int] = mapped_column(nullable=False)
    node_type: Mapped[str] = mapped_column(String(80), nullable=False)
    label: Mapped[str] = mapped_column(String(255), nullable=False)
    lifecycle_object_type: Mapped[str | None] = mapped_column(String(120))
    lifecycle_object_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    evidence_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    created_at = tz(False)
    __table_args__ = (
        ForeignKeyConstraint(["tenant_id", "failure_chain_id"], ["failure_chains.tenant_id", "failure_chains.id"]),
        ForeignKeyConstraint(["tenant_id", "evidence_id"], ["evidence.tenant_id", "evidence.id"]),
        UniqueConstraint("tenant_id", "failure_chain_id", "sequence_number", name="uq_failure_chain_nodes_sequence"),
        UniqueConstraint("tenant_id", "id", name="uq_failure_chain_nodes_tenant_id_id"),
    )


class FailureChainEdge(Base):
    __tablename__ = "failure_chain_edges"
    id = uuid_pk()
    tenant_id = tenant_fk()
    failure_chain_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    from_node_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    to_node_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    edge_status: Mapped[str] = mapped_column(String(40), nullable=False)
    evidence_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    rationale: Mapped[str | None] = mapped_column(Text)
    created_at = tz(False)
    # md30: link states SUPPORTED, PARTIALLY_SUPPORTED, HYPOTHESIZED, UNKNOWN, CONTRADICTED; who set them.
    updated_by: Mapped[str | None] = mapped_column(String(255))
    updated_at = tz()
    __table_args__ = (
        ForeignKeyConstraint(["tenant_id", "failure_chain_id"], ["failure_chains.tenant_id", "failure_chains.id"]),
        ForeignKeyConstraint(
            ["tenant_id", "from_node_id"],
            ["failure_chain_nodes.tenant_id", "failure_chain_nodes.id"],
            name="fk_failure_chain_edges_from_node",
        ),
        ForeignKeyConstraint(
            ["tenant_id", "to_node_id"],
            ["failure_chain_nodes.tenant_id", "failure_chain_nodes.id"],
            name="fk_failure_chain_edges_to_node",
        ),
        ForeignKeyConstraint(["tenant_id", "evidence_id"], ["evidence.tenant_id", "evidence.id"]),
        CheckConstraint(
            # md31 adds the link states people and adopted AI chains use; the original three stay valid.
            "edge_status in ('established_fact','hypothesized','contradicted',"
            "'SUPPORTED','PARTIALLY_SUPPORTED','HYPOTHESIZED','UNKNOWN','CONTRADICTED')",
            name="failure_chain_edge_status_allowed",
        ),
    )


class RealityRelationship(Base):
    __tablename__ = "reality_relationships"
    id = uuid_pk()
    tenant_id = tenant_fk()
    source_entity_type: Mapped[str] = mapped_column(String(120), nullable=False)
    source_entity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    target_entity_type: Mapped[str] = mapped_column(String(120), nullable=False)
    target_entity_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    relationship_type: Mapped[str] = mapped_column(String(120), nullable=False)
    assertion_status: Mapped[str] = mapped_column(String(40), nullable=False, server_default="supported")
    evidence_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    confidence_label: Mapped[str | None] = mapped_column(String(80))
    effective_timestamp = tz()
    recorded_timestamp = tz()
    provenance: Mapped[dict | None] = mapped_column(JSONB)
    created_at = tz(False)
    __table_args__ = (
        ForeignKeyConstraint(["tenant_id", "evidence_id"], ["evidence.tenant_id", "evidence.id"]),
        CheckConstraint(
            "assertion_status in ('supported','contradicted','hypothesized','unknown')",
            name="reality_relationship_assertion_allowed",
        ),
    )


class EvidenceEmbedding(Base):
    __tablename__ = "evidence_embeddings"
    id = uuid_pk()
    tenant_id = tenant_fk()
    evidence_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    embedding_model: Mapped[str] = mapped_column(String(120), nullable=False)
    embedding: Mapped[object | None] = mapped_column(Vector(1536))
    embedding_vector_ref: Mapped[str | None] = mapped_column(String(255))
    created_at = tz(False)
    __table_args__ = (ForeignKeyConstraint(["tenant_id", "evidence_id"], ["evidence.tenant_id", "evidence.id"]),)


class ConnectorConfiguration(Base):
    __tablename__ = "connector_configurations"
    business_id: Mapped[str] = business_id_column()
    id = uuid_pk()
    tenant_id = tenant_fk()
    code: Mapped[str] = mapped_column(String(100), nullable=False)
    connector_type: Mapped[str] = mapped_column(String(80), nullable=False)
    configuration: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    version: Mapped[str] = mapped_column(String(40), nullable=False, server_default="v1")
    status: Mapped[str] = mapped_column(String(30), nullable=False, server_default="DRAFT")
    # The customer system's API key, encrypted (AES-GCM); never returned. Takes precedence over credential_ref.
    credential_encrypted: Mapped[str | None] = mapped_column(Text)
    credential_hint: Mapped[str | None] = mapped_column(String(8))
    credential_set_at = tz()
    created_at = tz(False)
    updated_at = tz(False)
    __table_args__ = (UniqueConstraint("tenant_id", "code", "version", name="uq_connector_configuration"),)


class MappingConfiguration(Base):
    __tablename__ = "mapping_configurations"
    id = uuid_pk()
    tenant_id = tenant_fk()
    code: Mapped[str] = mapped_column(String(100), nullable=False)
    source_system: Mapped[str] = mapped_column(String(120), nullable=False)
    target_entity: Mapped[str] = mapped_column(String(120), nullable=False)
    mapping_rules: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    version: Mapped[str] = mapped_column(String(40), nullable=False, server_default="v1")
    status: Mapped[str] = mapped_column(String(30), nullable=False, server_default="DRAFT")
    created_at = tz(False)
    updated_at = tz(False)
    __table_args__ = (UniqueConstraint("tenant_id", "code", "version", name="uq_mapping_configuration"),)


class MasterMapping(Base):
    __tablename__ = "master_mappings"
    id = uuid_pk()
    code: Mapped[str] = mapped_column(String(100), nullable=False, unique=True)
    source_system: Mapped[str] = mapped_column(String(120), nullable=False)
    target_entity: Mapped[str] = mapped_column(String(120), nullable=False)
    definition: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    status: Mapped[str] = mapped_column(String(30), nullable=False, server_default="ACTIVE")
    created_at = tz(False)
    updated_at = tz(False)


class TenantMappingVersion(Base):
    __tablename__ = "tenant_mapping_versions"
    id = uuid_pk()
    tenant_id = tenant_fk()
    master_mapping_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    version: Mapped[str] = mapped_column(String(40), nullable=False)
    rules: Mapped[dict | list] = mapped_column(JSONB, nullable=False, server_default="{}")
    status: Mapped[str] = mapped_column(String(30), nullable=False, server_default="DRAFT")
    effective_from = tz()
    effective_to = tz()
    created_at = tz(False)
    updated_at = tz(False)
    __table_args__ = (
        ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        ForeignKeyConstraint(["master_mapping_id"], ["master_mappings.id"]),
        UniqueConstraint("tenant_id", "master_mapping_id", "version", name="uq_tenant_mapping_version"),
        UniqueConstraint("tenant_id", "id", name="uq_tenant_mapping_version_tenant_id"),
    )


class TenantMappingOverride(Base):
    __tablename__ = "tenant_mapping_overrides"
    id = uuid_pk()
    tenant_id = tenant_fk()
    mapping_version_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    field_name: Mapped[str] = mapped_column(String(160), nullable=False)
    override_rule: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    status: Mapped[str] = mapped_column(String(30), nullable=False, server_default="ACTIVE")
    created_at = tz(False)
    updated_at = tz(False)
    __table_args__ = (
        ForeignKeyConstraint(
            ["tenant_id", "mapping_version_id"], ["tenant_mapping_versions.tenant_id", "tenant_mapping_versions.id"]
        ),
        UniqueConstraint("tenant_id", "mapping_version_id", "field_name", name="uq_tenant_mapping_override"),
    )


class MappingImpactHistory(Base):
    __tablename__ = "mapping_impact_history"
    id = uuid_pk()
    tenant_id = tenant_fk()
    master_mapping_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    from_version: Mapped[str | None] = mapped_column(String(40))
    to_version: Mapped[str] = mapped_column(String(40), nullable=False)
    impact: Mapped[dict] = mapped_column(JSONB, nullable=False, server_default="{}")
    created_at = tz(False)
    __table_args__ = (
        ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        ForeignKeyConstraint(["master_mapping_id"], ["master_mappings.id"]),
    )


Index("ix_products_tenant_product_identifier", Product.tenant_id, Product.product_identifier)
Index("ix_product_versions_tenant_product", ProductVersion.tenant_id, ProductVersion.product_id)
Index("ix_components_tenant_identifier", Component.tenant_id, Component.component_identifier)
Index("ix_complaints_tenant_product_event", Complaint.tenant_id, Complaint.product_id, Complaint.event_timestamp)
Index("ix_investigations_tenant_product", Investigation.tenant_id, Investigation.product_id)
Index("ix_evidence_tenant_investigation", Evidence.tenant_id, Evidence.investigation_id)
Index(
    "ix_hypothesis_evidence_relation",
    HypothesisEvidence.tenant_id,
    HypothesisEvidence.hypothesis_id,
    HypothesisEvidence.relation_type,
)
Index(
    "ix_reality_relationship_lookup",
    RealityRelationship.tenant_id,
    RealityRelationship.source_entity_type,
    RealityRelationship.source_entity_id,
)
