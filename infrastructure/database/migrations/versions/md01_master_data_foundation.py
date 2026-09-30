"""Master Data foundation: md_master schema, business-ID allocator and all Master Data tables.

Implements MDARIX Master Data Foundation and Maintenance Standard v1.0:
- one registry of business-ID prefixes, each backed by its own PostgreSQL
  sequence; md_master.next_business_id(prefix) is the only allocator (atomic,
  never MAX()+1, never recycled, never truncated);
- every Master Data table (sections 3-10) with UUID keys, business IDs,
  controlled status values and uniqueness rules;
- triggers: business IDs are immutable; records can be hard-deleted only while
  DRAFT (referenced records are additionally protected by foreign keys);
  RELEASED master mapping versions and their items cannot be changed.

Table DDL below was generated from backend/app/db/models/master.py with
Alembic autogenerate and reviewed.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "md01masterdata"
down_revision = "z45audithashchain"
branch_labels = None
depends_on = None

# prefix, entity, minimum digits, owning schema.
PREFIXES = [
    # Master Data (Master Data Foundation section 1.3 plus prefixes used by its tables)
    ("CUST", "Customer", 5, "md_control"),
    ("TEN", "Tenant", 5, "md_control"),
    ("VEND", "Application Vendor", 5, "md_master"),
    ("IND", "Industry Domain", 5, "md_master"),
    ("APPCAT", "Application Category", 5, "md_master"),
    ("APP", "External Application", 5, "md_master"),
    ("APPIND", "External Application Industry", 5, "md_master"),
    ("APPVER", "Application Version", 5, "md_master"),
    ("SOBJ", "Source Object", 5, "md_master"),
    ("FGRP", "Field Group", 5, "md_master"),
    ("SFLD", "Source Field", 5, "md_master"),
    ("CENT", "Canonical Entity", 5, "md_master"),
    ("CFLD", "Canonical Field", 5, "md_master"),
    ("OVRP", "Mapping Override Policy", 5, "md_master"),
    ("SAUT", "Source Authority Type", 5, "md_master"),
    ("TRN", "Transformation", 5, "md_master"),
    ("VAL", "Validation Rule", 5, "md_master"),
    ("REFR", "Reference Resolution Rule", 5, "md_master"),
    ("DQR", "Data Quality Rule", 5, "md_master"),
    ("CVS", "Canonical Value Set", 5, "md_master"),
    ("CVI", "Canonical Value Item", 5, "md_master"),
    ("SVS", "Source Value Set", 5, "md_master"),
    ("SVI", "Source Value Item", 5, "md_master"),
    ("VMAP", "Value Mapping", 5, "md_master"),
    ("MMF", "Master Mapping Family", 5, "md_master"),
    ("MMV", "Master Mapping Version", 5, "md_master"),
    ("MMI", "Master Mapping Item", 5, "md_master"),
    ("AUTH", "Authentication Type", 5, "md_master"),
    ("PAGE", "Pagination Type", 5, "md_master"),
    ("SYNC", "Sync Mode", 5, "md_master"),
    ("CONN", "Connector", 5, "md_master"),
    ("CONV", "Connector Version", 5, "md_master"),
    ("DCL", "Data Classification", 5, "md_master"),
    ("CTR", "Country", 5, "md_master"),
    ("REG", "Region", 5, "md_master"),
    ("TZ", "Timezone", 5, "md_master"),
    ("UOM", "Unit of Measure", 5, "md_master"),
    ("JUR", "Jurisdiction", 5, "md_master"),
    ("RA", "Regulatory Authority", 5, "md_master"),
    ("CRSN", "Change Reason", 5, "md_master"),
    ("STAT", "Record Status", 5, "md_master"),
    ("AIOT", "AI Output Type", 5, "md_master"),
    ("AIG", "AI Guardrail", 5, "md_master"),
    # Transactional business data (Transactional Data Architecture section 2 and table definitions)
    ("PROD", "Product", 5, "md_transaction"),
    ("PV", "Product Version", 5, "md_transaction"),
    ("COMP", "Component", 5, "md_transaction"),
    ("PCOMP", "Product Component", 5, "md_transaction"),
    ("SUP", "Supplier", 5, "md_transaction"),
    ("SITE", "Manufacturing Site", 5, "md_transaction"),
    ("LOT", "Lot / Batch", 5, "md_transaction"),
    ("CHG", "Product Change", 5, "md_transaction"),
    ("CMP", "Complaint", 5, "md_transaction"),
    ("SIG", "Signal", 5, "md_transaction"),
    ("INV", "Investigation", 5, "md_transaction"),
    ("EVD", "Evidence", 5, "md_transaction"),
    ("RSK", "Risk", 5, "md_transaction"),
    ("HAZ", "Hazard", 5, "md_transaction"),
    ("FM", "Failure Mode", 5, "md_transaction"),
    ("CTL", "Control", 5, "md_transaction"),
    ("RAST", "Risk Assessment", 5, "md_transaction"),
    ("CAPA", "CAPA", 5, "md_transaction"),
    ("VIG", "Vigilance Assessment", 5, "md_transaction"),
    ("FA", "Field Action", 5, "md_transaction"),
    ("REC", "Recall", 5, "md_transaction"),
    # Intelligence
    ("OBS", "Observation", 5, "md_intelligence"),
    ("HYP", "Hypothesis", 5, "md_intelligence"),
    ("UNK", "Unknown", 5, "md_intelligence"),
    ("CONTRA", "Contradiction", 5, "md_intelligence"),
    ("CHL", "Challenge", 5, "md_intelligence"),
    ("FC", "Failure Chain", 5, "md_intelligence"),
    ("AIEX", "AI Execution", 5, "md_intelligence"),
    ("AIO", "AI Output", 5, "md_intelligence"),
    ("AIREV", "AI Output Review", 5, "md_intelligence"),
    # Workflow
    ("TSK", "Task", 5, "md_workflow"),
    ("EVR", "Evidence Request", 5, "md_workflow"),
    ("REVREQ", "Review Request", 5, "md_workflow"),
    ("RCM", "Review Comment", 5, "md_workflow"),
    ("DBR", "Decision Brief", 5, "md_workflow"),
    ("DEC", "Decision", 5, "md_workflow"),
    ("SIGCER", "Signature Ceremony", 5, "md_workflow"),
    ("CTXSNAP", "Context Snapshot", 5, "md_workflow"),
    # Integration and provenance
    ("SRC", "Source Record", 8, "md_integration"),
    ("SRCP", "Source Payload", 8, "md_integration"),
    ("ING", "Ingestion Run", 5, "md_integration"),
    ("MAPEX", "Mapping Execution", 5, "md_integration"),
    ("LIN", "Mapping Field Lineage", 8, "md_integration"),
    ("SDR", "Schema Drift Event", 5, "md_integration"),
    ("MCF", "Mapping Conflict", 5, "md_integration"),
    ("QRN", "Quarantine Record", 5, "md_integration"),
    # Audit
    ("AUD", "Audit Event", 8, "md_audit"),
    ("ACCEVT", "Access Event", 8, "md_audit"),
    ("AUTHEVT", "Authentication Event", 8, "md_audit"),
    ("EXPEVT", "Data Export Event", 8, "md_audit"),
    ("CFGEVT", "Configuration Change Event", 8, "md_audit"),
    ("AIAUD", "AI Audit Event", 8, "md_audit"),
    # Operations (CONVO resolves the specs' CONV collision with Connector Version)
    ("WSC", "Workspace Context", 5, "md_operations"),
    ("CONVO", "AI Conversation", 5, "md_operations"),
    ("MSG", "AI Conversation Message", 5, "md_operations"),
    ("OMSG", "Outbound Message", 5, "md_operations"),
    ("IMSG", "Inbound Message", 5, "md_operations"),
    ("JOB", "Job Run", 5, "md_operations"),
    ("INC", "System Incident", 5, "md_operations"),
    ("USEVT", "Usage Event", 8, "md_operations"),
    ("METER", "Usage Meter", 5, "md_operations"),
    ("RPT", "Report Execution", 5, "md_operations"),
]

NEXT_BUSINESS_ID = r"""
create or replace function md_master.next_business_id(p_prefix text) returns text
language plpgsql volatile as $fn$
declare
    v_sequence text;
    v_width integer;
    v_number text;
begin
    select sequence_name, id_width into v_sequence, v_width
    from md_master.business_id_prefix where prefix = p_prefix;
    if v_sequence is null then
        raise exception 'Unknown business identifier prefix %', p_prefix using errcode = '22023';
    end if;
    v_number := nextval(format('md_master.%I', v_sequence))::text;
    -- Pad to the minimum width but never truncate once the number outgrows it.
    if length(v_number) < v_width then
        v_number := lpad(v_number, v_width, '0');
    end if;
    return p_prefix || v_number;
end
$fn$;
"""

GUARD_FUNCTIONS = r"""
create or replace function md_master.reject_business_id_change() returns trigger
language plpgsql as $fn$
begin
    if (to_jsonb(new) ->> tg_argv[0]) is distinct from (to_jsonb(old) ->> tg_argv[0]) then
        raise exception 'Business identifier %.% is immutable', tg_table_name, tg_argv[0] using errcode = '55000';
    end if;
    return new;
end
$fn$;

create or replace function md_master.reject_non_draft_delete() returns trigger
language plpgsql as $fn$
begin
    if coalesce(to_jsonb(old) ->> 'status', '') <> 'DRAFT' then
        raise exception 'Master Data %.% is retired, not deleted (only never-used DRAFT records may be deleted)',
            tg_table_schema, tg_table_name using errcode = '55000';
    end if;
    return old;
end
$fn$;

create or replace function md_master.protect_prefix_registry() returns trigger
language plpgsql as $fn$
begin
    if tg_op = 'DELETE' then
        raise exception 'Business identifier prefixes are never removed' using errcode = '55000';
    end if;
    if new.prefix <> old.prefix or new.sequence_name <> old.sequence_name then
        raise exception 'Business identifier prefix definitions are immutable' using errcode = '55000';
    end if;
    return new;
end
$fn$;

create or replace function md_master.protect_released_mapping_version() returns trigger
language plpgsql as $fn$
declare
    v_mutable text[] := array['status', 'effective_to', 'updated_at', 'updated_by'];
begin
    if old.status in ('RELEASED', 'SUPERSEDED', 'RETIRED') then
        if (to_jsonb(new) - v_mutable) is distinct from (to_jsonb(old) - v_mutable) then
            raise exception 'Released master mapping version % is immutable; create a new version',
                old.mapping_version_id using errcode = '55000';
        end if;
        if not ((old.status = new.status)
                or (old.status = 'RELEASED' and new.status in ('SUPERSEDED', 'RETIRED'))
                or (old.status = 'SUPERSEDED' and new.status = 'RETIRED')) then
            raise exception 'Invalid status transition % -> % for a released mapping version', old.status, new.status
                using errcode = '55000';
        end if;
    end if;
    return new;
end
$fn$;

create or replace function md_master.protect_released_mapping_items() returns trigger
language plpgsql as $fn$
declare
    v_version uuid;
    v_status text;
begin
    if tg_op = 'DELETE' then
        v_version := old.mapping_version_uuid;
    else
        v_version := new.mapping_version_uuid;
    end if;
    select status into v_status from md_master.master_mapping_version where mapping_version_uuid = v_version;
    if v_status not in ('DRAFT', 'VALIDATION') then
        raise exception 'Mapping items of a % version cannot change; create a new version', v_status
            using errcode = '55000';
    end if;
    if tg_op = 'UPDATE' and new.mapping_version_uuid <> old.mapping_version_uuid then
        raise exception 'Mapping items cannot move between versions' using errcode = '55000';
    end if;
    if tg_op = 'DELETE' then
        return old;
    end if;
    return new;
end
$fn$;
"""

BUSINESS_ID_COLUMNS = {
    "industry_domain": "industry_id",
    "application_vendor": "vendor_id",
    "application_category": "category_id",
    "external_application": "application_id",
    "external_application_industry": "relation_id",
    "application_version_definition": "application_version_id",
    "source_object_definition": "source_object_id",
    "field_group_definition": "field_group_id",
    "source_field_definition": "source_field_id",
    "canonical_entity_definition": "canonical_entity_id",
    "canonical_field_definition": "canonical_field_id",
    "mapping_override_policy": "override_policy_id",
    "source_authority_type": "source_authority_id",
    "transformation_definition": "transformation_id",
    "validation_rule_definition": "validation_rule_id",
    "reference_resolution_rule": "reference_rule_id",
    "data_quality_rule": "data_quality_rule_id",
    "master_mapping_family": "mapping_family_id",
    "master_mapping_version": "mapping_version_id",
    "master_mapping_item": "mapping_item_id",
    "canonical_value_set": "value_set_id",
    "canonical_value_item": "value_item_id",
    "source_value_set": "source_value_set_id",
    "source_value_item": "source_value_item_id",
    "value_mapping_definition": "value_mapping_id",
    "authentication_type_definition": "authentication_type_id",
    "pagination_type_definition": "pagination_type_id",
    "sync_mode_definition": "sync_mode_id",
    "connector_definition": "connector_id",
    "connector_version_definition": "connector_version_id",
    "data_classification": "classification_id",
    "country_reference": "country_id",
    "region_reference": "region_id",
    "timezone_reference": "timezone_id",
    "unit_of_measure": "uom_id",
    "jurisdiction_reference": "jurisdiction_id",
    "regulatory_authority": "authority_id",
    "change_reason_code": "change_reason_id",
    "record_status_definition": "status_id",
    "ai_output_type_definition": "ai_output_type_id",
    "ai_guardrail_definition": "guardrail_id",
}


def upgrade():
    op.execute("create schema if not exists md_master")
    op.execute(NEXT_BUSINESS_ID)
    op.create_table(
        "ai_guardrail_definition",
        sa.Column("guardrail_uuid", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "guardrail_id",
            sa.String(length=24),
            server_default=sa.text("md_master.next_business_id('AIG')"),
            nullable=False,
        ),
        sa.Column("guardrail_code", sa.String(length=100), nullable=False),
        sa.Column("guardrail_name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("severity", sa.String(length=20), nullable=False),
        sa.Column("blocking", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("status", sa.String(length=30), server_default="ACTIVE", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.Column("updated_by", sa.UUID(), nullable=True),
        sa.CheckConstraint(
            "severity in ('WARNING', 'BLOCKING')", name=op.f("ck_ai_guardrail_definition_severity_allowed")
        ),
        sa.CheckConstraint("status in ('ACTIVE', 'RETIRED')", name=op.f("ck_ai_guardrail_definition_status_allowed")),
        sa.CheckConstraint(
            "guardrail_code = upper(guardrail_code)", name=op.f("ck_ai_guardrail_definition_guardrail_code_upper")
        ),
        sa.PrimaryKeyConstraint("guardrail_uuid", name=op.f("pk_ai_guardrail_definition")),
        sa.UniqueConstraint("guardrail_code", name=op.f("uq_ai_guardrail_definition_guardrail_code")),
        sa.UniqueConstraint("guardrail_id", name=op.f("uq_ai_guardrail_definition_guardrail_id")),
        schema="md_master",
    )
    op.create_table(
        "ai_output_type_definition",
        sa.Column("ai_output_type_uuid", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "ai_output_type_id",
            sa.String(length=24),
            server_default=sa.text("md_master.next_business_id('AIOT')"),
            nullable=False,
        ),
        sa.Column("output_code", sa.String(length=100), nullable=False),
        sa.Column("output_name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("human_review_required", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("regulated_decision_prohibited", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("status", sa.String(length=30), server_default="ACTIVE", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.Column("updated_by", sa.UUID(), nullable=True),
        sa.CheckConstraint("status in ('ACTIVE', 'RETIRED')", name=op.f("ck_ai_output_type_definition_status_allowed")),
        sa.CheckConstraint(
            "output_code = upper(output_code)", name=op.f("ck_ai_output_type_definition_output_code_upper")
        ),
        sa.PrimaryKeyConstraint("ai_output_type_uuid", name=op.f("pk_ai_output_type_definition")),
        sa.UniqueConstraint("ai_output_type_id", name=op.f("uq_ai_output_type_definition_ai_output_type_id")),
        sa.UniqueConstraint("output_code", name=op.f("uq_ai_output_type_definition_output_code")),
        schema="md_master",
    )
    op.create_table(
        "application_category",
        sa.Column("category_uuid", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "category_id",
            sa.String(length=24),
            server_default=sa.text("md_master.next_business_id('APPCAT')"),
            nullable=False,
        ),
        sa.Column("category_code", sa.String(length=100), nullable=False),
        sa.Column("category_name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("display_order", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=30), server_default="ACTIVE", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.Column("updated_by", sa.UUID(), nullable=True),
        sa.CheckConstraint("status in ('ACTIVE', 'RETIRED')", name=op.f("ck_application_category_status_allowed")),
        sa.CheckConstraint(
            "category_code = upper(category_code)", name=op.f("ck_application_category_category_code_upper")
        ),
        sa.PrimaryKeyConstraint("category_uuid", name=op.f("pk_application_category")),
        sa.UniqueConstraint("category_code", name=op.f("uq_application_category_category_code")),
        sa.UniqueConstraint("category_id", name=op.f("uq_application_category_category_id")),
        schema="md_master",
    )
    op.create_table(
        "authentication_type_definition",
        sa.Column("authentication_type_uuid", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "authentication_type_id",
            sa.String(length=24),
            server_default=sa.text("md_master.next_business_id('AUTH')"),
            nullable=False,
        ),
        sa.Column("auth_code", sa.String(length=100), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("secret_fields_schema", postgresql.JSONB(), nullable=True),
        sa.Column("status", sa.String(length=30), server_default="ACTIVE", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.Column("updated_by", sa.UUID(), nullable=True),
        sa.CheckConstraint(
            "status in ('ACTIVE', 'RETIRED')", name=op.f("ck_authentication_type_definition_status_allowed")
        ),
        sa.CheckConstraint(
            "auth_code = upper(auth_code)", name=op.f("ck_authentication_type_definition_auth_code_upper")
        ),
        sa.PrimaryKeyConstraint("authentication_type_uuid", name=op.f("pk_authentication_type_definition")),
        sa.UniqueConstraint("auth_code", name=op.f("uq_authentication_type_definition_auth_code")),
        sa.UniqueConstraint(
            "authentication_type_id", name=op.f("uq_authentication_type_definition_authentication_type_id")
        ),
        schema="md_master",
    )
    op.create_table(
        "business_id_prefix",
        sa.Column("prefix", sa.String(length=12), nullable=False),
        sa.Column("entity_name", sa.String(length=120), nullable=False),
        sa.Column("sequence_name", sa.String(length=80), nullable=False),
        sa.Column("id_width", sa.Integer(), server_default="5", nullable=False),
        sa.Column("owning_schema", sa.String(length=40), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.CheckConstraint("prefix ~ '^[A-Z]{1,12}$'", name=op.f("ck_business_id_prefix_prefix_format")),
        sa.CheckConstraint("id_width between 3 and 12", name=op.f("ck_business_id_prefix_id_width_range")),
        sa.PrimaryKeyConstraint("prefix", name=op.f("pk_business_id_prefix")),
        sa.UniqueConstraint("sequence_name", name=op.f("uq_business_id_prefix_sequence_name")),
        schema="md_master",
    )
    op.create_table(
        "canonical_entity_definition",
        sa.Column("canonical_entity_uuid", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "canonical_entity_id",
            sa.String(length=24),
            server_default=sa.text("md_master.next_business_id('CENT')"),
            nullable=False,
        ),
        sa.Column("entity_code", sa.String(length=100), nullable=False),
        sa.Column("entity_name", sa.String(length=255), nullable=False),
        sa.Column("domain", sa.String(length=80), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("version", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=30), server_default="ACTIVE", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.Column("updated_by", sa.UUID(), nullable=True),
        sa.CheckConstraint(
            "status in ('ACTIVE', 'DEPRECATED', 'RETIRED')", name=op.f("ck_canonical_entity_definition_status_allowed")
        ),
        sa.CheckConstraint(
            "entity_code = upper(entity_code)", name=op.f("ck_canonical_entity_definition_entity_code_upper")
        ),
        sa.PrimaryKeyConstraint("canonical_entity_uuid", name=op.f("pk_canonical_entity_definition")),
        sa.UniqueConstraint("canonical_entity_id", name=op.f("uq_canonical_entity_definition_canonical_entity_id")),
        sa.UniqueConstraint("entity_code", name=op.f("uq_canonical_entity_definition_entity_code")),
        schema="md_master",
    )
    op.create_table(
        "canonical_value_set",
        sa.Column("value_set_uuid", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "value_set_id",
            sa.String(length=24),
            server_default=sa.text("md_master.next_business_id('CVS')"),
            nullable=False,
        ),
        sa.Column("value_set_code", sa.String(length=100), nullable=False),
        sa.Column("value_set_name", sa.String(length=255), nullable=False),
        sa.Column("domain", sa.String(length=80), nullable=False),
        sa.Column("version", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=30), server_default="ACTIVE", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.Column("updated_by", sa.UUID(), nullable=True),
        sa.CheckConstraint("status in ('ACTIVE', 'RETIRED')", name=op.f("ck_canonical_value_set_status_allowed")),
        sa.CheckConstraint(
            "value_set_code = upper(value_set_code)", name=op.f("ck_canonical_value_set_value_set_code_upper")
        ),
        sa.PrimaryKeyConstraint("value_set_uuid", name=op.f("pk_canonical_value_set")),
        sa.UniqueConstraint("value_set_code", "version", name="uq_canonical_value_set_code_version"),
        sa.UniqueConstraint("value_set_id", name=op.f("uq_canonical_value_set_value_set_id")),
        schema="md_master",
    )
    op.create_table(
        "change_reason_code",
        sa.Column("change_reason_uuid", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "change_reason_id",
            sa.String(length=24),
            server_default=sa.text("md_master.next_business_id('CRSN')"),
            nullable=False,
        ),
        sa.Column("reason_code", sa.String(length=100), nullable=False),
        sa.Column("reason_label", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("requires_comment", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("requires_approval", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("status", sa.String(length=30), server_default="ACTIVE", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.Column("updated_by", sa.UUID(), nullable=True),
        sa.CheckConstraint("status in ('ACTIVE', 'RETIRED')", name=op.f("ck_change_reason_code_status_allowed")),
        sa.CheckConstraint("reason_code = upper(reason_code)", name=op.f("ck_change_reason_code_reason_code_upper")),
        sa.PrimaryKeyConstraint("change_reason_uuid", name=op.f("pk_change_reason_code")),
        sa.UniqueConstraint("change_reason_id", name=op.f("uq_change_reason_code_change_reason_id")),
        sa.UniqueConstraint("reason_code", name=op.f("uq_change_reason_code_reason_code")),
        schema="md_master",
    )
    op.create_table(
        "country_reference",
        sa.Column("country_uuid", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "country_id",
            sa.String(length=24),
            server_default=sa.text("md_master.next_business_id('CTR')"),
            nullable=False,
        ),
        sa.Column("iso_alpha2", sa.String(length=2), nullable=False),
        sa.Column("iso_alpha3", sa.String(length=3), nullable=False),
        sa.Column("country_name", sa.String(length=255), nullable=False),
        sa.Column("region_group", sa.String(length=80), nullable=True),
        sa.Column("status", sa.String(length=30), server_default="ACTIVE", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.Column("updated_by", sa.UUID(), nullable=True),
        sa.CheckConstraint("iso_alpha2 ~ '^[A-Z]{2}$'", name=op.f("ck_country_reference_iso_alpha2_format")),
        sa.CheckConstraint("iso_alpha3 ~ '^[A-Z]{3}$'", name=op.f("ck_country_reference_iso_alpha3_format")),
        sa.CheckConstraint("status in ('ACTIVE', 'RETIRED')", name=op.f("ck_country_reference_status_allowed")),
        sa.PrimaryKeyConstraint("country_uuid", name=op.f("pk_country_reference")),
        sa.UniqueConstraint("country_id", name=op.f("uq_country_reference_country_id")),
        sa.UniqueConstraint("iso_alpha2", name=op.f("uq_country_reference_iso_alpha2")),
        sa.UniqueConstraint("iso_alpha3", name=op.f("uq_country_reference_iso_alpha3")),
        schema="md_master",
    )
    op.create_table(
        "data_classification",
        sa.Column("classification_uuid", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "classification_id",
            sa.String(length=24),
            server_default=sa.text("md_master.next_business_id('DCL')"),
            nullable=False,
        ),
        sa.Column("classification_code", sa.String(length=100), nullable=False),
        sa.Column("classification_name", sa.String(length=255), nullable=False),
        sa.Column("sensitivity_level", sa.Integer(), nullable=False),
        sa.Column("masking_required", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("encryption_required", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("export_restricted", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("ai_usage_restricted", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("status", sa.String(length=30), server_default="ACTIVE", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.Column("updated_by", sa.UUID(), nullable=True),
        sa.CheckConstraint("status in ('ACTIVE', 'RETIRED')", name=op.f("ck_data_classification_status_allowed")),
        sa.CheckConstraint(
            "classification_code = upper(classification_code)",
            name=op.f("ck_data_classification_classification_code_upper"),
        ),
        sa.PrimaryKeyConstraint("classification_uuid", name=op.f("pk_data_classification")),
        sa.UniqueConstraint("classification_code", name=op.f("uq_data_classification_classification_code")),
        sa.UniqueConstraint("classification_id", name=op.f("uq_data_classification_classification_id")),
        schema="md_master",
    )
    op.create_table(
        "field_group_definition",
        sa.Column("field_group_uuid", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "field_group_id",
            sa.String(length=24),
            server_default=sa.text("md_master.next_business_id('FGRP')"),
            nullable=False,
        ),
        sa.Column("group_code", sa.String(length=100), nullable=False),
        sa.Column("group_name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("display_order", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=30), server_default="ACTIVE", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.Column("updated_by", sa.UUID(), nullable=True),
        sa.CheckConstraint("status in ('ACTIVE', 'RETIRED')", name=op.f("ck_field_group_definition_status_allowed")),
        sa.CheckConstraint("group_code = upper(group_code)", name=op.f("ck_field_group_definition_group_code_upper")),
        sa.PrimaryKeyConstraint("field_group_uuid", name=op.f("pk_field_group_definition")),
        sa.UniqueConstraint("field_group_id", name=op.f("uq_field_group_definition_field_group_id")),
        sa.UniqueConstraint("group_code", name=op.f("uq_field_group_definition_group_code")),
        schema="md_master",
    )
    op.create_table(
        "industry_domain",
        sa.Column("industry_uuid", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "industry_id",
            sa.String(length=24),
            server_default=sa.text("md_master.next_business_id('IND')"),
            nullable=False,
        ),
        sa.Column("industry_code", sa.String(length=100), nullable=False),
        sa.Column("industry_name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=30), server_default="ACTIVE", nullable=False),
        sa.Column("display_order", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.Column("updated_by", sa.UUID(), nullable=True),
        sa.CheckConstraint(
            "status in ('ACTIVE', 'DEPRECATED', 'RETIRED')", name=op.f("ck_industry_domain_status_allowed")
        ),
        sa.CheckConstraint("industry_code = upper(industry_code)", name=op.f("ck_industry_domain_industry_code_upper")),
        sa.PrimaryKeyConstraint("industry_uuid", name=op.f("pk_industry_domain")),
        sa.UniqueConstraint("industry_code", name=op.f("uq_industry_domain_industry_code")),
        sa.UniqueConstraint("industry_id", name=op.f("uq_industry_domain_industry_id")),
        schema="md_master",
    )
    op.create_table(
        "mapping_override_policy",
        sa.Column("override_policy_uuid", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "override_policy_id",
            sa.String(length=24),
            server_default=sa.text("md_master.next_business_id('OVRP')"),
            nullable=False,
        ),
        sa.Column("policy_code", sa.String(length=100), nullable=False),
        sa.Column("policy_name", sa.String(length=255), nullable=False),
        sa.Column("can_edit_source", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("can_edit_target", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("can_edit_transform", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("can_edit_validation", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("can_edit_enum_mapping", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("requires_approval", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("status", sa.String(length=30), server_default="ACTIVE", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.Column("updated_by", sa.UUID(), nullable=True),
        sa.CheckConstraint("status in ('ACTIVE', 'RETIRED')", name=op.f("ck_mapping_override_policy_status_allowed")),
        sa.CheckConstraint(
            "policy_code = upper(policy_code)", name=op.f("ck_mapping_override_policy_policy_code_upper")
        ),
        sa.PrimaryKeyConstraint("override_policy_uuid", name=op.f("pk_mapping_override_policy")),
        sa.UniqueConstraint("override_policy_id", name=op.f("uq_mapping_override_policy_override_policy_id")),
        sa.UniqueConstraint("policy_code", name=op.f("uq_mapping_override_policy_policy_code")),
        schema="md_master",
    )
    op.create_table(
        "pagination_type_definition",
        sa.Column("pagination_type_uuid", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "pagination_type_id",
            sa.String(length=24),
            server_default=sa.text("md_master.next_business_id('PAGE')"),
            nullable=False,
        ),
        sa.Column("pagination_code", sa.String(length=100), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=30), server_default="ACTIVE", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.Column("updated_by", sa.UUID(), nullable=True),
        sa.CheckConstraint(
            "status in ('ACTIVE', 'RETIRED')", name=op.f("ck_pagination_type_definition_status_allowed")
        ),
        sa.CheckConstraint(
            "pagination_code = upper(pagination_code)", name=op.f("ck_pagination_type_definition_pagination_code_upper")
        ),
        sa.PrimaryKeyConstraint("pagination_type_uuid", name=op.f("pk_pagination_type_definition")),
        sa.UniqueConstraint("pagination_code", name=op.f("uq_pagination_type_definition_pagination_code")),
        sa.UniqueConstraint("pagination_type_id", name=op.f("uq_pagination_type_definition_pagination_type_id")),
        schema="md_master",
    )
    op.create_table(
        "record_status_definition",
        sa.Column("status_uuid", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "status_id",
            sa.String(length=24),
            server_default=sa.text("md_master.next_business_id('STAT')"),
            nullable=False,
        ),
        sa.Column("domain", sa.String(length=80), nullable=False),
        sa.Column("status_code", sa.String(length=60), nullable=False),
        sa.Column("status_label", sa.String(length=120), nullable=False),
        sa.Column("terminal", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("display_order", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=30), server_default="ACTIVE", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.Column("updated_by", sa.UUID(), nullable=True),
        sa.CheckConstraint("status in ('ACTIVE', 'RETIRED')", name=op.f("ck_record_status_definition_status_allowed")),
        sa.CheckConstraint("domain = upper(domain)", name=op.f("ck_record_status_definition_domain_upper")),
        sa.CheckConstraint(
            "status_code = upper(status_code)", name=op.f("ck_record_status_definition_status_code_upper")
        ),
        sa.PrimaryKeyConstraint("status_uuid", name=op.f("pk_record_status_definition")),
        sa.UniqueConstraint("domain", "status_code", name="uq_record_status_definition_code"),
        sa.UniqueConstraint("status_id", name=op.f("uq_record_status_definition_status_id")),
        schema="md_master",
    )
    op.create_table(
        "source_authority_type",
        sa.Column("source_authority_uuid", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "source_authority_id",
            sa.String(length=24),
            server_default=sa.text("md_master.next_business_id('SAUT')"),
            nullable=False,
        ),
        sa.Column("authority_code", sa.String(length=100), nullable=False),
        sa.Column("authority_name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("precedence", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=30), server_default="ACTIVE", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.Column("updated_by", sa.UUID(), nullable=True),
        sa.CheckConstraint("status in ('ACTIVE', 'RETIRED')", name=op.f("ck_source_authority_type_status_allowed")),
        sa.CheckConstraint(
            "authority_code = upper(authority_code)", name=op.f("ck_source_authority_type_authority_code_upper")
        ),
        sa.PrimaryKeyConstraint("source_authority_uuid", name=op.f("pk_source_authority_type")),
        sa.UniqueConstraint("authority_code", name=op.f("uq_source_authority_type_authority_code")),
        sa.UniqueConstraint("source_authority_id", name=op.f("uq_source_authority_type_source_authority_id")),
        schema="md_master",
    )
    op.create_table(
        "sync_mode_definition",
        sa.Column("sync_mode_uuid", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "sync_mode_id",
            sa.String(length=24),
            server_default=sa.text("md_master.next_business_id('SYNC')"),
            nullable=False,
        ),
        sa.Column("sync_code", sa.String(length=100), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=30), server_default="ACTIVE", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.Column("updated_by", sa.UUID(), nullable=True),
        sa.CheckConstraint("status in ('ACTIVE', 'RETIRED')", name=op.f("ck_sync_mode_definition_status_allowed")),
        sa.CheckConstraint("sync_code = upper(sync_code)", name=op.f("ck_sync_mode_definition_sync_code_upper")),
        sa.PrimaryKeyConstraint("sync_mode_uuid", name=op.f("pk_sync_mode_definition")),
        sa.UniqueConstraint("sync_code", name=op.f("uq_sync_mode_definition_sync_code")),
        sa.UniqueConstraint("sync_mode_id", name=op.f("uq_sync_mode_definition_sync_mode_id")),
        schema="md_master",
    )
    op.create_table(
        "timezone_reference",
        sa.Column("timezone_uuid", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "timezone_id",
            sa.String(length=24),
            server_default=sa.text("md_master.next_business_id('TZ')"),
            nullable=False,
        ),
        sa.Column("iana_name", sa.String(length=80), nullable=False),
        sa.Column("display_name", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=30), server_default="ACTIVE", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.Column("updated_by", sa.UUID(), nullable=True),
        sa.CheckConstraint("status in ('ACTIVE', 'RETIRED')", name=op.f("ck_timezone_reference_status_allowed")),
        sa.PrimaryKeyConstraint("timezone_uuid", name=op.f("pk_timezone_reference")),
        sa.UniqueConstraint("iana_name", name=op.f("uq_timezone_reference_iana_name")),
        sa.UniqueConstraint("timezone_id", name=op.f("uq_timezone_reference_timezone_id")),
        schema="md_master",
    )
    op.create_table(
        "transformation_definition",
        sa.Column("transformation_uuid", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "transformation_id",
            sa.String(length=24),
            server_default=sa.text("md_master.next_business_id('TRN')"),
            nullable=False,
        ),
        sa.Column("transformation_code", sa.String(length=100), nullable=False),
        sa.Column("transformation_name", sa.String(length=255), nullable=False),
        sa.Column("category", sa.String(length=30), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("parameter_schema", postgresql.JSONB(), nullable=True),
        sa.Column("customer_override_allowed", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("version", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=30), server_default="ACTIVE", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.Column("updated_by", sa.UUID(), nullable=True),
        sa.CheckConstraint(
            "category in ('DIRECT', 'FORMAT', 'LOOKUP', 'VALUE')",
            name=op.f("ck_transformation_definition_category_allowed"),
        ),
        sa.CheckConstraint(
            "status in ('ACTIVE', 'DEPRECATED', 'RETIRED')", name=op.f("ck_transformation_definition_status_allowed")
        ),
        sa.CheckConstraint(
            "transformation_code = upper(transformation_code)",
            name=op.f("ck_transformation_definition_transformation_code_upper"),
        ),
        sa.PrimaryKeyConstraint("transformation_uuid", name=op.f("pk_transformation_definition")),
        sa.UniqueConstraint("transformation_code", "version", name="uq_transformation_definition_code_version"),
        sa.UniqueConstraint("transformation_id", name=op.f("uq_transformation_definition_transformation_id")),
        schema="md_master",
    )
    op.create_table(
        "unit_of_measure",
        sa.Column("uom_uuid", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "uom_id", sa.String(length=24), server_default=sa.text("md_master.next_business_id('UOM')"), nullable=False
        ),
        sa.Column("uom_code", sa.String(length=20), nullable=False),
        sa.Column("uom_name", sa.String(length=120), nullable=False),
        sa.Column("dimension", sa.String(length=60), nullable=True),
        sa.Column("canonical_unit_uuid", sa.UUID(), nullable=True),
        sa.Column("conversion_factor", sa.Numeric(precision=30, scale=12), nullable=True),
        sa.Column("status", sa.String(length=30), server_default="ACTIVE", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.Column("updated_by", sa.UUID(), nullable=True),
        sa.CheckConstraint("status in ('ACTIVE', 'RETIRED')", name=op.f("ck_unit_of_measure_status_allowed")),
        sa.ForeignKeyConstraint(
            ["canonical_unit_uuid"],
            ["md_master.unit_of_measure.uom_uuid"],
            name=op.f("fk_unit_of_measure_canonical_unit_uuid_unit_of_measure"),
        ),
        sa.PrimaryKeyConstraint("uom_uuid", name=op.f("pk_unit_of_measure")),
        sa.UniqueConstraint("uom_code", name=op.f("uq_unit_of_measure_uom_code")),
        sa.UniqueConstraint("uom_id", name=op.f("uq_unit_of_measure_uom_id")),
        schema="md_master",
    )
    op.create_table(
        "validation_rule_definition",
        sa.Column("validation_rule_uuid", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "validation_rule_id",
            sa.String(length=24),
            server_default=sa.text("md_master.next_business_id('VAL')"),
            nullable=False,
        ),
        sa.Column("rule_code", sa.String(length=100), nullable=False),
        sa.Column("rule_name", sa.String(length=255), nullable=False),
        sa.Column("rule_type", sa.String(length=30), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("parameter_schema", postgresql.JSONB(), nullable=True),
        sa.Column("severity", sa.String(length=20), nullable=False),
        sa.Column("blocking", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("version", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=30), server_default="ACTIVE", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.Column("updated_by", sa.UUID(), nullable=True),
        sa.CheckConstraint(
            "rule_type in ('FIELD', 'REFERENCE', 'CROSS_FIELD')",
            name=op.f("ck_validation_rule_definition_rule_type_allowed"),
        ),
        sa.CheckConstraint(
            "severity in ('INFO', 'WARNING', 'ERROR', 'BLOCKING')",
            name=op.f("ck_validation_rule_definition_severity_allowed"),
        ),
        sa.CheckConstraint(
            "status in ('ACTIVE', 'RETIRED')", name=op.f("ck_validation_rule_definition_status_allowed")
        ),
        sa.CheckConstraint("rule_code = upper(rule_code)", name=op.f("ck_validation_rule_definition_rule_code_upper")),
        sa.PrimaryKeyConstraint("validation_rule_uuid", name=op.f("pk_validation_rule_definition")),
        sa.UniqueConstraint("rule_code", "version", name="uq_validation_rule_definition_code_version"),
        sa.UniqueConstraint("validation_rule_id", name=op.f("uq_validation_rule_definition_validation_rule_id")),
        schema="md_master",
    )
    op.create_table(
        "application_vendor",
        sa.Column("vendor_uuid", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "vendor_id",
            sa.String(length=24),
            server_default=sa.text("md_master.next_business_id('VEND')"),
            nullable=False,
        ),
        sa.Column("vendor_code", sa.String(length=100), nullable=False),
        sa.Column("vendor_name", sa.String(length=255), nullable=False),
        sa.Column("legal_name", sa.String(length=255), nullable=True),
        sa.Column("website", sa.String(length=500), nullable=True),
        sa.Column("country_uuid", sa.UUID(), nullable=True),
        sa.Column("status", sa.String(length=30), server_default="ACTIVE", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.Column("updated_by", sa.UUID(), nullable=True),
        sa.CheckConstraint(
            "status in ('ACTIVE', 'DEPRECATED', 'RETIRED')", name=op.f("ck_application_vendor_status_allowed")
        ),
        sa.CheckConstraint("vendor_code = upper(vendor_code)", name=op.f("ck_application_vendor_vendor_code_upper")),
        sa.ForeignKeyConstraint(
            ["country_uuid"],
            ["md_master.country_reference.country_uuid"],
            name=op.f("fk_application_vendor_country_uuid_country_reference"),
        ),
        sa.PrimaryKeyConstraint("vendor_uuid", name=op.f("pk_application_vendor")),
        sa.UniqueConstraint("vendor_code", name=op.f("uq_application_vendor_vendor_code")),
        sa.UniqueConstraint("vendor_id", name=op.f("uq_application_vendor_vendor_id")),
        sa.UniqueConstraint("vendor_name", name=op.f("uq_application_vendor_vendor_name")),
        schema="md_master",
    )
    op.create_table(
        "canonical_field_definition",
        sa.Column("canonical_field_uuid", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "canonical_field_id",
            sa.String(length=24),
            server_default=sa.text("md_master.next_business_id('CFLD')"),
            nullable=False,
        ),
        sa.Column("canonical_entity_uuid", sa.UUID(), nullable=False),
        sa.Column("field_name", sa.String(length=255), nullable=False),
        sa.Column("field_label", sa.String(length=255), nullable=False),
        sa.Column("data_type", sa.String(length=30), nullable=False),
        sa.Column("required", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("nullable", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("reference_entity_uuid", sa.UUID(), nullable=True),
        sa.Column("system_managed", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("mapping_allowed", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("override_policy_uuid", sa.UUID(), nullable=True),
        sa.Column("data_classification_uuid", sa.UUID(), nullable=True),
        sa.Column("field_group_uuid", sa.UUID(), nullable=True),
        sa.Column("status", sa.String(length=30), server_default="ACTIVE", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.Column("updated_by", sa.UUID(), nullable=True),
        sa.CheckConstraint(
            "data_type <> 'UUID_REF' or reference_entity_uuid is not null",
            name=op.f("ck_canonical_field_definition_reference_has_target"),
        ),
        sa.CheckConstraint(
            "data_type in ('STRING', 'TEXT', 'INTEGER', 'DECIMAL', 'BOOLEAN', 'DATE', 'DATETIME', 'UUID', 'UUID_REF', 'JSON', 'ENUM')",
            name=op.f("ck_canonical_field_definition_data_type_allowed"),
        ),
        sa.CheckConstraint(
            "status in ('ACTIVE', 'DEPRECATED', 'RETIRED')", name=op.f("ck_canonical_field_definition_status_allowed")
        ),
        sa.CheckConstraint(
            "not (system_managed and mapping_allowed)",
            name=op.f("ck_canonical_field_definition_system_managed_not_mappable"),
        ),
        sa.ForeignKeyConstraint(
            ["canonical_entity_uuid"],
            ["md_master.canonical_entity_definition.canonical_entity_uuid"],
            name=op.f("fk_canonical_field_definition_canonical_entity_uuid_canonical_entity_definition"),
        ),
        sa.ForeignKeyConstraint(
            ["data_classification_uuid"],
            ["md_master.data_classification.classification_uuid"],
            name=op.f("fk_canonical_field_definition_data_classification_uuid_data_classification"),
        ),
        sa.ForeignKeyConstraint(
            ["field_group_uuid"],
            ["md_master.field_group_definition.field_group_uuid"],
            name=op.f("fk_canonical_field_definition_field_group_uuid_field_group_definition"),
        ),
        sa.ForeignKeyConstraint(
            ["override_policy_uuid"],
            ["md_master.mapping_override_policy.override_policy_uuid"],
            name=op.f("fk_canonical_field_definition_override_policy_uuid_mapping_override_policy"),
        ),
        sa.ForeignKeyConstraint(
            ["reference_entity_uuid"],
            ["md_master.canonical_entity_definition.canonical_entity_uuid"],
            name=op.f("fk_canonical_field_definition_reference_entity_uuid_canonical_entity_definition"),
        ),
        sa.PrimaryKeyConstraint("canonical_field_uuid", name=op.f("pk_canonical_field_definition")),
        sa.UniqueConstraint("canonical_entity_uuid", "field_name", name="uq_canonical_field_definition_name"),
        sa.UniqueConstraint("canonical_field_id", name=op.f("uq_canonical_field_definition_canonical_field_id")),
        schema="md_master",
    )
    op.create_table(
        "canonical_value_item",
        sa.Column("value_item_uuid", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "value_item_id",
            sa.String(length=24),
            server_default=sa.text("md_master.next_business_id('CVI')"),
            nullable=False,
        ),
        sa.Column("value_set_uuid", sa.UUID(), nullable=False),
        sa.Column("value_code", sa.String(length=100), nullable=False),
        sa.Column("display_label", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("display_order", sa.Integer(), nullable=True),
        sa.Column("effective_from", sa.Date(), nullable=True),
        sa.Column("effective_to", sa.Date(), nullable=True),
        sa.Column("status", sa.String(length=30), server_default="ACTIVE", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.Column("updated_by", sa.UUID(), nullable=True),
        sa.CheckConstraint("status in ('ACTIVE', 'RETIRED')", name=op.f("ck_canonical_value_item_status_allowed")),
        sa.CheckConstraint("value_code = upper(value_code)", name=op.f("ck_canonical_value_item_value_code_upper")),
        sa.ForeignKeyConstraint(
            ["value_set_uuid"],
            ["md_master.canonical_value_set.value_set_uuid"],
            name=op.f("fk_canonical_value_item_value_set_uuid_canonical_value_set"),
        ),
        sa.PrimaryKeyConstraint("value_item_uuid", name=op.f("pk_canonical_value_item")),
        sa.UniqueConstraint("value_item_id", name=op.f("uq_canonical_value_item_value_item_id")),
        sa.UniqueConstraint("value_set_uuid", "value_code", name="uq_canonical_value_item_code"),
        schema="md_master",
    )
    op.create_table(
        "data_quality_rule",
        sa.Column("data_quality_rule_uuid", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "data_quality_rule_id",
            sa.String(length=24),
            server_default=sa.text("md_master.next_business_id('DQR')"),
            nullable=False,
        ),
        sa.Column("rule_code", sa.String(length=100), nullable=False),
        sa.Column("canonical_entity_uuid", sa.UUID(), nullable=False),
        sa.Column("rule_type", sa.String(length=30), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("severity", sa.String(length=20), nullable=False),
        sa.Column("blocking", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("version", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=30), server_default="ACTIVE", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.Column("updated_by", sa.UUID(), nullable=True),
        sa.CheckConstraint(
            "rule_type in ('CROSS_FIELD', 'REFERENTIAL', 'TEMPORAL')",
            name=op.f("ck_data_quality_rule_rule_type_allowed"),
        ),
        sa.CheckConstraint(
            "severity in ('WARNING', 'ERROR', 'BLOCKING')", name=op.f("ck_data_quality_rule_severity_allowed")
        ),
        sa.CheckConstraint("status in ('ACTIVE', 'RETIRED')", name=op.f("ck_data_quality_rule_status_allowed")),
        sa.CheckConstraint("rule_code = upper(rule_code)", name=op.f("ck_data_quality_rule_rule_code_upper")),
        sa.ForeignKeyConstraint(
            ["canonical_entity_uuid"],
            ["md_master.canonical_entity_definition.canonical_entity_uuid"],
            name=op.f("fk_data_quality_rule_canonical_entity_uuid_canonical_entity_definition"),
        ),
        sa.PrimaryKeyConstraint("data_quality_rule_uuid", name=op.f("pk_data_quality_rule")),
        sa.UniqueConstraint("data_quality_rule_id", name=op.f("uq_data_quality_rule_data_quality_rule_id")),
        sa.UniqueConstraint("rule_code", "version", name="uq_data_quality_rule_code_version"),
        schema="md_master",
    )
    op.create_table(
        "jurisdiction_reference",
        sa.Column("jurisdiction_uuid", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "jurisdiction_id",
            sa.String(length=24),
            server_default=sa.text("md_master.next_business_id('JUR')"),
            nullable=False,
        ),
        sa.Column("jurisdiction_code", sa.String(length=40), nullable=False),
        sa.Column("jurisdiction_name", sa.String(length=255), nullable=False),
        sa.Column("jurisdiction_type", sa.String(length=20), nullable=False),
        sa.Column("country_uuid", sa.UUID(), nullable=True),
        sa.Column("status", sa.String(length=30), server_default="ACTIVE", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.Column("updated_by", sa.UUID(), nullable=True),
        sa.CheckConstraint(
            "jurisdiction_type in ('COUNTRY', 'REGION')",
            name=op.f("ck_jurisdiction_reference_jurisdiction_type_allowed"),
        ),
        sa.CheckConstraint("status in ('ACTIVE', 'RETIRED')", name=op.f("ck_jurisdiction_reference_status_allowed")),
        sa.CheckConstraint(
            "jurisdiction_code = upper(jurisdiction_code)",
            name=op.f("ck_jurisdiction_reference_jurisdiction_code_upper"),
        ),
        sa.ForeignKeyConstraint(
            ["country_uuid"],
            ["md_master.country_reference.country_uuid"],
            name=op.f("fk_jurisdiction_reference_country_uuid_country_reference"),
        ),
        sa.PrimaryKeyConstraint("jurisdiction_uuid", name=op.f("pk_jurisdiction_reference")),
        sa.UniqueConstraint("jurisdiction_code", name=op.f("uq_jurisdiction_reference_jurisdiction_code")),
        sa.UniqueConstraint("jurisdiction_id", name=op.f("uq_jurisdiction_reference_jurisdiction_id")),
        schema="md_master",
    )
    op.create_table(
        "reference_resolution_rule",
        sa.Column("reference_rule_uuid", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "reference_rule_id",
            sa.String(length=24),
            server_default=sa.text("md_master.next_business_id('REFR')"),
            nullable=False,
        ),
        sa.Column("rule_code", sa.String(length=100), nullable=False),
        sa.Column("target_entity_uuid", sa.UUID(), nullable=False),
        sa.Column("lookup_fields", postgresql.JSONB(), nullable=False),
        sa.Column("match_strategy", sa.String(length=20), nullable=False),
        sa.Column("case_sensitive", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("ambiguity_policy", sa.String(length=20), nullable=False),
        sa.Column("not_found_policy", sa.String(length=30), nullable=False),
        sa.Column("version", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=30), server_default="ACTIVE", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.Column("updated_by", sa.UUID(), nullable=True),
        sa.CheckConstraint(
            "ambiguity_policy in ('BLOCK', 'REVIEW')",
            name=op.f("ck_reference_resolution_rule_ambiguity_policy_allowed"),
        ),
        sa.CheckConstraint(
            "match_strategy in ('EXACT', 'NORMALIZED')",
            name=op.f("ck_reference_resolution_rule_match_strategy_allowed"),
        ),
        sa.CheckConstraint(
            "not_found_policy in ('BLOCK', 'DEFER', 'PRESERVE_UNRESOLVED')",
            name=op.f("ck_reference_resolution_rule_not_found_policy_allowed"),
        ),
        sa.CheckConstraint("status in ('ACTIVE', 'RETIRED')", name=op.f("ck_reference_resolution_rule_status_allowed")),
        sa.CheckConstraint("rule_code = upper(rule_code)", name=op.f("ck_reference_resolution_rule_rule_code_upper")),
        sa.ForeignKeyConstraint(
            ["target_entity_uuid"],
            ["md_master.canonical_entity_definition.canonical_entity_uuid"],
            name=op.f("fk_reference_resolution_rule_target_entity_uuid_canonical_entity_definition"),
        ),
        sa.PrimaryKeyConstraint("reference_rule_uuid", name=op.f("pk_reference_resolution_rule")),
        sa.UniqueConstraint("reference_rule_id", name=op.f("uq_reference_resolution_rule_reference_rule_id")),
        sa.UniqueConstraint("rule_code", "version", name="uq_reference_resolution_rule_code_version"),
        schema="md_master",
    )
    op.create_table(
        "region_reference",
        sa.Column("region_uuid", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "region_id",
            sa.String(length=24),
            server_default=sa.text("md_master.next_business_id('REG')"),
            nullable=False,
        ),
        sa.Column("country_uuid", sa.UUID(), nullable=False),
        sa.Column("region_code", sa.String(length=20), nullable=False),
        sa.Column("region_name", sa.String(length=255), nullable=False),
        sa.Column("region_type", sa.String(length=60), nullable=True),
        sa.Column("status", sa.String(length=30), server_default="ACTIVE", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.Column("updated_by", sa.UUID(), nullable=True),
        sa.CheckConstraint("status in ('ACTIVE', 'RETIRED')", name=op.f("ck_region_reference_status_allowed")),
        sa.CheckConstraint("region_code = upper(region_code)", name=op.f("ck_region_reference_region_code_upper")),
        sa.ForeignKeyConstraint(
            ["country_uuid"],
            ["md_master.country_reference.country_uuid"],
            name=op.f("fk_region_reference_country_uuid_country_reference"),
        ),
        sa.PrimaryKeyConstraint("region_uuid", name=op.f("pk_region_reference")),
        sa.UniqueConstraint("country_uuid", "region_code", name="uq_region_reference_code"),
        sa.UniqueConstraint("region_id", name=op.f("uq_region_reference_region_id")),
        schema="md_master",
    )
    op.create_table(
        "external_application",
        sa.Column("application_uuid", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "application_id",
            sa.String(length=24),
            server_default=sa.text("md_master.next_business_id('APP')"),
            nullable=False,
        ),
        sa.Column("application_code", sa.String(length=100), nullable=False),
        sa.Column("application_name", sa.String(length=255), nullable=False),
        sa.Column("vendor_uuid", sa.UUID(), nullable=False),
        sa.Column("category_uuid", sa.UUID(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("integration_support_status", sa.String(length=30), server_default="PLANNED", nullable=False),
        sa.Column("supports_api", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("supports_webhook", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("supports_schema_discovery", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("supports_incremental_sync", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("status", sa.String(length=30), server_default="DRAFT", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.Column("updated_by", sa.UUID(), nullable=True),
        sa.CheckConstraint(
            "integration_support_status in ('PLANNED', 'CONFIGURABLE', 'SUPPORTED')",
            name=op.f("ck_external_application_support_status_allowed"),
        ),
        sa.CheckConstraint(
            "status in ('DRAFT', 'ACTIVE', 'DEPRECATED', 'RETIRED')",
            name=op.f("ck_external_application_status_allowed"),
        ),
        sa.CheckConstraint(
            "application_code = upper(application_code)", name=op.f("ck_external_application_application_code_upper")
        ),
        sa.ForeignKeyConstraint(
            ["category_uuid"],
            ["md_master.application_category.category_uuid"],
            name=op.f("fk_external_application_category_uuid_application_category"),
        ),
        sa.ForeignKeyConstraint(
            ["vendor_uuid"],
            ["md_master.application_vendor.vendor_uuid"],
            name=op.f("fk_external_application_vendor_uuid_application_vendor"),
        ),
        sa.PrimaryKeyConstraint("application_uuid", name=op.f("pk_external_application")),
        sa.UniqueConstraint("application_code", name=op.f("uq_external_application_application_code")),
        sa.UniqueConstraint("application_id", name=op.f("uq_external_application_application_id")),
        schema="md_master",
    )
    op.create_table(
        "regulatory_authority",
        sa.Column("authority_uuid", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "authority_id",
            sa.String(length=24),
            server_default=sa.text("md_master.next_business_id('RA')"),
            nullable=False,
        ),
        sa.Column("authority_code", sa.String(length=60), nullable=False),
        sa.Column("authority_name", sa.String(length=255), nullable=False),
        sa.Column("jurisdiction_uuid", sa.UUID(), nullable=False),
        sa.Column("country_uuid", sa.UUID(), nullable=True),
        sa.Column("authority_type", sa.String(length=80), nullable=True),
        sa.Column("website_reference", sa.String(length=500), nullable=True),
        sa.Column("status", sa.String(length=30), server_default="ACTIVE", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.Column("updated_by", sa.UUID(), nullable=True),
        sa.CheckConstraint("status in ('ACTIVE', 'RETIRED')", name=op.f("ck_regulatory_authority_status_allowed")),
        sa.CheckConstraint(
            "authority_code = upper(authority_code)", name=op.f("ck_regulatory_authority_authority_code_upper")
        ),
        sa.ForeignKeyConstraint(
            ["country_uuid"],
            ["md_master.country_reference.country_uuid"],
            name=op.f("fk_regulatory_authority_country_uuid_country_reference"),
        ),
        sa.ForeignKeyConstraint(
            ["jurisdiction_uuid"],
            ["md_master.jurisdiction_reference.jurisdiction_uuid"],
            name=op.f("fk_regulatory_authority_jurisdiction_uuid_jurisdiction_reference"),
        ),
        sa.PrimaryKeyConstraint("authority_uuid", name=op.f("pk_regulatory_authority")),
        sa.UniqueConstraint("authority_code", name=op.f("uq_regulatory_authority_authority_code")),
        sa.UniqueConstraint("authority_id", name=op.f("uq_regulatory_authority_authority_id")),
        schema="md_master",
    )
    op.create_table(
        "application_version_definition",
        sa.Column("application_version_uuid", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "application_version_id",
            sa.String(length=24),
            server_default=sa.text("md_master.next_business_id('APPVER')"),
            nullable=False,
        ),
        sa.Column("application_uuid", sa.UUID(), nullable=False),
        sa.Column("version_code", sa.String(length=80), nullable=False),
        sa.Column("api_version", sa.String(length=80), nullable=True),
        sa.Column("schema_version", sa.String(length=80), nullable=True),
        sa.Column("release_date", sa.Date(), nullable=True),
        sa.Column("support_status", sa.String(length=30), server_default="SUPPORTED", nullable=False),
        sa.Column("effective_from", sa.Date(), nullable=True),
        sa.Column("effective_to", sa.Date(), nullable=True),
        sa.Column("status", sa.String(length=30), server_default="ACTIVE", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.Column("updated_by", sa.UUID(), nullable=True),
        sa.CheckConstraint(
            "status in ('ACTIVE', 'DEPRECATED', 'RETIRED')",
            name=op.f("ck_application_version_definition_status_allowed"),
        ),
        sa.CheckConstraint(
            "support_status in ('SUPPORTED', 'LEGACY', 'PLANNED')",
            name=op.f("ck_application_version_definition_support_status_allowed"),
        ),
        sa.ForeignKeyConstraint(
            ["application_uuid"],
            ["md_master.external_application.application_uuid"],
            name=op.f("fk_application_version_definition_application_uuid_external_application"),
        ),
        sa.PrimaryKeyConstraint("application_version_uuid", name=op.f("pk_application_version_definition")),
        sa.UniqueConstraint("application_uuid", "version_code", name="uq_application_version_definition_code"),
        sa.UniqueConstraint(
            "application_version_id", name=op.f("uq_application_version_definition_application_version_id")
        ),
        schema="md_master",
    )
    op.create_table(
        "connector_definition",
        sa.Column("connector_uuid", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "connector_id",
            sa.String(length=24),
            server_default=sa.text("md_master.next_business_id('CONN')"),
            nullable=False,
        ),
        sa.Column("application_uuid", sa.UUID(), nullable=False),
        sa.Column("connector_code", sa.String(length=100), nullable=False),
        sa.Column("connector_name", sa.String(length=255), nullable=False),
        sa.Column("connector_type", sa.String(length=30), nullable=False),
        sa.Column("default_authentication_type_uuid", sa.UUID(), nullable=True),
        sa.Column("supports_schema_discovery", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("supports_incremental_sync", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("supports_webhook", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("status", sa.String(length=30), server_default="ACTIVE", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.Column("updated_by", sa.UUID(), nullable=True),
        sa.CheckConstraint(
            "connector_type in ('REST', 'FILE', 'WEBHOOK', 'DB_GATEWAY')",
            name=op.f("ck_connector_definition_connector_type_allowed"),
        ),
        sa.CheckConstraint(
            "status in ('ACTIVE', 'DEPRECATED', 'RETIRED')", name=op.f("ck_connector_definition_status_allowed")
        ),
        sa.CheckConstraint(
            "connector_code = upper(connector_code)", name=op.f("ck_connector_definition_connector_code_upper")
        ),
        sa.ForeignKeyConstraint(
            ["application_uuid"],
            ["md_master.external_application.application_uuid"],
            name=op.f("fk_connector_definition_application_uuid_external_application"),
        ),
        sa.ForeignKeyConstraint(
            ["default_authentication_type_uuid"],
            ["md_master.authentication_type_definition.authentication_type_uuid"],
            name=op.f("fk_connector_definition_default_authentication_type_uuid_authentication_type_definition"),
        ),
        sa.PrimaryKeyConstraint("connector_uuid", name=op.f("pk_connector_definition")),
        sa.UniqueConstraint("connector_code", name=op.f("uq_connector_definition_connector_code")),
        sa.UniqueConstraint("connector_id", name=op.f("uq_connector_definition_connector_id")),
        schema="md_master",
    )
    op.create_table(
        "external_application_industry",
        sa.Column("relation_uuid", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "relation_id",
            sa.String(length=24),
            server_default=sa.text("md_master.next_business_id('APPIND')"),
            nullable=False,
        ),
        sa.Column("application_uuid", sa.UUID(), nullable=False),
        sa.Column("industry_uuid", sa.UUID(), nullable=False),
        sa.Column("is_primary", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("status", sa.String(length=30), server_default="ACTIVE", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.Column("updated_by", sa.UUID(), nullable=True),
        sa.CheckConstraint(
            "status in ('ACTIVE', 'INACTIVE')", name=op.f("ck_external_application_industry_status_allowed")
        ),
        sa.ForeignKeyConstraint(
            ["application_uuid"],
            ["md_master.external_application.application_uuid"],
            name=op.f("fk_external_application_industry_application_uuid_external_application"),
        ),
        sa.ForeignKeyConstraint(
            ["industry_uuid"],
            ["md_master.industry_domain.industry_uuid"],
            name=op.f("fk_external_application_industry_industry_uuid_industry_domain"),
        ),
        sa.PrimaryKeyConstraint("relation_uuid", name=op.f("pk_external_application_industry")),
        sa.UniqueConstraint("application_uuid", "industry_uuid", name="uq_external_application_industry_pair"),
        sa.UniqueConstraint("relation_id", name=op.f("uq_external_application_industry_relation_id")),
        schema="md_master",
    )
    op.create_table(
        "connector_version_definition",
        sa.Column("connector_version_uuid", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "connector_version_id",
            sa.String(length=24),
            server_default=sa.text("md_master.next_business_id('CONV')"),
            nullable=False,
        ),
        sa.Column("connector_uuid", sa.UUID(), nullable=False),
        sa.Column("version_code", sa.String(length=40), nullable=False),
        sa.Column("api_version", sa.String(length=80), nullable=True),
        sa.Column("schema_version", sa.String(length=80), nullable=True),
        sa.Column("authentication_type_uuid", sa.UUID(), nullable=True),
        sa.Column("pagination_type_uuid", sa.UUID(), nullable=True),
        sa.Column("default_sync_mode_uuid", sa.UUID(), nullable=True),
        sa.Column("released_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deprecated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(length=30), server_default="ACTIVE", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.Column("updated_by", sa.UUID(), nullable=True),
        sa.CheckConstraint(
            "status in ('ACTIVE', 'DEPRECATED', 'RETIRED')", name=op.f("ck_connector_version_definition_status_allowed")
        ),
        sa.ForeignKeyConstraint(
            ["authentication_type_uuid"],
            ["md_master.authentication_type_definition.authentication_type_uuid"],
            name=op.f("fk_connector_version_definition_authentication_type_uuid_authentication_type_definition"),
        ),
        sa.ForeignKeyConstraint(
            ["connector_uuid"],
            ["md_master.connector_definition.connector_uuid"],
            name=op.f("fk_connector_version_definition_connector_uuid_connector_definition"),
        ),
        sa.ForeignKeyConstraint(
            ["default_sync_mode_uuid"],
            ["md_master.sync_mode_definition.sync_mode_uuid"],
            name=op.f("fk_connector_version_definition_default_sync_mode_uuid_sync_mode_definition"),
        ),
        sa.ForeignKeyConstraint(
            ["pagination_type_uuid"],
            ["md_master.pagination_type_definition.pagination_type_uuid"],
            name=op.f("fk_connector_version_definition_pagination_type_uuid_pagination_type_definition"),
        ),
        sa.PrimaryKeyConstraint("connector_version_uuid", name=op.f("pk_connector_version_definition")),
        sa.UniqueConstraint("connector_uuid", "version_code", name="uq_connector_version_definition_code"),
        sa.UniqueConstraint("connector_version_id", name=op.f("uq_connector_version_definition_connector_version_id")),
        schema="md_master",
    )
    op.create_table(
        "source_object_definition",
        sa.Column("source_object_uuid", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "source_object_id",
            sa.String(length=24),
            server_default=sa.text("md_master.next_business_id('SOBJ')"),
            nullable=False,
        ),
        sa.Column("application_uuid", sa.UUID(), nullable=False),
        sa.Column("application_version_uuid", sa.UUID(), nullable=True),
        sa.Column("object_code", sa.String(length=100), nullable=False),
        sa.Column("object_name", sa.String(length=255), nullable=False),
        sa.Column("api_object_name", sa.String(length=255), nullable=True),
        sa.Column("primary_key_field", sa.String(length=255), nullable=True),
        sa.Column("incremental_cursor_field", sa.String(length=255), nullable=True),
        sa.Column("schema_version", sa.String(length=80), nullable=True),
        sa.Column("status", sa.String(length=30), server_default="ACTIVE", nullable=False),
        sa.Column("effective_from", sa.Date(), nullable=True),
        sa.Column("effective_to", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.Column("updated_by", sa.UUID(), nullable=True),
        sa.CheckConstraint(
            "status in ('ACTIVE', 'DEPRECATED', 'RETIRED')", name=op.f("ck_source_object_definition_status_allowed")
        ),
        sa.CheckConstraint(
            "object_code = upper(object_code)", name=op.f("ck_source_object_definition_object_code_upper")
        ),
        sa.ForeignKeyConstraint(
            ["application_uuid"],
            ["md_master.external_application.application_uuid"],
            name=op.f("fk_source_object_definition_application_uuid_external_application"),
        ),
        sa.ForeignKeyConstraint(
            ["application_version_uuid"],
            ["md_master.application_version_definition.application_version_uuid"],
            name=op.f("fk_source_object_definition_application_version_uuid_application_version_definition"),
        ),
        sa.PrimaryKeyConstraint("source_object_uuid", name=op.f("pk_source_object_definition")),
        sa.UniqueConstraint("application_uuid", "object_code", name="uq_source_object_definition_code"),
        sa.UniqueConstraint("source_object_id", name=op.f("uq_source_object_definition_source_object_id")),
        schema="md_master",
    )
    op.create_table(
        "master_mapping_family",
        sa.Column("mapping_family_uuid", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "mapping_family_id",
            sa.String(length=24),
            server_default=sa.text("md_master.next_business_id('MMF')"),
            nullable=False,
        ),
        sa.Column("application_uuid", sa.UUID(), nullable=False),
        sa.Column("source_object_uuid", sa.UUID(), nullable=False),
        sa.Column("mapping_code", sa.String(length=100), nullable=False),
        sa.Column("mapping_name", sa.String(length=255), nullable=False),
        sa.Column("default_canonical_entity_uuid", sa.UUID(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=30), server_default="ACTIVE", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.Column("updated_by", sa.UUID(), nullable=True),
        sa.CheckConstraint("status in ('ACTIVE', 'RETIRED')", name=op.f("ck_master_mapping_family_status_allowed")),
        sa.CheckConstraint(
            "mapping_code = upper(mapping_code)", name=op.f("ck_master_mapping_family_mapping_code_upper")
        ),
        sa.ForeignKeyConstraint(
            ["application_uuid"],
            ["md_master.external_application.application_uuid"],
            name=op.f("fk_master_mapping_family_application_uuid_external_application"),
        ),
        sa.ForeignKeyConstraint(
            ["default_canonical_entity_uuid"],
            ["md_master.canonical_entity_definition.canonical_entity_uuid"],
            name=op.f("fk_master_mapping_family_default_canonical_entity_uuid_canonical_entity_definition"),
        ),
        sa.ForeignKeyConstraint(
            ["source_object_uuid"],
            ["md_master.source_object_definition.source_object_uuid"],
            name=op.f("fk_master_mapping_family_source_object_uuid_source_object_definition"),
        ),
        sa.PrimaryKeyConstraint("mapping_family_uuid", name=op.f("pk_master_mapping_family")),
        sa.UniqueConstraint("mapping_code", name=op.f("uq_master_mapping_family_mapping_code")),
        sa.UniqueConstraint("mapping_family_id", name=op.f("uq_master_mapping_family_mapping_family_id")),
        schema="md_master",
    )
    op.create_table(
        "source_field_definition",
        sa.Column("source_field_uuid", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "source_field_id",
            sa.String(length=24),
            server_default=sa.text("md_master.next_business_id('SFLD')"),
            nullable=False,
        ),
        sa.Column("source_object_uuid", sa.UUID(), nullable=False),
        sa.Column("field_name", sa.String(length=255), nullable=False),
        sa.Column("field_label", sa.String(length=255), nullable=False),
        sa.Column("field_group_uuid", sa.UUID(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("data_type", sa.String(length=30), nullable=False),
        sa.Column("required", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("nullable", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("sample_value", sa.Text(), nullable=True),
        sa.Column("data_classification_uuid", sa.UUID(), nullable=True),
        sa.Column("introduced_schema_version", sa.String(length=80), nullable=True),
        sa.Column("deprecated_schema_version", sa.String(length=80), nullable=True),
        sa.Column("status", sa.String(length=30), server_default="ACTIVE", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.Column("updated_by", sa.UUID(), nullable=True),
        sa.CheckConstraint(
            "data_type in ('STRING', 'TEXT', 'INTEGER', 'DECIMAL', 'BOOLEAN', 'DATE', 'DATETIME', 'UUID', 'UUID_REF', 'JSON', 'ENUM')",
            name=op.f("ck_source_field_definition_data_type_allowed"),
        ),
        sa.CheckConstraint(
            "status in ('ACTIVE', 'DEPRECATED', 'RETIRED')", name=op.f("ck_source_field_definition_status_allowed")
        ),
        sa.ForeignKeyConstraint(
            ["data_classification_uuid"],
            ["md_master.data_classification.classification_uuid"],
            name=op.f("fk_source_field_definition_data_classification_uuid_data_classification"),
        ),
        sa.ForeignKeyConstraint(
            ["field_group_uuid"],
            ["md_master.field_group_definition.field_group_uuid"],
            name=op.f("fk_source_field_definition_field_group_uuid_field_group_definition"),
        ),
        sa.ForeignKeyConstraint(
            ["source_object_uuid"],
            ["md_master.source_object_definition.source_object_uuid"],
            name=op.f("fk_source_field_definition_source_object_uuid_source_object_definition"),
        ),
        sa.PrimaryKeyConstraint("source_field_uuid", name=op.f("pk_source_field_definition")),
        sa.UniqueConstraint("source_field_id", name=op.f("uq_source_field_definition_source_field_id")),
        sa.UniqueConstraint("source_object_uuid", "field_name", name="uq_source_field_definition_name"),
        schema="md_master",
    )
    op.create_table(
        "master_mapping_version",
        sa.Column("mapping_version_uuid", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "mapping_version_id",
            sa.String(length=24),
            server_default=sa.text("md_master.next_business_id('MMV')"),
            nullable=False,
        ),
        sa.Column("mapping_family_uuid", sa.UUID(), nullable=False),
        sa.Column("version_code", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=30), server_default="DRAFT", nullable=False),
        sa.Column("based_on_version_uuid", sa.UUID(), nullable=True),
        sa.Column("source_schema_version", sa.String(length=80), nullable=True),
        sa.Column("change_summary", sa.Text(), nullable=True),
        sa.Column("validated_by", sa.UUID(), nullable=True),
        sa.Column("validated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approved_by", sa.UUID(), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("released_by", sa.UUID(), nullable=True),
        sa.Column("released_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("released_content_hash", sa.String(length=64), nullable=True),
        sa.Column("effective_from", sa.Date(), nullable=True),
        sa.Column("effective_to", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.Column("updated_by", sa.UUID(), nullable=True),
        sa.CheckConstraint(
            "status in ('DRAFT', 'VALIDATION', 'APPROVED', 'RELEASED', 'SUPERSEDED', 'RETIRED')",
            name=op.f("ck_master_mapping_version_status_allowed"),
        ),
        sa.CheckConstraint(
            "status not in ('RELEASED', 'SUPERSEDED') or (released_at is not null and released_content_hash is not null)",
            name=op.f("ck_master_mapping_version_released_has_evidence"),
        ),
        sa.ForeignKeyConstraint(
            ["based_on_version_uuid"],
            ["md_master.master_mapping_version.mapping_version_uuid"],
            name=op.f("fk_master_mapping_version_based_on_version_uuid_master_mapping_version"),
        ),
        sa.ForeignKeyConstraint(
            ["mapping_family_uuid"],
            ["md_master.master_mapping_family.mapping_family_uuid"],
            name=op.f("fk_master_mapping_version_mapping_family_uuid_master_mapping_family"),
        ),
        sa.PrimaryKeyConstraint("mapping_version_uuid", name=op.f("pk_master_mapping_version")),
        sa.UniqueConstraint("mapping_family_uuid", "version_code", name="uq_master_mapping_version_code"),
        sa.UniqueConstraint("mapping_version_id", name=op.f("uq_master_mapping_version_mapping_version_id")),
        schema="md_master",
    )
    op.create_table(
        "source_value_set",
        sa.Column("source_value_set_uuid", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "source_value_set_id",
            sa.String(length=24),
            server_default=sa.text("md_master.next_business_id('SVS')"),
            nullable=False,
        ),
        sa.Column("application_uuid", sa.UUID(), nullable=False),
        sa.Column("source_object_uuid", sa.UUID(), nullable=False),
        sa.Column("source_field_uuid", sa.UUID(), nullable=False),
        sa.Column("schema_version", sa.String(length=80), nullable=True),
        sa.Column("status", sa.String(length=30), server_default="ACTIVE", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.Column("updated_by", sa.UUID(), nullable=True),
        sa.CheckConstraint("status in ('ACTIVE', 'RETIRED')", name=op.f("ck_source_value_set_status_allowed")),
        sa.ForeignKeyConstraint(
            ["application_uuid"],
            ["md_master.external_application.application_uuid"],
            name=op.f("fk_source_value_set_application_uuid_external_application"),
        ),
        sa.ForeignKeyConstraint(
            ["source_field_uuid"],
            ["md_master.source_field_definition.source_field_uuid"],
            name=op.f("fk_source_value_set_source_field_uuid_source_field_definition"),
        ),
        sa.ForeignKeyConstraint(
            ["source_object_uuid"],
            ["md_master.source_object_definition.source_object_uuid"],
            name=op.f("fk_source_value_set_source_object_uuid_source_object_definition"),
        ),
        sa.PrimaryKeyConstraint("source_value_set_uuid", name=op.f("pk_source_value_set")),
        sa.UniqueConstraint("source_value_set_id", name=op.f("uq_source_value_set_source_value_set_id")),
        schema="md_master",
    )
    op.create_table(
        "master_mapping_item",
        sa.Column("mapping_item_uuid", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "mapping_item_id",
            sa.String(length=24),
            server_default=sa.text("md_master.next_business_id('MMI')"),
            nullable=False,
        ),
        sa.Column("mapping_version_uuid", sa.UUID(), nullable=False),
        sa.Column("source_field_uuid", sa.UUID(), nullable=False),
        sa.Column("canonical_entity_uuid", sa.UUID(), nullable=False),
        sa.Column("canonical_field_uuid", sa.UUID(), nullable=False),
        sa.Column("sequence_no", sa.Integer(), nullable=False),
        sa.Column("mapping_type", sa.String(length=20), nullable=False),
        sa.Column("transformation_uuid", sa.UUID(), nullable=True),
        sa.Column("validation_rule_uuid", sa.UUID(), nullable=True),
        sa.Column("reference_rule_uuid", sa.UUID(), nullable=True),
        sa.Column("null_handling_policy", sa.String(length=30), server_default="ALLOW_NULL", nullable=False),
        sa.Column("source_authority_uuid", sa.UUID(), nullable=True),
        sa.Column("required_for_mapping", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("customer_override_allowed", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("override_policy_uuid", sa.UUID(), nullable=False),
        sa.Column("default_value", sa.Text(), nullable=True),
        sa.Column("mapping_notes", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=30), server_default="ACTIVE", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.Column("updated_by", sa.UUID(), nullable=True),
        sa.CheckConstraint(
            "mapping_type <> 'REFERENCE' or reference_rule_uuid is not null",
            name=op.f("ck_master_mapping_item_reference_has_rule"),
        ),
        sa.CheckConstraint(
            "mapping_type <> 'TRANSFORM' or transformation_uuid is not null",
            name=op.f("ck_master_mapping_item_transform_has_rule"),
        ),
        sa.CheckConstraint(
            "mapping_type in ('DIRECT', 'TRANSFORM', 'LOOKUP', 'REFERENCE')",
            name=op.f("ck_master_mapping_item_mapping_type_allowed"),
        ),
        sa.CheckConstraint(
            "null_handling_policy in ('ALLOW_NULL', 'REJECT', 'PRESERVE_UNKNOWN', 'DEFAULT_VALUE')",
            name=op.f("ck_master_mapping_item_null_handling_allowed"),
        ),
        sa.CheckConstraint("status in ('ACTIVE', 'DEPRECATED')", name=op.f("ck_master_mapping_item_status_allowed")),
        sa.ForeignKeyConstraint(
            ["canonical_entity_uuid"],
            ["md_master.canonical_entity_definition.canonical_entity_uuid"],
            name=op.f("fk_master_mapping_item_canonical_entity_uuid_canonical_entity_definition"),
        ),
        sa.ForeignKeyConstraint(
            ["canonical_field_uuid"],
            ["md_master.canonical_field_definition.canonical_field_uuid"],
            name=op.f("fk_master_mapping_item_canonical_field_uuid_canonical_field_definition"),
        ),
        sa.ForeignKeyConstraint(
            ["mapping_version_uuid"],
            ["md_master.master_mapping_version.mapping_version_uuid"],
            name=op.f("fk_master_mapping_item_mapping_version_uuid_master_mapping_version"),
        ),
        sa.ForeignKeyConstraint(
            ["override_policy_uuid"],
            ["md_master.mapping_override_policy.override_policy_uuid"],
            name=op.f("fk_master_mapping_item_override_policy_uuid_mapping_override_policy"),
        ),
        sa.ForeignKeyConstraint(
            ["reference_rule_uuid"],
            ["md_master.reference_resolution_rule.reference_rule_uuid"],
            name=op.f("fk_master_mapping_item_reference_rule_uuid_reference_resolution_rule"),
        ),
        sa.ForeignKeyConstraint(
            ["source_authority_uuid"],
            ["md_master.source_authority_type.source_authority_uuid"],
            name=op.f("fk_master_mapping_item_source_authority_uuid_source_authority_type"),
        ),
        sa.ForeignKeyConstraint(
            ["source_field_uuid"],
            ["md_master.source_field_definition.source_field_uuid"],
            name=op.f("fk_master_mapping_item_source_field_uuid_source_field_definition"),
        ),
        sa.ForeignKeyConstraint(
            ["transformation_uuid"],
            ["md_master.transformation_definition.transformation_uuid"],
            name=op.f("fk_master_mapping_item_transformation_uuid_transformation_definition"),
        ),
        sa.ForeignKeyConstraint(
            ["validation_rule_uuid"],
            ["md_master.validation_rule_definition.validation_rule_uuid"],
            name=op.f("fk_master_mapping_item_validation_rule_uuid_validation_rule_definition"),
        ),
        sa.PrimaryKeyConstraint("mapping_item_uuid", name=op.f("pk_master_mapping_item")),
        sa.UniqueConstraint("mapping_item_id", name=op.f("uq_master_mapping_item_mapping_item_id")),
        sa.UniqueConstraint("mapping_version_uuid", "canonical_field_uuid", name="uq_master_mapping_item_target"),
        sa.UniqueConstraint("mapping_version_uuid", "sequence_no", name="uq_master_mapping_item_sequence"),
        schema="md_master",
    )
    op.create_table(
        "source_value_item",
        sa.Column("source_value_item_uuid", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "source_value_item_id",
            sa.String(length=24),
            server_default=sa.text("md_master.next_business_id('SVI')"),
            nullable=False,
        ),
        sa.Column("source_value_set_uuid", sa.UUID(), nullable=False),
        sa.Column("source_value", sa.String(length=255), nullable=False),
        sa.Column("source_label", sa.String(length=255), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=30), server_default="ACTIVE", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.Column("updated_by", sa.UUID(), nullable=True),
        sa.CheckConstraint("status in ('ACTIVE', 'RETIRED')", name=op.f("ck_source_value_item_status_allowed")),
        sa.ForeignKeyConstraint(
            ["source_value_set_uuid"],
            ["md_master.source_value_set.source_value_set_uuid"],
            name=op.f("fk_source_value_item_source_value_set_uuid_source_value_set"),
        ),
        sa.PrimaryKeyConstraint("source_value_item_uuid", name=op.f("pk_source_value_item")),
        sa.UniqueConstraint("source_value_item_id", name=op.f("uq_source_value_item_source_value_item_id")),
        sa.UniqueConstraint("source_value_set_uuid", "source_value", name="uq_source_value_item_value"),
        schema="md_master",
    )
    op.create_table(
        "value_mapping_definition",
        sa.Column("value_mapping_uuid", sa.UUID(), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column(
            "value_mapping_id",
            sa.String(length=24),
            server_default=sa.text("md_master.next_business_id('VMAP')"),
            nullable=False,
        ),
        sa.Column("application_uuid", sa.UUID(), nullable=False),
        sa.Column("source_value_item_uuid", sa.UUID(), nullable=False),
        sa.Column("canonical_value_item_uuid", sa.UUID(), nullable=False),
        sa.Column("mapping_version", sa.String(length=40), nullable=False),
        sa.Column("customer_override_allowed", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("status", sa.String(length=30), server_default="ACTIVE", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("created_by", sa.UUID(), nullable=True),
        sa.Column("updated_by", sa.UUID(), nullable=True),
        sa.CheckConstraint("status in ('ACTIVE', 'RETIRED')", name=op.f("ck_value_mapping_definition_status_allowed")),
        sa.ForeignKeyConstraint(
            ["application_uuid"],
            ["md_master.external_application.application_uuid"],
            name=op.f("fk_value_mapping_definition_application_uuid_external_application"),
        ),
        sa.ForeignKeyConstraint(
            ["canonical_value_item_uuid"],
            ["md_master.canonical_value_item.value_item_uuid"],
            name=op.f("fk_value_mapping_definition_canonical_value_item_uuid_canonical_value_item"),
        ),
        sa.ForeignKeyConstraint(
            ["source_value_item_uuid"],
            ["md_master.source_value_item.source_value_item_uuid"],
            name=op.f("fk_value_mapping_definition_source_value_item_uuid_source_value_item"),
        ),
        sa.PrimaryKeyConstraint("value_mapping_uuid", name=op.f("pk_value_mapping_definition")),
        sa.UniqueConstraint("source_value_item_uuid", "mapping_version", name="uq_value_mapping_definition_source"),
        sa.UniqueConstraint("value_mapping_id", name=op.f("uq_value_mapping_definition_value_mapping_id")),
        schema="md_master",
    )

    registry = sa.table(
        "business_id_prefix",
        sa.column("prefix", sa.String),
        sa.column("entity_name", sa.String),
        sa.column("sequence_name", sa.String),
        sa.column("id_width", sa.Integer),
        sa.column("owning_schema", sa.String),
        schema="md_master",
    )
    rows = []
    for prefix, entity, width, schema in PREFIXES:
        sequence = f"seq_business_id_{prefix.lower()}"
        op.execute(f"create sequence md_master.{sequence} as bigint start with 1 increment by 1 no cycle")
        rows.append(
            {
                "prefix": prefix,
                "entity_name": entity,
                "sequence_name": sequence,
                "id_width": width,
                "owning_schema": schema,
            }
        )
    op.bulk_insert(registry, rows)

    op.execute(GUARD_FUNCTIONS)
    op.execute(
        "create trigger trg_business_id_prefix_protect before update or delete on md_master.business_id_prefix "
        "for each row execute function md_master.protect_prefix_registry()"
    )
    for table, column in BUSINESS_ID_COLUMNS.items():
        op.execute(
            f"create trigger trg_{table}_business_id before update of {column} on md_master.{table} "
            f"for each row execute function md_master.reject_business_id_change('{column}')"
        )
        op.execute(
            f"create trigger trg_{table}_delete_guard before delete on md_master.{table} "
            f"for each row execute function md_master.reject_non_draft_delete()"
        )
    op.execute(
        "create trigger trg_master_mapping_version_release_guard before update on md_master.master_mapping_version "
        "for each row execute function md_master.protect_released_mapping_version()"
    )
    op.execute(
        "create trigger trg_master_mapping_item_release_guard "
        "before insert or update or delete on md_master.master_mapping_item "
        "for each row execute function md_master.protect_released_mapping_items()"
    )


def downgrade():
    op.execute("drop schema if exists md_master cascade")
