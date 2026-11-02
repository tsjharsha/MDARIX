"""Canada is a market of the per-market assessment (release 0.10.76, Release C, part C4).

The fifteenth migration of the trial line, chained from ``tr14reportcancelled`` (``tr03pmssources`` stays reserved
for proactive PMS); after the forward merge, ``mvp-1.0`` adds a merge revision joining its head and this one.

Expand-only: the market check of ``complaint_market_assessments`` also allows ``CA`` (Canada's starter question set,
Medical Devices Regulations SOR/98-282 ss. 59-61.1). No stored row changes; code before this release never writes it.

Legacy dedicated organization databases get the same from scripts/add_workflow_tables_to_legacy_planes.py, which runs
``allow_canada_assessments``.
"""

from alembic import op

from infrastructure.database.migrations.helpers import quoted

revision = "tr15canadamarket"
down_revision = "tr14reportcancelled"
branch_labels = None
depends_on = None

TABLE = "complaint_market_assessments"
CHECK = "ck_complaint_market_assessments_market_known"
MARKETS = ("US", "EU_NI", "GB", "IN")


def allow_canada_assessments(system_scope: bool = True) -> None:
    """The wider market check (also used for legacy organization databases; the table keeps its isolation)."""
    op.drop_constraint(op.f(CHECK), TABLE, type_="check")
    op.create_check_constraint(op.f(CHECK), TABLE, f"market IN ({quoted((*MARKETS, 'CA'))})")


def upgrade():
    allow_canada_assessments()


def downgrade():
    # A Canada assessment cannot exist under the narrower check: it is removed first (its audit events stay).
    op.execute(f"DELETE FROM {TABLE} WHERE market = 'CA'")
    op.drop_constraint(op.f(CHECK), TABLE, type_="check")
    op.create_check_constraint(op.f(CHECK), TABLE, f"market IN ({quoted(MARKETS)})")
