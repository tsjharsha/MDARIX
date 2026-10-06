"""Managing an investigation: edit its question, assign it, close and reopen it, each with a reason on record."""

import uuid
from datetime import datetime, timezone

from backend.app.db.models.foundation import AuditEvent, Decision, HumanReview, Product, Tenant
from backend.app.db.session import SessionLocal
from backend.app.db.tenant_scope import bind_system
from tests.test_business_permissions import _client_with_role

REASON = "Reason recorded for the audit trail"


def _open_case(user) -> str:
    with SessionLocal() as db:
        bind_system(db, "test: product")
        tenant = db.query(Tenant).filter(Tenant.tenant_key == "ACME_CARE_SYNTHETIC").first()
        product = db.query(Product.id).filter(Product.tenant_id == tenant.id).first()[0]
    made = user.post(
        "/api/v1/investigations",
        json={"product_id": str(product), "investigation_question": "Why do alarms rise after release B?"},
    )
    assert made.status_code == 201, made.text
    return made.json()["id"]


def test_edit_assign_close_and_reopen():
    lead = _client_with_role("INVESTIGATOR")
    case = _open_case(lead)
    path = f"/api/v1/investigations/{case}"
    edited = lead.patch(
        path, json={"reason": REASON, "investigation_question": "Why do occlusion alarms rise after release B?"}
    )
    assert edited.status_code == 200 and edited.json()["investigation_question"].startswith("Why do occlusion")
    assignees = lead.get("/api/v1/investigation-assignees").json()
    # Names and identifiers only, never contact details.
    assert assignees and all(set(person) == {"id", "business_id", "display_name"} for person in assignees)
    colleague = assignees[0]
    assigned = lead.patch(path, json={"reason": REASON, "assignee_id": colleague["id"]})
    assert assigned.status_code == 200 and assigned.json()["owner_ref"]
    assert lead.patch(path, json={"reason": REASON, "unassign": True}).json()["owner_ref"] is None
    closed = lead.patch(path, json={"reason": REASON, "status": "closed"})
    assert closed.status_code == 200 and closed.json()["status"] == "closed" and closed.json()["closed_at"]
    frozen = lead.patch(path, json={"reason": REASON, "investigation_question": "Changing a closed case should fail"})
    assert frozen.status_code == 409 and frozen.json()["detail"]["code"] == "INVESTIGATION_CLOSED"
    reopened = lead.patch(path, json={"reason": REASON, "status": "open"})
    assert reopened.status_code == 200 and reopened.json()["status"] == "open" and reopened.json()["closed_at"] is None
    with SessionLocal() as db:
        bind_system(db, "test: audit")
        actions = [row[0] for row in db.query(AuditEvent.action).filter(AuditEvent.entity_id == uuid.UUID(case)).all()]
    assert {"INVESTIGATION_OPENED", "INVESTIGATION_UPDATED", "INVESTIGATION_CLOSED", "INVESTIGATION_REOPENED"} <= set(
        actions
    )


def test_the_rules_around_managing_a_case():
    lead = _client_with_role("INVESTIGATOR")
    case = _open_case(lead)
    path = f"/api/v1/investigations/{case}"
    assert _client_with_role("VIEWER").patch(path, json={"reason": REASON, "status": "closed"}).status_code == 403
    assert lead.patch(path, json={"reason": "short", "status": "closed"}).status_code == 422
    assert (
        lead.patch(f"/api/v1/investigations/{uuid.uuid4()}", json={"reason": REASON, "status": "closed"}).status_code
        == 404
    )
    # Only colleagues who may work on cases: not a viewer, not someone from another organization.
    viewer = _client_with_role("VIEWER")
    viewer_id = viewer.get("/api/v1/session/context").json()["user_id"]
    refused = lead.patch(path, json={"reason": REASON, "assignee_id": viewer_id})
    assert refused.status_code == 422 and refused.json()["detail"]["code"] == "ASSIGNEE_NOT_ELIGIBLE"
    assert lead.patch(path, json={"reason": REASON, "assignee_id": str(uuid.uuid4())}).status_code == 422
    # A decision waiting for its human review keeps the case open.
    with SessionLocal() as db:
        bind_system(db, "test: pending decision")
        now = datetime.now(timezone.utc)
        decision = Decision(
            id=uuid.uuid4(),
            tenant_id=db.query(Tenant.id).filter(Tenant.tenant_key == "ACME_CARE_SYNTHETIC").first()[0],
            investigation_id=uuid.UUID(case),
            decision_identifier=f"PEND-{uuid.uuid4().hex[:8]}",
            decision_type="DISPOSITION",
            disposition="REQUIRES_REVIEW",
            rationale="Pending",
            decision_status="REQUIRES_REVIEW",
            authorized_by_ref="x",
            updated_at=now,
            decision_timestamp=now,
            created_at=now,
        )
        db.add(decision)
        db.commit()
        decision_id = decision.id
    blocked = lead.patch(path, json={"reason": REASON, "status": "closed"})
    assert blocked.status_code == 409 and blocked.json()["detail"]["code"] == "DECISIONS_AWAITING_REVIEW"
    with SessionLocal() as db:
        bind_system(db, "test cleanup")
        db.query(HumanReview).filter(HumanReview.decision_id == decision_id).delete(synchronize_session=False)
        db.query(Decision).filter(Decision.id == decision_id).delete(synchronize_session=False)
        db.commit()


def test_assigning_a_case_to_a_colleague_queues_one_email_with_ids_only():
    from backend.app.db.models.stage2 import OutboxEvent
    from backend.app.notifications import INVESTIGATION_ASSIGNED

    lead = _client_with_role("INVESTIGATOR")
    case = _open_case(lead)
    colleague = lead.get("/api/v1/investigation-assignees").json()[0]
    assigned = lead.patch(f"/api/v1/investigations/{case}", json={"reason": REASON, "assignee_id": colleague["id"]})
    assert assigned.status_code == 200, assigned.text
    with SessionLocal() as db:
        bind_system(db, "test: the assignment notification")
        events = (
            db.query(OutboxEvent)
            .filter(OutboxEvent.event_name == INVESTIGATION_ASSIGNED, OutboxEvent.aggregate_id == uuid.UUID(case))
            .all()
        )
        assert len(events) == 1
        payload = events[0].payload
        assert payload["assignee_user_id"] == colleague["id"] and "@" not in str(payload)
        for event in events:
            db.delete(event)
        db.commit()
