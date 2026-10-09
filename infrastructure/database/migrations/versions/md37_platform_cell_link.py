"""The platform-cell link (ADR-014): enrollment credentials, heartbeats, packages.

- ``cells`` gains the cell's credential (hashed), the licence the platform last issued it, and its last heartbeat.
- ``cell_heartbeats``: every heartbeat a cell sent (metadata only; the API refuses free text).
- ``packages``: signed packages the platform offers (reference data, mapping templates, policies); global rows.
- ``cell_package_states``: what each cell reported about each package.
- ``received_packages``: in the cell, every package fetched and verified against the pinned platform key.
Organization-owned tables get the forced row-level-security policy every tenant table has (md05).
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "md37platformcelllink"
down_revision = "md36cellsandlicences"
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


def _uuid_pk():
    return sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()"))


def _tenant():
    return sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False)


def upgrade():
    op.add_column("cells", sa.Column("credential_hash", sa.String(64)))
    op.add_column("cells", sa.Column("licence_envelope", postgresql.JSONB))
    op.add_column("cells", sa.Column("last_heartbeat", postgresql.JSONB))
    op.create_table(
        "cell_heartbeats",
        _uuid_pk(),
        _tenant(),
        sa.Column("cell_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("cells.id"), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("software_version", sa.String(80)),
        sa.Column("schema_version", sa.String(80)),
        sa.Column("health", sa.String(30)),
        sa.Column("metrics", postgresql.JSONB, nullable=False),
        sa.UniqueConstraint("tenant_id", "id", name="uq_cell_heartbeats_tenant_id"),
    )
    op.create_table(
        "packages",
        _uuid_pk(),
        sa.Column("kind", sa.String(40), nullable=False),
        sa.Column("code", sa.String(120), nullable=False),
        sa.Column("version", sa.String(40), nullable=False),
        sa.Column("content_sha256", sa.String(64), nullable=False, unique=True),
        sa.Column("key_id", sa.String(80), nullable=False),
        sa.Column("envelope", postgresql.JSONB, nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default="RELEASED"),
        sa.Column("released_at", sa.DateTime(timezone=True)),
        sa.Column("released_by", sa.String(255)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("kind", "code", "version", name="uq_packages_kind_code_version"),
        sa.CheckConstraint("status in ('RELEASED','WITHDRAWN')", name="package_status_allowed"),
    )
    op.execute(_GRANT.format(table="packages"))
    op.create_table(
        "cell_package_states",
        _uuid_pk(),
        _tenant(),
        sa.Column("package_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("packages.id"), nullable=False),
        sa.Column("state", sa.String(30), nullable=False),
        sa.Column("reported_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("detail", postgresql.JSONB),
        sa.UniqueConstraint("tenant_id", "package_id", name="uq_cell_package_states_tenant_package"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_cell_package_states_tenant_id"),
    )
    op.create_table(
        "received_packages",
        _uuid_pk(),
        _tenant(),
        sa.Column("kind", sa.String(40), nullable=False),
        sa.Column("code", sa.String(120), nullable=False),
        sa.Column("version", sa.String(40), nullable=False),
        sa.Column("content_sha256", sa.String(64), nullable=False, unique=True),
        sa.Column("key_id", sa.String(80), nullable=False),
        sa.Column("envelope", postgresql.JSONB, nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("applied_at", sa.DateTime(timezone=True)),
        sa.Column("detail", postgresql.JSONB),
        sa.UniqueConstraint("tenant_id", "id", name="uq_received_packages_tenant_id"),
    )
    for table in ("cell_heartbeats", "cell_package_states", "received_packages"):
        _tenant_policy(table)


def downgrade():
    op.drop_table("received_packages")
    op.drop_table("cell_package_states")
    op.drop_table("packages")
    op.drop_table("cell_heartbeats")
    op.drop_column("cells", "last_heartbeat")
    op.drop_column("cells", "licence_envelope")
    op.drop_column("cells", "credential_hash")
