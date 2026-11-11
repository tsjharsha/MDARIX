"""EU and GB MIR party parts (backlog item B8, step 6): the address and contact in the parts the MIR XML needs.

The twenty-ninth migration of the trial line, chained from ``tr28marketroles`` (B9's head). Expand-only, no data
step, no backfill, nothing guessed from the old text:

- ``market_responsible_parties``: ``street``, ``city``, ``postcode``, ``country_code`` (ISO 3166 alpha-2, or XI for
  Northern Ireland), ``contact_first_name``, ``contact_last_name``; all nullable. ``address`` and ``contact_name`` stay.
- ``products``: ``udi_issuing_entity``, nullable, one of GS1, HIBCC, ICCBBA, IFA (B8-D11).

Both tables are tenant-isolated already (row-level security unchanged, no new table). Downgrade drops the columns; it
refuses while any of them holds a value (never a silent loss). Legacy dedicated organization databases get the same
from scripts/add_workflow_tables_to_legacy_planes.py, which runs ``add_party_parts``.
"""

import sqlalchemy as sa
from alembic import op

revision = "tr29partyparts"
down_revision = "tr28marketroles"
branch_labels = None
depends_on = None

PARTS = (
    ("street", 500), ("city", 120), ("postcode", 20), ("country_code", 2),
    ("contact_first_name", 100), ("contact_last_name", 100),
)  # fmt: skip
ISSUERS = ("GS1", "HIBCC", "ICCBBA", "IFA")
COUNTRY_CHECK = "ck_market_responsible_parties_country_code_alpha2"
ISSUER_CHECK = "ck_products_udi_issuing_entity_known"


def add_party_parts(system_scope: bool = True) -> None:
    """Every change of this migration (also used for legacy organization databases)."""
    for name, length in PARTS:
        op.add_column("market_responsible_parties", sa.Column(name, sa.String(length), nullable=True))
    op.execute(
        f"ALTER TABLE market_responsible_parties ADD CONSTRAINT {COUNTRY_CHECK} "
        "CHECK (country_code IS NULL OR country_code ~ '^[A-Z]{2}$')"
    )
    op.add_column("products", sa.Column("udi_issuing_entity", sa.String(10), nullable=True))
    op.execute(
        f"ALTER TABLE products ADD CONSTRAINT {ISSUER_CHECK} "
        "CHECK (udi_issuing_entity IS NULL OR udi_issuing_entity IN (" + ", ".join(f"'{v}'" for v in ISSUERS) + "))"
    )


def upgrade():
    add_party_parts()


def downgrade():
    # Off, a row-level policy that would hide a row raises instead of filtering: the counts below see every tenant.
    op.execute("SET LOCAL row_security = off")
    bind = op.get_bind()
    held = " OR ".join(f"{name} IS NOT NULL" for name, _ in PARTS)
    if (
        bind.execute(sa.text(f"SELECT count(*) FROM market_responsible_parties WHERE {held}")).scalar()
        or bind.execute(sa.text("SELECT count(*) FROM products WHERE udi_issuing_entity IS NOT NULL")).scalar()
    ):
        raise RuntimeError("Party parts or a UDI issuing entity are set: clear them before downgrading tr29 (no loss)")
    op.execute(f"ALTER TABLE products DROP CONSTRAINT {ISSUER_CHECK}")
    op.drop_column("products", "udi_issuing_entity")
    op.execute(f"ALTER TABLE market_responsible_parties DROP CONSTRAINT {COUNTRY_CHECK}")
    for name, _ in reversed(PARTS):
        op.drop_column("market_responsible_parties", name)
