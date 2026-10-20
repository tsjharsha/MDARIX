"""Authenticator-app MFA: enrollment, sign-in second factor, recovery codes, attempt limits and the signature gate."""

import time
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient

from auth import totp
from auth.service import _hash
from backend.app.db.models.foundation import HumanReview, AuthUser, Decision, Investigation, Tenant, TenantMembership
from backend.app.db.models.stage2 import LoginThrottle
from backend.app.db.session import SessionLocal
from backend.app.db.tenant_scope import bind_system
from backend.app.main import app

PASSWORD = "Mfa-Test-Password-2026!"


def _make_user(role="APPROVER") -> str:
    email = f"mfa-{uuid.uuid4().hex[:10]}@example.invalid"
    with SessionLocal() as db:
        bind_system(db, "test: MFA user")
        tenant = db.query(Tenant).filter(Tenant.tenant_key == "ACME_CARE_SYNTHETIC").first() or db.query(Tenant).first()
        now = datetime.now(timezone.utc)
        user = AuthUser(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            username=email,
            display_name="MFA user",
            company="Test",
            password_hash=_hash(PASSWORD),
            role=role,
            status="ACTIVE",
            email_verified=True,
            created_at=now,
            updated_at=now,
        )
        db.add(user)
        db.flush()
        db.add(
            TenantMembership(
                id=uuid.uuid4(),
                tenant_id=tenant.id,
                user_id=user.id,
                status="ACTIVE",
                is_default=True,
                created_at=now,
                updated_at=now,
            )
        )
        db.commit()
    return email


def _sign_in(email: str) -> tuple[TestClient, dict]:
    client = TestClient(app)
    response = client.post("/api/v1/auth/signin", json={"email": email, "password": PASSWORD})
    assert response.status_code == 200, response.text
    return client, response.json()


def _enroll(client: TestClient) -> tuple[str, list[str]]:
    started = client.post("/api/v1/auth/mfa/enroll").json()
    assert started["otpauth_uri"].startswith("otpauth://totp/MDARIX:")
    secret = started["secret"]
    done = client.post("/api/v1/auth/mfa/verify-enrollment", json={"code": totp.current_code(secret)})
    assert done.status_code == 200 and done.json()["status"] == "MFA_ENROLLED"
    return secret, done.json()["recovery_codes"]


def _next_code(secret: str) -> str:
    # The code of the next 30-second step: inside the drift window, and newer than the one just used.
    return totp.code_at(secret, int(time.time() // 30) + 1)


def test_enrollment_needs_a_correct_code_and_stores_the_secret_encrypted():
    client, _ = _sign_in(_make_user())
    started = client.post("/api/v1/auth/mfa/enroll").json()
    wrong = client.post("/api/v1/auth/mfa/verify-enrollment", json={"code": "000000"})
    assert wrong.status_code == 403 and wrong.json()["detail"]["code"] == "MFA_CODE_INVALID"
    done = client.post("/api/v1/auth/mfa/verify-enrollment", json={"code": totp.current_code(started["secret"])})
    assert done.status_code == 200 and len(done.json()["recovery_codes"]) == 8
    with SessionLocal() as db:
        bind_system(db, "test: read user")
        user = db.query(AuthUser).filter(AuthUser.id == uuid.UUID(done.json()["user_id"])).one()
        assert user.mfa_secret_encrypted and started["secret"] not in user.mfa_secret_encrypted
        assert user.mfa_pending_secret_encrypted is None
        assert all(code not in str(user.mfa_recovery_hashes) for code in done.json()["recovery_codes"])


def test_an_enrolled_user_must_enter_a_code_before_the_session_can_do_anything():
    email = _make_user()
    client, _ = _sign_in(email)
    secret, recovery = _enroll(client)
    second, body = _sign_in(email)
    assert body["mfa_required"] is True
    blocked = second.get("/api/v1/session/context")
    assert blocked.status_code == 403 and blocked.json()["detail"]["code"] == "MFA_REQUIRED"
    assert second.get("/api/v1/auth/session").json()["mfa_state"] == "VERIFY"
    # A stolen password alone cannot replace the authenticator.
    assert second.post("/api/v1/auth/mfa/enroll").status_code == 403
    code = _next_code(secret)
    assert second.post("/api/v1/auth/mfa/verify", json={"code": code}).status_code == 200
    assert second.get("/api/v1/session/context").status_code == 200
    # The same code cannot be used again (replay).
    third, _ = _sign_in(email)
    assert third.post("/api/v1/auth/mfa/verify", json={"code": code}).status_code == 403
    # A recovery code works once.
    assert third.post("/api/v1/auth/mfa/verify", json={"code": recovery[0]}).status_code == 200
    fourth, _ = _sign_in(email)
    assert fourth.post("/api/v1/auth/mfa/verify", json={"code": recovery[0]}).status_code == 403


def test_five_wrong_codes_lock_mfa_for_a_while():
    email = _make_user()
    client, _ = _sign_in(email)
    secret, _ = _enroll(client)
    second, _ = _sign_in(email)
    statuses = [second.post("/api/v1/auth/mfa/verify", json={"code": "123456"}).status_code for _ in range(6)]
    assert statuses[:5] == [403] * 5 and statuses[5] == 429
    locked = second.post("/api/v1/auth/mfa/verify", json={"code": _next_code(secret)})
    assert locked.status_code == 429 and locked.json()["detail"]["code"] == "MFA_TEMPORARILY_LOCKED"


def test_policy_makes_administrators_set_up_mfa_before_anything_else(monkeypatch):
    monkeypatch.setenv("MDARIX_REQUIRE_MFA_ROLES", "PLATFORM_ADMIN,CUSTOMER_ADMIN")
    client, body = _sign_in(_make_user(role="CUSTOMER_ADMIN"))
    assert body["mfa_enrollment_required"] is True
    blocked = client.get("/api/v1/admin/identity/users")
    assert blocked.status_code == 403 and blocked.json()["detail"]["code"] == "MFA_ENROLLMENT_REQUIRED"
    _enroll(client)
    assert client.get("/api/v1/admin/identity/users").status_code == 200
    # A business role is not affected by the administrator policy.
    _, plain = _sign_in(_make_user(role="INVESTIGATOR"))
    assert plain["mfa_required"] is False and plain["mfa_enrollment_required"] is False


def test_an_idle_session_ends_on_the_server(monkeypatch):
    client, _ = _sign_in(_make_user(role="INVESTIGATOR"))
    assert client.get("/api/v1/session/context").status_code == 200
    with SessionLocal() as db:
        from backend.app.auth_router import hash_token
        from backend.app.db.models.stage2 import AuthSession

        bind_system(db, "test: age a session")
        db.query(AuthSession).filter(
            AuthSession.session_hash == hash_token(client.cookies.get("mdarix_session"))
        ).update({AuthSession.last_seen_at: datetime.now(timezone.utc) - timedelta(minutes=31)})
        db.commit()
    expired = client.get("/api/v1/session/context")
    assert expired.status_code == 401 and expired.json()["detail"]["code"] == "SESSION_IDLE_TIMEOUT"
    assert client.get("/api/v1/session/context").status_code == 401  # revoked, not just refused once


def test_a_background_read_does_not_keep_an_idle_session_alive():
    # A page's own poll (the trial's chapter banner) is served but is no activity: the idle timeout still ends it.
    from backend.app.auth_router import hash_token
    from backend.app.db.models.stage2 import AuthSession

    client, _ = _sign_in(_make_user(role="INVESTIGATOR"))
    assert client.get("/api/v1/session/context").status_code == 200
    session_hash = hash_token(client.cookies.get("mdarix_session"))
    aged = datetime.now(timezone.utc) - timedelta(minutes=20)
    with SessionLocal() as db:
        bind_system(db, "test: age a session")
        db.query(AuthSession).filter(AuthSession.session_hash == session_hash).update({AuthSession.last_seen_at: aged})
        db.commit()
    background = {"X-MDARIX-Background": "1"}
    assert client.get("/api/v1/session/context", headers=background).status_code == 200
    with SessionLocal() as db:
        bind_system(db, "test: read the session")
        row = db.query(AuthSession).filter(AuthSession.session_hash == session_hash).one()
        assert abs((row.last_seen_at - aged).total_seconds()) < 1  # the idle window did not restart
        db.query(AuthSession).filter(AuthSession.session_hash == session_hash).update(
            {AuthSession.last_seen_at: datetime.now(timezone.utc) - timedelta(minutes=31)}
        )
        db.commit()
    expired = client.get("/api/v1/session/context", headers=background)
    assert expired.status_code == 401 and expired.json()["detail"]["code"] == "SESSION_IDLE_TIMEOUT"


@pytest.fixture
def decision():
    with SessionLocal() as db:
        bind_system(db, "test: decision to sign")
        tenant = db.query(Tenant).filter(Tenant.tenant_key == "ACME_CARE_SYNTHETIC").first()
        investigation = db.query(Investigation).filter(Investigation.tenant_id == tenant.id).first()
        now = datetime.now(timezone.utc)
        row = Decision(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            investigation_id=investigation.id,
            decision_identifier=f"MFA-{uuid.uuid4().hex[:10]}",
            decision_type="INVESTIGATION_REVIEW",
            disposition="REQUIRES_REVIEW",
            rationale="MFA gate",
            decision_status="REQUIRES_REVIEW",
            authorized_by_ref="someone-else",
            updated_at=now,
            decision_timestamp=now,
            created_at=now,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        yield row
        db.query(HumanReview).filter(HumanReview.decision_id == row.id).delete(synchronize_session=False)
        db.query(Decision).filter(Decision.id == row.id).delete(synchronize_session=False)
        db.commit()


def _sign(client, decision, password=PASSWORD, code=None):
    body = {
        "decision": "APPROVE",
        "remarks": "Reviewed",
        "password": password,
        "object_version": decision.updated_at.isoformat(),
    }
    if code:
        body["mfa_code"] = code
    return client.post(f"/api/v1/governance/decisions/{decision.id}/sign", json=body)


def test_signing_needs_an_enrolled_authenticator_and_a_fresh_code(monkeypatch, decision):
    monkeypatch.setenv("MDARIX_REQUIRE_MFA_FOR_SIGNATURES", "true")
    email = _make_user(role="APPROVER")
    client, _ = _sign_in(email)
    not_enrolled = _sign(client, decision)
    assert not_enrolled.status_code == 403 and not_enrolled.json()["detail"]["code"] == "MFA_ENROLLMENT_REQUIRED"
    secret, _ = _enroll(client)
    no_code = _sign(client, decision)
    assert no_code.status_code == 403 and no_code.json()["detail"]["code"] == "MFA_REQUIRED"
    signed = _sign(client, decision, code=_next_code(secret))
    assert signed.status_code == 200, signed.text


def test_wrong_passwords_at_signing_are_limited(monkeypatch, decision):
    monkeypatch.setenv("MDARIX_REQUIRE_MFA_FOR_SIGNATURES", "false")
    client, _ = _sign_in(_make_user(role="APPROVER"))
    statuses = [_sign(client, decision, password=f"wrong-password-{n}").status_code for n in range(6)]
    assert statuses[:5] == [403] * 5 and statuses[5] == 429
    locked = _sign(client, decision)
    assert locked.status_code == 429 and locked.json()["detail"]["code"] == "SIGNATURE_TEMPORARILY_LOCKED"
    with SessionLocal() as db:
        db.query(LoginThrottle).filter(LoginThrottle.identifier.like("sign:%")).delete(synchronize_session=False)
        db.commit()
