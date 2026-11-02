"""0.10.74, Release C part C2: list views and record pages.

- Each list view of the one complaint list (``GET /api/v1/complaints?work=1&view=…``) holds exactly the complaints its
  rule names, read from the same dated items, watch, requests and signatures as the complaint page, Home and Oversight.
- For SAMPLE-RV-06, SAMPLE-RV-08 and SAMPLE-RV-11 the record page shows the same deadline, owner, stage and next step
  as the list views, Home (Oversight's dated items) and Oversight's event row.
- Related lists the linked records; Activity is the complaint's own audit events in plain words, nothing else.
- Records leads with the latest record the person signed (every organization), from the server.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from backend.app.db.session import SessionLocal
from tests.test_flagship_walkthrough import _answers_from_record
from tests.test_free_trial import PASSWORD, _approved_trial_client
from tests.test_market_assessment_api import _acknowledge, _save, _sign
from tests.test_sample_story_days import FLAGSHIP_US

pytestmark = pytest.mark.db

EVENTS = "/api/v1/oversight/events"
LIST = "/api/v1/complaints"
SAMPLE = ("SAMPLE-RV-06", "SAMPLE-RV-08", "SAMPLE-RV-11")
WEEK_HOURS = 7 * 24


def _ok(response, status: int = 200):
    assert response.status_code == status, response.text
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
            purge_trial(db, tenant_id, "test:release-c2-cleanup")


def _view(user, view: str) -> list[dict]:
    return _ok(user.get(LIST, params={"work": "1", "view": view, "page_size": 200}))["items"]


def _dated(user) -> list[dict]:
    """Every dated item of every complaint, as each complaint's own page lists them (its work line)."""
    rows = _ok(user.get(LIST, params={"work": "1", "page_size": 200}))["items"]
    return [{**item, "complaint_id": row["id"]} for row in rows for item in row["work"]["due"]]


@pytest.mark.parametrize("ref", SAMPLE)
def test_the_record_page_shows_the_same_deadline_owner_and_next_step_as_the_lists_home_and_oversight(trial, ref):
    user = trial["user"]
    page = _ok(user.get(f"{EVENTS}/{ref}"))
    work, complaint_id = page["work"], page["event"]["complaint_id"]
    # The list views: the complaint's row carries the page's own work line wherever it is listed.
    listed = {view: {row["id"]: row for row in _view(user, view)} for view in ("open", "due-week", "legal-week")}
    assert listed["open"][complaint_id]["work"] == work
    for rows in listed.values():
        if complaint_id in rows:
            assert rows[complaint_id]["work"] == work
    # Due this week and legal clocks this week hold it exactly when its own dated items say so.
    soon = [item for item in work["due"] if item["hours_left"] <= WEEK_HOURS]
    assert (complaint_id in listed["due-week"]) == any(item["state"] != "OVERDUE" for item in soon)
    assert (complaint_id in listed["legal-week"]) == any(
        item["category"] in ("REPORTING", "OBLIGATION") for item in soon
    )
    # Home counts and lists Oversight's dated items (home.ts): the same deadlines, each with its own title.
    home = [item for item in _ok(user.get("/api/v1/oversight", params={"show": "all"}))["items"]]
    mine = sorted((item["due_at"], item["title"]) for item in home if item["complaint_id"] == complaint_id)
    assert mine == sorted((item["due_at"], item["title"]) for item in work["due"])
    # Oversight's event row: the same owner, stage and next step as the page's header and rail.
    event = next(
        (item for item in _ok(user.get("/api/v1/oversight"))["events"] if item["complaint_id"] == complaint_id), None
    )
    if event is not None:
        assert (event["owner_name"], event["stage"], event["next"]) == (work["owner_name"], work["stage"], work["next"])
    # The rail's next step is the header's next action; its nearest deadline the list's urgency.
    action = page["summary"]["next_action"]
    assert (action["label"] if action else None) == work["next"]
    if work["due"]:
        assert page["summary"]["nearest_deadline"]["due_at"] == work["due"][0]["due_at"]
    # Related: one group per kind of linked record, in the page's order, each in plain lines.
    assert [group["key"] for group in page["related"]] == [
        "communications",
        "assessments",
        "service",
        "investigations",
        "reports",
        "decisions",
    ]
    assert all(group["lines"] and all(isinstance(line, str) for line in group["lines"]) for group in page["related"])


def test_each_list_view_holds_exactly_the_complaints_its_rule_names(trial):
    user = trial["user"]
    everything = _ok(user.get(LIST, params={"work": "1", "page_size": 200}))
    closed = ("closed", "cancelled", "canceled", "completed", "done")
    assert {row["id"] for row in _view(user, "open")} == {
        row["id"] for row in everything["items"] if str(row["status"] or "").lower() not in closed
    }
    dated = _dated(user)
    due_week = {
        item["complaint_id"] for item in dated if item["hours_left"] <= WEEK_HOURS and item["state"] != "OVERDUE"
    }
    assert {row["id"] for row in _view(user, "due-week")} == due_week
    legal = {
        item["complaint_id"]
        for item in dated
        if item["hours_left"] <= WEEK_HOURS and item["category"] in ("REPORTING", "OBLIGATION")
    }
    assert {row["id"] for row in _view(user, "legal-week")} == legal
    # Most urgent first: each row's nearest qualifying deadline is no later than the next row's.
    firsts = [
        min(
            item["due_at"]
            for item in row["work"]["due"]
            if item["hours_left"] <= WEEK_HOURS and item["state"] != "OVERDUE"
        )
        for row in _view(user, "due-week")
    ]
    assert firsts == sorted(firsts)
    watch = _ok(user.get("/api/v1/complaints/reportability", params={"show": "open", "page_size": 200}))["items"]
    assert {row["id"] for row in _view(user, "reportability")} == {str(item["id"]) for item in watch}
    requests = _ok(user.get("/api/v1/communications"))["items"]
    waiting = {item["complaint_id"] for item in requests if item["status"] == "OPEN" and item.get("complaint_id")}
    assert {row["id"] for row in _view(user, "waiting-reporter")} == waiting
    # The sample's views are not empty, so these checks compare something.
    assert due_week or legal
    assert watch
    # An unknown view is refused, never read as "all".
    refused = user.get(LIST, params={"work": "1", "view": "everything"})
    assert refused.status_code == 422 and refused.json()["detail"]["code"] == "UNKNOWN_LIST_VIEW"


def test_signing_puts_the_complaint_in_signed_this_month_its_activity_and_the_person_s_latest_record(trial):
    user = trial["user"]
    page = _ok(user.get(f"{EVENTS}/SAMPLE-RV-11"))
    complaint = page["event"]["complaint_id"]
    before = _ok(user.get("/api/v1/oversight/latest-signed"))["record"]
    assert before is None  # the trial owner has signed nothing yet: the sample's signatures are its author's
    # The triage, then the US conclusion, signed by the trial owner.
    people = _ok(user.get("/api/v1/triage"))["people"]
    owner = next(person["id"] for person in people)
    _ok(
        user.post(
            f"/api/v1/triage/COMPLAINT/{complaint}/record",
            json={
                "severity": "NEGLIGIBLE",
                "event_owner": owner,
                "triage_owner": owner,
                "immediate_action": "Sent for service.",
            },
        )
    )
    detail = _ok(user.get(f"/api/v1/complaints/{complaint}/market-assessments"))
    _acknowledge(user, "US")
    answers, _ = _answers_from_record(detail, "US", FLAGSHIP_US)
    saved = _save(user, complaint, "US", answers, harm_level=detail["severity_level"])
    assert _sign(user, complaint, "US", saved, "REPORTABLE", password=PASSWORD).status_code == 200

    assert complaint in {row["id"] for row in _view(user, "signed-month")}
    latest = _ok(user.get("/api/v1/oversight/latest-signed"))["record"]
    assert latest["what"] == "United States (FDA) conclusion: reportable"
    assert latest["complaint"] == {"id": complaint, "ref": "SAMPLE-RV-11"}
    assert latest["signed_by"] and latest["investigation"] is None
    signed_at = datetime.fromisoformat(latest["signed_at"])
    assert datetime.now(timezone.utc) - signed_at < timedelta(minutes=5)

    activity = _ok(user.get(f"{EVENTS}/SAMPLE-RV-11/activity"))
    titles = [item["title"] for item in activity["items"]]
    assert "Market conclusion signed" in titles and "Triage record completed" in titles
    signed = next(item for item in activity["items"] if item["title"] == "Market conclusion signed")
    assert signed["who"] == latest["signed_by"]
    # Newest first, the record's own received and awareness times last, marked as from the record.
    dated = [item["at"] for item in activity["items"] if not item.get("from_record")]
    assert dated == sorted(dated, reverse=True)
    assert activity["items"][-1]["from_record"] and "awareness" in activity["items"][-1]["title"].lower()
    # Plain words only: no network address, browser or raw detail leaves the server.
    assert all(set(item) <= {"at", "title", "who", "reason", "from_record"} for item in activity["items"])
    assert not any("_" in item["title"] and item["title"].upper() == item["title"] for item in activity["items"])
    # Related names the signed conclusion.
    related = {group["key"]: group for group in _ok(user.get(f"{EVENTS}/SAMPLE-RV-11"))["related"]}
    assert any(line.startswith("United States (FDA): Reportable, signed") for line in related["assessments"]["lines"])


def test_activity_and_the_latest_record_stay_in_their_organization(trial):
    other, _, _ = _approved_trial_client()
    ref = _ok(trial["user"].get(f"{EVENTS}/SAMPLE-RV-11"))["event"]["complaint_id"]
    assert other.get(f"{EVENTS}/{ref}/activity").status_code == 404
    assert _ok(other.get("/api/v1/oversight/latest-signed"))["record"] is None
