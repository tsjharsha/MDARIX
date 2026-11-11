"""Other countries (B9b, OC spec approved 9 Nov 2026): a country outside the five markets, per assessment and report.

The thirty-first migration of the trial line, chained from ``tr30personaldata`` (B8's head). Expand-only, no data step,
no backfill (every existing row is one of the five markets and keeps an empty country):

- ``complaint_market_assessments.country`` and ``report_obligations.country``: ISO 3166 alpha-2, set when the market is
  ``OTHER`` and empty otherwise (a check on each table).
- The assessment market check also allows ``OTHER``.
- The two unique keys gain ``coalesce(country, '')``, so one complaint can carry Australia and Switzerland side by side:
  the assessment version key and the one-initial-report-per-market index.

Downgrade restores the keys and checks and drops the columns; it refuses while any ``OTHER`` row exists (no silent
loss). Legacy dedicated organization databases get the same from scripts/add_workflow_tables_to_legacy_planes.py,
which runs ``add_other_countries``.
"""

import sqlalchemy as sa
from alembic import op

from infrastructure.database.migrations.helpers import quoted

revision = "tr31othercountries"
down_revision = "tr30personaldata"
branch_labels = None
depends_on = None

ASSESSMENTS, OBLIGATIONS = "complaint_market_assessments", "report_obligations"
MARKET_CHECK = "ck_complaint_market_assessments_market_known"
MARKETS = ("US", "EU_NI", "GB", "IN", "CA")
COUNTRY_RULE = (
    "(market = 'OTHER' AND country IS NOT NULL AND country ~ '^[A-Z]{2}$') OR (market <> 'OTHER' AND country IS NULL)"
)
VERSION_KEY, INITIAL_KEY = "uq_complaint_market_assessments_version", "uq_report_obligations_initial"
COUNTRY = sa.text("coalesce(country, '')")


def add_other_countries(system_scope: bool = True) -> None:
    """Every change of this migration (also used for legacy organization databases; isolation unchanged)."""
    for table in (ASSESSMENTS, OBLIGATIONS):
        op.add_column(table, sa.Column("country", sa.String(2), nullable=True))
        op.create_check_constraint(op.f(f"ck_{table}_country_when_other"), table, COUNTRY_RULE)
    op.drop_constraint(op.f(MARKET_CHECK), ASSESSMENTS, type_="check")
    op.create_check_constraint(op.f(MARKET_CHECK), ASSESSMENTS, f"market IN ({quoted((*MARKETS, 'OTHER'))})")
    op.drop_constraint(VERSION_KEY, ASSESSMENTS, type_="unique")
    op.create_index(VERSION_KEY, ASSESSMENTS, ["tenant_id", "complaint_id", "market", COUNTRY, "version"], unique=True)
    op.drop_index(INITIAL_KEY, table_name=OBLIGATIONS)
    op.create_index(
        INITIAL_KEY,
        OBLIGATIONS,
        ["tenant_id", "complaint_id", "market", COUNTRY],
        unique=True,
        postgresql_where=sa.text("kind = 'INITIAL'"),
    )


def upgrade():
    add_other_countries()


def downgrade():
    # Off, a row-level policy that would hide a row raises instead of filtering: the count below sees every tenant.
    op.execute("SET LOCAL row_security = off")
    bind = op.get_bind()
    found = sum(
        bind.execute(sa.text(f"SELECT count(*) FROM {table} WHERE market = 'OTHER'")).scalar()
        for table in (ASSESSMENTS, OBLIGATIONS)
    )
    if found:
        raise RuntimeError("Other-country assessments or reports exist: they would be lost by downgrading tr31")
    op.drop_index(INITIAL_KEY, table_name=OBLIGATIONS)
    op.create_index(
        INITIAL_KEY,
        OBLIGATIONS,
        ["tenant_id", "complaint_id", "market"],
        unique=True,
        postgresql_where=sa.text("kind = 'INITIAL'"),
    )
    op.drop_index(VERSION_KEY, table_name=ASSESSMENTS)
    op.create_unique_constraint(VERSION_KEY, ASSESSMENTS, ["tenant_id", "complaint_id", "market", "version"])
    op.drop_constraint(op.f(MARKET_CHECK), ASSESSMENTS, type_="check")
    op.create_check_constraint(op.f(MARKET_CHECK), ASSESSMENTS, f"market IN ({quoted(MARKETS)})")
    for table in (ASSESSMENTS, OBLIGATIONS):
        op.drop_constraint(op.f(f"ck_{table}_country_when_other"), table, type_="check")
        op.drop_column(table, "country")
