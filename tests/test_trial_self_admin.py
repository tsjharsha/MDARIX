"""A free trial looks after its own team: the trial owner removes colleagues, resets their MFA and decides on support
access (Getting started › Team); MDARIX resets a trial user's MFA without a support grant.

Every step goes through the real API: owner only (a colleague is refused), people of this trial only (another
trial's person is not found), the seat freed by a removal, sessions ended, sign-in refused, and each action in the
trial's own audit trail.
"""

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from backend.app import support_access as access
from backend.app.db.models.foundation import AuditEvent, AuthUser
from backend.app.db.models.stage2 import AuthSession, SubscriptionLifecycle
from backend.app.db.session import SessionLocal
from backend.app.db.tenant_scope import bind_system
from backend.app.main import app
from tests.conftest import authenticated_client
from tests.test_free_trial import (
    PASSWORD,
    _activate_and_sign_in,
    _activation_token,
    _approved_trial_client,
    _purge_trial_business_data,
)
from tests.test_support_access_customer_approval import GRANTS, _request, _start_now
from tests.test_support_access_sod import _platform_admin

TEAM = "/api/v1/trial/team"
SUPPORT = "/api/v1/trial/support-access"
RESET = {"reason": "Lost their phone and recovery codes"}


@pytest.fixture(autouse=True, scope="module")
def _clean_trial_workspaces():
    _purge_trial_business_data()
    yield
    _purge_trial_business_data()


def _audit(tenant_id, action: str) -> list[AuditEvent]:
    with SessionLocal() as db:
        bind_system(db, "test: read the trial's audit trail")
        rows = (
            db.query(AuditEvent)
            .filter(AuditEvent.tenant_id == uuid.UUID(str(tenant_id)), AuditEvent.action == action)
            .order_by(AuditEvent.chain_seq)
            .all()
        )
        db.expunge_all()
        return rows


def _user(user_id) -> AuthUser:
    with SessionLocal() as db:
        bind_system(db, "test: read the account")
        row = db.get(AuthUser, uuid.UUID(str(user_id)))
        db.expunge(row)
        return row


def _live_sessions(user_id) -> int:
    with SessionLocal() as db:
        bind_system(db, "test: count live sessions")
        return (
            db.query(AuthSession)
            .filter(AuthSession.user_id == uuid.UUID(str(user_id)), AuthSession.revoked_at.is_(None))
            .count()
        )


def _pretend_enrolled(user_id) -> None:
    """An authenticator set up (the reset only removes it, so its content does not matter here)."""
    with SessionLocal() as db:
        bind_system(db, "test: an enrolled authenticator")
        row = db.get(AuthUser, uuid.UUID(str(user_id)))
        row.mfa_secret_encrypted = "test-secret"
        row.mfa_recovery_hashes = ["test-hash"]
        row.mfa_enrolled_at = datetime.now(timezone.utc)
        db.commit()


def _member(owner: TestClient, email: str) -> dict:
    return next(member for member in owner.get(TEAM).json()["members"] if member["email"] == email)


def _trial_with_colleague():
    """A trial whose owner invited one colleague, who activated and signed in."""
    owner, approval, owner_email = _approved_trial_client()
    email = f"colleague-{uuid.uuid4().hex[:8]}@example.invalid"
    invited = owner.post(TEAM, json={"email": email, "display_name": "Casey Review"})
    assert invited.status_code == 200, invited.text
    colleague = _activate_and_sign_in(email, _activation_token(invited.json(), email))
    return owner, approval, owner_email, colleague, email


def test_the_owner_removes_a_colleague_and_the_seat_is_free_again():
    owner, approval, owner_email, colleague, email = _trial_with_colleague()
    tenant_id = approval["tenant_id"]
    pending = f"pending-{uuid.uuid4().hex[:8]}@example.invalid"
    invited = owner.post(TEAM, json={"email": pending, "display_name": "Robin QA"})
    assert invited.status_code == 200
    full = owner.post(TEAM, json={"email": f"extra-{uuid.uuid4().hex[:6]}@example.invalid", "display_name": "Extra"})
    assert full.status_code == 409 and full.json()["detail"]["code"] == "TRIAL_USER_LIMIT_REACHED"
    member = _member(owner, email)
    owner_id = _member(owner, owner_email)["id"]

    # A colleague cannot remove anyone, and nobody removes the owner (the owner least of all).
    refused = colleague.post(f"{TEAM}/{owner_id}/remove")
    assert refused.status_code == 403 and refused.json()["detail"]["code"] == "TRIAL_OWNER_REQUIRED"
    itself = owner.post(f"{TEAM}/{owner_id}/remove")
    assert itself.status_code == 409 and itself.json()["detail"]["code"] == "SELF_CHANGE_NOT_ALLOWED"

    assert _live_sessions(member["id"]) >= 1
    removed = owner.post(f"{TEAM}/{member['id']}/remove")
    assert removed.status_code == 200, removed.text
    assert removed.json()["status"] == "REMOVED" and removed.json()["sessions_revoked"] >= 1
    # Signed out at once, and refused at the next sign-in; the account is kept (offboarded), not deleted.
    assert _live_sessions(member["id"]) == 0
    assert colleague.get("/api/v1/trial/status").status_code == 401
    again = TestClient(app).post("/api/v1/auth/signin", json={"email": email, "password": PASSWORD})
    assert again.status_code != 200
    assert _user(member["id"]).status == "OFFBOARDED"
    assert owner.post(f"{TEAM}/{member['id']}/remove").status_code == 409  # already gone

    # The seat is free: the roster no longer lists them, and a new colleague can be invited.
    roster = owner.get(TEAM).json()
    assert roster["seats_used"] == 2 and email not in [item["email"] for item in roster["members"]]
    assert owner.get("/api/v1/trial/status").json()["usage"]["users"] == 2
    replacement = owner.post(TEAM, json={"email": f"new-{uuid.uuid4().hex[:6]}@example.invalid", "display_name": "Al"})
    assert replacement.status_code == 200, replacement.text

    # An invitation not yet accepted is withdrawn the same way: its link stops working.
    open_invitation = _member(owner, pending)
    withdrawn = owner.post(f"{TEAM}/{open_invitation['id']}/remove")
    assert withdrawn.status_code == 200 and withdrawn.json()["invitation_withdrawn"] is True
    activation = TestClient(app).post(
        "/api/v1/auth/activate-account",
        json={"token": _activation_token(invited.json(), pending), "password": PASSWORD},
    )
    assert activation.status_code != 200

    events = _audit(tenant_id, "TRIAL_COLLEAGUE_REMOVED")
    assert len(events) == 2
    first = events[0]
    assert first.actor_ref == owner_id and str(first.entity_id) == member["id"]
    assert first.details["source"] == "TRIAL_OWNER" and first.details["sessions_revoked"] >= 1
    assert first.old_values == {"status": "ACTIVE"} and first.new_values == {"status": "OFFBOARDED"}


def test_the_owner_acts_only_on_people_of_their_own_trial():
    owner, _, _ = _approved_trial_client()
    other_owner, _, other_email = _approved_trial_client()
    stranger = _member(other_owner, other_email)["id"]
    for path in (f"{TEAM}/{stranger}/remove", f"{TEAM}/{uuid.uuid4()}/remove"):
        missing = owner.post(path)
        assert missing.status_code == 404 and missing.json()["detail"]["code"] == "USER_NOT_FOUND"
    assert owner.post(f"{TEAM}/{stranger}/mfa-reset", json=RESET).status_code == 404
    assert _user(stranger).status == "ACTIVE"
    # Outside a trial there is no trial team to look after.
    customer = authenticated_client()
    assert customer.post(f"{TEAM}/{stranger}/remove").status_code == 404
    assert customer.get(SUPPORT).status_code == 404


def test_the_owner_resets_a_colleague_s_mfa_but_never_their_own():
    owner, approval, owner_email, colleague, email = _trial_with_colleague()
    member = _member(owner, email)
    owner_id = _member(owner, owner_email)["id"]
    _pretend_enrolled(member["id"])

    short = owner.post(f"{TEAM}/{member['id']}/mfa-reset", json={"reason": "Lost"})
    assert short.status_code == 422  # a reason of 5 to 500 characters
    refused = colleague.post(f"{TEAM}/{owner_id}/mfa-reset", json=RESET)
    assert refused.status_code == 403 and refused.json()["detail"]["code"] == "TRIAL_OWNER_REQUIRED"
    itself = owner.post(f"{TEAM}/{owner_id}/mfa-reset", json=RESET)
    assert itself.status_code == 409 and itself.json()["detail"]["code"] == "SELF_CHANGE_NOT_ALLOWED"

    reset = owner.post(f"{TEAM}/{member['id']}/mfa-reset", json=RESET)
    assert reset.status_code == 200, reset.text
    assert reset.json()["status"] == "MFA_RESET" and reset.json()["sessions_revoked"] >= 1
    account = _user(member["id"])
    assert account.mfa_secret_encrypted is None and account.mfa_enrolled_at is None and account.status == "ACTIVE"
    assert colleague.get("/api/v1/trial/status").status_code == 401  # signed out
    event = _audit(approval["tenant_id"], "USER_MFA_RESET")[-1]
    assert event.actor_ref == owner_id and str(event.entity_id) == member["id"]
    assert event.details["reason"] == RESET["reason"] and event.details["source"] == "TRIAL_OWNER"
    assert event.details["sessions_revoked"] >= 1
    # They can still sign in with their password, and set up a new authenticator there.
    assert TestClient(app).post("/api/v1/auth/signin", json={"email": email, "password": PASSWORD}).status_code == 200


def test_an_ended_trial_refuses_the_owner_s_changes():
    owner, approval, _, _, email = _trial_with_colleague()
    member = _member(owner, email)
    with SessionLocal() as db:
        bind_system(db, "test: end the trial")
        row = (
            db.query(SubscriptionLifecycle)
            .filter(SubscriptionLifecycle.tenant_id == uuid.UUID(approval["tenant_id"]))
            .one()
        )
        row.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        db.commit()
    for response in (
        owner.post(f"{TEAM}/{member['id']}/remove"),
        owner.post(f"{TEAM}/{member['id']}/mfa-reset", json=RESET),
    ):
        assert response.status_code == 403 and response.json()["detail"]["code"] == "TRIAL_ENDED"
    assert _user(member["id"]).status == "ACTIVE"


def _awaiting_grant(tenant_id) -> tuple[str, TestClient]:
    """A support request MDARIX approved on its side for the trial: it waits for the trial owner."""
    requester, _ = _platform_admin()
    recipient, recipient_id = _platform_admin()
    mdarix, _ = _platform_admin()
    made = _request(requester, tenant_id, recipient_id, areas=[access.CONFIGURATION])
    assert made.status_code == 200, made.text
    grant_id = made.json()["id"]
    approved = mdarix.post(f"{GRANTS}/{grant_id}/approve", json={"reason": "Reviewed the ticket with the team"})
    assert approved.status_code == 200 and approved.json()["status"] == access.AWAITING_CUSTOMER
    _start_now(grant_id)
    return grant_id, recipient


def test_the_trial_owner_decides_on_support_access_and_a_colleague_cannot():
    owner, approval, _, colleague, _ = _trial_with_colleague()
    tenant_id = approval["tenant_id"]
    grant_id, recipient = _awaiting_grant(tenant_id)
    mappings = f"/api/v1/platform-admin/tenants/{tenant_id}/mappings"
    assert recipient.get(mappings).status_code == 403  # nothing opens before the owner decides

    listing = owner.get(SUPPORT).json()
    assert listing["awaiting_decision"] == 1
    item = listing["items"][0]
    assert item["id"] == grant_id and item["can_approve"] and item["can_deny"]
    decision = {"reason": "Yes, for the import question"}
    for path in (
        SUPPORT,
        f"{SUPPORT}/{grant_id}/approve",
        f"{SUPPORT}/{grant_id}/deny",
        f"{SUPPORT}/{grant_id}/revoke",
    ):
        refused = colleague.get(path) if path == SUPPORT else colleague.post(path, json=decision)
        assert refused.status_code == 403 and refused.json()["detail"]["code"] == "TRIAL_OWNER_REQUIRED", path
    assert owner.post(f"{SUPPORT}/{grant_id}/approve", json={"reason": "Too short"}).status_code == 422

    approved = owner.post(f"{SUPPORT}/{grant_id}/approve", json=decision)
    assert approved.status_code == 200, approved.text
    assert approved.json()["status"] == access.APPROVED and approved.json()["can_revoke"]
    assert recipient.get(mappings).status_code == 200  # open now, as the owner allowed
    event = _audit(tenant_id, "SUPPORT_ACCESS_CUSTOMER_APPROVED")[-1]
    assert event.details["source"] == "TRIAL_OWNER" and event.details["areas"] == [access.CONFIGURATION]
    assert event.reason == decision["reason"]
    assert owner.post(f"{SUPPORT}/{grant_id}/deny", json=decision).status_code == 409  # decided already

    revoked = owner.post(f"{SUPPORT}/{grant_id}/revoke", json={"reason": "The question is answered"})
    assert revoked.status_code == 200 and revoked.json()["status"] == access.REVOKED
    assert recipient.get(mappings).status_code == 403
    assert _audit(tenant_id, "SUPPORT_ACCESS_REVOKED")[-1].details["source"] == "TRIAL_OWNER"

    # A second request, denied: it never opens.
    second, recipient = _awaiting_grant(tenant_id)
    denied = owner.post(f"{SUPPORT}/{second}/deny", json={"reason": "Not during our evaluation"})
    assert denied.status_code == 200 and denied.json()["status"] == access.DENIED
    assert recipient.get(mappings).status_code == 403
    assert _audit(tenant_id, "SUPPORT_ACCESS_DENIED")[-1].details["source"] == "TRIAL_OWNER"
    # Another trial's request is not this owner's to see or decide.
    other_owner, _, _ = _approved_trial_client()
    assert other_owner.post(f"{SUPPORT}/{second}/revoke", json=decision).status_code == 404
    assert other_owner.get(SUPPORT).json()["items"] == []


def test_platform_admin_resets_a_trial_user_s_mfa_without_a_support_grant():
    owner, approval, owner_email, colleague, email = _trial_with_colleague()
    tenant_id = approval["tenant_id"]
    owner_id = _member(owner, owner_email)["id"]
    colleague_id = _member(owner, email)["id"]
    staff, staff_id = _platform_admin()
    _pretend_enrolled(owner_id)

    # The trial owner: nobody inside the trial could do it, and no grant is needed.
    reset = staff.post(f"/api/v1/platform-admin/users/{owner_id}/mfa-reset", json=RESET)
    assert reset.status_code == 200, reset.text
    assert reset.json()["status"] == "MFA_RESET" and reset.json()["sessions_revoked"] >= 1
    assert _user(owner_id).mfa_enrolled_at is None
    assert owner.get("/api/v1/trial/status").status_code == 401
    event = _audit(tenant_id, "USER_MFA_RESET")[-1]
    assert event.actor_ref == str(staff_id) and str(event.entity_id) == owner_id
    assert event.details["trial_user"] is True and event.details["reason"] == RESET["reason"]
    assert event.details["source"] == "PLATFORM_ADMIN"
    assert not _audit(tenant_id, access.ACCESS_REFUSED)
    # A colleague of the trial too; still never one's own, and still with a reason.
    assert staff.post(f"/api/v1/platform-admin/users/{colleague_id}/mfa-reset", json=RESET).status_code == 200
    assert colleague.get("/api/v1/trial/status").status_code == 401
    own = staff.post(f"/api/v1/platform-admin/users/{staff_id}/mfa-reset", json=RESET)
    assert own.status_code == 409 and own.json()["detail"]["code"] == "SELF_CHANGE_NOT_ALLOWED"
    assert staff.post(f"/api/v1/platform-admin/users/{owner_id}/mfa-reset", json={"reason": "x"}).status_code == 422

    # The trials overview lists the trial's people, with their ids, for the button.
    overview = staff.get("/api/v1/platform-admin/trials", params={"q": owner_email}).json()
    row = next(item for item in overview["items"] if item["tenant_id"] == tenant_id)
    assert row["owner"]["id"] == owner_id
    assert {person["id"] for person in row["people"]} == {owner_id, colleague_id}
