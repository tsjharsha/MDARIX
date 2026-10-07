"""Signals and triage (Phase 2): signals, the complaints they cover, their history, the investigations opened for
them, and each organization's detection rule settings.

- ``signals``: numbered SIG000001 per organization by the business-id trigger of md26; never renumbered. A duplicate
  or merged signal points at its canonical signal (``canonical_signal_id``) and is never deleted.
- ``signal_complaints``, ``signal_events``, ``investigation_signals``, ``signal_rules``.
All five are tenant-isolated (FORCE row-level security) like md27's tables. The models are in
backend/app/db/models/signals.py. Legacy dedicated organization databases get the same tables from
scripts/add_workflow_tables_to_legacy_planes.py, which runs this module's ``create_signal_tables``.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from infrastructure.database.migrations.business_ids import COUNTER_TABLE, LATER_OBJECTS, WIDTH

revision = "md28signals"
down_revision = "md27workflow"
branch_labels = None
depends_on = None

SIGNAL_STATUSES = (
    "NEW",
    "TRIAGE",
    "MONITOR",
    "NO_ACTION",
    "DUPLICATE",
    "MERGED",
    "INVESTIGATION_REQUIRED",
    "ESCALATED",
    "INVESTIGATION_OPEN",
    "DECISION_RECORDED",
    "CLOSED",
)
SIGNAL_PRIORITIES = ("LOW", "MEDIUM", "HIGH", "CRITICAL")
SIGNAL_ORIGINS = ("MANUAL", "THRESHOLD_RULE", "AI_SUGGESTED", "IMPORT")
SIGNALS = next(item for item in LATER_OBJECTS if item.table == "signals")

_TENANT = "NULLIF(current_setting('app.tenant_id', true), '')::uuid"
_SYSTEM = "(SELECT public.mdarix_system_scope())"
_GRANT = (
    "DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'mdarix_runtime') THEN "
    "GRANT SELECT, INSERT, UPDATE, DELETE ON public.{table} TO mdarix_runtime; END IF; END $$;"
)
TABLES = ("signals", "signal_complaints", "signal_events", "investigation_signals", "signal_rules")


def _quoted(values) -> str:
    return ", ".join(f"'{value}'" for value in values)


def _tenant_policy(table: str, system_scope: bool = True) -> None:
    """Rows are visible to their organization and to system scope, as in md23 and md27 (organization only in a
    legacy database, which has no system scope)."""
    match = f"tenant_id = {_TENANT}"
    allowed = f"{match} OR {_SYSTEM}" if system_scope else match
    op.execute(f"ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE public.{table} FORCE ROW LEVEL SECURITY")
    op.execute(f"CREATE POLICY mdarix_tenant_isolation ON public.{table} USING ({allowed}) WITH CHECK ({allowed})")
    op.execute(_GRANT.format(table=table))


def _id() -> sa.Column:
    return sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False)


def _tenant(table: str):
    return (
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], name=op.f(f"fk_{table}_tenant_id_tenants")),
    )


def _now(name: str) -> sa.Column:
    return sa.Column(name, sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False)


def create_signal_tables(system_scope: bool = True) -> None:
    """The five tables, their isolation and the signal numbering (also used for legacy organization databases)."""
    tenant_column, tenant_fk = _tenant("signals")
    op.create_table(
        "signals",
        _id(),
        tenant_column,
        sa.Column("business_id", sa.String(20), nullable=False),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("origin", sa.String(30), nullable=False),
        sa.Column("rule_code", sa.String(60)),
        sa.Column("rule_version", sa.Integer()),
        sa.Column("rule_parameters", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("product_id", postgresql.UUID(as_uuid=True)),
        sa.Column("product_version_id", postgresql.UUID(as_uuid=True)),
        sa.Column("problem_key", sa.String(160)),
        sa.Column("complaint_count", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("first_event_at", sa.DateTime(timezone=True)),
        sa.Column("last_event_at", sa.DateTime(timezone=True)),
        sa.Column("highest_severity", sa.String(40)),
        sa.Column("serious_harm", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("suggested_priority", sa.String(20)),
        sa.Column("confirmed_priority", sa.String(20)),
        sa.Column("priority_reason", sa.Text()),
        sa.Column("status", sa.String(30), server_default="NEW", nullable=False),
        sa.Column("owner_user_id", postgresql.UUID(as_uuid=True)),
        sa.Column("due_at", sa.DateTime(timezone=True)),
        sa.Column("canonical_signal_id", postgresql.UUID(as_uuid=True)),
        sa.Column("disposition_reason", sa.Text()),
        sa.Column("dispositioned_by", sa.String(255)),
        sa.Column("dispositioned_at", sa.DateTime(timezone=True)),
        sa.Column("monitor_review_date", sa.Date()),
        sa.Column("monitor_trigger", sa.Text()),
        sa.Column("created_by", sa.String(255), nullable=False),
        _now("created_at"),
        _now("updated_at"),
        sa.Column("details", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_signals")),
        tenant_fk,
        sa.UniqueConstraint("tenant_id", "id", name="uq_signals_tenant_id_id"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "product_id"], ["products.tenant_id", "products.id"], name="fk_signals_product"
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "product_version_id"],
            ["product_versions.tenant_id", "product_versions.id"],
            name="fk_signals_product_version",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "canonical_signal_id"], ["signals.tenant_id", "signals.id"], name="fk_signals_canonical"
        ),
        sa.CheckConstraint(f"status IN ({_quoted(SIGNAL_STATUSES)})", name=op.f("ck_signals_status_known")),
        sa.CheckConstraint(f"origin IN ({_quoted(SIGNAL_ORIGINS)})", name=op.f("ck_signals_origin_known")),
        sa.CheckConstraint(
            f"suggested_priority IS NULL OR suggested_priority IN ({_quoted(SIGNAL_PRIORITIES)})",
            name=op.f("ck_signals_suggested_priority_known"),
        ),
        sa.CheckConstraint(
            f"confirmed_priority IS NULL OR confirmed_priority IN ({_quoted(SIGNAL_PRIORITIES)})",
            name=op.f("ck_signals_confirmed_priority_known"),
        ),
    )
    op.create_index("ix_signals_tenant_status", "signals", ["tenant_id", "status"])
    op.create_index(
        "ix_signals_tenant_problem", "signals", ["tenant_id", "product_id", "product_version_id", "problem_key"]
    )
    _tenant_policy("signals", system_scope)
    # Signal numbers: the md26 assigning function on insert, unique per organization, never changed afterwards.
    op.execute(f"CREATE UNIQUE INDEX {SIGNALS.index_name} ON public.signals (tenant_id, business_id)")
    op.execute(
        f"CREATE TRIGGER {SIGNALS.trigger_name} BEFORE INSERT ON public.signals "
        f"FOR EACH ROW EXECUTE FUNCTION public.mdarix_assign_business_id('{SIGNALS.prefix}', '{SIGNALS.scope}', "
        f"'{WIDTH}')"
    )
    op.execute(
        f"CREATE TRIGGER {SIGNALS.immutable_trigger_name} BEFORE UPDATE OF business_id ON public.signals "
        "FOR EACH ROW WHEN (OLD.business_id IS NOT NULL AND OLD.business_id IS DISTINCT FROM NEW.business_id) "
        "EXECUTE FUNCTION public.mdarix_reject_immutable_identifier()"
    )

    tenant_column, tenant_fk = _tenant("signal_complaints")
    op.create_table(
        "signal_complaints",
        _id(),
        tenant_column,
        sa.Column("signal_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("complaint_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("added_how", sa.String(20), nullable=False),
        sa.Column("added_by", sa.String(255), nullable=False),
        _now("added_at"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_signal_complaints")),
        tenant_fk,
        sa.UniqueConstraint("tenant_id", "signal_id", "complaint_id", name="uq_signal_complaints_signal_complaint"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "signal_id"],
            ["signals.tenant_id", "signals.id"],
            name="fk_signal_complaints_signal",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "complaint_id"],
            ["complaints.tenant_id", "complaints.id"],
            name="fk_signal_complaints_complaint",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "added_how IN ('RULE', 'MANUAL', 'MERGE')", name=op.f("ck_signal_complaints_added_how_known")
        ),
    )
    op.create_index("ix_signal_complaints_tenant_complaint", "signal_complaints", ["tenant_id", "complaint_id"])
    _tenant_policy("signal_complaints", system_scope)

    tenant_column, tenant_fk = _tenant("signal_events")
    op.create_table(
        "signal_events",
        _id(),
        tenant_column,
        sa.Column("signal_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_type", sa.String(40), nullable=False),
        sa.Column("actor_ref", sa.String(255)),
        sa.Column("actor_role", sa.String(60)),
        sa.Column("from_status", sa.String(30)),
        sa.Column("to_status", sa.String(30)),
        sa.Column("reason", sa.Text()),
        sa.Column("details", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        _now("created_at"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_signal_events")),
        tenant_fk,
        sa.ForeignKeyConstraint(
            ["tenant_id", "signal_id"],
            ["signals.tenant_id", "signals.id"],
            name="fk_signal_events_signal",
            ondelete="CASCADE",
        ),
    )
    op.create_index("ix_signal_events_tenant_signal", "signal_events", ["tenant_id", "signal_id"])
    _tenant_policy("signal_events", system_scope)

    tenant_column, tenant_fk = _tenant("investigation_signals")
    op.create_table(
        "investigation_signals",
        _id(),
        tenant_column,
        sa.Column("investigation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("signal_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_by", sa.String(255), nullable=False),
        _now("created_at"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_investigation_signals")),
        tenant_fk,
        sa.UniqueConstraint(
            "tenant_id", "investigation_id", "signal_id", name="uq_investigation_signals_investigation_signal"
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "investigation_id"],
            ["investigations.tenant_id", "investigations.id"],
            name="fk_investigation_signals_investigation",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "signal_id"],
            ["signals.tenant_id", "signals.id"],
            name="fk_investigation_signals_signal",
            ondelete="CASCADE",
        ),
    )
    op.create_index("ix_investigation_signals_tenant_signal", "investigation_signals", ["tenant_id", "signal_id"])
    _tenant_policy("investigation_signals", system_scope)

    tenant_column, tenant_fk = _tenant("signal_rules")
    op.create_table(
        "signal_rules",
        _id(),
        tenant_column,
        sa.Column("rule_code", sa.String(60), nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("min_complaints", sa.Integer(), nullable=False),
        sa.Column("window_days", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("updated_by", sa.String(255)),
        _now("updated_at"),
        sa.Column("last_run_at", sa.DateTime(timezone=True)),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_signal_rules")),
        tenant_fk,
        sa.UniqueConstraint("tenant_id", "rule_code", name="uq_signal_rules_tenant_rule"),
        sa.CheckConstraint("min_complaints BETWEEN 2 AND 1000", name=op.f("ck_signal_rules_min_complaints_range")),
        sa.CheckConstraint("window_days BETWEEN 1 AND 365", name=op.f("ck_signal_rules_window_days_range")),
    )
    _tenant_policy("signal_rules", system_scope)


def _registry_present(connection) -> bool:
    return bool(connection.execute(sa.text("SELECT to_regclass('md_master.business_id_prefix') IS NOT NULL")).scalar())


def upgrade():
    create_signal_tables()
    connection = op.get_bind()
    if _registry_present(connection):
        sequence = f"seq_business_id_{SIGNALS.prefix.lower()}"
        op.execute(f"CREATE SEQUENCE IF NOT EXISTS md_master.{sequence}")
        op.execute(
            f"""
            INSERT INTO md_master.business_id_prefix (prefix, entity_name, sequence_name, id_width, owning_schema)
            VALUES ('{SIGNALS.prefix}', '{SIGNALS.entity}', '{sequence}', {WIDTH}, 'md_transaction')
            ON CONFLICT (prefix) DO UPDATE SET id_width = {WIDTH}
            """
        )


def downgrade():
    # Prefixes are permanent (md_master.protect_prefix_registry refuses removal); re-applying reuses them.
    op.execute(f"DELETE FROM public.{COUNTER_TABLE} WHERE prefix = '{SIGNALS.prefix}'")
    for table in reversed(TABLES):
        op.drop_table(table)
