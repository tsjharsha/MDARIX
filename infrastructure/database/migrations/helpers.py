"""Steps the workflow migrations (md27-md33) share: organization row-level security on a new table, the runtime
role's grant, quoted value lists for CHECK constraints, and registering business-identifier prefixes.

Each migration used to carry its own copy of these. The SQL they emit is exactly what those copies emitted (a fresh
database built from every migration has the same schema and master data with either), so treat a change here as a
change to every migration that imports it.
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

from infrastructure.database.migrations.business_ids import WIDTH

# The organization a session is bound to, and the system scope (platform administration), as in md05/md15.
TENANT = "NULLIF(current_setting('app.tenant_id', true), '')::uuid"
SYSTEM = "(SELECT public.mdarix_system_scope())"
# The runtime role may not exist yet (a database migrated before the role is created); then the grant waits for
# scripts/grant_runtime_privileges.py.
GRANT = (
    "DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'mdarix_runtime') THEN "
    "GRANT SELECT, INSERT, UPDATE, DELETE ON public.{table} TO mdarix_runtime; END IF; END $$;"
)


def quoted(values) -> str:
    """'A', 'B', 'C' for a CHECK constraint's IN list."""
    return ", ".join(f"'{value}'" for value in values)


def tenant_policy(table: str, system_scope: bool = True) -> None:
    """Rows are visible to their organization and to system scope (platform administration), as in md23. A legacy
    organization database has no system scope; there the rows are visible to the organization only, as its other
    tables are."""
    match = f"tenant_id = {TENANT}"
    allowed = f"{match} OR {SYSTEM}" if system_scope else match
    op.execute(f"ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE public.{table} FORCE ROW LEVEL SECURITY")
    op.execute(f"CREATE POLICY mdarix_tenant_isolation ON public.{table} USING ({allowed}) WITH CHECK ({allowed})")
    op.execute(GRANT.format(table=table))


def forced_tables(connection, tables) -> list[str]:
    """The tables among ``tables`` that force row-level security in this database."""
    return [
        table
        for table in tables
        if connection.execute(
            sa.text("SELECT relforcerowsecurity FROM pg_class WHERE oid = to_regclass(:name)"),
            {"name": f"public.{table}"},
        ).scalar()
    ]


def registry_present(connection) -> bool:
    """Whether this database has the business-identifier prefix registry (the control database; not a legacy one)."""
    return bool(connection.execute(sa.text("SELECT to_regclass('md_master.business_id_prefix') IS NOT NULL")).scalar())


def register_prefixes(items) -> None:
    """Register each business object's prefix and its counter, where the registry exists. Re-running keeps both:
    prefixes are permanent (md_master.protect_prefix_registry) and numbering continues where it stopped."""
    connection = op.get_bind()
    if not registry_present(connection):
        return
    for item in items:
        sequence = f"seq_business_id_{item.prefix.lower()}"
        op.execute(f"CREATE SEQUENCE IF NOT EXISTS md_master.{sequence}")
        op.execute(
            f"""
            INSERT INTO md_master.business_id_prefix (prefix, entity_name, sequence_name, id_width, owning_schema)
            VALUES ('{item.prefix}', '{item.entity}', '{sequence}', {WIDTH}, 'md_transaction')
            ON CONFLICT (prefix) DO UPDATE SET id_width = {WIDTH}
            """
        )
