"""Signals and triage end to end: manual signals, triage, priority, each disposition, duplicate and merge lineage,
adding complaints, opening a case from a signal (its task and links), detection (idempotent, monitoring reopened),
the rule settings, list filters, organization isolation, permissions, and signals following their case.

Everything runs in a fresh organization of its own (on the shared plane), deleted at the end, so detection there sees
only this module's complaints and nothing is left in the golden organization.
"""

from __future__ import annotations

import secrets
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from auth.durable import persist_session
from auth.service import _hash
from backend.app.db.models.foundation import (
    AuditEvent,
    AuthUser,
    Complaint,
    Decision,
    Investigation,
    Product,
    ProductVersion,
    TenantMembership,
)
from backend.app.db.models.signals import InvestigationSignal, Signal, SignalComplaint, SignalEvent
from backend.app.db.models.workflow import WorkflowTask
from backend.app.db.session import SessionLocal
from backend.app.db.tenant_scope import bind_tenant
from backend.app.main import app
from tests.reports_seed import role_client

PASSWORD = "Signals triage 2026!"
REASON = "Reason recorded for the audit trail"


# B6b B3: the scenarios this file verifies (requirements.csv, class A); file level, so every test here carries them.
pytestmark = pytest.mark.requirement("CI-13", "IN-05", "TR-27", "TR-28", "TR-29", "TR-30", "TR-31")


@pytest.fixture(scope="module")
def org():
    """A fresh organization with a triage lead, two investigators and a viewer, removed afterwards."""
    from backend.app.customer_lifecycle import build_customer_tenant
    from backend.app.trial.retention import purge_trial

    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        customer, tenant = build_customer_tenant(
            db=db, tenant_key=f"SIGNALS_{uuid.uuid4().hex[:8].upper()}", name="Signals triage", status="ACTIVE", now=now
        )
        db.add(customer)
        db.add(tenant)
        db.commit()  # registers the organization on the shared plane (migration md20)
        tenant_id = tenant.id
    people = {}
    for name, role in (
        ("lead", "TRIAGE_LEAD"),
        ("investigator", "INVESTIGATOR"),
        ("colleague", "INVESTIGATOR"),
        ("viewer", "VIEWER"),
    ):
        people[name] = _client(tenant_id, role)
    try:
        yield {"tenant_id": tenant_id, **people}
    finally:
        with SessionLocal() as db:
            purge_trial(db, tenant_id, "test:signals-triage-cleanup")


def _client(tenant_id, role: str) -> tuple[TestClient, str]:
    with SessionLocal() as db:
        now = datetime.now(timezone.utc)
        user = AuthUser(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            username=f"signals-{role.lower()}-{uuid.uuid4().hex[:8]}@example.invalid",
            display_name=f"{role.title()} Signals",
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


def _seed(tenant_id, *, complaints: int, problem: str | None = None, days_ago: int = 2, **flags) -> dict:
    """A product with one version and ``complaints`` complaints about ``problem``, ``days_ago`` days ago."""
    now = datetime.now(timezone.utc)
    tag = uuid.uuid4().hex[:8].upper()
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        product = Product(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            product_identifier=f"SIG-P-{tag}",
            name=f"Signal Pump {tag}",
            created_at=now,
            updated_at=now,
        )
        db.add(product)
        db.flush()
        version = ProductVersion(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            product_id=product.id,
            version_identifier="Rev C",
            created_at=now,
            updated_at=now,
        )
        db.add(version)
        db.flush()
        ids = [_complaint(db, tenant_id, product.id, version.id, problem, days_ago, **flags) for _ in range(complaints)]
        db.commit()
        return {"product_id": str(product.id), "version_id": str(version.id), "complaint_ids": ids}


def _complaint(db, tenant_id, product_id, version_id, problem, days_ago, **flags) -> str:
    now = datetime.now(timezone.utc)
    identifier = f"SIG-C-{uuid.uuid4().hex[:10].upper()}"
    row = Complaint(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        complaint_identifier=identifier,
        product_id=uuid.UUID(str(product_id)),
        product_version_id=uuid.UUID(str(version_id)) if version_id else None,
        event_timestamp=now - timedelta(days=days_ago),
        description="Occlusion alarm without an occlusion",
        problem_code=problem,
        status="open",
        created_at=now,
        updated_at=now,
        **flags,
    )
    db.add(row)
    db.flush()
    return str(row.id)


def _add_complaint(tenant_id, seed: dict, problem: str | None, **flags) -> str:
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        complaint_id = _complaint(db, tenant_id, seed["product_id"], seed["version_id"], problem, 1, **flags)
        db.commit()
        return complaint_id


def _manual(client, seed: dict, title: str = "Occlusion alarms rising", **extra) -> dict:
    made = client.post(
        "/api/v1/triage/signals",
        json={
            "title": title,
            "product_id": seed["product_id"],
            "product_version_id": seed["version_id"],
            "complaint_ids": seed["complaint_ids"],
            **extra,
        },
    )
    assert made.status_code == 201, made.text
    return made.json()


def _tasks(tenant_id, signal_id, task_type: str = "SIGNAL_TRIAGE") -> list[WorkflowTask]:
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        rows = (
            db.query(WorkflowTask)
            .filter(WorkflowTask.source_entity_id == uuid.UUID(str(signal_id)), WorkflowTask.task_type == task_type)
            .order_by(WorkflowTask.created_at)
            .all()
        )
        db.expunge_all()
        return rows


def _signal(tenant_id, signal_id) -> Signal:
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        row = db.query(Signal).filter(Signal.id == uuid.UUID(str(signal_id))).one()
        db.expunge_all()
        return row


def _post(client, signal: dict, action: str, body: dict | None = None):
    return client.post(f"/api/v1/triage/signals/{signal['id']}/{action}", json=body or {})


def _code(response) -> str | None:
    detail = response.json().get("detail")
    return detail.get("code") if isinstance(detail, dict) else None


# ----------------------------------------------------------------------------------------------- manual + triage


def test_a_manual_signal_is_triaged_prioritised_and_monitored(org):
    lead, lead_id = org["lead"]
    seed = _seed(org["tenant_id"], complaints=2, problem="OCCLUSION")
    signal = _manual(lead, seed, description="Two alarms in a week")
    assert signal["business_id"].startswith("SIG") and signal["id"]
    assert signal["origin"] == "MANUAL" and signal["origin_label"] and signal["status"] == "NEW"
    assert signal["status_label"] == "New" and signal["complaint_count"] == 2 and signal["recent_complaints_7d"] == 2
    assert signal["problem_key"] == "OCCLUSION" and signal["suggested_priority"] == "LOW"
    assert signal["priority"] == "LOW" and signal["confirmed_priority"] is None
    assert signal["product"]["id"] == seed["product_id"] and signal["product"]["business_id"]
    assert signal["product_version"]["version_identifier"] == "Rev C"
    assert signal["owner"] is None and signal["due_at"] and not signal["overdue"]
    assert signal["actions"]["can_start"] and not signal["actions"]["can_create_investigation"]
    assert {item["added_how"] for item in signal["complaints"]} == {"MANUAL"}
    assert all(item["business_id"] for item in signal["complaints"])
    assert signal["version_split"] == [
        {
            "product_version_id": seed["version_id"],
            "product_version_business_id": signal["product_version"]["business_id"],
            "version_identifier": "Rev C",
            "count": 2,
        }
    ]
    assert set(signal["related"]) == {"changes", "open_capas", "open_investigations"}
    assert [event["event_type"] for event in signal["events"]] == ["CREATED"]
    assert signal["events"][0]["actor_role"] == "TRIAGE_LEAD" and signal["events"][0]["actor_name"]
    (task,) = _tasks(org["tenant_id"], signal["id"])
    assert task.status == "NEW" and task.assigned_role == "TRIAGE_LEAD" and task.assigned_user_id is None
    assert task.title.startswith(f"Triage {signal['business_id']}:") and task.priority == "LOW"
    # My Work shows the task with the signal's number.
    queued = lead.get("/api/v1/tasks", params={"view": "queue", "page_size": 200}).json()["items"]
    mine = [item for item in queued if item["source"]["id"] == signal["id"]]
    assert mine and mine[0]["source"]["business_id"] == signal["business_id"]
    assert mine[0]["source"]["label"] == f"Signal {signal['business_id']}"

    started = _post(lead, signal, "start")
    assert started.status_code == 200, started.text
    body = started.json()
    assert body["status"] == "TRIAGE" and body["owner"] == {"id": lead_id, "name": "Triage_Lead Signals"}
    (task,) = _tasks(org["tenant_id"], signal["id"])
    assert task.status == "ACCEPTED" and str(task.assigned_user_id) == lead_id
    again = _post(lead, signal, "start")
    assert again.status_code == 409 and _code(again) == "SIGNAL_STATE_CONFLICT"

    no_reason = _post(lead, signal, "priority", {"priority": "HIGH"})
    assert no_reason.status_code == 422 and _code(no_reason) == "REASON_REQUIRED"
    raised = _post(lead, signal, "priority", {"priority": "HIGH", "reason": "Pattern matches a known field issue"})
    assert raised.status_code == 200, raised.text
    body = raised.json()
    assert body["confirmed_priority"] == "HIGH" and body["priority"] == "HIGH"
    assert body["priority_reason"] == "Pattern matches a known field issue"
    assert _tasks(org["tenant_id"], signal["id"])[0].priority == "HIGH"
    # The suggested priority needs no reason.
    assert _post(lead, signal, "priority", {"priority": "LOW"}).status_code == 200

    missing = _post(lead, signal, "disposition", {"disposition": "MONITOR", "reason": REASON})
    assert missing.status_code == 422 and _code(missing) == "MONITOR_DETAILS_REQUIRED"
    past = _post(
        lead,
        signal,
        "disposition",
        {"disposition": "MONITOR", "reason": REASON, "monitor_review_date": "2020-01-01", "monitor_trigger": "More"},
    )
    assert past.status_code == 422 and _code(past) == "REVIEW_DATE_NOT_FUTURE"
    review = (datetime.now(timezone.utc).date() + timedelta(days=14)).isoformat()
    monitored = _post(
        lead,
        signal,
        "disposition",
        {"disposition": "MONITOR", "reason": REASON, "monitor_review_date": review, "monitor_trigger": "Two more"},
    )
    assert monitored.status_code == 200, monitored.text
    body = monitored.json()
    assert body["status"] == "MONITOR" and body["disposition"]["monitor_review_date"] == review
    assert body["disposition"]["reason"] == REASON and body["disposition"]["by_name"]
    (task,) = _tasks(org["tenant_id"], signal["id"])
    assert task.status == "COMPLETED" and task.completion_outcome == "MONITOR"
    assert [event["event_type"] for event in body["events"]] == [
        "CREATED",
        "TRIAGE_STARTED",
        "PRIORITY_SET",
        "PRIORITY_SET",
        "DISPOSITIONED",
    ]
    with SessionLocal() as db:
        bind_tenant(db, org["tenant_id"])
        actions = {
            row[0] for row in db.query(AuditEvent.action).filter(AuditEvent.entity_id == uuid.UUID(signal["id"]))
        }
    assert {"SIGNAL_CREATED", "SIGNAL_TRIAGE_STARTED", "SIGNAL_PRIORITY_SET", "SIGNAL_DISPOSITIONED"} <= actions


def test_creating_a_signal_checks_product_version_complaints_and_priority_reason(org):
    lead, _ = org["lead"]
    seed = _seed(org["tenant_id"], complaints=1, problem="LEAK")
    other = _seed(org["tenant_id"], complaints=1, problem="LEAK")
    base = {"title": "Leaks on the pump", "product_id": seed["product_id"]}
    missing = lead.post("/api/v1/triage/signals", json={**base, "product_id": str(uuid.uuid4())})
    assert missing.status_code == 404 and _code(missing) == "PRODUCT_NOT_FOUND"
    version = lead.post("/api/v1/triage/signals", json={**base, "product_version_id": other["version_id"]})
    assert version.status_code == 422 and _code(version) == "VERSION_NOT_FOR_PRODUCT"
    foreign = lead.post("/api/v1/triage/signals", json={**base, "complaint_ids": other["complaint_ids"]})
    assert foreign.status_code == 422 and _code(foreign) == "COMPLAINT_NOT_FOR_PRODUCT"
    no_reason = lead.post("/api/v1/triage/signals", json={**base, "priority": "CRITICAL"})
    assert no_reason.status_code == 422 and _code(no_reason) == "REASON_REQUIRED"
    made = lead.post(
        "/api/v1/triage/signals", json={**base, "priority": "CRITICAL", "reason": "Customer reported a fire risk"}
    )
    assert made.status_code == 201, made.text
    assert made.json()["confirmed_priority"] == "CRITICAL" and made.json()["complaint_count"] == 0


def test_viewers_and_investigators_cannot_triage(org):
    lead, _ = org["lead"]
    seed = _seed(org["tenant_id"], complaints=1, problem="NOISE")
    signal = _manual(lead, seed)
    for name in ("viewer", "investigator"):
        client, _ = org[name]
        assert client.get(f"/api/v1/triage/signals/{signal['id']}").status_code == 200  # reading is open
        for response in (
            client.post("/api/v1/triage/signals", json={"title": "Not allowed", "product_id": seed["product_id"]}),
            _post(client, signal, "start"),
            _post(client, signal, "priority", {"priority": "HIGH", "reason": REASON}),
            _post(client, signal, "disposition", {"disposition": "NO_ACTION", "reason": REASON}),
            client.post("/api/v1/triage/rules/run"),
        ):
            assert response.status_code == 403 and _code(response) == "PERMISSION_DENIED", (name, response.text)
        detail = client.get(f"/api/v1/triage/signals/{signal['id']}").json()
        assert not detail["actions"]["can_start"] and not detail["actions"]["can_disposition"]
    viewer, _ = org["viewer"]
    refused = _post(viewer, signal, "create-investigation", {"investigation_question": "Why the noise rises?"})
    assert refused.status_code == 403 and _code(refused) == "PERMISSION_DENIED"


def test_no_action_and_escalation(org):
    lead, _ = org["lead"]
    seed = _seed(org["tenant_id"], complaints=1, problem="DISPLAY")
    quiet = _manual(lead, seed, title="Display flicker reports")
    closed = _post(lead, quiet, "disposition", {"disposition": "NO_ACTION", "reason": REASON})
    assert closed.status_code == 200 and closed.json()["status"] == "NO_ACTION"
    assert _tasks(org["tenant_id"], quiet["id"])[0].completion_outcome == "NO_ACTION"
    late = _post(lead, quiet, "disposition", {"disposition": "ESCALATED", "reason": REASON})
    assert late.status_code == 409 and _code(late) == "SIGNAL_STATE_CONFLICT"

    urgent = _manual(lead, _seed(org["tenant_id"], complaints=1, problem="DISPLAY"), title="Display goes blank")
    escalated = _post(lead, urgent, "disposition", {"disposition": "ESCALATED", "reason": REASON})
    assert escalated.status_code == 200, escalated.text
    body = escalated.json()
    assert body["status"] == "ESCALATED" and body["confirmed_priority"] == "CRITICAL" and body["priority"] == "CRITICAL"
    assert body["actions"]["can_disposition"]
    assert _tasks(org["tenant_id"], urgent["id"])[0].completion_outcome == "ESCALATED"
    refused = _post(lead, urgent, "disposition", {"disposition": "NO_ACTION", "reason": REASON})
    assert refused.status_code == 409
    onward = _post(lead, urgent, "disposition", {"disposition": "INVESTIGATION_REQUIRED", "reason": REASON})
    assert onward.status_code == 200 and onward.json()["status"] == "INVESTIGATION_REQUIRED"


def test_duplicates_and_merges_keep_their_lineage(org):
    lead, _ = org["lead"]
    tenant_id = org["tenant_id"]
    seed = _seed(tenant_id, complaints=3, problem="BATTERY")
    first = _manual(lead, {**seed, "complaint_ids": seed["complaint_ids"][:1]}, title="Battery drains early")
    second = _manual(lead, {**seed, "complaint_ids": seed["complaint_ids"][1:2]}, title="Battery drains overnight")
    third = _manual(lead, {**seed, "complaint_ids": seed["complaint_ids"][2:]}, title="Battery empty after use")

    no_canonical = _post(lead, second, "disposition", {"disposition": "DUPLICATE", "reason": REASON})
    assert no_canonical.status_code == 422 and _code(no_canonical) == "CANONICAL_REQUIRED"
    itself = _post(
        lead, second, "disposition", {"disposition": "DUPLICATE", "reason": REASON, "canonical_signal_id": second["id"]}
    )
    assert itself.status_code == 422 and _code(itself) == "CANONICAL_INVALID"
    duplicate = _post(
        lead, second, "disposition", {"disposition": "DUPLICATE", "reason": REASON, "canonical_signal_id": first["id"]}
    )
    assert duplicate.status_code == 200, duplicate.text
    assert duplicate.json()["status"] == "DUPLICATE"
    assert duplicate.json()["canonical"] == {"id": first["id"], "business_id": first["business_id"]}
    chained = _post(
        lead, third, "disposition", {"disposition": "DUPLICATE", "reason": REASON, "canonical_signal_id": second["id"]}
    )
    assert chained.status_code == 422 and _code(chained) == "CANONICAL_INVALID"

    into_itself = _post(lead, first, "merge", {"source_signal_ids": [first["id"]], "reason": REASON})
    assert into_itself.status_code == 422
    not_open = _post(lead, first, "merge", {"source_signal_ids": [second["id"]], "reason": REASON})
    assert not_open.status_code == 409 and _code(not_open) == "SIGNAL_STATE_CONFLICT"
    unknown = _post(lead, first, "merge", {"source_signal_ids": [str(uuid.uuid4())], "reason": REASON})
    assert unknown.status_code == 404 and _code(unknown) == "SIGNAL_NOT_FOUND"
    elsewhere = _manual(lead, _seed(tenant_id, complaints=1, problem="BATTERY"), title="Battery on another pump")
    mismatch = _post(lead, first, "merge", {"source_signal_ids": [elsewhere["id"]], "reason": REASON})
    assert mismatch.status_code == 422 and _code(mismatch) == "PRODUCT_MISMATCH"

    merged = _post(lead, first, "merge", {"source_signal_ids": [third["id"]], "reason": REASON})
    assert merged.status_code == 200, merged.text
    body = merged.json()
    assert body["complaint_count"] == 2
    assert {item["id"]: item["added_how"] for item in body["complaints"]} == {
        seed["complaint_ids"][0]: "MANUAL",
        seed["complaint_ids"][2]: "MERGE",
    }
    assert {(item["business_id"], item["status"]) for item in body["merged_from"]} == {
        (second["business_id"], "DUPLICATE"),
        (third["business_id"], "MERGED"),
    }
    assert [event["event_type"] for event in body["events"]][-1] == "MERGED_FROM"
    source = lead.get(f"/api/v1/triage/signals/{third['id']}").json()
    assert source["status"] == "MERGED" and source["canonical"]["business_id"] == first["business_id"]
    assert source["events"][-1]["event_type"] == "MERGED_INTO" and source["complaint_count"] == 1  # nothing deleted
    assert _tasks(tenant_id, third["id"])[0].status == "SUPERSEDED"
    assert "DUPLICATE_LINKED" in [event["event_type"] for event in body["events"]]


def test_complaints_are_added_from_the_same_product_only(org):
    lead, _ = org["lead"]
    seed = _seed(org["tenant_id"], complaints=1, problem="SENSOR")
    other = _seed(org["tenant_id"], complaints=1, problem="SENSOR")
    signal = _manual(lead, seed, title="Sensor drift reports")
    foreign = _post(lead, signal, "complaints", {"complaint_ids": other["complaint_ids"], "reason": REASON})
    assert foreign.status_code == 422 and _code(foreign) == "COMPLAINT_NOT_FOR_PRODUCT"
    extra = _add_complaint(org["tenant_id"], seed, "SENSOR", death=True)
    added = _post(lead, signal, "complaints", {"complaint_ids": [extra], "reason": REASON})
    assert added.status_code == 200, added.text
    body = added.json()
    assert body["complaint_count"] == 2 and body["serious_harm"] and body["suggested_priority"] == "CRITICAL"
    assert body["events"][-1]["event_type"] == "COMPLAINTS_ADDED"
    again = _post(lead, signal, "complaints", {"complaint_ids": [extra], "reason": REASON})
    assert again.status_code == 422 and _code(again) == "NOTHING_TO_ADD"


# ------------------------------------------------------------------------------------------------ cases from signals


def _needs_case(org, problem: str) -> tuple[dict, dict]:
    lead, _ = org["lead"]
    seed = _seed(org["tenant_id"], complaints=2, problem=problem)
    signal = _manual(lead, seed, title=f"{problem.title()} complaints rising")
    early = _post(org["investigator"][0], signal, "create-investigation", {"investigation_question": "Why rising?"})
    assert early.status_code == 409 and _code(early) == "SIGNAL_STATE_CONFLICT"
    marked = _post(lead, signal, "disposition", {"disposition": "INVESTIGATION_REQUIRED", "reason": REASON})
    assert marked.status_code == 200, marked.text
    return signal, seed


def test_a_case_is_opened_from_a_signal_with_its_task_and_links(org):
    tenant_id = org["tenant_id"]
    investigator, _ = org["investigator"]
    colleague, colleague_id = org["colleague"]
    _, viewer_id = org["viewer"]
    signal, seed = _needs_case(org, "PRESSURE")
    also = _manual(org["lead"][0], {**seed, "complaint_ids": []}, title="Pressure readings drift")
    ineligible = _post(
        investigator,
        signal,
        "create-investigation",
        {"investigation_question": "Why do pressure alarms rise?", "assignee_user_id": viewer_id},
    )
    assert ineligible.status_code == 422 and _code(ineligible) == "ASSIGNEE_NOT_ELIGIBLE"
    opened = _post(
        investigator,
        signal,
        "create-investigation",
        {
            "investigation_question": "Why do pressure alarms rise?",
            "assignee_user_id": colleague_id,
            "also_signal_ids": [also["id"]],
        },
    )
    assert opened.status_code == 201, opened.text
    body = opened.json()
    case = body["investigation"]
    assert case["business_id"].startswith("INV") and case["complaints_linked"] == 2
    assert case["owner"]["id"] == colleague_id and case["owner"]["name"]
    assert body["signal"]["status"] == "INVESTIGATION_OPEN"
    assert body["signal"]["investigations"] == [
        {"id": case["id"], "business_id": case["business_id"], "status": "open"}
    ]
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        linked = {
            str(row[0])
            for row in db.query(InvestigationSignal.signal_id).filter(
                InvestigationSignal.investigation_id == uuid.UUID(case["id"])
            )
        }
        owner = db.query(Investigation.owner_ref).filter(Investigation.id == uuid.UUID(case["id"])).scalar()
        username = db.query(AuthUser.username).filter(AuthUser.id == uuid.UUID(colleague_id)).scalar()
    assert linked == {signal["id"], also["id"]} and owner == username
    assert _signal(tenant_id, also["id"]).status == "INVESTIGATION_OPEN"
    (task,) = _tasks(tenant_id, case["id"], "INVESTIGATION")
    assert task.status == "ASSIGNED" and str(task.assigned_user_id) == colleague_id
    assert colleague.get(f"/api/v1/tasks/{task.id}").status_code == 200
    events = investigator.get(f"/api/v1/triage/signals/{signal['id']}").json()["events"]
    assert events[-1]["event_type"] == "INVESTIGATION_CREATED" and events[-1]["actor_role"] == "INVESTIGATOR"

    # A second case from the same signal goes to the investigators' queue.
    second = _post(investigator, signal, "create-investigation", {"investigation_question": "Is Rev B affected too?"})
    assert second.status_code == 201, second.text
    assert len(second.json()["signal"]["investigations"]) == 2
    (queued,) = _tasks(tenant_id, second.json()["investigation"]["id"], "INVESTIGATION")
    assert queued.status == "NEW" and queued.assigned_user_id is None and queued.assigned_role == "INVESTIGATOR"
    # A signal a case was opened for cannot be merged away.
    refused = _post(
        org["lead"][0],
        _manual(org["lead"][0], {**seed, "complaint_ids": []}),
        "merge",
        {
            "source_signal_ids": [signal["id"]],
            "reason": REASON,
        },
    )
    assert refused.status_code == 409 and _code(refused) == "SIGNAL_HAS_INVESTIGATION"


def test_signals_follow_their_case_decision_and_closure(org):
    from backend.app.signals.hooks import on_case_decision_signed

    tenant_id = org["tenant_id"]
    lead, _ = org["lead"]
    signal, _ = _needs_case(org, "TUBING")
    opened = _post(lead, signal, "create-investigation", {"investigation_question": "Why does tubing kink?"})
    assert opened.status_code == 201, opened.text
    case_id = opened.json()["investigation"]["id"]
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        decision = Decision(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            investigation_id=uuid.UUID(case_id),
            decision_identifier=f"SIG-DEC-{uuid.uuid4().hex[:8]}",
            decision_type="INVESTIGATION_REVIEW",
            disposition="APPROVED",
            rationale="Signals lifecycle test",
            decision_status="APPROVED",
            authorized_by_ref="someone-else",
            updated_at=now,
            decision_timestamp=now,
            created_at=now,
        )
        db.add(decision)
        db.commit()
        on_case_decision_signed(db, decision, actor_user_id=org["lead"][1], actor_role="APPROVER")
    assert _signal(tenant_id, signal["id"]).status == "DECISION_RECORDED"

    path = f"/api/v1/investigations/{case_id}"
    assert lead.patch(path, json={"reason": REASON, "status": "closed"}).status_code == 200
    assert _signal(tenant_id, signal["id"]).status == "CLOSED"
    assert lead.patch(path, json={"reason": REASON, "status": "open"}).status_code == 200
    assert _signal(tenant_id, signal["id"]).status == "INVESTIGATION_OPEN"
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        history = [
            row[0]
            for row in db.query(SignalEvent.event_type)
            .filter(SignalEvent.signal_id == uuid.UUID(signal["id"]))
            .order_by(SignalEvent.created_at)
        ]
    assert history[-3:] == ["DECISION_RECORDED", "CLOSED", "REOPENED"]


def test_a_signal_with_another_open_case_stays_open_when_one_closes(org):
    tenant_id = org["tenant_id"]
    lead, _ = org["lead"]
    signal, _ = _needs_case(org, "VALVE")
    first = _post(lead, signal, "create-investigation", {"investigation_question": "Why do valves stick?"}).json()
    _post(lead, signal, "create-investigation", {"investigation_question": "Is the supplier lot involved?"})
    closed = lead.patch(
        f"/api/v1/investigations/{first['investigation']['id']}", json={"reason": REASON, "status": "closed"}
    )
    assert closed.status_code == 200
    assert _signal(tenant_id, signal["id"]).status == "INVESTIGATION_OPEN"


# --------------------------------------------------------------------------------------------------- detection


def _run(client) -> dict:
    response = client.post("/api/v1/triage/rules/run")
    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body) >= {"created", "updated", "monitor_reopened"}
    return body


def _product_signals(client, product_id) -> list[dict]:
    response = client.get("/api/v1/triage/signals", params={"product_id": product_id, "page_size": 200})
    assert response.status_code == 200, response.text
    return response.json()["items"]


def test_detection_raises_once_adds_later_complaints_and_reopens_monitoring(org):
    tenant_id = org["tenant_id"]
    lead, _ = org["lead"]
    seed = _seed(tenant_id, complaints=3, problem="AIR IN LINE", severity="major")
    below = _seed(tenant_id, complaints=2, problem="AIR IN LINE")
    old = _seed(tenant_id, complaints=3, problem="AIR IN LINE", days_ago=90)  # outside the 30-day window

    first = _run(lead)
    (signal,) = _product_signals(lead, seed["product_id"])
    assert signal["business_id"] in first["created"]
    assert signal["origin"] == "THRESHOLD_RULE" and signal["rule_code"] == "COMPLAINT_THRESHOLD"
    assert signal["complaint_count"] == 3 and signal["problem_key"] == "AIR IN LINE"
    assert signal["suggested_priority"] == "HIGH" and signal["highest_severity"] == "MAJOR"
    assert signal["title"].startswith("3 complaints: air in line on Signal Pump ") and signal["title"].endswith(
        "Rev C in 30 days"
    )
    detail = lead.get(f"/api/v1/triage/signals/{signal['id']}").json()
    assert detail["rule"]["parameters"] == {"min_complaints": 3, "window_days": 30}
    assert {item["added_how"] for item in detail["complaints"]} == {"RULE"}
    (task,) = _tasks(tenant_id, signal["id"])
    assert task.status == "NEW" and task.priority == "HIGH" and task.due_at is not None
    assert _product_signals(lead, below["product_id"]) == [] and _product_signals(lead, old["product_id"]) == []

    second = _run(lead)  # idempotent
    assert signal["business_id"] not in second["created"] + second["updated"] + second["monitor_reopened"]
    assert len(_product_signals(lead, seed["product_id"])) == 1

    _add_complaint(tenant_id, seed, "air in line")
    third = _run(lead)
    assert signal["business_id"] in third["updated"]
    assert _signal(tenant_id, signal["id"]).complaint_count == 4

    review = (datetime.now(timezone.utc).date() + timedelta(days=30)).isoformat()
    monitored = _post(
        lead,
        signal,
        "disposition",
        {"disposition": "MONITOR", "reason": REASON, "monitor_review_date": review, "monitor_trigger": "Any new case"},
    )
    assert monitored.status_code == 200, monitored.text
    _add_complaint(tenant_id, seed, "AIR IN LINE")
    fourth = _run(lead)
    assert signal["business_id"] in fourth["monitor_reopened"]
    reopened = _signal(tenant_id, signal["id"])
    assert reopened.status == "TRIAGE" and reopened.complaint_count == 5
    tasks = _tasks(tenant_id, signal["id"])
    assert [task.status for task in tasks] == ["COMPLETED", "NEW"]
    events = lead.get(f"/api/v1/triage/signals/{signal['id']}").json()["events"]
    assert "MONITOR_TRIGGERED" in [event["event_type"] for event in events]


def test_a_monitored_signal_comes_back_when_its_review_date_arrives(org):
    tenant_id = org["tenant_id"]
    lead, _ = org["lead"]
    signal = _manual(lead, _seed(tenant_id, complaints=1, problem="CASING"), title="Casing cracks reported")
    review = (datetime.now(timezone.utc).date() + timedelta(days=7)).isoformat()
    assert (
        _post(
            lead,
            signal,
            "disposition",
            {"disposition": "MONITOR", "reason": REASON, "monitor_review_date": review, "monitor_trigger": "Two more"},
        ).status_code
        == 200
    )
    due = lead.get("/api/v1/triage/signals", params={"review_due": "true", "page_size": 200}).json()
    assert signal["id"] not in [item["id"] for item in due["items"]]
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        db.query(Signal).filter(Signal.id == uuid.UUID(signal["id"])).update(
            {Signal.monitor_review_date: datetime.now(timezone.utc).date()}, synchronize_session=False
        )
        db.commit()
    due = lead.get("/api/v1/triage/signals", params={"review_due": "true", "page_size": 200}).json()
    assert signal["id"] in [item["id"] for item in due["items"]] and due["total"] == len(due["items"])
    assert lead.get("/api/v1/triage/summary").json()["counts"]["monitor_review_due"] >= 1
    assert signal["business_id"] in _run(lead)["monitor_reopened"]
    assert _signal(tenant_id, signal["id"]).status == "TRIAGE"
    assert [task.status for task in _tasks(tenant_id, signal["id"])] == ["COMPLETED", "NEW"]


def test_the_detection_dry_run_writes_nothing(org):
    from backend.app.signals.detection import detect

    tenant_id = org["tenant_id"]
    seed = _seed(tenant_id, complaints=3, problem="DRY RUN")
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        planned = detect(db, tenant_id, apply=False)
        db.rollback()
        assert any("dry run" in title for title in planned["created"]) and planned["applied"] is False
        assert db.query(Signal).filter(Signal.product_id == uuid.UUID(seed["product_id"])).count() == 0


def test_rule_settings_are_versioned_and_audited(org):
    lead, _ = org["lead"]
    viewer, _ = org["viewer"]
    (rule,) = lead.get("/api/v1/triage/rules").json()
    assert rule["rule_code"] == "COMPLAINT_THRESHOLD" and rule["label"] and rule["description"]
    assert rule["defaults"] == {"min_complaints": 3, "window_days": 30}
    path = "/api/v1/triage/rules/COMPLAINT_THRESHOLD"
    settings = {"enabled": True, "min_complaints": 3, "window_days": 45, "reason": "Longer window for rare events"}
    refused = viewer.put(path, json=settings)
    assert refused.status_code == 403 and _code(refused) == "PERMISSION_DENIED"
    assert lead.put(path, json={**settings, "min_complaints": 1}).status_code == 422
    assert lead.put("/api/v1/triage/rules/OTHER_RULE", json=settings).status_code == 404
    updated = lead.put(path, json=settings)
    assert updated.status_code == 200, updated.text
    body = updated.json()
    assert body["window_days"] == 45 and body["version"] == rule["version"] + 1
    assert body["updated_by_name"] and body["updated_at"]
    same = lead.put(path, json=settings)
    assert same.status_code == 422 and _code(same) == "NOTHING_TO_CHANGE"
    restored = lead.put(path, json={**settings, "window_days": 30, "reason": "Back to the standard window"})
    assert restored.status_code == 200 and restored.json()["version"] == rule["version"] + 2
    _run(lead)
    assert lead.get("/api/v1/triage/rules").json()[0]["last_run_at"]
    with SessionLocal() as db:
        bind_tenant(db, org["tenant_id"])
        actions = [
            row[0]
            for row in db.query(AuditEvent.action).filter(
                AuditEvent.tenant_id == org["tenant_id"],
                AuditEvent.action.in_(["SIGNAL_RULE_UPDATED", "SIGNAL_RULE_RUN"]),
            )
        ]
    assert actions.count("SIGNAL_RULE_UPDATED") == 2 and "SIGNAL_RULE_RUN" in actions


# ------------------------------------------------------------------------------------------- list, isolation


def test_list_filters_sorting_paging_and_summary(org):
    lead, lead_id = org["lead"]
    tenant_id = org["tenant_id"]
    seed = _seed(tenant_id, complaints=1, problem="FILTER")
    low = _manual(lead, seed, title="Filter clogging reports")
    high = _manual(
        lead, {**seed, "complaint_ids": []}, title="Filter housing cracks", priority="HIGH", reason="Housing can leak"
    )
    _post(lead, high, "start")
    listing = lead.get(
        "/api/v1/triage/signals",
        params={"status": "NEW,TRIAGE", "priority": "HIGH,CRITICAL", "product_id": seed["product_id"]},
    ).json()
    assert [item["id"] for item in listing["items"]] == [high["id"]] and listing["total"] == 1
    assert listing["page"] == 1 and listing["page_size"] == 50
    assert set(listing["counts_by_status"]) >= {"NEW", "TRIAGE", "MONITOR"}
    # Counted over the other filters (here HIGH or CRITICAL on this product): one in triage, none new.
    assert listing["counts_by_status"]["TRIAGE"] == 1 and listing["counts_by_status"]["NEW"] == 0
    mine = lead.get("/api/v1/triage/signals", params={"owner": "me", "product_id": seed["product_id"]}).json()
    assert [item["id"] for item in mine["items"]] == [high["id"]] and mine["items"][0]["owner"]["id"] == lead_id
    unowned = lead.get("/api/v1/triage/signals", params={"owner": "unassigned", "product_id": seed["product_id"]})
    assert [item["id"] for item in unowned.json()["items"]] == [low["id"]]
    found = lead.get("/api/v1/triage/signals", params={"q": high["business_id"]}).json()
    assert [item["id"] for item in found["items"]] == [high["id"]]
    ordered = lead.get("/api/v1/triage/signals", params={"product_id": seed["product_id"]}).json()["items"]
    assert [item["id"] for item in ordered] == [high["id"], low["id"]]  # highest priority first
    by_age = lead.get("/api/v1/triage/signals", params={"product_id": seed["product_id"], "sort": "-created_at"})
    assert [item["id"] for item in by_age.json()["items"]] == [low["id"], high["id"]]
    open_ones = lead.get("/api/v1/triage/signals", params={"status": "OPEN", "product_id": seed["product_id"]})
    assert open_ones.json()["total"] == 2

    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        db.query(Signal).filter(Signal.id == uuid.UUID(low["id"])).update(
            {Signal.due_at: datetime.now(timezone.utc) - timedelta(days=1)}, synchronize_session=False
        )
        db.commit()
    overdue = lead.get("/api/v1/triage/signals", params={"overdue": "true", "product_id": seed["product_id"]}).json()
    assert [item["id"] for item in overdue["items"]] == [low["id"]] and overdue["items"][0]["overdue"]
    assert overdue["total"] == 1

    for bad in ({"status": "NEW,LOST"}, {"priority": "URGENT"}, {"origin": "EMAIL"}, {"page_size": 201}, {"sort": "x"}):
        response = lead.get("/api/v1/triage/signals", params=bad)
        assert response.status_code == 422, bad
    assert _code(lead.get("/api/v1/triage/signals", params={"status": "LOST"})) == "UNKNOWN_STATUS"

    summary = lead.get("/api/v1/triage/summary").json()
    assert set(summary["counts"]) == {
        "new",
        "triage",
        "escalated",
        "investigation_required",
        "monitor",
        "monitor_review_due",
        "unowned",
        "overdue",
    }
    assert set(summary["by_priority"]) == {"LOW", "MEDIUM", "HIGH", "CRITICAL"}
    assert summary["counts"]["overdue"] >= 1 and summary["counts"]["new"] >= 1 and summary["by_priority"]["HIGH"] >= 1


def test_other_organizations_signals_are_not_found(org):
    lead, _ = org["lead"]
    signal = _manual(lead, _seed(org["tenant_id"], complaints=1, problem="ISOLATION"), title="Isolation check")
    outsider, _ = role_client("LEADER")  # the golden organization, with every permission
    for response in (
        outsider.get(f"/api/v1/triage/signals/{signal['id']}"),
        _post(outsider, signal, "start"),
        _post(outsider, signal, "priority", {"priority": "HIGH", "reason": REASON}),
        _post(outsider, signal, "disposition", {"disposition": "NO_ACTION", "reason": REASON}),
        _post(outsider, signal, "complaints", {"complaint_ids": [str(uuid.uuid4())], "reason": REASON}),
        _post(outsider, signal, "create-investigation", {"investigation_question": "Not my organization?"}),
        lead.get(f"/api/v1/triage/signals/{uuid.uuid4()}"),
    ):
        assert response.status_code == 404 and _code(response) == "SIGNAL_NOT_FOUND", response.text
    merged = _post(lead, signal, "merge", {"source_signal_ids": [str(uuid.uuid4())], "reason": REASON})
    assert merged.status_code == 404 and _code(merged) == "SIGNAL_NOT_FOUND"
    listed = outsider.get("/api/v1/triage/signals", params={"q": signal["business_id"], "page_size": 200}).json()
    assert signal["id"] not in [item["id"] for item in listed["items"]]
    assert _signal(org["tenant_id"], signal["id"]).status == "NEW"
    with SessionLocal() as db:
        bind_tenant(db, org["tenant_id"])
        assert db.query(SignalComplaint).filter(SignalComplaint.signal_id == uuid.UUID(signal["id"])).count() == 1


def test_a_rule_title_from_before_grouped_counts_reads_grouped_everywhere_and_stays_stored(org):
    # Rule signals raised before 0.10.44 stored "2290 complaints: ..."; the API shows "2,290 complaints: ..." in the
    # inbox, the signal, its triage task and Readiness, without rewriting the stored title (no migration). A title a
    # person wrote is never touched, even one that looks like a rule's.
    from backend.app.readiness_home import service as readiness
    from backend.app.signals import service as signal_service

    lead, lead_id = org["lead"]
    tenant_id = org["tenant_id"]
    seed = _seed(tenant_id, complaints=2, problem="GROUPING")
    old_title = "2290 complaints: unspecified problem on Grouping Pump Rev C in 30 days"
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        rule = signal_service.create_signal(
            db,
            tenant_id,
            title=old_title,
            origin="THRESHOLD_RULE",
            product_id=seed["product_id"],
            product_version_id=seed["version_id"],
            complaint_ids=[uuid.UUID(item) for item in seed["complaint_ids"]],
            actor_ref=None,
        )
        rule.due_at = datetime.now(timezone.utc) - timedelta(days=1)
        db.commit()
        rule_id, rule_number = str(rule.id), rule.business_id
    person = _manual(lead, {**seed, "complaint_ids": []}, title="2290 complaints: our own wording kept as written")
    grouped = "2,290 complaints: unspecified problem on Grouping Pump Rev C in 30 days"

    listing = lead.get("/api/v1/triage/signals", params={"product_id": seed["product_id"]}).json()["items"]
    titles = {item["id"]: item["title"] for item in listing}
    assert titles == {rule_id: grouped, person["id"]: "2290 complaints: our own wording kept as written"}
    assert lead.get(f"/api/v1/triage/signals/{rule_id}").json()["title"] == grouped
    found = lead.get("/api/v1/triage/signals", params={"q": "2,290 complaints: unspecified"}).json()["items"]
    assert [item["id"] for item in found] == [rule_id]

    queue = lead.get("/api/v1/tasks", params={"view": "queue", "page_size": 200, "q": rule_number}).json()["items"]
    assert [item["title"] for item in queue] == [f"Triage {rule_number}: {grouped}"]
    mine = lead.get("/api/v1/tasks", params={"view": "queue", "page_size": 200, "q": person["business_id"]}).json()
    assert [item["title"] for item in mine["items"]] == [
        f"Triage {person['business_id']}: 2290 complaints: our own wording kept as written"
    ]

    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        overdue = readiness.triage_overdue(db, tenant_id, datetime.now(timezone.utc).date())
        assert {"id": rule_id, "ref": rule_number, "label": grouped} in overdue["items"]
        assert db.query(Signal.title).filter(Signal.id == uuid.UUID(rule_id)).scalar() == old_title  # as stored
        task_title = db.query(WorkflowTask.title).filter(WorkflowTask.source_entity_id == uuid.UUID(rule_id)).scalar()
        assert task_title == f"Triage {rule_number}: {old_title}"
