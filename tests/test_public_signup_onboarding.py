import uuid

from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.db.models.foundation import AuthUser, Tenant
from backend.app.db.models.stage2 import OnboardingRequest
from backend.app.db.session import SessionLocal
from tests.signup_profile import PROFILE


def test_public_signup_creates_pending_request_not_tenant():
    email = f"onboarding-{uuid.uuid4().hex[:10]}@example.invalid"
    db = SessionLocal()
    before = db.query(Tenant).count()
    db.close()
    try:
        response = TestClient(app).post(
            "/api/v1/auth/signup",
            json={
                "email": email,
                "password": "TemporaryPassword123!",
                "display_name": "Pending Customer",
                "organization": "Pending Organization",
                **PROFILE,
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "ONBOARDING_REQUEST_ACCEPTED"
        assert body["tenant_created"] is False

        db = SessionLocal()
        assert db.query(Tenant).count() == before
        assert db.query(AuthUser).filter(AuthUser.username == email).first() is None
        assert db.query(OnboardingRequest).filter(OnboardingRequest.email == email).count() == 1
        stored = db.query(OnboardingRequest).filter(OnboardingRequest.email == email).one()
        # An old client's password is ignored: it is stored nowhere, not even in the profile.
        assert "TemporaryPassword123!" not in str(stored.profile) and "password" not in stored.profile
        assert stored.profile["job_title"] == "Quality Lead" and stored.profile["no_patient_data_confirmed"] is True
    finally:
        db.query(OnboardingRequest).filter(OnboardingRequest.email == email).delete()
        db.commit()
        db.close()
