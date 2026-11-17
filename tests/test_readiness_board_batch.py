"""The readiness board reads every check in one SAVEPOINT (performance, review P3); a failing check is still shown as
"could not be read" without failing the others."""

import uuid
from datetime import date

import pytest
from sqlalchemy import event
from sqlalchemy.engine import Engine

from backend.app.db.session import SessionLocal
from backend.app.db.tenant_scope import bind_system
from backend.app.readiness_home import service

pytestmark = pytest.mark.db


def _board(tenant_id):
    statements = []

    def seen(_conn, _cursor, statement, *_args):
        statements.append(statement)

    event.listen(Engine, "before_cursor_execute", seen)
    try:
        with SessionLocal() as db:
            bind_system(db, "test: readiness board")
            board = service.readiness(db, tenant_id, date(2026, 11, 17))
    finally:
        event.remove(Engine, "before_cursor_execute", seen)
    return board, sum(1 for statement in statements if statement.startswith("SAVEPOINT"))


def test_every_check_is_read_in_one_savepoint():
    board, savepoints = _board(uuid.uuid4())
    assert savepoints <= 2  # the batch, and the organization calendar read once inside it
    assert len(board["checks"]) == len(service.CHECKS)


def test_a_failing_check_is_shown_unread_and_the_others_are_read(monkeypatch):
    def broken(*_args):
        raise RuntimeError("a missing table on an older database")

    broken.__name__ = service.CHECKS[0].__name__
    monkeypatch.setattr(service, "CHECKS", (broken, *service.CHECKS[1:]))
    board, savepoints = _board(uuid.uuid4())
    by_code = {check["code"]: check for check in board["checks"]}
    unread = "This check could not be read; try again shortly"
    assert by_code[broken.__name__.upper()]["state"] == service.NOT_SET
    assert [check["code"] for check in board["checks"] if check["detail"] == unread] == [broken.__name__.upper()]
