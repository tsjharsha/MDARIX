"""Investigation evidence end to end: the inventory (links and evidence recorded on the case), idempotent linking,
review rules and their history, provenance, requests to a colleague or a role (create -> tasks -> acknowledge ->
respond -> review into evidence -> inventory), cannot provide, cancel, a supplier request reviewed into evidence,
attachment permissions, permissions and organization isolation.

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
from backend.app.db.models.case_scope import EvidenceReviewEvent
from backend.app.db.models.foundation import (
    AuditEvent,
    AuthUser,
    Evidence,
    Investigation,
    Product,
    Supplier,
    TenantMembership,
    Unknown,
)
from backend.app.db.models.stage3 import SupplierEvidenceRequest
from backend.app.db.models.workflow import WorkflowTask
from backend.app.db.session import SessionLocal
from backend.app.db.tenant_scope import bind_tenant
from backend.app.main import app
from tests.reports_seed import role_client

PASSWORD = "Evidence workflow 2026!"
REASON = "Reason recorded for the audit trail"
PDF = b"%PDF-1.4 batch record KS-5521"


@pytest.fixture(scope="module")
def org():
    """A fresh organization with a product, two investigators, a risk reviewer, a quality reviewer and a viewer."""
    from backend.app.customer_lifecycle import build_customer_tenant
    from backend.app.trial.retention import purge_trial

    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        customer, tenant = build_customer_tenant(
            db=db, tenant_key=f"EVIDENCE_{uuid.uuid4().hex[:8].upper()}", name="Evidence work", status="ACTIVE", now=now
        )
        db.add(customer)
        db.add(tenant)
        db.commit()  # registers the organization on the shared plane (migration md20)
        tenant_id = tenant.id
    people = {}
    for name, role in (
        ("investigator", "INVESTIGATOR"),
        ("colleague", "INVESTIGATOR"),
        ("risk", "RISK_REVIEWER"),
        ("reviewer", "REVIEWER"),
        ("viewer", "VIEWER"),
    ):
        people[name] = _client(tenant_id, role)
    try:
        yield {"tenant_id": tenant_id, "product_id": _product(tenant_id), **people}
    finally:
        with SessionLocal() as db:
            purge_trial(db, tenant_id, "test:evidence-workflow-cleanup")


def _client(tenant_id, role: str) -> tuple[TestClient, str]:
    with SessionLocal() as db:
        now = datetime.now(timezone.utc)
        user = AuthUser(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            username=f"evidence-{role.lower()}-{uuid.uuid4().hex[:8]}@example.invalid",
            display_name=f"{role.title()} Evidence",
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


def _product(tenant_id) -> str:
    now = datetime.now(timezone.utc)
    tag = uuid.uuid4().hex[:8].upper()
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        product = Product(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            product_identifier=f"EVW-P-{tag}",
            name=f"Evidence Pump {tag}",
            created_at=now,
            updated_at=now,
        )
        db.add(product)
        db.commit()
        return str(product.id)


def _case(org, who: str = "investigator") -> dict:
    client, _ = org[who]
    made = client.post(
        "/api/v1/investigations",
        json={
            "product_id": org["product_id"],
            "investigation_question": "Why do occlusion alarms rise after release B?",
            "assign_to_me": True,
        },
    )
    assert made.status_code == 201, made.text
    return made.json()


def _evidence(tenant_id, *, case_id=None, title: str = "Service report") -> str:
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        row = Evidence(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            evidence_identifier=f"EVW-{uuid.uuid4().hex[:10].upper()}",
            investigation_id=uuid.UUID(case_id) if case_id else None,
            evidence_type="SERVICE_REPORT",
            title=title,
            source_system="Service desk",
            source_identifier=f"SR-{uuid.uuid4().hex[:6]}",
            source_timestamp=now - timedelta(days=3),
            ingestion_timestamp=now,
            content="Occlusion alarm reproduced at 4 psi.",
            created_at=now,
            updated_at=now,
        )
        db.add(row)
        db.commit()
        return str(row.id)


def _unknown(tenant_id, case_id) -> dict:
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        row = Unknown(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            investigation_id=uuid.UUID(case_id),
            description="Was lot KS-5521 sterilized in the validated cycle?",
            status="open",
            created_at=now,
            updated_at=now,
        )
        db.add(row)
        db.commit()
        return {"id": str(row.id), "business_id": row.business_id}


def _supplier(tenant_id) -> str:
    now = datetime.now(timezone.utc)
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        row = Supplier(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            supplier_identifier=f"SUP-EVW-{uuid.uuid4().hex[:8].upper()}",
            name="Tubing Co",
            created_at=now,
            updated_at=now,
        )
        db.add(row)
        db.commit()
        return str(row.id)


def _close(tenant_id, case_id) -> None:
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        case = db.query(Investigation).filter(Investigation.id == uuid.UUID(case_id)).one()
        case.workflow_state = "CLOSED"
        case.status = "closed"
        db.commit()


def _tasks(tenant_id, source_id, task_type: str | None = None) -> list[WorkflowTask]:
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        query = db.query(WorkflowTask).filter(WorkflowTask.source_entity_id == uuid.UUID(str(source_id)))
        if task_type:
            query = query.filter(WorkflowTask.task_type == task_type)
        rows = query.order_by(WorkflowTask.created_at).all()
        db.expunge_all()
        return rows


def _review_events(tenant_id, evidence_id) -> list[EvidenceReviewEvent]:
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        rows = (
            db.query(EvidenceReviewEvent)
            .filter(EvidenceReviewEvent.evidence_id == uuid.UUID(str(evidence_id)))
            .order_by(EvidenceReviewEvent.created_at, EvidenceReviewEvent.id)
            .all()
        )
        db.expunge_all()
        return rows


def _audit_actions(tenant_id, entity_id) -> list[str]:
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        return [
            row[0]
            for row in db.query(AuditEvent.action)
            .filter(AuditEvent.tenant_id == tenant_id, AuditEvent.entity_id == uuid.UUID(str(entity_id)))
            .order_by(AuditEvent.created_at)
        ]


def _code(response) -> str | None:
    detail = response.json().get("detail")
    return detail.get("code") if isinstance(detail, dict) else None


def _inventory(client, case_id) -> dict:
    response = client.get(f"/api/v1/investigations/{case_id}/evidence-inventory")
    assert response.status_code == 200, response.text
    return response.json()


def _item(inventory: dict, evidence_id: str) -> dict:
    (found,) = [item for item in inventory["items"] if item["evidence"]["id"] == evidence_id]
    return found


def _internal(case_id, client, **changes):
    body = {
        "kind": "INTERNAL",
        "title": "Batch record for lot KS-5521",
        "requested_items": ["Batch record", "Sterilization cycle printout"],
        "rationale": "Needed to close the sterilization unknown",
        "priority": "HIGH",
        "due_at": (datetime.now(timezone.utc) + timedelta(days=5)).isoformat(),
        **changes,
    }
    return client.post(f"/api/v1/investigations/{case_id}/evidence-requests", json=body)


# ------------------------------------------------------------------------------------------------------ inventory


def test_the_inventory_unites_links_and_case_evidence_and_linking_is_idempotent(org):
    tenant_id = org["tenant_id"]
    client, _ = org["investigator"]
    case = _case(org)
    direct = _evidence(tenant_id, case_id=case["id"], title="Complaint photo")
    elsewhere = _evidence(tenant_id, title="Field service report")

    inventory = _inventory(client, case["id"])
    item = _item(inventory, direct)
    assert item["origin"] == "DIRECT" and item["request"] is None
    assert item["link"]["linked"] is False and item["link"]["review_status"] == "UNREVIEWED"
    assert item["link"]["review_status_label"] == "Not reviewed"
    assert item["evidence"]["business_id"].startswith("EVD") and item["evidence"]["has_document"] is False
    assert inventory["counts"]["total"] == 1 and inventory["counts"]["unreviewed"] == 1
    assert inventory["actions"] == {"can_link": True, "can_review": True, "can_request": True}
    assert _inventory(org["viewer"][0], case["id"])["actions"] == {
        "can_link": False,
        "can_review": False,
        "can_request": False,
    }

    path = f"/api/v1/investigations/{case['id']}/evidence-links"
    body = {"evidence_ids": [elsewhere], "relationship": "CONTEXTUAL", "reason": "Same pump model, same week"}
    first = client.post(path, json=body)
    assert first.status_code == 200, first.text
    assert first.json()["linked"] == 1 and first.json()["already_linked"] == 0
    linked = first.json()["items"][0]
    assert linked["origin"] == "LINKED" and linked["link"]["linked"] is True
    assert linked["link"]["relationship"] == "CONTEXTUAL" and linked["link"]["linked_by_name"]
    again = client.post(path, json=body)
    assert again.status_code == 200 and again.json()["linked"] == 0 and again.json()["already_linked"] == 1

    inventory = _inventory(client, case["id"])
    assert inventory["counts"]["total"] == 2 and inventory["counts"]["contextual"] == 1
    (event,) = _review_events(tenant_id, elsewhere)
    assert event.event_type == "LINKED" and event.to_relationship == "CONTEXTUAL"
    assert event.actor_role == "INVESTIGATOR" and event.reason == "Same pump model, same week"
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        linked_audits = (
            db.query(AuditEvent).filter(AuditEvent.tenant_id == tenant_id, AuditEvent.action == "EVIDENCE_LINKED").all()
        )
    assert len([row for row in linked_audits if (row.details or {}).get("evidence_id") == elsewhere]) == 1

    missing = client.post(path, json={"evidence_ids": [str(uuid.uuid4())]})
    assert missing.status_code == 404 and _code(missing) == "EVIDENCE_NOT_FOUND"
    assert org["viewer"][0].post(path, json=body).status_code == 403
    assert client.post(path, json={"evidence_ids": [elsewhere], "relationship": "RELEVANT"}).status_code == 422


def test_review_rules_history_and_provenance(org):
    tenant_id = org["tenant_id"]
    client, _ = org["investigator"]
    case = _case(org)
    direct = _evidence(tenant_id, case_id=case["id"], title="Pressure log")
    unrelated = _evidence(tenant_id, title="Another product's log")
    base = f"/api/v1/investigations/{case['id']}/evidence"

    for body in (
        {"review_status": "REJECTED", "relationship": "UNRELATED"},
        {"review_status": "ACCEPTED_WITH_LIMITATION", "relationship": "SUPPORTING"},
        {"review_status": "UNREVIEWED", "relationship": "SUPPORTING"},
    ):
        assert client.post(f"{base}/{direct}/review", json=body).status_code == 422
    limited = client.post(
        f"{base}/{direct}/review",
        json={
            "review_status": "ACCEPTED_WITH_LIMITATION",
            "relationship": "SUPPORTING",
            "limitation": "Only the first week was logged",
        },
    )
    assert limited.status_code == 200, limited.text
    assert limited.json()["link"]["linked"] is True and limited.json()["origin"] == "DIRECT"
    assert limited.json()["link"]["review_status"] == "ACCEPTED_WITH_LIMITATION"
    assert limited.json()["link"]["limitation"] == "Only the first week was logged"
    assert limited.json()["link"]["reviewed_by_name"] and limited.json()["link"]["reviewed_at"]
    rejected = client.post(
        f"{base}/{direct}/review",
        json={"review_status": "REJECTED", "relationship": "UNRELATED", "reason": REASON},
    )
    assert rejected.status_code == 200 and rejected.json()["link"]["review_reason"] == REASON
    assert rejected.json()["link"]["limitation"] is None

    first, second = _review_events(tenant_id, direct)
    assert (first.event_type, first.from_review_status, first.to_review_status) == (
        "REVIEWED",
        "UNREVIEWED",
        "ACCEPTED_WITH_LIMITATION",
    )
    assert (second.from_review_status, second.to_review_status) == ("ACCEPTED_WITH_LIMITATION", "REJECTED")
    assert (second.from_relationship, second.to_relationship) == ("SUPPORTING", "UNRELATED")
    assert second.reason == REASON and second.actor_role == "INVESTIGATOR"
    counts = _inventory(client, case["id"])["counts"]
    assert counts["rejected"] == 1 and counts["unrelated"] == 1 and counts["unreviewed"] == 0

    not_in_case = client.post(
        f"{base}/{unrelated}/review", json={"review_status": "ACCEPTED", "relationship": "SUPPORTING"}
    )
    assert not_in_case.status_code == 404 and _code(not_in_case) == "EVIDENCE_NOT_IN_CASE"
    assert (
        org["viewer"][0]
        .post(f"{base}/{direct}/review", json={"review_status": "ACCEPTED", "relationship": "SUPPORTING"})
        .status_code
        == 403
    )

    provenance = client.get(f"{base}/{direct}/provenance")
    assert provenance.status_code == 200, provenance.text
    body = provenance.json()
    assert body["evidence"]["id"] == direct and body["evidence"]["in_case"] is True
    assert body["evidence"]["review_status"] == "REJECTED"
    assert body["source"]["system"] == "Service desk" and body["source"]["record_identifier"]
    assert body["document"] is None and body["request"] is None
    assert [item["event_type"] for item in body["review_history"]] == ["REVIEWED", "REVIEWED"]
    assert body["review_history"][0]["limitation"] == "Only the first week was logged"
    assert body["review_history"][1]["actor_name"] and body["review_history"][1]["actor_role"] == "INVESTIGATOR"
    assert body["used_by"] == {"observations": 0, "hypotheses": 0}
    # Read-only: looking at provenance wrote nothing.
    assert len(_review_events(tenant_id, direct)) == 2


def test_a_closed_case_keeps_its_evidence_as_it_was(org):
    tenant_id = org["tenant_id"]
    client, _ = org["investigator"]
    case = _case(org)
    direct = _evidence(tenant_id, case_id=case["id"])
    other = _evidence(tenant_id)
    _close(tenant_id, case["id"])
    review = client.post(
        f"/api/v1/investigations/{case['id']}/evidence/{direct}/review",
        json={"review_status": "ACCEPTED", "relationship": "SUPPORTING"},
    )
    assert review.status_code == 409 and _code(review) == "CASE_CLOSED"
    link = client.post(f"/api/v1/investigations/{case['id']}/evidence-links", json={"evidence_ids": [other]})
    assert link.status_code == 409 and _code(link) == "CASE_CLOSED"
    request = _internal(case["id"], client, recipient_role="INVESTIGATOR")
    assert request.status_code == 409 and _code(request) == "CASE_CLOSED"
    assert _inventory(client, case["id"])["actions"] == {"can_link": False, "can_review": False, "can_request": False}


# ------------------------------------------------------------------------------------------- requests to colleagues


def test_an_internal_request_is_answered_and_reviewed_into_evidence(org):
    tenant_id = org["tenant_id"]
    requester, requester_id = org["investigator"]
    colleague, colleague_id = org["colleague"]
    case = _case(org)
    unknown = _unknown(tenant_id, case["id"])

    made = _internal(case["id"], requester, recipient_user_id=colleague_id, unknown_id=unknown["id"])
    assert made.status_code == 201, made.text
    request = made.json()
    assert request["kind"] == "INTERNAL" and request["status"] == "OPEN" and request["status_label"] == "Open"
    assert request["business_id"].startswith("EVR") and request["priority"] == "HIGH" and request["due_at"]
    assert request["overdue"] is False and request["requested_items"] == [
        "Batch record",
        "Sterilization cycle printout",
    ]
    assert request["rationale"] == "Needed to close the sterilization unknown"
    assert request["investigation"] == {"id": case["id"], "business_id": case["business_id"]}
    assert request["unknown"]["business_id"] == unknown["business_id"] and request["unknown"]["description"]
    assert request["requester"]["id"] == requester_id and request["requester"]["name"]
    assert request["recipient"]["user"]["id"] == colleague_id and request["recipient"]["email"] is None
    assert request["actions"]["can_cancel"] and not request["actions"]["can_respond"]
    request_id = request["id"]
    assert "EVIDENCE_REQUESTED" in _audit_actions(tenant_id, request_id)

    (response_task,) = _tasks(tenant_id, request_id, "EVIDENCE_RESPONSE")
    assert response_task.status == "ASSIGNED" and str(response_task.assigned_user_id) == colleague_id
    assert response_task.source_entity_type == "EvidenceRequest" and response_task.priority == "HIGH"
    assert response_task.due_at is not None and str(response_task.investigation_id) == case["id"]
    (waiting,) = _tasks(tenant_id, request_id, "EVIDENCE_REQUEST")
    assert waiting.status == "WAITING" and str(waiting.assigned_user_id) == requester_id
    # My Work shows the task with the request as its source.
    assigned = colleague.get("/api/v1/tasks", params={"view": "assigned", "page_size": 200}).json()["items"]
    (listed,) = [item for item in assigned if item["id"] == str(response_task.id)]
    assert listed["task_type_label"] == "Provide evidence"
    assert listed["source"]["label"] == f"Evidence request {request['business_id']}"

    def box(client, name):
        response = client.get("/api/v1/evidence-requests", params={"box": name, "investigation_id": case["id"]})
        assert response.status_code == 200, response.text
        return [item["id"] for item in response.json()["items"]]

    assert request_id in box(colleague, "received") and request_id not in box(colleague, "sent")
    assert request_id in box(requester, "sent") and request_id not in box(requester, "received")
    assert request_id in box(org["viewer"][0], "all")

    base = f"/api/v1/evidence-requests/{request_id}"
    not_recipient = requester.post(f"{base}/acknowledge")
    assert not_recipient.status_code == 403 and _code(not_recipient) == "NOT_RECIPIENT"
    acknowledged = colleague.post(f"{base}/acknowledge")
    assert acknowledged.status_code == 200 and acknowledged.json()["status"] == "ACKNOWLEDGED"
    assert acknowledged.json()["actions"]["can_respond"] and not acknowledged.json()["actions"]["can_acknowledge"]
    assert colleague.post(f"{base}/acknowledge").status_code == 409
    (response_task,) = _tasks(tenant_id, request_id, "EVIDENCE_RESPONSE")
    assert response_task.status == "ACCEPTED"

    uploaded = colleague.post(f"{base}/attachments", files={"file": ("batch-record.pdf", PDF, "application/pdf")})
    assert uploaded.status_code == 200, uploaded.text
    attachment_id = uploaded.json()["id"]
    wrong_type = colleague.post(f"{base}/attachments", files={"file": ("x.exe", b"MZ", "application/x-msdownload")})
    assert wrong_type.status_code == 415
    download = f"{base}/attachments/{attachment_id}"
    assert requester.get(download).status_code == 200 and requester.get(download).content == PDF
    assert colleague.get(download).status_code == 200
    viewer_download = org["viewer"][0].get(download)
    assert viewer_download.status_code == 403
    assert (
        org["viewer"][0].post(f"{base}/attachments", files={"file": ("a.pdf", PDF, "application/pdf")}).status_code
        == 403
    )

    assert colleague.post(f"{base}/respond", json={"note": "   "}).status_code == 422
    responded = colleague.post(f"{base}/respond", json={"note": "Batch record attached; cycle 121 C for 30 min"})
    assert responded.status_code == 200, responded.text
    assert responded.json()["status"] == "RECEIVED" and responded.json()["status_label"] == "Answered"
    assert responded.json()["responded_at"] and responded.json()["attachments_count"] == 1
    assert colleague.post(f"{base}/respond", json={"note": "Again"}).status_code == 409
    (response_task,) = _tasks(tenant_id, request_id, "EVIDENCE_RESPONSE")
    assert response_task.status == "COMPLETED" and response_task.completion_outcome == "REPLY_RECEIVED"
    (waiting,) = _tasks(tenant_id, request_id, "EVIDENCE_REQUEST")
    assert waiting.status == "COMPLETED"
    (review_task,) = _tasks(tenant_id, request_id, "EVIDENCE_REVIEW")
    assert review_task.status == "ASSIGNED" and str(review_task.assigned_user_id) == requester_id

    reviewed = requester.post(
        f"{base}/review",
        json={
            "accept": True,
            "review_status": "ACCEPTED",
            "relationship": "SUPPORTING",
            "evidence_type": "batch record",
        },
    )
    assert reviewed.status_code == 200, reviewed.text
    body = reviewed.json()
    assert body["status"] == "REVIEWED" and body["resolved_evidence"]["business_id"].startswith("EVD")
    assert body["review"]["accepted"] is True and body["reviewed_by_name"]
    evidence = body["evidence"]
    assert evidence["origin"] == "REQUEST" and evidence["request"] == {
        "id": request_id,
        "business_id": request["business_id"],
    }
    assert evidence["evidence"]["evidence_identifier"] == f"{request['business_id']}-1"
    assert evidence["evidence"]["evidence_type"] == "BATCH_RECORD"
    assert evidence["evidence"]["title"] == "Batch record for lot KS-5521"
    assert evidence["evidence"]["source_system"] == "MDARIX evidence request"
    assert evidence["evidence"]["has_document"] is True
    assert evidence["link"]["review_status"] == "ACCEPTED" and evidence["link"]["relationship"] == "SUPPORTING"
    assert requester.post(f"{base}/review", json={"accept": False, "reason": REASON}).status_code == 409
    (review_task,) = _tasks(tenant_id, request_id, "EVIDENCE_REVIEW")
    assert review_task.status == "COMPLETED" and review_task.completion_outcome == "EVIDENCE_ACCEPTED"
    evidence_id = evidence["evidence"]["id"]
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        stored = db.query(Evidence).filter(Evidence.id == uuid.UUID(evidence_id)).one()
        assert str(stored.investigation_id) == case["id"] and stored.content.startswith("Batch record attached")
        assert stored.fact_type == "source_fact" and stored.source_identifier == request["business_id"]

    item = _item(_inventory(requester, case["id"]), evidence_id)
    assert item["origin"] == "REQUEST" and item["link"]["review_status"] == "ACCEPTED"

    provenance = requester.get(f"/api/v1/investigations/{case['id']}/evidence/{evidence_id}/provenance").json()
    assert provenance["request"]["id"] == request_id and provenance["request"]["kind"] == "INTERNAL"
    assert provenance["request"]["requested_by_name"] and provenance["request"]["responded_at"]
    assert provenance["document"]["available"] is True and provenance["document"]["filename"] == "batch-record.pdf"
    assert provenance["document"]["size"] == len(PDF) and provenance["document"]["checksum"]
    assert [item["event_type"] for item in provenance["review_history"]] == ["LINKED", "REVIEWED"]

    detail = requester.get(base)
    assert detail.status_code == 200, detail.text
    detail = detail.json()
    assert [item["id"] for item in detail["attachments"]] == [attachment_id]
    actions = [item["action"] for item in detail["history"]]
    for action in (
        "EVIDENCE_REQUESTED",
        "EVIDENCE_REQUEST_ACKNOWLEDGED",
        "EVIDENCE_REQUEST_ATTACHMENT_UPLOADED",
        "EVIDENCE_REQUEST_RESPONDED",
        "EVIDENCE_REQUEST_REVIEWED",
    ):
        assert action in actions
    # Requests to colleagues stay out of the supplier screens and their endpoints.
    suppliers = requester.get("/api/v1/stage3/supplier-evidence-requests").json()
    assert request_id not in [item["id"] for item in suppliers]
    reply = requester.post(f"/api/v1/stage3/supplier-evidence-requests/{request_id}/reply", json={"note": "x"})
    assert reply.status_code == 404
    assert (
        requester.get(f"/api/v1/stage3/supplier-evidence-requests/{request_id}/attachments/{attachment_id}").status_code
        == 404
    )


def test_a_role_says_it_cannot_provide_and_requests_are_cancelled(org):
    tenant_id = org["tenant_id"]
    requester, requester_id = org["investigator"]
    risk, _ = org["risk"]
    colleague, _ = org["colleague"]
    case = _case(org)

    for role in ("APPROVER", "CUSTOMER_ADMIN", "NOBODY"):
        refused = _internal(case["id"], requester, recipient_role=role)
        assert refused.status_code == 422 and _code(refused) == "ROLE_NOT_ELIGIBLE", role
    made = _internal(case["id"], requester, recipient_role="risk reviewer", due_at=None, priority="LOW")
    assert made.status_code == 201, made.text
    request = made.json()
    assert request["recipient"]["role"] == "RISK_REVIEWER" and request["recipient"]["role_label"] == "Risk Reviewer"
    assert request["recipient"]["user"] is None
    (queued,) = _tasks(tenant_id, request["id"], "EVIDENCE_RESPONSE")
    assert queued.status == "NEW" and queued.assigned_user_id is None and queued.assigned_role == "RISK_REVIEWER"
    queue = risk.get("/api/v1/tasks", params={"view": "queue", "page_size": 200}).json()["items"]
    assert str(queued.id) in [item["id"] for item in queue]
    assert request["id"] in [
        item["id"] for item in risk.get("/api/v1/evidence-requests", params={"box": "received"}).json()["items"]
    ]

    base = f"/api/v1/evidence-requests/{request['id']}"
    assert colleague.post(f"{base}/cannot-provide", json={"reason": REASON}).status_code == 403
    assert risk.post(f"{base}/cannot-provide", json={"reason": "short"}).status_code == 422
    declined = risk.post(f"{base}/cannot-provide", json={"reason": "The cycle printouts were not kept for 2024"})
    assert declined.status_code == 200, declined.text
    assert declined.json()["status"] == "CANNOT_PROVIDE" and declined.json()["status_label"] == "Cannot provide"
    assert declined.json()["cannot_provide_reason"] == "The cycle printouts were not kept for 2024"
    (queued,) = _tasks(tenant_id, request["id"], "EVIDENCE_RESPONSE")
    assert queued.status == "COMPLETED" and queued.completion_outcome == "CANNOT_PROVIDE"
    (waiting,) = _tasks(tenant_id, request["id"], "EVIDENCE_REQUEST")
    assert waiting.status == "COMPLETED"
    (follow_up,) = _tasks(tenant_id, request["id"], "FOLLOW_UP")
    assert follow_up.is_return is True and str(follow_up.assigned_user_id) == requester_id
    assert follow_up.status == "ASSIGNED"
    cancel_late = requester.post(f"{base}/cancel", json={"reason": REASON})
    assert cancel_late.status_code == 409
    # Nothing was answered, so there is nothing to review.
    assert risk.post(f"{base}/review", json={"accept": False, "reason": REASON}).status_code == 409

    second = _internal(case["id"], requester, recipient_user_id=org["colleague"][1]).json()
    path = f"/api/v1/evidence-requests/{second['id']}/cancel"
    not_mine = colleague.post(path, json={"reason": REASON})
    assert not_mine.status_code == 403 and _code(not_mine) == "NOT_REQUESTER"
    assert requester.post(path, json={"reason": "short"}).status_code == 422
    cancelled = requester.post(path, json={"reason": REASON})
    assert cancelled.status_code == 200 and cancelled.json()["status"] == "CANCELLED"
    assert {task.status for task in _tasks(tenant_id, second["id"])} == {"CANCELLED"}
    assert colleague.post(f"/api/v1/evidence-requests/{second['id']}/respond", json={"note": "Late"}).status_code == 409

    # Whoever assigns work may withdraw someone else's request.
    third = _internal(case["id"], requester, recipient_user_id=org["colleague"][1]).json()
    by_reviewer = org["reviewer"][0].post(f"/api/v1/evidence-requests/{third['id']}/cancel", json={"reason": REASON})
    assert by_reviewer.status_code == 200 and by_reviewer.json()["status"] == "CANCELLED"
    assert "EVIDENCE_REQUEST_CANCELLED" in _audit_actions(tenant_id, third["id"])


def test_a_supplier_request_from_a_case_is_reviewed_into_evidence(org, monkeypatch):
    monkeypatch.setenv("MDARIX_SUPPLIER_REQUESTS_PER_DAY", "100000")
    monkeypatch.setenv("MDARIX_SUPPLIER_REQUESTS_PER_HOUR", "100000")
    tenant_id = org["tenant_id"]
    requester, requester_id = org["investigator"]
    case = _case(org)
    supplier_id = _supplier(tenant_id)
    path = f"/api/v1/investigations/{case['id']}/evidence-requests"
    body = {
        "kind": "SUPPLIER",
        "title": "Certificate of conformance for tubing lot T-88",
        "requested_items": ["Certificate of conformance"],
        "supplier_id": supplier_id,
        "recipient": "quality@supplier.example",
        "priority": "CRITICAL",
    }
    assert requester.post(path, json={**body, "title": "Visit https://evil.example now"}).status_code == 422
    unknown_supplier = requester.post(path, json={**body, "supplier_id": str(uuid.uuid4())})
    assert unknown_supplier.status_code == 404 and _code(unknown_supplier) == "SUPPLIER_NOT_FOUND"
    made = requester.post(path, json=body)
    assert made.status_code == 201, made.text
    request = made.json()
    assert request["kind"] == "SUPPLIER" and request["status"] in {"SENT", "PENDING_DELIVERY"}
    assert request["status_label"] == "Sent" and request["email_delivery"]
    assert request["priority"] == "CRITICAL" and request["recipient"]["email"] == "quality@supplier.example"
    assert request["recipient"]["supplier"]["id"] == supplier_id and request["recipient"]["supplier"]["name"]
    request_id = request["id"]
    (waiting,) = _tasks(tenant_id, request_id, "EVIDENCE_REQUEST")
    assert waiting.source_entity_type == "SupplierEvidenceRequest" and waiting.status == "WAITING"
    assert waiting.priority == "CRITICAL" and str(waiting.assigned_user_id) == requester_id
    actions = _audit_actions(tenant_id, request_id)
    assert "SUPPLIER_EVIDENCE_REQUEST_CREATED" in actions and "EVIDENCE_REQUESTED" in actions
    listed = requester.get("/api/v1/stage3/supplier-evidence-requests").json()
    assert request_id in [item["id"] for item in listed]
    # The address may also be sent as recipient_email (the name the case screen uses).
    aliased = {key: value for key, value in body.items() if key != "recipient"}
    second = requester.post(path, json={**aliased, "recipient_email": "qa@supplier.example", "title": "CoC"})
    assert second.status_code == 201, second.text
    assert second.json()["recipient"]["email"] == "qa@supplier.example" and second.json()["title"] == "CoC"

    base = f"/api/v1/evidence-requests/{request_id}"
    assert requester.post(f"{base}/acknowledge").status_code == 409
    assert requester.post(f"{base}/review", json={"accept": False, "reason": REASON}).status_code == 409
    reply = requester.post(
        f"/api/v1/stage3/supplier-evidence-requests/{request_id}/reply", json={"note": "Certificate CoC-88 received"}
    )
    assert reply.status_code == 200, reply.text
    (review_task,) = _tasks(tenant_id, request_id, "EVIDENCE_REVIEW")
    assert review_task.status == "ASSIGNED"
    answered = requester.get(base).json()
    assert answered["status"] == "REPLIED" and answered["status_label"] == "Answered"
    assert answered["response_note"] == "Certificate CoC-88 received" and answered["responded_at"]
    assert answered["replies"][0]["note"] == "Certificate CoC-88 received"

    assert requester.post(f"{base}/review", json={"accept": False}).status_code == 422
    reviewed = requester.post(
        f"{base}/review",
        json={
            "accept": True,
            "title": "Tubing lot T-88 certificate",
            "review_status": "ACCEPTED_WITH_LIMITATION",
            "relationship": "CONTEXTUAL",
            "limitation": "Covers the tubing only, not the connector",
        },
    )
    assert reviewed.status_code == 200, reviewed.text
    evidence = reviewed.json()["evidence"]
    assert reviewed.json()["status"] == "REVIEWED" and evidence["origin"] == "REQUEST"
    assert evidence["evidence"]["title"] == "Tubing lot T-88 certificate"
    assert evidence["evidence"]["evidence_type"] == "EVIDENCE_REQUEST_RESPONSE"
    assert evidence["link"]["limitation"] == "Covers the tubing only, not the connector"
    (review_task,) = _tasks(tenant_id, request_id, "EVIDENCE_REVIEW")
    assert review_task.status == "COMPLETED" and review_task.completion_outcome == "EVIDENCE_ACCEPTED"
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        stored = db.query(Evidence).filter(Evidence.id == uuid.UUID(evidence["evidence"]["id"])).one()
        assert stored.content == "Certificate CoC-88 received" and stored.document_ref is None
        row = db.query(SupplierEvidenceRequest).filter(SupplierEvidenceRequest.id == uuid.UUID(request_id)).one()
        assert row.resolved_evidence_id == stored.id and row.request_kind == "SUPPLIER"
        assert row.responded_at is not None


def test_a_rejected_answer_creates_no_evidence(org):
    tenant_id = org["tenant_id"]
    requester, _ = org["investigator"]
    colleague, colleague_id = org["colleague"]
    case = _case(org)
    request = _internal(case["id"], requester, recipient_user_id=colleague_id).json()
    base = f"/api/v1/evidence-requests/{request['id']}"
    assert colleague.post(f"{base}/respond", json={"note": "A photo of the wrong lot"}).status_code == 200
    before = _inventory(requester, case["id"])["counts"]["total"]
    # An evidence reviewer other than the requester may review the answer too.
    rejected = org["risk"][0].post(f"{base}/review", json={"accept": False, "reason": "The photo shows lot KS-5520"})
    assert rejected.status_code == 200, rejected.text
    assert rejected.json()["status"] == "REVIEWED" and rejected.json()["evidence"] is None
    assert rejected.json()["resolved_evidence"] is None and rejected.json()["review"]["accepted"] is False
    assert _inventory(requester, case["id"])["counts"]["total"] == before
    (review_task,) = _tasks(tenant_id, request["id"], "EVIDENCE_REVIEW")
    assert review_task.status == "COMPLETED" and review_task.completion_outcome == "RESPONSE_REJECTED"


# --------------------------------------------------------------------------------------- permissions and isolation


def test_permissions_and_other_organizations(org):
    tenant_id = org["tenant_id"]
    requester, _ = org["investigator"]
    viewer, _ = org["viewer"]
    case = _case(org)
    direct = _evidence(tenant_id, case_id=case["id"])
    other_case = _case(org)
    foreign_unknown = _unknown(tenant_id, other_case["id"])

    denied = _internal(case["id"], viewer, recipient_role="INVESTIGATOR")
    assert denied.status_code == 403 and _code(denied) == "PERMISSION_DENIED"
    wrong_unknown = _internal(case["id"], requester, recipient_role="INVESTIGATOR", unknown_id=foreign_unknown["id"])
    assert wrong_unknown.status_code == 404 and _code(wrong_unknown) == "UNKNOWN_NOT_FOUND"
    outsider, outsider_id = role_client("LEADER")  # the golden organization, with every permission
    not_colleague = _internal(case["id"], requester, recipient_user_id=outsider_id)
    assert not_colleague.status_code == 422 and _code(not_colleague) == "RECIPIENT_NOT_ELIGIBLE"
    past = _internal(case["id"], requester, recipient_role="INVESTIGATOR", due_at="2020-01-01T00:00:00Z")
    assert past.status_code == 422

    request = _internal(case["id"], requester, recipient_role="INVESTIGATOR").json()
    uploaded = requester.post(
        f"/api/v1/evidence-requests/{request['id']}/attachments",
        files={"file": ("record.pdf", PDF, "application/pdf")},
    )
    assert uploaded.status_code == 200, uploaded.text
    case_path = f"/api/v1/investigations/{case['id']}"
    request_path = f"/api/v1/evidence-requests/{request['id']}"
    review = {"review_status": "ACCEPTED", "relationship": "SUPPORTING"}
    for response, code in (
        (outsider.get(f"{case_path}/evidence-inventory"), "INVESTIGATION_NOT_FOUND"),
        (outsider.get(f"{case_path}/evidence/{direct}/provenance"), "INVESTIGATION_NOT_FOUND"),
        (outsider.post(f"{case_path}/evidence-links", json={"evidence_ids": [direct]}), "INVESTIGATION_NOT_FOUND"),
        (outsider.post(f"{case_path}/evidence/{direct}/review", json=review), "INVESTIGATION_NOT_FOUND"),
        (_internal(case["id"], outsider, recipient_role="INVESTIGATOR"), "INVESTIGATION_NOT_FOUND"),
        (outsider.get(request_path), "EVIDENCE_REQUEST_NOT_FOUND"),
        (outsider.post(f"{request_path}/acknowledge"), "EVIDENCE_REQUEST_NOT_FOUND"),
        (outsider.post(f"{request_path}/cancel", json={"reason": REASON}), "EVIDENCE_REQUEST_NOT_FOUND"),
        (
            outsider.post(f"{request_path}/review", json={"accept": False, "reason": REASON}),
            "EVIDENCE_REQUEST_NOT_FOUND",
        ),
        (outsider.get(f"{request_path}/attachments/{uploaded.json()['id']}"), "EVIDENCE_REQUEST_NOT_FOUND"),
        (requester.get(f"/api/v1/evidence-requests/{uuid.uuid4()}"), "EVIDENCE_REQUEST_NOT_FOUND"),
        (requester.get(f"/api/v1/investigations/{uuid.uuid4()}/evidence-inventory"), "INVESTIGATION_NOT_FOUND"),
    ):
        assert response.status_code == 404 and _code(response) == code, response.text
    listed = outsider.get("/api/v1/evidence-requests", params={"box": "all", "page_size": 200}).json()
    assert request["id"] not in [item["id"] for item in listed["items"]]
    assert requester.get("/api/v1/evidence-requests", params={"box": "inbox"}).status_code == 422
    # Reading is open to the organization; only the people on the request (or on cases) open its files.
    assert viewer.get(request_path).status_code == 200
    assert viewer.get(f"{request_path}/attachments/{uploaded.json()['id']}").status_code == 403
    assert org["colleague"][0].get(f"{request_path}/attachments/{uploaded.json()['id']}").status_code == 200
