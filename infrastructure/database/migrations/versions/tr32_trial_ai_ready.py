"""AI ready, switched off (AI-R) and AI for free trials on sample data (owner amendment, 14 Nov 2026).

The thirty-second migration of the trial line, built on ``tr31othercountries`` and re-attached after ``trrcatools``
(root-cause tools) when both joined the demo line, under the one-head rule. Expand-only: two new tables and
two new columns with defaults. Nothing is dropped or renamed; no data step.

- ``tenants.ai_features``: the organization's per-feature AI switches (``{"ask": true}``), off when absent. Only known
  feature keys and boolean values are accepted (genai/features.py).
- ``auth_users.ai_access``: the person's own AI flag, ``ACTIVE`` (default, also for every existing person) or
  ``INACTIVE``; set by a Platform Administrator only. It applies to free trials only (genai/governance.py).
- ``ai_calls``: one row per request sent to a model (backend/app/db/models/ai_records.py).
- ``ai_output_reviews``: a person's accept, edit or reject decision on an AI output.

Both new tables get the forced organization row-level policy and are append-only (a trigger refuses UPDATE and
DELETE, as for audit_events). The downgrade refuses while ``ai_calls`` holds rows: call records are audit records.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from infrastructure.database.migrations.helpers import quoted
from infrastructure.database.migrations.helpers import tenant_policy as _tenant_policy

revision = "tr32aiready"
down_revision = "trrcatools"
branch_labels = None
depends_on = None

FEATURE_KEYS = (
    "ask",
    "summaries",
    "case_analysis",
    "drafting",
    "evidence_extraction",
    "code_suggestions",
    "decision_advisory",
    "regulatory_drafting",
)
NEW_TABLES = ("ai_calls", "ai_output_reviews")
OUTCOMES = ("ANSWERED", "FAILED", "INVALID_OUTPUT")
DECISIONS = ("ACCEPTED", "EDITED", "REJECTED")
APPEND_ONLY_FUNCTION = "mdarix_reject_ai_record_mutation"


def _tz(name: str, nullable: bool = True) -> sa.Column:
    return sa.Column(name, sa.DateTime(timezone=True), nullable=nullable)


def _jsonb(name: str, default: str) -> sa.Column:
    return sa.Column(name, postgresql.JSONB(), nullable=False, server_default=sa.text(f"'{default}'::jsonb"))


def _common(table: str) -> list:
    return [
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f(f"pk_{table}")),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], name=op.f(f"fk_{table}_tenant_id_tenants")),
        sa.UniqueConstraint("tenant_id", "id", name=f"uq_{table}_tenant_id_id"),
    ]


def _integer(name: str) -> sa.Column:
    return sa.Column(name, sa.Integer(), nullable=False, server_default=sa.text("0"))


def _columns() -> None:
    op.add_column("tenants", _jsonb("ai_features", "{}"))
    op.create_check_constraint(
        "ck_tenants_ai_features_known",
        "tenants",
        "jsonb_typeof(ai_features) = 'object' "
        f"AND (ai_features - ARRAY[{quoted(FEATURE_KEYS)}]) = '{{}}'::jsonb "
        "AND NOT jsonb_path_exists(ai_features, '$.* ? (@.type() != \"boolean\")')",
    )
    op.add_column(
        "auth_users", sa.Column("ai_access", sa.String(10), nullable=False, server_default=sa.text("'ACTIVE'"))
    )
    op.create_check_constraint("ck_auth_users_ai_access_known", "auth_users", "ai_access IN ('ACTIVE', 'INACTIVE')")


def _calls() -> None:
    table = "ai_calls"
    op.create_table(
        table,
        *_common(table),
        sa.Column("user_ref", sa.String(255)),
        sa.Column("feature", sa.String(40), nullable=False),
        sa.Column("risk", sa.String(10), nullable=False),
        sa.Column("prompt_version", sa.String(80), nullable=False),
        sa.Column("prompt_sha256", sa.String(64), nullable=False),
        sa.Column("content_sha256", sa.String(64), nullable=False),
        sa.Column("provider", sa.String(40)),
        sa.Column("model", sa.String(200)),
        sa.Column("model_version", sa.String(120)),
        sa.Column("upstream_provider", sa.String(80)),
        sa.Column("upstream_model", sa.String(200)),
        sa.Column("region", sa.String(80)),
        sa.Column("configuration_version", sa.String(80), nullable=False),
        sa.Column("retrieval_policy_version", sa.String(80)),
        sa.Column("organisation_type", sa.String(10), nullable=False),
        sa.Column("chain", sa.String(10), nullable=False),
        sa.Column("chain_position", sa.Integer()),
        _jsonb("attempts", "[]"),
        _jsonb("records", "[]"),
        _integer("input_tokens"),
        _integer("output_tokens"),
        _integer("thinking_tokens"),
        _integer("latency_ms"),
        sa.Column("outcome", sa.String(20), nullable=False),
        sa.Column("output_text", sa.Text()),
        sa.Column("output_sha256", sa.String(64)),
        _tz("created_at", False),
        sa.CheckConstraint(f"outcome IN ({quoted(OUTCOMES)})", name="ck_ai_calls_outcome_known"),
        sa.CheckConstraint("organisation_type IN ('TRIAL', 'PAID')", name="ck_ai_calls_type_known"),
        sa.CheckConstraint("chain IN ('trial', 'paid')", name="ck_ai_calls_chain_known"),
        sa.CheckConstraint("risk IN ('LOW', 'MEDIUM')", name="ck_ai_calls_risk_allowed"),
        sa.CheckConstraint(
            "(outcome = 'ANSWERED') = (output_sha256 IS NOT NULL)", name="ck_ai_calls_output_when_answered"
        ),
    )
    op.create_index("ix_ai_calls_tenant_feature_created", table, ["tenant_id", "feature", "created_at"])


def _reviews() -> None:
    table = "ai_output_reviews"
    op.create_table(
        table,
        *_common(table),
        sa.Column("ai_call_id", postgresql.UUID(as_uuid=True)),
        sa.Column("subject_type", sa.String(60), nullable=False),
        sa.Column("subject_id", sa.String(120), nullable=False),
        sa.Column("decision", sa.String(10), nullable=False),
        sa.Column("edited_text", sa.Text()),
        sa.Column("edited_text_sha256", sa.String(64)),
        sa.Column("reason", sa.Text()),
        sa.Column("reviewer", sa.String(255), nullable=False),
        _tz("created_at", False),
        sa.ForeignKeyConstraint(
            ["tenant_id", "ai_call_id"], ["ai_calls.tenant_id", "ai_calls.id"], name="fk_ai_output_reviews_call"
        ),
        sa.CheckConstraint(f"decision IN ({quoted(DECISIONS)})", name="ck_ai_output_reviews_decision_known"),
        sa.CheckConstraint(
            "decision <> 'EDITED' OR (edited_text IS NOT NULL AND edited_text_sha256 IS NOT NULL "
            "AND reason IS NOT NULL)",
            name="ck_ai_output_reviews_edit_complete",
        ),
        sa.CheckConstraint("decision <> 'REJECTED' OR reason IS NOT NULL", name="ck_ai_output_reviews_reject_reason"),
    )
    op.create_index(
        "ix_ai_output_reviews_tenant_subject", table, ["tenant_id", "subject_type", "subject_id", "created_at"]
    )
    op.create_index("ix_ai_output_reviews_tenant_call", table, ["tenant_id", "ai_call_id"])


def _append_only() -> None:
    op.execute(
        f"""
        CREATE OR REPLACE FUNCTION public.{APPEND_ONLY_FUNCTION}() RETURNS trigger AS $$
        BEGIN
          -- The organization's purge (backend/app/tenant_purge.py, system scope, organization PURGING) removes them
          -- with the rest of its data; nothing else may change or delete a row.
          IF TG_OP = 'DELETE'
             AND (SELECT public.mdarix_system_scope())
             AND EXISTS (SELECT 1 FROM public.tenants WHERE id = OLD.tenant_id AND status = 'PURGING') THEN
            RETURN OLD;
          END IF;
          RAISE EXCEPTION '% is append-only', TG_TABLE_NAME;
        END;
        $$ LANGUAGE plpgsql
        """
    )
    for table in NEW_TABLES:
        op.execute(
            f"CREATE TRIGGER {table}_append_only BEFORE UPDATE OR DELETE ON public.{table} "
            f"FOR EACH ROW EXECUTE FUNCTION public.{APPEND_ONLY_FUNCTION}()"
        )


def add_ai_ready(system_scope: bool = True) -> None:
    """Every change of this migration (also usable for a legacy organization database)."""
    _columns()
    _calls()
    _reviews()
    for table in NEW_TABLES:
        _tenant_policy(table, system_scope)
    _append_only()


def upgrade():
    add_ai_ready()


def downgrade():
    rows = op.get_bind().execute(sa.text("SELECT count(*) FROM ai_calls")).scalar()
    if rows:
        raise RuntimeError(f"ai_calls holds {rows} call records; they are audit records and are not dropped silently")
    for table in reversed(NEW_TABLES):
        op.execute(f"DROP TRIGGER IF EXISTS {table}_append_only ON public.{table}")
        op.drop_table(table)
    op.execute(f"DROP FUNCTION IF EXISTS public.{APPEND_ONLY_FUNCTION}()")
    op.drop_constraint("ck_auth_users_ai_access_known", "auth_users", type_="check")
    op.drop_column("auth_users", "ai_access")
    op.drop_constraint("ck_tenants_ai_features_known", "tenants", type_="check")
    op.drop_column("tenants", "ai_features")
