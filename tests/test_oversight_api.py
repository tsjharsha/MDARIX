"""0.10.60, T-G25, T-G9 and T-G28 through the API as a trial user (migration tr07): the working calendar, who is told
when an item is due soon or overdue (owner, backup while away, the escalation role, nobody else), the sample's
reminders and escalations with read state, an absence routing them to the backup, the oversight view with filters and
its CSV, the event's owner, checklist, signed "ready to close in the QMS" and the event decision record."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone

import pytest

from backend.app import feature_set
from backend.app.oversight import rules
from backend.app.oversight.rules import Calendar
from tests.test_free_trial import PASSWORD, _approved_trial_client
from tests.test_reporting_capa_api import _client

# Database tests by default, its pure tests marked unit (tests/conftest.py DB_WITHOUT_GOLDEN).

VIEW = "/api/v1/oversight"


def _ok(response):
    assert response.status_code == 200, response.text
    return response.json()


@pytest.fixture(scope="module")
def trial():
    from backend.app.db.session import SessionLocal
    from backend.app.trial.retention import purge_trial

    from backend.app.db.models.foundation import AuthUser

    user, approval, email = _approved_trial_client()
    tenant_id = uuid.UUID(approval["tenant_id"])
    with SessionLocal() as db:
        user_id = str(db.query(AuthUser.id).filter(AuthUser.username == email).scalar())
    try:
        yield {"user": user, "tenant_id": tenant_id, "user_id": user_id}
    finally:
        with SessionLocal() as db:
            purge_trial(db, tenant_id, "test:oversight-cleanup")


# --------------------------------------------------------------------------------------------- the rules


@pytest.mark.unit
def test_the_working_calendar_skips_days_off_in_the_organizations_time_zone():
    diwali = date(2026, 11, 9)
    calendar = Calendar("Asia/Kolkata", (0, 1, 2, 3, 4), frozenset({diwali}))
    friday = datetime(2026, 11, 6, 10, 0, tzinfo=timezone.utc)  # 15:30 in India
    # The next working day after Friday is Tuesday: the weekend and the holiday do not count.
    end = calendar.working_day_end(friday, 1)
    assert end == datetime(2026, 11, 10, 23, 59, 59, tzinfo=calendar.tz).astimezone(timezone.utc)
    # Friday 23:30 in India plus one working hour ends on Tuesday 00:30.
    late = datetime(2026, 11, 6, 18, 0, tzinfo=timezone.utc)
    assert calendar.working_hour_after(late).astimezone(calendar.tz).isoformat().startswith("2026-11-10T00:30")
    # The default calendar is the one before 0.10.60: Monday to Friday in UTC.
    assert Calendar().working_day_end(datetime(2026, 11, 6, 10, tzinfo=timezone.utc), 1).date() == date(2026, 11, 9)
    assert rules.calendar_problem("Mars/Olympus", [0], []) == "Choose the time zone from the list"
    assert rules.calendar_problem("UTC", [], []) == "Choose at least one working weekday"
    assert rules.calendar_problem("UTC", [0], [{"date": diwali}, {"date": diwali}]).endswith("listed twice")


@pytest.mark.unit
def test_the_chain_reminds_the_owner_or_the_backup_and_escalates_at_the_due_time():
    today = date(2026, 11, 2)
    active = {"owner", "backup", "head", "deputy"}
    item = {"owner_id": "owner", "backup_id": None}
    assert rules.recipients(item, rules.LATER, active, [], ["head"], today) == []
    assert rules.recipients(item, rules.DUE_SOON, active, [], ["head"], today) == [("REMINDER", "owner", "OWNER")]
    overdue = rules.recipients(item, rules.OVERDUE, active, [], ["head", "owner"], today)
    # The owner is skipped in the escalation: the head of QA is told.
    assert overdue == [("REMINDER", "owner", "OWNER"), ("ESCALATION", "head", "ESCALATION_ROLE")]
    away = [{"user_id": "owner", "backup_id": "backup", "starts_on": today, "ends_on": today}]
    covered = rules.recipients(item, rules.OVERDUE, active, away, ["head"], today)
    assert covered == [
        ("REMINDER", "backup", "COVERING"),
        ("ESCALATION", "backup", "COVERING"),
        ("ESCALATION", "head", "ESCALATION_ROLE"),
    ]
    # An absence that is over routes nothing.
    assert rules.recipients(item, rules.DUE_SOON, active, away, ["head"], today + timedelta(days=1))[0][1] == "owner"
    # A triage record's own backup is told at the due time.
    triage = rules.recipients({"owner_id": "owner", "backup_id": "deputy"}, rules.OVERDUE, active, [], [], today)
    assert ("ESCALATION", "deputy", "BACKUP") in triage
    # Nobody else: the owner is told so, so the deadline never passes silently.
    alone = rules.recipients(item, rules.OVERDUE, {"owner"}, [], ["owner"], today)
    assert alone == [("REMINDER", "owner", "OWNER"), ("ESCALATION", "owner", "NO_ONE_ELSE")]
    # No owner, or one who can no longer sign in: the escalation role at once.
    assert rules.recipients({"owner_id": None}, rules.DUE_SOON, active, [], ["head"], today) == [
        ("REMINDER", "head", "NO_OWNER")
    ]
    assert rules.recipients({"owner_id": "gone"}, rules.DUE_SOON, active, [], ["head"], today)[0][2] == "OWNER_INACTIVE"


# --------------------------------------------------------------------------------------------- through the API


def test_the_sample_shows_an_escalation_a_reminder_and_an_away_colleague(trial):
    user = trial["user"]
    mine = _ok(user.get(f"{VIEW}/alerts"))
    by_ref = {(item["ref"], item["category"]): item for item in mine["items"]}
    reply = by_ref[("SAMPLE-RV-08", "COMMUNICATION")]
    assert reply["tier"] == "ESCALATION" and reply["state"] == "OVERDUE" and reply["reason"] == "NO_ONE_ELSE"
    assert len(reply["ids"]) == 2  # the reminder and the escalation, one line
    # 0.10.64, a calm day 0: SAMPLE-CALL-02's QMS task is due later (it was escalated, "overdue"), and the only
    # triage reminders are the story's two steps.
    assert ("SAMPLE-CALL-02", "TRIAGE") not in by_ref
    assert {ref for ref, category in by_ref if category == "TRIAGE"} == {"SAMPLE-URG-01", "SAMPLE-RV-11"}
    assert mine["unread"] == len(mine["items"]) == 3 and mine["escalations"] == 1
    assert mine["absences"][0]["user_name"] == "MDARIX sample author" and "never" in mine
    # Reading never resolves an alert.
    assert _ok(user.post(f"{VIEW}/alerts/read", json={"ids": reply["ids"]}))["read"] == 2
    again = _ok(user.get(f"{VIEW}/alerts"))
    assert next(item for item in again["items"] if item["id"] == reply["id"])["read"] is True
    assert again["unread"] == mine["unread"] - 1

    view = _ok(user.get(VIEW))
    assert view["overdue"] == 1 and view["due_soon"] == 2
    rv08 = next(item for item in view["items"] if item["ref"] == "SAMPLE-RV-08" and item["category"] == "COMMUNICATION")
    assert rv08["owner"] and rv08["escalated_to"] and rv08["hours_left"] < 0
    assert view["away"][0]["backup_id"] == trial["user_id"]
    assert "invite a colleague" in view["staffing"]
    # The sample author's items show the absence and who covers it.
    everything = _ok(user.get(VIEW, params={"show": "all"}))
    covered = [item for item in everything["items"] if item["away"]]
    assert covered and all(item["owner"] == "MDARIX sample author" for item in covered)
    # Filters by product, market and category.
    products = everything["filters"]["products"]
    assert products and all(
        item["product"] == products[0]
        for item in _ok(user.get(VIEW, params={"show": "all", "product": products[0]}))["items"]
    )
    us = _ok(user.get(VIEW, params={"show": "all", "market": "US"}))["items"]
    assert us and all(item["market"] == "US" for item in us)
    triage = _ok(user.get(VIEW, params={"category": "TRIAGE"}))["items"]
    assert triage and all(item["category"] == "TRIAGE" for item in triage)
    exported = user.get(f"{VIEW}/export.csv", params={"show": "all"})
    assert exported.status_code == 200 and exported.text.lstrip("﻿").startswith("category,title,ref")
    assert "SAMPLE-RV-08" in exported.text and "ward nurse" not in exported.text.split("\n", 1)[0]
    # Events: RV-08 not ready, RT-03's checklist clear, the closed sample complaints flagged.
    events = {item["ref"]: item for item in view["events"]}
    assert events["SAMPLE-RV-08"]["state"] == "NOT_READY" and events["SAMPLE-RV-08"]["blocked"] >= 2
    assert events["SAMPLE-RT-03"]["state"] == "READY_TO_SIGN" and events["SAMPLE-RT-03"]["owner_id"] == trial["user_id"]
    assert view["event_counts"]["CLOSED_BEFORE_READY"] >= 1


def test_the_working_calendar_is_set_by_quality_and_used_by_the_communications_log(trial):
    user = trial["user"]
    body = _ok(user.get(f"{VIEW}/settings"))
    # The calendar starts in the sign-up country's time zone (the test sign-up says United States; 0.10.63, J16).
    assert body["time_zone"] == "America/New_York" and body["work_days"] == [0, 1, 2, 3, 4]
    # One name per zone: the current one, never an old alias beside it.
    assert (
        "Asia/Kolkata" in body["zones"] and "Asia/Calcutta" not in body["zones"] and "US/Eastern" not in body["zones"]
    )
    wrong = user.put(f"{VIEW}/settings", json={**_settings(), "time_zone": "Mars/Olympus"})
    assert wrong.status_code == 422 and wrong.json()["detail"]["code"] == "SETTINGS_INVALID"
    # B6a G10: the calendar changes only with a reason (it changes reminders, not legal clocks); switched off, as before.
    no_reason = user.put(f"{VIEW}/settings", json={**_settings(), "reason": "  "})
    if feature_set.switched_on("MDARIX_B6_CHANGE_REASON"):
        assert no_reason.status_code == 422 and no_reason.json()["detail"]["code"] == "CHANGE_REASON_REQUIRED"
    else:
        assert no_reason.status_code == 200, no_reason.text
    # A browser's old name is stored under the current one.
    saved = _ok(user.put(f"{VIEW}/settings", json={**_settings(), "time_zone": "Asia/Calcutta"}))
    assert saved["time_zone"] == "Asia/Kolkata" and saved["holidays"][0] == {"date": "2026-11-09", "name": "Diwali"}
    assert saved["reminder_hours"] == 48 and saved["escalation_role_label"]
    log = _ok(user.get("/api/v1/communications"))
    assert log["s4"]["in_mdarix"] >= 1  # still counted, now on the organization's calendar
    _ok(
        user.put(
            f"{VIEW}/settings",
            json={**_settings(), "time_zone": "America/New_York", "holidays": [], "reminder_hours": 24},
        )
    )


def _settings() -> dict:
    return {
        "time_zone": "Asia/Kolkata",
        "work_days": [0, 1, 2, 3, 4],
        "holidays": [{"date": "2026-11-09", "name": "Diwali"}],
        "reminder_hours": 48,
        "escalation_role": "LEADER",
        "reason": "Calendar of the India site",
    }


def test_an_absence_sends_the_owners_alerts_to_the_backup(trial):
    user = trial["user"]
    # Today in the organization's time zone, as the server counts absences (the machine's own date read a day ahead
    # in India before 05:30, and the test failed every night).
    zone = _ok(user.get(f"{VIEW}/settings"))["time_zone"]
    today = datetime.now(rules.zone_info(zone)).date()
    alone = user.post(
        f"{VIEW}/absences", json={"starts_on": today.isoformat(), "ends_on": today.isoformat(), "backup_id": "nobody"}
    )
    assert alone.status_code == 422 and alone.json()["detail"]["code"] == "ABSENCE_INVALID"
    colleague = _client(trial["tenant_id"], "LEADER", "Priya Backup")
    people = _ok(user.get(f"{VIEW}/alerts"))["people"]
    backup = next(person["id"] for person in people if person["name"] == "Priya Backup")
    recorded = _ok(
        user.post(
            f"{VIEW}/absences",
            json={
                "starts_on": today.isoformat(),
                "ends_on": (today + timedelta(days=3)).isoformat(),
                "backup_id": backup,
                "note": "Training course",
            },
        )
    )
    mine = next(item for item in recorded["items"] if item["user_id"] == trial["user_id"])
    assert mine["backup_name"] == "Priya Backup"
    covering = _ok(colleague.get(f"{VIEW}/alerts"))
    reply = next(
        item for item in covering["items"] if item["ref"] == "SAMPLE-RV-08" and item["category"] == "COMMUNICATION"
    )
    assert reply["reason"] == "COVERING" and reply["tier"] == "ESCALATION"
    # The owner, away, is not reminded; the item itself is unchanged (still the owner's, still open).
    assert not any(
        item["ref"] == "SAMPLE-RV-08" and item["category"] == "COMMUNICATION"
        for item in _ok(user.get(f"{VIEW}/alerts"))["items"]
    )
    log = _ok(user.get("/api/v1/communications"))
    entry = next(item for item in log["items"] if item["complaint_ref"] and item["party"]["type"] == "REPORTER")
    assert entry["status"] == "OPEN" and entry["owner_id"] == trial["user_id"]
    # Only the person themself cancels their absence; the alerts go back to the owner.
    assert colleague.post(f"{VIEW}/absences/{mine['id']}/cancel").status_code == 404
    _ok(user.post(f"{VIEW}/absences/{mine['id']}/cancel"))
    back = _ok(user.get(f"{VIEW}/alerts"))
    assert any(item["ref"] == "SAMPLE-RV-08" and item["category"] == "COMMUNICATION" for item in back["items"])
    # The sample story's escalations go to the trial owner; a colleague holding the escalation role does not inherit
    # them (0.10.64, J2: on 0.10.63 the colleague was told, ESCALATION_ROLE).
    assert not any(
        item["ref"] == "SAMPLE-RV-08" and item["category"] == "COMMUNICATION"
        for item in _ok(colleague.get(f"{VIEW}/alerts"))["items"]
    )


def test_the_event_owner_signs_ready_to_close_and_files_the_decision_record(trial):
    user = trial["user"]
    view = _ok(user.get(VIEW, params={"show": "all"}))
    events = {item["ref"]: item for item in view["events"]}
    blocked = _ok(user.get(f"{VIEW}/events/{events['SAMPLE-RV-08']['complaint_id']}"))
    assert blocked["you_are_owner"] and blocked["blocked"] >= 2
    codes = {item["code"]: item for item in blocked["checklist"]}
    assert codes["MARKETS"]["result"] == "BLOCKED" and codes["REQUESTS"]["result"] == "BLOCKED"
    assert codes["MARKETS"]["action"].startswith("Sign the United States")
    assert codes["REQUESTS"]["action"] == "Answer or close the open information request"
    assert events["SAMPLE-RV-08"]["next"] == "Sign the United States (FDA) market assessment"
    assert codes["REQUESTS"]["opens"]["tab"].startswith("Communications?complaint=")
    assert [stage["code"] for stage in blocked["stages"]][-1] == "CLOSED" and blocked["summary"]["next_action"][
        "label"
    ] == "Sign the United States (FDA) market assessment"
    refused = user.post(f"{VIEW}/events/{blocked['event']['complaint_id']}/ready", json={"password": PASSWORD})
    assert refused.status_code == 422 and refused.json()["detail"]["code"] == "REASON_REQUIRED"

    complaint_id = events["SAMPLE-RT-03"]["complaint_id"]
    clear = _ok(user.get(f"{VIEW}/events/{complaint_id}"))
    assert clear["blocked"] == 0 and clear["state"] == "READY_TO_SIGN"
    assert any(entry["kind"] == "Disposition" for entry in clear["decision_record"]["entries"])
    other = _client(trial["tenant_id"], "LEADER", "Not The Owner")
    assert other.post(f"{VIEW}/events/{complaint_id}/ready", json={"password": PASSWORD}).status_code == 403
    wrong = user.post(f"{VIEW}/events/{complaint_id}/ready", json={"password": "not-the-password"})
    assert wrong.status_code == 403
    assert user.put(f"{VIEW}/events/{complaint_id}/filing", json={"reference": "QMS-1"}).status_code == 409
    signed = _ok(user.post(f"{VIEW}/events/{complaint_id}/ready", json={"password": PASSWORD}))
    assert signed["state"] == "NOT_FILED" and signed["ready"]["state"] == "READY" and signed["ready"]["version"] == 1
    last = signed["decision_record"]["entries"][-1]
    assert last["kind"] == "Ready to close in the QMS" and "ready to close in the QMS" in last["meaning"]
    assert len(signed["decision_record"]["sha256"]) == 64
    filed = _ok(user.put(f"{VIEW}/events/{complaint_id}/filing", json={"reference": "QMS-CMP-2026-0311"}))
    assert filed["state"] == "FILED" and filed["decision_record"]["filed"]["reference"] == "QMS-CMP-2026-0311"
    pdf = user.get(f"{VIEW}/events/{complaint_id}/decision-record.pdf")
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
    # Naming another owner is recorded; only that person signs from then on.
    people = {person["name"]: person["id"] for person in _ok(user.get(f"{VIEW}/events/{complaint_id}"))["people"]}
    moved = _ok(user.put(f"{VIEW}/events/{complaint_id}/owner", json={"owner_id": people["Not The Owner"]}))
    assert moved["event"]["owner_name"] == "Not The Owner" and not moved["you_are_owner"]
    assert user.put(f"{VIEW}/events/{complaint_id}/owner", json={"owner_id": "someone"}).status_code == 422
    assert user.get(f"{VIEW}/events/{uuid.uuid4()}").status_code == 404


def test_the_sweep_resolves_alerts_whose_item_is_done(trial):
    from backend.app.db.models.oversight import DueAlert
    from backend.app.db.session import SessionLocal
    from backend.app.db.tenant_scope import bind_tenant
    from backend.app.oversight import service

    user = trial["user"]
    log = _ok(user.get("/api/v1/communications"))
    entry = next(item for item in log["items"] if item["complaint_ref"] and item["party"]["type"] == "REPORTER")
    _ok(user.post(f"/api/v1/communications/{entry['id']}/close", json={"status": "CLOSED", "note": "Not needed now."}))
    with SessionLocal() as db:
        bind_tenant(db, trial["tenant_id"])
        first = service.sweep(db, db, trial["tenant_id"])
        again = service.sweep(db, db, trial["tenant_id"])
        db.commit()
        assert again == {"raised": 0, "resolved": 0} and first["raised"] >= 0  # idempotent
        open_rv08 = (
            db.query(DueAlert)
            .filter(
                DueAlert.tenant_id == trial["tenant_id"],
                DueAlert.ref == "SAMPLE-RV-08",
                DueAlert.category == "COMMUNICATION",
                DueAlert.resolved_at.is_(None),
            )
            .count()
        )
        assert open_rv08 == 0
