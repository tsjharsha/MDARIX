"""The scripts that create or grant the runtime role (DB-1: sql-text-review D-1 and H-1)."""

import sys
from pathlib import Path

import pytest
from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

PROBE = "mdarix_probe_runtime_role"


def test_upgrade_data_planes_creates_and_updates_the_runtime_role_with_a_password():
    """CREATE/ALTER ROLE takes no bound parameter: the password is quoted as a literal, quotes included."""
    from upgrade_data_planes import grant_runtime_role

    from backend.app.db.session import engine

    with engine.connect() as connection:
        transaction = connection.begin()
        try:
            grant_runtime_role(connection, PROBE, "it's a p@ss")
            flags = connection.execute(
                text("SELECT rolcanlogin, rolsuper, rolbypassrls FROM pg_roles WHERE rolname = :r"), {"r": PROBE}
            ).one()
            assert tuple(flags) == (True, False, False)
            assert connection.scalar(text("SELECT has_table_privilege(:r, 'public.products', 'SELECT')"), {"r": PROBE})
            # Second run: the role exists, so the password is changed with ALTER ROLE.
            grant_runtime_role(connection, PROBE, "another 'one'")
        finally:
            transaction.rollback()


def test_upgrade_data_planes_refuses_a_role_name_that_is_not_plain():
    from upgrade_data_planes import grant_runtime_role

    with pytest.raises(ValueError):
        grant_runtime_role(object(), 'bad"role', "x")


@pytest.mark.parametrize("name", ['mdarix"; DROP ROLE x; --', "Runtime", "a b"])
def test_migrate_data_planes_refuses_a_runtime_role_name_that_is_not_plain(monkeypatch, name):
    from migrate_data_planes import _grants

    monkeypatch.setenv("MDARIX_DB_RUNTIME_USER", name)

    class NoEngine:
        def begin(self):  # pragma: no cover - reaching the database is the failure
            raise AssertionError("the role name must be checked before any statement")

    with pytest.raises(SystemExit):
        _grants(NoEngine())


def test_the_deploy_grant_leaves_the_tables_without_row_level_security_read_only():
    """grant_runtime_privileges.py runs on every deploy; its broad grant must not give back what tr21 revoked."""
    from grant_runtime_privileges import main

    from backend.app.db.session import engine

    assert main() == 0
    with engine.connect() as connection:
        for table in ("alembic_version", "business_id_counters"):
            for privilege in ("INSERT", "UPDATE", "DELETE"):
                allowed = connection.scalar(
                    text("SELECT has_table_privilege('mdarix_runtime', :t, :p)"),
                    {"t": f"public.{table}", "p": privilege},
                )
                assert not allowed, f"{privilege} on {table}"
