"""B6a Part A, G18a (B6-01..B6-06): the daily deadline list and its downloads. The list holds the open reporting
deadlines (Oversight's reads), overdue first; never description text; sent once per organization-day from 06:00 local,
also when empty; opt-out except the last recipient; downloads need data.export, are audited and never show another
organization's items; switched off, nothing is queued and the downloads answer 404."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from backend.app import notifications
from backend.app.db.data_plane import open_tenant_data_session
from backend.app.db.models.foundation import AuditEvent, Complaint
from backend.app.db.models.stage2 import OutboxEvent
from backend.app.db.session import SessionLocal
from backend.app.db.tenant_scope import bind_system
from backend.app.oversight import deadline_list
from backend.app.oversight.rules import zone_info
from tests.test_free_trial import _approved_trial_client
from tests.test_reporting_capa_api import _client

# B6b B3: scenarios this file verifies (its register row names it, or it is the group's own test file).
pytestmark = [pytest.mark.db, pytest.mark.requirement("B6-01", "B6-02", "B6-03", "B6-04", "B6-05", "B6-06")]

URL = "/api/v1/oversight"
REAL_IN_TRIAL = deadline_list.in_trial


@pytest.fixture(autouse=True)
def as_pilot(monkeypatch):
    """The tests are about the list where it is on by default (a pilot or a paying organization), run on a trial's
    sample data; the free-trial default (off until tried; owner, 11 Nov) is tested on its own below."""
    monkeypatch.setattr(deadline_list, "in_trial", lambda *_args: False)


@pytest.fixture(scope="module")
def trial():
    from backend.app.trial.retention import purge_trial

    user, approval, email = _approved_trial_client()
    tenant_id = uuid.UUID(approval["tenant_id"])
    try:
        yield {"user": user, "tenant_id": tenant_id, "email": email}
    finally:
        with SessionLocal() as db:
            purge_trial(db, tenant_id, "test:b6a-deadline-list-cleanup")


def _lines(tenant_id, now=None) -> dict:
    with SessionLocal() as control, open_tenant_data_session(tenant_id) as data:
        bind_system(control, "test: deadline list")
        return deadline_list.lines(data, control, tenant_id, now)


def _descriptions(tenant_id) -> list[str]:
    with open_tenant_data_session(tenant_id) as data:
        return [
            row[0]
            for row in data.query(Complaint.description).filter(Complaint.tenant_id == tenant_id)
            if row[0] and len(row[0]) > 20
        ]


def test_the_list_holds_the_open_reporting_deadlines_overdue_first_without_text(trial):  # B6-03, B6-04
    found = _lines(trial["tenant_id"])
    lines = found["lines"]
    assert lines, "the sample has open reporting deadlines"
    # SAMPLE-RV-10's India report is listed with its zone (the sample's oversight calendar).
    india = [line for line in lines if line["ref"] == "SAMPLE-RV-10" and "India" in line["market"]]
    assert india and all(found["zone"] in line["due_label"] or line["due_label"] for line in india)
    # Overdue first, then soonest.
    states = [line["state"] == "OVERDUE" for line in lines]
    assert states == sorted(states, reverse=True)
    dated = [line["due_at"] for line in lines if line["state"] != "OVERDUE" and line["due_at"]]
    assert dated == sorted(dated)
    # Only reporting deadlines and report obligations; never a description, patient or reporter text.
    text = str(lines)
    assert not [words for words in _descriptions(trial["tenant_id"]) if words[:40] in text]
    assert "@" not in text


def test_downloads_need_data_export_are_audited_and_hold_only_this_organization(trial):  # B6-06, B6-45
    user = trial["user"]
    csv = user.get(f"{URL}/deadlines.csv")
    assert csv.status_code == 200, csv.text
    body = csv.content.decode("utf-8-sig")
    assert body.splitlines()[0] == ",".join(deadline_list.CSV_FIELDS) and "SAMPLE-RV-10" in body
    pdf = user.get(f"{URL}/deadlines.pdf")
    assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF")
    assert pdf.headers["content-type"] == "application/pdf"
    with open_tenant_data_session(trial["tenant_id"]) as data:
        audited = [
            row.details.get("format")
            for row in data.query(AuditEvent).filter(
                AuditEvent.tenant_id == trial["tenant_id"], AuditEvent.action == "DEADLINE_LIST_DOWNLOADED"
            )
        ]
    assert sorted(audited) == ["csv", "pdf"]
    # A role without data.export is refused.
    viewer = _client(trial["tenant_id"], "VIEWER")
    assert viewer.get(f"{URL}/deadlines.csv").status_code == 403
    assert viewer.get(f"{URL}/deadlines.pdf").status_code == 403
    # Another organization lists its own sample only, never this one's complaints.
    other, approval, _ = _approved_trial_client()
    try:
        theirs = other.get(f"{URL}/deadlines.csv").content.decode("utf-8-sig")
        mine_ids = {line["complaint_id"] for line in _lines(trial["tenant_id"])["lines"]}
        their_ids = {line["complaint_id"] for line in _lines(uuid.UUID(approval["tenant_id"]))["lines"]}
        assert theirs.splitlines()[0] == body.splitlines()[0] and not (mine_ids & their_ids) - {None}
    finally:
        from backend.app.trial.retention import purge_trial

        with SessionLocal() as db:
            purge_trial(db, uuid.UUID(approval["tenant_id"]), "test:b6a-deadline-list-other")


def _queued(tenant_id) -> list[OutboxEvent]:
    with SessionLocal() as db:
        bind_system(db, "test: deadline list queue")
        return (
            db.query(OutboxEvent)
            .filter(OutboxEvent.tenant_id == tenant_id, OutboxEvent.event_name == deadline_list.EVENT)
            .order_by(OutboxEvent.occurred_at)
            .all()
        )


def _local_noon(tenant_id, days: int) -> datetime:
    zone = zone_info(_lines(tenant_id)["zone"])
    return (datetime.now(zone) + timedelta(days=days)).replace(hour=12, minute=0, second=0, microsecond=0)


def _queue(tenant_id, now) -> bool:
    with SessionLocal() as control, open_tenant_data_session(tenant_id) as data:
        bind_system(control, "test: deadline list queue")
        made = deadline_list.queue_for_tenant(control, data, tenant_id, now)
        control.commit()
        return made


def test_queued_once_per_local_day_from_six_and_sent_to_the_leader(trial, monkeypatch):  # B6-01, B6-04
    from auth import emailer

    tenant_id = trial["tenant_id"]
    zone = _lines(tenant_id)["zone"]
    local = datetime.now(zone_info(zone)) + timedelta(days=30)
    early = local.replace(hour=5, minute=59, second=0, microsecond=0)
    six = local.replace(hour=6, minute=0, second=0, microsecond=0)
    assert _queue(tenant_id, early.astimezone(timezone.utc)) is False  # before 06:00 local
    assert _queue(tenant_id, six.astimezone(timezone.utc)) is True
    assert _queue(tenant_id, (six + timedelta(hours=5)).astimezone(timezone.utc)) is False  # once that day
    (event,) = [row for row in _queued(tenant_id) if row.payload["day"] == six.date().isoformat()]
    payload = event.payload
    assert "@" not in str(payload) and payload["zone"] == zone and payload["lines"]
    assert set(payload["lines"][0]) == {
        "ref",
        "market",
        "owed",
        "due_at",
        "due_label",
        "state",
        "state_label",
        "owner_id",
    }
    sent = []
    monkeypatch.setattr(
        emailer, "send_deadline_list", lambda recipient, **details: sent.append((recipient, details)) or "SENT"
    )
    with SessionLocal() as db:
        bind_system(db, "test: deadline list delivery")
        assert notifications.handle_event(db, deadline_list.EVENT, payload) is True
    assert [recipient for recipient, _ in sent] == [trial["email"]]  # the trial's Leader
    assert sent[0][1]["day"] == six.date().isoformat() and len(sent[0][1]["lines"]) == len(payload["lines"])


def test_an_empty_list_is_still_sent(trial, monkeypatch):  # B6-02
    from auth import emailer

    monkeypatch.setattr(deadline_list.service, "due_items", lambda *args, **kwargs: [])
    monkeypatch.setattr(deadline_list, "_other_lines", lambda *args, **kwargs: [])
    assert _queue(trial["tenant_id"], _local_noon(trial["tenant_id"], 60)) is True
    event = _queued(trial["tenant_id"])[-1]
    assert event.payload["lines"] == []
    captured = {}

    def fake_send(recipient, message):
        captured["subject"], captured["items"] = message.subject, message.items
        return "SENT"

    monkeypatch.setattr(emailer, "_send", fake_send)
    with SessionLocal() as db:
        bind_system(db, "test: empty deadline list")
        notifications.handle_event(db, deadline_list.EVENT, event.payload)
    assert captured["subject"].startswith("0 open reporting deadlines today") and captured["items"] == ()


def test_opt_out_except_the_last_recipient(trial):  # B6-05
    user = trial["user"]
    shown = user.get("/api/v1/me/email-preferences").json()
    assert shown["daily_deadlines"] is True and shown["daily_deadlines_eligible"] is True
    assert shown["daily_deadlines_locked"] is True  # the trial's only Leader
    refused = user.put("/api/v1/me/email-preferences", json={"daily_deadlines": False})
    assert refused.status_code == 409 and refused.json()["detail"]["code"] == "LAST_DEADLINE_RECIPIENT"
    # A second Leader joins: now the first may switch it off, and gets none; the colleague is then the last.
    colleague = _client(trial["tenant_id"], "LEADER")
    off = user.put("/api/v1/me/email-preferences", json={"daily_deadlines": False})
    assert off.status_code == 200 and off.json()["daily_deadlines"] is False
    with SessionLocal() as db:
        bind_system(db, "test: deadline recipients")
        assert trial["email"] not in deadline_list.recipients(db, trial["tenant_id"])
        assert len(deadline_list.recipients(db, trial["tenant_id"])) == 1
    assert colleague.put("/api/v1/me/email-preferences", json={"daily_deadlines": False}).status_code == 409
    # The weekly readiness choice is untouched by the daily one, and audited on its own.
    assert user.get("/api/v1/me/email-preferences").json()["weekly_readiness"] is True
    assert user.put("/api/v1/me/email-preferences", json={"daily_deadlines": True}).json()["daily_deadlines"] is True
    # A Viewer does not receive it.
    viewer = _client(trial["tenant_id"], "VIEWER").get("/api/v1/me/email-preferences").json()
    assert viewer["daily_deadlines_eligible"] is False


def test_a_free_trial_is_told_apart_from_a_customer_organization(trial):  # owner, 11 Nov
    from tests.test_auth_hardening import _tenant

    with SessionLocal() as db:
        bind_system(db, "test: trial or not")
        assert REAL_IN_TRIAL(db, trial["tenant_id"]) is True
        assert REAL_IN_TRIAL(db, _tenant(db).id) is False  # the synthetic customer organization, no trial plan


def test_in_a_free_trial_the_list_is_off_until_the_person_tries_it(monkeypatch):  # owner, 11 Nov
    from backend.app.trial.retention import purge_trial

    monkeypatch.setattr(deadline_list, "in_trial", REAL_IN_TRIAL)
    user, approval, email = _approved_trial_client()
    tenant_id = uuid.UUID(approval["tenant_id"])
    try:
        shown = user.get("/api/v1/me/email-preferences").json()
        assert shown["daily_deadlines"] is False and shown["daily_deadlines_trial"] is True
        assert shown["daily_deadlines_locked"] is False and shown["daily_deadlines_eligible"] is True
        with SessionLocal() as db:
            bind_system(db, "test: deadline recipients")
            assert deadline_list.recipients(db, tenant_id) == []
        assert _queue(tenant_id, _local_noon(tenant_id, 1)) is False and not _queued(tenant_id)
        # The downloads are always there.
        assert user.get(f"{URL}/deadlines.csv").status_code == 200
        # "Try the daily list": on for this person, who then gets it, and may switch it off again (no last-recipient
        # lock where the list is off by default).
        tried = user.put("/api/v1/me/email-preferences", json={"daily_deadlines": True})
        assert tried.status_code == 200 and tried.json()["daily_deadlines"] is True
        with SessionLocal() as db:
            bind_system(db, "test: deadline recipients")
            assert deadline_list.recipients(db, tenant_id) == [email]
        assert _queue(tenant_id, _local_noon(tenant_id, 1)) is True
        off = user.put("/api/v1/me/email-preferences", json={"daily_deadlines": False})
        assert off.status_code == 200 and off.json()["daily_deadlines"] is False
    finally:
        with SessionLocal() as db:
            purge_trial(db, tenant_id, "test:b6a-deadline-list-trial-default")


def test_the_switch_off_on_off(trial, monkeypatch):  # B6-46
    user = trial["user"]
    later = _local_noon(trial["tenant_id"], 90)
    for state in ("off", "on", "off"):
        monkeypatch.setenv(deadline_list.SWITCH, state)
        on = state == "on"
        assert (user.get(f"{URL}/deadlines.csv").status_code == 200) is on
        assert user.get("/api/v1/session/context").json()["b6"]["deadline_list"] is on
        assert _queue(trial["tenant_id"], later) is on
        later += timedelta(days=1)


def test_a_source_that_cannot_be_read_makes_the_list_say_incomplete(trial, monkeypatch):  # review finding 3
    real = deadline_list.service.due_items

    def failing(db, control_db, tenant_id, now=None, failed=None):
        found = real(db, control_db, tenant_id, now, failed)
        failed.append("reports")
        return found

    monkeypatch.setattr(deadline_list.service, "due_items", failing)
    body = trial["user"].get(f"{URL}/deadlines.csv").content.decode("utf-8-sig")
    assert body.splitlines()[1].startswith("INCOMPLETE") and "reports could not be read" in body
    with pytest.raises(RuntimeError, match="incomplete"):  # never e-mailed as if complete; the job alerts and retries
        _queue(trial["tenant_id"], _local_noon(trial["tenant_id"], 120))
