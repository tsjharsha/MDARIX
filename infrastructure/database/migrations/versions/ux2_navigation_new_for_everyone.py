"""One navigation for every organization (Persona Blueprint wave D, owner decision 18 Nov 2026).

On ``tr33inconclusive``. Two changes to ``tenants.navigation``:

- the column's default becomes ``new``, so every organization created from now on (a pilot, a customer, a trial)
  starts on the new navigation;
- every existing row on ``classic`` is moved to ``new``. Exactly these rows change: ``UPDATE tenants SET navigation =
  'new' WHERE navigation = 'classic'`` (the migration prints how many). Rows already on ``new`` are untouched; no
  other column changes.

``classic`` stays an allowed value, so a platform administrator can still set it in Tenant 360 as a fallback for one
release; it is no longer anyone's default. The downgrade puts the default back to ``classic`` but does not move rows
back: which organizations were on classic is not recorded, and Tenant 360 can set it per organization.
"""

from alembic import op
import sqlalchemy as sa

revision = "ux2navigationnew"
down_revision = "tr33inconclusive"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("tenants", "navigation", server_default=sa.text("'new'"))
    moved = op.get_bind().execute(sa.text("UPDATE tenants SET navigation = 'new' WHERE navigation = 'classic'"))
    print(f"ux2navigationnew: {moved.rowcount} organization(s) moved from classic to new navigation")


def downgrade() -> None:
    op.alter_column("tenants", "navigation", server_default=sa.text("'classic'"))
