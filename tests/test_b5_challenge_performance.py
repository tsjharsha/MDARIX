"""B5a performance budget (spec 5.2, B6 targets): the challenge read (GET .../challenge) answers within 1.5 s and in
at most 12 queries' worth of work per table read, on the sample (SAMPLE-INV-001) and on the same case grown to about
200 scope complaints. The number of queries must not grow with the number of complaints."""

from __future__ import annotations

import time
import uuid

import pytest
from sqlalchemy import event
from sqlalchemy.engine import Engine

from backend.app.db.models.foundation import Complaint, Investigation, InvestigationComplaint
from backend.app.db.models.case_scope import InvestigationScopeVersion
from backend.app.db.session import SessionLocal
from backend.app.db.tenant_scope import bind_tenant
from tests.test_free_trial import _approved_trial_client

pytestmark = pytest.mark.db

BUDGET_SECONDS = 1.5


@pytest.fixture(scope="module")
def trial():
    from backend.app.trial.retention import purge_trial

    user, approval, _ = _approved_trial_client()
    tenant_id = uuid.UUID(approval["tenant_id"])
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        case_id = (
            db.query(Investigation.id)
            .filter(Investigation.tenant_id == tenant_id, Investigation.investigation_identifier == "SAMPLE-INV-001")
            .scalar()
        )
    try:
        yield {"user": user, "tenant_id": tenant_id, "case_id": case_id}
    finally:
        with SessionLocal() as db:
            purge_trial(db, tenant_id, "test:b5-performance-cleanup")


def _measure(trial) -> tuple[int, float]:
    counted = []

    def count(*_args, **_kwargs):
        counted.append(1)

    path = f"/api/v1/investigations/{trial['case_id']}/challenge"
    trial["user"].get(path)  # warm: the first view writes its audit row once
    event.listen(Engine, "before_cursor_execute", count)
    try:
        started = time.perf_counter()
        response = trial["user"].get(path)
        elapsed = time.perf_counter() - started
    finally:
        event.remove(Engine, "before_cursor_execute", count)
    assert response.status_code == 200, response.text
    return len(counted), elapsed


def _grow_scope(trial, total: int) -> None:
    """Copies of the sample's scope complaints (same product, version, lot and problem) until the scope holds about
    ``total``, in the latest scope version."""
    with SessionLocal() as db:
        bind_tenant(db, trial["tenant_id"])
        scope = (
            db.query(InvestigationScopeVersion)
            .filter(InvestigationScopeVersion.investigation_id == trial["case_id"])
            .order_by(InvestigationScopeVersion.version.desc())
            .first()
        )
        included = [str(item) for item in scope.included_complaint_ids]
        originals = db.query(Complaint).filter(Complaint.id.in_([uuid.UUID(item) for item in included])).all()
        columns = [column.key for column in Complaint.__table__.columns]
        added = []
        for n in range(total - len(included)):
            source = originals[n % len(originals)]
            values = {key: getattr(source, key) for key in columns}
            values.pop("business_id")  # numbered by the database
            values.update(id=uuid.uuid4(), complaint_identifier=f"PERF-{n:04d}")
            added.append(Complaint(**values))
        db.add_all(added)
        db.flush()
        for item in added:
            db.add(
                InvestigationComplaint(
                    id=uuid.uuid4(),
                    tenant_id=trial["tenant_id"],
                    investigation_id=trial["case_id"],
                    complaint_id=item.id,
                    created_at=item.created_at,
                )
            )
        scope.included_complaint_ids = included + [str(item.id) for item in added]
        db.commit()


def _view_queries(trial) -> int:
    """The queries of the challenge read itself (facts, drafts, questions, actions, answers), without the request's
    sign-in and tenant checks."""
    from backend.app.case_challenge.router import challenge_view
    from backend.app.case_intelligence.router import now_utc

    counted = []

    def count(*_args, **_kwargs):
        counted.append(1)

    with SessionLocal() as db:
        bind_tenant(db, trial["tenant_id"])
        case = db.query(Investigation).filter(Investigation.id == trial["case_id"]).one()
        event.listen(Engine, "before_cursor_execute", count)
        try:
            challenge_view(db, case, now_utc())
        finally:
            event.remove(Engine, "before_cursor_execute", count)
    return len(counted)


def test_the_challenge_read_stays_within_budget_and_its_queries_do_not_grow(trial, capsys):
    sample_view = _view_queries(trial)
    sample_queries, sample_seconds = _measure(trial)
    _grow_scope(trial, 200)
    grown_queries, grown_seconds = _measure(trial)
    grown_view = _view_queries(trial)
    with capsys.disabled():
        print(
            f"\nchallenge GET: sample {sample_queries} queries ({sample_view} in the read) {sample_seconds:.3f}s; "
            f"200 complaints {grown_queries} queries ({grown_view} in the read) {grown_seconds:.3f}s"
        )
    assert sample_seconds < BUDGET_SECONDS and grown_seconds < BUDGET_SECONDS
    assert grown_queries <= sample_queries + 2 and grown_view <= sample_view
