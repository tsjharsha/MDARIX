"""B6a B5 (spec 4.3, B6-15): the complaint page and the story have a query budget, and their query count stays flat with
the organization's size (100 and 1,000 imported complaints: the same count). A page that starts reading per complaint,
or a new repeated read, fails here before it reaches a pilot."""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import event
from sqlalchemy.engine import Engine

from tests.test_b6a_scoped_watch import _import
from tests.test_free_trial import _approved_trial_client

pytestmark = pytest.mark.db

# Queries per call, measured in B6a run 3 at 5,000 imported complaints (106 and 129), plus about 10%.
BUDGET = {"/api/v1/oversight/events/SAMPLE-RV-11": 115, "/api/v1/trial/one-story": 140}


def _queries(client, path: str) -> int:
    seen = {"count": 0}

    def count(*_args, **_kwargs):
        seen["count"] += 1

    event.listen(Engine, "before_cursor_execute", count)
    try:
        response = client.get(path)
    finally:
        event.remove(Engine, "before_cursor_execute", count)
    assert response.status_code == 200, (path, response.text[:300])
    return seen["count"]


def test_the_pages_stay_in_budget_and_flat_with_organization_size():  # B6-15
    from backend.app.db.session import SessionLocal
    from backend.app.trial.retention import purge_trial

    user, approval, _ = _approved_trial_client()
    tenant_id = uuid.UUID(approval["tenant_id"])
    try:
        _import(user, 100)
        for path in BUDGET:
            _queries(user, path)  # the first call of a page warms what a process keeps (not counted)
        at_100 = {path: _queries(user, path) for path in BUDGET}
        _import(user, 1000)  # the first 100 again (unchanged) and 900 more
        at_1000 = {path: _queries(user, path) for path in BUDGET}
        assert at_1000 == at_100, (at_100, at_1000)
        for path, limit in BUDGET.items():
            assert at_1000[path] <= limit, (path, at_1000[path], limit)
    finally:
        with SessionLocal() as db:
            purge_trial(db, tenant_id, "test:b6a-query-budget-cleanup")


def test_a_setting_kept_for_the_request_is_read_again_after_a_write():  # B6a run 3: per-request memo
    from sqlalchemy import text

    from backend.app.db.request_memo import once
    from backend.app.db.session import SessionLocal

    reads = []
    with SessionLocal() as db:
        assert once(db, ("k",), lambda: reads.append(1) or len(reads)) == 1
        assert once(db, ("k",), lambda: reads.append(1) or len(reads)) == 1  # kept: not read again
        with db.begin_nested():  # a section read in a savepoint, released: nothing written, still kept
            db.execute(text("SELECT 1"))
        assert once(db, ("k",), lambda: reads.append(1) or len(reads)) == 1
        db.commit()  # a write (commit, flush or rollback) drops what was kept
        assert once(db, ("k",), lambda: reads.append(1) or len(reads)) == 2
        db.execute(text("SELECT 1"))  # a transaction in progress, so the rollback is a real one
        db.rollback()
        assert once(db, ("k",), lambda: reads.append(1) or len(reads)) == 3
    with SessionLocal() as other:  # another request's session never sees it
        assert once(other, ("k",), lambda: "fresh") == "fresh"
