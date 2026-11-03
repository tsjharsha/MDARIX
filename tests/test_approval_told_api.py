"""0.10.64, J13 "the approver is told": a report snapshot or decision guide version waiting for approval is a task in
the approver's My Work (and, when due soon, a bell line); before any password the screen says who may approve; working
alone in a trial, separation of duties gives way to the practice approval of one's own work ("same person", T-B8),
never in a pilot; the author withdraws a waiting guide version; RV-06 and the India report to correct are finished by
the trial owner alone."""

from __future__ import annotations

import uuid
from datetime import timedelta

import pytest

from tests.report_fill import fill

from backend.app.db.models.oversight import DueAlert
from backend.app.db.models.workflow import WorkflowTask
from backend.app.db.session import SessionLocal
from backend.app.db.tenant_scope import bind_tenant
from backend.app.workflow import approvals
from tests.test_authority_reports_api import REPORTS, _complaint_id, _items, _start_rv06
from tests.test_free_trial import PASSWORD, _approved_trial_client
from tests.test_reporting_capa_api import PASSWORD as COLLEAGUE_PASSWORD
from tests.test_reporting_capa_api import _client

GUIDES = "/api/v1/decision-guides"
PRACTICE = "In a pilot a colleague approves this; in the trial you may approve your own practice"


def _ok(response):
    assert response.status_code == 200, response.text
    return response.json()


def _trial(colleague: bool):
    from backend.app.trial.retention import purge_trial

    user, approval, _ = _approved_trial_client()
    tenant_id = uuid.UUID(approval["tenant_id"])
    found = {"user": user, "tenant_id": tenant_id}
    if colleague:
        found["colleague"] = _client(tenant_id, "LEADER", "Rahul Colleague")
    try:
        yield found
    finally:
        with SessionLocal() as db:
            purge_trial(db, tenant_id, "test:approval-told-cleanup")


@pytest.fixture(scope="module")
def solo():
    yield from _trial(colleague=False)


@pytest.fixture(scope="module")
def pair():
    yield from _trial(colleague=True)


def _approval_tasks(client, source_type: str) -> list[dict]:
    return [
        item
        for item in _ok(client.get("/api/v1/tasks", params={"view": "assigned"}))["items"]
        if item["task_type"] == approvals.TASK_TYPE and item["source"]["type"] == source_type
    ]


# --------------------------------------------------------------------------------------------- the rule


@pytest.mark.unit
def test_who_approves_is_said_before_any_password():
    pilot = approvals.standing("You prepared this worksheet", True, ["Rahul"], False, "LEADER", "report")
    assert not pilot["may_approve"] and not pilot["same_person"]
    assert pilot["message"] == (
        "You prepared this worksheet. A colleague with regulatory approval rights approves this: Rahul."
    )
    # A pilot never gives way, even with nobody else to approve: it says what to do.
    alone = approvals.standing("You prepared this worksheet", True, [], False, "LEADER", "report")
    assert not alone["may_approve"] and "an administrator gives a colleague" in alone["message"]
    # Working alone in a trial: one's own practice report, as one's role.
    trial = approvals.standing("You prepared this worksheet", True, [], True, "LEADER", "report")
    assert trial["may_approve"] and trial["same_person"]
    assert trial["message"] == f"{PRACTICE} report as Leader (Quality Manager)."
    # In a trial with a colleague who may approve, the colleague does.
    assert not approvals.standing("You prepared it", True, ["Rahul"], True, "LEADER", "report")["may_approve"]
    # An administrator or a role without approval rights is no separation of duties: never.
    assert not approvals.standing("An administrator cannot approve", False, [], True, "ADMIN", "report")["may_approve"]
    assert approvals.standing(None, False, ["Rahul"], False, "LEADER", "report") == {
        "may_approve": True,
        "same_person": False,
        "approvers": ["Rahul"],
        "message": None,
    }


def _fill(user, report_id: str) -> None:
    """Every mandatory field still empty, entered: on the new navigation Send for approval waits for them (0.10.75)."""
    fill(user, REPORTS, report_id, _ok(user.get(f"{REPORTS}/{report_id}"))["mandatory"]["missing"])


# --------------------------------------------------------------------------------------------- alone in a trial


@pytest.mark.db
def test_the_trial_owner_alone_finishes_rv06(solo):
    user = solo["user"]
    detail = _start_rv06(solo)
    assert detail["approval"]["approvers"] == [] and detail["approval"]["same_person"]
    _ok(user.put(f"{REPORTS}/{detail['id']}/fields/MFR_REPORT", json={"value": "1234567-2026-00001"}))
    _fill(user, detail["id"])
    asked = _ok(user.post(f"{REPORTS}/{detail['id']}/snapshots"))
    standing = asked["approval"]
    assert standing["may_approve"] and standing["same_person"]
    assert standing["message"] == f"{PRACTICE} report as Leader (Quality Manager)."
    # The approval waits in the owner's own My Work, and opens the complaint's reports.
    [task] = _approval_tasks(user, "ReportSnapshot")
    assert task["title"].startswith("Approve snapshot 1 of the Form FDA 3500A worksheet (eMDR) for CMP")
    assert task["details"]["complaint_id"] == _complaint_id(solo["tenant_id"], "SAMPLE-RV-06")
    assert task["due_at"]
    snapshot = asked["pending_snapshot"]
    approved = _ok(
        user.post(f"{REPORTS}/{detail['id']}/snapshots/{snapshot['id']}/approve", json={"password": PASSWORD})
    )
    assert approved["state"] == "APPROVED" and approved["snapshots"][0]["same_person"]
    assert approved["approval"] is None
    assert _approval_tasks(user, "ReportSnapshot") == []


@pytest.mark.db
def test_the_trial_owner_alone_corrects_the_india_report(solo):
    user = solo["user"]
    item = _items(user)[("SAMPLE-RV-10", "IN", "INITIAL")]
    detail = _ok(user.get(f"{REPORTS}/{item['id']}"))
    assert detail["state"] == "CORRECTION_REQUIRED"
    asked = _ok(user.post(f"{REPORTS}/{detail['id']}/snapshots"))
    assert asked["approval"]["may_approve"] and asked["approval"]["same_person"]
    snapshot = asked["pending_snapshot"]
    approved = _ok(
        user.post(f"{REPORTS}/{detail['id']}/snapshots/{snapshot['id']}/approve", json={"password": PASSWORD})
    )
    assert approved["state"] == "APPROVED" and approved["snapshots"][0]["same_person"]


@pytest.mark.db
def test_alone_in_a_trial_one_approves_ones_own_guide_version(solo):
    user = solo["user"]
    _ok(user.post(f"{GUIDES}/GB/drafts"))
    _ok(user.post(f"{GUIDES}/GB/versions/2/tests"))
    asked = _ok(
        user.post(f"{GUIDES}/GB/versions/2/approval-request", json={"change_reason": "Adopting the starter as ours."})
    )
    assert asked["approval"]["same_person"] and asked["approval"]["message"].startswith(f"{PRACTICE} guide version")
    assert len(_approval_tasks(user, "DecisionGuideVersion")) == 1
    published = _ok(user.post(f"{GUIDES}/GB/versions/2/approve", json={"password": PASSWORD}))
    assert published["state"] == "PUBLISHED" and published["signature"]["signer_name"]
    assert _approval_tasks(user, "DecisionGuideVersion") == []


# --------------------------------------------------------------------------------------------- two people


@pytest.mark.db
def test_the_approver_gets_a_task_and_a_bell_line_and_the_preparer_is_told_who(pair):
    from backend.app.oversight import service

    user, colleague = pair["user"], pair["colleague"]
    detail = _start_rv06(pair)
    assert detail["approval"]["approvers"] == ["Rahul Colleague"]
    _fill(user, detail["id"])
    asked = _ok(user.post(f"{REPORTS}/{detail['id']}/snapshots"))
    standing = asked["approval"]
    # The preparer sees who approves in place of the form; separation of duties holds when a colleague may approve.
    assert not standing["may_approve"] and not standing["same_person"]
    assert standing["message"].endswith("A colleague with regulatory approval rights approves this: Rahul Colleague.")
    assert _approval_tasks(user, "ReportSnapshot") == []
    [task] = _approval_tasks(colleague, "ReportSnapshot")
    assert _ok(colleague.get(f"{REPORTS}/{detail['id']}"))["approval"]["may_approve"]
    # When it is due soon, the reminders tell the approver (the bell), once.
    with SessionLocal() as db:
        bind_tenant(db, pair["tenant_id"])
        row = db.get(WorkflowTask, uuid.UUID(task["id"]))
        items = [item for item in service.due_items(db, db, pair["tenant_id"]) if item["key"] == f"task:{row.id}"]
        assert len(items) == 1 and items[0]["category"] == "OBLIGATION"
        # The report itself (0.10.76), not the complaint's list of reports.
        assert items[0]["opens"]["tab"] == f"Reports?report={detail['id']}"
        service.sweep(db, db, pair["tenant_id"], row.due_at - timedelta(hours=1))
        db.commit()
        alerts = db.query(DueAlert).filter(
            DueAlert.tenant_id == pair["tenant_id"], DueAlert.item_key == f"task:{row.id}"
        )
        assert {alert.recipient_id for alert in alerts} == {str(row.assigned_user_id)}
    snapshot = asked["pending_snapshot"]
    approved = _ok(
        colleague.post(
            f"{REPORTS}/{detail['id']}/snapshots/{snapshot['id']}/approve", json={"password": COLLEAGUE_PASSWORD}
        )
    )
    assert approved["state"] == "APPROVED" and not approved["snapshots"][0]["same_person"]
    assert _approval_tasks(colleague, "ReportSnapshot") == []


@pytest.mark.db
def test_the_author_withdraws_a_waiting_guide_version_and_it_shows_once(pair):
    from backend.app.oversight import service

    user, colleague = pair["user"], pair["colleague"]
    _ok(user.post(f"{GUIDES}/IN/drafts"))
    _ok(user.post(f"{GUIDES}/IN/versions/2/tests"))
    asked = _ok(
        user.post(f"{GUIDES}/IN/versions/2/approval-request", json={"change_reason": "Adopting the starter as ours."})
    )
    assert asked["you_asked"] and not asked["approval"]["may_approve"]
    assert asked["approval"]["approvers"] == ["Rahul Colleague"]
    [task] = _approval_tasks(colleague, "DecisionGuideVersion")
    with SessionLocal() as db:
        bind_tenant(db, pair["tenant_id"])
        keys = [item["key"] for item in service.due_items(db, db, pair["tenant_id"]) if item["category"] == "GUIDE"]
    assert keys == [f"task:{task['id']}"]  # the task stands for the version: never a second "guide:" line
    # Only its author withdraws it; the approver's task ends.
    refused = colleague.post(f"{GUIDES}/IN/versions/2/withdraw")
    assert refused.status_code == 403 and refused.json()["detail"]["code"] == "NOT_THE_AUTHOR"
    withdrawn = _ok(user.post(f"{GUIDES}/IN/versions/2/withdraw"))
    assert withdrawn["state"] == "DRAFT" and not withdrawn.get("you_asked")
    assert _approval_tasks(colleague, "DecisionGuideVersion") == []
    assert user.post(f"{GUIDES}/IN/versions/2/withdraw").status_code == 409
