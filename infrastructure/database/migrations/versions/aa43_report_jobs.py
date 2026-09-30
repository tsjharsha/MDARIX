"""Persist tenant-scoped report jobs and artifact metadata."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "af48reportjobs"
down_revision = "ae47tenantdataplanes"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "report_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("actor_id", sa.String(255), nullable=False),
        sa.Column("report_code", sa.String(80), nullable=False),
        sa.Column("output_format", sa.String(12), nullable=False),
        sa.Column("context", postgresql.JSONB, nullable=False),
        sa.Column("hidden_fields", postgresql.JSONB, nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="QUEUED"),
        sa.Column("attempts", sa.Integer, nullable=False, server_default="0"),
        sa.Column("artifact_path", sa.Text),
        sa.Column("content_type", sa.String(120)),
        sa.Column("report_version", sa.String(40), nullable=False, server_default="1.0"),
        sa.Column("last_error", sa.String(120)),
        sa.Column("created_at", sa.DateTime(timezone=False), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=False), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
    )
    op.create_index("ix_report_jobs_tenant_status", "report_jobs", ["tenant_id", "status"])


def downgrade():
    op.drop_index("ix_report_jobs_tenant_status", table_name="report_jobs")
    op.drop_table("report_jobs")
