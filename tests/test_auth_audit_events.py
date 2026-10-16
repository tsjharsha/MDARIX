"""Every authentication event is audited (ids, outcomes and address; never an email, password, code or link), and the
account owner is told by email when the way they sign in changes (security notices through the outbox)."""

import secrets
import time
import uuid
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from auth import security_notices, totp
from auth.durable import issue_invitation
from auth.emailer import EmailDeliveryError
from backend.app.db.models.foundation import AuditEvent, AuthUser
from backend.app.db.models.stage2 import OutboxEvent
from backend.app.db.session import SessionLocal
from backend.app.db.tenant_scope import bind_system
from backend.app.main import app
from backend.app import notifications
from backend.app.notifications import NotificationFailed
from tests.test_auth_hardening import PASSWORD, _client_for, _user


@pytest.fixture
def behind_proxy(monkeypatch):
    monkeypatch.setenv("MDARIX_TRUSTED_PROXY_HOPS", "1")


def _events(user_id, action=None) -> list[AuditEvent]:
    with SessionLocal() as db:
        bind_system(db, "test: authentication audit")
        query = db.query(AuditEvent).filter(AuditEvent.entity_id == user_id)
        if action:
            query = query.filter(AuditEvent.action == action)
        rows = query.order_by(AuditEvent.created_at).all()
        db.expunge_all()
        return rows


def _notices(user_id) -> list[dict]:
    with SessionLocal() as db:
        bind_system(db, "test: security notices")
        rows = (
            db.query(OutboxEvent)
            .filter(OutboxEvent.event_name == "SECURITY_NOTICE", OutboxEvent.aggregate_id == user_id)
            .order_by(OutboxEvent.occurred_at)
            .all()
        )
        return [dict(row.payload) for row in rows]


def _assert_nothing_secret(user, *secrets_):
    for event in _events(user.id):
        recorded = " ".join(str(value) for value in (event.details, event.reason, event.old_values, event.new_values))
        assert user.username not in recorded, event.action
        for secret in secrets_:
            assert secret not in recorded, event.action


def _signin(client, email, password, address="198.51.100.40"):
    return client.post(
        "/api/v1/auth/signin", json={"email": email, "password": password}, headers={"X-Forwarded-For": address}
    )


# ------------------------------------------------------------------------------------------- sign-in and out


def test_sign_in_success_failure_lockout_and_sign_out_are_audited(behind_proxy):
    user = _user()
    client = TestClient(app)
    wrong = "a wrong password 1"
    for _ in range(5):
        assert _signin(client, user.username, wrong, "203.0.113.41").status_code == 401
    failed = _events(user.id, "SIGN_IN_FAILED")
    assert len(failed) == 5
    assert failed[0].details == {"reason": "INVALID_CREDENTIALS", "account_known": True}
    assert failed[0].actor_ref == str(user.id) and failed[0].source_ip == "203.0.113.41"
    locked = _events(user.id, "ACCOUNT_LOCKED")
    assert len(locked) == 1 and locked[0].details["scope"] == "SIGN_IN_ADDRESS"

    assert _signin(client, user.username, PASSWORD).status_code == 200
    succeeded = _events(user.id, "SIGN_IN_SUCCEEDED")
    assert len(succeeded) == 1 and succeeded[0].details == {"mfa": "NONE"}
    assert succeeded[0].source_ip == "198.51.100.40"

    assert client.post("/api/v1/auth/signout").status_code == 200
    signed_out = _events(user.id, "SIGN_OUT")
    assert len(signed_out) == 1 and signed_out[0].details == {"mfa_pending": False}
    _assert_nothing_secret(user, wrong, PASSWORD)


def test_a_failed_sign_in_for_an_unknown_email_names_no_one():
    email = f"nobody-{uuid.uuid4().hex}@example.invalid"
    assert TestClient(app).post("/api/v1/auth/signin", json={"email": email, "password": "x" * 12}).status_code == 401
    with SessionLocal() as db:
        bind_system(db, "test: anonymous failures")
        rows = db.query(AuditEvent).filter(AuditEvent.action == "SIGN_IN_FAILED", AuditEvent.actor_ref == "ANONYMOUS")
        assert all(email not in str(row.details) for row in rows.order_by(AuditEvent.created_at.desc()).limit(50))


# ------------------------------------------------------------------------------------------- passwords


def test_a_password_change_is_audited_and_the_owner_told():
    user = _user()
    client, _ = _client_for(user)
    new_password = "Another long passphrase 2027"
    response = client.post(
        "/api/v1/auth/change-password", json={"current_password": PASSWORD, "new_password": new_password}
    )
    assert response.status_code == 200, response.text
    assert [event.details for event in _events(user.id, "PASSWORD_CHANGED")] == [{"other_sessions_signed_out": 0}]
    notices = _notices(user.id)
    assert [notice["kind"] for notice in notices] == ["PASSWORD_CHANGED"]
    assert set(notices[0]) == {"user_id", "kind", "occurred_at"}  # no address in the queue
    _assert_nothing_secret(user, PASSWORD, new_password)


def test_a_reset_request_and_its_use_are_audited_and_the_owner_told():
    user = _user()
    client = TestClient(app)
    requested = client.post("/api/v1/auth/forgot-password", json={"email": user.username})
    assert requested.status_code == 200
    token = requested.json().get("development_token")
    assert token, "local development without SMTP shows the reset token"
    assert _events(user.id, "PASSWORD_RESET_REQUESTED")[0].details == {"source": "SELF_SERVICE"}
    new_password = "A completely new passphrase 9"
    assert (
        client.post("/api/v1/auth/reset-password", json={"token": token, "password": new_password}).status_code == 200
    )
    completed = _events(user.id, "PASSWORD_RESET_COMPLETED")
    assert len(completed) == 1 and "sessions_signed_out" in completed[0].details
    assert [notice["kind"] for notice in _notices(user.id)] == ["PASSWORD_RESET"]
    _assert_nothing_secret(user, token, new_password)


def test_an_activation_is_audited():
    user = _user()
    with SessionLocal() as db:
        bind_system(db, "test: an invited account")
        row = db.get(AuthUser, user.id)
        row.status = "INVITED"
        row.email_verified = False
        db.commit()
        token = issue_invitation(db, user.id, user.tenant_id)
    password = "My own activation passphrase 3"
    response = TestClient(app).post("/api/v1/auth/activate-account", json={"token": token, "password": password})
    assert response.status_code == 200, response.text
    assert [event.details for event in _events(user.id, "ACCOUNT_ACTIVATED")] == [{"was_active": False}]
    assert _notices(user.id) == []  # the person just chose this password themselves
    _assert_nothing_secret(user, token, password)


# ------------------------------------------------------------------------------------------- MFA


def _next_code(secret: str, steps_ahead: int = 1) -> str:
    return totp.code_at(secret, int(time.time() // 30) + steps_ahead)


def test_mfa_steps_are_audited_and_changes_need_reauthentication(monkeypatch):
    # A fixed authenticator clock: every code below belongs to a known 30-second step.
    clock = {"step": int(time.time() // 30)}
    monkeypatch.setattr(totp, "_step", lambda at=None: clock["step"])
    user = _user(role="Investigator")
    client, _ = _client_for(user)
    started = client.post("/api/v1/auth/mfa/enroll")
    assert started.status_code == 200, started.text
    secret = started.json()["secret"]
    assert client.post("/api/v1/auth/mfa/verify-enrollment", json={"code": "000000"}).status_code == 403
    enrolled = client.post("/api/v1/auth/mfa/verify-enrollment", json={"code": totp.current_code(secret)})
    assert enrolled.status_code == 200, enrolled.text
    recovery = enrolled.json()["recovery_codes"]
    assert _events(user.id, "MFA_FAILED")[0].details == {"step": "ENROLLMENT"}
    assert _events(user.id, "MFA_ENROLLED")[0].details == {"replaced": False, "recovery_codes": 8}

    # Replacing the authenticator or the recovery codes needs the password and a fresh code, even now.
    clock["step"] += 1
    code = totp.current_code(secret)
    missing = client.post("/api/v1/auth/mfa/recovery-codes")
    assert missing.status_code == 403 and missing.json()["detail"]["code"] == "REAUTHENTICATION_REQUIRED"
    password_only = client.post("/api/v1/auth/mfa/recovery-codes", json={"password": PASSWORD})
    assert password_only.status_code == 403 and password_only.json()["detail"]["code"] == "REAUTHENTICATION_REQUIRED"
    code_only = client.post("/api/v1/auth/mfa/recovery-codes", json={"mfa_code": code})
    assert code_only.status_code == 403 and code_only.json()["detail"]["code"] == "REAUTHENTICATION_REQUIRED"
    wrong = client.post("/api/v1/auth/mfa/recovery-codes", json={"password": "not my password", "mfa_code": code})
    assert wrong.status_code == 403 and wrong.json()["detail"]["code"] == "REAUTHENTICATION_FAILED"
    assert _events(user.id, "MFA_FAILED")[-1].details == {"step": "REAUTHENTICATION"}
    # The wrong password did not spend the code.
    reissued = client.post("/api/v1/auth/mfa/recovery-codes", json={"password": PASSWORD, "mfa_code": code})
    assert reissued.status_code == 200, reissued.text
    assert _events(user.id, "MFA_RECOVERY_CODES_REGENERATED")[0].details == {"recovery_codes": 8}
    refused = client.post("/api/v1/auth/mfa/enroll")
    assert refused.status_code == 403 and refused.json()["detail"]["code"] == "REAUTHENTICATION_REQUIRED"
    clock["step"] += 1
    replacing = client.post(
        "/api/v1/auth/mfa/enroll", json={"password": PASSWORD, "mfa_code": totp.current_code(secret)}
    )
    assert replacing.status_code == 200, replacing.text
    replaced = client.post(
        "/api/v1/auth/mfa/verify-enrollment", json={"code": totp.current_code(replacing.json()["secret"])}
    )
    assert replaced.status_code == 200, replaced.text
    assert _events(user.id, "MFA_ENROLLED")[-1].details["replaced"] is True

    # A new sign-in owes a code: verified with a recovery code from the replaced set (none are valid) fails.
    second = TestClient(app)
    assert second.post("/api/v1/auth/signin", json={"email": user.username, "password": PASSWORD}).json()[
        "mfa_required"
    ]
    assert second.post("/api/v1/auth/mfa/verify", json={"code": recovery[0]}).status_code == 403
    assert _events(user.id, "SIGN_IN_SUCCEEDED")[-1].details == {"mfa": "VERIFY"}

    kinds = [notice["kind"] for notice in _notices(user.id)]
    assert kinds == ["MFA_ENROLLED", "MFA_RECOVERY_CODES_REGENERATED", "MFA_REPLACED"]
    _assert_nothing_secret(user, secret, PASSWORD, *recovery)


def test_a_verified_sign_in_and_a_used_recovery_code_are_audited():
    user = _user(role="Investigator")
    client, _ = _client_for(user)
    secret = client.post("/api/v1/auth/mfa/enroll").json()["secret"]
    recovery = client.post("/api/v1/auth/mfa/verify-enrollment", json={"code": totp.current_code(secret)}).json()[
        "recovery_codes"
    ]
    second = TestClient(app)
    second.post("/api/v1/auth/signin", json={"email": user.username, "password": PASSWORD})
    assert second.post("/api/v1/auth/mfa/verify", json={"code": _next_code(secret)}).status_code == 200
    assert _events(user.id, "MFA_VERIFIED")[-1].details == {"method": "AUTHENTICATOR"}
    third = TestClient(app)
    third.post("/api/v1/auth/signin", json={"email": user.username, "password": PASSWORD})
    assert third.post("/api/v1/auth/mfa/verify", json={"code": recovery[0]}).status_code == 200
    assert _events(user.id, "MFA_VERIFIED")[-1].details == {"method": "RECOVERY_CODE"}
    assert _events(user.id, "MFA_RECOVERY_CODE_USED")[-1].details == {"recovery_codes_left": 7}
    _assert_nothing_secret(user, secret, *recovery)


# ------------------------------------------------------------------------------------------- notice delivery


def test_a_notice_names_what_happened_never_the_new_value(monkeypatch):
    user = _user()
    sent = []
    monkeypatch.setattr(
        "auth.emailer._send", lambda recipient, message, **_: sent.append((recipient, message)) or "SENT"
    )
    with SessionLocal() as db:
        bind_system(db, "test: deliver a notice")
        payload = {
            "user_id": str(user.id),
            "kind": "MFA_REPLACED",
            "occurred_at": datetime.now(timezone.utc).isoformat(),
        }
        # The outbox worker's own entry point hands the event over.
        assert notifications.handle_event(db, "SECURITY_NOTICE", payload) is True
        assert security_notices.handle_security_notice(db, "SOMETHING_ELSE", payload) is False
        gone = {**payload, "user_id": str(uuid.uuid4())}
        assert security_notices.handle_security_notice(db, "SECURITY_NOTICE", gone) is True  # erased: nothing to send
    assert len(sent) == 1
    recipient, message = sent[0]
    assert recipient == user.username
    assert message.subject == security_notices.KINDS["MFA_REPLACED"][0]
    assert message.button is None  # no link to click in a security notice
    assert "If it was not you" in " ".join(message.closing)


def test_a_failed_delivery_is_retried_through_the_outbox(monkeypatch):
    user = _user()

    def refuse(*_args, **_kwargs):
        raise EmailDeliveryError("provider down")

    monkeypatch.setattr("auth.emailer._send", refuse)
    with SessionLocal() as db:
        bind_system(db, "test: deliver a notice")
        payload = {
            "user_id": str(user.id),
            "kind": "PASSWORD_CHANGED",
            "occurred_at": datetime.now(timezone.utc).isoformat(),
        }
        with pytest.raises(NotificationFailed):
            security_notices.handle_security_notice(db, "SECURITY_NOTICE", payload)


def test_an_unknown_notice_kind_is_refused():
    user = _user()
    with SessionLocal() as db, pytest.raises(ValueError):
        bind_system(db, "test: queue a notice")
        security_notices.queue_security_notice(db, db.get(AuthUser, user.id), "SOMETHING_" + secrets.token_hex(2))


def test_an_over_long_user_agent_cannot_dodge_the_lockout_or_break_sign_in(behind_proxy):
    user = _user()
    client = TestClient(app)
    headers = {"X-Forwarded-For": "203.0.113.42", "User-Agent": "u" * 2000}
    statuses = [
        client.post(
            "/api/v1/auth/signin", json={"email": user.username, "password": "wrong!"}, headers=headers
        ).status_code
        for _ in range(6)
    ]
    # Every failure was counted: the sixth attempt meets the lock, not another password check.
    assert statuses == [401] * 5 + [429]
    failed = _events(user.id, "SIGN_IN_FAILED")
    assert len(failed) == 5 and all(len(event.user_agent) == 512 for event in failed)
    ok = client.post(
        "/api/v1/auth/signin",
        json={"email": user.username, "password": PASSWORD},
        headers={"X-Forwarded-For": "198.51.100.42", "User-Agent": "u" * 2000},
    )
    assert ok.status_code == 200, ok.text
