"""Tenant security for non-admin users: suspension, self-reactivation, decision authority and audit export.

Each test reproduces a weakness found in the non-admin security audit and proves it is closed.
"""

import uuid
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from auth.durable import issue_reset
from backend.app.db.models.foundation import (
    AuthUser,
    Decision,
    Investigation,
    Product,
    Tenant,
    TenantMembership,
)
from backend.app.db.session import SessionLocal
from backend.app.main import app
from tests.test_customer_admin_account_security import PASSWORD, _client_for, _tenant, _user


def _set(model, row_id, **values):
    db = SessionLocal()
    try:
        db.query(model).filter(model.id == row_id).update(values)
        db.commit()
    finally:
        db.close()


@pytest.fixture
def org():
    """A fresh tenant with a viewer, two approvers and one investigation."""
    db = SessionLocal()
    try:
        tenant = _tenant(db, "SEC")
        viewer = _user(db, tenant, "Viewer", "sec-viewer")
        approver = _user(db, tenant, "Approver", "sec-approver")
        second_approver = _user(db, tenant, "Approver", "sec-approver-2")
        now = datetime.now(timezone.utc)
        product = Product(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            product_identifier=f"SEC-PRODUCT-{uuid.uuid4().hex[:8]}",
            name="Security Product",
            lifecycle_status="active",
            created_at=now,
            updated_at=now,
        )
        db.add(product)
        db.flush()
        investigation = Investigation(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            product_id=product.id,
            investigation_identifier=f"SEC-INV-{uuid.uuid4().hex[:8]}",
            investigation_question="Tenant security",
            status="open",
            opened_at=now,
            created_at=now,
            updated_at=now,
        )
        db.add(investigation)
        db.commit()
        world = {
            "tenant": tenant.id,
            "investigation": investigation.id,
            "clients": {
                "viewer": _client_for(db, viewer),
                "approver": _client_for(db, approver),
                "second_approver": _client_for(db, second_approver),
            },
            "ids": {"viewer": str(viewer.id), "approver": str(approver.id), "second_approver": str(second_approver.id)},
            "emails": {"viewer": viewer.username},
        }
        db.commit()
        return world
    finally:
        db.close()


def _decision(world, created_by: str):
    db = SessionLocal()
    try:
        now = datetime.now(timezone.utc)
        row = Decision(
            id=uuid.uuid4(),
            tenant_id=world["tenant"],
            investigation_id=world["investigation"],
            decision_identifier=f"SEC-{uuid.uuid4().hex[:10]}",
            decision_type="INVESTIGATION_REVIEW",
            disposition="REQUIRES_REVIEW",
            rationale="Tenant security",
            decision_status="REQUIRES_REVIEW",
            authorized_by_ref=created_by,
            updated_at=now,
            decision_timestamp=now,
            created_at=now,
        )
        db.add(row)
        db.commit()
        return row.id
    finally:
        db.close()


# --- Suspension -----------------------------------------------------------------------------------------------


def test_suspending_the_organization_blocks_existing_sessions_and_new_sign_ins(org):
    client = org["clients"]["viewer"]
    assert client.get("/api/v1/session/context").status_code == 200
    _set(Tenant, org["tenant"], status="SUSPENDED")
    try:
        blocked = client.get("/api/v1/session/context")
        assert blocked.status_code == 403
        assert blocked.json()["detail"]["code"] == "TENANT_ACCESS_SUSPENDED"
        assert client.get("/api/v1/auth/session").status_code == 403
        sign_in = TestClient(app).post(
            "/api/v1/auth/signin", json={"email": org["emails"]["viewer"], "password": PASSWORD}
        )
        assert sign_in.status_code == 403
    finally:
        _set(Tenant, org["tenant"], status="ACTIVE")
    assert client.get("/api/v1/session/context").status_code == 200


def test_suspending_a_membership_blocks_that_user_only(org):
    db = SessionLocal()
    try:
        membership = (
            db.query(TenantMembership)
            .filter(
                TenantMembership.user_id == uuid.UUID(org["ids"]["viewer"]), TenantMembership.tenant_id == org["tenant"]
            )
            .one()
        )
        membership.status = "SUSPENDED"
        db.commit()
    finally:
        db.close()
    blocked = org["clients"]["viewer"].get("/api/v1/session/context")
    assert blocked.status_code == 403
    assert blocked.json()["detail"]["code"] == "MEMBERSHIP_SUSPENDED"
    assert org["clients"]["approver"].get("/api/v1/session/context").status_code == 200


def test_a_suspended_user_cannot_reactivate_themselves_with_a_password_reset(org):
    email = org["emails"]["viewer"]
    db = SessionLocal()
    try:
        # A reset link issued before the suspension must not lift it.
        token = issue_reset(db, uuid.UUID(org["ids"]["viewer"]), org["tenant"])
        db.commit()
    finally:
        db.close()
    _set(AuthUser, uuid.UUID(org["ids"]["viewer"]), status="SUSPENDED")
    anonymous = TestClient(app)
    forgot = anonymous.post("/api/v1/auth/forgot-password", json={"email": email})
    assert forgot.status_code == 200
    assert forgot.json()["email_delivery"] == "NOT_SENT"
    assert not forgot.json().get("development_token")
    reset = anonymous.post("/api/v1/auth/reset-password", json={"token": token, "password": "A brand new password 456"})
    assert reset.status_code >= 400
    db = SessionLocal()
    try:
        assert db.query(AuthUser).filter(AuthUser.id == uuid.UUID(org["ids"]["viewer"])).one().status == "SUSPENDED"
    finally:
        db.close()


# --- Decision authority -------------------------------------------------------------------------------------


def test_decision_author_is_the_signed_in_user_not_a_name_in_the_request(org, monkeypatch):
    from backend.app import decision_router
    from decision_center.service import DecisionCenterError

    captured = {}

    def fake_create(db, tenant_id, investigation_id, request):
        captured["author"] = request.authorized_by_ref
        raise DecisionCenterError("CAPTURED", "stop after capturing the request")

    monkeypatch.setattr(decision_router.service, "create_decision", fake_create)
    attempt = {
        "selected_action": decision_router.OPTIONS[0],
        "rationale": "Spoofing attempt",
        "authorized_by_ref": "qa-director@elsewhere",
    }
    # A read-only Viewer may not create decisions at all.
    refused = org["clients"]["viewer"].post(f"/api/v1/investigations/{org['investigation']}/decisions", json=attempt)
    assert refused.status_code == 403 and refused.json()["detail"]["code"] == "PERMISSION_DENIED"
    response = org["clients"]["approver"].post(f"/api/v1/investigations/{org['investigation']}/decisions", json=attempt)
    assert response.status_code == 400
    assert captured["author"] == org["ids"]["approver"]


def test_a_viewer_cannot_approve_through_a_review_or_a_signature(org):
    decision_id = _decision(org, created_by=org["ids"]["approver"])
    viewer = org["clients"]["viewer"]
    # Touching governance used to grant the Viewer role approval authority on the spot.
    assert viewer.get("/api/v1/governance/effective-access").status_code == 200
    review = viewer.post(
        f"/api/v1/investigations/decisions/{decision_id}/reviews",
        json={"disposition": "APPROVED", "reviewer_ref": "Chief Quality Officer"},
    )
    assert review.status_code == 403
    assert review.json()["detail"]["code"] == "APPROVAL_AUTHORITY_DENIED"
    db = SessionLocal()
    try:
        decision = db.query(Decision).filter(Decision.id == decision_id).one()
        assert decision.decision_status == "REQUIRES_REVIEW"
        version = decision.updated_at.isoformat()
    finally:
        db.close()
    sign = viewer.post(
        f"/api/v1/governance/decisions/{decision_id}/sign",
        json={"decision": "APPROVE", "remarks": "Viewer", "password": PASSWORD, "object_version": version},
    )
    assert sign.status_code == 403
    assert sign.json()["detail"]["code"] == "APPROVAL_AUTHORITY_DENIED"


def test_nobody_approves_their_own_decision_but_another_approver_can(org):
    decision_id = _decision(org, created_by=org["ids"]["approver"])
    own = org["clients"]["approver"].post(
        f"/api/v1/investigations/decisions/{decision_id}/reviews", json={"disposition": "APPROVED"}
    )
    assert own.status_code == 403
    assert own.json()["detail"]["code"] == "SOD_DENIED"
    other = org["clients"]["second_approver"].post(
        f"/api/v1/investigations/decisions/{decision_id}/reviews", json={"disposition": "APPROVED"}
    )
    assert other.status_code == 200, other.text
    assert other.json()["reviewer_ref"] == org["ids"]["second_approver"]


def test_requesting_more_evidence_does_not_need_approval_authority(org):
    decision_id = _decision(org, created_by=org["ids"]["approver"])
    response = org["clients"]["viewer"].post(
        f"/api/v1/investigations/decisions/{decision_id}/reviews",
        json={"disposition": "REQUIRES_ADDITIONAL_EVIDENCE", "comments": "Need the lot records"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["reviewer_ref"] == org["ids"]["viewer"]


# --- Audit export and entitlements ---------------------------------------------------------------------------


def test_a_viewer_cannot_export_the_audit_trail(org):
    response = org["clients"]["viewer"].get("/api/v1/stage3/compliance-report", params={"output_format": "JSON"})
    assert response.status_code == 403


def test_entitlement_check_answers_instead_of_crashing(org):
    client = org["clients"]["viewer"]
    client.get("/api/v1/governance/effective-access")  # the demo bootstrap entitles the tenant
    response = client.get("/api/v1/me/entitlements/DECISION_CENTER_SIGNATURES")
    assert response.status_code == 200, response.text
    assert set(response.json()) == {"feature", "entitled", "limits"}
