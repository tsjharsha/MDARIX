"""A trial request is acknowledged by email once it is stored; a known or repeated email gets no email (and the same
answer), and a mail failure never fails the request."""

import uuid

from fastapi.testclient import TestClient

from auth import emailer
from backend.app.db.models.stage2 import OnboardingRequest
from backend.app.db.session import SessionLocal
from backend.app.db.tenant_scope import bind_system
from backend.app.main import app
from tests.signup_profile import PROFILE
from tests.test_auth_hardening import _user

URL = "/api/v1/auth/signup"


def _request(email):
    return {"email": email, "display_name": "Dana Requester", "organization": "Acme Devices", **PROFILE}


def _stored(email) -> int:
    with SessionLocal() as db:
        bind_system(db, "test: trial requests")
        return db.query(OnboardingRequest).filter(OnboardingRequest.email == email).count()


def test_a_new_request_is_acknowledged_once_and_a_repeat_or_known_email_is_not(monkeypatch):
    sent = []
    monkeypatch.setattr(
        emailer, "send_trial_request_acknowledgement", lambda recipient, **kwargs: sent.append((recipient, kwargs))
    )
    client = TestClient(app)
    email = f"ack-{uuid.uuid4().hex[:10]}@example.invalid"
    first = client.post(URL, json=_request(email))
    again = client.post(URL, json=_request(email))
    known = client.post(URL, json=_request(_user().username))
    assert first.status_code == again.status_code == known.status_code == 200
    assert first.json() == again.json() == known.json()
    assert sent == [(email, {"display_name": "Dana Requester", "organization": "Acme Devices"})]


def test_a_mail_failure_does_not_fail_the_request(monkeypatch, caplog):
    def refuse(*_args, **_kwargs):
        raise emailer.EmailDeliveryError("provider down")

    monkeypatch.setattr(emailer, "send_trial_request_acknowledgement", refuse)
    email = f"ack-fail-{uuid.uuid4().hex[:10]}@example.invalid"
    response = TestClient(app).post(URL, json=_request(email))
    assert response.status_code == 200 and response.json()["status"] == "ONBOARDING_REQUEST_ACCEPTED"
    assert _stored(email) == 1
    logged = " ".join(record.getMessage() for record in caplog.records)
    assert "acknowledgement failed" in logged and email not in logged
