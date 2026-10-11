"""Focused Day 23 security checks that do not require a browser or secrets."""

import hashlib
import json

import pytest
import uuid
from datetime import datetime, timezone
from fastapi.testclient import TestClient

from auth.service import _hash
from auth.durable import consume, issue_reset, new_session
from backend.app.main import app
from backend.app.governance_router import bootstrap
from backend.app.db.session import SessionLocal
from backend.app.db.models.foundation import (
    ApprovalAuthority,
    AuthUser,
    Decision,
    FeatureEntitlement,
    Investigation,
    Product,
    SignedApprovalRecord,
    Tenant,
    TenantMembership,
)
from backend.app.db.models.customer_lifecycle import Customer


def _legacy_user():
    from tests.conftest import _ensure_legacy_user

    db = SessionLocal()
    try:
        tenant = db.query(Tenant).filter(Tenant.tenant_key == "ACME_CARE_SYNTHETIC").first() or db.query(Tenant).first()
        user = _ensure_legacy_user(db, tenant)
        return user.id, user.tenant_id
    finally:
        db.close()


def test_stored_password_is_a_hash_not_the_password():
    stored = _hash("Correct current password 123")
    assert "Correct current password 123" not in stored


def test_unknown_or_forged_session_is_refused():
    client = TestClient(app)
    client.cookies.set("mdarix_session", "not-a-session")
    assert client.get("/api/v1/me/context").status_code == 401


def test_signed_content_fingerprint_changes_on_material_change():
    original = {"object_id": "decision-1", "object_version": "v3", "decision": "APPROVE", "remarks": "Reviewed"}
    changed = {**original, "object_version": "v4"}
    first = hashlib.sha256(json.dumps(original, sort_keys=True).encode()).hexdigest()
    second = hashlib.sha256(json.dumps(changed, sort_keys=True).encode()).hexdigest()
    assert first != second


def test_replay_token_cannot_be_reused():
    user_id, tenant_id = _legacy_user()
    db = SessionLocal()
    try:
        raw = issue_reset(db, user_id, tenant_id)
        assert consume(db, raw, "reset") == str(user_id)
        with pytest.raises(ValueError, match="INVALID_RESET_TOKEN"):
            consume(db, raw, "reset")
    finally:
        db.close()


def test_a_new_reset_link_replaces_the_earlier_one():
    user_id, tenant_id = _legacy_user()
    db = SessionLocal()
    try:
        first = issue_reset(db, user_id, tenant_id)
        second = issue_reset(db, user_id, tenant_id)
        with pytest.raises(ValueError):
            consume(db, first, "reset")
        assert consume(db, second, "reset") == str(user_id)
    finally:
        db.close()


def test_password_is_not_in_signin_or_reset_responses():
    _legacy_user()
    client = TestClient(app)
    signin = client.post(
        "/api/v1/auth/signin",
        json={"email": "legacy-test-auth@synthetic.invalid", "password": "LegacyTestPassword123!"},
    )
    assert signin.status_code == 200, signin.text
    assert "password" not in signin.text.lower()
    reset = client.post("/api/v1/auth/forgot-password", json={"email": "legacy-test-auth@synthetic.invalid"})
    assert "LegacyTestPassword123!" not in reset.text


def _client(email, tenant_id):
    db = SessionLocal()
    now = datetime.now(timezone.utc)
    # The governance bootstrap grants approval authority to the Approver role
    # only (never to read-only Viewers); these signers are Approvers.
    user = AuthUser(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        username=email,
        display_name=email.split("@")[0],
        company="Day23",
        password_hash=_hash("Correct current password 123"),
        role="Approver",
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
    persisted_user_id = str(user.id)
    token = new_session(db, user.id, tenant_id)
    db.close()
    client = TestClient(app)
    client.cookies.set("mdarix_session", token)
    client.test_user_id = persisted_user_id
    return client


def _decision(db, tenant_id, investigation, creator):
    now = datetime.now(timezone.utc)
    row = Decision(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        investigation_id=investigation.id,
        decision_identifier=f"D23-{uuid.uuid4().hex[:10]}",
        decision_type="INVESTIGATION_REVIEW",
        disposition="REQUIRES_REVIEW",
        rationale="Day23 API matrix",
        decision_status="REQUIRES_REVIEW",
        authorized_by_ref=creator,
        updated_at=now,
        decision_timestamp=now,
        created_at=now,
    )
    db.add(row)
    db.commit()
    return row


def test_api_signing_security_matrix():
    db = SessionLocal()
    tenant = db.query(Tenant).filter(Tenant.status == "active").first()
    if tenant is None:
        now = datetime.now(timezone.utc)
        customer = Customer(
            id=uuid.uuid4(),
            customer_identifier=f"D23-BASE-CUSTOMER-{uuid.uuid4().hex[:8]}",
            legal_name="Day 23 Base Customer",
            display_name="Day 23 Base Customer",
            customer_type="DESIGN_PARTNER",
            country="US",
            lifecycle_status="ACTIVE",
            created_at=now,
            updated_at=now,
        )
        db.add(customer)
        db.flush()
        tenant = Tenant(
            id=uuid.uuid4(),
            customer_id=customer.id,
            tenant_key=f"D23-BASE-{uuid.uuid4().hex[:8]}",
            tenant_identifier=f"D23-BASE-{uuid.uuid4().hex[:8]}",
            name="Day 23 Base Tenant",
            display_name="Day 23 Base Tenant",
            tenant_slug=f"d23-base-{uuid.uuid4().hex[:8]}",
            tenant_type="STANDARD",
            deployment_model="SHARED",
            primary_region="US",
            residency_region="US",
            cross_border_processing_allowed=False,
            provisioning_status="PROVISIONED",
            status="ACTIVE",
            lock_version=1,
            created_at=now,
            updated_at=now,
        )
        db.add(tenant)
        db.flush()
        product = Product(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            product_identifier=f"D23-BASE-PRODUCT-{uuid.uuid4().hex[:8]}",
            name="Day 23 Base Product",
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
            investigation_identifier=f"D23-BASE-INV-{uuid.uuid4().hex[:8]}",
            investigation_question="Day 23 governance baseline",
            status="open",
            opened_at=now,
            created_at=now,
            updated_at=now,
        )
        db.add(investigation)
        db.commit()
    else:
        investigation = db.query(Investigation).filter_by(tenant_id=tenant.id).first()
        if investigation is None:
            product = Product(
                id=uuid.uuid4(),
                tenant_id=tenant.id,
                product_identifier=f"D23-BASE-PRODUCT-{uuid.uuid4().hex[:8]}",
                name="Day 23 Base Product",
                lifecycle_status="active",
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
            db.add(product)
            db.flush()
            investigation = Investigation(
                id=uuid.uuid4(),
                tenant_id=tenant.id,
                product_id=product.id,
                investigation_identifier=f"D23-BASE-INV-{uuid.uuid4().hex[:8]}",
                investigation_question="Day 23 governance baseline",
                status="open",
                opened_at=datetime.now(timezone.utc),
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
            db.add(investigation)
            db.commit()
    bootstrap(db, tenant)
    db.commit()
    ids = []
    approver = f"approver-{uuid.uuid4().hex[:8]}@example.com"
    creator = f"creator-{uuid.uuid4().hex[:8]}@example.com"
    approver_client = _client(approver, tenant.id)
    creator_client = _client(creator, tenant.id)
    try:
        assert approver_client.get("/api/v1/governance/effective-access").status_code == 200
        first = _decision(db, tenant.id, investigation, creator)
        ids.append(first.id)
        version = first.updated_at.isoformat()
        wrong = approver_client.post(
            f"/api/v1/governance/decisions/{first.id}/sign",
            json={
                "decision": "APPROVE",
                "remarks": "Reviewed",
                "password": "wrong password",
                "object_version": version,
            },
        )
        assert wrong.status_code == 403
        db.expire_all()
        assert db.query(SignedApprovalRecord).filter_by(object_id=first.id).count() == 0
        signed = approver_client.post(
            f"/api/v1/governance/decisions/{first.id}/sign",
            json={
                "decision": "APPROVE",
                "remarks": "Reviewed",
                "password": "Correct current password 123",
                "object_version": version,
            },
        )
        assert signed.status_code == 200
        replay = approver_client.post(
            f"/api/v1/governance/decisions/{first.id}/sign",
            json={
                "decision": "APPROVE",
                "remarks": "Reviewed",
                "password": "Correct current password 123",
                "object_version": version,
            },
        )
        assert replay.status_code == 409
        db.expire_all()
        assert db.query(SignedApprovalRecord).filter_by(object_id=first.id).count() == 1
        own = _decision(db, tenant.id, investigation, creator_client.test_user_id)
        ids.append(own.id)
        own_result = creator_client.post(
            f"/api/v1/governance/decisions/{own.id}/sign",
            json={
                "decision": "APPROVE",
                "remarks": "Self",
                "password": "Correct current password 123",
                "object_version": own.updated_at.isoformat(),
            },
        )
        assert own_result.status_code == 403 and own_result.json()["detail"]["code"] == "SOD_DENIED"
        stale = _decision(db, tenant.id, investigation, creator)
        ids.append(stale.id)
        stale_version = stale.updated_at.isoformat()
        changed = approver_client.post(
            f"/api/v1/governance/decisions/{stale.id}/material-change",
            json={"change_summary": "Material conclusion updated", "expected_updated_at": stale_version},
        )
        assert changed.status_code == 200
        stale_sign = approver_client.post(
            f"/api/v1/governance/decisions/{stale.id}/sign",
            json={
                "decision": "REJECT",
                "remarks": "Old version",
                "password": "Correct current password 123",
                "object_version": stale_version,
            },
        )
        assert stale_sign.status_code == 409
        db.expire_all()
        assert db.query(SignedApprovalRecord).filter_by(object_id=stale.id).count() == 0
        # The approver made the material change, so the policy refuses their approval of the current version too.
        current_version = db.get(Decision, stale.id).updated_at.isoformat()
        editor_sign = approver_client.post(
            f"/api/v1/governance/decisions/{stale.id}/sign",
            json={
                "decision": "APPROVE",
                "remarks": "Own edit",
                "password": "Correct current password 123",
                "object_version": current_version,
            },
        )
        assert editor_sign.status_code == 403
        assert editor_sign.json()["detail"] == {
            "code": "SOD_DENIED",
            "message": "Approval by the last material editor is not permitted",
        }
        db.expire_all()
        assert db.query(SignedApprovalRecord).filter_by(object_id=stale.id).count() == 0
        entitlement = db.query(FeatureEntitlement).filter_by(feature_code="DECISION_CENTER_SIGNATURES").first()
        entitlement.enabled = False
        db.commit()
        denied = _decision(db, tenant.id, investigation, creator)
        ids.append(denied.id)
        assert (
            approver_client.post(
                f"/api/v1/governance/decisions/{denied.id}/sign",
                json={
                    "decision": "APPROVE",
                    "remarks": "Denied",
                    "password": "Correct current password 123",
                    "object_version": denied.updated_at.isoformat(),
                },
            ).status_code
            == 403
        )
        entitlement.enabled = True
        db.commit()
        authority = db.query(ApprovalAuthority).filter_by(tenant_id=tenant.id, role_name="Approver").first()
        authority.status = "REVOKED"
        db.commit()
        no_authority = _decision(db, tenant.id, investigation, creator)
        ids.append(no_authority.id)
        assert (
            approver_client.post(
                f"/api/v1/governance/decisions/{no_authority.id}/sign",
                json={
                    "decision": "APPROVE",
                    "remarks": "Denied",
                    "password": "Correct current password 123",
                    "object_version": no_authority.updated_at.isoformat(),
                },
            ).status_code
            == 403
        )
        authority.status = "ACTIVE"
        db.commit()
        other_customer = Customer(
            id=uuid.uuid4(),
            customer_identifier=f"D23-CUSTOMER-{uuid.uuid4().hex[:8]}",
            legal_name="Other synthetic customer",
            display_name="Other synthetic customer",
            customer_type="DESIGN_PARTNER",
            country="US",
            lifecycle_status="ACTIVE",
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        db.add(other_customer)
        db.flush()
        other = Tenant(
            id=uuid.uuid4(),
            customer_id=other_customer.id,
            tenant_key=f"D23-{uuid.uuid4().hex[:8]}",
            tenant_identifier=f"D23-{uuid.uuid4().hex[:8]}",
            name="Other synthetic tenant",
            display_name="Other synthetic tenant",
            tenant_slug=f"d23-{uuid.uuid4().hex[:8]}",
            tenant_type="STANDARD",
            deployment_model="SHARED",
            primary_region="US",
            residency_region="US",
            cross_border_processing_allowed=False,
            provisioning_status="PROVISIONED",
            status="ACTIVE",
            lock_version=1,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
        )
        db.add(other)
        db.commit()
        foreign_client = _client(f"foreign-{uuid.uuid4().hex[:8]}@example.com", other.id)
        assert foreign_client.post(
            f"/api/v1/governance/decisions/{first.id}/sign",
            json={
                "decision": "REJECT",
                "remarks": "Cross tenant",
                "password": "Correct current password 123",
                "object_version": version,
            },
        ).status_code in {403, 404}
        assert foreign_client.get(f"/api/v1/governance/decisions/{first.id}/signature-history").json() == []
    finally:
        # Audit evidence is append-only and must remain available after the test.
        db.query(SignedApprovalRecord).filter(SignedApprovalRecord.object_id.in_(ids)).delete(synchronize_session=False)
        db.query(Decision).filter(Decision.id.in_(ids)).delete(synchronize_session=False)
        db.commit()
        db.close()


def test_signing_and_verification_read_the_decision_from_the_tenant_data_plane():
    """Decisions live in the tenant data plane. A decision only that session can see must still be signable."""
    from backend.app.db.data_plane import get_data_plane_db

    db = SessionLocal()
    investigation = db.query(Investigation).first()
    tenant = db.query(Tenant).filter(Tenant.id == investigation.tenant_id).one()
    bootstrap(db, tenant)
    db.commit()
    approver_client = _client(f"approver-{uuid.uuid4().hex[:8]}@example.com", tenant.id)

    # Uncommitted in its own session: invisible to the control-plane session the old code used.
    data = SessionLocal()
    now = datetime.now(timezone.utc)
    decision = Decision(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        investigation_id=investigation.id,
        decision_identifier=f"D23-DP-{uuid.uuid4().hex[:10]}",
        decision_type="INVESTIGATION_REVIEW",
        disposition="REQUIRES_REVIEW",
        rationale="Data-plane signing",
        decision_status="REQUIRES_REVIEW",
        authorized_by_ref=f"creator-{uuid.uuid4().hex[:8]}@example.com",
        updated_at=now,
        decision_timestamp=now,
        created_at=now,
    )
    data.add(decision)
    data.flush()

    def tenant_data_plane():
        yield data

    app.dependency_overrides[get_data_plane_db] = tenant_data_plane
    try:
        signed = approver_client.post(
            f"/api/v1/governance/decisions/{decision.id}/sign",
            json={
                "decision": "APPROVE",
                "remarks": "Reviewed in the data plane",
                "password": "Correct current password 123",
                "object_version": decision.updated_at.isoformat(),
            },
        )
        assert signed.status_code == 200, signed.text
        assert signed.json()["status"] == "APPROVED"
        data.refresh(decision)
        assert decision.decision_status == "APPROVED"
        verification = approver_client.get(f"/api/v1/governance/decisions/{decision.id}/signature-verification")
        assert verification.status_code == 200
        assert verification.json()["signatures"][0]["valid"] is True
    finally:
        app.dependency_overrides.pop(get_data_plane_db, None)
        db.query(SignedApprovalRecord).filter_by(object_id=decision.id).delete()
        db.commit()
        data.query(Decision).filter(Decision.id == decision.id).delete()
        data.commit()
        data.close()
        db.close()
