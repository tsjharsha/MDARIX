"""Emails: branded text + HTML, escaped values, honest delivery states, and notifications from outbox events."""

import uuid
from datetime import datetime, timedelta, timezone

import pytest

from auth import emailer
from backend.app import notifications
from backend.app.db.models.foundation import AuthUser, PlanDefinition, Tenant
from backend.app.db.models.stage2 import OutboxEvent, SubscriptionLifecycle
from backend.app.db.session import SessionLocal
from backend.app.db.tenant_scope import bind_system


@pytest.fixture
def company(monkeypatch):
    monkeypatch.setenv("MDARIX_COMPANY_LEGAL_NAME", "Example Labs Ltd")
    monkeypatch.setenv("MDARIX_COMPANY_ADDRESS", "1 Main Street, Boston MA")
    monkeypatch.setenv("MDARIX_SUPPORT_EMAIL", "support@example.com")
    monkeypatch.setenv("MDARIX_APP_URL", "https://app.example.com")


@pytest.fixture
def outbox(monkeypatch):
    """Capture what would be sent over SMTP."""
    sent = []
    monkeypatch.setattr(
        emailer,
        "_send_email",
        lambda to, subject, text, html=None, reply_to=None: (
            sent.append({"to": to, "subject": subject, "text": text, "html": html, "reply_to": reply_to}) or "SENT"
        ),
    )
    return sent


def test_every_email_has_text_and_html_with_company_and_support(company, outbox):
    assert emailer.send_activation_email("a@example.com", "tok123", "Acme Devices") == "SENT"
    message = outbox[0]
    assert message["subject"] == "Activate your MDARIX account"
    for body in (message["text"], message["html"]):
        assert "https://app.example.com/activate-account?token=tok123" in body
        assert "Example Labs Ltd" in body and "support@example.com" in body and "72 hours" in body


def test_values_from_people_are_escaped_in_html(company, outbox):
    emailer.send_activation_email("a@example.com", "tok", "<script>alert(1)</script> & Co")
    html = outbox[0]["html"]
    assert "<script>" not in html and "&lt;script&gt;" in html and "&amp; Co" in html


def test_the_trial_invitation_says_what_the_trial_includes_and_when_data_is_deleted(company, outbox):
    emailer.send_trial_invitation("a@example.com", "tok", "Acme", ends_on="3 November 2026", users=3, rows=5000)
    text = outbox[0]["text"]
    assert "3 November 2026" in text and "up to 3 users and 5,000 uploaded rows" in text
    assert "deleted 30 days after the trial ends" in text


def test_supplier_requests_reply_to_the_requester(company, outbox):
    emailer.send_supplier_evidence_request(
        "qa@supplier.example",
        "Acme",
        title="Sensor lot KS-5521",
        items=["CoA", "Process change notice"],
        reply_to="engineer@acme.example",
    )
    assert outbox[0]["reply_to"] == "engineer@acme.example"
    assert "CoA" in outbox[0]["text"] and "Process change notice" in outbox[0]["html"]


def test_without_smtp_nothing_is_claimed_as_sent(monkeypatch):
    for name in ("MDARIX_SMTP_HOST", "MDARIX_SMTP_USERNAME", "MDARIX_SMTP_PASSWORD", "MDARIX_SMTP_FROM"):
        monkeypatch.setenv(name, "")
    assert emailer.send_password_reset_email("a@example.com", "tok") == "NOT_CONFIGURED"


def test_header_injection_in_a_recipient_is_refused(monkeypatch):
    for name, value in {
        "MDARIX_SMTP_HOST": "smtp.example.test",
        "MDARIX_SMTP_USERNAME": "u",
        "MDARIX_SMTP_PASSWORD": "p",
        "MDARIX_SMTP_FROM": "no-reply@example.test",
    }.items():
        monkeypatch.setenv(name, value)
    with pytest.raises(emailer.EmailDeliveryError):
        emailer._send_email("victim@example.com\r\nBcc: all@example.com", "Hi", "body")


# ------------------------------------------------------------------------------------------- notifications


def _admin(db, tenant):
    now = datetime.now(timezone.utc)
    user = AuthUser(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        username=f"admin-{uuid.uuid4().hex[:8]}@example.invalid",
        display_name="Admin",
        company="Test",
        password_hash="x",
        role="CUSTOMER_ADMIN",
        status="ACTIVE",
        email_verified=True,
        created_at=now,
        updated_at=now,
    )
    db.add(user)
    db.flush()
    return user


def test_a_subscription_reminder_emails_the_customer_administrators(company, monkeypatch):
    sent = []
    monkeypatch.setattr(
        emailer, "send_subscription_reminder", lambda recipient, **kw: sent.append((recipient, kw)) or "SENT"
    )
    db = SessionLocal()
    try:
        bind_system(db, "test")
        tenant = db.query(Tenant).filter(Tenant.tenant_key == "ACME_CARE_SYNTHETIC").first() or db.query(Tenant).first()
        admin = _admin(db, tenant)
        plan = db.query(PlanDefinition).first()
        now = datetime.now(timezone.utc)
        subscription = SubscriptionLifecycle(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            plan_id=plan.id,
            plan_version="1",
            starts_at=now,
            expires_at=now + timedelta(days=30),
            created_at=now,
            updated_at=now,
        )
        db.add(subscription)
        db.flush()
        assert notifications.handle_event(db, "SUBSCRIPTION_REMINDER", {"subscription_id": str(subscription.id)})
        assert admin.username in [recipient for recipient, _ in sent]
        assert all(kw["days_left"] in (29, 30) for _, kw in sent)
    finally:
        db.rollback()
        db.close()


def test_a_failed_email_makes_the_outbox_retry(company, monkeypatch):
    def refuse(*_args, **_kwargs):
        raise emailer.EmailDeliveryError("refused")

    monkeypatch.setattr(emailer, "send_tenant_lifecycle_notice", refuse)
    db = SessionLocal()
    try:
        bind_system(db, "test")
        tenant = db.query(Tenant).filter(Tenant.tenant_key == "ACME_CARE_SYNTHETIC").first() or db.query(Tenant).first()
        _admin(db, tenant)
        with pytest.raises(notifications.NotificationFailed):
            notifications.handle_event(
                db, "TENANT_LIFECYCLE_NOTIFICATION", {"tenant_id": str(tenant.id), "transition": "SUSPENDED"}
            )
    finally:
        db.rollback()
        db.close()


def test_other_events_are_not_notifications():
    db = SessionLocal()
    try:
        assert notifications.handle_event(db, "PROVIDER_RECORD_RECEIVED", {}) is False
    finally:
        db.close()


def test_trial_reminders_are_queued_once_per_stage():
    db = SessionLocal()
    try:
        bind_system(db, "test")
        plan = db.query(PlanDefinition).filter(PlanDefinition.code == "FREE_TRIAL").first()
        if plan is None:
            pytest.skip("no Free Trial plan in this database")
        tenant = db.query(Tenant).filter(Tenant.tenant_key == "ACME_CARE_SYNTHETIC").first() or db.query(Tenant).first()
        now = datetime.now(timezone.utc)
        subscription = SubscriptionLifecycle(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            plan_id=plan.id,
            plan_version="1",
            starts_at=now - timedelta(days=25),
            expires_at=now + timedelta(days=5),
            created_at=now,
            updated_at=now,
        )
        db.add(subscription)
        db.flush()

        def queued():
            return [
                row.payload["stage"]
                for row in db.query(OutboxEvent).filter(
                    OutboxEvent.event_name == "TRIAL_REMINDER",
                    OutboxEvent.payload["subscription_id"].as_string() == str(subscription.id),
                )
            ]

        notifications.queue_trial_reminders(db, now)
        db.flush()
        notifications.queue_trial_reminders(db, now)
        db.flush()
        assert queued() == ["7_DAY"]
        notifications.queue_trial_reminders(db, now + timedelta(days=4, hours=12))
        db.flush()
        assert sorted(queued()) == ["1_DAY", "7_DAY"]
        notifications.queue_trial_reminders(db, now + timedelta(days=6))
        db.flush()
        assert sorted(queued()) == ["1_DAY", "7_DAY", "ENDED"]
    finally:
        db.rollback()
        db.close()
