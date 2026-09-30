"""MDARIX Master Data (schema ``md_master``).

Implements *MDARIX Master Data Foundation and Maintenance Standard v1.0*.
Every table has an internal UUID primary key (``<entity>_uuid``) and an
immutable, sequential business identifier (``<entity>_id``, e.g. APP00001)
issued by ``md_master.next_business_id(prefix)`` as a column default, so IDs are
always allocated by the database and never by a client.
"""

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from backend.app.db.base import Base

SCHEMA = "md_master"

ACTIVE_RETIRED = ("ACTIVE", "RETIRED")
ACTIVE_DEPRECATED_RETIRED = ("ACTIVE", "DEPRECATED", "RETIRED")


def _pk():
    return mapped_column(UUID(as_uuid=True), primary_key=True, server_default=text("gen_random_uuid()"))


def _business_id(prefix: str):
    return mapped_column(
        String(24), nullable=False, unique=True, server_default=text(f"md_master.next_business_id('{prefix}')")
    )


def _fk(target: str, nullable: bool = True):
    return mapped_column(UUID(as_uuid=True), ForeignKey(f"{SCHEMA}.{target}"), nullable=nullable)


def _flag(default: bool = False):
    return mapped_column(Boolean, nullable=False, server_default=text("true" if default else "false"))


def _status(default: str = "ACTIVE"):
    return mapped_column(String(30), nullable=False, server_default=default)


def _in(column: str, values: tuple[str, ...]) -> str:
    return f"{column} in ({', '.join(repr(v) for v in values)})"


def _args(table: str, statuses: tuple[str, ...], *extra):
    """Table args: status CHECK, extra constraints and the md_master schema."""
    return (CheckConstraint(_in("status", statuses), name="status_allowed"), *extra, {"schema": SCHEMA})


def _upper(column: str) -> CheckConstraint:
    return CheckConstraint(f"{column} = upper({column})", name=f"{column}_upper")


class _Audit:
    """Creation/update tracking required by Master Data §12.2."""

    created_at = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    created_by = mapped_column(UUID(as_uuid=True), nullable=True)
    updated_by = mapped_column(UUID(as_uuid=True), nullable=True)


class BusinessIdPrefix(Base):
    """Registry of business-identifier prefixes and their sequences (§1.2)."""

    __tablename__ = "business_id_prefix"
    prefix: Mapped[str] = mapped_column(String(12), primary_key=True)
    entity_name: Mapped[str] = mapped_column(String(120), nullable=False)
    sequence_name: Mapped[str] = mapped_column(String(80), nullable=False, unique=True)
    id_width: Mapped[int] = mapped_column(Integer, nullable=False, server_default="5")
    owning_schema: Mapped[str] = mapped_column(String(40), nullable=False)
    created_at = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    __table_args__ = (
        CheckConstraint("prefix ~ '^[A-Z]{1,12}$'", name="prefix_format"),
        CheckConstraint("id_width between 3 and 12", name="id_width_range"),
        {"schema": SCHEMA},
    )


# --- 3. Industry and application masters ------------------------------------


class IndustryDomain(_Audit, Base):
    __tablename__ = "industry_domain"
    industry_uuid = _pk()
    industry_id = _business_id("IND")
    industry_code = mapped_column(String(100), nullable=False, unique=True)
    industry_name = mapped_column(String(255), nullable=False)
    description = mapped_column(Text)
    status = _status()
    display_order = mapped_column(Integer)
    __table_args__ = _args("industry_domain", ACTIVE_DEPRECATED_RETIRED, _upper("industry_code"))


class ApplicationVendor(_Audit, Base):
    __tablename__ = "application_vendor"
    vendor_uuid = _pk()
    vendor_id = _business_id("VEND")
    vendor_code = mapped_column(String(100), nullable=False, unique=True)
    vendor_name = mapped_column(String(255), nullable=False, unique=True)
    legal_name = mapped_column(String(255))
    website = mapped_column(String(500))
    country_uuid = _fk("country_reference.country_uuid")
    status = _status()
    __table_args__ = _args("application_vendor", ACTIVE_DEPRECATED_RETIRED, _upper("vendor_code"))


class ApplicationCategory(_Audit, Base):
    __tablename__ = "application_category"
    category_uuid = _pk()
    category_id = _business_id("APPCAT")
    category_code = mapped_column(String(100), nullable=False, unique=True)
    category_name = mapped_column(String(255), nullable=False)
    description = mapped_column(Text)
    display_order = mapped_column(Integer)
    status = _status()
    __table_args__ = _args("application_category", ACTIVE_RETIRED, _upper("category_code"))


class ExternalApplication(_Audit, Base):
    __tablename__ = "external_application"
    application_uuid = _pk()
    application_id = _business_id("APP")
    application_code = mapped_column(String(100), nullable=False, unique=True)
    application_name = mapped_column(String(255), nullable=False)
    vendor_uuid = _fk("application_vendor.vendor_uuid", nullable=False)
    category_uuid = _fk("application_category.category_uuid", nullable=False)
    description = mapped_column(Text)
    integration_support_status = mapped_column(String(30), nullable=False, server_default="PLANNED")
    supports_api = _flag()
    supports_webhook = _flag()
    supports_schema_discovery = _flag()
    supports_incremental_sync = _flag()
    status = _status("DRAFT")
    __table_args__ = _args(
        "external_application",
        ("DRAFT", "ACTIVE", "DEPRECATED", "RETIRED"),
        _upper("application_code"),
        CheckConstraint(
            _in("integration_support_status", ("PLANNED", "CONFIGURABLE", "SUPPORTED")), name="support_status_allowed"
        ),
    )


class ExternalApplicationIndustry(_Audit, Base):
    __tablename__ = "external_application_industry"
    relation_uuid = _pk()
    relation_id = _business_id("APPIND")
    application_uuid = _fk("external_application.application_uuid", nullable=False)
    industry_uuid = _fk("industry_domain.industry_uuid", nullable=False)
    is_primary = _flag()
    status = _status()
    __table_args__ = _args(
        "external_application_industry",
        ("ACTIVE", "INACTIVE"),
        UniqueConstraint("application_uuid", "industry_uuid", name="uq_external_application_industry_pair"),
    )


class ApplicationVersionDefinition(_Audit, Base):
    __tablename__ = "application_version_definition"
    application_version_uuid = _pk()
    application_version_id = _business_id("APPVER")
    application_uuid = _fk("external_application.application_uuid", nullable=False)
    version_code = mapped_column(String(80), nullable=False)
    api_version = mapped_column(String(80))
    schema_version = mapped_column(String(80))
    release_date = mapped_column(Date)
    support_status = mapped_column(String(30), nullable=False, server_default="SUPPORTED")
    effective_from = mapped_column(Date)
    effective_to = mapped_column(Date)
    status = _status()
    __table_args__ = _args(
        "application_version_definition",
        ACTIVE_DEPRECATED_RETIRED,
        UniqueConstraint("application_uuid", "version_code", name="uq_application_version_definition_code"),
        CheckConstraint(_in("support_status", ("SUPPORTED", "LEGACY", "PLANNED")), name="support_status_allowed"),
    )


# --- 4. Source schema masters -------------------------------------------------


class SourceObjectDefinition(_Audit, Base):
    __tablename__ = "source_object_definition"
    source_object_uuid = _pk()
    source_object_id = _business_id("SOBJ")
    application_uuid = _fk("external_application.application_uuid", nullable=False)
    application_version_uuid = _fk("application_version_definition.application_version_uuid")
    object_code = mapped_column(String(100), nullable=False)
    object_name = mapped_column(String(255), nullable=False)
    api_object_name = mapped_column(String(255))
    primary_key_field = mapped_column(String(255))
    incremental_cursor_field = mapped_column(String(255))
    schema_version = mapped_column(String(80))
    status = _status()
    effective_from = mapped_column(Date)
    effective_to = mapped_column(Date)
    __table_args__ = _args(
        "source_object_definition",
        ACTIVE_DEPRECATED_RETIRED,
        _upper("object_code"),
        UniqueConstraint("application_uuid", "object_code", name="uq_source_object_definition_code"),
    )


class FieldGroupDefinition(_Audit, Base):
    __tablename__ = "field_group_definition"
    field_group_uuid = _pk()
    field_group_id = _business_id("FGRP")
    group_code = mapped_column(String(100), nullable=False, unique=True)
    group_name = mapped_column(String(255), nullable=False)
    description = mapped_column(Text)
    display_order = mapped_column(Integer)
    status = _status()
    __table_args__ = _args("field_group_definition", ACTIVE_RETIRED, _upper("group_code"))


FIELD_DATA_TYPES = (
    "STRING",
    "TEXT",
    "INTEGER",
    "DECIMAL",
    "BOOLEAN",
    "DATE",
    "DATETIME",
    "UUID",
    "UUID_REF",
    "JSON",
    "ENUM",
)


class SourceFieldDefinition(_Audit, Base):
    __tablename__ = "source_field_definition"
    source_field_uuid = _pk()
    source_field_id = _business_id("SFLD")
    source_object_uuid = _fk("source_object_definition.source_object_uuid", nullable=False)
    field_name = mapped_column(String(255), nullable=False)
    field_label = mapped_column(String(255), nullable=False)
    field_group_uuid = _fk("field_group_definition.field_group_uuid")
    description = mapped_column(Text)
    data_type = mapped_column(String(30), nullable=False)
    required = _flag()
    nullable = _flag(True)
    sample_value = mapped_column(Text)
    data_classification_uuid = _fk("data_classification.classification_uuid")
    introduced_schema_version = mapped_column(String(80))
    deprecated_schema_version = mapped_column(String(80))
    status = _status()
    __table_args__ = _args(
        "source_field_definition",
        ACTIVE_DEPRECATED_RETIRED,
        UniqueConstraint("source_object_uuid", "field_name", name="uq_source_field_definition_name"),
        CheckConstraint(_in("data_type", FIELD_DATA_TYPES), name="data_type_allowed"),
    )


# --- 5. Canonical model masters ---------------------------------------------------


class CanonicalEntityDefinition(_Audit, Base):
    __tablename__ = "canonical_entity_definition"
    canonical_entity_uuid = _pk()
    canonical_entity_id = _business_id("CENT")
    entity_code = mapped_column(String(100), nullable=False, unique=True)
    entity_name = mapped_column(String(255), nullable=False)
    domain = mapped_column(String(80), nullable=False)
    description = mapped_column(Text)
    version = mapped_column(String(40), nullable=False)
    status = _status()
    __table_args__ = _args("canonical_entity_definition", ACTIVE_DEPRECATED_RETIRED, _upper("entity_code"))


class CanonicalFieldDefinition(_Audit, Base):
    __tablename__ = "canonical_field_definition"
    canonical_field_uuid = _pk()
    canonical_field_id = _business_id("CFLD")
    canonical_entity_uuid = _fk("canonical_entity_definition.canonical_entity_uuid", nullable=False)
    field_name = mapped_column(String(255), nullable=False)
    field_label = mapped_column(String(255), nullable=False)
    data_type = mapped_column(String(30), nullable=False)
    required = _flag()
    nullable = _flag(True)
    reference_entity_uuid = _fk("canonical_entity_definition.canonical_entity_uuid")
    system_managed = _flag()
    mapping_allowed = _flag(True)
    override_policy_uuid = _fk("mapping_override_policy.override_policy_uuid")
    data_classification_uuid = _fk("data_classification.classification_uuid")
    field_group_uuid = _fk("field_group_definition.field_group_uuid")
    status = _status()
    __table_args__ = _args(
        "canonical_field_definition",
        ACTIVE_DEPRECATED_RETIRED,
        UniqueConstraint("canonical_entity_uuid", "field_name", name="uq_canonical_field_definition_name"),
        CheckConstraint(_in("data_type", FIELD_DATA_TYPES), name="data_type_allowed"),
        # Protected system fields (tenant ownership, provenance, audit) are never mapping targets.
        CheckConstraint("not (system_managed and mapping_allowed)", name="system_managed_not_mappable"),
        CheckConstraint("data_type <> 'UUID_REF' or reference_entity_uuid is not null", name="reference_has_target"),
    )


# --- 6. Mapping, transformation and validation masters ------------------------------


class MappingOverridePolicy(_Audit, Base):
    __tablename__ = "mapping_override_policy"
    override_policy_uuid = _pk()
    override_policy_id = _business_id("OVRP")
    policy_code = mapped_column(String(100), nullable=False, unique=True)
    policy_name = mapped_column(String(255), nullable=False)
    can_edit_source = _flag()
    can_edit_target = _flag()
    can_edit_transform = _flag()
    can_edit_validation = _flag()
    can_edit_enum_mapping = _flag()
    requires_approval = _flag(True)
    status = _status()
    __table_args__ = _args("mapping_override_policy", ACTIVE_RETIRED, _upper("policy_code"))


class SourceAuthorityType(_Audit, Base):
    __tablename__ = "source_authority_type"
    source_authority_uuid = _pk()
    source_authority_id = _business_id("SAUT")
    authority_code = mapped_column(String(100), nullable=False, unique=True)
    authority_name = mapped_column(String(255), nullable=False)
    description = mapped_column(Text)
    precedence = mapped_column(Integer)
    status = _status()
    __table_args__ = _args("source_authority_type", ACTIVE_RETIRED, _upper("authority_code"))


class TransformationDefinition(_Audit, Base):
    __tablename__ = "transformation_definition"
    transformation_uuid = _pk()
    transformation_id = _business_id("TRN")
    transformation_code = mapped_column(String(100), nullable=False)
    transformation_name = mapped_column(String(255), nullable=False)
    category = mapped_column(String(30), nullable=False)
    description = mapped_column(Text)
    parameter_schema = mapped_column(JSONB)
    customer_override_allowed = _flag()
    version = mapped_column(String(40), nullable=False)
    status = _status()
    __table_args__ = _args(
        "transformation_definition",
        ACTIVE_DEPRECATED_RETIRED,
        _upper("transformation_code"),
        UniqueConstraint("transformation_code", "version", name="uq_transformation_definition_code_version"),
        CheckConstraint(_in("category", ("DIRECT", "FORMAT", "LOOKUP", "VALUE")), name="category_allowed"),
    )


class ValidationRuleDefinition(_Audit, Base):
    __tablename__ = "validation_rule_definition"
    validation_rule_uuid = _pk()
    validation_rule_id = _business_id("VAL")
    rule_code = mapped_column(String(100), nullable=False)
    rule_name = mapped_column(String(255), nullable=False)
    rule_type = mapped_column(String(30), nullable=False)
    description = mapped_column(Text)
    parameter_schema = mapped_column(JSONB)
    severity = mapped_column(String(20), nullable=False)
    blocking = _flag()
    version = mapped_column(String(40), nullable=False)
    status = _status()
    __table_args__ = _args(
        "validation_rule_definition",
        ACTIVE_RETIRED,
        _upper("rule_code"),
        UniqueConstraint("rule_code", "version", name="uq_validation_rule_definition_code_version"),
        CheckConstraint(_in("rule_type", ("FIELD", "REFERENCE", "CROSS_FIELD")), name="rule_type_allowed"),
        CheckConstraint(_in("severity", ("INFO", "WARNING", "ERROR", "BLOCKING")), name="severity_allowed"),
    )


class ReferenceResolutionRule(_Audit, Base):
    __tablename__ = "reference_resolution_rule"
    reference_rule_uuid = _pk()
    reference_rule_id = _business_id("REFR")
    rule_code = mapped_column(String(100), nullable=False)
    target_entity_uuid = _fk("canonical_entity_definition.canonical_entity_uuid", nullable=False)
    lookup_fields = mapped_column(JSONB, nullable=False)
    match_strategy = mapped_column(String(20), nullable=False)
    case_sensitive = _flag()
    ambiguity_policy = mapped_column(String(20), nullable=False)
    not_found_policy = mapped_column(String(30), nullable=False)
    version = mapped_column(String(40), nullable=False)
    status = _status()
    __table_args__ = _args(
        "reference_resolution_rule",
        ACTIVE_RETIRED,
        _upper("rule_code"),
        UniqueConstraint("rule_code", "version", name="uq_reference_resolution_rule_code_version"),
        CheckConstraint(_in("match_strategy", ("EXACT", "NORMALIZED")), name="match_strategy_allowed"),
        CheckConstraint(_in("ambiguity_policy", ("BLOCK", "REVIEW")), name="ambiguity_policy_allowed"),
        CheckConstraint(
            _in("not_found_policy", ("BLOCK", "DEFER", "PRESERVE_UNRESOLVED")), name="not_found_policy_allowed"
        ),
    )


class DataQualityRule(_Audit, Base):
    __tablename__ = "data_quality_rule"
    data_quality_rule_uuid = _pk()
    data_quality_rule_id = _business_id("DQR")
    rule_code = mapped_column(String(100), nullable=False)
    canonical_entity_uuid = _fk("canonical_entity_definition.canonical_entity_uuid", nullable=False)
    rule_type = mapped_column(String(30), nullable=False)
    description = mapped_column(Text, nullable=False)
    severity = mapped_column(String(20), nullable=False)
    blocking = _flag()
    version = mapped_column(String(40), nullable=False)
    status = _status()
    __table_args__ = _args(
        "data_quality_rule",
        ACTIVE_RETIRED,
        _upper("rule_code"),
        UniqueConstraint("rule_code", "version", name="uq_data_quality_rule_code_version"),
        CheckConstraint(_in("rule_type", ("CROSS_FIELD", "REFERENTIAL", "TEMPORAL")), name="rule_type_allowed"),
        CheckConstraint(_in("severity", ("WARNING", "ERROR", "BLOCKING")), name="severity_allowed"),
    )


class MasterMappingFamily(_Audit, Base):
    __tablename__ = "master_mapping_family"
    mapping_family_uuid = _pk()
    mapping_family_id = _business_id("MMF")
    application_uuid = _fk("external_application.application_uuid", nullable=False)
    source_object_uuid = _fk("source_object_definition.source_object_uuid", nullable=False)
    mapping_code = mapped_column(String(100), nullable=False, unique=True)
    mapping_name = mapped_column(String(255), nullable=False)
    default_canonical_entity_uuid = _fk("canonical_entity_definition.canonical_entity_uuid", nullable=False)
    description = mapped_column(Text)
    status = _status()
    __table_args__ = _args("master_mapping_family", ACTIVE_RETIRED, _upper("mapping_code"))


MAPPING_VERSION_STATUSES = ("DRAFT", "VALIDATION", "APPROVED", "RELEASED", "SUPERSEDED", "RETIRED")


class MasterMappingVersion(_Audit, Base):
    """Versioned release of a mapping family; RELEASED content is immutable (trigger-enforced)."""

    __tablename__ = "master_mapping_version"
    mapping_version_uuid = _pk()
    mapping_version_id = _business_id("MMV")
    mapping_family_uuid = _fk("master_mapping_family.mapping_family_uuid", nullable=False)
    version_code = mapped_column(String(40), nullable=False)
    status = _status("DRAFT")
    based_on_version_uuid = _fk("master_mapping_version.mapping_version_uuid")
    source_schema_version = mapped_column(String(80))
    change_summary = mapped_column(Text)
    validated_by = mapped_column(UUID(as_uuid=True))
    validated_at = mapped_column(DateTime(timezone=True))
    approved_by = mapped_column(UUID(as_uuid=True))
    approved_at = mapped_column(DateTime(timezone=True))
    released_by = mapped_column(UUID(as_uuid=True))
    released_at = mapped_column(DateTime(timezone=True))
    released_content_hash = mapped_column(String(64))
    effective_from = mapped_column(Date)
    effective_to = mapped_column(Date)
    __table_args__ = _args(
        "master_mapping_version",
        MAPPING_VERSION_STATUSES,
        UniqueConstraint("mapping_family_uuid", "version_code", name="uq_master_mapping_version_code"),
        CheckConstraint(
            "status not in ('RELEASED', 'SUPERSEDED') or (released_at is not null and released_content_hash is not null)",
            name="released_has_evidence",
        ),
    )


class MasterMappingItem(_Audit, Base):
    """One field-to-field mapping rule; editable only while its version is DRAFT or VALIDATION."""

    __tablename__ = "master_mapping_item"
    mapping_item_uuid = _pk()
    mapping_item_id = _business_id("MMI")
    mapping_version_uuid = _fk("master_mapping_version.mapping_version_uuid", nullable=False)
    source_field_uuid = _fk("source_field_definition.source_field_uuid", nullable=False)
    canonical_entity_uuid = _fk("canonical_entity_definition.canonical_entity_uuid", nullable=False)
    canonical_field_uuid = _fk("canonical_field_definition.canonical_field_uuid", nullable=False)
    sequence_no = mapped_column(Integer, nullable=False)
    mapping_type = mapped_column(String(20), nullable=False)
    transformation_uuid = _fk("transformation_definition.transformation_uuid")
    validation_rule_uuid = _fk("validation_rule_definition.validation_rule_uuid")
    reference_rule_uuid = _fk("reference_resolution_rule.reference_rule_uuid")
    null_handling_policy = mapped_column(String(30), nullable=False, server_default="ALLOW_NULL")
    source_authority_uuid = _fk("source_authority_type.source_authority_uuid")
    required_for_mapping = _flag()
    customer_override_allowed = _flag()
    override_policy_uuid = _fk("mapping_override_policy.override_policy_uuid", nullable=False)
    default_value = mapped_column(Text)
    mapping_notes = mapped_column(Text)
    status = _status()
    __table_args__ = _args(
        "master_mapping_item",
        ("ACTIVE", "DEPRECATED"),
        UniqueConstraint("mapping_version_uuid", "canonical_field_uuid", name="uq_master_mapping_item_target"),
        UniqueConstraint("mapping_version_uuid", "sequence_no", name="uq_master_mapping_item_sequence"),
        CheckConstraint(
            _in("mapping_type", ("DIRECT", "TRANSFORM", "LOOKUP", "REFERENCE")), name="mapping_type_allowed"
        ),
        CheckConstraint(
            _in("null_handling_policy", ("ALLOW_NULL", "REJECT", "PRESERVE_UNKNOWN", "DEFAULT_VALUE")),
            name="null_handling_allowed",
        ),
        CheckConstraint("mapping_type <> 'REFERENCE' or reference_rule_uuid is not null", name="reference_has_rule"),
        CheckConstraint("mapping_type <> 'TRANSFORM' or transformation_uuid is not null", name="transform_has_rule"),
    )


# --- 7. Controlled value and enumeration masters ------------------------------------


class CanonicalValueSet(_Audit, Base):
    __tablename__ = "canonical_value_set"
    value_set_uuid = _pk()
    value_set_id = _business_id("CVS")
    value_set_code = mapped_column(String(100), nullable=False)
    value_set_name = mapped_column(String(255), nullable=False)
    domain = mapped_column(String(80), nullable=False)
    version = mapped_column(String(40), nullable=False)
    status = _status()
    __table_args__ = _args(
        "canonical_value_set",
        ACTIVE_RETIRED,
        _upper("value_set_code"),
        UniqueConstraint("value_set_code", "version", name="uq_canonical_value_set_code_version"),
    )


class CanonicalValueItem(_Audit, Base):
    __tablename__ = "canonical_value_item"
    value_item_uuid = _pk()
    value_item_id = _business_id("CVI")
    value_set_uuid = _fk("canonical_value_set.value_set_uuid", nullable=False)
    value_code = mapped_column(String(100), nullable=False)
    display_label = mapped_column(String(255), nullable=False)
    description = mapped_column(Text)
    display_order = mapped_column(Integer)
    effective_from = mapped_column(Date)
    effective_to = mapped_column(Date)
    status = _status()
    __table_args__ = _args(
        "canonical_value_item",
        ACTIVE_RETIRED,
        _upper("value_code"),
        UniqueConstraint("value_set_uuid", "value_code", name="uq_canonical_value_item_code"),
    )


class SourceValueSet(_Audit, Base):
    __tablename__ = "source_value_set"
    source_value_set_uuid = _pk()
    source_value_set_id = _business_id("SVS")
    application_uuid = _fk("external_application.application_uuid", nullable=False)
    source_object_uuid = _fk("source_object_definition.source_object_uuid", nullable=False)
    source_field_uuid = _fk("source_field_definition.source_field_uuid", nullable=False)
    schema_version = mapped_column(String(80))
    status = _status()
    __table_args__ = _args("source_value_set", ACTIVE_RETIRED)


class SourceValueItem(_Audit, Base):
    __tablename__ = "source_value_item"
    source_value_item_uuid = _pk()
    source_value_item_id = _business_id("SVI")
    source_value_set_uuid = _fk("source_value_set.source_value_set_uuid", nullable=False)
    source_value = mapped_column(String(255), nullable=False)
    source_label = mapped_column(String(255))
    description = mapped_column(Text)
    status = _status()
    __table_args__ = _args(
        "source_value_item",
        ACTIVE_RETIRED,
        UniqueConstraint("source_value_set_uuid", "source_value", name="uq_source_value_item_value"),
    )


class ValueMappingDefinition(_Audit, Base):
    __tablename__ = "value_mapping_definition"
    value_mapping_uuid = _pk()
    value_mapping_id = _business_id("VMAP")
    application_uuid = _fk("external_application.application_uuid", nullable=False)
    source_value_item_uuid = _fk("source_value_item.source_value_item_uuid", nullable=False)
    canonical_value_item_uuid = _fk("canonical_value_item.value_item_uuid", nullable=False)
    mapping_version = mapped_column(String(40), nullable=False)
    customer_override_allowed = _flag()
    status = _status()
    __table_args__ = _args(
        "value_mapping_definition",
        ACTIVE_RETIRED,
        UniqueConstraint("source_value_item_uuid", "mapping_version", name="uq_value_mapping_definition_source"),
    )


# --- 8. Integration and connector masters ------------------------------------------------


class AuthenticationTypeDefinition(_Audit, Base):
    """Supported authentication patterns. Stores secret *schemas*, never credentials."""

    __tablename__ = "authentication_type_definition"
    authentication_type_uuid = _pk()
    authentication_type_id = _business_id("AUTH")
    auth_code = mapped_column(String(100), nullable=False, unique=True)
    display_name = mapped_column(String(255), nullable=False)
    description = mapped_column(Text)
    secret_fields_schema = mapped_column(JSONB)
    status = _status()
    __table_args__ = _args("authentication_type_definition", ACTIVE_RETIRED, _upper("auth_code"))


class PaginationTypeDefinition(_Audit, Base):
    __tablename__ = "pagination_type_definition"
    pagination_type_uuid = _pk()
    pagination_type_id = _business_id("PAGE")
    pagination_code = mapped_column(String(100), nullable=False, unique=True)
    display_name = mapped_column(String(255), nullable=False)
    description = mapped_column(Text)
    status = _status()
    __table_args__ = _args("pagination_type_definition", ACTIVE_RETIRED, _upper("pagination_code"))


class SyncModeDefinition(_Audit, Base):
    __tablename__ = "sync_mode_definition"
    sync_mode_uuid = _pk()
    sync_mode_id = _business_id("SYNC")
    sync_code = mapped_column(String(100), nullable=False, unique=True)
    display_name = mapped_column(String(255), nullable=False)
    description = mapped_column(Text)
    status = _status()
    __table_args__ = _args("sync_mode_definition", ACTIVE_RETIRED, _upper("sync_code"))


class ConnectorDefinition(_Audit, Base):
    __tablename__ = "connector_definition"
    connector_uuid = _pk()
    connector_id = _business_id("CONN")
    application_uuid = _fk("external_application.application_uuid", nullable=False)
    connector_code = mapped_column(String(100), nullable=False, unique=True)
    connector_name = mapped_column(String(255), nullable=False)
    connector_type = mapped_column(String(30), nullable=False)
    default_authentication_type_uuid = _fk("authentication_type_definition.authentication_type_uuid")
    supports_schema_discovery = _flag()
    supports_incremental_sync = _flag()
    supports_webhook = _flag()
    status = _status()
    __table_args__ = _args(
        "connector_definition",
        ACTIVE_DEPRECATED_RETIRED,
        _upper("connector_code"),
        CheckConstraint(
            _in("connector_type", ("REST", "FILE", "WEBHOOK", "DB_GATEWAY")), name="connector_type_allowed"
        ),
    )


class ConnectorVersionDefinition(_Audit, Base):
    __tablename__ = "connector_version_definition"
    connector_version_uuid = _pk()
    connector_version_id = _business_id("CONV")
    connector_uuid = _fk("connector_definition.connector_uuid", nullable=False)
    version_code = mapped_column(String(40), nullable=False)
    api_version = mapped_column(String(80))
    schema_version = mapped_column(String(80))
    authentication_type_uuid = _fk("authentication_type_definition.authentication_type_uuid")
    pagination_type_uuid = _fk("pagination_type_definition.pagination_type_uuid")
    default_sync_mode_uuid = _fk("sync_mode_definition.sync_mode_uuid")
    released_at = mapped_column(DateTime(timezone=True))
    deprecated_at = mapped_column(DateTime(timezone=True))
    status = _status()
    __table_args__ = _args(
        "connector_version_definition",
        ACTIVE_DEPRECATED_RETIRED,
        UniqueConstraint("connector_uuid", "version_code", name="uq_connector_version_definition_code"),
    )


# --- 9. Shared reference, security and regulatory masters ---------------------------


class DataClassification(_Audit, Base):
    __tablename__ = "data_classification"
    classification_uuid = _pk()
    classification_id = _business_id("DCL")
    classification_code = mapped_column(String(100), nullable=False, unique=True)
    classification_name = mapped_column(String(255), nullable=False)
    sensitivity_level = mapped_column(Integer, nullable=False)
    masking_required = _flag()
    encryption_required = _flag()
    export_restricted = _flag()
    ai_usage_restricted = _flag()
    status = _status()
    __table_args__ = _args("data_classification", ACTIVE_RETIRED, _upper("classification_code"))


class CountryReference(_Audit, Base):
    __tablename__ = "country_reference"
    country_uuid = _pk()
    country_id = _business_id("CTR")
    iso_alpha2 = mapped_column(String(2), nullable=False, unique=True)
    iso_alpha3 = mapped_column(String(3), nullable=False, unique=True)
    country_name = mapped_column(String(255), nullable=False)
    region_group = mapped_column(String(80))
    status = _status()
    __table_args__ = _args(
        "country_reference",
        ACTIVE_RETIRED,
        CheckConstraint("iso_alpha2 ~ '^[A-Z]{2}$'", name="iso_alpha2_format"),
        CheckConstraint("iso_alpha3 ~ '^[A-Z]{3}$'", name="iso_alpha3_format"),
    )


class RegionReference(_Audit, Base):
    __tablename__ = "region_reference"
    region_uuid = _pk()
    region_id = _business_id("REG")
    country_uuid = _fk("country_reference.country_uuid", nullable=False)
    region_code = mapped_column(String(20), nullable=False)
    region_name = mapped_column(String(255), nullable=False)
    region_type = mapped_column(String(60))
    status = _status()
    __table_args__ = _args(
        "region_reference",
        ACTIVE_RETIRED,
        _upper("region_code"),
        UniqueConstraint("country_uuid", "region_code", name="uq_region_reference_code"),
    )


class TimezoneReference(_Audit, Base):
    __tablename__ = "timezone_reference"
    timezone_uuid = _pk()
    timezone_id = _business_id("TZ")
    iana_name = mapped_column(String(80), nullable=False, unique=True)
    display_name = mapped_column(String(255), nullable=False)
    status = _status()
    __table_args__ = _args("timezone_reference", ACTIVE_RETIRED)


class UnitOfMeasure(_Audit, Base):
    """Units are case-sensitive (mg vs Mg), so uom_code is not upper-cased."""

    __tablename__ = "unit_of_measure"
    uom_uuid = _pk()
    uom_id = _business_id("UOM")
    uom_code = mapped_column(String(20), nullable=False, unique=True)
    uom_name = mapped_column(String(120), nullable=False)
    dimension = mapped_column(String(60))
    canonical_unit_uuid = _fk("unit_of_measure.uom_uuid")
    conversion_factor = mapped_column(Numeric(30, 12))
    status = _status()
    __table_args__ = _args("unit_of_measure", ACTIVE_RETIRED)


class JurisdictionReference(_Audit, Base):
    __tablename__ = "jurisdiction_reference"
    jurisdiction_uuid = _pk()
    jurisdiction_id = _business_id("JUR")
    jurisdiction_code = mapped_column(String(40), nullable=False, unique=True)
    jurisdiction_name = mapped_column(String(255), nullable=False)
    jurisdiction_type = mapped_column(String(20), nullable=False)
    country_uuid = _fk("country_reference.country_uuid")
    status = _status()
    __table_args__ = _args(
        "jurisdiction_reference",
        ACTIVE_RETIRED,
        _upper("jurisdiction_code"),
        CheckConstraint(_in("jurisdiction_type", ("COUNTRY", "REGION")), name="jurisdiction_type_allowed"),
    )


class RegulatoryAuthority(_Audit, Base):
    __tablename__ = "regulatory_authority"
    authority_uuid = _pk()
    authority_id = _business_id("RA")
    authority_code = mapped_column(String(60), nullable=False, unique=True)
    authority_name = mapped_column(String(255), nullable=False)
    jurisdiction_uuid = _fk("jurisdiction_reference.jurisdiction_uuid", nullable=False)
    country_uuid = _fk("country_reference.country_uuid")
    authority_type = mapped_column(String(80))
    website_reference = mapped_column(String(500))
    status = _status()
    __table_args__ = _args("regulatory_authority", ACTIVE_RETIRED, _upper("authority_code"))


class ChangeReasonCode(_Audit, Base):
    __tablename__ = "change_reason_code"
    change_reason_uuid = _pk()
    change_reason_id = _business_id("CRSN")
    reason_code = mapped_column(String(100), nullable=False, unique=True)
    reason_label = mapped_column(String(255), nullable=False)
    description = mapped_column(Text)
    requires_comment = _flag()
    requires_approval = _flag()
    status = _status()
    __table_args__ = _args("change_reason_code", ACTIVE_RETIRED, _upper("reason_code"))


class RecordStatusDefinition(_Audit, Base):
    __tablename__ = "record_status_definition"
    status_uuid = _pk()
    status_id = _business_id("STAT")
    domain = mapped_column(String(80), nullable=False)
    status_code = mapped_column(String(60), nullable=False)
    status_label = mapped_column(String(120), nullable=False)
    terminal = _flag()
    display_order = mapped_column(Integer)
    status = _status()
    __table_args__ = _args(
        "record_status_definition",
        ACTIVE_RETIRED,
        _upper("domain"),
        _upper("status_code"),
        UniqueConstraint("domain", "status_code", name="uq_record_status_definition_code"),
    )


# --- 10. AI governance masters -------------------------------------------------------------


class AIOutputTypeDefinition(_Audit, Base):
    __tablename__ = "ai_output_type_definition"
    ai_output_type_uuid = _pk()
    ai_output_type_id = _business_id("AIOT")
    output_code = mapped_column(String(100), nullable=False, unique=True)
    output_name = mapped_column(String(255), nullable=False)
    description = mapped_column(Text)
    human_review_required = _flag(True)
    regulated_decision_prohibited = _flag(True)
    status = _status()
    __table_args__ = _args("ai_output_type_definition", ACTIVE_RETIRED, _upper("output_code"))


class AIGuardrailDefinition(_Audit, Base):
    __tablename__ = "ai_guardrail_definition"
    guardrail_uuid = _pk()
    guardrail_id = _business_id("AIG")
    guardrail_code = mapped_column(String(100), nullable=False, unique=True)
    guardrail_name = mapped_column(String(255), nullable=False)
    description = mapped_column(Text)
    severity = mapped_column(String(20), nullable=False)
    blocking = _flag()
    status = _status()
    __table_args__ = _args(
        "ai_guardrail_definition",
        ACTIVE_RETIRED,
        _upper("guardrail_code"),
        CheckConstraint(_in("severity", ("WARNING", "BLOCKING")), name="severity_allowed"),
    )


MASTER_TABLES_WITH_BUSINESS_IDS = {
    # table -> (business id column, prefix)
    "industry_domain": ("industry_id", "IND"),
    "application_vendor": ("vendor_id", "VEND"),
    "application_category": ("category_id", "APPCAT"),
    "external_application": ("application_id", "APP"),
    "external_application_industry": ("relation_id", "APPIND"),
    "application_version_definition": ("application_version_id", "APPVER"),
    "source_object_definition": ("source_object_id", "SOBJ"),
    "field_group_definition": ("field_group_id", "FGRP"),
    "source_field_definition": ("source_field_id", "SFLD"),
    "canonical_entity_definition": ("canonical_entity_id", "CENT"),
    "canonical_field_definition": ("canonical_field_id", "CFLD"),
    "mapping_override_policy": ("override_policy_id", "OVRP"),
    "source_authority_type": ("source_authority_id", "SAUT"),
    "transformation_definition": ("transformation_id", "TRN"),
    "validation_rule_definition": ("validation_rule_id", "VAL"),
    "reference_resolution_rule": ("reference_rule_id", "REFR"),
    "data_quality_rule": ("data_quality_rule_id", "DQR"),
    "master_mapping_family": ("mapping_family_id", "MMF"),
    "master_mapping_version": ("mapping_version_id", "MMV"),
    "master_mapping_item": ("mapping_item_id", "MMI"),
    "canonical_value_set": ("value_set_id", "CVS"),
    "canonical_value_item": ("value_item_id", "CVI"),
    "source_value_set": ("source_value_set_id", "SVS"),
    "source_value_item": ("source_value_item_id", "SVI"),
    "value_mapping_definition": ("value_mapping_id", "VMAP"),
    "authentication_type_definition": ("authentication_type_id", "AUTH"),
    "pagination_type_definition": ("pagination_type_id", "PAGE"),
    "sync_mode_definition": ("sync_mode_id", "SYNC"),
    "connector_definition": ("connector_id", "CONN"),
    "connector_version_definition": ("connector_version_id", "CONV"),
    "data_classification": ("classification_id", "DCL"),
    "country_reference": ("country_id", "CTR"),
    "region_reference": ("region_id", "REG"),
    "timezone_reference": ("timezone_id", "TZ"),
    "unit_of_measure": ("uom_id", "UOM"),
    "jurisdiction_reference": ("jurisdiction_id", "JUR"),
    "regulatory_authority": ("authority_id", "RA"),
    "change_reason_code": ("change_reason_id", "CRSN"),
    "record_status_definition": ("status_id", "STAT"),
    "ai_output_type_definition": ("ai_output_type_id", "AIOT"),
    "ai_guardrail_definition": ("guardrail_id", "AIG"),
}
