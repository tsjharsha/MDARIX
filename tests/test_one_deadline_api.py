"""One deadline per market, the same on every screen, through the API (0.10.63, quality plan stage 2: J3, J14, J16, J28).

- J3: triage shows the event's own market first, the other enabled markets only "if also reportable", and a signed
  market conclusion's deadline instead of its provisional one (the sample's RV-06 and RV-07).
- J14: the reportability watch binds the earliest of the window's clock and a signed shorter category (an EU 2-day
  serious public health threat while a 15-day window runs); Readiness counts it overdue; signing gives a report started
  while the market was pending its category's deadline.
- J16: a trial's working calendar starts in the sign-up country's time zone, before the sample is seeded.
- J28: a call's time is converted in the time zone chosen for it (Chicago 09:00 is 15:00 UTC in November).

Every check here failed on 0.10.62.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from backend.app.db.models.foundation import Complaint
from backend.app.db.session import SessionLocal
from backend.app.db.tenant_scope import bind_tenant
from backend.app.main import app
from backend.app.oversight.rules import zone_info
from backend.app.reportability import deadlines
from tests.conftest import authenticated_client
from tests.signup_profile import PROFILE
from tests.test_free_trial import PASSWORD, _activation_token, _approved_trial_client, _request_id
from tests.test_market_assessment_api import _acknowledge, _answers, _market, _save, _sign, _url, org  # noqa: F401
from tests.test_reporting_capa_api import WATCH, _complaint

pytestmark = pytest.mark.db

EU_THREAT = dict(EU1="YES", EU2="NO", EU4="YES", EU5="YES", EU6="NO", **{f"EU3{x}": "NO" for x in "ABCDEF"})
US_PENDING = dict(US1="NO", US2A="UNKNOWN", US2B="UNKNOWN", US2C="UNKNOWN", US3="YES", US4="NO", US5="NO", US6="NO")


def _ok(response):
    assert response.status_code == 200, response.text
    return response.json()


def _purge(tenant_id) -> None:
    from backend.app.trial.retention import purge_trial

    with SessionLocal() as db:
        purge_trial(db, tenant_id, "test:one-deadline-cleanup")


@pytest.fixture(scope="module")
def trial():
    user, approval, _ = _approved_trial_client()
    tenant_id = uuid.UUID(approval["tenant_id"])
    try:
        yield {"user": user, "tenant_id": tenant_id}
    finally:
        _purge(tenant_id)


def test_triage_shows_the_events_own_market_first_and_a_signed_conclusion_instead(trial):
    # The sample author has triaged RV-06 and RV-07 (0.10.64, a calm day 0): they are on the list with the finished ones.
    items = {item["ref"]: item for item in _ok(trial["user"].get("/api/v1/triage", params={"show": "all"}))["items"]}
    complaints = _ok(trial["user"].get(f"{WATCH}?show=all&page_size=100"))["items"]
    ref = {item["complaint_identifier"]: item["business_id"] for item in complaints}
    # SAMPLE-RV-06 (US): the FDA deadline comes first; the EU and India deadlines only if also reportable.
    # Triage lists each complaint by its own reference (the business id before 0.10.81).
    rv06 = items["SAMPLE-RV-06"]["deadlines"]
    assert (rv06[0]["market"], rv06[0]["role"]) == ("US", "OWN")
    assert {item["role"] for item in rv06[1:]} == {"IF_ALSO"}
    # SAMPLE-RV-07 (France, EU concluded reportable, 15 days): the signed deadline, as the watch and Reports show it.
    rv07 = items["SAMPLE-RV-07"]["deadlines"][0]
    watched = next(item for item in complaints if item["complaint_identifier"] == "SAMPLE-RV-07")
    assert rv07["market"] == "EU_NI" and rv07["role"] == "SIGNED" and rv07["days"] == 15
    # 0.10.84: in the organization's time zone, as every deadline label (it read Brussels' CET before).
    assert rv07["due_label"] == watched["binding"]["due_label"]
    report = next(
        item
        for item in _ok(trial["user"].get("/api/v1/reports"))["items"]
        if item["complaint_ref"] in ("SAMPLE-RV-07", ref["SAMPLE-RV-07"])
    )
    assert report["due_label"] == rv07["due_label"] and report["days_left"] == rv07["days_left"]


def test_a_signed_shorter_category_binds_the_watch_and_readiness_and_a_started_report(org):  # noqa: F811
    regulatory = org["regulatory"]
    # A French serious injury: the EU 15-day window runs; concluded as a serious public health threat (2 days), signed.
    complaint = _complaint(
        org["tenant_id"], org["product"], country="France", serious_injury=True, death=False, aware_days_ago=4
    )
    before = next(item for item in _ok(regulatory.get(f"{WATCH}?show=all"))["items"] if item["id"] == complaint)
    assert before["binding"]["days"] == 15 and before["state"] == "RUNNING"
    _acknowledge(regulatory, "EU_NI")
    item = _save(regulatory, complaint, "EU_NI", _answers(**EU_THREAT), harm_level="CRITICAL")
    assert item["evaluation"]["report_type"] == "EU_2_DAY"
    assert _sign(regulatory, complaint, "EU_NI", item, "REPORTABLE").status_code == 200
    after = next(item for item in _ok(regulatory.get(f"{WATCH}?show=all"))["items"] if item["id"] == complaint)
    assert after["binding"]["days"] == 2 and after["state"] == "OVERDUE"  # 0.10.62: 15 days, RUNNING
    readiness = next(
        check for check in _ok(regulatory.get("/api/v1/readiness"))["checks"] if check["code"] == "REPORTING_CLOCKS"
    )
    assert complaint in {entry["id"] for entry in readiness["items"]} and readiness["state"] == "CRITICAL"

    # A US report started while the market is pending keeps the 30-day provisional date until the 5-work-day
    # conclusion is signed; then it takes the signed category's deadline (0.10.62: it kept the provisional date).
    us = _complaint(org["tenant_id"], org["product"], country="US", serious_injury=True, death=False, aware_days_ago=1)
    _acknowledge(regulatory, "US")
    pending = _save(regulatory, us, "US", _answers(**US_PENDING), harm_level="CRITICAL")
    assert pending["evaluation"]["suggested"] == "PENDING_INFORMATION"
    started = regulatory.post("/api/v1/reports", json={"complaint_id": us, "market": "US"})
    assert started.status_code == 200, started.text
    listed = next(row for row in _ok(regulatory.get("/api/v1/reports", params={"complaint_id": us}))["items"])
    assert listed["provisional"] and listed["days_left"] >= 28
    item = _save(
        regulatory,
        us,
        "US",
        _answers(**{**US_PENDING, "US2A": "NO", "US2B": "NO", "US2C": "YES", "US6": "YES"}),
        harm_level="CRITICAL",
    )
    assert _sign(regulatory, us, "US", item, "REPORTABLE").status_code == 200
    listed = next(row for row in _ok(regulatory.get("/api/v1/reports", params={"complaint_id": us}))["items"])
    signed = _market(regulatory.get(_url(us)).json(), "US")["current"]
    assert not listed["provisional"] and listed["due_on"] == signed["due_on"] and listed["days_left"] <= 7


def _india_trial() -> tuple[TestClient, uuid.UUID]:
    email = f"trial-{uuid.uuid4().hex[:10]}@example.invalid"
    profile = {**PROFILE, "country": "India"}
    asked = TestClient(app).post(
        "/api/v1/auth/signup",
        json={"email": email, "display_name": "Asha Quality", "organization": "Pune Devices", **profile},
    )
    assert asked.status_code == 200, asked.text
    admin = authenticated_client()
    approval = _ok(admin.post(f"/api/v1/platform-admin/trial-requests/{_request_id(admin, email)}/approve"))
    user = TestClient(app)
    token = _activation_token(approval, email)
    assert user.post("/api/v1/auth/activate-account", json={"token": token, "password": PASSWORD}).status_code == 200
    assert user.post("/api/v1/auth/signin", json={"email": email, "password": PASSWORD}).status_code == 200
    return user, uuid.UUID(approval["tenant_id"])


def test_an_indian_trial_works_in_india_time_and_its_sample_deadlines_say_so():
    user, tenant_id = _india_trial()
    try:
        settings = _ok(user.get("/api/v1/oversight/settings"))
        assert settings["time_zone"] == "Asia/Kolkata"  # 0.10.62: UTC
        watched = _ok(user.get(f"{WATCH}?show=all&page_size=100"))["items"]
        rv10 = next(item for item in watched if item["complaint_identifier"] == "SAMPLE-RV-10")
        assert rv10["binding"]["due_label"].endswith("23:59 IST") and rv10["binding"]["due_zone"] == "Asia/Kolkata"
        with SessionLocal() as db:
            bind_tenant(db, tenant_id)
            row = db.query(Complaint).filter(Complaint.id == uuid.UUID(rv10["id"])).one()
            expected = deadlines.count(row.awareness_timestamp, 15, "CALENDAR", "IN", "Asia/Kolkata")
        assert rv10["binding"]["due_date"] == expected.day.isoformat()
    finally:
        _purge(tenant_id)


def test_a_calls_time_is_converted_in_the_time_zone_chosen_for_it(trial):
    user = trial["user"]
    guide = _ok(user.get("/api/v1/intake/guide"))
    assert "America/Chicago" in guide["zones"] and "Asia/Calcutta" not in guide["zones"]
    day = (datetime.now(timezone.utc) - timedelta(days=2)).date()
    chicago = datetime.combine(day, datetime.min.time().replace(hour=9), zone_info("America/Chicago"))
    body = {
        "kind": "CONTACT",
        "reporter_words": "Caller in Chicago reports the pump alarmed at the start of the morning shift.",
        "received_at": f"{day.isoformat()}T09:00",
        "received_zone": "America/Chicago",
        # B6a G18b: a call two days ago is a back-entry.
        "late_entry_reason": "Entered from the paper log after the outage.",
    }
    logged = _ok(user.post("/api/v1/intake", json=body))
    received = datetime.fromisoformat(logged["times"]["received"]["at"])
    # 09:00 in Chicago: 15:00 UTC in winter (CST), 14:00 UTC in summer (CDT); 0.10.62 stored the browser's 09:00.
    assert received == chicago and received.astimezone(timezone.utc).hour in (14, 15)
    assert logged["times"]["received"]["zone"] == "America/Chicago"
    refused = user.post("/api/v1/intake", json={**body, "received_zone": "Mars/Olympus"})
    assert refused.status_code == 422 and refused.json()["detail"]["code"] == "TIME_ZONE_UNKNOWN"
    # A browser's old name is kept under the current one.
    old = _ok(user.post("/api/v1/intake", json={**body, "received_zone": "Asia/Calcutta"}))
    assert old["times"]["received"]["zone"] == "Asia/Kolkata"


def test_a_follow_up_request_is_due_on_the_day_its_task_is_due_on_the_organizations_calendar(trial):
    from backend.app.db.models.guides_communications import CommunicationEntry
    from backend.app.db.models.workflow import WorkflowTask
    from backend.app.oversight.rules import Calendar

    user = trial["user"]
    settings = _ok(user.get("/api/v1/oversight/settings"))
    keep = {key: settings[key] for key in ("work_days", "holidays", "reminder_hours", "escalation_role")}
    _ok(
        user.put(
            "/api/v1/oversight/settings", json={**keep, "time_zone": "America/New_York", "reason": "Back to New York"}
        )
    )
    unknown = {f"Q{n}": {"answer": "NO"} for n in range(1, 10)} | {"Q4": {"answer": "UNKNOWN"}}
    logged = _ok(
        user.post(
            "/api/v1/intake",
            json={
                "kind": "CONTACT",
                "reporter_words": "Caller is not sure whether the patient was hurt when the pump stopped.",
                "received_zone": "America/New_York",
                "answers": unknown,
            },
        )
    )
    with SessionLocal() as db:
        bind_tenant(db, trial["tenant_id"])
        entry = (
            db.query(CommunicationEntry)
            .filter(
                CommunicationEntry.tenant_id == trial["tenant_id"],
                CommunicationEntry.intake_event_id == uuid.UUID(logged["id"]),
            )
            .one()
        )
        task = db.get(WorkflowTask, entry.task_id)
        # 0.10.62: the UTC date of the task's end (23:59 in New York is 04:59 UTC the next day), one day late.
        assert entry.reply_due_on == Calendar("America/New_York").local_day(task.due_at)
