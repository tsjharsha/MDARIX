"""Indexes for organization filters and references (DB-1, defect DB-05). Expand-only: indexes only.

Chained from ``tr23compositetenantfks``. Each index is built with CREATE INDEX CONCURRENTLY outside a transaction
(Alembic ``autocommit_block``), so writes continue while it builds. The list, and why each index is there, is in
infrastructure/database/migrations/tenant_indexes.py; drift_policy.py treats them as migration-owned.

A concurrent build that fails leaves an INVALID index: this migration drops any invalid index of its own before
building it, so a re-run repairs it.
"""

from alembic import op

from infrastructure.database.migrations.tenant_indexes import INDEXES

revision = "tr24tenantindexes"
down_revision = "tr23compositetenantfks"
branch_labels = None
depends_on = None


def _outside_any_transaction() -> None:
    """Inside ``autocommit_block`` the pg8000 driver can still hold the transaction that Alembic's isolation-level
    read opened; end it, so the concurrent build is not refused as "inside a transaction block"."""
    op.execute("COMMIT")


def upgrade():
    with op.get_context().autocommit_block():
        _outside_any_transaction()
        connection = op.get_bind()
        for name, table, columns in INDEXES:
            invalid = connection.exec_driver_sql(
                "SELECT NOT indisvalid FROM pg_index WHERE indexrelid = to_regclass(%s)", (f"public.{name}",)
            ).scalar()
            if invalid:
                op.execute(f"DROP INDEX CONCURRENTLY IF EXISTS public.{name}")
            op.execute(f"CREATE INDEX CONCURRENTLY IF NOT EXISTS {name} ON public.{table} ({', '.join(columns)})")


def downgrade():
    with op.get_context().autocommit_block():
        _outside_any_transaction()
        for name, _table, _columns in reversed(INDEXES):
            op.execute(f"DROP INDEX CONCURRENTLY IF EXISTS public.{name}")
