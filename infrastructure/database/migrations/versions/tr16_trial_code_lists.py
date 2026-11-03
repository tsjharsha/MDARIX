"""Code lists and product identity (release 0.10.77, Release C, part C5).

The sixteenth migration of the trial line, chained from ``tr15canadamarket`` (``tr03pmssources`` stays reserved for
proactive PMS); after the forward merge, ``mvp-1.0`` adds a merge revision joining its head and this one.

Expand-only: new nullable columns and two new tables; no existing row changes. The downgrade removes only what this
migration added.

- ``imdrf_codes.status`` and ``status_note``: the term's status as IMDRF's own file states it ("Retired (2025)",
  "Not selectable", "Modified (editorial)", ...) and its explanation. A retired code is never deleted: old reports
  keep it, the code picker no longer offers it.
- ``reference_codes``: the other published code lists, by list and version: FDA's CDRH adverse event codes with
  FDA's own IMDRF code per row (``FDA_CDRH``), FDA's product classification (``FDA_PRODUCT_CODE``) and the European
  Medical Device Nomenclature (``EMDN``). Shared reference data, loaded by scripts/load_code_lists.py from the
  publishers' files; the runtime role only reads it. GMDN is licensed and never loaded.
- ``code_list_files``: each file loaded, with its source, version, publication date, SHA-256 and row count.
- ``products.basic_udi_di`` and ``emdn_code``; ``product_registrations.risk_class`` (the class in that market);
  ``market_responsible_parties.srn`` (the EUDAMED single registration number).

The organization columns go with their rows, so retention, the purge and sample removal already take them. Legacy
dedicated organization databases get them from scripts/add_workflow_tables_to_legacy_planes.py, which runs
``add_identity_columns`` (the two shared tables live in the control database).
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "tr16codelists"
down_revision = "tr15canadamarket"
branch_labels = None
depends_on = None

LISTS = "'FDA_CDRH', 'FDA_PRODUCT_CODE', 'EMDN'"
RUNTIME_READS = (
    "DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'mdarix_runtime') THEN "
    "GRANT SELECT ON public.reference_codes, public.code_list_files TO mdarix_runtime; END IF; END $$;"
)


def add_identity_columns(system_scope: bool = True) -> None:
    """The organization tables' columns (also used for legacy organization databases; the tables keep their
    isolation)."""
    op.add_column("products", sa.Column("basic_udi_di", sa.String(120), nullable=True))
    op.add_column("products", sa.Column("emdn_code", sa.String(30), nullable=True))
    op.add_column("product_registrations", sa.Column("risk_class", sa.String(10), nullable=True))
    op.add_column("market_responsible_parties", sa.Column("srn", sa.String(40), nullable=True))


def upgrade():
    add_identity_columns()
    op.add_column("imdrf_codes", sa.Column("status", sa.String(60), nullable=True))
    op.add_column("imdrf_codes", sa.Column("status_note", sa.Text(), nullable=True))
    op.create_table(
        "reference_codes",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("list", sa.String(30), nullable=False),
        sa.Column("version", sa.String(30), nullable=False),
        sa.Column("subset", sa.String(80), server_default="", nullable=False),
        sa.Column("code", sa.String(30), nullable=False),
        sa.Column("term", sa.String(500), nullable=False),
        sa.Column("definition", sa.Text()),
        sa.Column("parent_code", sa.String(30)),
        sa.Column("imdrf_code", sa.String(20)),
        sa.Column("status", sa.String(60)),
        sa.Column("details", postgresql.JSONB(astext_type=sa.Text())),
        sa.Column("loaded_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_reference_codes")),
        sa.UniqueConstraint("list", "version", "subset", "code", name="uq_reference_code"),
        sa.CheckConstraint(f"list IN ({LISTS})", name="reference_code_list_known"),
    )
    op.create_index("ix_reference_codes_imdrf", "reference_codes", ["list", "version", "imdrf_code"])
    op.create_table(
        "code_list_files",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("list", sa.String(30), nullable=False),
        sa.Column("version", sa.String(30), nullable=False),
        sa.Column("file_name", sa.String(300), nullable=False),
        sa.Column("source_url", sa.Text(), nullable=False),
        sa.Column("published", sa.String(200), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("rows", sa.Integer(), nullable=False),
        sa.Column("loaded_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_code_list_files")),
    )
    # Shared reference data: the runtime role reads it; only the loader (the database owner) writes it.
    op.execute(RUNTIME_READS)


def downgrade():
    op.drop_table("code_list_files")
    op.drop_index("ix_reference_codes_imdrf", table_name="reference_codes")
    op.drop_table("reference_codes")
    op.drop_column("imdrf_codes", "status_note")
    op.drop_column("imdrf_codes", "status")
    op.drop_column("market_responsible_parties", "srn")
    op.drop_column("product_registrations", "risk_class")
    op.drop_column("products", "emdn_code")
    op.drop_column("products", "basic_udi_di")
