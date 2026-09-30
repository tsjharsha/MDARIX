"""Local synthetic-MVP MFA enrollment and challenge regression coverage."""

import os
import uuid
from datetime import datetime, timedelta, timezone

from backend.app.db.models.stage2 import MfaChallenge
from backend.app.db.models.foundation import ApprovalAuthority, AuthUser, Decision, Investigation, Tenant
from backend.app.db.session import SessionLocal
from tests.conftest import authenticated_client


def test_local_mfa_enrollment_invalid_expired_replay_and_signature_gate():
    os.environ["MDARIX_ENV"] = "development"
    client = authenticated_client()

    enrollment = client.post("/api/v1/auth/mfa/enroll")
    assert enrollment.status_code == 200
    code = enrollment.json()["development_code"]
    assert len(code) == 6

    invalid = client.post("/api/v1/auth/mfa/verify-enrollment", json={"code": "000000"})
    assert invalid.status_code == 403
    assert invalid.json()["detail"]["code"] == "MFA_CODE_INVALID"

    verified = client.post("/api/v1/auth/mfa/verify", json={"code": code})
    assert verified.status_code == 200
    assert verified.json()["status"] == "MFA_ENROLLED"

    replay = client.post("/api/v1/auth/mfa/verify-enrollment", json={"code": code})
    assert replay.status_code == 400
    assert replay.json()["detail"]["code"] == "MFA_CHALLENGE_INVALID"

    db = SessionLocal()
    try:
        session_token = client.cookies.get("mdarix_session")
        from backend.app.auth_router import _mfa_hash
        from backend.app.auth_router import hash_token
        from backend.app.db.models.stage2 import AuthSession

        session = db.query(AuthSession).filter(AuthSession.session_hash == hash_token(session_token)).first()
        now = datetime.now(timezone.utc)
        db.add(
            MfaChallenge(
                id=uuid.uuid4(),
                user_id=session.user_id,
                tenant_id=session.tenant_id,
                code_hash=_mfa_hash("123456"),
                purpose="ENROLLMENT",
                expires_at=now - timedelta(minutes=1),
                created_at=now - timedelta(minutes=2),
            )
        )
        db.commit()
    finally:
        db.close()

    expired = client.post("/api/v1/auth/mfa/verify-enrollment", json={"code": "123456"})
    assert expired.status_code == 400
    assert expired.json()["detail"]["code"] == "MFA_CHALLENGE_INVALID"

    signature_challenge = client.post("/api/v1/auth/mfa/challenge")
    assert signature_challenge.status_code == 200
    assert signature_challenge.json()["status"] == "MFA_CHALLENGE_ISSUED"
    assert len(signature_challenge.json()["development_code"]) == 6

    # Ensure the final end-to-end assertion reaches the MFA gate.  The
    # synthetic authenticated user is granted explicit signing authority;
    # without this fixture governance correctly stops at authority denial.
    db = SessionLocal()
    decision_id = None
    previous_mfa_requirement = os.environ.get("MDARIX_REQUIRE_MFA_FOR_SIGNATURES")
    try:
        session_token = client.cookies.get("mdarix_session")
        from backend.app.auth_router import hash_token
        from backend.app.db.models.stage2 import AuthSession

        session = db.query(AuthSession).filter(AuthSession.session_hash == hash_token(session_token)).first()
        user = db.query(AuthUser).filter(AuthUser.id == session.user_id).first()
        tenant = db.query(Tenant).filter(Tenant.id == session.tenant_id).first()
        investigation = db.query(Investigation).filter(Investigation.tenant_id == tenant.id).first()
        assert user and tenant and investigation
        db.add(
            ApprovalAuthority(
                id=uuid.uuid4(),
                tenant_id=tenant.id,
                role_name=user.role,
                object_type="Decision",
                decision_type="INVESTIGATION_REVIEW",
                scope={},
                authority="AUTHORIZED",
                version="mfa-test-v1",
                status="ACTIVE",
                effective_from=datetime.now(timezone.utc),
                created_at=datetime.now(timezone.utc),
                updated_at=datetime.now(timezone.utc),
            )
        )
        decision = Decision(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            investigation_id=investigation.id,
            decision_identifier=f"MFA-{uuid.uuid4().hex[:10]}",
            decision_type="INVESTIGATION_REVIEW",
            disposition="REQUIRES_REVIEW",
            rationale="MFA gate regression",
            decision_status="REQUIRES_REVIEW",
            authorized_by_ref="different-reviewer",
            updated_at=datetime.now(timezone.utc),
            decision_timestamp=datetime.now(timezone.utc),
            created_at=datetime.now(timezone.utc),
        )
        db.add(decision)
        db.commit()
        db.refresh(decision)
        decision_id = decision.id
        os.environ["MDARIX_REQUIRE_MFA_FOR_SIGNATURES"] = "true"
        denied = client.post(
            f"/api/v1/governance/decisions/{decision.id}/sign",
            json={
                "decision": "APPROVE",
                "remarks": "MFA gate test",
                "password": "LegacyTestPassword123!",
                "object_version": decision.updated_at.isoformat(),
            },
        )
        assert denied.status_code == 403
        assert denied.json()["detail"]["code"] == "MFA_REQUIRED"
    finally:
        if previous_mfa_requirement is None:
            os.environ.pop("MDARIX_REQUIRE_MFA_FOR_SIGNATURES", None)
        else:
            os.environ["MDARIX_REQUIRE_MFA_FOR_SIGNATURES"] = previous_mfa_requirement
        if decision_id is not None:
            db.query(Decision).filter(Decision.id == decision_id).delete(synchronize_session=False)
            db.commit()
        db.close()
