"""Personal data at the report step (B9-D9 / B8-D9, owner 11 Nov 2026): one organization-level on/off setting.

The thirtieth migration of the trial line, chained from ``tr29partyparts`` (B8's head). Expand-only, no data step, no
backfill:

- ``reportability_settings.report_personal_data``: boolean, default false (off: patient and reporter boxes stay blank,
  "enter in the authority's route", as before). On: they may be typed at Send for approval and are kept only in that
  report's frozen snapshot. Set only by a Customer Admin with a reason, audited. The table is tenant-isolated already
  (row-level security unchanged, no new table).

Downgrade drops the column; it refuses while any organization has the setting on (never a silent change of what an
organization chose). Legacy dedicated organization databases get the same from
scripts/add_workflow_tables_to_legacy_planes.py, which runs ``add_personal_data``.
"""

import sqlalchemy as sa
from alembic import op

revision = "tr30personaldata"
down_revision = "tr29partyparts"
branch_labels = None
depends_on = None


def add_personal_data(system_scope: bool = True) -> None:
    """Every change of this migration (also used for legacy organization databases)."""
    op.add_column(
        "reportability_settings",
        sa.Column("report_personal_data", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )


def upgrade():
    add_personal_data()


def downgrade():
    # Off, a row-level policy that would hide a row raises instead of filtering: the count below sees every tenant.
    op.execute("SET LOCAL row_security = off")
    found = op.get_bind().execute(sa.text("SELECT count(*) FROM reportability_settings WHERE report_personal_data"))
    if found.scalar():
        raise RuntimeError(
            "An organization has personal data at the report step on: switch it off before downgrading tr30"
        )
    op.drop_column("reportability_settings", "report_personal_data")
