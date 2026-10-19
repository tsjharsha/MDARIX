"""The legal and compliance fixes of 0.10.33 from the final pre-launch review: what the texts say MDARIX does, it does.

- CMP-11: AI stays off for free trials by a server rule: switching it on is refused, and a trial's model requests are
  refused whatever its switch says (backend/app/ai_settings.py, genai/governance.py).
- CMP-15: a trial request records which version of the Terms, the Free Trial Agreement and the Privacy Policy it
  accepted, and when; the record survives the erasure of the requester (backend/app/site_info.py legal_versions).
  Invitation emails link the privacy policy.
- CMP-22: the deletion date in trial emails and on Getting started counts a grace extension and the MVP hold, and is
  worded "at the earliest" (backend/app/trial/retention.py deletion_date).
- CMP-24: sign-up refuses countries and regions under comprehensive sanctions (backend/app/trial/request_profile.py).
- CMP-08: the feedback consent names what a published quote is credited with (job title and company, never the name).
"""

import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from backend.app.db.models.foundation import Tenant
from backend.app.db.models.stage2 import OnboardingRequest, SubscriptionLifecycle
from backend.app.db.session import SessionLocal
from backend.app.db.tenant_scope import bind_system
from backend.app.main import app
from genai import governance
from genai.provider import REFUSAL_MESSAGES, GenAIUnavailable
from tests.conftest import authenticated_client
from tests.signup_profile import PROFILE
from tests.test_free_trial import _approved_trial_client, _clean_trial_workspaces  # noqa: F401 (module fixture)

DAY = timedelta(days=1)


def _set_tenant(tenant_id, **values) -> None:
    with SessionLocal() as db:
        bind_system(db, "test")
        tenant = db.get(Tenant, uuid.UUID(str(tenant_id)))
        for key, value in values.items():
            setattr(tenant, key, value)
        db.commit()


def _subscription(tenant_id) -> SubscriptionLifecycle:
    with SessionLocal() as db:
        bind_system(db, "test")
        row = db.query(SubscriptionLifecycle).filter(SubscriptionLifecycle.tenant_id == tenant_id).one()
        db.expunge(row)
        return row


# ------------------------------------------------------------------------------------------- CMP-11


def test_a_free_trial_never_reaches_a_model_even_with_its_switch_on():
    _user, approval, _email = _approved_trial_client()
    tenant_id = uuid.UUID(approval["tenant_id"])
    # The switch can only be on through a direct database change (or a script); the request is refused anyway.
    _set_tenant(tenant_id, ai_processing_allowed=True)
    try:
        with governance.tenant_scope(tenant_id):
            with pytest.raises(GenAIUnavailable) as refused:
                governance.check_allowed(100)
        assert refused.value.code == "GENAI_OFF_FOR_FREE_TRIAL"
        assert refused.value.user_message == REFUSAL_MESSAGES["GENAI_OFF_FOR_FREE_TRIAL"]
        assert "free trials" in refused.value.user_message
    finally:
        _set_tenant(tenant_id, ai_processing_allowed=False)


def test_ai_cannot_be_switched_on_for_a_free_trial_and_its_status_says_off():
    from tests.support_grants import grant_support_access

    user, approval, _email = _approved_trial_client()
    tenant_id = approval["tenant_id"]
    grant_support_access(tenant_id, areas=("CONFIGURATION",))
    admin = authenticated_client()
    url = f"/api/v1/platform-admin/tenants/{tenant_id}/ai-settings"
    settings = admin.get(url)
    assert settings.status_code == 200, settings.text
    assert settings.json()["free_trial"] is True and settings.json()["ai_processing_allowed"] is False
    switched = admin.put(
        url,
        json={"ai_processing_allowed": True, "acknowledgement": True, "reason": "Trying to switch AI on for a trial"},
    )
    assert switched.status_code == 409, switched.text
    assert switched.json()["detail"]["code"] == "AI_OFF_FOR_FREE_TRIALS"
    with SessionLocal() as db:
        bind_system(db, "test")
        assert db.get(Tenant, uuid.UUID(tenant_id)).ai_processing_allowed is False
    # Switching off, and the token allowance, still work.
    assert admin.put(url, json={"monthly_token_budget": 1000, "reason": "Allowance for the record"}).status_code == 200
    # The trial's own screens hear that AI is off, whatever the switch says.
    _set_tenant(tenant_id, ai_processing_allowed=True)
    try:
        status = user.get("/api/v1/ai/status").json()
        assert status["trial"] is True and status["enabled"] is False
        assert "free trials" in status["message"]
    finally:
        _set_tenant(tenant_id, ai_processing_allowed=False)


def test_an_organization_that_is_not_a_trial_is_not_refused_as_one():
    with SessionLocal() as db:
        bind_system(db, "test")
        assert governance.is_free_trial(db, uuid.uuid4()) is False


# ------------------------------------------------------------------------------------------- CMP-15


def _legal_dir(tmp_path, terms_date="16 October 2026"):
    for name, date in (("privacy", "19 October 2026"), ("terms", terms_date), ("trial-agreement", "19 October 2026")):
        (tmp_path / f"{name}.md").write_text(f"# {name}\n\nLast updated: {date}\n\nText of {name}.\n", encoding="utf-8")
    return tmp_path


def test_legal_versions_are_the_dates_and_fingerprints_of_the_served_texts(tmp_path, monkeypatch):
    from backend.app.site_info import legal_versions

    monkeypatch.setenv("MDARIX_LEGAL_DIR", str(_legal_dir(tmp_path)))
    versions = legal_versions()
    assert set(versions) == {"privacy", "terms", "trial-agreement"}
    assert versions["terms"]["last_updated"] == "16 October 2026"
    assert versions["privacy"]["available"] is True and len(versions["privacy"]["sha256"]) == 64
    (tmp_path / "terms.md").write_text("# terms\n\nLast updated: 19 October 2026\n\nChanged.\n", encoding="utf-8")
    changed = legal_versions()
    assert changed["terms"]["last_updated"] == "19 October 2026"
    assert changed["terms"]["sha256"] != versions["terms"]["sha256"]
    (tmp_path / "privacy.md").unlink()
    assert legal_versions()["privacy"] == {"available": False, "last_updated": None, "sha256": None}


def test_a_trial_request_records_which_texts_it_accepted_and_keeps_that_after_erasure(tmp_path, monkeypatch):
    from backend.app.tenant_purge import _pseudonymize_request

    monkeypatch.setenv("MDARIX_LEGAL_DIR", str(_legal_dir(tmp_path)))
    email = f"accept-{uuid.uuid4().hex[:10]}@example.invalid"
    before = datetime.now(timezone.utc)
    response = TestClient(app).post(
        "/api/v1/auth/signup",
        json={"email": email, "display_name": "Asha Rao", "organization": "Accepting Devices", **PROFILE},
    )
    assert response.status_code == 200, response.text
    with SessionLocal() as db:
        bind_system(db, "test")
        row = db.query(OnboardingRequest).filter(OnboardingRequest.email == email).one()
        acceptance = row.legal_acceptance
        assert datetime.fromisoformat(acceptance["accepted_at"]) >= before
        documents = acceptance["documents"]
        assert documents["terms"]["last_updated"] == "16 October 2026"
        assert documents["trial-agreement"]["last_updated"] == "19 October 2026"
        assert documents["privacy"]["last_updated"] == "19 October 2026"
        # The record names nobody, so the requester's erasure keeps it.
        _pseudonymize_request(row, datetime.now(timezone.utc))
        db.commit()
        db.refresh(row)
        assert row.display_name == "Removed" and row.legal_acceptance == acceptance
    # The Platform Administrator's queue shows it with the request.
    items = authenticated_client().get("/api/v1/platform-admin/trial-requests", params={"q": row.email}).json()["items"]
    assert any(item.get("legal_acceptance") == acceptance for item in items)


def test_invitation_emails_link_the_privacy_policy_before_activation(monkeypatch):
    import auth.emailer as emailer

    sent = []
    monkeypatch.setenv("MDARIX_APP_URL", "https://mdarix.in")
    monkeypatch.setattr(emailer, "_send", lambda recipient, message: sent.append(message) or "SENT")
    emailer.send_activation_email("a@example.invalid", "token", "Acme")
    emailer.send_trial_invitation("b@example.invalid", "token", "Acme", ends_on="18 November 2026", users=3, rows=5000)
    emailer.send_trial_invitation(
        "c@example.invalid", "token", "Acme", ends_on="18 November 2026", users=3, rows=5000, invited_by="Asha Rao"
    )
    assert len(sent) == 3
    for message in sent:
        assert any("https://mdarix.in/privacy" in line for line in message.closing), message.subject


# ------------------------------------------------------------------------------------------- CMP-22


def test_the_deletion_date_counts_a_grace_extension_and_is_worded_at_the_earliest(monkeypatch):
    from backend.app import notifications
    from backend.app.trial.retention import deletion_date

    user, approval, email = _approved_trial_client()
    tenant_id = uuid.UUID(approval["tenant_id"])
    with SessionLocal() as db:
        bind_system(db, "test")
        row = db.query(SubscriptionLifecycle).filter(SubscriptionLifecycle.tenant_id == tenant_id).one()
        row.grace_ends_at = row.expires_at + 10 * DAY
        db.commit()
    subscription = _subscription(tenant_id)
    expected = subscription.grace_ends_at + 30 * DAY
    with SessionLocal() as db:
        bind_system(db, "test")
        assert deletion_date(db, db, subscription) == expected

    captured = {}

    def remember(name):
        def send(recipient, **details):
            captured[name] = details
            return "SENT"

        return send

    fake = SimpleNamespace(
        send_trial_reminder=remember("reminder"),
        send_trial_ended=remember("ended"),
        send_trial_ended_early=remember("early"),
        EmailDeliveryError=RuntimeError,
    )
    with SessionLocal() as db:
        bind_system(db, "test")
        for stage, early in (("7_DAY", False), ("ENDED", False), ("ENDED", True)):
            notifications._trial_reminder(
                db, {"subscription_id": str(subscription.id), "stage": stage, "early": early}, fake
            )
    long_date = f"{expected.day} {expected:%B %Y}"
    assert captured["reminder"]["delete_on"] == long_date
    assert captured["ended"]["delete_on"] == long_date
    assert captured["early"]["delete_on"] == long_date
    # Getting started shows the same date.
    status = user.get("/api/v1/trial/status").json()
    assert datetime.fromisoformat(status["data_deleted_at"]) == expected


def test_the_trial_emails_say_the_date_is_the_earliest_one():
    import auth.emailer as emailer

    messages = []
    original = emailer._send
    emailer._send = lambda recipient, message: messages.append(message) or "SENT"
    try:
        emailer.send_trial_reminder(
            "a@example.invalid", "Acme", days_left=7, ends_on="1 Nov 2026", delete_on="1 Dec 2026"
        )
        emailer.send_trial_ended("a@example.invalid", "Acme", delete_on="1 Dec 2026")
    finally:
        emailer._send = original
    for message in messages:
        assert ("Data deleted, at the earliest, on", "1 Dec 2026") in message.details
    assert "at the earliest" in " ".join(messages[0].paragraphs)
    assert "kept at least until the date below" in " ".join(messages[1].paragraphs)


# ------------------------------------------------------------------------------------------- CMP-24


@pytest.mark.parametrize(
    "country",
    [
        "Cuba",
        "Iran",
        "Iran, Islamic Republic of",
        "North Korea",
        "Korea, Democratic People's Republic of",
        "Syria",
        "Syrian Arab Republic",
        "Crimea",
        "Sevastopol",
        "Donetsk People's Republic",
        "so-called Luhansk People’s Republic",
        "KP",
    ],
)
def test_sign_up_refuses_countries_and_regions_under_comprehensive_sanctions(country):
    from backend.app.trial.request_profile import is_sanctioned_region

    assert is_sanctioned_region(country)
    response = TestClient(app).post(
        "/api/v1/auth/signup",
        json={
            "email": f"sanctioned-{uuid.uuid4().hex[:10]}@example.invalid",
            "display_name": "Test Person",
            "organization": "Sanctioned Test Org",
            **{**PROFILE, "country": country},
        },
    )
    assert response.status_code == 422, response.text
    assert response.json()["detail"]["code"] == "COUNTRY_NOT_SERVED"


@pytest.mark.parametrize(
    "country", ["United States", "India", "Ukraine", "Russia", "South Korea", "Iraq", "Dominican Republic", "Ireland"]
)
def test_other_countries_are_accepted(country):
    from backend.app.trial.request_profile import is_sanctioned_region

    assert not is_sanctioned_region(country)


# ------------------------------------------------------------------------------------------- CMP-08


def test_the_feedback_consent_names_what_a_published_quote_is_credited_with():
    from backend.app.trial.feedback import attribution, consent_wording

    named = consent_wording("NAMED", "Acme Devices")
    assert "my job title and my company's name, Acme Devices" in named and "not my own name" in named
    anonymous = consent_wording("ANONYMOUS", "Acme Devices")
    assert "Acme Devices" not in anonymous and "area of work" in anonymous
    row = SimpleNamespace(publish_consent="NAMED", job_title="Head of Quality", organization_name="Acme Devices")
    assert attribution(row) == "Head of Quality, Acme Devices"
