"""A SAVEPOINT does not apply the tenant scope again (one statement per savepoint saved, review P3-P5), and the scope
the database holds is still the session's inside every savepoint, after a rolled-back one too."""

import uuid

import pytest
from sqlalchemy import event, text
from sqlalchemy.engine import Engine

from backend.app.db.session import SessionLocal
from backend.app.db.tenant_scope import bind_system, bind_tenant

pytestmark = pytest.mark.db


def _scope(db) -> tuple:
    return tuple(
        db.execute(
            text("SELECT current_setting('app.tenant_id', true), current_setting('app.rls_bypass', true) <> ''")
        ).one()
    )


def test_savepoints_keep_the_scope_without_applying_it_again():
    tenant = str(uuid.uuid4())
    applied = []

    def seen(_conn, _cursor, statement, *_args):
        if "set_config('app.tenant_id'" in statement:
            applied.append(statement)

    with SessionLocal() as db:
        bind_tenant(db, tenant)
        assert _scope(db) == (tenant, False)
        event.listen(Engine, "before_cursor_execute", seen)
        try:
            for _ in range(3):
                with db.begin_nested():
                    assert _scope(db) == (tenant, False)
            assert applied == []
            try:
                with db.begin_nested():
                    bind_system(db, "test: changed inside a savepoint that is rolled back")
                    raise RuntimeError("roll back")
            except RuntimeError:
                pass
            with db.begin_nested():  # after a rollback the scope is applied again: the session's, not the reverted one
                assert len(applied) == 2
                assert _scope(db) == (tenant, True)  # the system scope the session now has
        finally:
            event.remove(Engine, "before_cursor_execute", seen)
        db.commit()
        assert _scope(db) == (tenant, True)  # a new transaction applies it at its start
