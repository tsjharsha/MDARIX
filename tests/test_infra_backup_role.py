"""The backup login (scripts/configure_backup_role.py): reads everything, writes nothing, and degrades safely when the
database refuses BYPASSRLS. Runs against the test database, whose owner login is a superuser."""

from __future__ import annotations

import importlib.util
import secrets
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError

from backend.app.db.session import database_url, engine

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("configure_backup_role", ROOT / "scripts" / "configure_backup_role.py")
backup_role = importlib.util.module_from_spec(spec)
spec.loader.exec_module(backup_role)


@pytest.fixture
def role():
    name = f"mdarix_backup_t{secrets.token_hex(4)}"
    yield name
    with engine.begin() as connection:
        connection.execute(text(f'DROP OWNED BY "{name}"'))
        connection.execute(text(f'DROP ROLE IF EXISTS "{name}"'))


def test_the_backup_login_reads_every_row_and_writes_nothing(role):
    password = secrets.token_urlsafe(24)
    with engine.begin() as connection:
        result = backup_role.configure(connection, role, password)
    assert result["created"] and result["login"] and not result["superuser"]
    assert result["bypass_rls"] and result["bypass_granted_now"]
    assert "public" in result["schemas"]

    login = create_engine(database_url(role, password))
    try:
        with login.connect() as connection:
            # Row-level security does not hide any organization's rows from it (no tenant scope is set).
            assert connection.execute(text("SELECT count(*) FROM tenants")).scalar() > 0
            with pytest.raises(DBAPIError):
                connection.execute(text("UPDATE tenants SET updated_at = updated_at"))
    finally:
        login.dispose()


def test_running_it_again_updates_the_login(role):
    with engine.begin() as connection:
        backup_role.configure(connection, role, secrets.token_urlsafe(24))
    with engine.begin() as connection:
        again = backup_role.configure(connection, role, secrets.token_urlsafe(24))
    assert not again["created"] and again["bypass_rls"]


class _Refusing:
    """A connection whose server refuses ALTER ROLE ... BYPASSRLS, as managed services usually do."""

    class _Savepoint:
        rolled_back = committed = False

        def rollback(self):
            self.rolled_back = True

        def commit(self):
            self.committed = True

    def __init__(self, sqlstate: str):
        self.sqlstate = sqlstate
        self.savepoint = self._Savepoint()

    def begin_nested(self):
        return self.savepoint

    def execute(self, _statement):
        raise DBAPIError("ALTER ROLE", {}, Exception({"C": self.sqlstate, "M": "permission denied"}))


def test_a_refused_bypass_leaves_the_role_without_it():
    connection = _Refusing(backup_role.INSUFFICIENT_PRIVILEGE)
    assert backup_role.grant_bypass(connection, "mdarix_backup") is False
    assert connection.savepoint.rolled_back and not connection.savepoint.committed


def test_other_database_errors_are_not_mistaken_for_a_refusal():
    with pytest.raises(DBAPIError):
        backup_role.grant_bypass(_Refusing("08006"), "mdarix_backup")


def test_a_short_password_is_refused(monkeypatch, capsys):
    monkeypatch.setenv("MDARIX_BACKUP_DB_PASSWORD", "too-short")
    assert backup_role.main() == 2
    assert "at least 24 characters" in capsys.readouterr().err
