"""A paying organization's team changes are emailed (0.10.40, NEW-2; backend/app/team_notices.py, auth/emailer.py).

When a Customer Administrator removes, suspends or restores a user, withdraws an invitation, changes a role or resets
MFA, the person changed is told what changed and by whom; when the change concerns an administrator account, the
organization's other Customer Administrators are told too (and when a Customer Administrator is invited). The words
follow the trial's team emails, without any trial wording. Each email is its own outbox event, queued with the change:
a failed address is retried alone and nobody gets an email twice. A free trial's changes keep the trial's emails.

Checked as rendered (text and HTML from one message, escaped, dates in UTC), and through the real API and the outbox
worker's per-event transaction.
"""

import uuid

import pytest

from auth import emailer
from backend.app import notifications, team_notices
from backend.app.db.models.foundation import AuthUser
from backend.app.db.models.stage2 import OutboxEvent
from backend.app.db.models.workflow import UserAdditionalRole
from backend.app.db.session import SessionLocal
from backend.app.db.tenant_scope import bind_system
from tests.test_customer_admin_account_security import _client_for, _tenant, _user
from tests.test_trial_team_emails import company, deliver_team_notices, team_notices as queued_notices  # noqa: F401

USERS = "/api/v1/admin/identity/users"
REASON = "Lost phone, confirmed by a call to the desk"


@pytest.fixture
def mail(monkeypatch):
    """What would be sent over SMTP."""
    sent = []
    monkeypatch.setattr(
        emailer,
        "_send_email",
        lambda to, subject, text, html=None, reply_to=None: (
            sent.append({"to": to, "subject": subject, "text": text, "html": html}) or "SENT"
        ),
    )
    return sent


@pytest.fixture
def organization():
    """A paying organization with three Customer Administrators (Ada acts) and a Viewer."""
    with SessionLocal() as db:
        bind_system(db, "test: an organization and its team")
        tenant = _tenant(db, "TEAM")
        ada = _user(db, tenant, "CUSTOMER_ADMIN", "Ada Admin")
        ben = _user(db, tenant, "CUSTOMER_ADMIN", "Ben Admin")
        cara = _user(db, tenant, "CUSTOMER_ADMIN", "Cara Admin")
        vic = _user(db, tenant, "Viewer", "Vic Viewer")
        db.commit()
        client = _client_for(db, ada)
        people = {
            name: {"id": str(user.id), "email": user.username} for name, user in zip("abcv", (ada, ben, cara, vic))
        }
        return {"client": client, "tenant_id": str(tenant.id), "organization": tenant.display_name, **people}


def _audiences(tenant_id) -> list[tuple[str, str | None]]:
    return [(event.payload["audience"], event.payload.get("recipient_user_id")) for event in queued_notices(tenant_id)]


# ------------------------------------------------------------------------------------------- the emails themselves


@pytest.mark.parametrize(
    ("change", "subject", "sentence"),
    [
        (emailer.TEAM_REMOVED, "Ada Admin removed you from MDARIX for Acme Devices", "can no longer sign in"),
        (
            emailer.TEAM_INVITATION_WITHDRAWN,
            "Ada Admin withdrew your invitation to MDARIX for Acme Devices",
            "no longer works",
        ),
        (emailer.TEAM_SUSPENDED, "Ada Admin suspended your MDARIX account for Acme Devices", "restores your account"),
        (emailer.TEAM_RESTORED, "Your MDARIX account for Acme Devices is active again", "You can sign in"),
        (
            emailer.TEAM_ROLE_CHANGED,
            "Ada Admin changed your role in MDARIX for Acme Devices",
            "changed what you can do",
        ),
        (emailer.TEAM_MFA_RESET, "The authenticator app of your MDARIX account was removed", "set up a new"),
    ],
)
def test_the_person_changed_is_told_what_changed_and_by_whom(company, mail, change, subject, sentence):  # noqa: F811
    emailer.send_team_change_notice(
        "vic@example.com",
        change=change,
        actor="Ada Admin",
        organization="Acme Devices",
        when="21 October 2026 at 09:30 UTC",
        role_before="Viewer",
        role_now="Quality Investigator",
        roles_added=("Risk Reviewer",),
    )
    (message,) = mail
    assert message["subject"] == subject
    text = message["text"]
    assert sentence in text and "Ada Admin" in text and "When: 21 October 2026 at 09:30 UTC" in text
    for words in ("trial", "Trial", "MVP"):
        assert words not in text and words not in message["html"]
    assert "MDARIX · Hyderabad, Telangana, India" in text and "You are receiving this email because" in text
    if change == emailer.TEAM_ROLE_CHANGED:
        assert "Role before: Viewer" in text and "Role now: Quality Investigator" in text
        assert "Added: Risk Reviewer" in text
    if change == emailer.TEAM_RESTORED:
        assert "Sign in: https://app.example.com/signin" in text


def test_the_other_administrators_are_told_of_a_change_to_an_administrator_account(company, mail):  # noqa: F811
    emailer.send_team_admin_change_notice(
        "cara@example.com",
        change=emailer.TEAM_ROLE_CHANGED,
        actor="Ada <b>Admin</b>",
        actor_email="ada@example.com",
        person="Vic Viewer",
        person_email="vic@example.com",
        organization="Acme & Co",
        when="21 October 2026 at 09:30 UTC",
        role_before="Viewer",
        role_now="Customer Administrator",
    )
    (message,) = mail
    assert message["subject"] == "Ada <b>Admin</b> made Vic Viewer a Customer Administrator of Acme & Co"
    text = message["text"]
    assert "Changed by: Ada <b>Admin</b> (ada@example.com)" in text and "Person: Vic Viewer (vic@example.com)" in text
    assert "Every Customer Administrator of Acme & Co is told" in text and "When: 21 October 2026 at 09:30 UTC" in text
    assert "If you did not expect this, check with Ada <b>Admin</b> and contact support@mdarix.in." in text
    assert "<b>Admin" not in message["html"] and "Ada &lt;b&gt;Admin&lt;/b&gt;" in message["html"]
    assert "&amp; Co" in message["html"] and "trial" not in text and "MVP" not in text


def test_an_invitation_names_the_administrator_who_sent_it(company, mail):  # noqa: F811
    emailer.send_activation_email("vic@example.com", "tok", "Acme Devices", invited_by="Ada Admin")
    emailer.send_activation_email("vic@example.com", "tok", "Acme Devices")
    named, plain = mail
    assert "Ada Admin invited you to MDARIX for Acme Devices" in named["text"]
    assert "because Ada Admin, an administrator of Acme Devices, invited you" in named["text"]
    assert "You are invited to MDARIX for Acme Devices" in plain["text"]


# ------------------------------------------------------------------------------------------- through the API


@pytest.mark.db
def test_removing_a_user_tells_them_and_nobody_else(organization, mail):
    org, tenant = organization, organization["tenant_id"]
    removed = org["client"].patch(f"{USERS}/{org['v']['id']}/status", json={"status": "OFFBOARDED"})
    assert removed.status_code == 200, removed.text
    assert _audiences(tenant) == [("PERSON", None)]  # a Viewer: no administrator account concerned
    deliver_team_notices(tenant)
    (message,) = mail
    assert message["to"] == org["v"]["email"]
    assert message["subject"] == f"Ada Admin removed you from MDARIX for {org['organization']}"


@pytest.mark.db
def test_suspending_an_administrator_tells_them_and_the_other_administrators_never_the_actor(organization, mail):
    org, tenant = organization, organization["tenant_id"]
    suspended = org["client"].patch(f"{USERS}/{org['b']['id']}/status", json={"status": "SUSPENDED"})
    assert suspended.status_code == 200, suspended.text
    assert _audiences(tenant) == [("PERSON", None), ("ADMIN", org["c"]["id"])]
    deliver_team_notices(tenant)
    assert [message["to"] for message in mail] == [org["b"]["email"], org["c"]["email"]]
    to_person, to_admin = mail
    assert to_person["subject"] == f"Ada Admin suspended your MDARIX account for {org['organization']}"
    assert to_admin["subject"] == f"Ada Admin suspended Ben Admin, a Customer Administrator of {org['organization']}"

    mail.clear()
    restored = org["client"].patch(f"{USERS}/{org['b']['id']}/status", json={"status": "ACTIVE"})
    assert restored.status_code == 200
    deliver_team_notices(tenant)
    assert [message["subject"] for message in mail] == [
        f"Your MDARIX account for {org['organization']} is active again",
        f"Ada Admin restored the account of Ben Admin, a Customer Administrator of {org['organization']}",
    ]


@pytest.mark.db
def test_a_role_change_says_before_and_after_and_an_administrator_role_tells_the_administrators(organization, mail):
    org, tenant = organization, organization["tenant_id"]
    changed = org["client"].patch(
        f"/api/v1/admin/control-plane/users/{org['v']['id']}", json={"values": {"role": "CUSTOMER_ADMIN"}}
    )
    assert changed.status_code == 200, changed.text
    assert _audiences(tenant) == [("PERSON", None), ("ADMIN", org["b"]["id"]), ("ADMIN", org["c"]["id"])] or (
        _audiences(tenant) == [("PERSON", None), ("ADMIN", org["c"]["id"]), ("ADMIN", org["b"]["id"])]
    )
    deliver_team_notices(tenant)
    to_person = mail[0]
    assert to_person["to"] == org["v"]["email"]
    assert (
        "Role before: Executive (view only)" in to_person["text"]
        and "Role now: Customer Administrator" in to_person["text"]
    )
    assert sorted(message["to"] for message in mail[1:]) == sorted([org["b"]["email"], org["c"]["email"]])
    assert all(
        message["subject"] == f"Ada Admin made Vic Viewer a Customer Administrator of {org['organization']}"
        for message in mail[1:]
    )


@pytest.mark.db
def test_workflow_roles_given_and_taken_are_listed_for_the_person(organization, mail):
    org, tenant = organization, organization["tenant_id"]
    with SessionLocal() as db:
        bind_system(db, "test: an investigator")
        db.get(AuthUser, uuid.UUID(org["v"]["id"])).role = "INVESTIGATOR"
        db.commit()
    path = f"{USERS}/{org['v']['id']}/roles"
    given = org["client"].put(path, json={"additional_roles": ["RISK_REVIEWER"], "reason": "Covers risk reviews now"})
    assert given.status_code == 200, given.text
    deliver_team_notices(tenant)
    (message,) = mail
    assert "Added: Risk Reviewer" in message["text"] and "Removed:" not in message["text"]
    mail.clear()
    taken = org["client"].put(path, json={"additional_roles": [], "reason": "Risk reviews move to Cara now"})
    assert taken.status_code == 200
    deliver_team_notices(tenant)
    assert "Removed: Risk Reviewer" in mail[0]["text"]
    # The same list again changes nothing and tells nobody.
    assert org["client"].put(path, json={"additional_roles": [], "reason": "Nothing changes here"}).status_code == 200
    assert queued_notices(tenant) == []
    with SessionLocal() as db:
        bind_system(db, "test: the role rows")
        assert db.query(UserAdditionalRole).filter(UserAdditionalRole.user_id == uuid.UUID(org["v"]["id"])).count()


@pytest.mark.db
def test_an_mfa_reset_tells_the_person_without_the_reason(organization, mail):
    org, tenant = organization, organization["tenant_id"]
    reset = org["client"].post(f"{USERS}/{org['c']['id']}/mfa-reset", json={"reason": REASON})
    assert reset.status_code == 200, reset.text
    deliver_team_notices(tenant)
    assert [message["to"] for message in mail] == [org["c"]["email"], org["b"]["email"]]
    assert mail[0]["subject"] == "The authenticator app of your MDARIX account was removed"
    assert "Ada Admin, an administrator of" in mail[0]["text"]
    assert mail[1]["subject"] == (
        f"Ada Admin reset the authenticator of Cara Admin, a Customer Administrator of {org['organization']}"
    )
    for message in mail:
        assert REASON not in message["text"] and REASON not in message["html"]


@pytest.mark.db
def test_inviting_an_administrator_tells_the_others_and_withdrawing_the_invitation_tells_the_invitee(
    organization, mail
):
    org, tenant = organization, organization["tenant_id"]
    email = f"dev-{uuid.uuid4().hex[:8]}@synthetic.invalid"
    invited = org["client"].post(
        USERS, json={"email": email, "display_name": "Dev Admin", "company": "Synthetic", "role": "CUSTOMER_ADMIN"}
    )
    assert invited.status_code == 200, invited.text
    # The invitation itself went at once, naming who sent it; the other administrators are told by the outbox.
    (invitation,) = mail
    assert invitation["to"] == email and "Ada Admin invited you to MDARIX" in invitation["text"]
    assert sorted(_audiences(tenant)) == sorted([("ADMIN", org["b"]["id"]), ("ADMIN", org["c"]["id"])])
    mail.clear()
    deliver_team_notices(tenant)
    assert {message["subject"] for message in mail} == {
        f"Ada Admin invited Dev Admin as a Customer Administrator of {org['organization']}"
    }

    mail.clear()
    withdrawn = org["client"].patch(f"{USERS}/{invited.json()['id']}/status", json={"status": "OFFBOARDED"})
    assert withdrawn.status_code == 200
    deliver_team_notices(tenant)
    assert mail[0]["to"] == email
    assert mail[0]["subject"] == f"Ada Admin withdrew your invitation to MDARIX for {org['organization']}"

    # Inviting a Viewer is the invitation alone.
    mail.clear()
    viewer = org["client"].post(
        USERS,
        json={"email": f"v-{uuid.uuid4().hex[:8]}@synthetic.invalid", "display_name": "V", "company": "S"},
    )
    assert viewer.status_code == 200 and len(mail) == 1 and queued_notices(tenant) == []


@pytest.mark.db
def test_one_failed_administrator_address_is_retried_alone_and_nobody_gets_it_twice(organization, monkeypatch):
    from outbox.worker import OutboxWorker

    org, tenant = organization, organization["tenant_id"]
    sent, refused = [], {org["c"]["email"]}

    def smtp(to, subject, text, html=None, reply_to=None):
        if to in refused:
            raise emailer.EmailDeliveryError("The email provider refused the message")
        sent.append(to)
        return "SENT"

    monkeypatch.setattr(emailer, "_send_email", smtp)
    assert org["client"].patch(f"{USERS}/{org['b']['id']}/status", json={"status": "SUSPENDED"}).status_code == 200

    def publish(name, payload):
        with SessionLocal() as db:
            bind_system(db, "test: the outbox worker delivers")
            assert notifications.handle_event(db, name, payload)

    worker = OutboxWorker(publish, base_delay_seconds=1, max_delay_seconds=1)
    ids = [event.id for event in queued_notices(tenant)]
    stats = {"published": 0, "failed": 0, "dead_lettered": 0}

    def cycle():
        with SessionLocal() as db:
            bind_system(db, "test: one worker cycle")
            for event_id in ids:
                worker._deliver_one(db, event_id, stats)
            db.query(OutboxEvent).filter(OutboxEvent.id.in_(ids)).update(
                {"next_attempt_at": None}, synchronize_session=False
            )
            db.commit()

    cycle()
    assert sent == [org["b"]["email"]] and stats == {"published": 1, "failed": 1, "dead_lettered": 0}
    refused.clear()
    cycle()
    cycle()
    assert sent == [org["b"]["email"], org["c"]["email"]] and queued_notices(tenant) == []


@pytest.mark.db
def test_an_administrator_who_lost_the_role_meanwhile_gets_nothing(organization, mail):
    org, tenant = organization, organization["tenant_id"]
    assert org["client"].patch(f"{USERS}/{org['b']['id']}/status", json={"status": "SUSPENDED"}).status_code == 200
    with SessionLocal() as db:
        bind_system(db, "test: Cara is no longer an administrator")
        db.get(AuthUser, uuid.UUID(org["c"]["id"])).role = "VIEWER"
        db.commit()
    deliver_team_notices(tenant)
    assert [message["to"] for message in mail] == [org["b"]["email"]]


@pytest.mark.db
def test_a_free_trial_and_mdarix_staff_get_no_organization_emails():
    from tests.test_trial_self_admin import _trial_with_colleague

    owner, approval, _owner_email, _colleague, colleague_email = _trial_with_colleague()
    with SessionLocal() as db:
        bind_system(db, "test: the trial's people")
        tenant_id = uuid.UUID(approval["tenant_id"])
        people = db.query(AuthUser).filter(AuthUser.tenant_id == tenant_id).all()
        colleague = next(user for user in people if user.username == colleague_email)
        trial_owner = next(user for user in people if user.username == _owner_email)
        # A trial is never a pilot organization, whoever acts.
        assert team_notices.queue_organization_change(db, trial_owner, colleague, emailer.TEAM_SUSPENDED) == 0
        db.rollback()
    # The trial's own changes are the trial's emails only.
    member = next(
        item for item in owner.get("/api/v1/trial/team").json()["members"] if item["email"] == colleague_email
    )
    assert owner.post(f"/api/v1/trial/team/{member['id']}/remove").status_code == 200
    assert {event.payload["kind"] for event in queued_notices(approval["tenant_id"])} == {team_notices.TRIAL}

    with SessionLocal() as db:
        bind_system(db, "test: MDARIX staff in an organization")
        tenant = _tenant(db, "STAFF")
        staff = _user(db, tenant, "PLATFORM_ADMIN", "Staff Member")
        person = _user(db, tenant, "Viewer", "Some Viewer")
        assert team_notices.queue_organization_change(db, staff, person, emailer.TEAM_REMOVED) == 0
        db.rollback()
