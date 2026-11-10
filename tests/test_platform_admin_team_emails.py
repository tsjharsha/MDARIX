"""Changes MDARIX support makes to a paying organization's administrators in Platform Admin are emailed (0.10.41,
follow-on to NEW-2; backend/app/access/platform_customer_admins.py, backend/app/team_notices.py).

Adding, suspending or restoring a Customer Administrator and resetting an account's MFA queue the same
``TEAM_CHANGE_NOTICE`` events as an administrator's own changes: the person changed (an invitation is its own email)
and the organization's other active Customer Administrators. The one who made the change reads "MDARIX support",
never the staff member's name or address. In a free trial, MDARIX support's MFA reset of its owner or a colleague is
told to that person (0.10.43; before, nobody was told). Nothing for MDARIX's own staff or for an erasure; the reason
stays in the audit trail.
"""

import uuid

import pytest

from auth import emailer
from backend.app import team_notices
from backend.app.db.models.foundation import AuthUser
from backend.app.db.session import SessionLocal
from backend.app.db.tenant_scope import bind_system
from tests.conftest import authenticated_client
from tests.test_customer_admin_account_security import _tenant, _user
from tests.test_trial_team_emails import company, deliver_team_notices, team_notices as queued_notices  # noqa: F401

REASON = "Confirmed by a call to the customer's quality lead"


@pytest.fixture
def mail(monkeypatch):
    sent = []
    monkeypatch.setattr(
        emailer,
        "_send_email",
        lambda to, subject, text, html=None, reply_to=None: (
            sent.append({"to": to, "subject": subject, "text": text, "html": html}) or "SENT"
        ),
    )
    return sent


@pytest.fixture(scope="module")
def staff():
    return authenticated_client()


def _staff_name() -> list[str]:
    """The platform administrator's name and address, which no customer email may carry."""
    with SessionLocal() as db:
        bind_system(db, "test: the staff account")
        user = db.query(AuthUser).filter(AuthUser.username == "legacy-test-auth@synthetic.invalid").one()
        return [user.display_name, user.username]


def _organization(admins: int):
    with SessionLocal() as db:
        bind_system(db, "test: an organization and its administrators")
        tenant = _tenant(db, "SUP")
        people = [
            _user(db, tenant, "CUSTOMER_ADMIN", name) for name in ("Ada Admin", "Ben Admin", "Cara Admin")[:admins]
        ]
        people.append(_user(db, tenant, "Viewer", "Vic Viewer"))
        db.commit()
        return str(tenant.id), tenant.display_name, [{"id": str(p.id), "email": p.username} for p in people]


def _audiences(tenant_id) -> list[tuple[str, str | None]]:
    return [(event.payload["audience"], event.payload.get("recipient_user_id")) for event in queued_notices(tenant_id)]


def _no_staff_member(mail) -> None:
    for message in mail:
        for words in _staff_name():
            assert words not in message["subject"] and words not in message["text"] and words not in message["html"]
        assert REASON not in message["text"] and REASON not in message["html"]


def test_suspending_and_restoring_an_administrator_tells_them_and_the_other_administrators(staff, mail, company):  # noqa: F811
    tenant, organization, (ada, ben, cara, _vic) = _organization(3)
    suspended = staff.post(
        f"/api/v1/platform-admin/customer-admins/{ben['id']}/status", json={"status": "SUSPENDED", "reason": REASON}
    )
    assert suspended.status_code == 200, suspended.text
    # Every other active administrator is told: MDARIX support is not one of them.
    assert sorted(_audiences(tenant)) == sorted([("PERSON", None), ("ADMIN", ada["id"]), ("ADMIN", cara["id"])])
    events = queued_notices(tenant)
    assert all(event.payload["actor"] == team_notices.MDARIX_SUPPORT for event in events)
    assert all(event.payload["actor_user_id"] is None for event in events)
    deliver_team_notices(tenant)
    to_person = next(message for message in mail if message["to"] == ben["email"])
    assert to_person["subject"] == f"MDARIX support suspended your MDARIX account for {organization}"
    assert "If this is unexpected, please contact MDARIX support." in to_person["text"]
    to_admins = [message for message in mail if message["to"] != ben["email"]]
    assert sorted(message["to"] for message in to_admins) == sorted([ada["email"], cara["email"]])
    for message in to_admins:
        assert message["subject"] == f"MDARIX support suspended Ben Admin, a Customer Administrator of {organization}"
        assert "Changed by: MDARIX support" in message["text"]
        assert "Changed by: MDARIX support (" not in message["text"]
        assert "If you did not expect this, contact support@mdarix.in." in message["text"]
        assert "check with MDARIX support" not in message["text"]
    _no_staff_member(mail)

    mail.clear()
    restored = staff.post(
        f"/api/v1/platform-admin/customer-admins/{ben['id']}/status", json={"status": "ACTIVE", "reason": REASON}
    )
    assert restored.status_code == 200, restored.text
    deliver_team_notices(tenant)
    assert {message["subject"] for message in mail} == {
        f"Your MDARIX account for {organization} is active again",
        f"MDARIX support restored the account of Ben Admin, a Customer Administrator of {organization}",
    }
    assert "MDARIX support restored your account." in next(m for m in mail if m["to"] == ben["email"])["text"]
    _no_staff_member(mail)


def test_adding_an_administrator_tells_the_others_and_the_invitation_is_its_own_email(staff, mail, company):  # noqa: F811
    tenant, organization, (ada, ben, _vic) = _organization(2)
    email = f"dev-{uuid.uuid4().hex[:8]}@synthetic.invalid"
    # The organization has active administrators: adding one needs its People grant (0.10.95, owner decision c).
    from tests.support_grants import grant_for

    grant_for(staff, tenant, areas=("PEOPLE",))
    added = staff.post(
        f"/api/v1/platform-admin/tenants/{tenant}/customer-admins",
        json={"email": email, "display_name": "Dev Admin", "reason": REASON},
    )
    assert added.status_code == 200, added.text
    (invitation,) = mail  # the activation email, at once
    assert invitation["to"] == email
    assert sorted(_audiences(tenant)) == sorted([("ADMIN", ada["id"]), ("ADMIN", ben["id"])])
    mail.clear()
    deliver_team_notices(tenant)
    assert {message["subject"] for message in mail} == {
        f"MDARIX support invited Dev Admin as a Customer Administrator of {organization}"
    }
    _no_staff_member(mail)


def test_an_mfa_reset_tells_the_person_in_mdarix_supports_words(staff, mail, company):  # noqa: F811
    # The organization's only active administrator: MDARIX support may recover it without the customer's approval.
    tenant, organization, (ada, _vic) = _organization(1)
    reset = staff.post(f"/api/v1/platform-admin/users/{ada['id']}/mfa-reset", json={"reason": REASON})
    assert reset.status_code == 200, reset.text
    assert _audiences(tenant) == [("PERSON", None)]  # no other administrator to tell
    deliver_team_notices(tenant)
    (message,) = mail
    assert message["to"] == ada["email"]
    assert message["subject"] == "The authenticator app of your MDARIX account was removed"
    assert "MDARIX support removed the authenticator app of your account, and you were signed out." in message["text"]
    assert "an administrator of" not in message["text"]
    assert "If you did not ask for this, contact support@mdarix.in." in message["text"]
    _no_staff_member(mail)


def test_an_mfa_reset_in_a_free_trial_tells_the_person_in_mdarix_supports_words(staff, mail, company):  # noqa: F811
    from tests.test_trial_self_admin import _member, _pretend_enrolled, _trial_with_colleague

    owner, approval, owner_email, _colleague, colleague_email = _trial_with_colleague()
    tenant = approval["tenant_id"]
    owner_id, colleague_id = _member(owner, owner_email)["id"], _member(owner, colleague_email)["id"]
    _pretend_enrolled(owner_id)
    # A colleague, and the owner (whose MFA nobody inside the trial can reset): each is told, and nobody else.
    for person_id, email in ((colleague_id, colleague_email), (owner_id, owner_email)):
        mail.clear()
        reset = staff.post(f"/api/v1/platform-admin/users/{person_id}/mfa-reset", json={"reason": REASON})
        assert reset.status_code == 200, reset.text
        events = queued_notices(tenant)
        assert [
            (event.payload["audience"], event.payload["kind"], event.payload["actor"], event.payload["actor_user_id"])
            for event in events
        ] == [("PERSON", team_notices.TRIAL, team_notices.MDARIX_SUPPORT, None)]
        assert events[0].payload["change"] == emailer.TEAM_MFA_RESET and events[0].payload["user_id"] == person_id
        deliver_team_notices(tenant)
        (message,) = mail
        assert message["to"] == email
        assert message["subject"] == "The authenticator app of your MDARIX account was removed"
        assert "MDARIX support removed the authenticator app of your MDARIX account" in message["text"]
        assert (
            "MDARIX support removed the authenticator app of your account in the MDARIX free trial of "
            in message["text"]
        )
        assert "and you were signed out." in message["text"]
        assert "who runs the MDARIX free trial" not in message["text"]
        assert "If you did not ask for this, contact support@mdarix.in." in message["text"]
        assert "UTC" in message["text"]  # when, in UTC
        _no_staff_member(mail)
        assert queued_notices(tenant) == []  # delivered once


def test_nothing_for_mdarix_staff_and_only_an_mfa_reset_in_a_free_trial():
    from backend.app.support_access import platform_tenant_id
    from tests.test_trial_self_admin import _trial_with_colleague

    _owner, _approval, _owner_email, _colleague, colleague_email = _trial_with_colleague()
    with SessionLocal() as db:
        bind_system(db, "test: the trial's colleague")
        colleague = db.query(AuthUser).filter(AuthUser.username == colleague_email).one()
        # In a free trial MDARIX support resets MFA, told to the person; it makes no other change to a trial's team.
        assert team_notices.queue_support_change(db, colleague, emailer.TEAM_MFA_RESET) == 1
        assert team_notices.queue_support_change(db, colleague, emailer.TEAM_MFA_RESET, tell_person=False) == 0
        assert team_notices.queue_support_change(db, colleague, emailer.TEAM_SUSPENDED) == 0
        staff_member = (
            db.query(AuthUser).filter(AuthUser.tenant_id == platform_tenant_id(db)).first()
            if platform_tenant_id(db)
            else None
        )
        if staff_member is not None:
            assert team_notices.queue_support_change(db, staff_member, emailer.TEAM_MFA_RESET) == 0
        tenant = _tenant(db, "STF")
        operator = _user(db, tenant, "PLATFORM_ADMIN", "Staff Member")
        assert team_notices.queue_support_change(db, operator, emailer.TEAM_MFA_RESET) == 0
        with pytest.raises(ValueError):
            team_notices.queue_support_change(db, colleague, "SOMETHING_ELSE")
        db.rollback()
