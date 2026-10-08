"""Tenant cells and their licences (ADR-014).

``cells`` is the platform's registry of each customer's tenant cell: where it runs, its enrollment, what it last
reported. ``cell_licences`` is written in the cell when a signed licence is applied (backend/app/cell_licence.py).
Both are organization-owned rows and get the same forced row-level security as every other tenant table (md05).
A MULTI deployment holds both; a cell holds its own licences and no ``cells`` rows; the platform holds ``cells``.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "md36cellsandlicences"
down_revision = "md35supportrequester"
branch_labels = None
depends_on = None

_TENANT = "NULLIF(current_setting('app.tenant_id', true), '')::uuid"
_SYSTEM = "(SELECT public.mdarix_system_scope())"
_GRANT = (
    "DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'mdarix_runtime') THEN "
    "GRANT SELECT, INSERT, UPDATE, DELETE ON public.{table} TO mdarix_runtime; END IF; END $$;"
)


def _tenant_policy(table: str) -> None:
    allowed = f"tenant_id = {_TENANT} OR {_SYSTEM}"
    op.execute(f"ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE public.{table} FORCE ROW LEVEL SECURITY")
    op.execute(f"CREATE POLICY mdarix_tenant_isolation ON public.{table} USING ({allowed}) WITH CHECK ({allowed})")
    op.execute(_GRANT.format(table=table))


def upgrade():
    op.create_table(
        "cells",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("hosting_mode", sa.String(40), nullable=False),
        sa.Column("public_endpoint", sa.String(500)),
        sa.Column("enrollment_token_hash", sa.String(64)),
        sa.Column("enrolled_at", sa.DateTime(timezone=True)),
        sa.Column("client_certificate_fingerprint", sa.String(128)),
        sa.Column("software_version", sa.String(80)),
        sa.Column("schema_version", sa.String(80)),
        sa.Column("last_heartbeat_at", sa.DateTime(timezone=True)),
        sa.Column("health", sa.String(30)),
        sa.Column("status", sa.String(30), nullable=False, server_default="PROVISIONING"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("tenant_id", name="uq_cells_tenant"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_cells_tenant_id"),
        sa.CheckConstraint(
            "hosting_mode in ('MDARIX_MANAGED','CUSTOMER_CLOUD','CUSTOMER_ON_PREM')", name="cell_hosting_mode_allowed"
        ),
        sa.CheckConstraint("status in ('PROVISIONING','ACTIVE','SUSPENDED','RETIRED')", name="cell_status_allowed"),
    )
    op.create_table(
        "cell_licences",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("content_sha256", sa.String(64), nullable=False, unique=True),
        sa.Column("key_id", sa.String(80), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_until", sa.DateTime(timezone=True)),
        sa.Column("applied_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("envelope", postgresql.JSONB, nullable=False),
        sa.UniqueConstraint("tenant_id", "id", name="uq_cell_licences_tenant_id"),
    )
    _tenant_policy("cells")
    _tenant_policy("cell_licences")


def downgrade():
    op.drop_table("cell_licences")
    op.drop_table("cells")
