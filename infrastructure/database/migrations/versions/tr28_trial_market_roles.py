"""Reporting roles per market (backlog item B9, Part C): an organization's role in a market picks its floor.

The twenty-eighth migration of the trial line, chained from ``tr27ruleregister`` (B4's head). Expand-only, no data
step, no backfill:

- ``reportability_settings.reporting_roles``: JSONB object, market -> ``IMPORTER`` or ``USER_FACILITY``; absent means
  Manufacturer (today's behaviour). Default ``{}``; a check keeps it a JSON object. The table is tenant-isolated
  already (row-level security unchanged, no new table).
- ``market_responsible_parties``: the role check gains ``USER_FACILITY`` (the user facility profile: name, address,
  contact, HCFA number).

Downgrade drops the column and restores the role check; it refuses while a ``USER_FACILITY`` party exists (never a
silent loss). Legacy dedicated organization databases get the same from scripts/add_workflow_tables_to_legacy_planes.py,
which runs ``add_market_roles``.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "tr28marketroles"
down_revision = "tr27ruleregister"
branch_labels = None
depends_on = None

ROLES_BEFORE = (
    "MANUFACTURER", "IMPORTER", "AUTHORISED_REPRESENTATIVE", "UK_RESPONSIBLE_PERSON", "SPONSOR", "LICENCE_HOLDER",
)  # fmt: skip
ROLE_CHECK = "ck_market_responsible_parties_responsible_party_role_known"
OBJECT_CHECK = "ck_reportability_settings_reporting_roles_object"


def _roles(values) -> str:
    return "role IN (" + ", ".join(f"'{value}'" for value in values) + ")"


def add_market_roles(system_scope: bool = True) -> None:
    """Every change of this migration (also used for legacy organization databases)."""
    op.add_column(
        "reportability_settings",
        sa.Column("reporting_roles", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
    )
    op.execute(
        f"ALTER TABLE reportability_settings ADD CONSTRAINT {OBJECT_CHECK} "
        "CHECK (jsonb_typeof(reporting_roles) = 'object')"
    )
    op.execute(f"ALTER TABLE market_responsible_parties DROP CONSTRAINT {ROLE_CHECK}")
    op.execute(
        f"ALTER TABLE market_responsible_parties ADD CONSTRAINT {ROLE_CHECK} "
        f"CHECK ({_roles((*ROLES_BEFORE, 'USER_FACILITY'))})"
    )


def upgrade():
    add_market_roles()


def downgrade():
    # Off, a row-level policy that would hide a row raises instead of filtering: the count below sees every tenant.
    op.execute("SET LOCAL row_security = off")
    found = op.get_bind().execute(
        sa.text("SELECT count(*) FROM market_responsible_parties WHERE role = 'USER_FACILITY'")
    )
    if found.scalar():
        raise RuntimeError("A user facility profile exists: remove it before downgrading tr28 (no silent loss)")
    op.execute(f"ALTER TABLE market_responsible_parties DROP CONSTRAINT {ROLE_CHECK}")
    op.execute(f"ALTER TABLE market_responsible_parties ADD CONSTRAINT {ROLE_CHECK} CHECK ({_roles(ROLES_BEFORE)})")
    op.execute(f"ALTER TABLE reportability_settings DROP CONSTRAINT {OBJECT_CHECK}")
    op.drop_column("reportability_settings", "reporting_roles")
