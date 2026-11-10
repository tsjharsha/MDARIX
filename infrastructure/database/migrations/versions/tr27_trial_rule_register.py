"""The rule register (backlog item B4): the reportability floor a market conclusion used.

The twenty-seventh migration of the trial line, chained from ``tr26challengeloop`` (B5's head). Expand-only: three
nullable columns on ``complaint_market_assessments`` (tenant-isolated already; row-level security unchanged, no new
table). The register itself is versioned files in the code (``backend/app/rule_register/data``), not a table.

- ``floor_code``: the floor version in force on the awareness day (``US-floor-1``), set at every draft save and at
  signing. Empty on rows signed before B4: never backfilled (R-D5).
- ``rules_applied``: the floor's rules that applied or could apply, with their state, and the report-type row chosen;
  for the routine path ``routine-basis-1``.
- ``date_calc``: how the due date was counted: awareness moment and source, the day that picked the floor, days and
  basis, window or regulation, the binding time zone and the counting rule's code.

Legacy dedicated organization databases get the same from scripts/add_workflow_tables_to_legacy_planes.py, which runs
``add_rule_register``.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "tr27ruleregister"
down_revision = "tr26challengeloop"
branch_labels = None
depends_on = None

TABLE = "complaint_market_assessments"


def add_rule_register(system_scope: bool = True) -> None:
    """Every change of this migration (also used for legacy organization databases)."""
    op.add_column(TABLE, sa.Column("floor_code", sa.String(40), nullable=True))
    op.add_column(TABLE, sa.Column("rules_applied", postgresql.JSONB(), nullable=True))
    op.add_column(TABLE, sa.Column("date_calc", postgresql.JSONB(), nullable=True))


def upgrade():
    add_rule_register()


def downgrade():
    op.drop_column(TABLE, "date_calc")
    op.drop_column(TABLE, "rules_applied")
    op.drop_column(TABLE, "floor_code")
