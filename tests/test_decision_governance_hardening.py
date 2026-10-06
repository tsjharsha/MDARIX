"""Decision governance: who may review, approve and sign; signed decisions are closed; no hidden demo plan."""

import uuid
from datetime import datetime, timezone

import pytest

from backend.app.db.models.foundation import (
    HumanReview,
    Decision,
    Investigation,
    PlanDefinition,
    Tenant,
    TenantPlanAssignment,
)
from backend.app.db.session import SessionLocal
from backend.app.db.tenant_scope import bind_system
from tests.test_business_permissions import _client_with_role


@pytest.fixture
def decision():
    with SessionLocal() as db:
        bind_system(db, "test: decision")
        tenant = db.query(Tenant).filter(Tenant.tenant_key == "ACME_CARE_SYNTHETIC").first()
        investigation = db.query(Investigation).filter(Investigation.tenant_id == tenant.id).first()
        now = datetime.now(timezone.utc)
        row = Decision(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            investigation_id=investigation.id,
            decision_identifier=f"GOV-{uuid.uuid4().hex[:10]}",
            decision_type="INVESTIGATION_REVIEW",
            disposition="REQUIRES_REVIEW",
            rationale="Governance test",
            decision_status="REQUIRES_REVIEW",
            authorized_by_ref="someone-else",
            updated_at=now,
            decision_timestamp=now,
            created_at=now,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        yield row
        db.query(HumanReview).filter(HumanReview.decision_id == row.id).delete(synchronize_session=False)
        db.query(Decision).filter(Decision.id == row.id).delete(synchronize_session=False)
        db.commit()


def _review(client, decision, disposition):
    return client.post(
        f"/api/v1/investigations/decisions/{decision.id}/reviews", json={"disposition": disposition, "comments": "test"}
    )


def test_a_viewer_cannot_review_a_decision(decision):
    refused = _review(_client_with_role("VIEWER"), decision, "REJECTED")
    assert refused.status_code == 403 and refused.json()["detail"]["code"] == "PERMISSION_DENIED"


@pytest.mark.parametrize("stored_role", ["APPROVER", "Approver", "approver", "LEADER"])
def test_approvers_and_leaders_may_approve_whatever_the_case_of_the_stored_role(stored_role, decision):
    approved = _review(_client_with_role(stored_role), decision, "APPROVED")
    assert approved.status_code == 200, approved.text


def test_an_investigator_still_cannot_approve(decision):
    refused = _review(_client_with_role("INVESTIGATOR"), decision, "APPROVED")
    assert refused.status_code == 403 and refused.json()["detail"]["code"] == "APPROVAL_AUTHORITY_DENIED"


def test_a_signed_decision_cannot_be_reviewed_or_reopened(decision):
    with SessionLocal() as db:
        bind_system(db, "test: mark signed")
        db.query(Decision).filter(Decision.id == decision.id).update({Decision.decision_status: "APPROVED"})
        db.commit()
    for role, disposition in (("REVIEWER", "NEEDS_MORE_EVIDENCE"), ("APPROVER", "APPROVED")):
        locked = _review(_client_with_role(role), decision, disposition)
        assert locked.status_code == 409 and locked.json()["detail"]["code"] == "DECISION_LOCKED"


def test_signing_never_assigns_the_synthetic_demo_plan(decision):
    client = _client_with_role("APPROVER")
    tenant_id = decision.tenant_id

    def demo_assignments():
        with SessionLocal() as db:
            bind_system(db, "test: count plans")
            return (
                db.query(TenantPlanAssignment)
                .join(PlanDefinition, PlanDefinition.id == TenantPlanAssignment.plan_id)
                .filter(TenantPlanAssignment.tenant_id == tenant_id, PlanDefinition.code == "R1_GOVERNANCE_DEMO")
                .count()
            )

    before = demo_assignments()
    client.post(
        f"/api/v1/governance/decisions/{decision.id}/sign",
        json={"decision": "APPROVE", "remarks": "x", "password": "wrong-password-x", "object_version": "x"},
    )
    client.get("/api/v1/governance/effective-access")
    assert demo_assignments() == before


def test_controlled_signatures_are_part_of_every_active_plan_unless_switched_off():
    from backend.app.access.plan_features import plan_includes

    with SessionLocal() as db:
        bind_system(db, "test: plan features")
        tenant = db.query(Tenant).filter(Tenant.tenant_key == "ACME_CARE_SYNTHETIC").first()
        assert plan_includes(db, tenant.id, "DECISION_CENTER_SIGNATURES") is True
        assert plan_includes(db, tenant.id, "ASK_MDARIX") is True
        assert plan_includes(db, uuid.uuid4(), "DECISION_CENTER_SIGNATURES") is False  # no plan, no features


def test_a_signature_accepts_the_current_version_however_it_is_written_and_nothing_else():
    from datetime import timedelta

    from backend.app.governance_router import same_object_version

    current = datetime(2026, 10, 6, 9, 30, 15, 123456, tzinfo=timezone.utc)
    assert same_object_version(current.isoformat(), current)
    assert same_object_version("2026-10-06T09:30:15.123456Z", current)
    assert same_object_version("2026-10-06T11:30:15.123456+02:00", current)
    # Any other moment, even a microsecond apart, is stale; so is text that is not a time.
    assert not same_object_version((current + timedelta(microseconds=1)).isoformat(), current)
    assert not same_object_version("2026-10-06T09:30:15.123Z", current)
    assert not same_object_version("x", current)
    assert not same_object_version("", current)


def test_verification_status_is_invalid_when_any_signature_fails():
    from backend.app.governance_router import verification_status

    assert verification_status([]) == "NOT_SIGNED"
    assert verification_status([{"valid": True}, {"valid": True}]) == "VALID"
    assert verification_status([{"valid": True}, {"valid": False}]) == "INVALID"
