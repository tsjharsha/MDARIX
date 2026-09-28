"""Add durable tenant-scoped regulatory document versions."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "z43regulatorydocuments"
down_revision = "af48reportjobs"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "regulatory_documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("document_identifier", sa.String(120), nullable=False),
        sa.Column("document_type", sa.String(30), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default="DRAFT"),
        sa.Column("current_version", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("lock_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_by", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=False), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=False), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.UniqueConstraint("tenant_id", "document_identifier", name="uq_regulatory_document_tenant_identifier"),
    )
    op.create_index("ix_regulatory_documents_tenant_status", "regulatory_documents", ["tenant_id", "status"])
    op.create_table(
        "regulatory_document_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("content", postgresql.JSONB(), nullable=False),
        sa.Column("citations", postgresql.JSONB(), nullable=False),
        sa.Column("source_context", postgresql.JSONB(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default="DRAFT"),
        sa.Column("change_reason", sa.Text(), nullable=False),
        sa.Column("created_by", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=False), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.UniqueConstraint("tenant_id", "document_id", "version", name="uq_regulatory_document_version"),
    )
    op.create_index("ix_regulatory_document_versions_tenant_document", "regulatory_document_versions", ["tenant_id", "document_id", "version"])


def downgrade():
    op.drop_index("ix_regulatory_document_versions_tenant_document", table_name="regulatory_document_versions")
    op.drop_table("regulatory_document_versions")
    op.drop_index("ix_regulatory_documents_tenant_status", table_name="regulatory_documents")
    op.drop_table("regulatory_documents")
