"""Reviews and the Decision Brief (Phase 5): risk and regulatory case reviews, controlled Decision Brief versions and
their quality-review actions.

- ``case_reviews`` (REV000001 per organization), ``decision_brief_versions`` (DBV000001 per organization), both
  numbered by the business-id trigger of md26, and ``brief_review_actions``. All tenant-isolated.
The models are in backend/app/db/models/reviews.py. Legacy dedicated organization databases get the same tables from
scripts/add_workflow_tables_to_legacy_planes.py, which runs ``create_review_tables``.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from infrastructure.database.migrations.business_ids import COUNTER_TABLE, LATER_OBJECTS, WIDTH

revision = "md32reviewsbrief"
down_revision = "md31intelligencevalues"
branch_labels = None
depends_on = None

REVIEW_TYPES = ("RISK", "REGULATORY")
REVIEW_STATUSES = ("REQUESTED", "IN_PROGRESS", "COMPLETED", "CANCELLED", "SUPERSEDED")
OUTCOMES = (
    "ADDITIONAL_EVIDENCE_REQUIRED",
    "ESCALATE_REGULATORY",
    "ESCALATE_SAFETY_CONCERN",
    "NO_CHANGE_REQUIRED",
    "NO_REPORTABILITY_CONCERN_IDENTIFIED",
    "REPORTABILITY_ASSESSMENT_COMPLETE",
    "REPORTING_REQUIRED",
    "RISK_CONTROL_REVIEW_REQUIRED",
    "RISK_FILE_REASSESSMENT_REQUIRED",
    "TREND_REPORTING_REVIEW_REQUIRED",
)
BRIEF_STATUSES = ("DRAFT", "READY_FOR_REVIEW", "UNDER_REVIEW", "RETURNED", "APPROVED_FOR_DECISION", "SUPERSEDED")
QUALITY_ACTIONS = (
    "START_REVIEW",
    "ACCEPT_FOR_DECISION",
    "RETURN_FOR_EVIDENCE",
    "RETURN_FOR_ANALYSIS",
    "RETURN_FOR_RISK_REVIEW",
    "RETURN_FOR_REGULATORY_REVIEW",
    "REJECT_PROPOSED_CONCLUSION",
    "ESCALATE",
)
NUMBERED = {item.table: item for item in LATER_OBJECTS if item.table in ("case_reviews", "decision_brief_versions")}
TABLES = ("brief_review_actions", "decision_brief_versions", "case_reviews")

_TENANT = "NULLIF(current_setting('app.tenant_id', true), '')::uuid"
_SYSTEM = "(SELECT public.mdarix_system_scope())"
_GRANT = (
    "DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'mdarix_runtime') THEN "
    "GRANT SELECT, INSERT, UPDATE, DELETE ON public.{table} TO mdarix_runtime; END IF; END $$;"
)


def _quoted(values) -> str:
    return ", ".join(f"'{value}'" for value in values)


def _tenant_policy(table: str, system_scope: bool = True) -> None:
    match = f"tenant_id = {_TENANT}"
    allowed = f"{match} OR {_SYSTEM}" if system_scope else match
    op.execute(f"ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE public.{table} FORCE ROW LEVEL SECURITY")
    op.execute(f"CREATE POLICY mdarix_tenant_isolation ON public.{table} USING ({allowed}) WITH CHECK ({allowed})")
    op.execute(_GRANT.format(table=table))


def _number(table: str) -> None:
    """Business ids: the md26 assigning function on insert, unique per organization, never changed afterwards."""
    item = NUMBERED[table]
    op.execute(f"CREATE UNIQUE INDEX {item.index_name} ON public.{table} (tenant_id, business_id)")
    op.execute(
        f"CREATE TRIGGER {item.trigger_name} BEFORE INSERT ON public.{table} FOR EACH ROW "
        f"EXECUTE FUNCTION public.mdarix_assign_business_id('{item.prefix}', '{item.scope}', '{WIDTH}')"
    )
    op.execute(
        f"CREATE TRIGGER {item.immutable_trigger_name} BEFORE UPDATE OF business_id ON public.{table} "
        "FOR EACH ROW WHEN (OLD.business_id IS NOT NULL AND OLD.business_id IS DISTINCT FROM NEW.business_id) "
        "EXECUTE FUNCTION public.mdarix_reject_immutable_identifier()"
    )


def _base(table: str) -> list:
    return [
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f(f"pk_{table}")),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], name=op.f(f"fk_{table}_tenant_id_tenants")),
    ]


def _now(name: str) -> sa.Column:
    return sa.Column(name, sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False)


def create_review_tables(system_scope: bool = True) -> None:
    """The three tables, their isolation and numbering (also used for legacy organization databases)."""
    op.create_table(
        "case_reviews",
        *_base("case_reviews"),
        sa.Column("business_id", sa.String(20), nullable=False),
        sa.Column("investigation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("review_type", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), server_default="REQUESTED", nullable=False),
        sa.Column("required_by_policy", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("policy_reasons", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("requested_by", sa.String(255), nullable=False),
        sa.Column("requested_role", sa.String(60)),
        sa.Column("request_reason", sa.Text()),
        sa.Column("reviewer_user_id", postgresql.UUID(as_uuid=True)),
        sa.Column("reviewer_role", sa.String(60)),
        sa.Column("outcome", sa.String(60)),
        sa.Column("rationale", sa.Text()),
        sa.Column("assessed", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("scope_version", sa.Integer()),
        sa.Column("brief_version_id", postgresql.UUID(as_uuid=True)),
        sa.Column("due_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("superseded_reason", sa.Text()),
        _now("created_at"),
        _now("updated_at"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_case_reviews_tenant_id_id"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "investigation_id"],
            ["investigations.tenant_id", "investigations.id"],
            name="fk_case_reviews_investigation",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(f"review_type IN ({_quoted(REVIEW_TYPES)})", name=op.f("ck_case_reviews_review_type_known")),
        sa.CheckConstraint(f"status IN ({_quoted(REVIEW_STATUSES)})", name=op.f("ck_case_reviews_status_known")),
        sa.CheckConstraint(
            f"outcome IS NULL OR outcome IN ({_quoted(OUTCOMES)})", name=op.f("ck_case_reviews_outcome_known")
        ),
    )
    op.create_index("ix_case_reviews_tenant_case", "case_reviews", ["tenant_id", "investigation_id"])
    op.create_index("ix_case_reviews_tenant_status", "case_reviews", ["tenant_id", "review_type", "status"])
    _tenant_policy("case_reviews", system_scope)
    _number("case_reviews")

    op.create_table(
        "decision_brief_versions",
        *_base("decision_brief_versions"),
        sa.Column("business_id", sa.String(20), nullable=False),
        sa.Column("investigation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(30), server_default="DRAFT", nullable=False),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("content", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("narrative", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("readiness", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("content_hash", sa.String(64)),
        sa.Column("scope_version", sa.Integer()),
        sa.Column("source_ai_brief_id", postgresql.UUID(as_uuid=True)),
        sa.Column("created_by", sa.String(255), nullable=False),
        sa.Column("created_role", sa.String(60)),
        sa.Column("submitted_by", sa.String(255)),
        sa.Column("submitted_at", sa.DateTime(timezone=True)),
        sa.Column("reviewed_by", sa.String(255)),
        sa.Column("reviewed_at", sa.DateTime(timezone=True)),
        _now("created_at"),
        _now("updated_at"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_decision_brief_versions_tenant_id_id"),
        sa.UniqueConstraint("tenant_id", "investigation_id", "version", name="uq_decision_brief_versions_version"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "investigation_id"],
            ["investigations.tenant_id", "investigations.id"],
            name="fk_decision_brief_versions_investigation",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            f"status IN ({_quoted(BRIEF_STATUSES)})", name=op.f("ck_decision_brief_versions_status_known")
        ),
    )
    op.create_index("ix_decision_brief_versions_tenant_status", "decision_brief_versions", ["tenant_id", "status"])
    _tenant_policy("decision_brief_versions", system_scope)
    _number("decision_brief_versions")

    op.create_table(
        "brief_review_actions",
        *_base("brief_review_actions"),
        sa.Column("brief_version_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("investigation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("action", sa.String(40), nullable=False),
        sa.Column("comment", sa.Text()),
        sa.Column("actor_ref", sa.String(255), nullable=False),
        sa.Column("actor_role", sa.String(60)),
        _now("created_at"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "brief_version_id"],
            ["decision_brief_versions.tenant_id", "decision_brief_versions.id"],
            name="fk_brief_review_actions_brief",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            f"action IN ({_quoted(QUALITY_ACTIONS)})", name=op.f("ck_brief_review_actions_action_known")
        ),
    )
    op.create_index("ix_brief_review_actions_tenant_brief", "brief_review_actions", ["tenant_id", "brief_version_id"])
    _tenant_policy("brief_review_actions", system_scope)


def _registry_present(connection) -> bool:
    return bool(connection.execute(sa.text("SELECT to_regclass('md_master.business_id_prefix') IS NOT NULL")).scalar())


def upgrade():
    create_review_tables()
    connection = op.get_bind()
    if _registry_present(connection):
        for item in NUMBERED.values():
            sequence = f"seq_business_id_{item.prefix.lower()}"
            op.execute(f"CREATE SEQUENCE IF NOT EXISTS md_master.{sequence}")
            op.execute(
                f"""
                INSERT INTO md_master.business_id_prefix (prefix, entity_name, sequence_name, id_width, owning_schema)
                VALUES ('{item.prefix}', '{item.entity}', '{sequence}', {WIDTH}, 'md_transaction')
                ON CONFLICT (prefix) DO UPDATE SET id_width = {WIDTH}
                """
            )


def downgrade():
    # Prefixes are permanent (md_master.protect_prefix_registry refuses removal); re-applying reuses them.
    for item in NUMBERED.values():
        op.execute(f"DELETE FROM public.{COUNTER_TABLE} WHERE prefix = '{item.prefix}'")
    for table in TABLES:
        op.drop_table(table)
