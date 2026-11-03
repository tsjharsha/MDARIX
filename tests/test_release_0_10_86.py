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
