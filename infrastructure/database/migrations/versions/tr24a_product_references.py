"""A Case's lot and the product of decisions, briefs, assurance results and AI interactions are organization-safe
references; a person's case context never holds a version without its product (DB-1, owner decisions 1 and 2).

Chained from ``tr24tenantindexes``. No column is added, dropped or renamed; the application writes the same rows.

1. Pre-check: counts the rows that would break a rule (a lot or product that is not a row of the same organization,
   a context's version without a product) and refuses with the counts before anything changes, as tr22 does
   (``scripts/check_tenant_references.py`` prints the same counts read only).
2. The composite references ``(tenant_id, x_id) -> parent (tenant_id, id)`` on ``intake_events.lot_batch_id``
   (lot_batches) and on ``product_id`` (products) of decisions, investigation_briefs, assurance_results and
   ai_interactions, each added NOT VALID and then validated; and the check on ``case_contexts``.
3. The index for the Case's lot reference, built CONCURRENTLY outside a transaction (as tr24), so writes continue.

The lists are in infrastructure/database/migrations/product_references.py; the models mirror them.
``scripts/add_workflow_tables_to_legacy_planes.py`` runs the same steps (``apply_to_legacy_plane``) in one
transaction on a legacy dedicated database.
"""

from alembic import op

from infrastructure.database.migrations.helpers import forced_tables
from infrastructure.database.migrations.product_references import (
    INDEXES,
    REFERENCES,
    VERSION_CHECK,
    VERSION_CHECK_TABLES,
    tables_read,
    version_check_name,
    violation_counts,
)
from infrastructure.database.migrations.tenant_references import refusal

revision = "tr24aproductreferences"
down_revision = "tr24tenantindexes"
branch_labels = None
depends_on = None


def _exists(connection, name: str) -> bool:
    return bool(connection.exec_driver_sql("SELECT 1 FROM pg_constraint WHERE conname = %s", (name,)).scalar())


def check_rows() -> None:
    """Refuse with the counts when any row breaks a rule. The owner must see every row: when it is neither superuser
    nor BYPASSRLS, forced row-level security is lifted on the tables read for the count and forced again in the same
    transaction (as tr22)."""
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


def add_constraints() -> None:
    """Each constraint once (a re-run after a failed index build finds them there)."""
    connection = op.get_bind()
    for ref in REFERENCES:
        if not _exists(connection, ref.name):
            op.execute(
                f"ALTER TABLE public.{ref.child} ADD CONSTRAINT {ref.name} FOREIGN KEY (tenant_id, {ref.column}) "
                f"REFERENCES public.{ref.parent} (tenant_id, id) NOT VALID"
            )
            op.execute(f"ALTER TABLE public.{ref.child} VALIDATE CONSTRAINT {ref.name}")
    for table in VERSION_CHECK_TABLES:
        name = version_check_name(table)
        if not _exists(connection, name):
            op.execute(f"ALTER TABLE public.{table} ADD CONSTRAINT {name} CHECK ({VERSION_CHECK}) NOT VALID")
            op.execute(f"ALTER TABLE public.{table} VALIDATE CONSTRAINT {name}")


def create_indexes(concurrently: bool = True) -> None:
    """The indexes; CONCURRENTLY only outside a transaction (the caller's autocommit block)."""
    connection = op.get_bind()
    how = " CONCURRENTLY" if concurrently else ""
    for name, table, columns in INDEXES:
        invalid = connection.exec_driver_sql(
            "SELECT NOT indisvalid FROM pg_index WHERE indexrelid = to_regclass(%s)", (f"public.{name}",)
        ).scalar()
        if invalid:
            op.execute(f"DROP INDEX{how} IF EXISTS public.{name}")
        op.execute(f"CREATE INDEX{how} IF NOT EXISTS {name} ON public.{table} ({', '.join(columns)})")


def apply_to_legacy_plane(system_scope: bool = True) -> None:
    """Every change of this migration in the caller's one transaction (a legacy dedicated database is small)."""
    check_rows()
    add_constraints()
    create_indexes(concurrently=False)


def upgrade():
    check_rows()
    add_constraints()
    with op.get_context().autocommit_block():
        op.execute("COMMIT")  # end the transaction pg8000 may still hold (see tr24)
        create_indexes()


def downgrade():
    with op.get_context().autocommit_block():
        op.execute("COMMIT")
        for name, _table, _columns in reversed(INDEXES):
            op.execute(f"DROP INDEX CONCURRENTLY IF EXISTS public.{name}")
    for table in reversed(VERSION_CHECK_TABLES):
        op.execute(f"ALTER TABLE public.{table} DROP CONSTRAINT IF EXISTS {version_check_name(table)}")
    for ref in reversed(REFERENCES):
        op.execute(f"ALTER TABLE public.{ref.child} DROP CONSTRAINT IF EXISTS {ref.name}")
