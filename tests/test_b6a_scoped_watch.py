"""B6a B2 (spec 4.2, B6-14): the scoped reads equal the whole organization's reads, complaint by complaint.

A complaint page reads only its complaint's dated items and watch (oversight complaint_work, reportability watch with
``complaint_ids``). These tests are the guard against a wrong deadline: for every complaint of the sample trial, the
scoped result equals the organization-wide result filtered to that complaint (same items, same order, same dates).
The same proof on the 5,000-row load set is opt-in (it imports 5,000 complaints):

    MDARIX_TRIAL_LOAD_MEASURE=1 python -m pytest tests/test_b6a_scoped_watch.py -k load_set
"""

from __future__ import annotations

import os
import uuid
from datetime import datetime, timezone

import pytest

from backend.app.db.models.foundation import Complaint
from backend.app.db.session import SessionLocal
from backend.app.db.tenant_scope import bind_tenant
from backend.app.oversight import router as oversight_router
from backend.app.oversight import service as oversight
from tests.test_free_trial import _approved_trial_client

pytestmark = pytest.mark.db
NOW = datetime.now(timezone.utc).replace(microsecond=0)


@pytest.fixture(scope="module")
def trial():
    from backend.app.trial.retention import purge_trial

    user, approval, _ = _approved_trial_client()
    tenant_id = uuid.UUID(approval["tenant_id"])
    try:
        yield {"user": user, "tenant_id": tenant_id}
    finally:
        with SessionLocal() as db:
            purge_trial(db, tenant_id, "test:b6a-scoped-watch-cleanup")


def _assert_scoped_equals_whole(tenant_id, monkeypatch, ids: list[str] | None = None) -> int:
    """Every complaint (or ``ids``): its scoped watch, due items and page work equal the whole organization's read
    filtered to it. Returns how many complaints had a dated item (so a test cannot pass on empty data)."""
    from backend.app.intake import service as intake
    from backend.app.reportability import service as reportability

    monkeypatch.setattr(oversight, "now_utc", lambda: NOW)
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        complaints = db.query(Complaint).filter(Complaint.tenant_id == tenant_id).order_by(Complaint.id).all()
        if ids is not None:
            complaints = [row for row in complaints if str(row.id) in ids]
        whole_triage = intake.triage(db, db, tenant_id, "all", NOW)["items"]
        whole_watch = reportability.watch(db, db, tenant_id, show="all", page_size=100_000, today=NOW)["items"]
        whole_items = oversight.due_items(db, db, tenant_id, NOW)
        reads = oversight_router.dated_reads(db, db, tenant_id, NOW)
        whole_work = oversight_router.complaint_work(db, db, tenant_id, complaints, reads)
        dated = 0
        for complaint in complaints:
            key = {str(complaint.id)}
            member = f"{intake.COMPLAINT}:{complaint.id}"
            triage = intake.triage(db, db, tenant_id, "all", NOW, complaint_ids=key)["items"]
            assert triage == [item for item in whole_triage if member in item["members"]], (
                complaint.complaint_identifier
            )
            watch = reportability.watch(db, db, tenant_id, show="all", page_size=100_000, today=NOW, complaint_ids=key)
            assert watch["items"] == [item for item in whole_watch if item["id"] in key], complaint.complaint_identifier
            failed: list[str] = []  # a source that fails is dropped silently by due_items: never in this proof
            items = oversight.due_items(db, db, tenant_id, NOW, failed, complaint_ids=key)
            assert not failed, (complaint.complaint_identifier, failed)
            assert items == [item for item in whole_items if item["complaint_id"] in key], (
                complaint.complaint_identifier
            )
            work = oversight_router.complaint_work(db, db, tenant_id, [complaint])
            assert work == {k: whole_work[k] for k in key}, complaint.complaint_identifier
            dated += bool(work[str(complaint.id)]["due"])
        return dated


def test_every_sample_complaint_reads_the_same_scoped_as_organization_wide(trial, monkeypatch):  # B6-14
    dated = _assert_scoped_equals_whole(trial["tenant_id"], monkeypatch)
    assert dated >= 5  # the sample's story complaints carry clocks, deadlines and targets


def test_a_page_of_complaints_reads_the_same_as_each_alone(trial, monkeypatch):  # B6-14
    monkeypatch.setattr(oversight, "now_utc", lambda: NOW)
    with SessionLocal() as db:
        bind_tenant(db, trial["tenant_id"])
        complaints = db.query(Complaint).filter(Complaint.tenant_id == trial["tenant_id"]).all()
        together = oversight_router.complaint_work(db, db, trial["tenant_id"], complaints)
        for complaint in complaints:
            alone = oversight_router.complaint_work(db, db, trial["tenant_id"], [complaint])
            assert alone[str(complaint.id)] == together[str(complaint.id)], complaint.complaint_identifier


def test_another_organizations_complaint_is_never_read_into_a_scoped_page(trial, monkeypatch):
    """Tenant isolation: a scoped read names complaint ids, never a tenant: another organization's id reads nothing."""
    from backend.app.reportability import service as reportability

    other, approval, _ = _approved_trial_client()
    other_tenant = uuid.UUID(approval["tenant_id"])
    try:
        with SessionLocal() as db:
            bind_tenant(db, other_tenant)
            theirs = {str(row.id) for row in db.query(Complaint.id).filter(Complaint.tenant_id == other_tenant)}
        with SessionLocal() as db:
            bind_tenant(db, trial["tenant_id"])
            assert theirs  # the other trial has its sample complaints, so the test cannot pass on nothing
            assert not reportability.watch(db, db, trial["tenant_id"], complaint_ids=theirs, show="all")["items"]
            assert not oversight.due_items(db, db, trial["tenant_id"], NOW, complaint_ids=theirs)
    finally:
        from backend.app.trial.retention import purge_trial

        with SessionLocal() as db:
            purge_trial(db, other_tenant, "test:b6a-scoped-watch-cleanup")


def _import(user, rows: int) -> None:
    from tests.test_trial_load_measure import _complaints_csv

    query = f"?date_format=ISO&on_problems=skip&personal_data=refuse&file_name=load-{rows}.csv"
    imported = user.post(
        f"/api/v1/data/import/complaints{query}", content=_complaints_csv(rows), headers={"Content-Type": "text/csv"}
    )
    assert imported.status_code == 200, imported.text[:300]


def _story_choice_before_b6a(db, tenant_id):
    """The story's choice as 0.10.88-0.11.02 made it: every imported complaint loaded, harm ranked in Python."""
    from backend.app.trial.imports import UPLOAD_SOURCE
    from backend.app.trial.one_story import harm_rank

    rows = db.query(Complaint).filter(Complaint.tenant_id == tenant_id, Complaint.source_system == UPLOAD_SOURCE).all()
    top = max(harm_rank(row) for row in rows)
    serious = [row for row in rows if harm_rank(row) == top]
    work = oversight_router.complaint_work(
        db, db, tenant_id, serious, oversight_router.dated_reads(db, db, tenant_id, NOW)
    )

    def clock(row) -> str:
        due = work.get(str(row.id), {}).get("due") or []
        return due[0]["due_at"] if due else "9999"

    return min(serious, key=lambda row: (clock(row), row.complaint_identifier or ""))


def _assert_story_chooses_as_before(tenant_id, monkeypatch) -> None:
    from backend.app.trial.one_story import most_urgent

    monkeypatch.setattr(oversight, "now_utc", lambda: NOW)
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        assert most_urgent(db, db, tenant_id).id == _story_choice_before_b6a(db, tenant_id).id


def test_the_story_chooses_the_same_imported_complaint_as_before(trial, monkeypatch):  # B6a B3
    _import(trial["user"], 200)  # three serious injuries (rows 0, 97, 194) among malfunctions and none
    _assert_story_chooses_as_before(trial["tenant_id"], monkeypatch)
    assert _assert_scoped_equals_whole(trial["tenant_id"], monkeypatch) >= 5


@pytest.mark.slow
@pytest.mark.skipif(not os.getenv("MDARIX_TRIAL_LOAD_MEASURE"), reason="opt-in: imports 5,000 complaints")
def test_the_load_set_reads_the_same_scoped_as_organization_wide(trial, monkeypatch):  # B6-14, load set
    _import(trial["user"], 5000)
    _assert_story_chooses_as_before(trial["tenant_id"], monkeypatch)
    assert _assert_scoped_equals_whole(trial["tenant_id"], monkeypatch) >= 100
