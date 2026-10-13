"""Units per lot: ``lot_batches.quantity`` (how many devices a lot released, nullable, never negative).

The trend check (backend/app/signals/trend_rules.py) uses it as its denominator: when every lot of a product version
has a quantity, a version's expected complaints follow the units in the field (unit-days) instead of the calendar, so
a version shipped in growing numbers no longer looks like a rising trend for that reason alone. Without quantities the
check stays on the calendar, as before, and says so. Legacy dedicated organization databases get the same column from
scripts/add_workflow_tables_to_legacy_planes.py, which runs this module's ``add_lot_quantity``.
"""

import sqlalchemy as sa
from alembic import op

revision = "md43lotquantity"
down_revision = "md42caseairun"
branch_labels = None
depends_on = None


def add_lot_quantity(system_scope: bool = True) -> None:
    """The column and its check (also used for legacy organization databases; ``system_scope`` is not needed: the
    table keeps its isolation)."""
    op.add_column("lot_batches", sa.Column("quantity", sa.Integer(), nullable=True))
    op.create_check_constraint(
        "ck_lot_batches_quantity_not_negative", "lot_batches", "quantity IS NULL OR quantity >= 0"
    )


def upgrade():
    add_lot_quantity()


def downgrade():
    op.drop_constraint("ck_lot_batches_quantity_not_negative", "lot_batches", type_="check")
    op.drop_column("lot_batches", "quantity")
