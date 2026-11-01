"""Small truths in the records (release 0.10.64, quality plan stage 3, J22 and J32).

The eighth migration of the trial line, chained from ``tr08lotimpact`` (``tr03pmssources`` stays reserved for
proactive PMS); after the forward merge, ``mvp-1.0`` adds a merge revision joining its head and this one.

Expand-only: nullable columns, no default, no existing row changes. The downgrade removes only what this migration
added.

- ``capas.qms_reference``: the number the customer's QMS gave a CAPA that MDARIX recorded for raising there;
- ``lot_batches.expiry_date``: the lot's expiry (use-by) date, when it has one;
- ``products.device_category``: IMPLANT, SINGLE_USE, REUSABLE (reusable or capital equipment), SOFTWARE, IVD or KIT
  (backend/app/product_facts.py checks the values);
- ``complaints.other_lots``: the lot identifiers beyond the first of a complaint that names several (a kit's lots).

Legacy dedicated organization databases get the same from scripts/add_workflow_tables_to_legacy_planes.py, which runs
``add_record_facts``.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "tr09recordfacts"
down_revision = "tr08lotimpact"
branch_labels = None
depends_on = None

COLUMNS = (
    ("capas", "qms_reference", lambda: sa.String(120)),
    ("lot_batches", "expiry_date", sa.Date),
    ("products", "device_category", lambda: sa.String(40)),
    ("complaints", "other_lots", postgresql.JSONB),
)


def add_record_facts(system_scope: bool = True) -> None:
    """The columns (also used for legacy organization databases; ``system_scope`` is not needed: each table keeps its
    isolation)."""
    for table, column, kind in COLUMNS:
        op.add_column(table, sa.Column(column, kind(), nullable=True))


def upgrade():
    add_record_facts()


def downgrade():
    for table, column, _ in reversed(COLUMNS):
        op.drop_column(table, column)
