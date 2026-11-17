"""DB-1's migrations (tr21-tr24a) go down to tr19casesescalation and back up to head, leaving the same schema.

Runs Alembic against a fresh database of its own (the ``migration_database`` fixture in conftest.py): rows other tests
leave in the shared test database would make the later migrations' downgrade guards refuse.
"""

import subprocess
import sys
from pathlib import Path

from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[1]
BEFORE_DB1 = "tr19casesescalation"

FINGERPRINT = """
SELECT 'constraint', conrelid::regclass::text || ' ' || conname || ' ' || pg_get_constraintdef(oid)
FROM pg_constraint WHERE connamespace = 'public'::regnamespace
UNION ALL
SELECT 'index', indexrelid::regclass::text || ' ' || pg_get_indexdef(indexrelid)
FROM pg_index WHERE indrelid IN (SELECT oid FROM pg_class WHERE relnamespace = 'public'::regnamespace)
UNION ALL
SELECT 'policy', tablename || ' ' || policyname || ' ' || cmd || ' ' || coalesce(qual, '') || ' ' ||
       coalesce(with_check, '')
FROM pg_policies WHERE schemaname = 'public'
UNION ALL
SELECT 'rls', relname || ' ' || relrowsecurity::text || ' ' || relforcerowsecurity::text
FROM pg_class WHERE relnamespace = 'public'::regnamespace AND relkind = 'r'
UNION ALL
SELECT 'grant', table_name || ' ' || privilege_type
FROM information_schema.role_table_grants WHERE grantee = 'mdarix_runtime' AND table_schema = 'public'
"""


def _alembic(env: dict, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run([sys.executable, "-m", "alembic", *args], cwd=ROOT, env=env, capture_output=True, text=True)


def _ok(result: subprocess.CompletedProcess) -> None:
    assert result.returncode == 0, result.stderr[-2000:]


def _fingerprint(engine) -> set[tuple[str, str]]:
    with engine.connect() as connection:
        return {tuple(row) for row in connection.execute(text(FINGERPRINT))}


def test_db1_migrations_go_down_and_up_again_to_the_same_schema(migration_database):
    engine, env = migration_database
    at_head = _fingerprint(engine)
    try:
        _ok(_alembic(env, "downgrade", BEFORE_DB1))
        before = _fingerprint(engine)
    finally:
        _ok(_alembic(env, "upgrade", "head"))
    assert _fingerprint(engine) == at_head
    # The downgrade really removed DB-1: the composite references and the plane policies are gone.
    names = " ".join(item for _, item in before)
    assert "fk_complaints_source_record_id_tenant" not in names
    assert "fk_complaints_version_of_product" not in names
    assert "mdarix_plane_insert" not in names
    assert "fk_complaints_source_record_id_source_records" in names
    # tr24a: the lot and product references, the case context's check and the lot index.
    assert "fk_intake_events_lot_batch_id_tenant" not in names
    assert "fk_decisions_product_id_tenant" not in names
    assert "ck_case_contexts_version_needs_product" not in names
    assert "ix_intake_events_tenant_lot_batch" not in names
    after = " ".join(item for _, item in at_head)
    assert "fk_intake_events_lot_batch_id_tenant" in after and "ix_intake_events_tenant_lot_batch" in after
