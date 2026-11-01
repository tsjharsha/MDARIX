"""Regulatory reference data (G2a, backend/app/regulatory_reference.py).

- ``products`` gains ``udi_di``, ``gmdn_code`` and ``gmdn_term``.
- ``product_registrations``: a product's registration in a market (FDA product code with 510(k)/PMA, EU or UK
  identifier with its notified or approved body, Health Canada licence, CDSCO licence, ARTG entry).
- ``market_responsible_parties``: the organization's responsible party in each market, by legal role.
- ``imdrf_codes``: IMDRF annex terms A-G by release; reference data shared by every organization, loaded from IMDRF's
  files by scripts/load_imdrf_annex.py (the runtime role only reads it).
- ``imdrf_code_mappings``: the organization's own codes mapped to IMDRF codes, many-to-many, proposed and reviewed.
The organization tables are tenant-isolated.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from infrastructure.database.migrations.helpers import tenant_policy as _tenant_policy

revision = "md52regulatoryreference"
down_revision = "md51importlineage"
branch_labels = None
depends_on = None

MARKETS = "'US', 'EU', 'GB', 'NI', 'CA', 'IN', 'AU'"
ROLES = "'MANUFACTURER', 'IMPORTER', 'AUTHORISED_REPRESENTATIVE', 'UK_RESPONSIBLE_PERSON', 'SPONSOR', 'LICENCE_HOLDER'"
RUNTIME_READS_IMDRF = (
    "DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'mdarix_runtime') THEN "
    "GRANT SELECT ON public.imdrf_codes TO mdarix_runtime; END IF; END $$;"
)


def _id():
    return sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False)


def _tenant():
    return sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False)


def _when(name, nullable=False):
    return sa.Column(name, sa.DateTime(timezone=True), nullable=nullable)


def upgrade():
    op.add_column("products", sa.Column("udi_di", sa.String(80)))
    op.add_column("products", sa.Column("gmdn_code", sa.String(10)))
    op.add_column("products", sa.Column("gmdn_term", sa.String(300)))

    op.create_table(
        "product_registrations",
        _id(),
        _tenant(),
        sa.Column("product_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("market", sa.String(4), nullable=False),
        sa.Column("registration_type", sa.String(40), nullable=False),
        sa.Column("registration_number", sa.String(120), nullable=False),
        sa.Column("product_code", sa.String(20)),
        sa.Column("body_name", sa.String(200)),
        sa.Column("body_number", sa.String(20)),
        _when("created_at"),
        _when("updated_at"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_product_registrations")),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], name=op.f("fk_product_registrations_tenant_id_tenants")),
        sa.ForeignKeyConstraint(
            ["tenant_id", "product_id"],
            ["products.tenant_id", "products.id"],
            name="fk_product_registrations_product",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("tenant_id", "product_id", "market", "registration_number", name="uq_product_registration"),
        sa.CheckConstraint(f"market IN ({MARKETS})", name="product_registration_market_known"),
    )
    op.create_index("ix_product_registrations_product", "product_registrations", ["tenant_id", "product_id"])
    _tenant_policy("product_registrations")

    op.create_table(
        "market_responsible_parties",
        _id(),
        _tenant(),
        sa.Column("market", sa.String(4), nullable=False),
        sa.Column("role", sa.String(40), nullable=False),
        sa.Column("organisation", sa.String(200), nullable=False),
        sa.Column("address", sa.Text()),
        sa.Column("contact_name", sa.String(200)),
        sa.Column("contact_email", sa.String(254)),
        sa.Column("contact_phone", sa.String(40)),
        _when("created_at"),
        _when("updated_at"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_market_responsible_parties")),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name=op.f("fk_market_responsible_parties_tenant_id_tenants")
        ),
        sa.UniqueConstraint("tenant_id", "market", "role", name="uq_market_responsible_party"),
        sa.CheckConstraint(f"market IN ({MARKETS})", name="responsible_party_market_known"),
        sa.CheckConstraint(f"role IN ({ROLES})", name="responsible_party_role_known"),
    )
    _tenant_policy("market_responsible_parties")

    op.create_table(
        "imdrf_codes",
        _id(),
        sa.Column("release", sa.String(20), nullable=False),
        sa.Column("annex", sa.String(1), nullable=False),
        sa.Column("code", sa.String(20), nullable=False),
        sa.Column("term", sa.String(300), nullable=False),
        sa.Column("definition", sa.Text()),
        sa.Column("parent_code", sa.String(20)),
        _when("loaded_at"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_imdrf_codes")),
        sa.UniqueConstraint("release", "annex", "code", name="uq_imdrf_code"),
        sa.CheckConstraint("annex IN ('A', 'B', 'C', 'D', 'E', 'F', 'G')", name="imdrf_code_annex_known"),
    )
    # Shared reference data: the runtime role reads it; only the loader (the database owner) writes it.
    op.execute(RUNTIME_READS_IMDRF)

    op.create_table(
        "imdrf_code_mappings",
        _id(),
        _tenant(),
        sa.Column("customer_system", sa.String(80), nullable=False),
        sa.Column("customer_code", sa.String(120), nullable=False),
        sa.Column("customer_term", sa.String(300)),
        sa.Column("release", sa.String(20), nullable=False),
        sa.Column("annex", sa.String(1), nullable=False),
        sa.Column("imdrf_code", sa.String(20), nullable=False),
        sa.Column("status", sa.String(20), server_default="PROPOSED", nullable=False),
        sa.Column("proposed_by", sa.String(120), nullable=False),
        _when("proposed_at"),
        sa.Column("reviewed_by", sa.String(120)),
        _when("reviewed_at", nullable=True),
        sa.Column("review_note", sa.Text()),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_imdrf_code_mappings")),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], name=op.f("fk_imdrf_code_mappings_tenant_id_tenants")),
        sa.UniqueConstraint(
            "tenant_id", "customer_system", "customer_code", "release", "annex", "imdrf_code", name="uq_imdrf_mapping"
        ),
        sa.CheckConstraint("status IN ('PROPOSED', 'APPROVED', 'REJECTED')", name="imdrf_mapping_status_known"),
    )
    op.create_index("ix_imdrf_mappings_code", "imdrf_code_mappings", ["tenant_id", "customer_system", "customer_code"])
    _tenant_policy("imdrf_code_mappings")


def downgrade():
    op.drop_index("ix_imdrf_mappings_code", table_name="imdrf_code_mappings")
    op.drop_table("imdrf_code_mappings")
    op.drop_table("imdrf_codes")
    op.drop_table("market_responsible_parties")
    op.drop_index("ix_product_registrations_product", table_name="product_registrations")
    op.drop_table("product_registrations")
    op.drop_column("products", "gmdn_term")
    op.drop_column("products", "gmdn_code")
    op.drop_column("products", "udi_di")
