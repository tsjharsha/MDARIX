"""Case workflow end to end: the state, priority, due date and first scope a case opens with (directly and from a
signal), taking its task starts it, manual moves between states (status kept in step, tasks cancelled and restored,
permissions, other organizations), the versioned scope and the complaint links that follow it, managing a case
(priority, due date, a new question as a new scope version), readiness, and the investigator's own cases.

Everything runs in a fresh organization of its own (on the shared plane), deleted at the end.
"""

from __future__ import annotations

import secrets
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from auth.durable import persist_session
from auth.service import _hash
from backend.app.db.models.case_scope import InvestigationScopeVersion
from backend.app.db.models.foundation import (
    AuditEvent,
    AuthUser,
    Complaint,
    Decision,
    Evidence,
    FailureMode,
    Investigation,
    InvestigationComplaint,
    LotBatch,
    Product,
    ProductVersion,
    Tenant,
    TenantMembership,
    Unknown,
)
from backend.app.db.models.stage3 import SupplierEvidenceRequest
from backend.app.db.models.workflow import WorkflowTask
from backend.app.db.session import SessionLocal
from backend.app.db.tenant_scope import bind_system, bind_tenant
from backend.app.main import app

PASSWORD = "Case workflow 2026!"
REASON = "Reason recorded for the audit trail"
QUESTION = "Why do occlusion alarms rise after release B?"


@pytest.fixture(scope="module")
def org():
    """A fresh organization with an investigator, a colleague, a triage lead and a viewer, removed afterwards."""
    from backend.app.customer_lifecycle import build_customer_tenant
    from backend.app.trial.retention import purge_trial

    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        customer, tenant = build_customer_tenant(
            db=db, tenant_key=f"CASEFLOW_{uuid.uuid4().hex[:8].upper()}", name="Case workflow", status="ACTIVE", now=now
        )
        db.add(customer)
        db.add(tenant)
        db.commit()  # registers the organization on the shared plane (migration md20)
        tenant_id = tenant.id
    people = {
        name: _client(tenant_id, role, name.title())
        for name, role in (
            ("investigator", "INVESTIGATOR"),
            ("colleague", "INVESTIGATOR"),
            ("lead", "TRIAGE_LEAD"),
            ("viewer", "VIEWER"),
        )
    }
    try:
        yield {"tenant_id": tenant_id, **people}
    finally:
        with SessionLocal() as db:
            bind_tenant(db, tenant_id)
            db.query(InvestigationScopeVersion).filter(InvestigationScopeVersion.tenant_id == tenant_id).delete(
                synchronize_session=False
            )
            db.commit()
        with SessionLocal() as db:
            purge_trial(db, tenant_id, "test:case-workflow-cleanup")


def _client(tenant_id, role: str, name: str) -> tuple[TestClient, str]:
    with SessionLocal() as db:
        now = datetime.now(timezone.utc)
        user = AuthUser(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            username=f"caseflow-{role.lower()}-{uuid.uuid4().hex[:8]}@example.invalid",
            display_name=f"{name} Caseflow",
            company="Test",
            password_hash=_hash(PASSWORD),
            role=role,
            status="ACTIVE",
            email_verified=True,
            created_at=now,
            updated_at=now,
        )
        db.add(user)
        db.flush()
        db.add(
            TenantMembership(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                user_id=user.id,
                status="ACTIVE",
                is_default=True,
                created_at=now,
                updated_at=now,
            )
        )
        db.commit()
        token = secrets.token_urlsafe(32)
        persist_session(db, token, user.id, tenant_id)
        user_id = str(user.id)
    client = TestClient(app)
    client.cookies.set("mdarix_session", token)
    return client, user_id


def _seed(tenant_id) -> dict:
    """A product with versions A and B: two recent complaints on A, an old one on B; another product with a version
    and a complaint; a lot and a failure mode."""
    now = datetime.now(timezone.utc)
    tag = uuid.uuid4().hex[:8].upper()
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)

        def product(suffix: str) -> Product:
            row = Product(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                product_identifier=f"CW-P-{tag}-{suffix}",
                name=f"Case Pump {tag} {suffix}",
                created_at=now,
                updated_at=now,
            )
            db.add(row)
            db.flush()
            return row

        def version(product_id, identifier: str) -> ProductVersion:
            row = ProductVersion(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                product_id=product_id,
                version_identifier=identifier,
                created_at=now,
                updated_at=now,
            )
            db.add(row)
            db.flush()
            return row

        def complaint(product_id, version_id, days_ago: int) -> str:
            row = Complaint(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                complaint_identifier=f"CW-C-{uuid.uuid4().hex[:10].upper()}",
                product_id=product_id,
                product_version_id=version_id,
                event_timestamp=now - timedelta(days=days_ago),
                description="Occlusion alarm without an occlusion",
                severity="MALFUNCTION",
                status="open",
                created_at=now,
                updated_at=now,
            )
            db.add(row)
            db.flush()
            return str(row.id)

        main, other = product("M"), product("O")
        version_a, version_b, other_version = (
            version(main.id, "Rev A"),
            version(main.id, "Rev B"),
            version(other.id, "X"),
        )
        complaints = [
            complaint(main.id, version_a.id, 5),
            complaint(main.id, version_a.id, 10),
            complaint(main.id, version_b.id, 400),
        ]
        foreign = complaint(other.id, other_version.id, 5)
        lot = LotBatch(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            lot_identifier=f"CW-L-{tag}",
            product_version_id=version_a.id,
            created_at=now,
            updated_at=now,
        )
        mode = FailureMode(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            failure_mode_identifier=f"CW-FM-{tag}",
            name="Sensor drift",
            created_at=now,
            updated_at=now,
        )
        db.add_all([lot, mode])
        db.commit()
        return {
            "product_id": str(main.id),
            "version_a": str(version_a.id),
            "version_b": str(version_b.id),
            "other_version": str(other_version.id),
            "complaints": complaints,
            "foreign_complaint": foreign,
            "lot_id": str(lot.id),
            "failure_mode_id": str(mode.id),
        }


def _open(client, seed: dict, complaints: list[str], *, assign_to_me: bool = True) -> dict:
    made = client.post(
        "/api/v1/investigations",
        json={
            "product_id": seed["product_id"],
            "investigation_question": QUESTION,
            "complaint_ids": complaints,
            "assign_to_me": assign_to_me,
        },
    )
    assert made.status_code == 201, made.text
    return made.json()


def _code(response) -> str | None:
    return (response.json().get("detail") or {}).get("code")


def _row(tenant_id, case_id) -> Investigation:
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        row = db.query(Investigation).filter(Investigation.id == uuid.UUID(str(case_id))).one()
        db.expunge(row)
        return row


def _links(tenant_id, case_id) -> set[str]:
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        return {
            str(row[0])
            for row in db.query(InvestigationComplaint.complaint_id).filter(
                InvestigationComplaint.investigation_id == uuid.UUID(str(case_id))
            )
        }


def _audits(tenant_id, case_id, action: str) -> list[AuditEvent]:
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        rows = (
            db.query(AuditEvent)
            .filter(AuditEvent.entity_id == uuid.UUID(str(case_id)), AuditEvent.action == action)
            .order_by(AuditEvent.created_at)
            .all()
        )
        db.expunge_all()
        return rows


def _case_tasks(tenant_id, case_id) -> list[WorkflowTask]:
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        rows = (
            db.query(WorkflowTask)
            .filter(WorkflowTask.investigation_id == uuid.UUID(str(case_id)))
            .order_by(WorkflowTask.created_at)
            .all()
        )
        db.expunge_all()
        return rows


def _foreign_case() -> str:
    """A case of another organization (the golden one)."""
    with SessionLocal() as db:
        bind_system(db, "test: a case of another organization")
        golden = db.query(Tenant.id).filter(Tenant.tenant_key == "ACME_CARE_SYNTHETIC").one()[0]
        return str(db.query(Investigation.id).filter(Investigation.tenant_id == golden).first()[0])


def _add(tenant_id, *rows) -> None:
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        db.add_all(rows)
        db.commit()


def _request(tenant_id, case_id, requested_by: str, *, status: str, priority: str = "MEDIUM", **extra):
    now = datetime.now(timezone.utc)
    return SupplierEvidenceRequest(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        investigation_id=uuid.UUID(str(case_id)),
        requested_by=requested_by,
        title="Bench test results of the returned pumps",
        requested_items={"items": ["Bench test report"]},
        status=status,
        priority=priority,
        created_at=now,
        updated_at=now,
        # A request always names who is asked (ck_supplier_evidence_requests_has_recipient): the supplier's contact.
        **{"recipient": "supplier.quality@example.invalid", **extra},
    )


def _evidence(tenant_id, case_id) -> Evidence:
    now = datetime.now(timezone.utc)
    return Evidence(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        evidence_identifier=f"CW-EV-{uuid.uuid4().hex[:10].upper()}",
        evidence_type="test_report",
        title="Bench test of the occlusion sensor",
        investigation_id=uuid.UUID(str(case_id)),
        created_at=now,
        updated_at=now,
    )


def _near(value: str, expected: datetime, tolerance: timedelta = timedelta(minutes=10)) -> bool:
    return abs(datetime.fromisoformat(value) - expected) <= tolerance


# ------------------------------------------------------------------------------------------------- opening


def test_a_new_case_opens_with_its_state_priority_due_date_and_first_scope(org):
    investigator, _ = org["investigator"]
    seed = _seed(org["tenant_id"])
    first, second, _ = seed["complaints"]
    case = _open(investigator, seed, [first, second])
    assert case["workflow_state"] == "IN_PROGRESS" and case["workflow_state_label"] == "In progress"
    assert case["priority"] == "MEDIUM" and _near(case["due_at"], datetime.now(timezone.utc) + timedelta(days=60))
    row = _row(org["tenant_id"], case["id"])
    assert row.status == "open" and row.workflow_state == "IN_PROGRESS" and row.state_changed_at is not None

    body = investigator.get(f"/api/v1/investigations/{case['id']}/scope")
    assert body.status_code == 200, body.text
    body = body.json()
    assert body["investigation"] == {
        "id": case["id"],
        "business_id": case["business_id"],
        "workflow_state": "IN_PROGRESS",
    }
    current = body["current"]
    assert current["version"] == 1 and current["question"] == QUESTION and current["change_reason"] is None
    assert [item["id"] for item in current["included_complaints"]] == [first, second]
    assert all(
        item["business_id"] and item["product_version"]["version_identifier"] == "Rev A"
        for item in current["included_complaints"]
    )
    assert [item["id"] for item in current["product_versions"]] == [seed["version_a"]]
    assert current["excluded_complaints"] == [] and current["created_by_name"] == "Investigator Caseflow"
    assert [item["version"] for item in body["versions"]] == [1]
    assert investigator.get(f"/api/v1/investigations/{case['id']}/scope/versions/1").json() == current

    queued = _open(investigator, seed, [], assign_to_me=False)
    assert queued["workflow_state"] == "OPEN" and queued["owner_ref"] is None
    empty = investigator.get(f"/api/v1/investigations/{queued['id']}/scope").json()["current"]
    assert empty["version"] == 1 and empty["included_complaints"] == [] and empty["product_versions"] == []
    opened = _audits(org["tenant_id"], queued["id"], "INVESTIGATION_OPENED")
    assert opened and opened[0].details["workflow_state"] == "OPEN" and opened[0].details["priority"] == "MEDIUM"


def _signal_needing_a_case(org, seed: dict) -> dict:
    lead, _ = org["lead"]
    made = lead.post(
        "/api/v1/triage/signals",
        json={
            "title": "Occlusion alarms rising",
            "product_id": seed["product_id"],
            "product_version_id": seed["version_a"],
            "complaint_ids": seed["complaints"][:2],
            "priority": "CRITICAL",
            "reason": "Customer reported alarms during infusion",
        },
    )
    assert made.status_code == 201, made.text
    signal = made.json()
    marked = lead.post(
        f"/api/v1/triage/signals/{signal['id']}/disposition",
        json={"disposition": "INVESTIGATION_REQUIRED", "reason": REASON},
    )
    assert marked.status_code == 200, marked.text
    return signal


def test_a_case_opened_from_a_signal_takes_its_priority(org):
    investigator, investigator_id = org["investigator"]
    _, colleague_id = org["colleague"]
    seed = _seed(org["tenant_id"])
    signal = _signal_needing_a_case(org, seed)
    opened = investigator.post(
        f"/api/v1/triage/signals/{signal['id']}/create-investigation",
        json={"investigation_question": QUESTION, "assignee_user_id": investigator_id},
    )
    assert opened.status_code == 201, opened.text
    case = opened.json()["investigation"]
    row = _row(org["tenant_id"], case["id"])
    # Opened by the person who takes it: in progress, due in 15 days as a critical case.
    assert row.priority == "CRITICAL" and row.workflow_state == "IN_PROGRESS"
    assert abs(row.due_at - (row.opened_at + timedelta(days=15))) < timedelta(seconds=1)
    scope = investigator.get(f"/api/v1/investigations/{case['id']}/scope").json()["current"]
    assert scope["version"] == 1 and {item["id"] for item in scope["included_complaints"]} == set(
        seed["complaints"][:2]
    )

    # Opened for a colleague: it waits for them (OPEN).
    other = _signal_needing_a_case(org, _seed(org["tenant_id"]))
    for_colleague = investigator.post(
        f"/api/v1/triage/signals/{other['id']}/create-investigation",
        json={"investigation_question": QUESTION, "assignee_user_id": colleague_id},
    )
    assert for_colleague.status_code == 201, for_colleague.text
    waiting = _row(org["tenant_id"], for_colleague.json()["investigation"]["id"])
    assert waiting.workflow_state == "OPEN" and waiting.priority == "CRITICAL"


def _task_of(client, view: str, case_id) -> dict:
    listed = client.get("/api/v1/tasks", params={"view": view, "page_size": 200})
    assert listed.status_code == 200, listed.text
    items = [
        item
        for item in listed.json()["items"]
        if item["task_type"] == "INVESTIGATION" and item["source"]["id"] == str(case_id)
    ]
    assert len(items) == 1, items
    return items[0]


def test_taking_the_case_task_starts_an_open_case(org):
    tenant_id = org["tenant_id"]
    investigator, _ = org["investigator"]
    colleague, colleague_id = org["colleague"]
    seed = _seed(tenant_id)

    claimed_case = _open(investigator, seed, [], assign_to_me=False)
    assert claimed_case["workflow_state"] == "OPEN"
    task = _task_of(colleague, "queue", claimed_case["id"])
    claimed = colleague.post(f"/api/v1/tasks/{task['id']}/claim")
    assert claimed.status_code == 200, claimed.text
    assert _row(tenant_id, claimed_case["id"]).workflow_state == "IN_PROGRESS"
    changed = _audits(tenant_id, claimed_case["id"], "INVESTIGATION_STATE_CHANGED")
    assert len(changed) == 1 and changed[0].actor_ref == colleague_id
    assert changed[0].new_values == {"workflow_state": "IN_PROGRESS"} and task["business_id"] in changed[0].reason

    accepted_case = _open(investigator, seed, [], assign_to_me=False)
    assigned = investigator.patch(
        f"/api/v1/investigations/{accepted_case['id']}", json={"reason": REASON, "assignee_id": colleague_id}
    )
    assert assigned.status_code == 200, assigned.text
    assert assigned.json()["workflow_state"] == "OPEN"  # assigning alone does not start the work
    task = _task_of(colleague, "assigned", accepted_case["id"])
    assert task["status"] == "ASSIGNED"
    accepted = colleague.post(f"/api/v1/tasks/{task['id']}/accept")
    assert accepted.status_code == 200, accepted.text
    assert _row(tenant_id, accepted_case["id"]).workflow_state == "IN_PROGRESS"
    # One move: OPEN to IN_PROGRESS when the task was accepted.
    assert len(_audits(tenant_id, accepted_case["id"], "INVESTIGATION_STATE_CHANGED")) == 1


# ------------------------------------------------------------------------------------------------ transitions


def _move(client, case_id, to_state: str, reason: str = REASON):
    return client.post(f"/api/v1/investigations/{case_id}/transition", json={"to_state": to_state, "reason": reason})


def test_moving_a_case_between_states(org):
    tenant_id = org["tenant_id"]
    investigator, _ = org["investigator"]
    lead, lead_id = org["lead"]
    viewer, _ = org["viewer"]
    seed = _seed(tenant_id)
    case = _open(investigator, seed, [seed["complaints"][0]])

    held = _move(investigator, case["id"], "ON_HOLD")
    assert held.status_code == 200, held.text
    assert held.json()["workflow_state"] == "ON_HOLD" and held.json()["workflow_state_label"] == "On hold"
    assert held.json()["status"] == "open" and held.json()["closed_at"] is None and held.json()["state_changed_at"]
    again = _move(investigator, case["id"], "ON_HOLD")
    assert again.status_code == 409 and _code(again) == "INVALID_TRANSITION"
    assert _move(investigator, case["id"], "IN_PROGRESS").json()["workflow_state"] == "IN_PROGRESS"
    for target in ("OPEN", "CLOSED", "BRIEF_IN_REVIEW", "READY_FOR_DECISION", "DECIDED"):
        refused = _move(investigator, case["id"], target)
        assert refused.status_code == 409 and _code(refused) == "INVALID_TRANSITION", target
    assert _move(investigator, case["id"], "ON_HOLD", "too short").status_code == 422
    assert _move(investigator, case["id"], "PAUSED").status_code == 422

    # Starting and holding need investigation.work; cancelling needs investigation.assign.
    for client, target in ((viewer, "ON_HOLD"), (lead, "ON_HOLD"), (investigator, "CANCELLED"), (viewer, "CANCELLED")):
        refused = _move(client, case["id"], target)
        assert refused.status_code == 403 and _code(refused) == "PERMISSION_DENIED", (target, refused.text)
    assert _move(investigator, uuid.uuid4(), "ON_HOLD").status_code == 404
    foreign = _move(lead, _foreign_case(), "CANCELLED")
    assert foreign.status_code == 404 and _code(foreign) == "INVESTIGATION_NOT_FOUND"

    # A decision waiting for its review keeps the case from being cancelled.
    now = datetime.now(timezone.utc)
    decision_id = uuid.uuid4()
    decision = Decision(
        id=decision_id,
        tenant_id=tenant_id,
        investigation_id=uuid.UUID(case["id"]),
        decision_identifier=f"CW-PEND-{uuid.uuid4().hex[:8]}",
        decision_type="DISPOSITION",
        disposition="REQUIRES_REVIEW",
        rationale="Pending",
        decision_status="REQUIRES_REVIEW",
        authorized_by_ref="x",
        updated_at=now,
        decision_timestamp=now,
        created_at=now,
    )
    _add(tenant_id, decision)
    blocked = _move(lead, case["id"], "CANCELLED")
    assert blocked.status_code == 409 and _code(blocked) == "DECISIONS_AWAITING_REVIEW"
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        db.query(Decision).filter(Decision.id == decision_id).delete(synchronize_session=False)
        db.commit()

    cancelled = _move(lead, case["id"], "CANCELLED")
    assert cancelled.status_code == 200, cancelled.text
    body = cancelled.json()
    assert body["workflow_state"] == "CANCELLED" and body["status"] == "closed" and body["closed_at"]
    tasks = _case_tasks(tenant_id, case["id"])
    assert tasks and all(task.status in ("COMPLETED", "CANCELLED", "SUPERSEDED") for task in tasks)
    assert any(task.status == "CANCELLED" and task.completion_outcome == "CASE_CANCELLED" for task in tasks)
    # A cancelled case is closed for everything that reads its status.
    path = f"/api/v1/investigations/{case['id']}"
    frozen = investigator.patch(path, json={"reason": REASON, "investigation_question": QUESTION + " (edited)"})
    assert frozen.status_code == 409 and _code(frozen) == "INVESTIGATION_CLOSED"
    scope = investigator.put(f"{path}/scope", json={"question": QUESTION, "change_reason": REASON})
    assert scope.status_code == 409 and _code(scope) == "INVESTIGATION_CLOSED"
    assert _move(investigator, case["id"], "ON_HOLD").status_code == 409

    resumed = _move(investigator, case["id"], "IN_PROGRESS")
    assert resumed.status_code == 200, resumed.text
    assert resumed.json()["status"] == "open" and resumed.json()["closed_at"] is None
    open_tasks = [
        task
        for task in _case_tasks(tenant_id, case["id"])
        if task.status not in ("COMPLETED", "CANCELLED", "SUPERSEDED")
    ]
    assert [task.task_type for task in open_tasks] == ["INVESTIGATION"]

    changes = _audits(tenant_id, case["id"], "INVESTIGATION_STATE_CHANGED")
    cancel = [event for event in changes if (event.new_values or {}).get("workflow_state") == "CANCELLED"]
    assert len(cancel) == 1 and cancel[0].actor_ref == lead_id and cancel[0].reason == REASON
    assert cancel[0].old_values == {"workflow_state": "IN_PROGRESS", "status": "open"}
    assert cancel[0].new_values == {"workflow_state": "CANCELLED", "status": "closed"}
    assert len(changes) == 4  # held, resumed, cancelled, taken up again


# ----------------------------------------------------------------------------------------------------- scope


def _put_scope(client, case_id, **body):
    return client.put(f"/api/v1/investigations/{case_id}/scope", json={"question": QUESTION, **body})


def test_saving_the_scope_versions_it_and_keeps_the_complaint_links_in_step(org):
    tenant_id = org["tenant_id"]
    investigator, _ = org["investigator"]
    seed = _seed(tenant_id)
    first, second, old = seed["complaints"]
    case = _open(investigator, seed, [first, second])

    no_reason = _put_scope(investigator, case["id"], included_complaint_ids=[first])
    assert no_reason.status_code == 422 and _code(no_reason) == "CHANGE_REASON_REQUIRED"
    both = _put_scope(
        investigator,
        case["id"],
        included_complaint_ids=[first],
        excluded_complaints=[{"complaint_id": first, "reason": "Duplicate report"}],
        change_reason=REASON,
    )
    assert both.status_code == 422 and _code(both) == "COMPLAINT_INCLUDED_AND_EXCLUDED"
    for body, code in (
        ({"included_complaint_ids": [seed["foreign_complaint"]]}, "COMPLAINT_NOT_FOR_PRODUCT"),
        (
            {"excluded_complaints": [{"complaint_id": str(uuid.uuid4()), "reason": "Unknown"}]},
            "COMPLAINT_NOT_FOR_PRODUCT",
        ),
        ({"product_version_ids": [seed["other_version"]]}, "VERSION_NOT_FOR_PRODUCT"),
        ({"lot_ids": [str(uuid.uuid4())]}, "LOT_NOT_FOUND"),
        ({"failure_mode_ids": [str(uuid.uuid4())]}, "FAILURE_MODE_NOT_FOUND"),
    ):
        refused = _put_scope(investigator, case["id"], change_reason=REASON, **body)
        assert refused.status_code == 422 and _code(refused) == code, (code, refused.text)
    for name in ("viewer", "lead"):
        refused = _put_scope(org[name][0], case["id"], change_reason=REASON)
        assert refused.status_code == 403 and _code(refused) == "PERMISSION_DENIED", name
    assert investigator.get(f"/api/v1/investigations/{_foreign_case()}/scope").status_code == 404
    assert _put_scope(investigator, _foreign_case(), change_reason=REASON).status_code == 404
    assert len(investigator.get(f"/api/v1/investigations/{case['id']}/scope").json()["versions"]) == 1

    today = datetime.now(timezone.utc).date()
    new_question = "Why do occlusion alarms rise on Rev A pumps since January?"
    saved = _put_scope(
        investigator,
        case["id"],
        question=new_question,
        product_version_ids=[seed["version_a"]],
        included_complaint_ids=[first, old],
        excluded_complaints=[{"complaint_id": second, "reason": "Duplicate of the first report"}],
        lot_ids=[seed["lot_id"]],
        markets=["EU", " eu "],
        failure_mode_ids=[seed["failure_mode_id"]],
        date_from=(today - timedelta(days=30)).isoformat(),
        date_to=today.isoformat(),
        objectives="Find the cause of the false alarms",
        change_reason=REASON,
        reviews_must_restart=True,
    )
    assert saved.status_code == 200, saved.text
    body = saved.json()
    current = body["scope"]
    assert current["version"] == 2 and current["question"] == new_question and current["change_reason"] == REASON
    assert [item["id"] for item in current["included_complaints"]] == [first, old]
    excluded = current["excluded_complaints"]
    assert [(item["id"], item["reason"]) for item in excluded] == [(second, "Duplicate of the first report")]
    assert excluded[0]["business_id"] and excluded[0]["complaint_identifier"]
    assert current["lots"][0]["id"] == seed["lot_id"] and current["lots"][0]["lot_identifier"].startswith("CW-L-")
    assert current["failure_modes"][0]["name"] == "Sensor drift" and current["markets"] == ["EU"]
    assert current["date_from"] == (today - timedelta(days=30)).isoformat() and current["date_to"] == today.isoformat()
    assert current["reviews_must_restart"] and not current["conclusions_invalidated"]
    assert current["created_by_name"] == "Investigator Caseflow"
    diff = body["diff"]
    assert [item["id"] for item in diff["added_complaints"]] == [old]
    assert [item["id"] for item in diff["removed_complaints"]] == [second]
    assert [item["id"] for item in diff["newly_excluded"]] == [second]
    assert diff["versions_added"] == [] and diff["versions_removed"] == [] and diff["question_changed"]
    # The old complaint is on Rev B and before the chosen dates: worth a second look, not an error.
    old_id = diff["added_complaints"][0]["business_id"]
    assert len(body["warnings"]) == 2 and all(old_id in warning for warning in body["warnings"])

    # The case follows its scope: its question and its complaint links.
    assert _row(tenant_id, case["id"]).investigation_question == new_question
    assert _links(tenant_id, case["id"]) == {first, old}
    audit = _audits(tenant_id, case["id"], "INVESTIGATION_SCOPE_CHANGED")
    assert len(audit) == 1 and audit[0].reason == REASON
    assert audit[0].details["version"] == 2 and audit[0].details["added_complaints"] == 1
    assert audit[0].details["removed_complaints"] == 1 and audit[0].details["complaint_links_removed"] == 1
    assert audit[0].new_values == {"question": new_question}

    history = investigator.get(f"/api/v1/investigations/{case['id']}/scope").json()
    assert history["current"] == current
    assert [item["version"] for item in history["versions"]] == [2, 1]
    assert history["versions"][0]["change_reason"] == REASON and history["versions"][0]["reviews_must_restart"]
    assert history["versions"][0]["created_by_name"] == "Investigator Caseflow"
    assert history["versions"][0]["created_role"] == "INVESTIGATOR"
    first_version = investigator.get(f"/api/v1/investigations/{case['id']}/scope/versions/1").json()
    assert [item["id"] for item in first_version["included_complaints"]] == [first, second]
    missing = investigator.get(f"/api/v1/investigations/{case['id']}/scope/versions/3")
    assert missing.status_code == 404 and _code(missing) == "SCOPE_VERSION_NOT_FOUND"
    assert investigator.get(f"/api/v1/investigations/{case['id']}/scope/versions/0").status_code == 422


def test_the_first_scope_saved_on_an_open_case_starts_it(org):
    tenant_id = org["tenant_id"]
    investigator, _ = org["investigator"]
    seed = _seed(tenant_id)
    case = _open(investigator, seed, [], assign_to_me=False)
    assert case["workflow_state"] == "OPEN"
    saved = _put_scope(investigator, case["id"], included_complaint_ids=seed["complaints"][:1], change_reason=REASON)
    assert saved.status_code == 200, saved.text
    assert _row(tenant_id, case["id"]).workflow_state == "IN_PROGRESS"
    assert _links(tenant_id, case["id"]) == set(seed["complaints"][:1])
    assert len(_audits(tenant_id, case["id"], "INVESTIGATION_STATE_CHANGED")) == 1


# --------------------------------------------------------------------------------------------------- managing


def test_managing_a_case_sets_priority_due_date_and_versions_a_new_question(org):
    tenant_id = org["tenant_id"]
    investigator, _ = org["investigator"]
    seed = _seed(tenant_id)
    case = _open(investigator, seed, seed["complaints"][:1])
    path = f"/api/v1/investigations/{case['id']}"
    due = (datetime.now(timezone.utc) + timedelta(days=10)).replace(microsecond=0)
    patched = investigator.patch(path, json={"reason": REASON, "priority": "HIGH", "due_at": due.isoformat()})
    assert patched.status_code == 200, patched.text
    body = patched.json()
    assert body["priority"] == "HIGH" and datetime.fromisoformat(body["due_at"]) == due
    assert body["workflow_state"] == "IN_PROGRESS" and body["status"] == "open"
    updated = _audits(tenant_id, case["id"], "INVESTIGATION_UPDATED")[-1]
    assert updated.reason == REASON and updated.old_values["priority"] == "MEDIUM"
    assert updated.new_values["priority"] == "HIGH" and updated.new_values["due_at"] == due.isoformat()
    assert body["owner_name"] == "Investigator Caseflow"
    assert investigator.patch(path, json={"reason": REASON, "priority": "URGENT"}).status_code == 422
    # Leaving the due date out keeps it; null clears it.
    kept = investigator.patch(path, json={"reason": REASON, "priority": "HIGH"}).json()
    assert datetime.fromisoformat(kept["due_at"]) == due
    cleared = investigator.patch(path, json={"reason": REASON, "due_at": None})
    assert cleared.status_code == 200 and cleared.json()["due_at"] is None
    assert _audits(tenant_id, case["id"], "INVESTIGATION_UPDATED")[-1].new_values == {"due_at": None}

    reason = "The question was too broad for the evidence we hold"
    new_question = "Why do occlusion alarms rise on Rev A pumps after release B?"
    edited = investigator.patch(path, json={"reason": reason, "investigation_question": new_question})
    assert edited.status_code == 200, edited.text
    scope = investigator.get(f"{path}/scope").json()
    assert scope["current"]["version"] == 2 and scope["current"]["question"] == new_question
    assert scope["current"]["change_reason"] == reason
    assert [item["id"] for item in scope["current"]["included_complaints"]] == seed["complaints"][:1]

    closed = investigator.patch(path, json={"reason": REASON, "status": "closed"})
    assert closed.status_code == 200 and closed.json()["workflow_state"] == "CLOSED"
    assert _row(tenant_id, case["id"]).workflow_state == "CLOSED"
    frozen = investigator.patch(path, json={"reason": REASON, "priority": "LOW"})
    assert frozen.status_code == 409 and _code(frozen) == "INVESTIGATION_CLOSED"
    reopened = investigator.patch(path, json={"reason": REASON, "status": "open"})
    assert reopened.status_code == 200 and reopened.json()["workflow_state"] == "IN_PROGRESS"
    assert reopened.json()["status"] == "open" and reopened.json()["closed_at"] is None


# -------------------------------------------------------------------------------------------------- readiness


def _results(body: dict) -> dict:
    return {check["key"]: check["result"] for check in body["checks"]}


def test_the_readiness_of_a_case(org):
    tenant_id = org["tenant_id"]
    investigator, investigator_id = org["investigator"]
    viewer, _ = org["viewer"]
    seed = _seed(tenant_id)
    case = _open(investigator, seed, seed["complaints"][:1])
    path = f"/api/v1/investigations/{case['id']}/readiness"
    first = viewer.get(path)  # reading needs only a session
    assert first.status_code == 200, first.text
    body = first.json()
    assert body["workflow_state"] == "IN_PROGRESS"
    assert [step["key"] for step in body["steps"]][0] == "overview" and len(body["steps"]) == 9
    results = _results(body)
    assert results["scope_complete"] == "PASS" and results["evidence_reviewed"] == "PENDING"
    assert results["no_blocking_request"] == "PASS" and results["unknowns"] == "PASS"
    # A medium-priority case whose complaint reports no injury, death or malfunction: no review is required.
    assert results["risk_review"] == results["regulatory_review"] == "NOT_REQUIRED"
    assert results["brief_ready"] == "PENDING" and results["decision"] == "PENDING"

    now = datetime.now(timezone.utc)
    _add(
        tenant_id,
        _evidence(tenant_id, case["id"]),
        _request(tenant_id, case["id"], investigator_id, status="SENT", priority="HIGH"),
        Unknown(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            investigation_id=uuid.UUID(case["id"]),
            description="Lot of the returned device",
            status="open",
            created_at=now,
            updated_at=now,
        ),
    )
    body = investigator.get(path).json()
    results = _results(body)
    assert results["no_blocking_request"] == "BLOCKED" and results["unknowns"] == "PENDING"
    assert results["evidence_reviewed"] == "PENDING"
    steps = {step["key"]: step["status"] for step in body["steps"]}
    assert steps["evidence"] == "BLOCKED" and steps["gaps"] == "IN_PROGRESS"
    rationale = {check["key"]: check["rationale"] for check in body["checks"]}
    assert rationale["evidence_reviewed"] == "1 of 1 pieces of evidence are not reviewed yet"

    assert investigator.get(f"/api/v1/investigations/{uuid.uuid4()}/readiness").status_code == 404
    assert investigator.get(f"/api/v1/investigations/{_foreign_case()}/readiness").status_code == 404


# --------------------------------------------------------------------------------------------- my open cases


def test_my_open_cases_and_what_waits_on_them(org):
    tenant_id = org["tenant_id"]
    investigator, _ = org["investigator"]
    me, me_id = _client(tenant_id, "INVESTIGATOR", "Dashboard")
    seed = _seed(tenant_id)
    first, second, _ = seed["complaints"]
    now = datetime.now(timezone.utc)

    def manage(case, **body):
        response = me.patch(f"/api/v1/investigations/{case['id']}", json={"reason": REASON, **body})
        assert response.status_code == 200, response.text

    low = _open(me, seed, [first])
    manage(low, priority="LOW")
    critical = _open(me, seed, [second])
    manage(critical, priority="CRITICAL", due_at=(now - timedelta(days=1)).isoformat())
    held = _open(me, seed, [])
    assert _move(me, held["id"], "ON_HOLD").status_code == 200
    manage(held, due_at=(now + timedelta(days=3)).isoformat())
    closed = _open(me, seed, [])
    manage(closed, status="closed")
    queued = _open(me, seed, [], assign_to_me=False)
    someone_elses = _open(investigator, seed, [])
    _add(
        tenant_id,
        _evidence(tenant_id, low["id"]),
        _request(tenant_id, critical["id"], me_id, status="SENT", priority="HIGH"),
        _request(tenant_id, critical["id"], me_id, status="REPLIED"),
        _request(tenant_id, critical["id"], me_id, status="REVIEWED", reviewed_at=now),
    )

    summary = me.get("/api/v1/investigations/mine/summary")
    assert summary.status_code == 200, summary.text
    body = summary.json()
    ids = [item["id"] for item in body["cases"]]
    # Most urgent first; closed, unowned and other people's cases are not mine.
    assert ids == [critical["id"], held["id"], low["id"]]
    assert not {closed["id"], queued["id"], someone_elses["id"]} & set(ids)
    by_id = {item["id"]: item for item in body["cases"]}
    top = by_id[critical["id"]]
    assert top["priority"] == "CRITICAL" and top["overdue"] and top["open_requests"] == 2
    assert top["workflow_state"] == "IN_PROGRESS" and top["workflow_state_label"] == "In progress"
    assert top["product"]["id"] == seed["product_id"] and top["product"]["name"].startswith("Case Pump")
    assert top["question"] == QUESTION and top["business_id"] == critical["business_id"]
    assert top["owner_name"] == "Dashboard Caseflow"
    assert by_id[low["id"]]["unreviewed_evidence"] == 1 and not by_id[low["id"]]["overdue"]
    assert by_id[held["id"]]["workflow_state"] == "ON_HOLD" and by_id[held["id"]]["open_unknowns"] == 0
    assert body["counts"] == {
        "open": 0,
        "in_progress": 2,
        "on_hold": 1,
        "due_soon": 1,
        "overdue": 1,
        "unreviewed_evidence": 1,
        "requests_waiting": 1,
        "requests_to_review": 1,
    }
    nothing = org["viewer"][0].get("/api/v1/investigations/mine/summary").json()
    assert nothing["cases"] == [] and set(nothing["counts"]) == set(body["counts"])
