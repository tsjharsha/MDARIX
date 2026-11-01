"""0.10.59, T-G30: the external communications log through the API as a trial user (migration tr06): the sample's
entries, requests with owner, due date and attempts, the move to the second contact and "unresolved after attempts",
the reply, Unknown answers raising a request, the S4 count, My Work, Readiness and the decision brief, nothing sent,
tenant isolation and sample removal."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from backend.app.communications import rules
from backend.app.db.models.foundation import Complaint
from backend.app.db.models.guides_communications import CommunicationEntry, DecisionGuideVersion, ExternalParty
from backend.app.db.session import RuntimeSessionLocal, SessionLocal, runtime_role_active
from backend.app.db.tenant_scope import bind_tenant
from tests.test_free_trial import _approved_trial_client

pytestmark = pytest.mark.db

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
        yield {"user": user, "tenant_id": tenant_id, "user_id": approval.get("trial_user_id")}
    finally:
        with SessionLocal() as db:
            purge_trial(db, tenant_id, "test:communications-cleanup")


def _complaint(tenant_id, identifier: str) -> str:
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        return str(
            db.query(Complaint.id)
            .filter(Complaint.tenant_id == tenant_id, Complaint.complaint_identifier == identifier)
            .scalar()
        )


def _now() -> datetime:
    return datetime.now(timezone.utc)


# --------------------------------------------------------------------------------------------- the rules


@pytest.mark.unit
def test_unanswered_attempts_move_to_the_second_contact_then_end_unresolved():
    sent = {"contact": "PRIMARY", "outcome": "SENT"}
    assert rules.unanswered([sent], "PRIMARY") == 0  # waiting for a reply
    assert rules.unanswered([sent, sent], "PRIMARY") == 1  # the earlier one went unanswered
    three = [sent, sent, {"contact": "PRIMARY", "outcome": "NO_ANSWER"}]
    assert rules.after_attempts(three, "PRIMARY", True, 3) == ("OPEN", "SECOND")
    assert rules.after_attempts(three, "PRIMARY", False, 3) == ("UNRESOLVED", "PRIMARY")
    assert rules.after_attempts(three[:2], "PRIMARY", True, 3) == ("OPEN", "PRIMARY")
    second = [*three, *([{"contact": "SECOND", "outcome": "BOUNCED"}] * 3)]
    assert rules.after_attempts(second, "SECOND", True, 3) == ("UNRESOLVED", "SECOND")


@pytest.mark.unit
def test_s4_counts_an_entry_logged_before_or_within_one_working_hour():
    friday = datetime(2026, 10, 30, 23, 30, tzinfo=timezone.utc)
    assert rules.in_mdarix(friday, friday - timedelta(minutes=5)) is True  # logged before it was sent
    assert rules.in_mdarix(friday, friday + timedelta(minutes=59)) is True
    assert rules.in_mdarix(friday, friday + timedelta(hours=2)) is True  # the weekend is not working time
    assert rules.in_mdarix(friday, friday + timedelta(days=3, hours=1)) is False
    tuesday = datetime(2026, 11, 3, 10, 0, tzinfo=timezone.utc)
    assert rules.in_mdarix(tuesday, tuesday + timedelta(hours=1, minutes=1)) is False


@pytest.mark.unit
def test_a_request_needs_its_owner_and_due_date():
    assert rules.entry_problem("SENT", "INFORMATION_REQUEST", "EMAIL", "Ask for the log", None, None)
    assert rules.entry_problem("SENT", "UPDATE", "EMAIL", "Told them we opened a case", None, None) is None
    assert rules.entry_problem("RECEIVED", "INFORMATION_REQUEST", "EMAIL", "They asked", None, None)


# --------------------------------------------------------------------------------------------- through the API


def test_the_sample_log_shows_a_reporter_follow_up_an_answer_and_one_unresolved(trial):
    body = _ok(trial["user"].get(LOG))
    by_ref = {}
    for item in body["items"]:
        by_ref.setdefault(item["complaint_ref"] or item["intake_reference"], []).append(item)
    reporter = next(item for item in body["items"] if item["party"]["type"] == "REPORTER" and item["complaint_ref"])
    assert reporter["status"] == "OPEN" and reporter["overdue"] and reporter["unanswered"] == 2
    assert [a["outcome"] for a in reporter["attempts"]] == ["SENT", "NO_ANSWER"]
    assert reporter["origin"]["type"] == "MarketAssessment" and reporter["owner"]
    distributor = next(item for item in body["items"] if item["party"]["type"] == "DISTRIBUTOR" and item["is_request"])
    assert distributor["status"] == "ANSWERED"
    detail = _ok(trial["user"].get(f"{LOG}/{distributor['id']}"))
    assert (
        detail["replies"][0]["qms_reference"] == "SAMPLE-QMS-COMM-0042"
        and detail["replies"][0]["direction"] == "RECEIVED"
    )
    hospital = next(item for item in body["items"] if item["party"]["type"] == "HOSPITAL")
    assert hospital["status"] == "UNRESOLVED" and hospital["current_contact"] == "SECOND"
    assert len(hospital["attempts"]) == 6 and hospital["status_label"] == "Unresolved after attempts"
    assert body["counts"]["overdue"] >= 1 and body["counts"]["unresolved"] >= 1
    assert body["s4"]["outside"] >= 1 and body["s4"]["in_mdarix"] > body["s4"]["outside"]
    assert "MDARIX sends nothing" in body["never_sends"] and body["attempts_limit"] == 3
    # The first-contact follow-ups of 0.10.57's sample are requests too, linked to their dated tasks.
    assert any(item["origin"] and item["origin"]["type"] == "IntakeEvent" for item in body["items"])


def test_the_overdue_request_is_in_my_work_readiness_and_the_case_brief(trial):
    user = trial["user"]
    overdue = _ok(user.get("/api/v1/tasks", params={"view": "overdue"}))
    rows = overdue.get("items") or overdue.get("tasks") or []
    assert any(row["task_type"] == "EXTERNAL_REPLY_DUE" for row in rows)
    checks = {check["code"]: check for check in _ok(user.get("/api/v1/readiness"))["checks"]}
    assert checks["EXTERNAL_REQUESTS"]["state"] == "ATTENTION" and checks["EXTERNAL_REQUESTS"]["unresolved"] >= 1


def test_a_request_moves_to_the_second_contact_and_ends_unresolved(trial):
    user, tenant_id = trial["user"], trial["tenant_id"]
    complaint = _complaint(tenant_id, "SAMPLE-RV-06")
    party = _ok(
        user.post(
            f"{LOG}/parties",
            json={
                "type": "SERVICE_PARTNER",
                "name": "Field Service Co (test)",
                "primary": {"name": "Dispatch", "details": "dispatch@example.invalid"},
                "second": {"name": "Manager", "details": "manager@example.invalid"},
            },
        )
    )
    assert party["second"]["name"] == "Manager"
    me = _ok(user.get(LOG))["colleagues"][0]["id"]
    sent = _now() - timedelta(days=2)
    missing_owner = user.post(
        LOG,
        json={
            "complaint_id": complaint,
            "party_id": party["id"],
            "direction": "SENT",
            "purpose": "INFORMATION_REQUEST",
            "subject": "Ask for the service report",
            "channel": "EMAIL",
            "occurred_at": sent.isoformat(),
        },
    )
    assert missing_owner.status_code == 422
    entry = _ok(
        user.post(
            LOG,
            json={
                "complaint_id": complaint,
                "party_id": party["id"],
                "direction": "SENT",
                "purpose": "INFORMATION_REQUEST",
                "subject": "Ask for the service report",
                "channel": "EMAIL",
                "occurred_at": sent.isoformat(),
                "owner_id": me,
                "reply_due_on": (sent + timedelta(days=1)).date().isoformat(),
            },
        )
    )
    assert entry["status"] == "OPEN" and len(entry["attempts"]) == 1 and entry["in_mdarix"] is False
    for index in range(5):
        entry = _ok(
            user.post(
                f"{LOG}/{entry['id']}/attempts",
                json={
                    "at": (sent + timedelta(hours=index + 1)).isoformat(),
                    "channel": "PHONE",
                    "outcome": "NO_ANSWER",
                },
            )
        )
        if index == 1:
            assert entry["current_contact"] == "SECOND" and entry["status"] == "OPEN"
    assert entry["status"] == "UNRESOLVED" and "3 attempts" in entry["close_note"]
    refused = user.post(
        f"{LOG}/{entry['id']}/attempts",
        json={"at": _now().isoformat(), "channel": "PHONE", "outcome": "NO_ANSWER"},
    )
    assert refused.status_code == 409


def test_a_reply_answers_the_request_and_finishes_its_task(trial):
    from backend.app.db.models.workflow import WorkflowTask

    user, tenant_id = trial["user"], trial["tenant_id"]
    complaint = _complaint(tenant_id, "SAMPLE-RV-05")
    body = _ok(user.get(LOG, params={"complaint_id": complaint}))
    distributor = next(item for item in _ok(user.get(f"{LOG}/parties"))["parties"] if item["type"] == "DISTRIBUTOR")
    sent = _now() - timedelta(hours=3)
    entry = _ok(
        user.post(
            LOG,
            json={
                "complaint_id": complaint,
                "party_id": distributor["id"],
                "direction": "SENT",
                "purpose": "INFORMATION_REQUEST",
                "subject": "Ask how many units of the lot are in stock",
                "channel": "EMAIL",
                "occurred_at": sent.isoformat(),
                "owner_id": body["colleagues"][0]["id"],
                "reply_due_on": _now().date().isoformat(),
            },
        )
    )
    answered = _ok(
        user.post(
            f"{LOG}/{entry['id']}/reply",
            json={
                "received_at": (sent + timedelta(hours=1)).isoformat(),
                "channel": "EMAIL",
                "summary": "Twelve units in stock, quarantined",
                "evidence": ["Distributor e-mail"],
                "qms_reference": "QMS-COMM-77",
            },
        )
    )
    assert (
        answered["status"] == "ANSWERED" and answered["replies"][0]["subject"] == "Twelve units in stock, quarantined"
    )
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        row = db.get(CommunicationEntry, uuid.UUID(entry["id"]))
        assert db.get(WorkflowTask, row.task_id).status == "COMPLETED"
    listed = _ok(user.get(LOG, params={"complaint_id": complaint}))
    assert listed["complaint"]["identifier"] == "SAMPLE-RV-05" and len(listed["items"]) == 2


def test_an_unknown_answer_raises_a_request_to_the_reporter(trial):
    user, tenant_id = trial["user"], trial["tenant_id"]
    complaint = _complaint(tenant_id, "SAMPLE-RV-06")
    answers = {"US1": {"answer": "NO", "rationale": "", "evidence": []}}
    answers["US2B"] = {"answer": "UNKNOWN", "rationale": "", "evidence": []}
    _ok(user.put(f"/api/v1/complaints/{complaint}/market-assessments/US", json={"answers": answers}))
    _ok(user.put(f"/api/v1/complaints/{complaint}/market-assessments/US", json={"answers": answers}))  # once only
    items = _ok(user.get(LOG, params={"complaint_id": complaint}))["items"]
    raised = [item for item in items if item["origin"] and item["origin"]["type"] == "MarketAssessment"]
    assert len(raised) == 1 and raised[0]["not_sent_yet"] and raised[0]["party"]["type"] == "REPORTER"
    assert raised[0]["origin"]["questions"] == ["US2B"] and "US2B" in raised[0]["subject"]
    sent = _ok(
        user.post(
            f"{LOG}/{raised[0]['id']}/attempts",
            json={"at": _now().isoformat(), "channel": "EMAIL", "outcome": "SENT"},
        )
    )
    assert sent["not_sent_yet"] is False and sent["in_mdarix"] is True


def test_the_setting_changes_the_number_of_attempts(trial):
    user = trial["user"]
    assert _ok(user.get(f"{LOG}/settings"))["attempts_before_escalation"] == 3
    assert user.put(f"{LOG}/settings", json={"attempts_before_escalation": 0}).status_code == 422
    assert _ok(user.put(f"{LOG}/settings", json={"attempts_before_escalation": 2}))["attempts_before_escalation"] == 2
    _ok(user.put(f"{LOG}/settings", json={"attempts_before_escalation": 3}))


def test_nothing_is_sent_and_another_organization_reads_none_of_it(trial, monkeypatch):
    from auth import emailer

    sent = []
    monkeypatch.setattr(emailer, "send_email", lambda *args, **kwargs: sent.append(args), raising=False)
    mine = _ok(trial["user"].get(LOG))["items"][0]
    other, _, _ = _approved_trial_client()
    assert other.get(f"{LOG}/{mine['id']}").status_code == 404
    assert mine["id"] not in {item["id"] for item in _ok(other.get(LOG))["items"]}
    assert sent == []
    if runtime_role_active():
        for model in (CommunicationEntry, ExternalParty, DecisionGuideVersion):
            for tenant, expected in ((uuid.uuid4(), False), (trial["tenant_id"], True)):
                runtime = RuntimeSessionLocal()
                try:
                    bind_tenant(runtime, tenant)
                    count = runtime.query(model).filter(model.tenant_id == trial["tenant_id"]).count()
                    assert (count > 0) == expected, model.__tablename__
                finally:
                    runtime.close()


def test_export_purge_and_sample_removal_cover_the_records():
    from backend.app.db.tenant_scope import bind_system
    from backend.app.tenant_export import _tables
    from backend.app.trial.retention import TRIAL_DATA_TABLES, purge_trial

    tables = {"communication_entries", "external_parties", "communication_settings", "decision_guide_versions"}
    user, approval, _ = _approved_trial_client()
    tenant_id = uuid.UUID(approval["tenant_id"])
    with SessionLocal() as db:
        bind_system(db, "test: tables an export and the purge cover")
        assert tables <= {table for _, table in _tables(db)} and tables <= set(TRIAL_DATA_TABLES)
    _ok(user.post("/api/v1/trial/sample-data/removal", json={"confirm": True}))
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        for model in (CommunicationEntry, ExternalParty, DecisionGuideVersion):
            assert db.query(model).filter(model.tenant_id == tenant_id).count() == 0, model.__tablename__
        purge_trial(db, tenant_id, "test:communications-removal")
