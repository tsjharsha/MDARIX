"""The runtime role cannot steer routing, numbering or the schema stamp (DB-1, defect DB-02).

Chained from ``tr19casesescalation`` (``tr20`` is kept for another build). No table or column changes; the 0.10.94
images run on this schema.

- ``alembic_version`` and ``business_id_counters`` have no row-level security, so the runtime role keeps only SELECT
  on them. Business identifiers are still assigned: the md26 trigger function is SECURITY DEFINER and writes the
  counters as their owner.
- ``tenant_data_planes`` (which database serves an organization) gets row-level security, forced: every session may
  read it (the routing lookup runs before a request is bound to an organization), and only system scope may insert,
  change or delete a row. Every writer (platform onboarding, trial approval, the demo workspace, tenant purge, the
  plane scripts) already works in system scope.

scripts/grant_runtime_privileges.py, upgrade_data_planes.py and migrate_data_planes.py revoke the same writes after
their broad grant, so a deploy does not give them back.
"""

from alembic import op

revision = "tr21runtimeprivileges"
down_revision = "tr19casesescalation"
branch_labels = None
depends_on = None

_SYSTEM = "(SELECT public.mdarix_system_scope())"
READ_ONLY_FOR_RUNTIME = ("alembic_version", "business_id_counters")
PLANE_POLICIES = (
    ("mdarix_plane_read", "SELECT", "USING (true)"),
    ("mdarix_plane_insert", "INSERT", f"WITH CHECK ({_SYSTEM})"),
    ("mdarix_plane_update", "UPDATE", f"USING ({_SYSTEM}) WITH CHECK ({_SYSTEM})"),
    ("mdarix_plane_delete", "DELETE", f"USING ({_SYSTEM})"),
)


def _when_runtime_exists(statement: str) -> str:
    return (
        "DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'mdarix_runtime') THEN "
        f"{statement} END IF; END $$;"
    )


def upgrade():
    for table in READ_ONLY_FOR_RUNTIME:
        op.execute(_when_runtime_exists(f"REVOKE INSERT, UPDATE, DELETE ON public.{table} FROM mdarix_runtime;"))
    op.execute("ALTER TABLE public.tenant_data_planes ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE public.tenant_data_planes FORCE ROW LEVEL SECURITY")
    for name, command, clause in PLANE_POLICIES:
        op.execute(f"CREATE POLICY {name} ON public.tenant_data_planes FOR {command} {clause}")


def downgrade():
    for name, _command, _clause in PLANE_POLICIES:
        op.execute(f"DROP POLICY IF EXISTS {name} ON public.tenant_data_planes")
    op.execute("ALTER TABLE public.tenant_data_planes NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE public.tenant_data_planes DISABLE ROW LEVEL SECURITY")
    for table in READ_ONLY_FOR_RUNTIME:
        op.execute(_when_runtime_exists(f"GRANT INSERT, UPDATE, DELETE ON public.{table} TO mdarix_runtime;"))
