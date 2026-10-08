"""Human decision (Phase 6): the signed decision on an approved Decision Brief, its follow-up actions, and impact
assessments for evidence that arrives after signing.

- ``decisions``: ``decision_kind`` (LEGACY for every existing row, BRIEF for the new signed decisions), the brief
  version and its content hash, outcome, conditions, follow-up actions, residual unknowns, who decided under which role
  and authority, the evidence-set hash, context snapshot, AI executions referred to, and the supersede chain. Existing
  decisions are unchanged.
- ``decision_follow_ups`` (FUP000001 per organization) and ``impact_assessments`` (IMP000001 per organization),
  numbered by the business-id trigger of md26; tenant-isolated.
The models are in backend/app/db/models/{foundation,decision_outcomes}.py. Legacy dedicated organization databases get
the same changes from scripts/add_workflow_tables_to_legacy_planes.py, which runs ``apply_decision_changes``.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from infrastructure.database.migrations.helpers import quoted as _quoted
from infrastructure.database.migrations.helpers import register_prefixes
from infrastructure.database.migrations.helpers import tenant_policy as _tenant_policy

from infrastructure.database.migrations.business_ids import COUNTER_TABLE, LATER_OBJECTS, WIDTH

revision = "md33humandecision"
down_revision = "md32reviewsbrief"
branch_labels = None
depends_on = None

OUTCOMES = ("ACCEPT_CONCLUSION", "ACCEPT_WITH_CONDITIONS", "REJECT_CONCLUSION", "CLOSE_NO_FURTHER_ACTION")
FOLLOW_UP_ACTIONS = (
    "CAPA_REQUIRED",
    "PRODUCT_CHANGE_REQUIRED",
    "FIELD_ACTION_REVIEW_REQUIRED",
    "RISK_REASSESSMENT_REQUIRED",
    "REGULATORY_ACTION_REQUIRED",
)
FOLLOW_UP_STATUSES = ("OPEN", "IN_PROGRESS", "DONE", "CANCELLED")
NUMBERED = {item.table: item for item in LATER_OBJECTS if item.table in ("decision_follow_ups", "impact_assessments")}
DECISION_COLUMNS = (
    "decision_kind",
    "brief_version_id",
    "outcome",
    "conditions",
    "follow_up_actions",
    "residual_unknowns",
    "decided_by_user_id",
    "decided_under_role",
    "approval_authority_id",
    "decided_at",
    "brief_content_hash",
    "evidence_set_hash",
    "context_snapshot_id",
    "ai_execution_refs",
    "supersedes_decision_id",
    "superseded_by_decision_id",
    "superseded_at",
    "supersede_reason",
)


def _number(table: str) -> None:
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


def _now(name: str) -> sa.Column:
    return sa.Column(name, sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False)


def apply_decision_changes(system_scope: bool = True) -> None:
    """Every change of this migration (also used for legacy organization databases)."""
    op.add_column("decisions", sa.Column("decision_kind", sa.String(20), server_default="LEGACY", nullable=False))
    op.add_column("decisions", sa.Column("brief_version_id", postgresql.UUID(as_uuid=True)))
    op.add_column("decisions", sa.Column("outcome", sa.String(40)))
    op.add_column("decisions", sa.Column("conditions", sa.Text()))
    op.add_column(
        "decisions",
        sa.Column("follow_up_actions", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False),
    )
    op.add_column(
        "decisions",
        sa.Column("residual_unknowns", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False),
    )
    op.add_column("decisions", sa.Column("decided_by_user_id", postgresql.UUID(as_uuid=True)))
    op.add_column("decisions", sa.Column("decided_under_role", sa.String(60)))
    op.add_column("decisions", sa.Column("approval_authority_id", postgresql.UUID(as_uuid=True)))
    op.add_column("decisions", sa.Column("decided_at", sa.DateTime(timezone=True)))
    op.add_column("decisions", sa.Column("brief_content_hash", sa.String(64)))
    op.add_column("decisions", sa.Column("evidence_set_hash", sa.String(64)))
    op.add_column("decisions", sa.Column("context_snapshot_id", postgresql.UUID(as_uuid=True)))
    op.add_column(
        "decisions",
        sa.Column("ai_execution_refs", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False),
    )
    op.add_column("decisions", sa.Column("supersedes_decision_id", postgresql.UUID(as_uuid=True)))
    op.add_column("decisions", sa.Column("superseded_by_decision_id", postgresql.UUID(as_uuid=True)))
    op.add_column("decisions", sa.Column("superseded_at", sa.DateTime(timezone=True)))
    op.add_column("decisions", sa.Column("supersede_reason", sa.Text()))
    op.create_check_constraint(
        op.f("ck_decisions_decision_kind_known"), "decisions", "decision_kind IN ('LEGACY', 'BRIEF')"
    )
    op.create_check_constraint(
        op.f("ck_decisions_outcome_known"), "decisions", f"outcome IS NULL OR outcome IN ({_quoted(OUTCOMES)})"
    )

    op.create_table(
        "decision_follow_ups",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("business_id", sa.String(20), nullable=False),
        sa.Column("decision_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("investigation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("action_type", sa.String(40), nullable=False),
        sa.Column("title", sa.String(300), nullable=False),
        sa.Column("assignee_user_id", postgresql.UUID(as_uuid=True)),
        sa.Column("assigned_role", sa.String(60)),
        sa.Column("due_at", sa.DateTime(timezone=True)),
        sa.Column("status", sa.String(20), server_default="OPEN", nullable=False),
        sa.Column("task_id", postgresql.UUID(as_uuid=True)),
        sa.Column("capa_id", postgresql.UUID(as_uuid=True)),
        sa.Column("completion_note", sa.Text()),
        sa.Column("completed_by", sa.String(255)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("created_by", sa.String(255), nullable=False),
        _now("created_at"),
        _now("updated_at"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_decision_follow_ups")),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], name=op.f("fk_decision_follow_ups_tenant_id_tenants")),
        sa.ForeignKeyConstraint(
            ["tenant_id", "decision_id"],
            ["decisions.tenant_id", "decisions.id"],
            name="fk_decision_follow_ups_decision",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            f"action_type IN ({_quoted(FOLLOW_UP_ACTIONS)})", name=op.f("ck_decision_follow_ups_action_type_known")
        ),
        sa.CheckConstraint(
            f"status IN ({_quoted(FOLLOW_UP_STATUSES)})", name=op.f("ck_decision_follow_ups_status_known")
        ),
    )
    op.create_index("ix_decision_follow_ups_tenant_case", "decision_follow_ups", ["tenant_id", "investigation_id"])
    _tenant_policy("decision_follow_ups", system_scope)
    _number("decision_follow_ups")

    op.create_table(
        "impact_assessments",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("business_id", sa.String(20), nullable=False),
        sa.Column("investigation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("decision_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("trigger", sa.String(40), nullable=False),
        sa.Column("evidence_id", postgresql.UUID(as_uuid=True)),
        sa.Column("status", sa.String(20), server_default="OPEN", nullable=False),
        sa.Column("conclusion", sa.String(20)),
        sa.Column("rationale", sa.Text()),
        sa.Column("assessed_by", sa.String(255)),
        sa.Column("assessed_role", sa.String(60)),
        sa.Column("assessed_at", sa.DateTime(timezone=True)),
        sa.Column("task_id", postgresql.UUID(as_uuid=True)),
        _now("created_at"),
        _now("updated_at"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_impact_assessments")),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], name=op.f("fk_impact_assessments_tenant_id_tenants")),
        sa.ForeignKeyConstraint(
            ["tenant_id", "investigation_id"],
            ["investigations.tenant_id", "investigations.id"],
            name="fk_impact_assessments_investigation",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint("status IN ('OPEN', 'COMPLETED')", name=op.f("ck_impact_assessments_status_known")),
        sa.CheckConstraint(
            "conclusion IS NULL OR conclusion IN ('NO_IMPACT', 'MATERIAL_IMPACT')",
            name=op.f("ck_impact_assessments_conclusion_known"),
        ),
    )
    op.create_index("ix_impact_assessments_tenant_case", "impact_assessments", ["tenant_id", "investigation_id"])
    _tenant_policy("impact_assessments", system_scope)
    _number("impact_assessments")


def upgrade():
    apply_decision_changes()
    register_prefixes(NUMBERED.values())


def downgrade():
    # Prefixes are permanent (md_master.protect_prefix_registry refuses removal); re-applying reuses them.
    for item in NUMBERED.values():
        op.execute(f"DELETE FROM public.{COUNTER_TABLE} WHERE prefix = '{item.prefix}'")
    op.drop_table("impact_assessments")
    op.drop_table("decision_follow_ups")
    for name in ("outcome_known", "decision_kind_known"):
        op.drop_constraint(op.f(f"ck_decisions_{name}"), "decisions", type_="check")
    for column in reversed(DECISION_COLUMNS):
        op.drop_column("decisions", column)
