"""Each organization's navigation: classic or new (release 0.10.67, quality plan stage 6, task 6.9).

The tenth migration of the trial line, chained from ``tr10setasidedismissed`` (``tr03pmssources`` stays reserved for
proactive PMS); after the forward merge, ``mvp-1.0`` adds a merge revision joining its head and this one.

Expand-only: one column with a default, so every existing organization keeps today's menu:

- ``tenants.navigation``: ``classic`` (today's menu, the default) or ``new`` (stage 7's four destinations, built behind
  it). A platform administrator sets it in Tenant 360 (PATCH /api/v1/platform-admin/tenants/{id}, with a reason);
  the session context names it, and nothing shows it yet.

No existing per-organization store fits: the tenant's plan assignment changes when a trial becomes a pilot, and the
settings tables each belong to one feature. Legacy dedicated organization databases get the same from
scripts/add_workflow_tables_to_legacy_planes.py, which runs ``add_navigation``.
"""

import sqlalchemy as sa
from alembic import op

revision = "tr11navigation"
down_revision = "tr10setasidedismissed"
branch_labels = None
depends_on = None


def add_navigation(system_scope: bool = True) -> None:
    """The column and its check (also used for legacy organization databases; ``system_scope`` is not needed)."""
    op.add_column(
        "tenants", sa.Column("navigation", sa.String(10), nullable=False, server_default=sa.text("'classic'"))
    )
    op.create_check_constraint(
        op.f("ck_tenants_tenant_navigation_allowed"), "tenants", "navigation in ('classic','new')"
    )


def upgrade():
    add_navigation()


def downgrade():
    op.drop_constraint(op.f("ck_tenants_tenant_navigation_allowed"), "tenants", type_="check")
    op.drop_column("tenants", "navigation")
