"""Distribution of lots and the case's lot impact list (release 0.10.61).

The seventh migration of the trial line's expert-feedback releases (T-G5, MVP G5 with G26's lot genealogy in cases),
chained from ``tr07oversight``. Its revision id starts with ``tr`` so it never collides with an ``md`` revision of
``mvp-1.0`` (``tr03pmssources`` stays reserved for proactive PMS); after the forward merge, ``mvp-1.0`` adds a merge
revision joining its head and this one.

Expand-only: one new table with its indexes and the tenant row-level security policy, and two new columns with
defaults on ``investigation_scope_versions``. No existing row changes. The downgrade removes only what this
migration added.

- ``lot_distributions``: one shipment of units of a lot to a consignee (an organization) in a country, on a day;
- ``investigation_scope_versions.excluded_lots``: ``[{lot_id, reason}]`` lots a person left out of the case;
- ``investigation_scope_versions.lot_impact``: the lot impact list's suspect factor and its last signed snapshot.

The models are in backend/app/db/models/lot_impact.py and case_scope.py. Legacy dedicated organization databases get
the same from scripts/add_workflow_tables_to_legacy_planes.py, which runs ``create_lot_impact_tables``.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from infrastructure.database.migrations.helpers import tenant_policy as _tenant_policy

revision = "tr08lotimpact"
down_revision = "tr07oversight"
branch_labels = None
depends_on = None

TABLE = "lot_distributions"
SCOPE = "investigation_scope_versions"


def create_lot_impact_tables(system_scope: bool = True) -> None:
    """The distribution table and its isolation, and the scope's two columns (also used for legacy databases)."""
    op.create_table(
        TABLE,
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("lot_batch_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("consignee", sa.String(255), nullable=False),
        sa.Column("consignee_type", sa.String(80)),
        sa.Column("consignee_reference", sa.String(120)),
        sa.Column("country", sa.String(2), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("ship_date", sa.Date(), nullable=False),
        sa.Column("source_system", sa.String(40)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f(f"pk_{TABLE}")),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], name=op.f(f"fk_{TABLE}_tenant_id_tenants")),
        sa.ForeignKeyConstraint(
            ["tenant_id", "lot_batch_id"],
            ["lot_batches.tenant_id", "lot_batches.id"],
            name="fk_lot_distributions_lot",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "tenant_id", "lot_batch_id", "consignee", "country", "ship_date", name="uq_lot_distributions_shipment"
        ),
        sa.CheckConstraint("quantity > 0", name=op.f(f"ck_{TABLE}_quantity_positive")),
    )
    op.create_index("ix_lot_distributions_tenant_lot", TABLE, ["tenant_id", "lot_batch_id"])
    _tenant_policy(TABLE, system_scope)
    op.add_column(
        SCOPE,
        sa.Column("excluded_lots", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False),
    )
    op.add_column(SCOPE, sa.Column("lot_impact", postgresql.JSONB()))


def upgrade():
    create_lot_impact_tables()


def downgrade():
    op.drop_column(SCOPE, "lot_impact")
    op.drop_column(SCOPE, "excluded_lots")
    op.drop_table(TABLE)
