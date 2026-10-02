"""Per-tenant limits: each tenant's plan assignment can hold its own licensed-user, customer-administrator and
connector limits, which take precedence over the plan's (shared by every tenant on the plan).

Existing assignments keep NULL, so they go on using their plan's limits exactly as before.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "md09tenantlimits"
down_revision = "md08totpmfa"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("tenant_plan_assignments", sa.Column("limits", postgresql.JSONB(), nullable=True))


def downgrade() -> None:
    op.drop_column("tenant_plan_assignments", "limits")
