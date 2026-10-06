import uuid
from contextlib import contextmanager
from datetime import datetime, timezone

from fastapi.testclient import TestClient
from sqlalchemy import text

from backend.app.db.session import engine
from backend.app.main import app
from decision_center.service import DecisionCenterService
from decision_center.schemas import DecisionContextRequest
from tests.test_customer_admin_account_security import _client_for, _user

client = TestClient(app)
service = DecisionCenterService()


def primary_investigation():
    with engine.connect() as conn:
        return conn.execute(
            text("SELECT id, tenant_id, product_id FROM investigations WHERE investigation_identifier='INV-001'")
        ).one()


def test_decision_context_preserves_upstream_semantics_and_readiness():
    investigation, tenant_id, product_id = primary_investigation()
    context = service.context(
        __import__("backend.app.db.session", fromlist=["SessionLocal"]).SessionLocal(),
        tenant_id,
        investigation,
        DecisionContextRequest(),
    )
    assert context["investigation"]["identifier"] == "INV-001"
    assert context["product_context"]["product_id"] == str(product_id)
    assert context["readiness"]["state"] in {
        "INSUFFICIENT_EVIDENCE",
        "MATERIAL_UNKNOWNS_REMAIN",
        "CONTRADICTORY_EVIDENCE",
        "SUFFICIENT_FOR_REVIEW",
    }
    assert context["guardrails"]["human_decision_required"] is True
    assert context["guardrails"]["ground_truth_used"] is False


def test_decision_context_api_and_temporal_context():
    investigation, _, _ = primary_investigation()
    response = client.get(
        f"/api/v1/investigations/{investigation}/decision-context",
        params={"temporal_mode": "event", "as_of": "2026-02-15T00:00:00Z"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["temporal_context"]["mode"] == "event"
    assert payload["guardrails"]["ai_advisory_is_not_decision"] is True


def test_advisory_cannot_finalize_decision():
    investigation, _, _ = primary_investigation()
    response = client.post(
        f"/api/v1/investigations/{investigation}/decision-advisory", json={"temporal_mode": "current"}
    )
    assert response.status_code == 200
    assert response.json()["advisory"]["human_authority_required"] is True
    assert "decision_status" not in response.json()["advisory"]


@contextmanager
def _role_may_approve(tenant_id, role_name: str):
    """Temporarily give a role approval authority (fresh databases grant it to Approver only)."""
    from backend.app.db.models.foundation import ApprovalAuthority, Tenant
    from backend.app.db.session import SessionLocal
    from backend.app.governance_router import bootstrap

    db = SessionLocal()
    now = datetime.now(timezone.utc)
    added = None
    try:
        bootstrap(db, db.query(Tenant).filter(Tenant.id == tenant_id).one())
        existing = (
            db.query(ApprovalAuthority)
            .filter_by(
                tenant_id=tenant_id,
                role_name=role_name,
                object_type="Decision",
                decision_type="INVESTIGATION_REVIEW",
                authority="AUTHORIZED",
                status="ACTIVE",
            )
            .first()
        )
        if existing is None:
            added = ApprovalAuthority(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                role_name=role_name,
                object_type="Decision",
                decision_type="INVESTIGATION_REVIEW",
                authority="AUTHORIZED",
                version="test",
                status="ACTIVE",
                effective_from=now,
                created_at=now,
                updated_at=now,
            )
            db.add(added)
        db.commit()
        yield
    finally:
        if added is not None:
            db.delete(added)
            db.commit()
        db.close()


def test_human_decision_requires_rationale_and_review():
    from backend.app.db.models.foundation import Tenant
    from backend.app.db.session import SessionLocal

    investigation, tenant_id, _ = primary_investigation()
    missing = client.post(
        f"/api/v1/investigations/{investigation}/decisions",
        json={"selected_action": "NO_DECISION_YET", "authorized_by_ref": "reviewer", "temporal_mode": "current"},
    )
    assert missing.status_code == 422
    db = SessionLocal()
    try:
        tenant = db.query(Tenant).filter(Tenant.id == tenant_id).one()
        author = _client_for(db, _user(db, tenant, "Approver", "day15-author"))
        approver = _client_for(db, _user(db, tenant, "Approver", "day15-approver"))
        db.commit()
    finally:
        db.close()
    created = author.post(
        f"/api/v1/investigations/{investigation}/decisions",
        json={
            "selected_action": "NO_DECISION_YET",
            "rationale": "Material unknowns remain; additional evidence is required.",
            "temporal_mode": "current",
        },
    )
    assert created.status_code == 200, created.text
    decision_id = created.json()["id"]
    assert created.json()["decision_status"] == "REQUIRES_REVIEW"
    # The author cannot approve their own decision (segregation of duties), although their role may approve...
    own = author.post(
        f"/api/v1/investigations/decisions/{decision_id}/reviews",
        json={"disposition": "APPROVED", "comments": "Human review completed."},
    )
    assert own.status_code == 403
    assert own.json()["detail"]["code"] == "SOD_DENIED"
    # ...an administrator never signs, even with an approval authority naming their role...
    with _role_may_approve(tenant_id, "Administrator"):
        admin = client.post(
            f"/api/v1/investigations/decisions/{decision_id}/reviews",
            json={"disposition": "APPROVED", "comments": "Human review completed."},
        )
    assert admin.status_code == 403 and admin.json()["detail"]["code"] == "ADMINISTRATOR_CANNOT_SIGN"
    # ...and a different user holding approval authority can.
    review = approver.post(
        f"/api/v1/investigations/decisions/{decision_id}/reviews",
        json={"disposition": "APPROVED", "comments": "Human review completed."},
    )
    assert review.status_code == 200, review.text
    assert client.get(f"/api/v1/investigations/decisions/{decision_id}").json()["decision_status"] == "DECIDED"


def test_invalid_investigation_and_tenant_scoping():
    invalid = client.get(f"/api/v1/investigations/{uuid.uuid4()}/decision-context")
    assert invalid.status_code == 404


def test_a_new_decision_tells_the_approvers_it_awaits_them():
    from backend.app.db.models.stage2 import OutboxEvent
    from backend.app.db.session import SessionLocal
    from backend.app.db.tenant_scope import bind_system
    from backend.app.notifications import DECISION_REVIEW_PENDING

    investigation, _, _ = primary_investigation()
    created = client.post(
        f"/api/v1/investigations/{investigation}/decisions",
        json={
            "selected_action": "NO_DECISION_YET",
            "rationale": "Comparative testing is still missing; approvers must review.",
            "temporal_mode": "current",
        },
    )
    assert created.status_code == 200, created.text
    decision_id = uuid.UUID(created.json()["id"])
    with SessionLocal() as db:
        bind_system(db, "test: the review-pending notification")
        events = (
            db.query(OutboxEvent)
            .filter(OutboxEvent.event_name == DECISION_REVIEW_PENDING, OutboxEvent.aggregate_id == decision_id)
            .all()
        )
        assert len(events) == 1 and "@" not in str(events[0].payload)
        for event in events:
            db.delete(event)
        db.commit()
