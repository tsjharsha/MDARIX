"""What follows a signed decision, end to end: follow-ups started, completed and cancelled with their tasks (both ways:
completing the task in My Work completes the follow-up), a CAPA opened from a follow-up, late evidence (linked,
reviewed, accepted from a request, or caught by the hourly sweep) asking for exactly one impact assessment, NO_IMPACT
versus MATERIAL_IMPACT (the case reopened, the signed decision never changed), the impact task refusing completion
in My Work, the closure check and closing a case in the Decision Brief flow, cases outside that flow closing as
before, permissions and other organizations.

Signed brief decisions and their follow-ups are written directly (as the signing step stores them), so these tests do
not depend on the signing screens. Everything runs in fresh organizations of their own (on the shared plane),
deleted at the end.
"""

from __future__ import annotations

import secrets
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from auth.durable import persist_session
from auth.service import _hash
from backend.app.case_workflow import states
from backend.app.db.models.decision_outcomes import DecisionFollowUp, ImpactAssessment
from backend.app.db.models.foundation import (
    AuditEvent,
    AuthUser,
    Capa,
    Decision,
    Evidence,
    Investigation,
    Product,
    TenantMembership,
)
from backend.app.db.models.reviews import CaseReview, DecisionBriefVersion
from backend.app.db.models.stage3 import SupplierEvidenceRequest
from backend.app.db.models.workflow import OPEN_TASK_STATUSES, WorkflowTask
from backend.app.db.session import SessionLocal
from backend.app.db.tenant_scope import bind_tenant
from backend.app.decision_followups import impact, rules
from backend.app.main import app
from backend.app.workflow import tasks as task_service

PASSWORD = "Follow ups 2026!"
QUESTION = "Why do occlusion alarms rise after release B?"
REASON = "The CAPA is tracked in the quality system"
NOTE = "Supplier changed the sensor batch; verified on 20 pumps"
RATIONALE = "The late service report repeats the known sensor drift"


def _organization(prefix: str):
    from backend.app.customer_lifecycle import build_customer_tenant

    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        customer, tenant = build_customer_tenant(
            db=db, tenant_key=f"{prefix}_{uuid.uuid4().hex[:8].upper()}", name="Follow-ups", status="ACTIVE", now=now
        )
        db.add(customer)
        db.add(tenant)
        db.commit()  # registers the organization on the shared plane (migration md20)
        return tenant.id


def _purge(tenant_id) -> None:
    from backend.app.trial.retention import purge_trial

    with SessionLocal() as db:
        purge_trial(db, tenant_id, "test:decision-followups-cleanup")


def _client(tenant_id, role: str, name: str) -> tuple[TestClient, str]:
    with SessionLocal() as db:
        now = datetime.now(timezone.utc)
        user = AuthUser(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            username=f"followups-{role.lower()}-{uuid.uuid4().hex[:8]}@example.invalid",
            display_name=f"{name} Followups",
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
    now = datetime.now(timezone.utc)
    tag = uuid.uuid4().hex[:8].upper()
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        product = Product(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            product_identifier=f"FU-P-{tag}",
            name=f"Follow-up Pump {tag}",
            created_at=now,
            updated_at=now,
        )
        db.add(product)
        db.commit()
        return {"product_id": str(product.id)}


def _open(client, seed: dict) -> dict:
    made = client.post(
        "/api/v1/investigations",
        json={"product_id": seed["product_id"], "investigation_question": QUESTION, "assign_to_me": True},
    )
    assert made.status_code == 201, made.text
    return made.json()


def _brief(db, tenant_id, case) -> uuid.UUID:
    count = (
        db.query(DecisionBriefVersion)
        .filter(DecisionBriefVersion.tenant_id == tenant_id, DecisionBriefVersion.investigation_id == case.id)
        .count()
    )
    now = datetime.now(timezone.utc)
    version = DecisionBriefVersion(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        investigation_id=case.id,
        version=count + 1,
        status="APPROVED_FOR_DECISION",
        title=f"Decision brief {case.business_id}",
        created_by="test",
        created_at=now,
        updated_at=now,
    )
    db.add(version)
    db.flush()
    return version.id


def _brief_only(tenant_id, case_id: str) -> None:
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        case = db.query(Investigation).filter(Investigation.id == uuid.UUID(case_id)).one()
        _brief(db, tenant_id, case)
        db.commit()


def _decide(
    tenant_id,
    case_id: str,
    *,
    outcome: str = "ACCEPT_CONCLUSION",
    follow_ups=(),
    state: str = "DECIDED",
    decided_at: datetime | None = None,
) -> dict:
    """A signed brief decision on the case as the signing step stores it: the brief version, the decision (kind
    BRIEF, SIGNED), each chosen follow-up with its FOLLOW_UP task (``skip_row`` leaves a chosen follow-up without its
    record), and the case moved to ``state``."""
    now = datetime.now(timezone.utc)
    decided = decided_at or now - timedelta(hours=1)
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        case = db.query(Investigation).filter(Investigation.id == uuid.UUID(case_id)).one()
        brief_id = _brief(db, tenant_id, case)
        decision = Decision(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            investigation_id=case.id,
            decision_identifier=f"FU-D-{uuid.uuid4().hex[:10]}",
            decision_type="CASE_DECISION",
            disposition=outcome,
            rationale="The sensor drift explains the alarms",
            decision_status="SIGNED",
            authorized_by_ref="approver@example.invalid",
            updated_at=decided,
            decision_timestamp=decided,
            created_at=decided,
            decision_kind="BRIEF",
            brief_version_id=brief_id,
            outcome=outcome,
            follow_up_actions=[
                {"action_type": item["action_type"], "title": item.get("title") or item["action_type"]}
                for item in follow_ups
            ],
            decided_at=decided,
        )
        db.add(decision)
        db.flush()
        ids, task_ids = [], []
        for item in follow_ups:
            if item.get("skip_row"):
                continue
            row = DecisionFollowUp(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                decision_id=decision.id,
                investigation_id=case.id,
                action_type=item["action_type"],
                title=item.get("title") or f"{item['action_type']} for {case.business_id}",
                assignee_user_id=uuid.UUID(item["assignee"]) if item.get("assignee") else None,
                assigned_role=item.get("role"),
                due_at=item.get("due_at"),
                status="OPEN",
                created_by="test",
                created_at=now,
                updated_at=now,
            )
            db.add(row)
            db.flush()
            task = task_service.create_task(
                db,
                tenant_id,
                task_type="FOLLOW_UP",
                title=row.title,
                source_type="DecisionFollowUp",
                source_id=row.id,
                investigation_id=case.id,
                assigned_user_id=row.assignee_user_id,
                assigned_role=row.assigned_role,
                due_at=row.due_at,
                created_by="test",
                details={"follow_up_id": str(row.id), "action_type": row.action_type, "decision_id": str(decision.id)},
            )
            row.task_id = task.id
            ids.append(str(row.id))
            task_ids.append(str(task.id))
        states.set_state(case, state, now)
        db.commit()
        return {
            "decision_id": str(decision.id),
            "decision_business_id": decision.business_id,
            "follow_ups": ids,
            "tasks": task_ids,
        }


def _evidence(tenant_id, *, case_id: str | None = None, ingested_at: datetime | None = None) -> str:
    now = datetime.now(timezone.utc)
    received = ingested_at or now
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        row = Evidence(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            evidence_identifier=f"FU-E-{uuid.uuid4().hex[:10].upper()}",
            investigation_id=uuid.UUID(case_id) if case_id else None,
            evidence_type="SERVICE_REPORT",
            title="Late service report",
            source_system="test",
            ingestion_timestamp=received,
            recorded_timestamp=received,
            created_at=received,
            updated_at=received,
        )
        db.add(row)
        db.commit()
        return str(row.id)


def _request_row(tenant_id, case_id: str, *, requester: str, status: str, priority: str, recipient=None) -> str:
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        row = SupplierEvidenceRequest(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            investigation_id=uuid.UUID(case_id),
            requested_by=requester,
            title="Batch record for lot KS-5521",
            requested_items={"items": ["Batch record"], "rationale": "Needed to check the sensor batch"},
            status=status,
            request_kind="INTERNAL",
            recipient_user_id=uuid.UUID(recipient) if recipient else None,
            # A request always names who is asked: the person, or else the investigators' queue.
            recipient_role=None if recipient else "INVESTIGATOR",
            priority=priority,
            responded_at=now if status == "RECEIVED" else None,
            response_note="Batch record attached; cycle 121 C for 30 min" if status == "RECEIVED" else None,
            created_at=now,
            updated_at=now,
        )
        db.add(row)
        db.commit()
        return str(row.id)


def _review_row(tenant_id, case_id: str, *, requester: str, status: str = "REQUESTED") -> str:
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        row = CaseReview(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            investigation_id=uuid.UUID(case_id),
            review_type="RISK",
            status=status,
            requested_by=requester,
        )
        db.add(row)
        db.commit()
        return str(row.id)


def _update(tenant_id, model, row_id: str, **values) -> None:
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        db.query(model).filter(model.id == uuid.UUID(str(row_id))).update(values)
        db.commit()


def _get(tenant_id, model, row_id):
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        row = db.query(model).filter(model.id == uuid.UUID(str(row_id))).one()
        db.expunge(row)
        return row


def _assessments(tenant_id, case_id: str) -> list[ImpactAssessment]:
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        rows = (
            db.query(ImpactAssessment)
            .filter(ImpactAssessment.investigation_id == uuid.UUID(case_id))
            .order_by(ImpactAssessment.created_at)
            .all()
        )
        for row in rows:
            db.expunge(row)
        return rows


def _audits(tenant_id, entity_id, action: str) -> list[AuditEvent]:
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        rows = (
            db.query(AuditEvent)
            .filter(AuditEvent.entity_id == uuid.UUID(str(entity_id)), AuditEvent.action == action)
            .order_by(AuditEvent.created_at)
            .all()
        )
        for row in rows:
            db.expunge(row)
        return rows


def _code(response) -> str | None:
    detail = response.json().get("detail")
    return detail.get("code") if isinstance(detail, dict) else None


def _criteria(body: dict) -> dict[str, str]:
    return {item["key"]: item["result"] for item in body["criteria"]}


def _link(client, case_id: str, evidence_ids: list[str]):
    return client.post(
        f"/api/v1/investigations/{case_id}/evidence-links",
        json={"evidence_ids": evidence_ids, "reason": "Service report received after the decision"},
    )


def _sweep(tenant_id) -> int:
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        made = impact.sweep_tenant(db, db, tenant_id)
        db.commit()
        return made


@pytest.fixture(scope="module")
def org():
    """A fresh organization with an investigator (the case owner), a colleague investigator, a quality reviewer
    (assigns work), a regulatory reviewer and a viewer; and another organization with a decided case, a follow-up and
    an impact assessment of its own."""
    tenant_id = _organization("FOLLOWUPS")
    other_id = _organization("FOLLOWUPS_OTHER")
    try:
        people = {
            name: _client(tenant_id, role, name.title())
            for name, role in (
                ("investigator", "INVESTIGATOR"),
                ("colleague", "INVESTIGATOR"),
                ("quality", "REVIEWER"),
                ("regulatory", "REGULATORY_REVIEWER"),
                ("viewer", "VIEWER"),
            )
        }
        seed = _seed(tenant_id)
        other_client, other_user = _client(other_id, "INVESTIGATOR", "Other")
        other_case = _open(other_client, _seed(other_id))
        other_made = _decide(
            other_id, other_case["id"], follow_ups=[{"action_type": "CAPA_REQUIRED", "assignee": other_user}]
        )
        linked = _link(other_client, other_case["id"], [_evidence(other_id)])
        assert linked.status_code == 200, linked.text
        (other_assessment,) = _assessments(other_id, other_case["id"])
        yield {
            "tenant_id": tenant_id,
            "seed": seed,
            "other": {
                "case_id": other_case["id"],
                "follow_up_id": other_made["follow_ups"][0],
                "assessment_id": str(other_assessment.id),
            },
            **people,
        }
    finally:
        _purge(tenant_id)
        _purge(other_id)


# ---------------------------------------------------------------------------------------------------- follow-ups


def test_starting_and_completing_a_follow_up_moves_its_task(org):
    tenant_id = org["tenant_id"]
    investigator, investigator_id = org["investigator"]
    colleague, colleague_id = org["colleague"]
    viewer, _ = org["viewer"]
    case = _open(investigator, org["seed"])
    made = _decide(
        tenant_id,
        case["id"],
        follow_ups=[
            {"action_type": "CAPA_REQUIRED", "assignee": investigator_id},
            {"action_type": "RISK_REASSESSMENT_REQUIRED", "role": "INVESTIGATOR"},
        ],
    )
    capa_id, risk_id = made["follow_ups"]
    capa_task, risk_task = made["tasks"]

    listed = viewer.get(f"/api/v1/investigations/{case['id']}/follow-ups")
    assert listed.status_code == 200, listed.text
    first, second = listed.json()["items"]
    assert first["id"] == capa_id and first["business_id"].startswith("FUP")
    assert first["action_type"] == "CAPA_REQUIRED" and first["action_label"] == "CAPA required"
    assert first["status"] == "OPEN" and first["status_label"] == "Open" and first["overdue"] is False
    assert first["assignee"] == {"id": investigator_id, "name": "Investigator Followups"}
    assert first["decision"] == {
        "id": made["decision_id"],
        "business_id": made["decision_business_id"],
        "outcome": "ACCEPT_CONCLUSION",
    }
    assert first["investigation"] == {"id": case["id"], "business_id": case["business_id"]}
    assert first["capa"] is None and first["completion_note"] is None and first["completed_at"] is None
    assert first["actions"] == {
        "can_start": False,
        "can_complete": False,
        "can_cancel": False,
        "can_create_capa": False,
        "can_set_qms_reference": False,
    }
    assert second["id"] == risk_id and second["assignee"] is None and second["assigned_role"] == "INVESTIGATOR"
    assert second["assigned_role_label"]

    not_theirs = colleague.post(f"/api/v1/follow-ups/{capa_id}/start")
    assert not_theirs.status_code == 403 and _code(not_theirs) == "FOLLOW_UP_NOT_YOURS"
    assert viewer.post(f"/api/v1/follow-ups/{risk_id}/start").status_code == 403

    started = investigator.post(f"/api/v1/follow-ups/{capa_id}/start")
    assert started.status_code == 200, started.text
    assert started.json()["status"] == "IN_PROGRESS"
    assert started.json()["actions"]["can_complete"] and not started.json()["actions"]["can_start"]
    assert _get(tenant_id, WorkflowTask, capa_task).status == "ACCEPTED"
    again = investigator.post(f"/api/v1/follow-ups/{capa_id}/start")
    assert again.status_code == 409 and _code(again) == "FOLLOW_UP_STATE_CONFLICT"

    assert investigator.post(f"/api/v1/follow-ups/{capa_id}/complete", json={"note": "done"}).status_code == 422
    done = investigator.post(f"/api/v1/follow-ups/{capa_id}/complete", json={"note": NOTE})
    assert done.status_code == 200, done.text
    body = done.json()
    assert body["status"] == "DONE" and body["completion_note"] == NOTE
    assert body["completed_by_name"] == "Investigator Followups" and body["completed_at"]
    task = _get(tenant_id, WorkflowTask, capa_task)
    assert task.status == "COMPLETED" and task.completion_outcome == "FOLLOW_UP_DONE"
    assert len(_audits(tenant_id, capa_id, "FOLLOW_UP_STARTED")) == 1
    (audit,) = _audits(tenant_id, capa_id, "FOLLOW_UP_COMPLETED")
    assert audit.reason == NOTE and audit.new_values == {"status": "DONE"}
    assert investigator.post(f"/api/v1/follow-ups/{capa_id}/complete", json={"note": NOTE}).status_code == 409

    mine = investigator.get("/api/v1/follow-ups", params={"box": "mine"}).json()["items"]
    assert {capa_id, risk_id} <= {item["id"] for item in mine}

    # A follow-up for a role: whoever holds the role starts it, it becomes theirs and so does its task.
    taken = colleague.post(f"/api/v1/follow-ups/{risk_id}/start")
    assert taken.status_code == 200, taken.text
    assert taken.json()["assignee"]["id"] == colleague_id and taken.json()["status"] == "IN_PROGRESS"
    task = _get(tenant_id, WorkflowTask, risk_task)
    assert task.status == "ACCEPTED" and str(task.assigned_user_id) == colleague_id
    colleague_mine = {
        item["id"] for item in colleague.get("/api/v1/follow-ups", params={"box": "mine"}).json()["items"]
    }
    assert risk_id in colleague_mine and capa_id not in colleague_mine
    investigator_mine = {
        item["id"] for item in investigator.get("/api/v1/follow-ups", params={"box": "mine"}).json()["items"]
    }
    assert capa_id in investigator_mine and risk_id not in investigator_mine
    finished = investigator.get("/api/v1/follow-ups", params={"box": "all", "status": "DONE"}).json()
    assert capa_id in {item["id"] for item in finished["items"]} and risk_id not in {
        item["id"] for item in finished["items"]
    }
    assert finished["page"] == 1 and finished["total"] >= 1
    assert investigator.get("/api/v1/follow-ups", params={"status": "FINISHED"}).status_code == 422
    assert investigator.get("/api/v1/follow-ups", params={"box": "inbox"}).status_code == 422


def test_completing_the_follow_up_task_in_my_work_completes_the_follow_up(org):
    tenant_id = org["tenant_id"]
    investigator, _ = org["investigator"]
    regulatory, regulatory_id = org["regulatory"]
    case = _open(investigator, org["seed"])
    made = _decide(
        tenant_id,
        case["id"],
        follow_ups=[
            {"action_type": "REGULATORY_ACTION_REQUIRED", "assignee": regulatory_id, "role": "REGULATORY_REVIEWER"},
            {"action_type": "FIELD_ACTION_REVIEW_REQUIRED", "assignee": regulatory_id},
        ],
    )
    (report_id, field_id), (report_task, field_task) = made["follow_ups"], made["tasks"]

    completed = regulatory.post(
        f"/api/v1/tasks/{report_task}/complete", json={"reason": "Vigilance report filed with the authority"}
    )
    assert completed.status_code == 200, completed.text
    assert completed.json()["status"] == "COMPLETED"
    row = _get(tenant_id, DecisionFollowUp, report_id)
    assert row.status == "DONE" and row.completion_note == "Vigilance report filed with the authority"
    assert row.completed_by == regulatory_id and row.completed_at is not None
    (audit,) = _audits(tenant_id, report_id, "FOLLOW_UP_COMPLETED")
    assert audit.details["through_task"]
    again = regulatory.post(f"/api/v1/follow-ups/{report_id}/complete", json={"note": NOTE})
    assert again.status_code == 409

    # Without a reason the follow-up still completes, noting the task.
    assert regulatory.post(f"/api/v1/tasks/{field_task}/complete", json={}).status_code == 200
    row = _get(tenant_id, DecisionFollowUp, field_id)
    task = _get(tenant_id, WorkflowTask, field_task)
    assert row.status == "DONE" and row.completion_note == f"Completed through its task {task.business_id}"


def test_cancelling_a_follow_up_needs_investigation_assign_and_cancels_its_task(org):
    tenant_id = org["tenant_id"]
    investigator, investigator_id = org["investigator"]
    quality, _ = org["quality"]
    case = _open(investigator, org["seed"])
    made = _decide(
        tenant_id, case["id"], follow_ups=[{"action_type": "PRODUCT_CHANGE_REQUIRED", "assignee": investigator_id}]
    )
    (follow_up_id,), (task_id,) = made["follow_ups"], made["tasks"]
    path = f"/api/v1/follow-ups/{follow_up_id}/cancel"

    denied = investigator.post(path, json={"reason": REASON})
    assert denied.status_code == 403 and _code(denied) == "PERMISSION_DENIED"
    assert quality.post(path, json={"reason": "short"}).status_code == 422
    cancelled = quality.post(path, json={"reason": REASON})
    assert cancelled.status_code == 200, cancelled.text
    assert cancelled.json()["status"] == "CANCELLED" and cancelled.json()["completion_note"] == REASON
    task = _get(tenant_id, WorkflowTask, task_id)
    assert task.status == "CANCELLED" and task.completion_outcome == "FOLLOW_UP_CANCELLED"
    (audit,) = _audits(tenant_id, follow_up_id, "FOLLOW_UP_CANCELLED")
    assert audit.reason == REASON
    assert quality.post(path, json={"reason": REASON}).status_code == 409
    assert investigator.post(f"/api/v1/follow-ups/{follow_up_id}/start").status_code == 409
    assert investigator.post(f"/api/v1/follow-ups/{follow_up_id}/complete", json={"note": NOTE}).status_code == 409


def test_a_capa_follow_up_opens_one_capa_record(org):
    tenant_id = org["tenant_id"]
    investigator, investigator_id = org["investigator"]
    colleague, _ = org["colleague"]
    regulatory, _ = org["regulatory"]
    case = _open(investigator, org["seed"])
    made = _decide(
        tenant_id,
        case["id"],
        follow_ups=[
            {"action_type": "CAPA_REQUIRED", "assignee": investigator_id},
            {"action_type": "CAPA_REQUIRED", "role": "INVESTIGATOR"},
            {"action_type": "RISK_REASSESSMENT_REQUIRED", "assignee": investigator_id},
        ],
    )
    first_id, second_id, risk_id = made["follow_ups"]
    body = {"title": "Replace the pressure sensor supplier", "due_at": "2027-03-31T12:00:00Z"}

    assert regulatory.post(f"/api/v1/follow-ups/{first_id}/capa", json=body).status_code == 403
    not_capa = investigator.post(f"/api/v1/follow-ups/{risk_id}/capa", json=body)
    assert not_capa.status_code == 409 and _code(not_capa) == "FOLLOW_UP_NOT_CAPA"
    assert investigator.post(f"/api/v1/follow-ups/{first_id}/capa", json={"title": "Fix"}).status_code == 422

    created = investigator.post(f"/api/v1/follow-ups/{first_id}/capa", json=body)
    assert created.status_code == 201, created.text
    capa = created.json()["capa"]
    assert capa["capa_identifier"] == f"CAPA-{case['business_id']}-1" and capa["business_id"]
    assert created.json()["status"] == "OPEN" and created.json()["actions"]["can_create_capa"] is False
    stored = _get(tenant_id, Capa, capa["id"])
    assert stored.title == body["title"] and stored.action_type == "CORRECTIVE"
    assert stored.source_type == "INVESTIGATION_DECISION" and stored.source_reference == made["decision_business_id"]
    assert stored.source_system == "MDARIX" and stored.status == "open" and stored.opened_at is not None
    assert str(stored.product_id) == org["seed"]["product_id"] and str(stored.investigation_id) == case["id"]
    assert stored.due_at.isoformat().startswith("2027-03-31")
    assert str(_get(tenant_id, DecisionFollowUp, first_id).capa_id) == capa["id"]
    (audit,) = _audits(tenant_id, first_id, "FOLLOW_UP_CAPA_CREATED")
    assert audit.details["capa_identifier"] == capa["capa_identifier"]

    again = investigator.post(f"/api/v1/follow-ups/{first_id}/capa", json=body)
    assert again.status_code == 409 and _code(again) == "CAPA_ALREADY_CREATED"
    second = colleague.post(f"/api/v1/follow-ups/{second_id}/capa", json={"title": "Second corrective action"})
    assert second.status_code == 201, second.text
    assert second.json()["capa"]["capa_identifier"] == f"CAPA-{case['business_id']}-2"


def test_a_recorded_capa_keeps_the_number_the_qms_gave_it(org):
    """J22: the CAPA MDARIX records is raised in the QMS; its QMS reference is kept with it, given when it is
    recorded or added later, and shown wherever the CAPA shows (the follow-up, the effectiveness board, the oversight
    view, the report worksheet's remedial action)."""
    tenant_id = org["tenant_id"]
    investigator, investigator_id = org["investigator"]
    regulatory, _ = org["regulatory"]
    case = _open(investigator, org["seed"])
    made = _decide(
        tenant_id,
        case["id"],
        follow_ups=[
            {"action_type": "CAPA_REQUIRED", "assignee": investigator_id},
            {"action_type": "CAPA_REQUIRED", "assignee": investigator_id},
        ],
    )
    first_id, second_id = made["follow_ups"]
    bad = investigator.post(
        f"/api/v1/follow-ups/{first_id}/capa", json={"title": "Fix the seal", "qms_reference": "=1+1"}
    )
    assert bad.status_code == 422
    created = investigator.post(
        f"/api/v1/follow-ups/{first_id}/capa", json={"title": "Fix the seal", "qms_reference": " CAPA-0450 "}
    )
    assert created.status_code == 201, created.text
    assert created.json()["capa"]["qms_reference"] == "CAPA-0450"
    assert created.json()["actions"]["can_set_qms_reference"] is True
    assert _get(tenant_id, Capa, created.json()["capa"]["id"]).qms_reference == "CAPA-0450"

    path = f"/api/v1/follow-ups/{second_id}/capa/qms-reference"
    early = investigator.post(path, json={"qms_reference": "CAPA-0451"})
    assert early.status_code == 409 and _code(early) == "FOLLOW_UP_HAS_NO_CAPA"
    recorded = investigator.post(f"/api/v1/follow-ups/{second_id}/capa", json={"title": "Retrain the ward"})
    assert recorded.json()["capa"]["qms_reference"] is None
    assert regulatory.post(path, json={"qms_reference": "CAPA-0451"}).status_code == 403
    saved = investigator.post(path, json={"qms_reference": "CAPA-0451"})
    assert saved.status_code == 200, saved.text
    assert saved.json()["capa"]["qms_reference"] == "CAPA-0451"
    (audit,) = _audits(tenant_id, second_id, "FOLLOW_UP_CAPA_QMS_REFERENCE_SET")
    assert audit.old_values == {"qms_reference": None} and audit.new_values == {"qms_reference": "CAPA-0451"}
    cleared = investigator.post(path, json={"qms_reference": "  "})
    assert cleared.status_code == 200 and cleared.json()["capa"]["qms_reference"] is None

    capa = _get(tenant_id, Capa, recorded.json()["capa"]["id"])
    assert rules.capa_qms_words(capa) == "to raise in your QMS"
    capa.qms_reference = "CAPA-0451"
    assert rules.capa_qms_words(capa) == "QMS reference CAPA-0451"
    capa.qms_reference, capa.source_system = None, "TRACKWISE"
    assert rules.capa_qms_words(capa) is None


# ----------------------------------------------------------------------------------------------- late evidence


def test_late_evidence_asks_for_one_impact_assessment_and_never_changes_the_decision(org):
    tenant_id = org["tenant_id"]
    investigator, investigator_id = org["investigator"]
    colleague, colleague_id = org["colleague"]
    quality, _ = org["quality"]
    viewer, _ = org["viewer"]
    case = _open(investigator, org["seed"])
    made = _decide(tenant_id, case["id"])
    before = _get(tenant_id, Decision, made["decision_id"])

    loose = _evidence(tenant_id)
    linked = _link(investigator, case["id"], [loose])
    assert linked.status_code == 200, linked.text
    (first,) = _assessments(tenant_id, case["id"])
    assert first.trigger == "EVIDENCE_LINKED" and first.status == "OPEN" and first.business_id.startswith("IMP")
    assert str(first.decision_id) == made["decision_id"] and str(first.evidence_id) == loose
    task = _get(tenant_id, WorkflowTask, first.task_id)
    assert task.task_type == "IMPACT_ASSESSMENT" and task.status == "ASSIGNED"
    assert str(task.assigned_user_id) == investigator_id and task.source_entity_type == "ImpactAssessment"
    assert task.details["impact_assessment_id"] == str(first.id)
    (audit,) = _audits(tenant_id, first.id, "LATE_EVIDENCE_RECEIVED")
    assert audit.details["trigger"] == "EVIDENCE_LINKED" and audit.details["decision_id"] == made["decision_id"]

    # Reviewing the same evidence, or linking it again, asks for nothing more.
    reviewed = quality.post(
        f"/api/v1/investigations/{case['id']}/evidence/{loose}/review",
        json={"review_status": "ACCEPTED", "relationship": "CONTEXTUAL"},
    )
    assert reviewed.status_code == 200, reviewed.text
    assert _link(investigator, case["id"], [loose]).json()["linked"] == 0
    assert len(_assessments(tenant_id, case["id"])) == 1

    # Evidence recorded on the case before the decision, reviewed now.
    direct = _evidence(tenant_id, case_id=case["id"], ingested_at=datetime.now(timezone.utc) - timedelta(days=2))
    assert (
        quality.post(
            f"/api/v1/investigations/{case['id']}/evidence/{direct}/review",
            json={"review_status": "ACCEPTED", "relationship": "SUPPORTING"},
        ).status_code
        == 200
    )

    # An answer to an evidence request accepted as evidence.
    request_id = _request_row(
        tenant_id, case["id"], requester=investigator_id, status="RECEIVED", priority="MEDIUM", recipient=colleague_id
    )
    accepted = investigator.post(
        f"/api/v1/evidence-requests/{request_id}/review",
        json={"accept": True, "review_status": "ACCEPTED", "relationship": "SUPPORTING"},
    )
    assert accepted.status_code == 200, accepted.text
    answer = accepted.json()["evidence"]["evidence"]["id"]

    triggers = {str(row.evidence_id): row.trigger for row in _assessments(tenant_id, case["id"])}
    assert triggers == {loose: "EVIDENCE_LINKED", direct: "EVIDENCE_REVIEWED", answer: "EVIDENCE_REQUEST_ACCEPTED"}

    listed = viewer.get(f"/api/v1/investigations/{case['id']}/impact-assessments")
    assert listed.status_code == 200, listed.text
    items = listed.json()["items"]
    assert len(items) == 3 and items[0]["evidence"]["id"] == answer
    oldest = items[-1]
    assert oldest["trigger"] == "EVIDENCE_LINKED" and oldest["trigger_label"] == "Evidence linked to the investigation"
    assert oldest["evidence"] == {
        "id": loose,
        "business_id": oldest["evidence"]["business_id"],
        "title": "Late service report",
    }
    assert oldest["decision"] == {"id": made["decision_id"], "business_id": made["decision_business_id"]}
    assert oldest["status"] == "OPEN" and oldest["conclusion"] is None and oldest["assessed_by_name"] is None
    assert oldest["actions"] == {"can_complete": False}
    mine = investigator.get(f"/api/v1/impact-assessments/{oldest['id']}")
    assert mine.status_code == 200 and mine.json()["actions"] == {"can_complete": True}

    after = _get(tenant_id, Decision, made["decision_id"])
    for field in ("decision_status", "outcome", "superseded_by_decision_id", "updated_at", "rationale"):
        assert getattr(after, field) == getattr(before, field), field
    assert _get(tenant_id, Investigation, case["id"]).workflow_state == "DECIDED"

    # A case without a signed decision asks for nothing.
    undecided = _open(investigator, org["seed"])
    assert _link(investigator, undecided["id"], [_evidence(tenant_id)]).status_code == 200
    assert _assessments(tenant_id, undecided["id"]) == []


def test_the_sweep_catches_evidence_ingested_after_the_decision_once(org):
    tenant_id = org["tenant_id"]
    investigator, investigator_id = org["investigator"]
    now = datetime.now(timezone.utc)
    case = _open(investigator, org["seed"])
    made = _decide(tenant_id, case["id"], state="CLOSED", decided_at=now - timedelta(hours=2))
    late = _evidence(tenant_id, case_id=case["id"], ingested_at=now)
    early = _evidence(tenant_id, case_id=case["id"], ingested_at=now - timedelta(days=1))

    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        found = {str(evidence_id) for evidence_id, _ in impact.late_evidence(db, tenant_id)}
    assert late in found and early not in found

    _sweep(tenant_id)
    (row,) = _assessments(tenant_id, case["id"])
    assert row.trigger == "EVIDENCE_INGESTED" and str(row.evidence_id) == late
    assert str(row.decision_id) == made["decision_id"]
    task = _get(tenant_id, WorkflowTask, row.task_id)
    assert task.created_by == "system:scheduler" and str(task.assigned_user_id) == investigator_id
    _sweep(tenant_id)
    assert len(_assessments(tenant_id, case["id"])) == 1


def test_no_impact_keeps_the_decision_and_a_material_impact_reopens_the_case(org):
    tenant_id = org["tenant_id"]
    investigator, _ = org["investigator"]
    colleague, _ = org["colleague"]
    regulatory, _ = org["regulatory"]
    viewer, _ = org["viewer"]
    case = _open(investigator, org["seed"])
    made = _decide(tenant_id, case["id"])
    before = _get(tenant_id, Decision, made["decision_id"])
    first_evidence, second_evidence = _evidence(tenant_id), _evidence(tenant_id)
    assert _link(investigator, case["id"], [first_evidence, second_evidence]).status_code == 200
    by_evidence = {str(row.evidence_id): row for row in _assessments(tenant_id, case["id"])}
    first, second = by_evidence[first_evidence], by_evidence[second_evidence]
    path = f"/api/v1/impact-assessments/{first.id}/complete"
    no_impact = {"conclusion": "NO_IMPACT", "rationale": RATIONALE}

    assert viewer.post(path, json=no_impact).status_code == 403
    assert regulatory.post(path, json=no_impact).status_code == 403
    assert colleague.post(path, json={"conclusion": "NO_IMPACT", "rationale": "Too short"}).status_code == 422
    assert colleague.post(path, json={"conclusion": "MAYBE", "rationale": RATIONALE}).status_code == 422
    done = colleague.post(path, json=no_impact)
    assert done.status_code == 200, done.text
    body = done.json()
    assert body["status"] == "COMPLETED" and body["conclusion"] == "NO_IMPACT" and body["rationale"] == RATIONALE
    assert body["conclusion_label"] == "No impact on the decision" and body["assessed_by_name"] == "Colleague Followups"
    assert body["assessed_role"] == "INVESTIGATOR" and body["assessed_at"]
    assert body["case_reopened"] is False and body["decision_under_reconsideration"] is False
    assert body["workflow_state"] == "DECIDED" and body["actions"] == {"can_complete": False}
    task = _get(tenant_id, WorkflowTask, first.task_id)
    assert task.status == "COMPLETED" and task.completion_outcome == "NO_IMPACT"
    again = colleague.post(path, json=no_impact)
    assert again.status_code == 409 and _code(again) == "IMPACT_ASSESSMENT_COMPLETED"
    assert len(_audits(tenant_id, first.id, "IMPACT_ASSESSMENT_COMPLETED")) == 1
    assert _audits(tenant_id, made["decision_id"], "DECISION_UNDER_RECONSIDERATION") == []

    material = investigator.post(
        f"/api/v1/impact-assessments/{second.id}/complete",
        json={"conclusion": "MATERIAL_IMPACT", "rationale": "The report shows a second failure mode we never assessed"},
    )
    assert material.status_code == 200, material.text
    body = material.json()
    assert body["case_reopened"] is True and body["decision_under_reconsideration"] is True
    assert body["workflow_state"] == "IN_PROGRESS"
    stored = _get(tenant_id, Investigation, case["id"])
    assert stored.workflow_state == "IN_PROGRESS" and stored.status == "open"
    changes = _audits(tenant_id, case["id"], "INVESTIGATION_STATE_CHANGED")
    assert changes and changes[-1].new_values == {"workflow_state": "IN_PROGRESS"}
    (reconsidered,) = _audits(tenant_id, made["decision_id"], "DECISION_UNDER_RECONSIDERATION")
    assert reconsidered.details["impact_assessment_id"] == str(second.id)
    after = _get(tenant_id, Decision, made["decision_id"])
    for field in ("decision_status", "outcome", "superseded_by_decision_id", "updated_at", "rationale", "decided_at"):
        assert getattr(after, field) == getattr(before, field), field
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        open_case_tasks = (
            db.query(WorkflowTask)
            .filter(
                WorkflowTask.investigation_id == uuid.UUID(case["id"]),
                WorkflowTask.task_type == "INVESTIGATION",
                WorkflowTask.status.in_(OPEN_TASK_STATUSES),
            )
            .count()
        )
    assert open_case_tasks >= 1


def test_a_material_impact_reopens_a_closed_case(org):
    tenant_id = org["tenant_id"]
    investigator, _ = org["investigator"]
    case = _open(investigator, org["seed"])
    _decide(tenant_id, case["id"], state="CLOSED")
    _evidence(tenant_id, case_id=case["id"])
    _sweep(tenant_id)
    (row,) = _assessments(tenant_id, case["id"])
    material = investigator.post(
        f"/api/v1/impact-assessments/{row.id}/complete",
        json={"conclusion": "MATERIAL_IMPACT", "rationale": "The report shows a second failure mode we never assessed"},
    )
    assert material.status_code == 200, material.text
    assert material.json()["case_reopened"] is True
    stored = _get(tenant_id, Investigation, case["id"])
    assert stored.workflow_state == "IN_PROGRESS" and stored.status == "open" and stored.closed_at is None


def test_the_impact_task_cannot_be_completed_in_my_work(org):
    tenant_id = org["tenant_id"]
    investigator, _ = org["investigator"]
    case = _open(investigator, org["seed"])
    _decide(tenant_id, case["id"])
    assert _link(investigator, case["id"], [_evidence(tenant_id)]).status_code == 200
    (row,) = _assessments(tenant_id, case["id"])

    refused = investigator.post(f"/api/v1/tasks/{row.task_id}/complete", json={"outcome": "DONE"})
    assert refused.status_code == 409 and _code(refused) == "USE_IMPACT_ASSESSMENT"
    assert _get(tenant_id, ImpactAssessment, row.id).status == "OPEN"
    assert _get(tenant_id, WorkflowTask, row.task_id).status == "ASSIGNED"
    shown = investigator.get(f"/api/v1/tasks/{row.task_id}")
    assert shown.status_code == 200 and shown.json()["actions"]["can_complete"] is False
    assert shown.json()["source"]["label"].startswith("Impact assessment IMP")


# ------------------------------------------------------------------------------------------------------- closure


def test_a_brief_case_closes_only_when_its_closure_criteria_are_met(org):
    tenant_id = org["tenant_id"]
    investigator, investigator_id = org["investigator"]
    viewer, _ = org["viewer"]
    case = _open(investigator, org["seed"])
    made = _decide(tenant_id, case["id"], follow_ups=[{"action_type": "CAPA_REQUIRED", "assignee": investigator_id}])
    (follow_up_id,), (task_id,) = made["follow_ups"], made["tasks"]
    assert _link(investigator, case["id"], [_evidence(tenant_id)]).status_code == 200
    (assessment,) = _assessments(tenant_id, case["id"])
    review_id = _review_row(tenant_id, case["id"], requester=investigator_id)
    request_id = _request_row(tenant_id, case["id"], requester=investigator_id, status="OPEN", priority="HIGH")
    path = f"/api/v1/investigations/{case['id']}/closure-check"

    check = viewer.get(path)
    assert check.status_code == 200, check.text
    assert check.json()["applies"] is True and check.json()["can_close"] is False
    results = _criteria(check.json())
    assert results["IMPACT_ASSESSMENTS"] == "BLOCKED" and results["CASE_REVIEWS"] == "BLOCKED"
    assert results["EVIDENCE_REQUESTS"] == "BLOCKED"
    assert results["SIGNED_DECISION"] == "PASS" and results["FOLLOW_UPS"] == "PASS" and results["CASE_OPEN"] == "PASS"

    refused = investigator.patch(f"/api/v1/investigations/{case['id']}", json={"status": "closed", "reason": REASON})
    assert refused.status_code == 409 and _code(refused) == "CLOSURE_CRITERIA_NOT_MET"
    assert {item["key"] for item in refused.json()["detail"]["criteria"]} == {
        "IMPACT_ASSESSMENTS",
        "CASE_REVIEWS",
        "EVIDENCE_REQUESTS",
    }
    assert _get(tenant_id, Investigation, case["id"]).workflow_state == "DECIDED"

    assert (
        investigator.post(
            f"/api/v1/impact-assessments/{assessment.id}/complete",
            json={"conclusion": "NO_IMPACT", "rationale": RATIONALE},
        ).status_code
        == 200
    )
    _update(tenant_id, CaseReview, review_id, status="CANCELLED")
    _update(tenant_id, SupplierEvidenceRequest, request_id, status="CANCELLED")
    check = viewer.get(path).json()
    assert check["can_close"] is True and all(item["result"] != "BLOCKED" for item in check["criteria"])

    closed = investigator.patch(f"/api/v1/investigations/{case['id']}", json={"status": "closed", "reason": REASON})
    assert closed.status_code == 200, closed.text
    assert closed.json()["status"] == "closed" and closed.json()["workflow_state"] == "CLOSED"
    assert _criteria(viewer.get(path).json())["CASE_OPEN"] == "BLOCKED"

    # The follow-up outlives the case: still open, with a live task replacing the one closing cancelled.
    row = _get(tenant_id, DecisionFollowUp, follow_up_id)
    assert row.status == "OPEN" and str(row.task_id) != task_id
    old, new = _get(tenant_id, WorkflowTask, task_id), _get(tenant_id, WorkflowTask, row.task_id)
    assert old.status == "CANCELLED" and old.completion_outcome == "CASE_CLOSED"
    assert new.status in OPEN_TASK_STATUSES and new.task_type == "FOLLOW_UP"
    assert new.details["follow_up_id"] == follow_up_id and str(new.assigned_user_id) == investigator_id
    assert len(_audits(tenant_id, follow_up_id, "FOLLOW_UP_TASK_RENEWED")) == 1
    done = investigator.post(f"/api/v1/follow-ups/{follow_up_id}/complete", json={"note": NOTE})
    assert done.status_code == 200 and _get(tenant_id, WorkflowTask, row.task_id).status == "COMPLETED"


def test_closure_needs_an_accepting_decision_and_every_chosen_follow_up(org):
    tenant_id = org["tenant_id"]
    investigator, investigator_id = org["investigator"]

    brief_only = _open(investigator, org["seed"])
    _brief_only(tenant_id, brief_only["id"])
    check = investigator.get(f"/api/v1/investigations/{brief_only['id']}/closure-check").json()
    assert check["applies"] is True and _criteria(check)["SIGNED_DECISION"] == "BLOCKED"
    refused = investigator.patch(
        f"/api/v1/investigations/{brief_only['id']}", json={"status": "closed", "reason": REASON}
    )
    assert refused.status_code == 409 and "SIGNED_DECISION" in {
        item["key"] for item in refused.json()["detail"]["criteria"]
    }

    rejected = _open(investigator, org["seed"])
    _decide(tenant_id, rejected["id"], outcome="REJECT_CONCLUSION", state="IN_PROGRESS")
    check = investigator.get(f"/api/v1/investigations/{rejected['id']}/closure-check").json()
    assert check["can_close"] is False and _criteria(check)["SIGNED_DECISION"] == "BLOCKED"

    missing = _open(investigator, org["seed"])
    _decide(
        tenant_id,
        missing["id"],
        follow_ups=[
            {"action_type": "CAPA_REQUIRED", "assignee": investigator_id},
            {"action_type": "RISK_REASSESSMENT_REQUIRED", "assignee": investigator_id, "skip_row": True},
        ],
    )
    check = investigator.get(f"/api/v1/investigations/{missing['id']}/closure-check").json()
    assert check["can_close"] is False and _criteria(check)["FOLLOW_UPS"] == "BLOCKED"
    refused = investigator.patch(f"/api/v1/investigations/{missing['id']}", json={"status": "closed", "reason": REASON})
    assert refused.status_code == 409 and [item["key"] for item in refused.json()["detail"]["criteria"]] == [
        "FOLLOW_UPS"
    ]


def test_a_case_outside_the_brief_flow_closes_as_before(org):
    tenant_id = org["tenant_id"]
    investigator, _ = org["investigator"]
    case = _open(investigator, org["seed"])
    check = investigator.get(f"/api/v1/investigations/{case['id']}/closure-check")
    assert check.status_code == 200, check.text
    assert check.json()["applies"] is False and check.json()["can_close"] is True
    assert [item["key"] for item in check.json()["criteria"]] == ["CASE_OPEN", "DECISIONS_REVIEWED"]

    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        legacy = Decision(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            investigation_id=uuid.UUID(case["id"]),
            decision_identifier=f"FU-L-{uuid.uuid4().hex[:10]}",
            decision_type="INVESTIGATION_REVIEW",
            disposition="REQUIRES_REVIEW",
            rationale="Awaiting its human review",
            decision_status="REQUIRES_REVIEW",
            authorized_by_ref="someone@example.invalid",
            updated_at=now,
            decision_timestamp=now,
            created_at=now,
        )
        db.add(legacy)
        db.commit()
        legacy_id = str(legacy.id)
    waiting = investigator.patch(f"/api/v1/investigations/{case['id']}", json={"status": "closed", "reason": REASON})
    assert waiting.status_code == 409 and _code(waiting) == "DECISIONS_AWAITING_REVIEW"
    check = investigator.get(f"/api/v1/investigations/{case['id']}/closure-check").json()
    assert check["applies"] is False and _criteria(check)["DECISIONS_REVIEWED"] == "BLOCKED"

    _update(tenant_id, Decision, legacy_id, decision_status="APPROVED")
    closed = investigator.patch(f"/api/v1/investigations/{case['id']}", json={"status": "closed", "reason": REASON})
    assert closed.status_code == 200, closed.text
    assert closed.json()["status"] == "closed"
    assert investigator.get(f"/api/v1/investigations/{case['id']}/follow-ups").json() == {"items": []}
    assert investigator.get(f"/api/v1/investigations/{case['id']}/impact-assessments").json() == {"items": []}


# ------------------------------------------------------------------------------------------ other organizations


def test_another_organizations_records_are_not_found(org):
    investigator, _ = org["investigator"]
    quality, _ = org["quality"]
    other = org["other"]
    follow_up, assessment, case_id = other["follow_up_id"], other["assessment_id"], other["case_id"]
    for path in (
        f"/api/v1/investigations/{case_id}/follow-ups",
        f"/api/v1/investigations/{case_id}/impact-assessments",
        f"/api/v1/investigations/{case_id}/closure-check",
        f"/api/v1/follow-ups/{follow_up}",
        f"/api/v1/impact-assessments/{assessment}",
        f"/api/v1/follow-ups/{uuid.uuid4()}",
    ):
        assert investigator.get(path).status_code == 404, path
    assert investigator.post(f"/api/v1/follow-ups/{follow_up}/start").status_code == 404
    assert investigator.post(f"/api/v1/follow-ups/{follow_up}/complete", json={"note": NOTE}).status_code == 404
    assert quality.post(f"/api/v1/follow-ups/{follow_up}/cancel", json={"reason": REASON}).status_code == 404
    capa = investigator.post(f"/api/v1/follow-ups/{follow_up}/capa", json={"title": "Replace the sensor"})
    assert capa.status_code == 404
    completed = investigator.post(
        f"/api/v1/impact-assessments/{assessment}/complete", json={"conclusion": "NO_IMPACT", "rationale": RATIONALE}
    )
    assert completed.status_code == 404
    listed = investigator.get("/api/v1/follow-ups", params={"box": "all", "page_size": 200}).json()["items"]
    assert follow_up not in {item["id"] for item in listed}
