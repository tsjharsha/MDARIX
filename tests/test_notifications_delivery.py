"""Notifications: verified SMTP TLS, the new event types (queued with identifiers only, delivered to the right
people), and renewal reminders that follow each organization's saved recipients and wording."""

import secrets
import ssl
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from auth import emailer
from auth.durable import persist_session
from backend.app import notifications
from backend.app.db.models.customer_lifecycle import CustomerContact, ReminderPolicyRecipient
from backend.app.db.models.foundation import AuthUser, ConnectorConfiguration, PlanDefinition, Tenant, TenantMembership
from backend.app.db.models.stage2 import (
    EmailTemplate,
    OnboardingRequest,
    OutboxEvent,
    ReminderPolicy,
    SubscriptionLifecycle,
    TrialFeedback,
)
from backend.app.db.session import SessionLocal
from backend.app.db.tenant_scope import bind_system
from backend.app.main import app
from tests.conftest import authenticated_client


# ------------------------------------------------------------------------------------------- SMTP transport


class _FakeSMTP:
    """Records how the connection was secured instead of opening one."""

    seen: list = []

    def __init__(self, host, port, timeout=None, context=None):
        self.context = context
        _FakeSMTP.seen.append(("connect", port, context))

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def starttls(self, context=None):
        _FakeSMTP.seen.append(("starttls", None, context))

    def login(self, username, password):
        pass

    def send_message(self, message):
        _FakeSMTP.seen.append(("sent", message["To"], None))


@pytest.fixture
def smtp(monkeypatch):
    for name, value in {
        "MDARIX_SMTP_HOST": "smtp.example.test",
        "MDARIX_SMTP_USERNAME": "user",
        "MDARIX_SMTP_PASSWORD": "secret",
        "MDARIX_SMTP_FROM": "no-reply@example.test",
        "MDARIX_SMTP_VERIFIED_DOMAIN": "example.test",
    }.items():
        monkeypatch.setenv(name, value)
    _FakeSMTP.seen = []
    monkeypatch.setattr(emailer.smtplib, "SMTP", _FakeSMTP)
    monkeypatch.setattr(emailer.smtplib, "SMTP_SSL", _FakeSMTP)
    return _FakeSMTP.seen


def _verifying(context) -> bool:
    return (
        isinstance(context, ssl.SSLContext)
        and context.verify_mode == ssl.CERT_REQUIRED
        and context.check_hostname is True
    )


def test_starttls_verifies_the_server_certificate_and_name(smtp, monkeypatch):
    monkeypatch.setenv("MDARIX_SMTP_PORT", "587")
    assert emailer._send_email("a@example.com", "Hi", "body") == "SENT"
    starttls = [context for step, _, context in smtp if step == "starttls"]
    assert len(starttls) == 1 and _verifying(starttls[0])
    assert ("sent", "a@example.com", None) in smtp


def test_implicit_tls_verifies_the_server_certificate_and_name(smtp, monkeypatch):
    monkeypatch.setenv("MDARIX_SMTP_PORT", "465")
    assert emailer._send_email("a@example.com", "Hi", "body") == "SENT"
    connect = [context for step, port, context in smtp if step == "connect" and port == 465]
    assert len(connect) == 1 and _verifying(connect[0])


# ------------------------------------------------------------------------------------------- email wording


@pytest.fixture
def company(monkeypatch):
    monkeypatch.setenv("MDARIX_COMPANY_LEGAL_NAME", "Example Labs Ltd")
    monkeypatch.setenv("MDARIX_SUPPORT_EMAIL", "support@example.com")
    monkeypatch.setenv("MDARIX_APP_URL", "https://app.example.com")


@pytest.fixture
def outbox(monkeypatch):
    sent = []
    monkeypatch.setattr(
        emailer,
        "_send_email",
        lambda to, subject, text, html=None, reply_to=None: (
            sent.append({"to": to, "subject": subject, "text": text, "html": html}) or "SENT"
        ),
    )
    return sent


def test_every_new_email_has_text_and_html_and_escapes_names(company, outbox):
    hostile = "<b>Eve</b>"
    emailer.send_assignment_notice("a@x.test", organization="Acme", reference="INV-7", assigned_by=hostile)
    emailer.send_review_pending_notice("a@x.test", organization="Acme", reference="INV-7", submitted_by=None)
    emailer.send_signoff_completed_notice(
        "a@x.test", organization="Acme", reference="INV-7", signed_by="Ann", decision="REJECT"
    )
    emailer.send_risk_review_requested_notice("a@x.test", organization="Acme", reference="R-1", requested_by="Bo")
    emailer.send_connector_sync_failed_notice("a@x.test", organization="Acme", connection="erp", failure="Down.")
    emailer.send_ai_budget_notice(
        "a@x.test", organization="Acme", percent=80, month="October 2026", tokens_used=800, budget=1000
    )
    emailer.send_feedback_alert(
        "a@x.test", organization="Acme", rating=4, recommend_score=None, consent="PRIVATE", contact_ok=False
    )
    emailer.send_demo_request_acknowledgement("a@x.test", display_name=hostile)
    emailer.send_trial_request_acknowledgement("a@x.test", display_name="Ann", organization="Acme")
    emailer.send_trial_request_declined("a@x.test", display_name="Ann", organization="Acme")
    assert len(outbox) == 10
    for message in outbox:
        assert message["text"] and message["html"] and "Example Labs Ltd" in message["text"]
        assert "<b>Eve</b>" not in message["html"]
    assert "Eve" in outbox[0]["text"] and "&lt;b&gt;Eve&lt;/b&gt;" in outbox[0]["html"]
    assert outbox[2]["subject"] == "The decision on INV-7 was rejected"
    assert "800 of 1,000 tokens" in outbox[5]["text"]
    assert "support@example.com" in outbox[9]["text"]


def test_the_approval_email_opens_the_decisions_screen(company, outbox):
    emailer.send_review_pending_notice("a@x.test", organization="Acme", reference="DEC000003", submitted_by="Ann")
    assert "https://app.example.com/app/decision" in outbox[0]["text"]
    assert "/app/my-work" not in outbox[0]["text"]


def test_a_saved_reminder_template_changes_the_words_but_not_the_layout(company, outbox):
    emailer.send_subscription_reminder(
        "a@x.test",
        "Acme",
        expires_on="1 May 2027",
        days_left=30,
        template=("Renew <now>", "Hello Acme,\n\nYour licence ends <script>x</script>."),
    )
    message = outbox[0]
    assert message["subject"] == "Renew <now>"
    assert "Your licence ends" in message["text"] and "<script>" not in message["html"]
    assert "Example Labs Ltd" in message["text"]


# ------------------------------------------------------------------------------------------- organizations


@pytest.fixture(scope="module")
def tenant_id():
    """A fresh customer organization, so recipients and settings are exactly what each test creates."""
    code = f"NTF{uuid.uuid4().hex[:6].upper()}"
    created = authenticated_client().post(
        "/api/v1/platform-admin/customers",
        json={"company_name": f"Notify Test {code}", "tenant_code": code, "plan_code": "STARTER"},
    )
    assert created.status_code == 200, created.text
    return uuid.UUID(created.json()["id"])


@pytest.fixture
def db():
    session = SessionLocal()
    bind_system(session, "notification tests")
    try:
        yield session
    finally:
        session.rollback()
        session.close()


def _user(db, tenant_id, role, *, status="ACTIVE", name=None) -> AuthUser:
    now = datetime.now(timezone.utc)
    user = AuthUser(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        username=f"ntf-{role.lower()}-{uuid.uuid4().hex[:8]}@example.invalid",
        display_name=name or f"{role.title()} Person",
        company="Test",
        password_hash="x",
        role=role,
        status=status,
        email_verified=True,
        created_at=now,
        updated_at=now,
    )
    db.add(user)
    db.flush()
    return user


@pytest.fixture
def sent(monkeypatch):
    """Capture every notification email by template name, without SMTP."""
    captured = []

    def capture(name):
        return lambda recipient, **kw: captured.append((name, recipient, kw)) or "SENT"

    for name in (
        "send_assignment_notice",
        "send_review_pending_notice",
        "send_signoff_completed_notice",
        "send_risk_review_requested_notice",
        "send_connector_sync_failed_notice",
        "send_ai_budget_notice",
        "send_feedback_alert",
        "send_trial_request_declined",
        "send_subscription_reminder",
    ):
        monkeypatch.setattr(emailer, name, capture(name))
    return captured


def _deliver(db, event: OutboxEvent) -> bool:
    db.flush()
    assert "@" not in str(event.payload), "the queue never holds an email address"
    return notifications.handle_event(db, event.event_name, dict(event.payload))


def test_an_assignment_emails_the_assignee_and_names_who_assigned(db, tenant_id, sent):
    lead = _user(db, tenant_id, "LEADER", name="Lena Lead")
    investigator = _user(db, tenant_id, "INVESTIGATOR")
    case = uuid.uuid4()
    event = notifications.notify_assignment(
        db,
        tenant_id,
        investigation_id=case,
        assignee_user_id=investigator.id,
        assigned_by_user_id=lead.id,
        reference="INV-2026-0042",
    )
    assert _deliver(db, event)
    assert sent == [
        (
            "send_assignment_notice",
            investigator.username,
            {"organization": sent[0][2]["organization"], "reference": "INV-2026-0042", "assigned_by": "Lena Lead"},
        )
    ]
    # Assigning a case to yourself sends nothing; neither does an account of another organization.
    assert (
        notifications.notify_assignment(
            db, tenant_id, investigation_id=case, assignee_user_id=lead.id, assigned_by_user_id=lead.id
        )
        is None
    )
    other = _user(db, uuid.UUID(str(db.query(Tenant.id).filter(Tenant.id != tenant_id).first()[0])), "INVESTIGATOR")
    assert notifications.notify_assignment(db, tenant_id, investigation_id=case, assignee_user_id=other.id) is None


def test_a_pending_decision_reaches_every_approver_but_the_submitter(db, tenant_id, sent):
    approver = _user(db, tenant_id, "APPROVER")
    leader = _user(db, tenant_id, "LEADER")
    submitter = _user(db, tenant_id, "APPROVER", name="Sam Submitter")
    _user(db, tenant_id, "INVESTIGATOR")
    _user(db, tenant_id, "APPROVER", status="OFFBOARDED")
    event = notifications.notify_review_pending(
        db, tenant_id, decision_id=uuid.uuid4(), requested_by=str(submitter.id), investigation_id=uuid.uuid4()
    )
    assert _deliver(db, event)
    recipients = {recipient for _, recipient, _ in sent}
    assert {approver.username, leader.username} <= recipients
    assert submitter.username not in recipients and all("investigator" not in r for r in recipients)
    assert all(kw["submitted_by"] == "Sam Submitter" for _, _, kw in sent)
    # A named approver gets it alone.
    sent.clear()
    event = notifications.notify_review_pending(db, tenant_id, decision_id=uuid.uuid4(), approver_user_id=approver.id)
    assert _deliver(db, event) and [recipient for _, recipient, _ in sent] == [approver.username]


def test_a_signoff_tells_the_case_owner_found_by_their_email(db, tenant_id, sent):
    owner = _user(db, tenant_id, "INVESTIGATOR")
    signer = _user(db, tenant_id, "APPROVER", name="Ada Approver")
    event = notifications.notify_signoff_completed(
        db,
        tenant_id,
        decision_id=uuid.uuid4(),
        owner_ref=owner.username,
        signer_user_id=signer.id,
        decision="APPROVE",
    )
    assert event.payload["owner_user_id"] == str(owner.id)
    assert _deliver(db, event)
    (name, recipient, details) = sent[0]
    assert recipient == owner.username and details["signed_by"] == "Ada Approver" and details["decision"] == "APPROVE"
    # The owner signing their own case is not told about it.
    assert (
        notifications.notify_signoff_completed(
            db, tenant_id, decision_id=uuid.uuid4(), owner_ref=owner.username, signer_user_id=owner.id
        )
        is None
    )


def test_a_risk_review_request_reaches_the_approvers_without_the_reason(db, tenant_id, sent):
    approver = _user(db, tenant_id, "APPROVER")
    requester = _user(db, tenant_id, "INVESTIGATOR")
    event = notifications.notify_risk_review_requested(
        db,
        tenant_id,
        risk_id=uuid.uuid4(),
        risk_identifier="RISK-12",
        requested_by=str(requester.id),
        reason="Customer text that must stay out of the queue",
    )
    assert "Customer text" not in str(event.payload)
    assert _deliver(db, event)
    assert approver.username in {recipient for _, recipient, _ in sent}
    assert all(kw["reference"] == "RISK-12" for _, _, kw in sent)


def test_connector_failures_and_ai_budget_reach_customer_administrators(db, tenant_id, sent):
    admin = _user(db, tenant_id, "CUSTOMER_ADMIN")
    _user(db, tenant_id, "INVESTIGATOR")
    now = datetime.now(timezone.utc)
    connector = ConnectorConfiguration(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        code=f"erp-{uuid.uuid4().hex[:6]}",
        connector_type="REST",
        configuration={},
        version="v1",
        status="ACTIVE",
        created_at=now,
        updated_at=now,
    )
    db.add(connector)
    event = notifications.notify_connector_sync_failed(
        db, tenant_id, connector_id=connector.id, failure="PROVIDER_READ_FAILED"
    )
    assert _deliver(db, event)
    assert [(name, recipient) for name, recipient, _ in sent] == [("send_connector_sync_failed_notice", admin.username)]
    assert sent[0][2]["connection"] == connector.code and "did not answer" in sent[0][2]["failure"]

    sent.clear()
    month = "2031-01"  # a month no other test touches
    first = notifications.notify_ai_budget_threshold(db, tenant_id, percent=80, month=month, tokens_used=8, budget=10)
    db.flush()
    assert notifications.notify_ai_budget_threshold(db, tenant_id, percent=80, month=month) is None  # once a month
    assert notifications.notify_ai_budget_threshold(db, tenant_id, percent=100, month=month) is not None
    with pytest.raises(ValueError):
        notifications.notify_ai_budget_threshold(db, tenant_id, percent=50)
    assert _deliver(db, first)
    assert sent[0][1] == admin.username and sent[0][2]["month"] == "January 2031" and sent[0][2]["percent"] == 80


def test_feedback_alerts_staff_and_a_declined_request_is_told_politely(db, tenant_id, sent, monkeypatch):
    user = _user(db, tenant_id, "INVESTIGATOR")
    now = datetime.now(timezone.utc)
    feedback = TrialFeedback(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        user_id=user.id,
        organization_name="Notify Org",
        rating_overall=4,
        recommend_score=8,
        features_used=[],
        publish_consent="PRIVATE",
        consent_text="x",
        consent_at=now,
        contact_ok=True,
        publication_status="NOT_REQUESTED",
        created_at=now,
        updated_at=now,
    )
    db.add(feedback)
    event = notifications.notify_feedback_submitted(db, tenant_id, feedback_id=feedback.id)
    monkeypatch.delenv("MDARIX_TRIAL_ALERT_EMAIL", raising=False)
    monkeypatch.setenv("MDARIX_SUPPORT_EMAIL", "support@example.com")
    assert _deliver(db, event)
    assert sent[0][:2] == ("send_feedback_alert", "support@example.com") and sent[0][2]["rating"] == 4

    sent.clear()
    request = OnboardingRequest(
        id=uuid.uuid4(),
        email=f"declined-{uuid.uuid4().hex[:8]}@example.invalid",
        display_name="Dee",
        organization="Declined Co",
        status="DECLINED",
        created_at=now,
        updated_at=now,
    )
    db.add(request)
    event = notifications.notify_trial_request_declined(db, tenant_id, request_id=request.id)
    assert _deliver(db, event)
    assert sent == [
        ("send_trial_request_declined", request.email, {"display_name": "Dee", "organization": "Declined Co"})
    ]


def test_security_notices_and_support_reports_are_delivered_by_the_worker(db, tenant_id, monkeypatch):
    user = _user(db, tenant_id, "INVESTIGATOR")
    delivered = []
    monkeypatch.setattr(
        "auth.security_notices.send_security_notice",
        lambda recipient, **kw: delivered.append((recipient, kw["kind"])) or "SENT",
    )
    event = notifications.notify_security_notice(db, tenant_id, user_id=user.id, kind="PASSWORD_CHANGED")
    assert _deliver(db, event) and delivered == [(user.username, "PASSWORD_CHANGED")]

    called = []
    monkeypatch.setattr(
        "backend.app.support_api.deliver_problem_report", lambda _db, payload: called.append(payload) or "SENT"
    )
    assert notifications.handle_event(db, "SUPPORT_PROBLEM_REPORTED", {"report_id": str(uuid.uuid4())})
    assert len(called) == 1


def test_a_failed_email_makes_a_new_notification_retry(db, tenant_id, monkeypatch):
    investigator = _user(db, tenant_id, "INVESTIGATOR")

    def refuse(*_args, **_kwargs):
        raise emailer.EmailDeliveryError("refused")

    monkeypatch.setattr(emailer, "send_assignment_notice", refuse)
    event = notifications.notify_assignment(
        db, tenant_id, investigation_id=uuid.uuid4(), assignee_user_id=investigator.id
    )
    with pytest.raises(notifications.NotificationFailed):
        _deliver(db, event)


# ------------------------------------------------------------------------------------------- renewal reminders


def _subscription(db, tenant_id) -> SubscriptionLifecycle:
    now = datetime.now(timezone.utc)
    row = SubscriptionLifecycle(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        plan_id=db.query(PlanDefinition.id).first()[0],
        plan_version="1",
        starts_at=now,
        expires_at=now + timedelta(days=30, hours=1),
        created_at=now,
        updated_at=now,
    )
    db.add(row)
    db.flush()
    return row


def _policy(db, tenant_id, types) -> ReminderPolicy:
    now = datetime.now(timezone.utc)
    policy = ReminderPolicy(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        name="Customer notification policy",
        thresholds=[30],
        timezone="UTC",
        recipient_types=types,
        version="v1",
        status="ACTIVE",
        created_at=now,
        updated_at=now,
    )
    db.add(policy)
    db.flush()
    return policy


def _contact(db, tenant_id, policy, recipient_type) -> str:
    now = datetime.now(timezone.utc)
    customer_id = db.query(Tenant.customer_id).filter(Tenant.id == tenant_id).scalar()
    contact = CustomerContact(
        id=uuid.uuid4(),
        customer_id=customer_id,
        contact_type="NOTIFICATION",
        name="Bill",
        email=f"contact-{uuid.uuid4().hex[:8]}@example.invalid",
        status="ACTIVE",
        created_at=now,
        updated_at=now,
    )
    db.add(contact)
    db.flush()
    db.add(
        ReminderPolicyRecipient(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            reminder_policy_id=policy.id,
            recipient_type=recipient_type,
            contact_id=contact.id,
            status="ACTIVE",
            created_at=now,
        )
    )
    db.flush()
    return contact.email


def test_reminders_follow_the_saved_recipients_and_wording(db, tenant_id, sent):
    admin = _user(db, tenant_id, "CUSTOMER_ADMIN")
    policy = _policy(db, tenant_id, ["CUSTOMER_ADMIN", "BILLING_CONTACT"])
    billing = _contact(db, tenant_id, policy, "BILLING_CONTACT")
    business = _contact(db, tenant_id, policy, "BUSINESS_CONTACT")  # a type the settings do not send to
    now = datetime.now(timezone.utc)
    db.add(
        EmailTemplate(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            stage="EXPIRING",
            version="v1",
            subject="{{customer_name}}: licence ends {{expiry_date}}",
            body="Hello {{ customer_name }},\n\n{{days_remaining}} days left. Renew: {{activation_link}}",
            allowed_variables=["customer_name", "expiry_date", "days_remaining", "activation_link"],
            status="ACTIVE",
            created_at=now,
            updated_at=now,
        )
    )
    row = _subscription(db, tenant_id)
    assert notifications.handle_event(db, "SUBSCRIPTION_REMINDER", {"subscription_id": str(row.id), "stage": "30_DAY"})
    recipients = sorted(recipient for _, recipient, _ in sent)
    assert recipients == sorted([admin.username, billing]) and business not in recipients
    subject, body = sent[0][2]["template"]
    organization = sent[0][2]["organization"]
    assert subject == f"{organization}: licence ends {sent[0][2]['expires_on']}"
    assert body.startswith(f"Hello {organization},") and "30 days left" in body and "{{" not in body


def test_reminders_without_admins_in_the_settings_still_reach_someone(db, tenant_id, sent):
    admin = _user(db, tenant_id, "CUSTOMER_ADMIN")
    _policy(db, tenant_id, ["ACCOUNT_OWNER"])  # nobody saved with that type
    row = _subscription(db, tenant_id)
    assert notifications.handle_event(db, "SUBSCRIPTION_REMINDER", {"subscription_id": str(row.id)})
    assert admin.username in {recipient for _, recipient, _ in sent}
    assert all(kw["template"] is None for _, _, kw in sent)  # no saved email: the standard wording


def test_a_template_with_an_unknown_value_falls_back_to_the_standard_wording(db, tenant_id):
    now = datetime.now(timezone.utc)
    row = _subscription(db, tenant_id)
    db.add(
        EmailTemplate(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            stage="7_DAY",
            version="v1",
            subject="Hi {{nickname}}",
            body="Body",
            allowed_variables=[],
            status="DRAFT",
            created_at=now,
            updated_at=now,
        )
    )
    db.flush()
    values = {"customer_name": "A", "expiry_date": "B", "days_remaining": "1", "activation_link": "C"}
    assert notifications.reminder_template(db, row, "7_DAY", values) is None


def test_saving_a_reminder_email_makes_it_the_one_used(tenant_id):
    platform = authenticated_client()
    for version, subject in (("v1", "First {{expiry_date}}"), ("v2", "Second {{expiry_date}}")):
        saved = platform.post(
            f"/api/v1/platform/subscriptions/{tenant_id}/email-templates",
            json={
                "stage": "GRACE",
                "version": version,
                "subject": subject,
                "body": "Body",
                "allowed_variables": ["expiry_date"],
            },
        )
        assert saved.status_code == 200 and saved.json()["status"] == "ACTIVE"
    session = SessionLocal()
    try:
        bind_system(session, "test")
        statuses = dict(
            session.query(EmailTemplate.version, EmailTemplate.status)
            .filter(EmailTemplate.tenant_id == tenant_id, EmailTemplate.stage == "GRACE")
            .all()
        )
    finally:
        session.close()
    assert statuses == {"v1": "SUPERSEDED", "v2": "ACTIVE"}


# ------------------------------------------------------------------------------------------- trial conversion


def test_converting_a_trial_makes_its_owner_the_customer_administrator(tenant_id):
    """A tenant on the Free Trial plan, owned by the person who requested it, moves to a paid plan."""
    db = SessionLocal()
    bind_system(db, "test")
    now = datetime.now(timezone.utc)
    try:
        from backend.app.trial.service import _free_trial_plan

        trial = _free_trial_plan(db, now)
        owner = _user(db, tenant_id, "Leader")
        db.add(
            TenantMembership(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                user_id=owner.id,
                status="ACTIVE",
                is_default=True,
                created_at=now,
                updated_at=now,
            )
        )
        db.add(
            OnboardingRequest(
                id=uuid.uuid4(),
                email=owner.username,
                display_name="Owner",
                organization="Converted Co",
                status="APPROVED",
                tenant_id=tenant_id,
                created_at=now,
                updated_at=now,
            )
        )
        db.add(
            SubscriptionLifecycle(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                plan_id=trial.id,
                plan_version=trial.version,
                starts_at=now,
                expires_at=now + timedelta(days=10),
                status="ACTIVE",
                created_at=now + timedelta(seconds=5),
                updated_at=now,
            )
        )
        db.commit()
        token = secrets.token_urlsafe(32)
        persist_session(db, token, owner.id, tenant_id)
        owner_id = owner.id
        starter = str(db.query(PlanDefinition.id).filter(PlanDefinition.code == "STARTER").scalar())
    finally:
        db.close()
    session = TestClient(app)
    session.cookies.set("mdarix_session", token)
    converted = authenticated_client().post(
        f"/api/v1/platform/customers/{tenant_id}/subscription",
        json={
            "plan_id": starter,
            "starts_at": now.isoformat(),
            "expires_at": (now + timedelta(days=365)).isoformat(),
            "reason": "Trial converted to a paid plan",
        },
    )
    assert converted.status_code == 200, converted.text
    assert converted.json()["trial_converted"] is True
    assert converted.json()["trial_owner_promoted"] == str(owner_id)
    check = SessionLocal()
    try:
        bind_system(check, "test")
        assert check.get(AuthUser, owner_id).role == "CUSTOMER_ADMIN"
        from backend.app.db.models.foundation import AuditEvent

        audit = (
            check.query(AuditEvent)
            .filter(AuditEvent.tenant_id == tenant_id, AuditEvent.action == "TRIAL_OWNER_PROMOTED")
            .one()
        )
        assert audit.entity_id == owner_id and "@" not in str(audit.details)
    finally:
        check.close()
    # The old session (with the old role) is ended; the next sign-in follows the administrator rules.
    assert session.get("/api/v1/auth/session").status_code == 401
