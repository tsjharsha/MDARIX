"""Import of every business record the customer systems hold, and connectors that keep their own API key.

- complaints: the regulatory details the quality system records (severity, country, reporter and complaint type,
  problem code, serial number, UDI, awareness date, device returned, patient involved, serious injury, death,
  malfunction). All nullable: existing complaints are unchanged.
- capas: corrective and preventive actions, tenant-owned with the same row-level security as every tenant table.
- lot_components.component_lot_identifier: which lot of the component went into the product lot (genealogy).
- connector_configurations.credential_*: the customer system's API key, encrypted, so a connector no longer needs a
  server environment variable per customer.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "md10businessimport"
down_revision = "md09tenantlimits"
branch_labels = None
depends_on = None

_TENANT = "NULLIF(current_setting('app.tenant_id', true), '')::uuid"
_SYSTEM = "current_setting('app.rls_bypass', true) = 'on'"
COMPLAINT_TEXT = {
    "severity": 40,
    "country": 80,
    "reporter_type": 80,
    "complaint_type": 80,
    "problem_code": 120,
    "serial_number": 120,
    "udi": 120,
}
COMPLAINT_FLAGS = ("device_returned", "patient_involved", "serious_injury", "death", "malfunction")


def _tz(name: str, nullable: bool = True) -> sa.Column:
    return sa.Column(name, sa.DateTime(timezone=True), nullable=nullable)


def upgrade() -> None:
    for name, length in COMPLAINT_TEXT.items():
        op.add_column("complaints", sa.Column(name, sa.String(length), nullable=True))
    op.add_column("complaints", _tz("awareness_timestamp"))
    for name in COMPLAINT_FLAGS:
        op.add_column("complaints", sa.Column(name, sa.Boolean(), nullable=True))

    op.create_table(
        "capas",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("source_record_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("source_records.id")),
        sa.Column("source_system", sa.String(120)),
        sa.Column("source_identifier", sa.String(255)),
        _tz("source_timestamp"),
        _tz("effective_timestamp"),
        _tz("recorded_timestamp"),
        _tz("ingestion_timestamp"),
        _tz("created_at", False),
        _tz("updated_at", False),
        sa.Column("capa_identifier", sa.String(120), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("action_type", sa.String(40)),
        sa.Column("source_type", sa.String(80)),
        sa.Column("source_reference", sa.String(120)),
        sa.Column("product_id", postgresql.UUID(as_uuid=True)),
        sa.Column("investigation_id", postgresql.UUID(as_uuid=True)),
        sa.Column("status", sa.String(40), nullable=False, server_default="open"),
        _tz("opened_at"),
        _tz("due_at"),
        _tz("effectiveness_check_at"),
        sa.ForeignKeyConstraint(["tenant_id", "product_id"], ["products.tenant_id", "products.id"]),
        sa.ForeignKeyConstraint(["tenant_id", "investigation_id"], ["investigations.tenant_id", "investigations.id"]),
        sa.UniqueConstraint("tenant_id", "capa_identifier", name="uq_capas_tenant_identifier"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_capas_tenant_id_id"),
    )
    op.create_index("ix_capas_tenant_product", "capas", ["tenant_id", "product_id"])
    op.execute("ALTER TABLE public.capas ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE public.capas FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY mdarix_tenant_isolation ON public.capas "
        f"USING (tenant_id = {_TENANT} OR {_SYSTEM}) WITH CHECK (tenant_id = {_TENANT} OR {_SYSTEM})"
    )
    op.execute(
        "DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'mdarix_runtime') THEN "
        "GRANT SELECT, INSERT, UPDATE, DELETE ON public.capas TO mdarix_runtime; END IF; END $$;"
    )

    op.add_column("lot_components", sa.Column("component_lot_identifier", sa.String(120), nullable=True))

    op.add_column("connector_configurations", sa.Column("credential_encrypted", sa.Text(), nullable=True))
    op.add_column("connector_configurations", sa.Column("credential_hint", sa.String(8), nullable=True))
    op.add_column("connector_configurations", _tz("credential_set_at"))


def downgrade() -> None:
    for name in ("credential_set_at", "credential_hint", "credential_encrypted"):
        op.drop_column("connector_configurations", name)
    op.drop_column("lot_components", "component_lot_identifier")
    op.drop_index("ix_capas_tenant_product", table_name="capas")
    op.drop_table("capas")
    for name in (*COMPLAINT_FLAGS, "awareness_timestamp", *COMPLAINT_TEXT):
        op.drop_column("complaints", name)
