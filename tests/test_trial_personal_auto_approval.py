"""Release 0.10.48: a personal address (Gmail, Outlook, ...) gets its free trial at once too, by default
(backend/app/trial/auto_approval.py).

- A company or a personal address is approved at once; a disposable address always waits for a person.
- Personal addresses have a daily cap of their own (10); the company cap (20) counts company addresses only.
- The one-trial-per-company rule does not reach across a personal provider: two people with Gmail addresses each get a
  trial, and a second request from the same address waits (sign-up already refuses it).
- The platform organization's own personal addresses wait (FUN-14), without holding back the provider's other users.
- ``company-domains`` keeps the behaviour before 0.10.48 (a personal address waits); ``off`` approves nothing.
- A personal approval is made by "Automatic approval (personal email)", which the Platform Admin queue names.
"""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from auth.service import _hash
from backend.app.db.models.foundation import AuthUser
from backend.app.db.models.stage2 import OnboardingRequest
from backend.app.db.session import SessionLocal
from backend.app.db.tenant_scope import bind_system
from backend.app.main import app
from backend.app.support_access import platform_tenant_id
from backend.app.trial import auto_approval
from tests.conftest import authenticated_client
from tests.signup_profile import PROFILE
from tests.test_free_trial import _clean_trial_workspaces, _platform_organization  # noqa: F401 (module fixture)


@pytest.fixture(autouse=True)
def _default_setting(monkeypatch):
    """The server as production runs it: MDARIX_TRIAL_AUTO_APPROVE unset (company-and-personal); caps out of the way
    and no DNS lookup unless a test says otherwise; a support address of its own."""
    _platform_organization()
    monkeypatch.delenv("MDARIX_TRIAL_AUTO_APPROVE", raising=False)
    monkeypatch.setenv("MDARIX_TRIAL_AUTO_APPROVE_DAILY_MAX", "100000")
    monkeypatch.setenv("MDARIX_TRIAL_AUTO_APPROVE_PERSONAL_DAILY_MAX", "100000")
    monkeypatch.setenv("MDARIX_TRIAL_DOMAIN_CHECK", "off")
    monkeypatch.setenv("MDARIX_SUPPORT_EMAIL", f"support@help-{uuid.uuid4().hex[:8]}.com")


@pytest.fixture
def stored():
    """A session, and a way to store requests that are removed after the test."""
    added: list = []
    with SessionLocal() as db:
        bind_system(db, "test: which trial requests are approved at once")

        def store(*rows):
            db.add_all(rows)
            db.commit()
            added.extend(rows)
            return rows

        yield db, store
        for row in reversed(added):
            db.delete(row)
        db.commit()


# A day of its own, far ahead, so the test database's other requests never count towards a cap.
def _day() -> datetime:
    return datetime(2099, 1, 1, tzinfo=timezone.utc) + timedelta(days=uuid.uuid4().int % 3000)


def _request(email: str, at: datetime | None = None, status: str = "PENDING_REVIEW") -> OnboardingRequest:
    at = at or _day()
    return OnboardingRequest(
        id=uuid.uuid4(),
        email=email,
        display_name="Taylor Quality",
        organization="Request Test",
        status=status,
        profile={},
        created_at=at,
        updated_at=at,
    )


def test_company_and_personal_addresses_are_approved_at_once_and_disposable_ones_wait(stored):
    db, store = stored
    tag = uuid.uuid4().hex[:8]
    company, gmail, outlook, disposable, disposable_sub, reserved = store(
        _request(f"quality.lead@devices-{tag}.com"),
        _request(f"asha.{tag}@gmail.com"),
        _request(f"Ravi.{tag}@Outlook.com"),
        _request(f"trial.{tag}@mailinator.com"),
        _request(f"trial.{tag}@inbox.yopmail.com"),
        _request(f"trial.{tag}@acme.invalid"),
    )
    assert auto_approval.eligible(db, company.id) == (True, "COMPANY_DOMAIN")
    assert auto_approval.eligible(db, gmail.id) == (True, "PERSONAL_ADDRESS")
    assert auto_approval.eligible(db, outlook.id) == (True, "PERSONAL_ADDRESS")
    assert auto_approval.eligible(db, disposable.id) == (False, "DISPOSABLE")
    assert auto_approval.eligible(db, disposable_sub.id) == (False, "DISPOSABLE")
    assert auto_approval.eligible(db, reserved.id) == (False, "RESERVED_DOMAIN")


def test_two_gmail_users_each_get_a_trial_but_one_address_gets_one_request(stored):
    """Gmail's users are not one company; one address is one person."""
    db, store = stored
    tag, day = uuid.uuid4().hex[:8], _day()
    first, second = store(
        _request(f"asha.{tag}@gmail.com", day + timedelta(hours=1)),
        _request(f"ravi.{tag}@gmail.com", day + timedelta(hours=2)),
    )
    assert auto_approval.eligible(db, first.id) == (True, "PERSONAL_ADDRESS")
    assert auto_approval.eligible(db, second.id) == (True, "PERSONAL_ADDRESS")
    # The same address again, whatever its capitals: it waits for a person.
    (again,) = store(_request(f"Asha.{tag}@GMAIL.com", day + timedelta(hours=3)))
    assert auto_approval.eligible(db, again.id) == (False, "ADDRESS_ALREADY_HAS_A_REQUEST")
    # A company is still one trial: the second colleague waits (the first invites them).
    _, colleague_two = store(
        _request(f"one@devices-{tag}.com", day + timedelta(hours=4)),
        _request(f"two@devices-{tag}.com", day + timedelta(hours=5)),
    )
    assert auto_approval.eligible(db, colleague_two.id) == (False, "COMPANY_ALREADY_HAS_A_REQUEST")


def test_sign_up_already_refuses_a_second_request_from_the_same_address():
    """The address rule matches sign-up's own: a repeated address is told it already asked (409), so no second
    request is stored."""
    email = f"repeat.{uuid.uuid4().hex[:8]}@example.invalid"
    body = {"email": email, "display_name": "Taylor Quality", "organization": "Repeat Devices", **PROFILE}
    assert TestClient(app).post("/api/v1/auth/signup", json=body).status_code == 200
    again = TestClient(app).post("/api/v1/auth/signup", json={**body, "email": email.upper()})
    assert again.status_code == 409 and again.json()["detail"]["code"] == "TRIAL_ALREADY_REQUESTED"


def test_personal_addresses_have_a_daily_cap_of_their_own(stored, monkeypatch):
    """Each cap counts the day's earlier requests of its own kind, approved or not; neither uses up the other."""
    db, store = stored
    tag, day = uuid.uuid4().hex[:8], _day()

    def at(hour: int) -> datetime:
        return day + timedelta(hours=hour)

    store(
        _request(f"a@first-{tag}.com", at(1)),
        _request(f"b@second-{tag}.com", at(2), "DECLINED"),
        _request(f"c.{tag}@gmail.com", at(3)),
        _request(f"d.{tag}@yahoo.co.in", at(4), "DECLINED"),  # never approved, still an attempt
        _request(f"e.{tag}@mailinator.com", at(5)),  # disposable: neither cap
    )
    personal, company = store(_request(f"f.{tag}@outlook.com", at(6)), _request(f"g@third-{tag}.com", at(7)))
    store(_request(f"h.{tag}@gmail.com", at(8)))  # after both: not counted

    monkeypatch.setenv("MDARIX_TRIAL_AUTO_APPROVE_PERSONAL_DAILY_MAX", "2")
    assert auto_approval.eligible(db, personal.id) == (False, "PERSONAL_DAILY_CAP")
    monkeypatch.setenv("MDARIX_TRIAL_AUTO_APPROVE_PERSONAL_DAILY_MAX", "3")
    assert auto_approval.eligible(db, personal.id) == (True, "PERSONAL_ADDRESS")
    monkeypatch.setenv("MDARIX_TRIAL_AUTO_APPROVE_DAILY_MAX", "2")
    assert auto_approval.eligible(db, company.id) == (False, "DAILY_CAP")
    # The company cap counts the two company requests only, not the three personal and one disposable before it.
    monkeypatch.setenv("MDARIX_TRIAL_AUTO_APPROVE_DAILY_MAX", "3")
    assert auto_approval.eligible(db, company.id) == (True, "COMPANY_DOMAIN")
    # A full personal cap never holds back a company address, nor a full company cap a personal one.
    monkeypatch.setenv("MDARIX_TRIAL_AUTO_APPROVE_PERSONAL_DAILY_MAX", "0")
    assert auto_approval.eligible(db, company.id) == (True, "COMPANY_DOMAIN")
    monkeypatch.setenv("MDARIX_TRIAL_AUTO_APPROVE_PERSONAL_DAILY_MAX", "3")
    monkeypatch.setenv("MDARIX_TRIAL_AUTO_APPROVE_DAILY_MAX", "0")
    assert auto_approval.eligible(db, personal.id) == (True, "PERSONAL_ADDRESS")


def test_a_personal_address_whose_domain_does_not_resolve_waits(stored, monkeypatch):
    """The DNS check stays for personal addresses: a made-up subdomain of a provider gets no invitation that bounces."""
    db, store = stored
    tag = uuid.uuid4().hex[:8]
    monkeypatch.setenv("MDARIX_TRIAL_DOMAIN_CHECK", "dns")
    monkeypatch.setattr(auto_approval, "domain_resolves", lambda domain: domain == "gmail.com")
    real, made_up = store(_request(f"asha.{tag}@gmail.com"), _request(f"asha.{tag}@made-up-{tag}.gmail.com"))
    assert auto_approval.eligible(db, real.id) == (True, "PERSONAL_ADDRESS")
    assert auto_approval.eligible(db, made_up.id) == (False, "DOMAIN_NOT_FOUND")


def test_company_domains_keeps_personal_addresses_waiting_and_off_approves_nothing(stored, monkeypatch):
    db, store = stored
    tag = uuid.uuid4().hex[:8]
    company, gmail, disposable = store(
        _request(f"lead@devices-{tag}.com"), _request(f"asha.{tag}@gmail.com"), _request(f"x.{tag}@yopmail.com")
    )
    monkeypatch.setenv("MDARIX_TRIAL_AUTO_APPROVE", "company-domains")
    assert auto_approval.eligible(db, company.id) == (True, "COMPANY_DOMAIN")
    assert auto_approval.eligible(db, gmail.id) == (False, "PERSONAL_MAIL")
    assert auto_approval.eligible(db, disposable.id) == (False, "DISPOSABLE")
    monkeypatch.setenv("MDARIX_TRIAL_AUTO_APPROVE", "off")
    for row in (company, gmail, disposable):
        assert auto_approval.eligible(db, row.id) == (False, "OFF")


def test_the_platform_organizations_personal_addresses_wait_but_not_the_providers_other_users(stored, monkeypatch):
    """FUN-14 for personal addresses: a staff account's or the support address's own Gmail or Outlook address waits;
    the provider's other users do not, since its domain is not the platform's."""
    db, store = stored
    tag = uuid.uuid4().hex[:8]
    monkeypatch.setenv("MDARIX_SUPPORT_EMAIL", f"Help.{tag}@Outlook.com")
    now = datetime.now(timezone.utc)
    staff = AuthUser(
        id=uuid.uuid4(),
        tenant_id=platform_tenant_id(db),
        username=f"ops.{tag}@gmail.com",
        display_name="Platform Operator",
        company="MDARIX",
        password_hash=_hash(uuid.uuid4().hex),
        role="PLATFORM_ADMIN",
        status="ACTIVE",
        email_verified=True,
        created_at=now,
        updated_at=now,
    )
    db.add(staff)
    db.flush()
    from_staff, from_support, other_user = store(
        _request(f"ops.{tag}@gmail.com"), _request(f"help.{tag}@outlook.com"), _request(f"asha.{tag}@gmail.com")
    )
    try:
        assert "gmail.com" not in auto_approval.platform_domains(db)
        assert "outlook.com" not in auto_approval.platform_domains(db)
        assert auto_approval.eligible(db, from_staff.id) == (False, "PLATFORM_ORGANIZATION")
        assert auto_approval.eligible(db, from_support.id) == (False, "PLATFORM_ORGANIZATION")
        assert auto_approval.eligible(db, other_user.id) == (True, "PERSONAL_ADDRESS")
    finally:
        db.delete(staff)
        db.commit()


def _queued(admin, email: str) -> dict:
    items = admin.get("/api/v1/platform-admin/trial-requests", params={"q": email}).json()["items"]
    return next(item for item in items if item["email"] == email)


def _sign_up(email: str) -> str:
    response = TestClient(app).post(
        "/api/v1/auth/signup",
        json={"email": email, "display_name": "Asha Rao", "organization": "Rao Medical", **PROFILE},
    )
    assert response.status_code == 200, response.text
    return response.json()["status"]


def test_a_personal_address_is_approved_at_sign_up_by_the_personal_approval_account():
    """End to end with the server's default setting: two Gmail users each get a trial at once, approved by
    "Automatic approval (personal email)"; a company email by "Automatic approval (company email)", as before; a
    disposable address waits."""
    tag = uuid.uuid4().hex[:8]
    first, second = f"asha.{tag}@gmail.com", f"ravi.{tag}@gmail.com"
    company, disposable = f"quality.lead@devices-{tag}.com", f"trial.{tag}@mailinator.com"
    assert _sign_up(first) == "TRIAL_APPROVING"
    assert _sign_up(second) == "TRIAL_APPROVING"
    assert _sign_up(company) == "TRIAL_APPROVING"
    assert _sign_up(disposable) == "ONBOARDING_REQUEST_ACCEPTED"
    with SessionLocal() as db:
        bind_system(db, "test: who approved each request")
        rows = {row.email: row for row in db.query(OnboardingRequest).filter(OnboardingRequest.email.like(f"%{tag}%"))}
        personal = db.query(AuthUser).filter(AuthUser.username == auto_approval.PERSONAL_APPROVER_USERNAME).one()
        company_approver = db.query(AuthUser).filter(AuthUser.username == auto_approval.APPROVER_USERNAME).one()
        assert personal.status == "DISABLED" and personal.tenant_id == platform_tenant_id(db)
        for email in (first, second):
            assert rows[email].status == "APPROVED" and rows[email].tenant_id is not None
            assert rows[email].reviewed_by == personal.id
        assert rows[first].tenant_id != rows[second].tenant_id  # two people, two workspaces
        assert rows[company].status == "APPROVED" and rows[company].reviewed_by == company_approver.id
        assert rows[disposable].status == "PENDING_REVIEW" and rows[disposable].reviewed_by is None
    admin = authenticated_client()
    assert _queued(admin, first)["reviewed_by_name"] == "Automatic approval (personal email)"
    assert _queued(admin, company)["reviewed_by_name"] == "Automatic approval (company email)"
    assert _queued(admin, disposable)["reviewed_by_name"] is None
    # The same address cannot ask again: it has an account now.
    again = TestClient(app).post(
        "/api/v1/auth/signup",
        json={"email": first, "display_name": "Asha Rao", "organization": "Rao Medical", **PROFILE},
    )
    assert again.status_code == 409
