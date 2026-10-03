"""Full data exports of one organization (backend/app/tenant_export.py).

A customer administrator (or a platform administrator, for offboarding) requests an export; the background worker
writes every table the organization has rows in and every stored file into one zip in object storage, with a
manifest of row counts and checksums. The zip can be downloaded for 7 days, then it is deleted.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "md19tenantexports"
down_revision = "md18auditchain"
branch_labels = None
depends_on = None

_TENANT = "NULLIF(current_setting('app.tenant_id', true), '')::uuid"
_SYSTEM = "(SELECT public.mdarix_system_scope())"


def upgrade():
    op.create_table(
        "tenant_exports",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("requested_by", sa.String(255), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="QUEUED"),
        sa.Column("object_key", sa.Text()),
        sa.Column("size_bytes", sa.BigInteger()),
        sa.Column("sha256", sa.String(64)),
        sa.Column("summary", postgresql.JSONB()),
        sa.Column("error", sa.String(200)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("expires_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_tenant_exports_tenant_created", "tenant_exports", ["tenant_id", "created_at"])
    op.execute("ALTER TABLE public.tenant_exports ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE public.tenant_exports FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY mdarix_tenant_isolation ON public.tenant_exports "
        f"USING (tenant_id = {_TENANT} OR {_SYSTEM}) WITH CHECK (tenant_id = {_TENANT} OR {_SYSTEM})"
    )
    op.execute(
        "DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'mdarix_runtime') THEN "
        "GRANT SELECT, INSERT, UPDATE, DELETE ON public.tenant_exports TO mdarix_runtime; END IF; END $$;"
    )


def downgrade():
    op.execute("DROP POLICY IF EXISTS mdarix_tenant_isolation ON public.tenant_exports")
    op.drop_index("ix_tenant_exports_tenant_created", table_name="tenant_exports")
    op.drop_table("tenant_exports")
