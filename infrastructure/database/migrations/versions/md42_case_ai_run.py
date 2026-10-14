"""The case's one AI run: ``case_ai_runs`` (each run of the case's AI analysis in one pass, its trigger and the
outcome of each step). Tenant-isolated (FORCE row-level security) like md41's tables. The model is in
backend/app/db/models/case_ai.py. Legacy dedicated organization databases get the same table from
scripts/add_workflow_tables_to_legacy_planes.py, which runs this module's ``create_case_ai_run_table``.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from infrastructure.database.migrations.helpers import tenant_policy as _tenant_policy

revision = "md42caseairun"
down_revision = "md41reportingcapa"
branch_labels = None
depends_on = None


def create_case_ai_run_table(system_scope: bool = True) -> None:
    """The table, its index and its isolation (also used for legacy organization databases)."""
    op.create_table(
        "case_ai_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("investigation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(20), server_default="QUEUED", nullable=False),
        sa.Column("trigger", sa.String(20), server_default="MANUAL", nullable=False),
        sa.Column("as_of", sa.DateTime(timezone=True), nullable=False),
        sa.Column("steps", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("error", sa.Text()),
        sa.Column("requested_by", sa.String(255), nullable=False),
        sa.Column("requested_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_case_ai_runs")),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], name=op.f("fk_case_ai_runs_tenant_id_tenants")),
        sa.ForeignKeyConstraint(
            ["tenant_id", "investigation_id"],
            ["investigations.tenant_id", "investigations.id"],
            name="fk_case_ai_runs_investigation",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "status IN ('QUEUED', 'RUNNING', 'COMPLETED', 'PARTIAL', 'FAILED')",
            name=op.f("ck_case_ai_runs_status_known"),
        ),
        sa.CheckConstraint("trigger IN ('AUTO', 'MANUAL')", name=op.f("ck_case_ai_runs_trigger_known")),
    )
    op.create_index("ix_case_ai_runs_tenant_case", "case_ai_runs", ["tenant_id", "investigation_id", "requested_at"])
    _tenant_policy("case_ai_runs", system_scope)


def upgrade():
    create_case_ai_run_table()


def downgrade():
    op.drop_table("case_ai_runs")
