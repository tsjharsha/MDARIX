"""DEV-04 (0.10.86): the free trial's row allowance holds when imports run at the same time.

Two sessions, as two requests: the first import stays uncommitted while the second runs in another thread. Before
0.10.86 both counted the same rows left, and both committed past the allowance. The allowance is now held by a
per-organization transaction lock (backend/app/trial/imports.py ``hold_allowance``): the second waits, then counts the
first's rows. Covered: the real 5,000-row boundary, a scaled limit, another kind of file, the reprocessing of a
set-aside row, a rollback, a re-upload of rows already there, and an unrelated organization (never blocked)."""

from __future__ import annotations

import dataclasses
import threading
import uuid

import pytest
from fastapi import HTTPException

from backend.app.db.session import SessionLocal
from backend.app.db.tenant_scope import bind_tenant
from backend.app.trial import imports
from backend.app.trial.service import TRIAL_ROW_LIMIT
from tests.test_free_trial import _approved_trial_client

pytestmark = pytest.mark.db


def _csv(prefix: str, rows: int, start: int = 0) -> bytes:
    lines = ["complaint_id,product_id,product_name,description,received_date"]
    lines += [
        f"{prefix}-{number:05d},{prefix}-PUMP,{prefix} Pump,Pressure alarm during infusion,2026-10-01"
        for number in range(start, start + rows)
    ]
    return ("\n".join(lines) + "\n").encode()


def _session(tenant_id):
    db = SessionLocal()
    bind_tenant(db, tenant_id)
    return db


def _used(tenant_id) -> int:
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        return imports.uploaded_rows(db, tenant_id)


def _race(tenant_a, first, tenant_b, second, *, end: str = "commit"):
    """``first(db)`` runs and stays open while ``second(db)`` runs in another session and thread; then the first
    ends (``commit`` or ``rollback``). Returns the second's outcome and whether it was still waiting meanwhile."""
    a = _session(tenant_a)
    first(a)
    outcome: dict = {}

    def other():
        b = _session(tenant_b)
        try:
            outcome["result"] = second(b)
            b.commit()
        except HTTPException as exc:
            outcome["refused"] = exc.detail
            b.rollback()
        finally:
            b.close()

    thread = threading.Thread(target=other)
    thread.start()
    thread.join(2.0)
    waited = thread.is_alive()
    getattr(a, end)()
    a.close()
    thread.join(120)
    assert not thread.is_alive(), "the second import never finished"
    return outcome, waited


def _refusal(outcome: dict) -> str:
    assert "refused" in outcome, outcome
    return " ".join(issue["message"] for issue in outcome["refused"]["report"]["issues"])


@pytest.fixture(scope="module")
def trials():
    from backend.app.trial.retention import purge_trial

    made = [uuid.UUID(_approved_trial_client()[1]["tenant_id"]) for _ in range(2)]
    try:
        yield made
    finally:
        for tenant_id in made:
            with SessionLocal() as db:
                purge_trial(db, tenant_id, "test:import-allowance-cleanup")


def _scaled(tenant_id, left: int):
    """The trial policy with only ``left`` rows left for this organization."""
    return dataclasses.replace(imports.TRIAL_POLICY, row_limit=_used(tenant_id) + left)


def test_two_imports_for_the_last_rows_commit_at_most_one(trials):
    tenant_id = trials[0]
    policy = _scaled(tenant_id, 2)
    outcome, waited = _race(
        tenant_id,
        lambda db: imports.import_file(db, tenant_id, "complaints", _csv("RACE-A", 2), policy),
        tenant_id,
        lambda db: imports.import_file(db, tenant_id, "complaints", _csv("RACE-B", 2), policy),
    )
    assert waited, "the second import did not wait for the first"
    assert "This file adds 2 rows; your trial has 0 of" in _refusal(outcome)
    assert _used(tenant_id) == policy.row_limit


def test_another_kind_of_file_and_a_reprocessed_row_count_against_the_same_allowance(trials):
    tenant_id = trials[0]
    policy = _scaled(tenant_id, 1)
    products = b"product_id,product_name\nRACE-OTHER-1,Other Monitor\n"
    outcome, waited = _race(
        tenant_id,
        lambda db: imports.import_file(db, tenant_id, "complaints", _csv("CROSS", 1), policy),
        tenant_id,
        lambda db: imports.import_file(db, tenant_id, "products", products, policy),
    )
    assert waited and "rows left" in _refusal(outcome)
    # A set-aside row corrected and imported again (import_quarantine.reprocess uses import_records) waits too.
    policy = _scaled(tenant_id, 1)
    record = {
        "complaint_id": "REDO-00001",
        "product_id": "REDO-PUMP",
        "product_name": "Redo Pump",
        "description": "Pressure alarm during infusion",
        "received_date": "2026-10-01",
    }
    outcome, waited = _race(
        tenant_id,
        lambda db: imports.import_file(db, tenant_id, "complaints", _csv("REDO-A", 1), policy),
        tenant_id,
        lambda db: imports.import_records(db, tenant_id, "complaints", [record], policy),
    )
    assert waited and "rows left" in _refusal(outcome)
    assert _used(tenant_id) == policy.row_limit


def test_a_rollback_gives_the_rows_back_and_a_re_upload_uses_none(trials):
    tenant_id = trials[0]
    policy = _scaled(tenant_id, 1)
    outcome, waited = _race(
        tenant_id,
        lambda db: imports.import_file(db, tenant_id, "complaints", _csv("BACK-A", 1), policy),
        tenant_id,
        lambda db: imports.import_file(db, tenant_id, "complaints", _csv("BACK-B", 1), policy),
        end="rollback",
    )
    assert waited and "result" in outcome, outcome  # the first rolled back: its row was free again
    assert _used(tenant_id) == policy.row_limit  # full now, with the second's row
    # The same row again, while another import holds the allowance: it waits, then updates and uses nothing.
    outcome, waited = _race(
        tenant_id,
        lambda db: imports.import_file(db, tenant_id, "complaints", _csv("BACK-B", 1), policy),
        tenant_id,
        lambda db: imports.import_file(db, tenant_id, "complaints", _csv("BACK-B", 1), policy),
    )
    assert waited and outcome["result"]["created"] == 0, outcome  # the row is there already: unchanged
    assert _used(tenant_id) == policy.row_limit


def test_an_unrelated_organization_is_never_blocked(trials):
    first, other = trials
    policy_first, policy_other = _scaled(first, 1), _scaled(other, 1)
    outcome, waited = _race(
        first,
        lambda db: imports.import_file(db, first, "complaints", _csv("MINE", 1), policy_first),
        other,
        lambda db: imports.import_file(db, other, "complaints", _csv("THEIRS", 1), policy_other),
        end="rollback",
    )
    assert not waited and "result" in outcome, outcome
    assert _used(other) == policy_other.row_limit


def test_the_real_allowance_of_5000_rows_admits_one_of_two_last_rows(trials):
    tenant_id = trials[1]
    used = _used(tenant_id)
    with _session(tenant_id) as db:
        imports.import_file(db, tenant_id, "complaints", _csv("FILL", TRIAL_ROW_LIMIT - used - 1), imports.TRIAL_POLICY)
        db.commit()
    assert _used(tenant_id) == TRIAL_ROW_LIMIT - 1
    outcome, waited = _race(
        tenant_id,
        lambda db: imports.import_file(db, tenant_id, "complaints", _csv("LAST-A", 1), imports.TRIAL_POLICY),
        tenant_id,
        lambda db: imports.import_file(db, tenant_id, "complaints", _csv("LAST-B", 1), imports.TRIAL_POLICY),
    )
    assert waited and "This file adds 1 row; your trial has 0 of 5,000 rows left." in _refusal(outcome)
    assert _used(tenant_id) == TRIAL_ROW_LIMIT
