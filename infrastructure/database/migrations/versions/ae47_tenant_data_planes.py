"""Add server-side tenant data-plane routing metadata."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "ae47tenantdataplanes"
down_revision = "ad46customertenant"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "tenant_data_planes",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("database_ref", sa.String(160), nullable=False),
        sa.Column("connection_secret_ref", sa.String(160), nullable=False),
        sa.Column("region", sa.String(80), nullable=False),
        sa.Column("residency_region", sa.String(80), nullable=False),
        sa.Column("schema_version", sa.String(80)),
        sa.Column("status", sa.String(30), server_default="PROVISIONING", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", name="uq_tenant_data_plane_tenant"),
        sa.UniqueConstraint("database_ref", name="uq_tenant_data_plane_database_ref"),
        sa.CheckConstraint("status in ('PROVISIONING','ACTIVE','SUSPENDED','FAILED','RETIRED')", name="tenant_data_plane_status_allowed"),
    )


def downgrade():
    op.drop_table("tenant_data_planes")
