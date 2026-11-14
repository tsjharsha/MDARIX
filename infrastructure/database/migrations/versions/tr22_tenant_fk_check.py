"""Pre-check before the organization-safe references of tr23 (DB-1, defect DB-01 and PV-1 F1). Changes nothing.

Chained from ``tr21runtimeprivileges``. Counts, for each single-column reference between organization tables that
tr23 makes composite, the rows that point at another organization's row; and, for each table with a product and a
version, the rows whose version is set without a product or is not a version of that product. Any count above zero
stops the upgrade with the counts, before a constraint is touched (infrastructure/database/migrations/
tenant_references.py; ``scripts/check_tenant_references.py`` runs the same count read only).

The owner must see every row: when it is neither superuser nor BYPASSRLS, forced row-level security is lifted on the
tables read for the duration of the count and forced again in the same transaction (as md18 did).
"""

from alembic import op

from infrastructure.database.migrations.helpers import forced_tables
from infrastructure.database.migrations.tenant_references import refusal, tables_read, violation_counts

revision = "tr22tenantfkcheck"
down_revision = "tr21runtimeprivileges"
branch_labels = None
depends_on = None


def check_rows(system_scope: bool = True) -> None:
    """The count and the refusal (also run on legacy organization databases before tr23's changes)."""
    connection = op.get_bind()
    sees_all = connection.exec_driver_sql(
        "SELECT rolsuper OR rolbypassrls FROM pg_roles WHERE rolname = current_user"
    ).scalar()
    lifted = [] if sees_all else forced_tables(connection, tables_read())
    for table in lifted:
        op.execute(f"ALTER TABLE public.{table} NO FORCE ROW LEVEL SECURITY")
    counts = violation_counts(connection)
    for table in lifted:
        op.execute(f"ALTER TABLE public.{table} FORCE ROW LEVEL SECURITY")
    message = refusal(counts)
    if message:
        raise RuntimeError(message)


def upgrade():
    check_rows()


def downgrade():
    pass  # nothing was changed
