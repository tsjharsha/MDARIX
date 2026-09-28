"""Local synthetic-MVP MFA enrollment and challenge regression coverage."""
import hashlib
import os
import uuid
from datetime import datetime, timedelta, timezone

from backend.app.db.models.stage2 import MfaChallenge
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
        db.add(MfaChallenge(id=uuid.uuid4(), user_id=session.user_id, tenant_id=session.tenant_id,
                            code_hash=_mfa_hash("123456"), purpose="ENROLLMENT",
                            expires_at=now - timedelta(minutes=1), created_at=now - timedelta(minutes=2)))
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
