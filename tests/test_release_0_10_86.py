"""0.10.86, a reliability release (external code review, DEV-01 to DEV-07): the regressions behind each fix."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from backend.app.communications import rules as comm_rules
from backend.app.db.bulk import insert_rows
from backend.app.db.models.foundation import Complaint
from backend.app.db.models.guides_communications import CommunicationEntry, ExternalParty
from backend.app.db.session import SessionLocal
from backend.app.db.tenant_scope import bind_tenant
from tests.test_free_trial import _approved_trial_client

LOG = "/api/v1/communications"


def _ok(response):
    assert response.status_code == 200, response.text
    return response.json()


@pytest.fixture(scope="module")
def trial():
    from backend.app.trial.retention import purge_trial

    user, approval, _ = _approved_trial_client()
    tenant_id = uuid.UUID(approval["tenant_id"])
    try:
        yield {"user": user, "tenant_id": tenant_id}
    finally:
        with SessionLocal() as db:
            purge_trial(db, tenant_id, "test:release-0.10.86-cleanup")


# ------------------------------------------------------------------------------ DEV-03: the communications log


def _many_entries(tenant_id) -> tuple[uuid.UUID, uuid.UUID]:
    """501 closed updates of the last days and, older than all of them, one overdue request: (overdue, oldest closed)."""
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        party = db.query(ExternalParty.id).filter(ExternalParty.tenant_id == tenant_id).first()[0]
        complaint = db.query(Complaint.id).filter(Complaint.tenant_id == tenant_id).first()[0]
        common = {
            "tenant_id": tenant_id,
            "party_id": party,
            "complaint_id": complaint,
            "channel": "EMAIL",
            "logged_by": "test",
            "updated_at": now,
        }
        overdue = uuid.uuid4()
        asked = now - timedelta(days=400)
        rows = [
            {
                **common,
                "id": overdue,
                "direction": comm_rules.SENT,
                "purpose": comm_rules.REQUEST,
                "subject": "The oldest question, never answered",
                "occurred_at": asked,
                "logged_at": asked + timedelta(hours=3),
                "owner_id": "test",
                "reply_due_on": (asked + timedelta(days=5)).date(),
                "status": comm_rules.OPEN,
                "attempts": [
                    {
                        "at": asked.isoformat(),
                        "logged_at": (asked + timedelta(hours=3)).isoformat(),
                        "channel": "EMAIL",
                        "contact": comm_rules.PRIMARY,
                        "outcome": comm_rules.WAITING,
                        "logged_by": "test",
                    }
                ],
            }
        ]
        oldest_closed = uuid.uuid4()
        for index in range(501):
            moment = now - timedelta(days=2, minutes=index)
            rows.append(
                {
                    **common,
                    "id": oldest_closed if index == 500 else uuid.uuid4(),
                    "direction": comm_rules.SENT,
                    "purpose": "UPDATE",
                    "subject": f"Update number {index}",
                    "occurred_at": moment,
                    # Every third one recorded two days late: outside MDARIX for S4.
                    "logged_at": moment + (timedelta(days=2) if index % 3 == 0 else timedelta(minutes=1)),
                    "status": comm_rules.CLOSED,
                }
            )
        insert_rows(db, CommunicationEntry, rows)
        db.commit()
    return overdue, oldest_closed


@pytest.mark.db
def test_the_oldest_overdue_request_leads_a_log_of_more_than_500_and_the_totals_cover_every_page(trial):
    user, tenant_id = trial["user"], trial["tenant_id"]
    overdue, oldest_closed = _many_entries(tenant_id)
    first = _ok(user.get(LOG))
    # Before 0.10.86 the newest 500 were read before sorting: this request, the oldest, was never shown or counted.
    leading = [item["id"] for item in first["items"] if item["overdue"]]
    assert str(overdue) in leading and first["items"][: len(leading)] == [i for i in first["items"] if i["overdue"]]
    assert first["total"] >= 502 and first["offset"] == 0 and first["next_offset"] == len(first["items"])
    # The same page twice is the same page; walking every page lists each entry once.
    assert [item["id"] for item in _ok(user.get(LOG))["items"]] == [item["id"] for item in first["items"]]
    pages, offset = [], 0
    while offset is not None:
        page = _ok(user.get(f"{LOG}?offset={offset}&limit=150"))
        pages.append(page)
        offset = page["next_offset"]
    seen = [item for page in pages for item in page["items"]]
    assert len(seen) == len({item["id"] for item in seen}) == first["total"]
    assert str(oldest_closed) in {item["id"] for item in pages[-1]["items"]}  # the older entries stay reachable
    ranks = [0 if item["overdue"] else 1 if item["status"] == comm_rules.OPEN else 2 for item in seen]
    assert ranks == sorted(ranks)
    # The counts and S4 are the whole log's, and agree with what the pages show entry by entry.
    for page in pages:
        assert page["counts"] == first["counts"] and page["s4"] == first["s4"] and page["total"] == first["total"]
    assert first["counts"] == {
        "open": sum(item["status"] == comm_rules.OPEN for item in seen),
        "overdue": sum(item["overdue"] for item in seen),
        "unresolved": sum(item["status"] == comm_rules.UNRESOLVED for item in seen),
    }
    flags = [flag for item in seen for flag in [item["in_mdarix"], *(a["in_mdarix"] for a in item["attempts"])]]
    assert first["s4"] == {"in_mdarix": flags.count(True), "outside": flags.count(False)}
    assert first["s4"]["outside"] >= 167  # every third of the 501 updates, plus the late-logged request
    # A page is at most 500 entries.
    assert user.get(f"{LOG}?limit=501").status_code == 422


@pytest.mark.unit
@pytest.mark.parametrize("day", range(7))
@pytest.mark.parametrize("hour", [9, 18, 23])
def test_the_sample_s_late_call_counts_outside_mdarix_whatever_day_the_trial_starts(day, hour):
    """The sample's "logged the next day" call was in MDARIX when the call fell on a Friday evening or a weekend
    (a day off has no working hour to miss), so the sample log's S4 showed no late message on some days."""
    from backend.app.oversight.rules import Calendar
    from backend.app.trial.sample_guides import late_log

    calendar = Calendar(zone="Asia/Kolkata")
    at = datetime(2026, 10, 26, hour, 30, tzinfo=calendar.tz).astimezone(timezone.utc) + timedelta(days=day)
    assert comm_rules.in_mdarix(at, late_log(at, calendar), calendar) is False


# ------------------------------------------------------- DEV-03 sweep: no open item behind a list's cap


@pytest.mark.db
def test_a_contact_waiting_to_be_signed_stays_listed_behind_500_newer_urgent_intakes(trial):
    from backend.app.db.models.intake import IntakeEvent

    user, tenant_id = trial["user"], trial["tenant_id"]
    now = datetime.now(timezone.utc)
    waiting = uuid.uuid4()
    common = {"tenant_id": tenant_id, "reporter_words": "The monitor alarmed twice", "created_by": "test"}
    rows = [
        {
            **common,
            "id": waiting,
            "reference": "CALL-T86-OLD",
            "kind": "CONTACT",
            "created_at": now - timedelta(days=90),
        }
    ]
    rows += [
        {**common, "id": uuid.uuid4(), "reference": f"URG-T86-{index}", "kind": "URGENT", "created_at": now}
        for index in range(501)
    ]
    for row in rows:
        row["updated_at"] = row["created_at"]
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        insert_rows(db, IntakeEvent, rows)
        db.commit()
    body = _ok(user.get("/api/v1/intake?show=to_sign"))
    # Before 0.10.86 the newest 500 were read first: this call, waiting to be signed, was not listed or counted.
    assert str(waiting) in [item["id"] for item in body["items"]]
    assert body["summary"]["to_sign"] >= 1 and body["summary"]["all"] >= 502


@pytest.mark.db
def test_open_items_are_never_cut_by_the_read_limits(trial, monkeypatch):
    """A complaint waiting for a disposition, a dated report and a dated CAPA: the lists that read them were capped
    newest first, or unordered, before 0.10.86. With the cap set to one, every one is still there."""
    from backend.app.complaint_disposition import service as dispositions
    from backend.app.oversight import service as oversight

    from backend.app.db.models.foundation import Capa

    tenant_id = trial["tenant_id"]
    due = datetime.now(timezone.utc) + timedelta(days=10)
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        for number, status in ((1, "open"), (2, "Closed"), (3, "in progress")):
            db.add(
                Capa(
                    tenant_id=tenant_id,
                    capa_identifier=f"CAPA-T86-{number}",
                    title="Seal",
                    status=status,
                    due_at=due,
                    created_at=due,
                    updated_at=due,
                )
            )
        db.commit()
        zone = oversight.calendar_of(db, tenant_id).zone
        before = (
            dispositions.waiting_ids(db, tenant_id),
            oversight._report_items(db, tenant_id, zone),
            oversight._capa_items(db, tenant_id),
        )
        monkeypatch.setattr(dispositions, "READ_LIMIT", 1)
        monkeypatch.setattr(oversight, "READ_LIMIT", 1)
        after = (
            dispositions.waiting_ids(db, tenant_id),
            oversight._report_items(db, tenant_id, zone),
            oversight._capa_items(db, tenant_id),
        )
    assert all(len(items) > 1 for items in before), [len(items) for items in before]
    assert after == before


def _platform_requests(model, rows):
    from backend.app.db.tenant_scope import bind_system

    with SessionLocal() as db:
        bind_system(db, "test: 0.10.86 request lists")
        insert_rows(db, model, rows)
        db.commit()


@pytest.mark.db
def test_a_pending_exit_request_and_an_open_mvp_request_stay_listed_behind_500_newer_decided_ones(trial):
    from backend.app.db.models.stage2 import TrialExitRequest, TrialMvpRequest
    from backend.app.db.tenant_scope import bind_system
    from backend.app.trial import early_exit, mvp_request

    tenant_id = trial["tenant_id"]
    now = datetime.now(timezone.utc)
    old = now - timedelta(days=60)
    pending, ids = uuid.uuid4(), []
    exits = [{"id": pending, "trial_tenant_id": uuid.uuid4(), "organization": "Old Co", "status": "PENDING"}]
    exits[0].update(created_at=old, updated_at=old)
    for _ in range(501):
        exits.append(
            {
                "id": uuid.uuid4(),
                "trial_tenant_id": uuid.uuid4(),
                "organization": "New Co",
                "status": "DECLINED",
                "created_at": now,
                "updated_at": now,
            }
        )
    opened = uuid.uuid4()
    person = {"requested_by": uuid.uuid4(), "display_name": "Asha", "email": "asha@example.invalid"}
    common = {**person, "tenant_id": tenant_id, "organization": "Trial Co", "expectations": "A pilot on our data"}
    mvps = [{**common, "id": opened, "status": "NEW", "created_at": old, "updated_at": old}]
    mvps += [
        {**common, "id": uuid.uuid4(), "status": "CLOSED", "created_at": now, "updated_at": now} for _ in range(501)
    ]
    ids = [row["id"] for row in exits]
    _platform_requests(TrialExitRequest, exits)
    _platform_requests(TrialMvpRequest, mvps)
    try:
        with SessionLocal() as db:
            bind_system(db, "test: 0.10.86 request lists")
            listed = early_exit.overview(db)
            # Pending requests come first; others the shared test database holds may be pending too.
            waiting = [item["id"] for item in listed if item["status"] == "PENDING"]
            assert str(pending) in waiting and all(item["status"] == "PENDING" for item in listed[: len(waiting)])
            assert str(opened) in [item["id"] for item in mvp_request.overview(db)["items"]]
    finally:
        with SessionLocal() as db:
            bind_system(db, "test: 0.10.86 request lists cleanup")
            db.query(TrialExitRequest).filter(TrialExitRequest.id.in_(ids)).delete(synchronize_session=False)
            db.query(TrialMvpRequest).filter(TrialMvpRequest.tenant_id == tenant_id).delete(synchronize_session=False)
            db.commit()
