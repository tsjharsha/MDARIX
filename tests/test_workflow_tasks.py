"""My Work: the tasks existing actions create (opening and managing a case, decisions, risk reviews, supplier
requests), the task API (views, claim, release, decline, accept, reassign, complete) and the backfill."""

import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import func

from backend.app.db.models.foundation import AuditEvent, Decision, HumanReview, Investigation, Product, Risk, Tenant
from backend.app.db.models.workflow import WorkflowTask, WorkflowTaskEvent
from backend.app.db.session import SessionLocal
from backend.app.db.tenant_scope import bind_system
from tests.reports_seed import GOLDEN, PASSWORD, role_client

REASON = "Reason recorded for the audit trail"


def _tenant_id():
    with SessionLocal() as db:
        bind_system(db, "test: golden organization")
        return db.query(Tenant.id).filter(Tenant.tenant_key == GOLDEN).one()[0]


def _open_case(client, *, assign_to_me: bool = True) -> dict:
    with SessionLocal() as db:
        bind_system(db, "test: a product to open a case for")
        product = db.query(Product.id).filter(Product.tenant_id == _tenant_id()).first()[0]
    made = client.post(
        "/api/v1/investigations",
        json={
            "product_id": str(product),
            "investigation_question": "Why do occlusion alarms rise after release B?",
            "assign_to_me": assign_to_me,
        },
    )
    assert made.status_code == 201, made.text
    return made.json()


def _tasks(source_id, task_type: str | None = None) -> list[WorkflowTask]:
    with SessionLocal() as db:
        bind_system(db, "test: read workflow tasks")
        query = db.query(WorkflowTask).filter(WorkflowTask.source_entity_id == uuid.UUID(str(source_id)))
        if task_type:
            query = query.filter(WorkflowTask.task_type == task_type)
        rows = query.order_by(WorkflowTask.created_at).all()
        db.expunge_all()
        return rows


def _listed(client, view: str, source_id) -> list[dict]:
    response = client.get("/api/v1/tasks", params={"view": view, "page_size": 200})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["view"] == view and body["page"] == 1 and body["page_size"] == 200
    return [item for item in body["items"] if item["source"]["id"] == str(source_id)]


def _delete_tasks(source_id) -> None:
    with SessionLocal() as db:
        bind_system(db, "test cleanup: workflow tasks")
        ids = [
            row[0]
            for row in db.query(WorkflowTask.id).filter(WorkflowTask.source_entity_id == uuid.UUID(str(source_id)))
        ]
        if ids:
            db.query(WorkflowTaskEvent).filter(WorkflowTaskEvent.task_id.in_(ids)).delete(synchronize_session=False)
            db.query(WorkflowTask).filter(WorkflowTask.id.in_(ids)).delete(synchronize_session=False)
        db.commit()


def test_opening_a_case_gives_its_owner_an_accepted_task():
    lead, lead_id = role_client("INVESTIGATOR")
    case = _open_case(lead)
    items = _listed(lead, "assigned", case["id"])
    assert len(items) == 1
    task = items[0]
    assert task["task_type"] == "INVESTIGATION" and task["task_type_label"] == "Investigation"
    assert task["status"] == "ACCEPTED" and task["assigned_user"]["id"] == lead_id and task["assigned_user"]["name"]
    assert task["business_id"].startswith("TASK")
    assert task["title"].startswith(f"Investigate {case['business_id']}:")
    assert task["source"] == {
        "type": "Investigation",
        "id": case["id"],
        "business_id": case["business_id"],
        "label": f"Investigation {case['business_id']}",
    }
    assert task["investigation"]["business_id"] == case["business_id"]
    assert task["assigned_role"] == "INVESTIGATOR" and task["assigned_role_label"] == "Quality Investigator"
    assert task["actions"]["can_release"] and task["actions"]["can_decline"] and not task["actions"]["can_complete"]
    # Searching finds it by the case number in its title.
    found = lead.get("/api/v1/tasks", params={"view": "assigned", "q": case["business_id"]}).json()
    assert [item["id"] for item in found["items"]] == [task["id"]] and found["total"] == 1

    detail = lead.get(f"/api/v1/tasks/{task['id']}")
    assert detail.status_code == 200, detail.text
    events = detail.json()["events"]
    assert [event["event_type"] for event in events] == ["CREATED"]
    assert events[0]["actor_role"] == "INVESTIGATOR" and events[0]["to_status"] == "ACCEPTED"
    # An investigation task ends with the case, never by hand.
    refused = lead.post(f"/api/v1/tasks/{task['id']}/complete", json={})
    assert refused.status_code == 409 and refused.json()["detail"]["code"] == "TASK_COMPLETES_AUTOMATICALLY"

    summary = lead.get("/api/v1/tasks/summary").json()
    assert summary["counts"]["assigned"] >= 1 and set(summary["counts"]) == {
        "assigned",
        "queue",
        "waiting",
        "returned",
        "due_soon",
        "overdue",
    }
    assert {"code": "INVESTIGATOR", "label": "Quality Investigator"} in summary["roles"]
    with SessionLocal() as db:
        bind_system(db, "test: task audit")
        actions = {row[0] for row in db.query(AuditEvent.action).filter(AuditEvent.entity_id == uuid.UUID(task["id"]))}
    assert "TASK_CREATED" in actions


def _case_owner_and_username(case_id, user_id):
    from backend.app.db.models.foundation import AuthUser, Investigation

    with SessionLocal() as db:
        bind_system(db, "test: case owner follows its task")
        owner = db.query(Investigation.owner_ref).filter(Investigation.id == uuid.UUID(case_id)).scalar()
        username = db.query(AuthUser.username).filter(AuthUser.id == uuid.UUID(user_id)).scalar()
    return owner, username


def test_a_queue_task_is_claimed_released_and_declined_by_its_rules():
    lead, _ = role_client("INVESTIGATOR")
    other, other_id = role_client("INVESTIGATOR")
    viewer, _ = role_client("VIEWER")
    case = _open_case(lead, assign_to_me=False)
    queued = _listed(other, "queue", case["id"])
    assert len(queued) == 1
    task = queued[0]
    assert task["status"] == "NEW" and task["assigned_user"] is None and task["actions"]["can_claim"]
    path = f"/api/v1/tasks/{task['id']}"
    # A viewer holds no investigation permission: the queue is not theirs and they cannot claim from it.
    assert _listed(viewer, "queue", case["id"]) == []
    denied = viewer.post(f"{path}/claim")
    assert denied.status_code == 403 and denied.json()["detail"]["code"] == "PERMISSION_DENIED"

    claimed = other.post(f"{path}/claim")
    assert claimed.status_code == 200, claimed.text
    assert claimed.json()["status"] == "ACCEPTED" and claimed.json()["assigned_user"]["id"] == other_id
    # Taking the case from the queue makes that person its owner, as assigning it would.
    owner, username = _case_owner_and_username(case["id"], other_id)
    assert owner == username
    taken = lead.post(f"{path}/claim")
    assert taken.status_code == 409 and taken.json()["detail"]["code"] == "TASK_STATE_CONFLICT"
    not_yours = lead.post(f"{path}/release", json={"reason": REASON})
    assert not_yours.status_code == 403 and not_yours.json()["detail"]["code"] == "TASK_NOT_YOURS"
    assert other.post(f"{path}/release", json={"reason": "short"}).status_code == 422

    released = other.post(f"{path}/release", json={"reason": REASON})
    assert released.status_code == 200 and released.json()["status"] == "NEW"
    assert released.json()["assigned_user"] is None
    assert _case_owner_and_username(case["id"], other_id)[0] is None
    assert other.post(f"{path}/claim").status_code == 200
    declined = other.post(f"{path}/decline", json={"reason": REASON})
    # A task with a role queue goes back to it when declined.
    assert declined.status_code == 200 and declined.json()["status"] == "NEW"

    events = other.get(path).json()["events"]
    assert [event["event_type"] for event in events] == ["CREATED", "CLAIMED", "RELEASED", "CLAIMED", "DECLINED"]
    assert events[1]["actor_role"] == "INVESTIGATOR" and events[2]["reason"] == REASON
    assert events[1]["actor_name"]


def test_tasks_of_other_organizations_and_unknown_tasks_are_not_found():
    client, _ = role_client("INVESTIGATOR")
    for response in (
        client.get(f"/api/v1/tasks/{uuid.uuid4()}"),
        client.post(f"/api/v1/tasks/{uuid.uuid4()}/accept"),
        client.post(f"/api/v1/tasks/{uuid.uuid4()}/claim"),
    ):
        assert response.status_code == 404 and response.json()["detail"]["code"] == "TASK_NOT_FOUND"
    assert client.get("/api/v1/tasks", params={"view": "everything"}).status_code == 422
    assert client.get("/api/v1/tasks", params={"page_size": 201}).status_code == 422


def test_managing_a_case_moves_cancels_and_restores_its_task():
    lead, _ = role_client("INVESTIGATOR")
    colleague, colleague_id = role_client("INVESTIGATOR")
    case = _open_case(lead)
    path = f"/api/v1/investigations/{case['id']}"
    assert lead.patch(path, json={"reason": REASON, "assignee_id": colleague_id}).status_code == 200
    first, second = _tasks(case["id"], "INVESTIGATION")
    assert first.status == "SUPERSEDED" and first.completion_outcome == "REASSIGNED"
    assert second.status == "ASSIGNED" and str(second.assigned_user_id) == colleague_id

    accepted = colleague.post(f"/api/v1/tasks/{second.id}/accept")
    assert accepted.status_code == 200 and accepted.json()["status"] == "ACCEPTED"
    assert lead.post(f"/api/v1/tasks/{second.id}/accept").status_code == 403

    assert lead.patch(path, json={"reason": REASON, "status": "closed"}).status_code == 200
    rows = _tasks(case["id"])
    assert rows and all(row.status in {"SUPERSEDED", "CANCELLED"} for row in rows)
    assert {row.completion_outcome for row in rows if row.status == "CANCELLED"} == {"CASE_CLOSED"}

    assert lead.patch(path, json={"reason": REASON, "status": "open"}).status_code == 200
    reopened = [row for row in _tasks(case["id"], "INVESTIGATION") if row.status == "ASSIGNED"]
    assert len(reopened) == 1 and str(reopened[0].assigned_user_id) == colleague_id

    assert lead.patch(path, json={"reason": REASON, "unassign": True}).status_code == 200
    queued = [row for row in _tasks(case["id"], "INVESTIGATION") if row.status == "NEW"]
    assert len(queued) == 1 and queued[0].assigned_user_id is None and queued[0].assigned_role == "INVESTIGATOR"


def test_reassigning_needs_the_assign_permission_and_an_eligible_assignee():
    lead, _ = role_client("INVESTIGATOR")
    assigner, _ = role_client("REVIEWER")  # holds investigation.assign
    colleague, colleague_id = role_client("INVESTIGATOR")
    _, viewer_id = role_client("VIEWER")
    case = _open_case(lead, assign_to_me=False)
    task_id = _tasks(case["id"], "INVESTIGATION")[0].id
    path = f"/api/v1/tasks/{task_id}/reassign"
    refused = lead.post(path, json={"reason": REASON, "assignee_user_id": colleague_id})
    assert refused.status_code == 403 and refused.json()["detail"]["code"] == "PERMISSION_DENIED"
    assert assigner.post(path, json={"reason": REASON}).status_code == 422
    viewer = assigner.post(path, json={"reason": REASON, "assignee_user_id": viewer_id})
    assert viewer.status_code == 422 and viewer.json()["detail"]["code"] == "ASSIGNEE_NOT_ELIGIBLE"
    wrong_role = assigner.post(path, json={"reason": REASON, "assigned_role": "RISK_REVIEWER"})
    assert wrong_role.status_code == 422 and wrong_role.json()["detail"]["code"] == "ROLE_NOT_ELIGIBLE"

    moved = assigner.post(path, json={"reason": REASON, "assignee_user_id": colleague_id})
    assert moved.status_code == 200, moved.text
    assert moved.json()["status"] == "ASSIGNED" and moved.json()["assigned_user"]["id"] == colleague_id
    assert [item["id"] for item in _listed(colleague, "assigned", case["id"])] == [str(task_id)]
    events = colleague.get(f"/api/v1/tasks/{task_id}").json()["events"]
    assert events[-1]["event_type"] == "REASSIGNED" and events[-1]["actor_role"] == "REVIEWER"


@pytest.fixture
def decision():
    with SessionLocal() as db:
        bind_system(db, "test: a decision awaiting review")
        case = db.query(Investigation).filter(Investigation.tenant_id == _tenant_id()).first()
        now = datetime.now(timezone.utc)
        row = Decision(
            id=uuid.uuid4(),
            tenant_id=case.tenant_id,
            investigation_id=case.id,
            decision_identifier=f"WFT-{uuid.uuid4().hex[:8]}",
            decision_type="INVESTIGATION_REVIEW",
            disposition="REQUIRES_REVIEW",
            rationale="Workflow task test",
            decision_status="REQUIRES_REVIEW",
            authorized_by_ref="someone-else",
            updated_at=now,
            decision_timestamp=now,
            created_at=now,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        case_business_id = case.business_id
        db.expunge_all()
    yield row, case_business_id
    _delete_tasks(row.id)
    with SessionLocal() as db:
        bind_system(db, "test cleanup: decision")
        db.query(HumanReview).filter(HumanReview.decision_id == row.id).delete(synchronize_session=False)
        db.query(Decision).filter(Decision.id == row.id).delete(synchronize_session=False)
        db.commit()


def _version(client, decision_id) -> str:
    response = client.get(f"/api/v1/investigations/decisions/{decision_id}")
    assert response.status_code == 200, response.text
    return response.json()["updated_at"]


def test_a_decision_is_queued_returned_resubmitted_and_signed(decision):
    row, case_business_id = decision
    author, _ = role_client("INVESTIGATOR")
    reviewer, _ = role_client("INVESTIGATOR")
    approver, _ = role_client("APPROVER")
    changed = author.post(
        f"/api/v1/governance/decisions/{row.id}/material-change",
        json={"change_summary": "New evidence", "expected_updated_at": _version(author, row.id)},
    )
    assert changed.status_code == 200, changed.text
    (approval,) = _tasks(row.id, "DECISION_APPROVAL")
    assert approval.status == "NEW" and approval.assigned_role == "APPROVER" and approval.assigned_user_id is None
    assert approval.title == f"Approve or reject {row.business_id} on {case_business_id}"
    assert [item["id"] for item in _listed(approver, "queue", row.id)] == [str(approval.id)]
    assert _listed(reviewer, "queue", row.id) == []  # investigators do not sign

    returned = reviewer.post(
        f"/api/v1/investigations/decisions/{row.id}/reviews",
        json={"disposition": "REQUIRES_ADDITIONAL_EVIDENCE", "comments": "Needs the drift data"},
    )
    assert returned.status_code == 200, returned.text
    (approval,) = _tasks(row.id, "DECISION_APPROVAL")
    assert approval.status == "COMPLETED" and approval.completion_outcome == "RETURNED"
    (follow_up,) = _tasks(row.id, "FOLLOW_UP")
    assert follow_up.is_return and follow_up.status == "NEW"  # the author is not an account here: the queue
    assert follow_up.title == f"{row.business_id} returned: needs additional evidence"

    resubmitted = author.post(
        f"/api/v1/governance/decisions/{row.id}/material-change",
        json={"change_summary": "Drift data added", "expected_updated_at": _version(author, row.id)},
    )
    assert resubmitted.status_code == 200, resubmitted.text
    (follow_up,) = _tasks(row.id, "FOLLOW_UP")
    assert follow_up.status == "COMPLETED" and follow_up.completion_outcome == "RESUBMITTED"
    pending = [task for task in _tasks(row.id, "DECISION_APPROVAL") if task.status == "NEW"]
    assert len(pending) == 1

    signed = approver.post(
        f"/api/v1/governance/decisions/{row.id}/sign",
        json={
            "decision": "APPROVE",
            "remarks": "Reviewed",
            "password": PASSWORD,
            "object_version": _version(approver, row.id),
        },
    )
    assert signed.status_code == 200, signed.text
    statuses = {(task.status, task.completion_outcome) for task in _tasks(row.id, "DECISION_APPROVAL")}
    assert ("COMPLETED", "SIGNED_APPROVE") in statuses and not any(status == "NEW" for status, _ in statuses)


def test_a_risk_review_request_lands_in_the_risk_reviewers_queue():
    with SessionLocal() as db:
        bind_system(db, "test: a risk")
        risk = db.query(Risk.id).filter(Risk.tenant_id == _tenant_id()).first()
    if risk is None:
        pytest.skip("the golden organization has no risk")
    risk_id = risk[0]
    try:
        requested = role_client("INVESTIGATOR")[0].post(
            f"/api/v1/risk/{risk_id}/review-request", json={"reason": "The new complaints change the probability"}
        )
        assert requested.status_code == 200, requested.text
        (task,) = [row for row in _tasks(risk_id, "RISK_REVIEW") if row.status == "NEW"]
        assert task.assigned_role == "RISK_REVIEWER" and task.source_entity_type == "Risk"
        assert [item["id"] for item in _listed(role_client("RISK_REVIEWER")[0], "queue", risk_id)] == [str(task.id)]
        assert _listed(role_client("VIEWER")[0], "queue", risk_id) == []
    finally:
        _delete_tasks(risk_id)


def test_a_supplier_request_waits_for_the_reply_then_asks_for_its_review(monkeypatch):
    from tests.test_supplier_evidence_requests import PATH, _body, own_supplier

    monkeypatch.setenv("MDARIX_SUPPLIER_REQUESTS_PER_DAY", "100000")
    client, user_id = role_client("INVESTIGATOR")
    made = client.post(PATH, json=_body(own_supplier(client)))
    assert made.status_code == 200, made.text
    request_id = made.json()["id"]
    (waiting,) = _tasks(request_id, "EVIDENCE_REQUEST")
    assert waiting.status == "WAITING" and str(waiting.assigned_user_id) == user_id
    assert [item["id"] for item in _listed(client, "waiting", request_id)] == [str(waiting.id)]
    assert _listed(client, "assigned", request_id) == []

    for note in ("Certificate received", "Drift data received"):
        reply = client.post(f"{PATH}/{request_id}/reply", json={"note": note})
        assert reply.status_code == 200, reply.text
    (done,) = _tasks(request_id, "EVIDENCE_REQUEST")
    assert done.status == "COMPLETED" and done.completion_outcome == "REPLY_RECEIVED"
    (review,) = _tasks(request_id, "EVIDENCE_REVIEW")  # one review task, however many replies
    assert review.status == "ASSIGNED" and str(review.assigned_user_id) == user_id
    assert review.title == f"Review supplier reply {made.json()['business_id']}"

    assert client.post(f"/api/v1/tasks/{review.id}/accept").status_code == 200
    completed = client.post(f"/api/v1/tasks/{review.id}/complete", json={"outcome": "ACCEPTED_FOR_REVIEW"})
    assert completed.status_code == 200, completed.text
    assert completed.json()["status"] == "COMPLETED" and completed.json()["completion_outcome"] == "ACCEPTED_FOR_REVIEW"
    assert [item["id"] for item in _listed(client, "completed", request_id)] == [str(review.id)]
    again = client.post(f"/api/v1/tasks/{review.id}/complete", json={})
    assert again.status_code == 409 and again.json()["detail"]["code"] == "TASK_STATE_CONFLICT"


def test_the_backfill_creates_missing_tasks_once():
    """A fresh organization with sample records (open cases, no tasks): a dry run counts, the run creates, a second
    run creates nothing."""
    from backend.app.customer_lifecycle import build_customer_tenant
    from backend.app.db.tenant_scope import bind_tenant
    from backend.app.trial.retention import purge_trial
    from backend.app.trial.sample_data import seed_sample_workspace
    from backend.app.workflow.backfill import backfill_tenant

    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        customer, tenant = build_customer_tenant(
            db=db,
            tenant_key=f"WFTASK_{uuid.uuid4().hex[:8].upper()}",
            name="Workflow backfill",
            status="ACTIVE",
            now=now,
        )
        db.add(customer)
        db.add(tenant)
        db.flush()
        seed_sample_workspace(db, tenant.id, now)
        db.commit()
        tenant_id = tenant.id
    try:
        with SessionLocal() as db:
            bind_tenant(db, tenant_id)
            open_cases = (
                db.query(Investigation)
                .filter(Investigation.tenant_id == tenant_id, func.lower(Investigation.status) != "closed")
                .count()
            )
            dry = backfill_tenant(db, db, tenant_id)
            db.rollback()
            assert dry["INVESTIGATION"] == open_cases and dry["applied"] is False
            assert db.query(WorkflowTask).filter(WorkflowTask.tenant_id == tenant_id).count() == 0
            first = backfill_tenant(db, db, tenant_id, apply=True)
            db.commit()
            assert first["INVESTIGATION"] == open_cases
            created = db.query(WorkflowTask).filter(WorkflowTask.tenant_id == tenant_id).count()
            assert created == first["INVESTIGATION"] + first["DECISION_APPROVAL"] + first["EVIDENCE_REQUEST"]
            second = backfill_tenant(db, db, tenant_id, apply=True)
            db.commit()
            assert second["INVESTIGATION"] == second["DECISION_APPROVAL"] == second["EVIDENCE_REQUEST"] == 0
            assert second["skipped"] == created
            assert db.query(WorkflowTask).filter(WorkflowTask.tenant_id == tenant_id).count() == created
    finally:
        with SessionLocal() as db:
            purge_trial(db, tenant_id, "test:workflow-backfill-cleanup")
