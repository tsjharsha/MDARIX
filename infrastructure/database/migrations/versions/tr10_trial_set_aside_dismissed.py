"""A set-aside import row can be dismissed with a reason (release 0.10.65, quality plan stage 4, J11).

The ninth migration of the trial line, chained from ``tr09recordfacts`` (``tr03pmssources`` stays reserved for
proactive PMS); after the forward merge, ``mvp-1.0`` adds a merge revision joining its head and this one.

Expand-only: the status check of ``import_quarantine_rows`` also allows ``DISMISSED`` (no stored row changes; code
before this release never writes it), and one nullable column, no default:

- ``import_quarantine_rows.resolution_note``: why a person dismissed the row (personal details masked), or that a
  later import set the same record aside again and its row replaces this one.

Legacy dedicated organization databases get the same from scripts/add_workflow_tables_to_legacy_planes.py, which runs
``allow_dismissed_rows``.
"""

import sqlalchemy as sa
from alembic import op

revision = "tr10setasidedismissed"
down_revision = "tr09recordfacts"
branch_labels = None
depends_on = None

TABLE = "import_quarantine_rows"
CHECK = "import_quarantine_status_allowed"


def allow_dismissed_rows(system_scope: bool = True) -> None:
    """The wider status check and the note (also used for legacy organization databases; ``system_scope`` is not
    needed: the table keeps its isolation)."""
    op.drop_constraint(op.f(f"ck_{TABLE}_{CHECK}"), TABLE, type_="check")
    op.create_check_constraint(op.f(f"ck_{TABLE}_{CHECK}"), TABLE, "status in ('OPEN','REPROCESSED','DISMISSED')")
    op.add_column(TABLE, sa.Column("resolution_note", sa.String(500), nullable=True))


def upgrade():
    allow_dismissed_rows()


def downgrade():
    op.drop_column(TABLE, "resolution_note")
    op.execute(f"UPDATE {TABLE} SET status = 'OPEN', resolved_at = NULL, resolved_by = NULL WHERE status = 'DISMISSED'")
    op.drop_constraint(op.f(f"ck_{TABLE}_{CHECK}"), TABLE, type_="check")
    op.create_check_constraint(op.f(f"ck_{TABLE}_{CHECK}"), TABLE, "status in ('OPEN','REPROCESSED')")
