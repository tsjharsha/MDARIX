"""Release 0.10.35: the P1 findings left after the free-trial launch (SEC-04, FUN-03, FUN-13)."""

from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from auth import emailer
from backend.app import notifications
from backend.app.main import app
from backend.app.plain_names import looks_like_link


# --------------------------------------------------------------------------------------- SEC-04: no links in names


@pytest.mark.parametrize(
    "value",
    [
        "Thank you https://evil.example/verify",
        "Visit www.evil-login",
        "admin@evil.example",
        "Acme secure-login.com",
        "verify at accounts.Help",
    ],
)
def test_a_name_with_a_web_or_email_address_counts_as_a_link(value):
    assert looks_like_link(value)


@pytest.mark.parametrize(
    "value", ["Asha Rao", "St. Jude Medical", "Smith & Co. Ltd", "Boston Scientific Corp.", "Dr. A. K. Menon", ""]
)
def test_ordinary_names_and_abbreviations_are_not_links(value):
    assert not looks_like_link(value)


def test_sign_up_refuses_a_name_or_organization_that_carries_a_link():
    client = TestClient(app)
    base = {"email": "someone@victim-company.example", "display_name": "Asha Rao", "organization": "Orbit Medical"}
    named = client.post(
        "/api/v1/auth/signup", json={**base, "display_name": "Your account is suspended, visit evil.com"}
    )
    assert named.status_code == 422 and named.json()["detail"]["code"] == "NAME_HAS_LINK"
    organization = client.post("/api/v1/auth/signup", json={**base, "organization": "https://evil.example"})
    assert organization.status_code == 422 and organization.json()["detail"]["code"] == "ORGANIZATION_HAS_LINK"


def test_the_public_demo_request_route_is_parked_in_the_mvp(monkeypatch):
    monkeypatch.setenv("MDARIX_FEATURE_SET", "mvp")
    response = TestClient(app).post(
        "/api/v1/public/demo-requests", json={"name": "Priya", "email": "p@example.com", "phone": "+91 98765 43210"}
    )
    assert response.status_code == 404 and response.json()["detail"]["code"] == "NOT_IN_THIS_FEATURE_SET"


# ------------------------------------------------------------------------------ FUN-03: reminder days rounded up


@pytest.mark.parametrize(
    ("left", "days"),
    [(timedelta(hours=20), 1), (timedelta(days=6, hours=20), 7), (timedelta(days=7), 7), (timedelta(hours=-1), 0)],
)
def test_reminders_count_whole_days_left_rounded_up(left, days):
    assert notifications._days_left(datetime.now(timezone.utc) + left) == days


def test_the_one_day_and_seven_day_reminders_say_tomorrow_and_in_7_days(monkeypatch):
    sent = []
    monkeypatch.setattr(
        emailer, "_send_email", lambda to, subject, text, html=None, reply_to=None: sent.append(subject) or "SENT"
    )
    for left in (timedelta(hours=20), timedelta(days=6, hours=20)):
        emailer.send_trial_reminder(
            "owner@example.com",
            "Orbit Medical",
            days_left=notifications._days_left(datetime.now(timezone.utc) + left),
            ends_on="19 November 2026",
            delete_on="19 December 2026",
        )
    assert "ends tomorrow" in sent[0] and "ends in 7 days" in sent[1]


# ----------------------------------------------------- FUN-13: the welcome email states the two-factor rule rightly


def test_the_welcome_email_tells_a_person_who_must_use_two_factor_sign_in_to_set_it_up(monkeypatch):
    sent = []
    monkeypatch.setattr(
        emailer, "_send_email", lambda to, subject, text, html=None, reply_to=None: sent.append(text) or "SENT"
    )
    emailer.send_welcome_email("leader@example.com", "Orbit Medical", mfa_required=True)
    emailer.send_welcome_email("viewer@example.com", "Orbit Medical", mfa_required=False)
    assert "set up an authenticator app" in sent[0] and "have your phone ready" in sent[0]
    assert "authenticator" not in sent[1]
    assert all("Administrators must" not in text for text in sent)


# --------------------------------------------------- DEV-004: a spent link is known before a password is typed


def test_the_link_status_says_whether_a_one_time_link_still_works_without_spending_it():
    from auth.durable import issue_invitation
    from backend.app.db.session import SessionLocal
    from tests.test_auth_hardening import _user

    user = _user()
    with SessionLocal() as db:
        token = issue_invitation(db, user.id, user.tenant_id)
    client = TestClient(app)
    check = {"token": token, "kind": "activation"}
    assert client.post("/api/v1/auth/link-status", json=check).json() == {"usable": True}
    assert client.post("/api/v1/auth/link-status", json=check).json() == {"usable": True}  # asking does not spend it
    activated = client.post(
        "/api/v1/auth/activate-account", json={"token": token, "password": "Spring rain on tin roofs 42"}
    )
    assert activated.status_code == 200, activated.text
    assert client.post("/api/v1/auth/link-status", json=check).json() == {"usable": False, "code": "INVALID_ACTIVATION"}
    unknown = client.post("/api/v1/auth/link-status", json={"token": "not-a-real-token", "kind": "reset"}).json()
    assert unknown == {"usable": False, "code": "INVALID_RESET"}
