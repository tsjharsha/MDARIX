"""The first contact, urgent intake and triage, and duplicates with import history (release 0.10.57).

The third migration of the trial line's expert-feedback releases (TRIAL_FEEDBACK_PLAN.md section 7: T-G32, T-G19,
T-G20), chained from the trial line's head ``tr03amergemvpimports``. Its revision id starts with ``tr`` so it never
collides with an ``md`` revision of ``mvp-1.0`` (``tr03pmssources`` stays reserved for proactive PMS); after the
forward merge, ``mvp-1.0`` adds a merge revision joining its head and this one.

Expand-only: five new tables, each with its indexes and the tenant row-level security policy. No existing table or
row changes. The downgrade removes only what this migration added.

- ``intake_events``: a logged contact, an urgent intake, or an imported service record given the first-contact check;
- ``first_contact_checks``: the check's versions (answers, suggestion, signed classification, the QA review);
- ``triage_records``: the triage record of a flagged item (an intake, a complaint or a set-aside row), with a
  manual escalation;
- ``record_links``: a person's decision on a possible duplicate (linked, dismissed, or a link undone), with the
  awareness before and after;
- ``record_field_changes``: the field changes a re-upload made to a record.

The models are in backend/app/db/models/intake.py. Legacy dedicated organization databases get the same from
scripts/add_workflow_tables_to_legacy_planes.py, which runs ``create_intake_tables``.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from infrastructure.database.migrations.helpers import quoted
from infrastructure.database.migrations.helpers import tenant_policy as _tenant_policy

revision = "tr04intaketriage"
down_revision = "tr03amergemvpimports"
branch_labels = None
depends_on = None

TABLES = ("record_field_changes", "record_links", "triage_records", "first_contact_checks", "intake_events")
KINDS = ("CONTACT", "URGENT", "SERVICE_RECORD")
OUTCOMES = ("COMPLAINT", "BOTH", "SERVICE_ONLY", "PENDING", "PENDING_CONFIRM")
SUBJECTS = ("INTAKE", "COMPLAINT", "QUARANTINE")
LINK_STATES = ("LINKED", "DISMISSED", "UNLINKED")


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


def create_intake_tables(system_scope: bool = True) -> None:
    """The five tables and their isolation (also used for legacy organization databases)."""
    op.create_table(
        "intake_events",
        *_common("intake_events"),
        sa.Column("reference", sa.String(30), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("reporter_words", sa.Text(), nullable=False),
        sa.Column("reporter_type", sa.String(40)),
        sa.Column("reporter_site", sa.String(120)),
        sa.Column("country", sa.String(80)),
        _uuid("product_id"),
        _uuid("product_version_id"),
        _uuid("lot_batch_id"),
        sa.Column("serial_number", sa.String(120)),
        sa.Column("requested", sa.String(30)),
        sa.Column("use_environment", sa.String(30)),
        sa.Column("user_type", sa.String(30)),
        _tz("event_at"),
        sa.Column("event_zone", sa.String(60)),
        _tz("first_knowledge_at"),
        sa.Column("first_knowledge_zone", sa.String(60)),
        sa.Column("first_knowledge_party", sa.String(30)),
        sa.Column("first_knowledge_basis", sa.String(30)),
        _tz("received_at"),
        sa.Column("received_zone", sa.String(60)),
        _tz("awareness_at"),
        sa.Column("awareness_zone", sa.String(60)),
        sa.Column("qms_ref", sa.String(120)),
        sa.Column("service_ticket", sa.String(120)),
        sa.Column("source_system", sa.String(40)),
        sa.Column("created_by", sa.String(255), nullable=False),
        _tz("created_at", False),
        _tz("updated_at", False),
        sa.UniqueConstraint("tenant_id", "reference", name="uq_intake_events_reference"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "product_id"], ["products.tenant_id", "products.id"], name="fk_intake_events_product"
        ),
        sa.CheckConstraint(f"kind IN ({quoted(KINDS)})", name=op.f("ck_intake_events_kind_known")),
    )
    op.create_index("ix_intake_events_tenant_created", "intake_events", ["tenant_id", "created_at"])
    op.create_table(
        "first_contact_checks",
        *_common("first_contact_checks"),
        _uuid("intake_event_id", False),
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("guide_version", sa.String(40), nullable=False),
        sa.Column("answers", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("unknowns", sa.Text()),
        sa.Column("suggestion", sa.String(30), nullable=False),
        sa.Column("classification", sa.String(30)),
        sa.Column("override_reason", sa.Text()),
        sa.Column("reason", sa.Text()),
        _uuid("signed_record_id"),
        sa.Column("content_fingerprint", sa.String(64)),
        sa.Column("signed_by", sa.String(255)),
        _tz("signed_at"),
        _uuid("superseded_by"),
        sa.Column("review_outcome", sa.String(20)),
        sa.Column("reviewed_by", sa.String(255)),
        _tz("reviewed_at"),
        sa.Column("review_note", sa.Text()),
        sa.Column("source_system", sa.String(40)),
        sa.Column("created_by", sa.String(255), nullable=False),
        _tz("created_at", False),
        _tz("updated_at", False),
        sa.ForeignKeyConstraint(
            ["intake_event_id"], ["intake_events.id"], name="fk_first_contact_checks_event", ondelete="CASCADE"
        ),
        sa.UniqueConstraint("intake_event_id", "version", name="uq_first_contact_checks_version"),
        sa.CheckConstraint(f"suggestion IN ({quoted(OUTCOMES)})", name=op.f("ck_first_contact_checks_suggestion")),
        sa.CheckConstraint(
            f"classification IS NULL OR classification IN ({quoted(OUTCOMES)})",
            name=op.f("ck_first_contact_checks_classification"),
        ),
        sa.CheckConstraint(
            "classification IS NULL OR signed_at IS NOT NULL", name=op.f("ck_first_contact_checks_signed")
        ),
        sa.CheckConstraint(
            "review_outcome IS NULL OR review_outcome IN ('AGREED', 'RECLASSIFIED')",
            name=op.f("ck_first_contact_checks_review_known"),
        ),
    )
    op.create_index("ix_first_contact_checks_tenant_event", "first_contact_checks", ["tenant_id", "intake_event_id"])
    op.create_table(
        "triage_records",
        *_common("triage_records"),
        sa.Column("subject_kind", sa.String(20), nullable=False),
        _uuid("subject_id", False),
        _tz("opened_at", False),
        sa.Column("target_hours", sa.Integer(), server_default=sa.text("24"), nullable=False),
        sa.Column("escalated_by", sa.String(255)),
        _tz("escalated_at"),
        sa.Column("escalation_reason", sa.Text()),
        sa.Column("severity", sa.String(20)),
        sa.Column("public_health_threat", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("remedial_action", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("event_owner", sa.String(255)),
        sa.Column("triage_owner", sa.String(255)),
        sa.Column("backup_owner", sa.String(255)),
        sa.Column("immediate_action", sa.Text()),
        sa.Column("no_action_reason", sa.Text()),
        _tz("awareness_confirmed_at"),
        sa.Column("awareness_note", sa.Text()),
        sa.Column("completed_by", sa.String(255)),
        _tz("completed_at"),
        sa.Column("source_system", sa.String(40)),
        sa.Column("created_by", sa.String(255), nullable=False),
        _tz("created_at", False),
        _tz("updated_at", False),
        sa.UniqueConstraint("tenant_id", "subject_kind", "subject_id", name="uq_triage_records_subject"),
        sa.CheckConstraint(f"subject_kind IN ({quoted(SUBJECTS)})", name=op.f("ck_triage_records_subject_known")),
        sa.CheckConstraint("target_hours BETWEEN 1 AND 168", name=op.f("ck_triage_records_target_range")),
    )
    op.create_table(
        "record_links",
        *_common("record_links"),
        sa.Column("left_kind", sa.String(20), nullable=False),
        _uuid("left_id", False),
        sa.Column("right_kind", sa.String(20), nullable=False),
        _uuid("right_id", False),
        sa.Column("state", sa.String(20), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("decided_by", sa.String(255), nullable=False),
        _tz("decided_at", False),
        _tz("awareness_before"),
        _tz("awareness_after"),
        sa.Column("conflict", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("undo_reason", sa.Text()),
        sa.Column("undone_by", sa.String(255)),
        _tz("undone_at"),
        sa.Column("source_system", sa.String(40)),
        _tz("created_at", False),
        sa.CheckConstraint(f"state IN ({quoted(LINK_STATES)})", name=op.f("ck_record_links_state_known")),
        sa.CheckConstraint(
            f"left_kind IN ({quoted(SUBJECTS[:2])}) AND right_kind IN ({quoted(SUBJECTS[:2])})",
            name=op.f("ck_record_links_kinds_known"),
        ),
        sa.CheckConstraint("state <> 'UNLINKED' OR undo_reason IS NOT NULL", name=op.f("ck_record_links_undo_reason")),
    )
    op.create_index("ix_record_links_tenant_left", "record_links", ["tenant_id", "left_id"])
    op.create_index("ix_record_links_tenant_right", "record_links", ["tenant_id", "right_id"])
    op.create_table(
        "record_field_changes",
        *_common("record_field_changes"),
        sa.Column("entity", sa.String(30), nullable=False),
        _uuid("record_id", False),
        sa.Column("record_key", sa.String(400), nullable=False),
        _uuid("import_ref"),
        sa.Column("field", sa.String(60), nullable=False),
        sa.Column("before", sa.Text()),
        sa.Column("after", sa.Text()),
        sa.Column("source", sa.String(40), nullable=False),
        _tz("changed_at", False),
    )
    op.create_index("ix_record_field_changes_record", "record_field_changes", ["tenant_id", "entity", "record_id"])
    op.create_index("ix_record_field_changes_import", "record_field_changes", ["import_ref"])
    for table in TABLES:
        _tenant_policy(table, system_scope)


def upgrade():
    create_intake_tables()


def downgrade():
    for table in TABLES:
        op.drop_table(table)
