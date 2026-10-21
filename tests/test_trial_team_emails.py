"""A trial owner's change to their team is emailed (backend/app/trial/team.py, auth/emailer.py): removing a colleague,
withdrawing an invitation and resetting a colleague's MFA each tell the person changed, confirm it to the owner and
alert the MDARIX team, once each, through the outbox (backend/app/team_notices.py: one event per email, queued with
the change).

The emails are checked as they are rendered (text and HTML from the same message, escaped, with the usual footer), and
through the real API and the outbox worker: who gets what, the owner's reason for an MFA reset never reaching the
colleague, no team alert without an alert address, an email failure leaving the change in place and retried alone,
the MFA-reset limit, and the change listed in Platform Admin's Trials overview.
"""

import secrets
import uuid
from datetime import datetime, timezone

import pytest
from auth import emailer
from backend.app import notifications
from backend.app.db.models.foundation import AuthUser, Tenant
from backend.app.db.models.stage2 import OutboxEvent
from backend.app.db.session import SessionLocal
from backend.app.db.tenant_scope import bind_system
from tests.conftest import authenticated_client
from tests.test_free_trial import _activate_and_sign_in, _activation_token, _approved_trial_client
from tests.test_free_trial import _clean_trial_workspaces  # noqa: F401 (module fixture)

TEAM = "/api/v1/trial/team"
REASON = "Lost phone on the 14:05 train, confirmed by a call"
ALERT = "trials@mdarix.invalid"


@pytest.fixture
def company(monkeypatch):
    monkeypatch.setenv("MDARIX_COMPANY_LEGAL_NAME", "MDARIX")
    monkeypatch.setenv("MDARIX_COMPANY_ADDRESS", "Hyderabad, Telangana, India")
    monkeypatch.setenv("MDARIX_SUPPORT_EMAIL", "support@mdarix.in")
    monkeypatch.setenv("MDARIX_APP_URL", "https://app.example.com")


@pytest.fixture
def outbox(monkeypatch):
    """Capture what would be sent over SMTP."""
    sent = []
    monkeypatch.setattr(
        emailer,
        "_send_email",
        lambda to, subject, text, html=None, reply_to=None: (
            sent.append({"to": to, "subject": subject, "text": text, "html": html}) or "SENT"
        ),
    )
    return sent


AUDIENCES = ("PERSON", "OWNER", "ADMIN", "MDARIX_TEAM")


def team_notices(tenant_id) -> list[OutboxEvent]:
    """The organization's queued team change emails not yet delivered, the person changed first."""
    with SessionLocal() as db:
        bind_system(db, "test: the queued team change emails")
        rows = (
            db.query(OutboxEvent)
            .filter(
                OutboxEvent.tenant_id == uuid.UUID(str(tenant_id)),
                OutboxEvent.event_name == notifications.TEAM_CHANGE_NOTICE,
                OutboxEvent.published_at.is_(None),
                OutboxEvent.dead_lettered_at.is_(None),
            )
            .order_by(OutboxEvent.occurred_at)
            .all()
        )
        db.expunge_all()
    return sorted(rows, key=lambda row: AUDIENCES.index(row.payload["audience"]))


def deliver_team_notices(tenant_id) -> None:
    """What the outbox worker does with them: each delivered once, then marked delivered."""
    for event in team_notices(tenant_id):
        with SessionLocal() as db:
            bind_system(db, "test: deliver a team change email")
            assert notifications.handle_event(db, event.event_name, event.payload) is True
            db.get(OutboxEvent, event.id).published_at = datetime.now(timezone.utc)
            db.commit()


def _footer(message: dict) -> None:
    for body in (message["text"], message["html"]):
        assert "MDARIX · Hyderabad, Telangana, India" in body and "support@mdarix.in" in body
        assert "You are receiving this email because" in body


# ------------------------------------------------------------------------------------------- the emails themselves


def test_a_removed_colleague_is_told_plainly_with_no_link_into_mdarix(company, outbox):
    emailer.send_trial_colleague_removed("casey@example.com", owner="Taylor Quality", organization="Acme Devices")
    message = outbox[0]
    assert message["subject"] == "Taylor Quality removed you from the MDARIX free trial of Acme Devices"
    text = message["text"]
    assert "You can no longer sign in to this trial, and you were signed out." in text
    assert "stays there under your name: it is part of the trial data of Acme Devices." in text
    assert "If this is unexpected, please contact Taylor Quality." in text
    assert "write to support@mdarix.in" in text
    assert "https://" not in text and "href" not in message["html"]
    _footer(message)


def test_a_withdrawn_invitation_says_the_link_no_longer_works(company, outbox):
    emailer.send_trial_invitation_withdrawn("robin@example.com", owner="Taylor Quality", organization="Acme Devices")
    message = outbox[0]
    assert message["subject"] == "Taylor Quality withdrew your invitation to the MDARIX free trial of Acme Devices"
    assert "The activation link in the earlier invitation email no longer works." in message["text"]
    assert "You do not need to do anything." in message["text"]
    assert "https://" not in message["text"] and "href" not in message["html"]
    _footer(message)


def test_the_mfa_reset_notice_says_who_did_it_and_what_happens_next(company, outbox):
    emailer.send_trial_mfa_reset_notice(
        "casey@example.com", owner="Taylor Quality", organization="Acme Devices", when="19 October 2026 at 09:30 UTC"
    )
    message = outbox[0]
    assert message["subject"] == "The authenticator app of your MDARIX account was removed"
    text = message["text"]
    assert "Taylor Quality removed the authenticator app of your MDARIX account" in text
    assert "you were signed out" in text and "set up a new authenticator app" in text
    assert "When: 19 October 2026 at 09:30 UTC" in text
    assert "If you did not ask for this, contact Taylor Quality or support@mdarix.in." in text
    assert "href" not in message["html"]
    _footer(message)


@pytest.mark.parametrize(
    ("change", "subject", "sentence"),
    [
        (emailer.TEAM_REMOVED, "You removed Casey Review from your MDARIX trial", "can no longer sign in"),
        (emailer.TEAM_INVITATION_WITHDRAWN, "You withdrew the invitation to Casey Review", "no longer works"),
        (emailer.TEAM_MFA_RESET, "You reset Casey Review's authenticator", "set up a new one at their next sign-in"),
    ],
)
def test_the_owner_gets_a_confirmation_that_is_also_a_security_notice(company, outbox, change, subject, sentence):
    emailer.send_trial_team_change_confirmation(
        "owner@example.com",
        change=change,
        person="Casey Review",
        person_email="casey@example.com",
        organization="Acme Devices",
        when="19 October 2026 at 09:30 UTC",
    )
    message = outbox[0]
    assert message["to"] == "owner@example.com" and message["subject"] == subject
    text = message["text"]
    assert sentence in text and "casey@example.com" in text and "When: 19 October 2026 at 09:30 UTC" in text
    assert "If this was not you, change your password now and contact support@mdarix.in." in text
    _footer(message)


def test_the_mdarix_team_alert_names_the_trial_the_owner_and_the_person(company, outbox):
    emailer.send_trial_team_change_alert(
        ALERT,
        change=emailer.TEAM_MFA_RESET,
        organization="Acme Devices",
        tenant_key="TRIAL_ACME_1",
        owner="Taylor Quality",
        owner_email="owner@example.com",
        person_email="casey@example.com",
        when="19 October 2026 at 09:30 UTC",
    )
    message = outbox[0]
    assert message["subject"] == (
        "Trial team change: Acme Devices (TRIAL_ACME_1): Taylor Quality reset MFA for casey@example.com"
    )
    assert "Trial owner: Taylor Quality (owner@example.com)" in message["text"]
    _footer(message)


def test_every_value_a_person_typed_is_escaped(company, outbox):
    owner, organization = "<b>Taylor</b>", "<script>alert(1)</script> & Co"
    emailer.send_trial_colleague_removed("a@example.com", owner=owner, organization=organization)
    emailer.send_trial_invitation_withdrawn("a@example.com", owner=owner, organization=organization)
    emailer.send_trial_mfa_reset_notice("a@example.com", owner=owner, organization=organization, when="now")
    for change in (emailer.TEAM_REMOVED, emailer.TEAM_INVITATION_WITHDRAWN, emailer.TEAM_MFA_RESET):
        emailer.send_trial_team_change_confirmation(
            "o@example.com",
            change=change,
            person="<i>Casey</i>",
            person_email="casey@example.com",
            organization=organization,
            when="now",
        )
    emailer.send_trial_team_change_alert(
        ALERT,
        change=emailer.TEAM_REMOVED,
        organization=organization,
        tenant_key="TRIAL_X",
        owner=owner,
        owner_email="o@example.com",
        person_email="casey@example.com",
        when="now",
    )
    assert len(outbox) == 7
    for message in outbox:
        assert "<script>" not in message["html"] and "<b>Taylor" not in message["html"]
        assert "<i>Casey" not in message["html"]
        assert "&lt;script&gt;" in message["html"] and "&amp; Co" in message["html"]


# ------------------------------------------------------------------------------------------- through the API


def _trial_with_colleague(name: str = "Casey Review"):
    """A trial whose owner invited one colleague, who activated and signed in."""
    owner, approval, owner_email = _approved_trial_client()
    email = f"colleague-{uuid.uuid4().hex[:8]}@example.invalid"
    invited = owner.post(TEAM, json={"email": email, "display_name": name})
    assert invited.status_code == 200, invited.text
    colleague = _activate_and_sign_in(email, _activation_token(invited.json(), email))
    member = next(item for item in owner.get(TEAM).json()["members"] if item["email"] == email)
    return owner, approval, owner_email, colleague, member


def _pretend_enrolled(user_id) -> None:
    with SessionLocal() as db:
        bind_system(db, "test: an enrolled authenticator")
        row = db.get(AuthUser, uuid.UUID(str(user_id)))
        row.mfa_secret_encrypted = "test-secret"
        row.mfa_recovery_hashes = ["test-hash"]
        db.commit()


def _tenant_key(tenant_id) -> str:
    with SessionLocal() as db:
        return db.get(Tenant, uuid.UUID(str(tenant_id))).tenant_key


def _status(user_id) -> str:
    with SessionLocal() as db:
        bind_system(db, "test: read the account")
        return db.get(AuthUser, uuid.UUID(str(user_id))).status


def test_removing_a_colleague_emails_them_the_owner_and_the_mdarix_team_once_each(company, monkeypatch):
    monkeypatch.setenv("MDARIX_DEMO_ALERT_EMAIL", ALERT)
    owner, approval, owner_email, _colleague, member = _trial_with_colleague("Casey <b>Review</b>")
    sent = []
    monkeypatch.setattr(
        emailer,
        "_send_email",
        lambda to, subject, text, html=None, reply_to=None: (
            sent.append({"to": to, "subject": subject, "text": text, "html": html}) or "SENT"
        ),
    )
    removed = owner.post(f"{TEAM}/{member['id']}/remove")
    assert removed.status_code == 200, removed.text
    assert "notify" not in removed.json()  # what the emails need stays on the server
    # Queued with the change, one event per email, with ids only (never an address).
    queued = team_notices(approval["tenant_id"])
    assert [event.payload["audience"] for event in queued] == ["PERSON", "OWNER", "MDARIX_TEAM"]
    assert not any("@" in str(value) for event in queued for value in event.payload.values())
    assert sent == []
    deliver_team_notices(approval["tenant_id"])

    assert [message["to"] for message in sent] == [member["email"], owner_email, ALERT]
    to_colleague, to_owner, to_team = sent
    assert to_colleague["subject"] == "Taylor Quality removed you from the MDARIX free trial of Trial Devices Inc"
    assert to_owner["subject"] == "You removed Casey <b>Review</b> from your MDARIX trial"
    assert "Casey &lt;b&gt;Review&lt;/b&gt;" in to_owner["html"] and "<b>Review" not in to_owner["html"]
    assert "When: " in to_owner["text"] and " UTC" in to_owner["text"]
    tenant_key = _tenant_key(approval["tenant_id"])
    assert to_team["subject"] == (
        f"Trial team change: Trial Devices Inc ({tenant_key}): Taylor Quality removed {member['email']}"
    )
    # Removing again is refused, so it sends nothing more.
    assert owner.post(f"{TEAM}/{member['id']}/remove").status_code == 409
    deliver_team_notices(approval["tenant_id"])
    assert len(sent) == 3

    # Platform Admin sees the change on the trial's row of the Trials overview.
    overview = authenticated_client().get("/api/v1/platform-admin/trials", params={"q": tenant_key}).json()
    row = next(item for item in overview["items"] if item["tenant_id"] == approval["tenant_id"])
    assert [(item["change"], item["person"]) for item in row["team_changes"]] == [("REMOVED", member["email"])]


def test_withdrawing_an_invitation_tells_the_invitee_and_the_owner(company, outbox, monkeypatch):
    monkeypatch.setenv("MDARIX_DEMO_ALERT_EMAIL", ALERT)
    owner, approval, owner_email = _approved_trial_client()
    email = f"pending-{uuid.uuid4().hex[:8]}@example.invalid"
    invited = owner.post(TEAM, json={"email": email, "display_name": "Robin QA"})
    assert invited.status_code == 200, invited.text
    outbox.clear()  # the invitation itself

    withdrawn = owner.post(f"{TEAM}/{invited.json()['id']}/remove")
    assert withdrawn.status_code == 200 and withdrawn.json()["invitation_withdrawn"] is True
    deliver_team_notices(approval["tenant_id"])
    assert [message["to"] for message in outbox] == [email, owner_email, ALERT]
    assert (
        outbox[0]["subject"] == "Taylor Quality withdrew your invitation to the MDARIX free trial of Trial Devices Inc"
    )
    assert outbox[1]["subject"] == "You withdrew the invitation to Robin QA"
    assert f"withdrew the invitation to {email}" in outbox[2]["subject"]

    overview = authenticated_client().get("/api/v1/platform-admin/trials", params={"q": owner_email}).json()
    row = next(item for item in overview["items"] if item["tenant_id"] == approval["tenant_id"])
    assert [item["change"] for item in row["team_changes"]] == ["INVITATION_WITHDRAWN"]


def test_an_mfa_reset_tells_the_colleague_without_the_owner_s_reason(company, outbox, monkeypatch):
    monkeypatch.setenv("MDARIX_DEMO_ALERT_EMAIL", ALERT)
    owner, approval, owner_email, _colleague, member = _trial_with_colleague()
    _pretend_enrolled(member["id"])
    outbox.clear()

    reset = owner.post(f"{TEAM}/{member['id']}/mfa-reset", json={"reason": REASON})
    assert reset.status_code == 200, reset.text
    assert "notify" not in reset.json()
    deliver_team_notices(approval["tenant_id"])
    assert [message["to"] for message in outbox] == [member["email"], owner_email, ALERT]
    to_colleague = outbox[0]
    assert to_colleague["subject"] == "The authenticator app of your MDARIX account was removed"
    assert "If you did not ask for this, contact Taylor Quality or support@mdarix.in." in to_colleague["text"]
    # The reason is the owner's note for the audit trail: in nobody's email.
    for message in outbox:
        assert REASON not in message["text"] and REASON not in message["html"]
    assert outbox[1]["subject"] == "You reset Casey Review's authenticator"
    assert outbox[2]["subject"].endswith(f"Taylor Quality reset MFA for {member['email']}")

    overview = authenticated_client().get("/api/v1/platform-admin/trials", params={"q": owner_email}).json()
    row = next(item for item in overview["items"] if item["tenant_id"] == approval["tenant_id"])
    assert [(item["change"], item["person"]) for item in row["team_changes"]] == [("MFA_RESET", member["email"])]


def test_without_an_alert_address_the_mdarix_team_is_not_emailed(company, outbox, monkeypatch):
    monkeypatch.delenv("MDARIX_DEMO_ALERT_EMAIL", raising=False)
    monkeypatch.delenv("MDARIX_TRIAL_ALERT_EMAIL", raising=False)
    owner, approval, owner_email, _colleague, member = _trial_with_colleague()
    outbox.clear()
    assert owner.post(f"{TEAM}/{member['id']}/remove").status_code == 200
    deliver_team_notices(approval["tenant_id"])
    assert [message["to"] for message in outbox] == [member["email"], owner_email]


def test_the_trial_alert_address_is_used_when_there_is_no_demo_alert_address(company, outbox, monkeypatch):
    monkeypatch.delenv("MDARIX_DEMO_ALERT_EMAIL", raising=False)
    monkeypatch.setenv("MDARIX_TRIAL_ALERT_EMAIL", "ops@mdarix.invalid")
    owner, approval, _owner_email, _colleague, member = _trial_with_colleague()
    outbox.clear()
    assert owner.post(f"{TEAM}/{member['id']}/remove").status_code == 200
    deliver_team_notices(approval["tenant_id"])
    assert outbox[-1]["to"] == "ops@mdarix.invalid" and outbox[-1]["subject"].startswith("Trial team change: ")


def test_an_email_failure_never_undoes_the_change_and_only_that_email_is_retried(company, monkeypatch):
    from outbox.worker import OutboxWorker

    monkeypatch.setenv("MDARIX_DEMO_ALERT_EMAIL", ALERT)
    owner, approval, owner_email, colleague, member = _trial_with_colleague()
    sent, refused = [], {owner_email}

    def smtp(to, subject, text, html=None, reply_to=None):
        if to in refused:
            raise emailer.EmailDeliveryError("The email provider refused the message")
        sent.append(to)
        return "SENT"

    monkeypatch.setattr(emailer, "_send_email", smtp)
    removed = owner.post(f"{TEAM}/{member['id']}/remove")
    assert removed.status_code == 200, removed.text
    assert _status(member["id"]) == "OFFBOARDED"
    assert colleague.get("/api/v1/trial/status").status_code == 401

    def publish(name, payload):
        with SessionLocal() as db:
            bind_system(db, "test: the outbox worker delivers")
            assert notifications.handle_event(db, name, payload)

    # The worker's own per-event transaction (outbox/worker.py), on this trial's events only.
    worker = OutboxWorker(publish, base_delay_seconds=1, max_delay_seconds=1)
    ids = [event.id for event in team_notices(approval["tenant_id"])]
    stats = {"published": 0, "failed": 0, "dead_lettered": 0}

    def cycle():
        with SessionLocal() as db:
            bind_system(db, "test: one worker cycle")
            for event_id in ids:
                worker._deliver_one(db, event_id, stats)
            # Due again at once for the retry below.
            db.query(OutboxEvent).filter(OutboxEvent.id.in_(ids)).update(
                {"next_attempt_at": None}, synchronize_session=False
            )
            db.commit()

    cycle()
    # The owner's address failed: the colleague and the MDARIX team have their email, once.
    assert sent == [member["email"], ALERT] and stats["published"] == 2 and stats["failed"] == 1
    (waiting,) = team_notices(approval["tenant_id"])
    assert waiting.payload["audience"] == "OWNER" and waiting.attempts == 1
    assert "could not be delivered" in waiting.last_error and owner_email not in waiting.last_error
    # The retry sends the owner's email alone; another cycle sends nothing.
    refused.clear()
    cycle()
    assert sent == [member["email"], ALERT, owner_email]
    assert team_notices(approval["tenant_id"]) == []
    cycle()
    assert len(sent) == 3


def test_mfa_resets_are_limited_so_they_cannot_send_mail_without_end(company, outbox, monkeypatch):
    from backend.app import rate_limit

    monkeypatch.setenv("MDARIX_RATE_LIMITS_ENABLED", "true")
    monkeypatch.setenv("MDARIX_RATE_LIMIT_SALT", secrets.token_hex(16))
    monkeypatch.setitem(rate_limit.LIMITS, "team-mfa-reset:org", rate_limit.Limit(1, 86400))
    owner, approval, _owner_email, _colleague, member = _trial_with_colleague()
    outbox.clear()
    assert owner.post(f"{TEAM}/{member['id']}/mfa-reset", json={"reason": REASON}).status_code == 200
    deliver_team_notices(approval["tenant_id"])
    before = len(outbox)
    again = owner.post(f"{TEAM}/{member['id']}/mfa-reset", json={"reason": REASON})
    assert again.status_code == 429 and "reset as many authenticators" in again.json()["detail"]["message"]
    assert team_notices(approval["tenant_id"]) == [] and len(outbox) == before


def test_a_trial_without_team_changes_lists_none():
    _owner, approval, owner_email = _approved_trial_client()
    overview = authenticated_client().get("/api/v1/platform-admin/trials", params={"q": owner_email}).json()
    row = next(item for item in overview["items"] if item["tenant_id"] == approval["tenant_id"])
    assert row["team_changes"] == []
