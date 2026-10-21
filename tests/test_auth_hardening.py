"""Authentication hardening: rate limits, lockout, password changes, one-time links, MFA reset, scope and config."""

import hashlib
import secrets
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from starlette.requests import Request
from starlette.responses import Response

from auth import cookies
from auth.durable import consume, issue_invitation, issue_reset, new_session, peek
from auth.service import _hash
from backend.app import config_check
from backend.app.client_ip import client_ip
from backend.app.db.models.foundation import AuthUser, Tenant, TenantMembership
from backend.app.db.models.stage2 import AuthSession, OnboardingRequest
from backend.app.db.session import SessionLocal, runtime_engine, runtime_role_active
from backend.app.main import app
from genai import policy
from tests.conftest import authenticated_client
from tests.signup_profile import PROFILE

PASSWORD = "Hardening test password 2026"


def _tenant(db):
    return db.query(Tenant).filter(Tenant.tenant_key == "ACME_CARE_SYNTHETIC").first() or db.query(Tenant).first()


def _user(role: str = "Investigator", password: str = PASSWORD, password_hash: str | None = None) -> AuthUser:
    db = SessionLocal()
    try:
        tenant = _tenant(db)
        now = datetime.now(timezone.utc)
        user = AuthUser(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            username=f"hardening-{uuid.uuid4().hex[:10]}@example.invalid",
            display_name="Hardening Test",
            company="Test",
            password_hash=password_hash or _hash(password),
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
        db.refresh(user)
        db.expunge(user)
        return user
    finally:
        db.close()


def _client_for(user: AuthUser) -> tuple[TestClient, str]:
    db = SessionLocal()
    try:
        token = new_session(db, user.id, user.tenant_id)
    finally:
        db.close()
    client = TestClient(app)
    client.cookies.set("mdarix_session", token)
    return client, token


def _session_live(token: str) -> bool:
    db = SessionLocal()
    try:
        row = db.query(AuthSession).filter(AuthSession.session_hash == hashlib.sha256(token.encode()).hexdigest()).one()
        return row.revoked_at is None
    finally:
        db.close()


@pytest.fixture
def limits_on(monkeypatch):
    """Rate limits on, with a fresh salt so counters from other tests do not count."""
    monkeypatch.setenv("MDARIX_RATE_LIMITS_ENABLED", "true")
    monkeypatch.setenv("MDARIX_RATE_LIMIT_SALT", secrets.token_hex(16))


@pytest.fixture
def behind_proxy(monkeypatch):
    monkeypatch.setenv("MDARIX_TRUSTED_PROXY_HOPS", "1")


# ------------------------------------------------------------------------------------------- Sign-up


def test_signup_tells_a_known_or_repeated_email_to_sign_in_or_wait():
    client = TestClient(app)
    existing = _user()
    new_email = f"signup-{uuid.uuid4().hex[:10]}@example.invalid"
    body = {"display_name": "Person", "organization": "Org", **PROFILE}
    first = client.post("/api/v1/auth/signup", json={**body, "email": new_email})
    again = client.post("/api/v1/auth/signup", json={**body, "email": new_email})
    known = client.post("/api/v1/auth/signup", json={**body, "email": existing.username})
    assert first.status_code == 200 and "request_id" not in first.json()
    # Product decision 2026-10-11: a known email is told so, to sign in or reset the password (rate limits apply).
    assert again.status_code == 409 and again.json()["detail"]["code"] == "TRIAL_ALREADY_REQUESTED"
    assert known.status_code == 409 and known.json()["detail"]["code"] == "EMAIL_ALREADY_REGISTERED"
    assert "reset your password" in known.json()["detail"]["message"]
    db = SessionLocal()
    try:
        assert db.query(OnboardingRequest).filter(OnboardingRequest.email == new_email).count() == 1
        assert db.query(OnboardingRequest).filter(OnboardingRequest.email == existing.username).count() == 0
    finally:
        db.close()


def test_signup_is_rate_limited_per_address(limits_on, behind_proxy):
    client = TestClient(app)
    headers = {"X-Forwarded-For": "203.0.113.20"}
    for _ in range(5):
        email = f"limit-{uuid.uuid4().hex[:10]}@example.invalid"
        response = client.post(
            "/api/v1/auth/signup",
            json={"email": email, "display_name": "P", "organization": "O", **PROFILE},
            headers=headers,
        )
        assert response.status_code == 200
    refused = client.post(
        "/api/v1/auth/signup",
        json={
            "email": f"limit-{uuid.uuid4().hex[:10]}@example.invalid",
            "display_name": "P",
            "organization": "O",
            **PROFILE,
        },
        headers=headers,
    )
    assert refused.status_code == 429
    assert refused.json()["detail"]["code"] == "RATE_LIMITED"
    assert int(refused.headers["Retry-After"]) > 0
    # Another address is not affected.
    other = client.post(
        "/api/v1/auth/signup",
        json={
            "email": f"limit-{uuid.uuid4().hex[:10]}@example.invalid",
            "display_name": "P",
            "organization": "O",
            **PROFILE,
        },
        headers={"X-Forwarded-For": "198.51.100.20"},
    )
    assert other.status_code == 200


# ------------------------------------------------------------------------------------------- Sign-in


def test_wrong_passwords_lock_only_the_address_that_sent_them(behind_proxy):
    user = _user()
    client = TestClient(app)
    attacker = {"X-Forwarded-For": "203.0.113.30"}
    for _ in range(5):
        wrong = client.post("/api/v1/auth/signin", json={"email": user.username, "password": "wrong"}, headers=attacker)
        assert wrong.status_code == 401
    locked = client.post("/api/v1/auth/signin", json={"email": user.username, "password": PASSWORD}, headers=attacker)
    assert locked.status_code == 429
    assert locked.json()["detail"]["code"] == "ACCOUNT_TEMPORARILY_LOCKED"
    owner = TestClient(app).post(
        "/api/v1/auth/signin",
        json={"email": user.username, "password": PASSWORD},
        headers={"X-Forwarded-For": "198.51.100.30"},
    )
    assert owner.status_code == 200, owner.text


def test_unknown_email_and_wrong_password_give_the_same_answer():
    user = _user()
    client = TestClient(app)
    unknown = client.post(
        "/api/v1/auth/signin", json={"email": f"nobody-{uuid.uuid4().hex}@example.invalid", "password": "x" * 12}
    )
    wrong = client.post("/api/v1/auth/signin", json={"email": user.username, "password": "x" * 12})
    assert unknown.status_code == wrong.status_code == 401
    assert unknown.json() == wrong.json()


def test_signin_response_comes_from_the_database_and_sets_the_cookie():
    user = _user()
    client = TestClient(app)
    response = client.post("/api/v1/auth/signin", json={"email": user.username, "password": PASSWORD})
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["user_id"] == str(user.id) and body["tenant_id"] == str(user.tenant_id)
    assert body["email"] == user.username and body["active_role"] == user.role
    assert client.cookies.get("mdarix_session")


def test_a_legacy_password_hash_is_upgraded_at_sign_in():
    salt = secrets.token_bytes(16)
    legacy = salt.hex() + ":" + hashlib.scrypt(PASSWORD.encode(), salt=salt, n=2**14, r=8, p=1).hex()
    user = _user(password_hash=legacy)
    assert (
        TestClient(app).post("/api/v1/auth/signin", json={"email": user.username, "password": PASSWORD}).status_code
        == 200
    )
    db = SessionLocal()
    try:
        assert db.get(AuthUser, user.id).password_hash.startswith("scrypt$")
    finally:
        db.close()


def test_a_session_that_still_owes_mfa_lives_for_minutes_not_an_hour(monkeypatch):
    monkeypatch.setenv("MDARIX_REQUIRE_MFA_ROLES", "CUSTOMER_ADMIN")
    user = _user(role="CUSTOMER_ADMIN")
    client = TestClient(app)
    response = client.post("/api/v1/auth/signin", json={"email": user.username, "password": PASSWORD})
    assert response.status_code == 200 and response.json()["mfa_enrollment_required"] is True
    token = client.cookies.get("mdarix_session")
    db = SessionLocal()
    try:
        row = db.query(AuthSession).filter(AuthSession.session_hash == hashlib.sha256(token.encode()).hexdigest()).one()
        assert (row.expires_at - row.created_at).total_seconds() <= cookies.PENDING_MFA_SECONDS
    finally:
        db.close()
    # The pending session cannot use the application.
    assert client.get("/api/v1/me/context").status_code == 403


# ------------------------------------------------------------------------------------------- Passwords


def test_change_password_checks_the_current_one_and_the_rules():
    user = _user()
    client, _token = _client_for(user)
    wrong = client.post(
        "/api/v1/auth/change-password", json={"current_password": "not it", "new_password": "A brand new passphrase 1"}
    )
    assert wrong.status_code == 403 and wrong.json()["detail"]["code"] == "INVALID_CURRENT_PASSWORD"
    breached = client.post(
        "/api/v1/auth/change-password", json={"current_password": PASSWORD, "new_password": "password1234"}
    )
    assert breached.status_code == 422 and breached.json()["detail"]["code"] == "PASSWORD_BREACHED"
    reused = client.post("/api/v1/auth/change-password", json={"current_password": PASSWORD, "new_password": PASSWORD})
    assert reused.status_code == 422 and reused.json()["detail"]["code"] == "PASSWORD_REUSE_NOT_ALLOWED"


def test_change_password_signs_out_other_sessions_and_keeps_this_one():
    user = _user()
    client, token = _client_for(user)
    _other_client, other_token = _client_for(user)
    new_password = "Another long passphrase 2026"
    changed = client.post(
        "/api/v1/auth/change-password", json={"current_password": PASSWORD, "new_password": new_password}
    )
    assert changed.status_code == 200, changed.text
    assert changed.json()["other_sessions_signed_out"] == 1
    assert _session_live(token) and not _session_live(other_token)
    signin = TestClient(app)
    assert signin.post("/api/v1/auth/signin", json={"email": user.username, "password": PASSWORD}).status_code == 401
    assert (
        signin.post("/api/v1/auth/signin", json={"email": user.username, "password": new_password}).status_code == 200
    )
    db = SessionLocal()
    try:
        assert db.get(AuthUser, user.id).password_expires_at is None  # no periodic expiry
    finally:
        db.close()


def test_change_password_counts_only_the_other_sessions_still_live():
    """NEW-5: sessions that had already expired or gone idle are no longer counted as "signed out"."""
    user = _user()
    client, token = _client_for(user)
    _live_client, live_token = _client_for(user)
    expired, idle = _client_for(user)[1], _client_for(user)[1]
    now = datetime.now(timezone.utc)
    db = SessionLocal()
    try:
        by_hash = lambda raw: AuthSession.session_hash == hashlib.sha256(raw.encode()).hexdigest()  # noqa: E731
        db.query(AuthSession).filter(by_hash(expired)).update({"expires_at": now - timedelta(minutes=1)})
        db.query(AuthSession).filter(by_hash(idle)).update({"last_seen_at": now - timedelta(hours=2)})
        db.commit()
    finally:
        db.close()
    changed = client.post(
        "/api/v1/auth/change-password",
        json={"current_password": PASSWORD, "new_password": "A fourth long passphrase 2026"},
    )
    assert changed.status_code == 200, changed.text
    assert changed.json()["other_sessions_signed_out"] == 1
    # Every other session is ended all the same; this one stays.
    assert _session_live(token) and not any(_session_live(raw) for raw in (live_token, expired, idle))


def test_a_refused_password_leaves_the_reset_link_usable_and_success_ends_every_session():
    user = _user()
    _client, live_token = _client_for(user)
    db = SessionLocal()
    try:
        raw = issue_reset(db, user.id, user.tenant_id)
    finally:
        db.close()
    client = TestClient(app)
    refused = client.post("/api/v1/auth/reset-password", json={"token": raw, "password": "password1234"})
    assert refused.status_code == 422
    done = client.post("/api/v1/auth/reset-password", json={"token": raw, "password": "A fresh secure passphrase 7"})
    assert done.status_code == 200, done.text
    assert not _session_live(live_token)
    again = client.post("/api/v1/auth/reset-password", json={"token": raw, "password": "A fresh secure passphrase 8"})
    assert again.status_code == 400


def test_invitations_last_48_hours_and_a_new_one_replaces_the_old():
    user = _user()
    db = SessionLocal()
    try:
        first = issue_invitation(db, user.id, user.tenant_id)
        second = issue_invitation(db, user.id, user.tenant_id)
        with pytest.raises(ValueError):
            peek(db, first, "activation")
        assert peek(db, second, "activation") == str(user.id)
        hours = db.execute(
            text(
                "SELECT extract(epoch FROM expires_at - created_at) / 3600 FROM user_invitations WHERE token_hash = :h"
            ),
            {"h": hashlib.sha256(second.encode()).hexdigest()},
        ).scalar()
        assert round(float(hours)) == 48
        assert consume(db, second, "activation") == str(user.id)
    finally:
        db.close()


# ------------------------------------------------------------------------------------------- MFA reset


def test_a_customer_admin_resets_a_users_mfa_but_not_their_own():
    tenant_admin = _user(role="CUSTOMER_ADMIN")
    member = _user(role="Investigator")
    admin_client, _ = _client_for(tenant_admin)
    _member_client, member_token = _client_for(member)
    db = SessionLocal()
    try:
        row = db.get(AuthUser, member.id)
        row.mfa_secret_encrypted = "sealed"
        row.mfa_enrolled_at = datetime.now(timezone.utc)
        db.commit()
    finally:
        db.close()
    own = admin_client.post(f"/api/v1/admin/identity/users/{tenant_admin.id}/mfa-reset", json={"reason": "Lost phone"})
    assert own.status_code == 409
    done = admin_client.post(f"/api/v1/admin/identity/users/{member.id}/mfa-reset", json={"reason": "Lost phone"})
    assert done.status_code == 200, done.text
    assert not _session_live(member_token)
    db = SessionLocal()
    try:
        row = db.get(AuthUser, member.id)
        assert row.mfa_secret_encrypted is None and row.mfa_enrolled_at is None
    finally:
        db.close()


def test_only_platform_admins_reset_mfa_across_organizations():
    member = _user(role="Investigator")
    viewer_client, _ = _client_for(_user(role="Viewer"))
    assert (
        viewer_client.post(
            f"/api/v1/platform-admin/users/{member.id}/mfa-reset", json={"reason": "Lost phone"}
        ).status_code
        == 403
    )
    from tests.support_grants import grant_support_access

    grant_support_access(member.tenant_id, areas=("PEOPLE",))  # the organization approved People access
    response = authenticated_client().post(
        f"/api/v1/platform-admin/users/{member.id}/mfa-reset", json={"reason": "Lost phone"}
    )
    assert response.status_code == 200, response.text


# ------------------------------------------------------------------------------------------- Request plumbing


def _request(headers: dict, peer: str = "10.0.0.5") -> Request:
    return Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/",
            "headers": [(key.lower().encode(), value.encode()) for key, value in headers.items()],
            "query_string": b"",
            "client": (peer, 1234),
        }
    )


def test_client_ip_trusts_only_the_hops_our_proxies_added(monkeypatch):
    monkeypatch.delenv("MDARIX_TRUST_PROXY_HEADERS", raising=False)
    monkeypatch.setenv("MDARIX_TRUSTED_PROXY_HOPS", "0")
    assert client_ip(_request({"X-Forwarded-For": "1.2.3.4"})) == "10.0.0.5"
    monkeypatch.setenv("MDARIX_TRUSTED_PROXY_HOPS", "1")
    # The client wrote 6.6.6.6 itself; our proxy appended the real address 203.0.113.9.
    assert client_ip(_request({"X-Forwarded-For": "6.6.6.6, 203.0.113.9"})) == "203.0.113.9"
    assert client_ip(_request({"X-Forwarded-For": "not-an-ip"})) == "10.0.0.5"


def test_every_response_carries_a_request_id_and_bad_ones_are_replaced():
    client = TestClient(app)
    kept = client.get("/health/live", headers={"X-Request-ID": "abc12345-req"})
    assert kept.headers["X-Request-ID"] == "abc12345-req"
    replaced = client.get("/health/live", headers={"X-Request-ID": "bad id with spaces and <script>"})
    assert replaced.headers["X-Request-ID"] != "bad id with spaces and <script>"


def test_sign_in_from_another_site_is_refused_in_production(monkeypatch):
    monkeypatch.setenv("MDARIX_ENV", "production")
    monkeypatch.setenv("MDARIX_APP_URL", "https://app.example.com")
    client = TestClient(app)
    response = client.post(
        "/api/v1/auth/signin",
        json={"email": "a@example.invalid", "password": "x" * 12},
        headers={"Origin": "https://evil.example.net"},
    )
    assert response.status_code == 403 and response.json()["detail"]["code"] == "CSRF_ORIGIN_DENIED"


def test_the_production_session_cookie_is_host_bound_and_secure(monkeypatch):
    monkeypatch.setenv("MDARIX_ENV", "production")
    response = Response()
    cookies.set_session_cookie(response, "token-value")
    header = response.headers["set-cookie"]
    assert header.startswith("__Host-mdarix_session=token-value")
    assert "Secure" in header and "HttpOnly" in header and "Path=/" in header and "Domain" not in header
    # Strict: only requests MDARIX's own pages make carry the session (no cross-site request ever does).
    assert "SameSite=strict" in header or "SameSite=Strict" in header


# ------------------------------------------------------------------------------------------- Configuration


def test_production_lists_every_missing_setting(monkeypatch):
    monkeypatch.setenv("MDARIX_ENV", "production")
    for name in (
        "MDARIX_APP_URL",
        "MDARIX_DB_RUNTIME_USER",
        "MDARIX_MFA_ENCRYPTION_KEY",
        "MDARIX_CONNECTOR_ENCRYPTION_KEY",
        "MDARIX_RLS_SYSTEM_TOKEN",
        "MDARIX_SMTP_HOST",
        "MDARIX_COMPANY_LEGAL_NAME",
    ):
        monkeypatch.delenv(name, raising=False)
    found = "\n".join(config_check.problems())
    for name in (
        "MDARIX_APP_URL",
        "MDARIX_DB_RUNTIME_USER",
        "MDARIX_MFA_ENCRYPTION_KEY",
        "MDARIX_RLS_SYSTEM_TOKEN",
        "MDARIX_SMTP_HOST",
        "MDARIX_COMPANY_LEGAL_NAME",
        "POSTGRES_SSLMODE",
    ):
        assert name in found
    with pytest.raises(SystemExit):
        config_check.enforce()


def test_production_refuses_the_public_local_system_token(monkeypatch):
    from backend.app.db.tenant_scope import LOCAL_SYSTEM_TOKEN

    monkeypatch.setenv("MDARIX_ENV", "production")
    monkeypatch.setenv("MDARIX_RLS_SYSTEM_TOKEN", LOCAL_SYSTEM_TOKEN)
    assert any("public local-development value" in item for item in config_check.problems())


def test_local_development_is_never_blocked(monkeypatch):
    monkeypatch.setenv("MDARIX_ENV", "development")
    assert config_check.problems() == []


def test_production_ai_goes_only_to_contracted_or_self_hosted_providers(monkeypatch):
    monkeypatch.setenv("MDARIX_ENV", "production")
    monkeypatch.setenv("MDARIX_GENAI_PROVIDER", "groq")
    monkeypatch.setenv("MDARIX_GENAI_FALLBACKS", "openrouter,ollama")
    monkeypatch.delenv("MDARIX_GENAI_CONTRACTED_PROVIDERS", raising=False)
    problems = policy.configuration_problems()
    assert any("uses groq" in item for item in problems) and any("uses openrouter" in item for item in problems)
    assert not any("uses ollama" in item for item in problems)
    monkeypatch.setenv("MDARIX_GENAI_CONTRACTED_PROVIDERS", "groq,openrouter")
    problems = policy.configuration_problems()
    assert not any("uses groq" in item for item in problems)
    assert any("uses openrouter" in item and "free" in item for item in problems)  # a ':free' model stays refused
    assert policy.allowed("ollama") and not policy.allowed("gemini")
    monkeypatch.setenv("MDARIX_ENV", "development")
    assert policy.allowed("gemini")


@pytest.mark.skipif(not runtime_role_active(), reason="needs the least-privilege runtime role")
def test_the_application_role_cannot_open_system_scope_by_itself():
    with runtime_engine.connect() as connection:
        connection.execute(text("SELECT set_config('app.rls_bypass', 'on', true)"))
        assert connection.execute(text("SELECT public.mdarix_system_scope()")).scalar() is False
        assert connection.execute(text("SELECT count(*) FROM auth_users")).scalar() == 0
        connection.rollback()
        with pytest.raises(Exception):
            connection.execute(text("SELECT token_hash FROM mdarix_rls_secret")).all()
