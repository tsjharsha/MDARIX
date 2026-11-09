"""Cases, escalation to a Complaint and triage at two speeds (release 0.10.93, backlog item B2).

The nineteenth migration of the trial line, chained from ``tr18changereason`` (``tr17`` was kept for a build that
needed none). Expand-only: new nullable columns or columns with a default, new tables, widened check constraints, one
check constraint dropped (``external_parties.party_type_known``: party roles are validated in code, so later roles
need no migration). No column is dropped or renamed; the 0.10.92 images run on this schema.

- ``intake_events`` (the Case): its state (one function sets it), owner, channel, the product and lot as typed, the
  device identifiers' status and source (ID-1, ``identifiers``), the Complaint it became (composite reference), the
  withdrawal, the origin, a row version for optimistic concurrency and a request key for idempotent create (A4).
- ``first_contact_checks``: outcomes ``INQUIRY`` and ``NOT_A_COMPLAINT``; an incomplete draft's suggestion is
  ``UNANSWERED`` (an unanswered question is never Unknown); each recalculation kept in ``history``.
- ``complaints``: the QMS complaint ID (unique per organization when set), the product and lot as typed, the software
  version, the last sync and the record owner.
- ``triage_records``: the two speeds, the version, the floor, the containment, the threat exclusion and the later
  awareness (signed), inheritance and the QMS triage; ``triage_record_versions`` keeps every version.
- ``case_addenda``: what was said later, by whom; never an edit of the reporter's words.
- ``external_parties``: linked to a Case, acting for the manufacturer, country, the contact columns (OD-1).
- ``due_alerts``: the channel, attempts and delivery result of each alert (A2).
- ``oversight_settings``: the fast-track hours (1-24, default 4), the case flow, the imported-backlog rule.
- ``record_ownership``: the system of record per domain (MDARIX or EXTERNAL).

New tables get the forced tenant row-level security policy. References between tenant tables are composite
``(tenant_id, x_id)``; their targets get ``UNIQUE (tenant_id, id)`` where missing. The models are in
backend/app/db/models/intake.py, foundation.py, guides_communications.py and oversight.py. Legacy dedicated
organization databases get the same from scripts/add_workflow_tables_to_legacy_planes.py, which runs
``add_cases_escalation``.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from infrastructure.database.migrations.helpers import quoted
from infrastructure.database.migrations.helpers import tenant_policy as _tenant_policy

revision = "tr19casesescalation"
down_revision = "tr18changereason"
branch_labels = None
depends_on = None

NEW_TABLES = ("triage_record_versions", "case_addenda", "record_ownership")
CASE_STATES = ("OPEN", "PENDING", "IN_REVIEW", "CLOSED", "ESCALATED", "VOIDED")
ESCALATIONS = ("CREATED", "ATTACHED")
OWNERS = ("MDARIX", "EXTERNAL")
PATIENTS = ("NONE", "ONE", "SEVERAL", "NOT_KNOWN")
OLD_OUTCOMES = ("COMPLAINT", "BOTH", "SERVICE_ONLY", "PENDING", "PENDING_CONFIRM")
OUTCOMES = (*OLD_OUTCOMES, "INQUIRY", "NOT_A_COMPLAINT")
SPEEDS = ("FAST", "ROUTINE")
ADDENDUM_KINDS = ("STATEMENT", "WITHDRAWAL", "TECHNICIAN_FINDING", "CORRECTION_BY_REPORTER")
CASE_FLOWS = ("ONE_RECORD", "SERVICE_FIRST")
PARTY_TYPES = ("REPORTER", "DISTRIBUTOR", "HOSPITAL", "SERVICE_PARTNER")
DELIVERIES = ("DELIVERED", "FAILED", "RETRYING")


def _uuid(name: str, nullable: bool = True) -> sa.Column:
    return sa.Column(name, postgresql.UUID(as_uuid=True), nullable=nullable)


def _tz(name: str, nullable: bool = True) -> sa.Column:
    return sa.Column(name, sa.DateTime(timezone=True), nullable=nullable)


def _common(table: str) -> list:
    return [
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        _uuid("tenant_id", False),
        sa.PrimaryKeyConstraint("id", name=op.f(f"pk_{table}")),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], name=op.f(f"fk_{table}_tenant_id_tenants")),
    ]


def _add(table: str, *columns: sa.Column) -> None:
    for column in columns:
        op.add_column(table, column)


def _check(table: str, name: str, condition: str) -> None:
    op.create_check_constraint(op.f(f"ck_{table}_{name}"), table, condition)


def _cases() -> None:
    table = "intake_events"
    _add(
        table,
        sa.Column("status", sa.String(20), nullable=False, server_default="OPEN"),
        sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("request_key", sa.String(80)),
        sa.Column("owner_id", sa.String(255)),
        sa.Column("channel", sa.String(40)),
        sa.Column("channel_ref", sa.String(200)),
        sa.Column("product_text", sa.String(200)),
        sa.Column("lot_text", sa.String(120)),
        sa.Column("udi", sa.String(120)),
        sa.Column("software_version", sa.String(60)),
        sa.Column("identifiers", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("reporter_country", sa.String(2)),
        sa.Column("country_text", sa.String(80)),
        sa.Column("late_entry_reason", sa.Text()),
        sa.Column("no_contact_reason", sa.Text()),
        sa.Column("patients", sa.String(12)),
        sa.Column("harm_text", sa.Text()),
        sa.Column("troubleshooting", sa.Text()),
        sa.Column("service_status", sa.String(20)),
        _tz("service_status_at"),
        sa.Column("masked", postgresql.JSONB()),
        _uuid("complaint_id"),
        sa.Column("escalation", sa.String(10)),
        _tz("escalated_at"),
        sa.Column("escalated_by", sa.String(255)),
        _tz("voided_at"),
        sa.Column("voided_by", sa.String(255)),
        sa.Column("void_reason", sa.Text()),
        _uuid("void_signed_record_id"),
        sa.Column("source_identifier", sa.String(255)),
        _tz("last_synced_at"),
        sa.Column("record_owner", sa.String(10)),
    )
    _check(table, "status_known", f"status IN ({quoted(CASE_STATES)})")
    _check(table, "version_positive", "version >= 1")
    _check(table, "escalation_known", f"escalation IS NULL OR escalation IN ({quoted(ESCALATIONS)})")
    _check(table, "escalated_complaint", "status <> 'ESCALATED' OR complaint_id IS NOT NULL")
    _check(table, "record_owner_known", f"record_owner IS NULL OR record_owner IN ({quoted(OWNERS)})")
    _check(table, "patients_known", f"patients IS NULL OR patients IN ({quoted(PATIENTS)})")
    _check(table, "void_reason", "voided_at IS NULL OR void_reason IS NOT NULL")
    op.create_unique_constraint("uq_intake_events_tenant_id_id", table, ["tenant_id", "id"])
    op.create_foreign_key(
        "fk_intake_events_complaint",
        table,
        "complaints",
        ["tenant_id", "complaint_id"],
        ["tenant_id", "id"],
    )
    op.create_index("ix_intake_events_tenant_status", table, ["tenant_id", "status"])
    op.create_index("ix_intake_events_tenant_owner", table, ["tenant_id", "owner_id"])
    op.create_index("ix_intake_events_tenant_complaint", table, ["tenant_id", "complaint_id"])
    op.create_index(
        "ix_intake_events_request_key",
        table,
        ["tenant_id", "request_key"],
        unique=True,
        postgresql_where=sa.text("request_key IS NOT NULL"),
    )


def _checks() -> None:
    table = "first_contact_checks"
    op.add_column(
        table, sa.Column("history", postgresql.JSONB(), nullable=False, server_default=sa.text("'[]'::jsonb"))
    )
    op.drop_constraint(op.f("ck_first_contact_checks_suggestion"), table, type_="check")
    op.drop_constraint(op.f("ck_first_contact_checks_classification"), table, type_="check")
    _check(table, "suggestion", f"suggestion IN ({quoted((*OUTCOMES, 'UNANSWERED'))})")
    _check(table, "classification", f"classification IS NULL OR classification IN ({quoted(OUTCOMES)})")


def _complaints() -> None:
    table = "complaints"
    _add(
        table,
        sa.Column("qms_ref", sa.String(120)),
        sa.Column("product_text", sa.String(200)),
        sa.Column("lot_text", sa.String(120)),
        sa.Column("software_version", sa.String(60)),
        _tz("last_synced_at"),
        sa.Column("record_owner", sa.String(10)),
    )
    _check(table, "record_owner_known", f"record_owner IS NULL OR record_owner IN ({quoted(OWNERS)})")
    # A new, empty column: the partial index has no row to build from, so a plain build holds its lock only briefly.
    op.create_index(
        "ix_complaints_tenant_qms_ref",
        table,
        ["tenant_id", "qms_ref"],
        unique=True,
        postgresql_where=sa.text("qms_ref IS NOT NULL"),
    )


def _triage() -> None:
    table = "triage_records"
    _add(
        table,
        sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("speed", sa.String(10)),
        _tz("due_at"),
        sa.Column("potential_severity", sa.String(20)),
        sa.Column("severity_floor", sa.String(20)),
        sa.Column("floor_reasons", postgresql.JSONB()),
        sa.Column("flags_at_completion", postgresql.JSONB()),
        sa.Column("containment", postgresql.JSONB()),
        sa.Column("change_reason", sa.Text()),
        _tz("reopened_at"),
        sa.Column("reopen_trigger", sa.String(30)),
        _tz("threat_excluded_at"),
        sa.Column("threat_excluded_by", sa.String(255)),
        sa.Column("threat_exclusion_reason", sa.Text()),
        _uuid("threat_signed_record_id"),
        _uuid("awareness_signed_record_id"),
        _uuid("inherited_from"),
        _tz("qms_triaged_at"),
        sa.Column("qms_owner_text", sa.String(255)),
        sa.Column("confirmed_by", sa.String(255)),
        _tz("confirmed_at"),
        sa.Column("source_identifier", sa.String(255)),
        _tz("acknowledged_at"),
        sa.Column("acknowledged_by", sa.String(255)),
        _tz("acknowledge_due_at"),
    )
    _check(table, "speed_known", f"speed IS NULL OR speed IN ({quoted(SPEEDS)})")
    _check(table, "version_positive", "version >= 1")
    op.create_unique_constraint("uq_triage_records_tenant_id_id", table, ["tenant_id", "id"])
    op.create_index("ix_triage_records_tenant_speed_completed", table, ["tenant_id", "speed", "completed_at"])
    op.create_table(
        "triage_record_versions",
        *_common("triage_record_versions"),
        _uuid("triage_record_id", False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("snapshot", postgresql.JSONB(), nullable=False),
        sa.Column("changed_fields", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("change_reason", sa.Text()),
        sa.Column("changed_by", sa.String(255), nullable=False),
        _tz("changed_at", False),
        _uuid("signed_record_id"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "triage_record_id"],
            ["triage_records.tenant_id", "triage_records.id"],
            name="fk_triage_record_versions_record",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("tenant_id", "triage_record_id", "version", name="uq_triage_record_versions_version"),
        sa.CheckConstraint("version >= 1", name=op.f("ck_triage_record_versions_version_positive")),
    )


def _addenda() -> None:
    op.create_table(
        "case_addenda",
        *_common("case_addenda"),
        _uuid("intake_event_id", False),
        sa.Column("kind", sa.String(30), nullable=False),
        sa.Column("said_by_role", sa.String(30), nullable=False),
        _tz("said_at"),
        sa.Column("said_zone", sa.String(60)),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("masked", postgresql.JSONB()),
        sa.Column("source_system", sa.String(40)),
        sa.Column("created_by", sa.String(255), nullable=False),
        _tz("created_at", False),
        sa.ForeignKeyConstraint(
            ["tenant_id", "intake_event_id"],
            ["intake_events.tenant_id", "intake_events.id"],
            name="fk_case_addenda_case",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(f"kind IN ({quoted(ADDENDUM_KINDS)})", name=op.f("ck_case_addenda_kind_known")),
    )
    op.create_index("ix_case_addenda_tenant_case", "case_addenda", ["tenant_id", "intake_event_id", "created_at"])


def _parties() -> None:
    table = "external_parties"
    _add(
        table,
        _uuid("intake_event_id"),
        sa.Column("acts_for_manufacturer", sa.Boolean()),
        sa.Column("country", sa.String(2)),
        sa.Column("contact_role", sa.String(120)),
        sa.Column("contact_email", sa.String(254)),
        sa.Column("contact_phone", sa.String(40)),
        sa.Column("preferred_channel", sa.String(20)),
        _tz("contact_erased_at"),
        sa.Column("contact_erased_by", sa.String(255)),
        sa.Column("contact_erase_reason", sa.Text()),
    )
    op.drop_constraint(op.f("ck_external_parties_party_type_known"), table, type_="check")
    op.create_foreign_key(
        "fk_external_parties_case", table, "intake_events", ["tenant_id", "intake_event_id"], ["tenant_id", "id"]
    )
    op.create_index("ix_external_parties_tenant_case", table, ["tenant_id", "intake_event_id"])


def _settings() -> None:
    table = "oversight_settings"
    _add(
        table,
        sa.Column("triage_fast_hours", sa.Integer(), nullable=False, server_default=sa.text("4")),
        sa.Column("case_flow", sa.String(20), nullable=False, server_default="ONE_RECORD"),
        sa.Column("backlog_days", sa.Integer(), nullable=False, server_default=sa.text("30")),
        sa.Column("backlog_target_days", sa.Integer(), nullable=False, server_default=sa.text("10")),
    )
    _check(table, "fast_hours_range", "triage_fast_hours BETWEEN 1 AND 24")
    _check(table, "case_flow_known", f"case_flow IN ({quoted(CASE_FLOWS)})")
    _check(table, "backlog_range", "backlog_days >= 1 AND backlog_target_days >= 1")
    op.create_table(
        "record_ownership",
        *_common("record_ownership"),
        sa.Column("domain", sa.String(40), nullable=False),
        sa.Column("owner", sa.String(10), nullable=False),
        sa.Column("system_name", sa.String(120)),
        sa.Column("set_by", sa.String(255), nullable=False),
        _tz("set_at", False),
        sa.UniqueConstraint("tenant_id", "domain", name="uq_record_ownership_domain"),
        sa.CheckConstraint(f"owner IN ({quoted(OWNERS)})", name=op.f("ck_record_ownership_owner_known")),
    )


def _alerts() -> None:
    """A2: each alert records its channel, attempts, last attempt and result; a failed delivery never resolves it."""
    table = "due_alerts"
    _add(
        table,
        sa.Column("channel", sa.String(20), nullable=False, server_default="IN_APP"),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default=sa.text("1")),
        _tz("last_attempt_at"),
        sa.Column("delivery", sa.String(20), nullable=False, server_default="DELIVERED"),
        sa.Column("delivery_error", sa.Text()),
    )
    _check(table, "delivery_known", f"delivery IN ({quoted(DELIVERIES)})")
    _check(table, "attempts_positive", "attempts >= 1")


def add_cases_escalation(system_scope: bool = True) -> None:
    """Every change of this migration (also used for legacy organization databases)."""
    _cases()
    _checks()
    _complaints()
    _triage()
    _addenda()
    _parties()
    _settings()
    _alerts()
    for table in NEW_TABLES:
        _tenant_policy(table, system_scope)


def upgrade():
    add_cases_escalation()


def downgrade():
    op.drop_constraint(op.f("ck_due_alerts_attempts_positive"), "due_alerts", type_="check")
    op.drop_constraint(op.f("ck_due_alerts_delivery_known"), "due_alerts", type_="check")
    for column in ("delivery_error", "delivery", "last_attempt_at", "attempts", "channel"):
        op.drop_column("due_alerts", column)
    for table in NEW_TABLES:
        op.drop_table(table)
    op.drop_constraint(op.f("ck_oversight_settings_backlog_range"), "oversight_settings", type_="check")
    op.drop_constraint(op.f("ck_oversight_settings_case_flow_known"), "oversight_settings", type_="check")
    op.drop_constraint(op.f("ck_oversight_settings_fast_hours_range"), "oversight_settings", type_="check")
    for column in ("backlog_target_days", "backlog_days", "case_flow", "triage_fast_hours"):
        op.drop_column("oversight_settings", column)
    op.drop_index("ix_external_parties_tenant_case", table_name="external_parties")
    op.drop_constraint("fk_external_parties_case", "external_parties", type_="foreignkey")
    # Rows with roles beyond the four of tr06 cannot keep the old check: it is restored only when every row fits.
    op.execute(
        "DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM external_parties WHERE party_type NOT IN "
        f"({quoted(PARTY_TYPES)})) THEN ALTER TABLE external_parties ADD CONSTRAINT "
        f"ck_external_parties_party_type_known CHECK (party_type IN ({quoted(PARTY_TYPES)})); END IF; END $$;"
    )
    for column in (
        "contact_erase_reason",
        "contact_erased_by",
        "contact_erased_at",
        "preferred_channel",
        "contact_phone",
        "contact_email",
        "contact_role",
        "country",
        "acts_for_manufacturer",
        "intake_event_id",
    ):
        op.drop_column("external_parties", column)
    op.drop_index("ix_triage_records_tenant_speed_completed", table_name="triage_records")
    op.drop_constraint("uq_triage_records_tenant_id_id", "triage_records", type_="unique")
    op.drop_constraint(op.f("ck_triage_records_version_positive"), "triage_records", type_="check")
    op.drop_constraint(op.f("ck_triage_records_speed_known"), "triage_records", type_="check")
    for column in (
        "acknowledge_due_at",
        "acknowledged_by",
        "acknowledged_at",
        "source_identifier",
        "confirmed_at",
        "confirmed_by",
        "qms_owner_text",
        "qms_triaged_at",
        "inherited_from",
        "awareness_signed_record_id",
        "threat_signed_record_id",
        "threat_exclusion_reason",
        "threat_excluded_by",
        "threat_excluded_at",
        "reopen_trigger",
        "reopened_at",
        "change_reason",
        "containment",
        "flags_at_completion",
        "floor_reasons",
        "severity_floor",
        "potential_severity",
        "due_at",
        "speed",
        "version",
    ):
        op.drop_column("triage_records", column)
    op.drop_index("ix_complaints_tenant_qms_ref", table_name="complaints")
    op.drop_constraint(op.f("ck_complaints_record_owner_known"), "complaints", type_="check")
    for column in ("record_owner", "last_synced_at", "software_version", "lot_text", "product_text", "qms_ref"):
        op.drop_column("complaints", column)
    # The new outcomes cannot stay under the old check: it is restored as NOT VALID, so rows signed under 0.10.93 are
    # kept (regulated records are never deleted) while new rows meet the old list.
    op.drop_constraint(op.f("ck_first_contact_checks_classification"), "first_contact_checks", type_="check")
    op.drop_constraint(op.f("ck_first_contact_checks_suggestion"), "first_contact_checks", type_="check")
    op.execute(
        "ALTER TABLE first_contact_checks ADD CONSTRAINT ck_first_contact_checks_suggestion "
        f"CHECK (suggestion IN ({quoted(OLD_OUTCOMES)})) NOT VALID"
    )
    op.execute(
        "ALTER TABLE first_contact_checks ADD CONSTRAINT ck_first_contact_checks_classification "
        f"CHECK (classification IS NULL OR classification IN ({quoted(OLD_OUTCOMES)})) NOT VALID"
    )
    op.drop_column("first_contact_checks", "history")
    op.drop_index("ix_intake_events_request_key", table_name="intake_events")
    op.drop_index("ix_intake_events_tenant_complaint", table_name="intake_events")
    op.drop_index("ix_intake_events_tenant_owner", table_name="intake_events")
    op.drop_index("ix_intake_events_tenant_status", table_name="intake_events")
    op.drop_constraint("fk_intake_events_complaint", "intake_events", type_="foreignkey")
    op.drop_constraint("uq_intake_events_tenant_id_id", "intake_events", type_="unique")
    for name in (
        "void_reason",
        "patients_known",
        "record_owner_known",
        "escalated_complaint",
        "escalation_known",
        "version_positive",
        "status_known",
    ):
        op.drop_constraint(op.f(f"ck_intake_events_{name}"), "intake_events", type_="check")
    for column in (
        "record_owner",
        "last_synced_at",
        "source_identifier",
        "void_signed_record_id",
        "void_reason",
        "voided_by",
        "voided_at",
        "escalated_by",
        "escalated_at",
        "escalation",
        "complaint_id",
        "masked",
        "service_status_at",
        "service_status",
        "troubleshooting",
        "harm_text",
        "patients",
        "late_entry_reason",
        "no_contact_reason",
        "country_text",
        "reporter_country",
        "identifiers",
        "software_version",
        "udi",
        "lot_text",
        "product_text",
        "channel_ref",
        "channel",
        "owner_id",
        "request_key",
        "version",
        "status",
    ):
        op.drop_column("intake_events", column)
