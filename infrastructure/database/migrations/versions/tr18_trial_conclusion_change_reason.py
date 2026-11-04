"""A re-signed market conclusion keeps why it changed (release 0.10.88, owner decision OD-4).

The eighteenth migration of the trial line, chained from ``tr16codelists`` (``tr17`` was kept for build B and ``tr19``
for build A of R2/R3; neither needed one). Expand-only: one nullable column. Re-signing a market conclusion, a new
version that supersedes a signed one, now asks why it changes, as re-signing a disposition does; the reason is kept
on the new version (``change_reason``), signed with it and audited. Earlier versions keep none.

Legacy dedicated organization databases get the same from scripts/add_workflow_tables_to_legacy_planes.py, which runs
``add_change_reason``.
"""

import sqlalchemy as sa
from alembic import op

revision = "tr18changereason"
down_revision = "tr16codelists"
branch_labels = None
depends_on = None

TABLE = "complaint_market_assessments"


def add_change_reason(system_scope: bool = True) -> None:
    """The column (also used for legacy organization databases; the table keeps its isolation)."""
    op.add_column(TABLE, sa.Column("change_reason", sa.Text(), nullable=True))


def upgrade():
    add_change_reason()


def downgrade():
    op.drop_column(TABLE, "change_reason")
