"""Limits around authentication: the per-account sign-in limit counts failures only, authentication limits fail
closed in production, password hashing is bounded in parallel, and the roles that must use MFA."""

import secrets
import threading
import time
import uuid

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from auth import service
from backend.app import mfa, rate_limit
from backend.app.db import session as db_session
from backend.app.main import app
from backend.app.role_codes import CUSTOMER_ADMIN, PLATFORM_ADMIN
from tests.test_auth_hardening import PASSWORD, _user


@pytest.fixture
def limits_on(monkeypatch):
    monkeypatch.setenv("MDARIX_RATE_LIMITS_ENABLED", "true")
    monkeypatch.setenv("MDARIX_RATE_LIMIT_SALT", secrets.token_hex(16))
    monkeypatch.setenv("MDARIX_TRUSTED_PROXY_HOPS", "1")


# ------------------------------------------------------------------------------------------- signin:account


def _signin(client, email, password, address):
    return client.post(
        "/api/v1/auth/signin", json={"email": email, "password": password}, headers={"X-Forwarded-For": address}
    )


def test_correct_passwords_never_count_against_the_account(limits_on):
    user = _user()
    client = TestClient(app)
    limit = rate_limit.LIMITS["signin:account"].limit
    for n in range(limit + 2):
        assert _signin(client, user.username, PASSWORD, f"198.51.100.{n + 1}").status_code == 200


def test_wrong_passwords_from_many_addresses_hit_the_account_limit_but_not_the_owner(limits_on):
    user = _user()
    client = TestClient(app)
    limit = rate_limit.LIMITS["signin:account"].limit
    # One attempt per address, so the per-address lockout never triggers: only the account limit can.
    statuses = [
        _signin(client, user.username, "wrong password!", f"203.0.113.{n + 1}").status_code for n in range(limit)
    ]
    assert statuses == [401] * limit
    refused = _signin(client, user.username, "wrong password!", "203.0.113.200")
    assert refused.status_code == 429 and refused.json()["detail"]["code"] == "RATE_LIMITED"
    # The owner, with the right password, is not locked out by someone else's guessing.
    assert _signin(client, user.username, PASSWORD, "192.0.2.10").status_code == 200


# ------------------------------------------------------------------------------------------- fail closed


class _BrokenEngine:
    def begin(self):
        raise RuntimeError("counter store unavailable")


def test_authentication_limits_fail_closed_in_production_and_others_fail_open(monkeypatch):
    monkeypatch.setenv("MDARIX_RATE_LIMITS_ENABLED", "true")
    monkeypatch.setattr(db_session, "runtime_engine", _BrokenEngine())
    monkeypatch.setenv("MDARIX_ENV", "production")
    for scope in sorted(rate_limit.AUTH_SCOPES):
        with pytest.raises(HTTPException) as refused:
            rate_limit.enforce(scope, "someone@example.invalid")
        assert refused.value.status_code == 503
        assert refused.value.detail["code"] == "RATE_LIMITER_UNAVAILABLE"
        assert refused.value.headers["Retry-After"] == "60"
    assert rate_limit.enforce("feedback:user", "someone") is None
    assert rate_limit.enforce("client-errors:ip", "203.0.113.1") is None
    # Local development is never blocked by a broken counter.
    monkeypatch.setenv("MDARIX_ENV", "development")
    assert rate_limit.enforce("signin:ip", "203.0.113.1") is None


def test_every_authentication_scope_is_listed_as_one():
    prefixes = ("signin:", "signup:", "forgot:", "token:", "mfa:", "password-change:")
    auth_like = {scope for scope in rate_limit.LIMITS if scope.startswith(prefixes)}
    assert auth_like == set(rate_limit.AUTH_SCOPES)
    assert set(rate_limit.AUTH_SCOPES) <= set(rate_limit.LIMITS)


# ------------------------------------------------------------------------------------------- password hashing


@pytest.mark.parametrize(("value", "expected"), [(None, 3), ("5", 5), ("0", 1), ("-4", 1), ("1000", 64), ("x", 3)])
def test_hash_concurrency_setting(monkeypatch, value, expected):
    if value is None:
        monkeypatch.delenv("MDARIX_PASSWORD_HASH_CONCURRENCY", raising=False)
    else:
        monkeypatch.setenv("MDARIX_PASSWORD_HASH_CONCURRENCY", value)
    assert service._hash_concurrency() == expected


def test_no_more_password_hashes_run_at_once_than_allowed(monkeypatch):
    running = 0
    peak = 0
    lock = threading.Lock()

    def slow_scrypt(*_args, **_kwargs):
        nonlocal running, peak
        with lock:
            running += 1
            peak = max(peak, running)
        time.sleep(0.05)
        with lock:
            running -= 1
        return b"\0" * 64

    monkeypatch.setattr(service, "_HASH_SLOTS", threading.BoundedSemaphore(2))
    monkeypatch.setattr(service.hashlib, "scrypt", slow_scrypt)
    threads = [threading.Thread(target=service._scrypt, args=("pw", b"salt", 10, 8, 1)) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert peak == 2


# ------------------------------------------------------------------------------------------- MFA policy


def test_outside_local_development_administrators_leaders_and_approvers_must_use_mfa(monkeypatch):
    monkeypatch.delenv("MDARIX_REQUIRE_MFA_ROLES", raising=False)
    monkeypatch.setenv("MDARIX_ENV", "production")
    assert mfa.required_roles() == {PLATFORM_ADMIN, CUSTOMER_ADMIN, "LEADER", "APPROVER"}

    class Account:
        mfa_enrolled_at = None
        mfa_secret_encrypted = None

        def __init__(self, role):
            self.role = role

    for role in ("Administrator", "Customer Admin", "Leader", "approver"):
        assert mfa.session_state_for(Account(role)) == "ENROLL", role
    for role in ("Investigator", "Viewer", "Reviewer"):
        assert mfa.session_state_for(Account(role)) is None, role


def test_local_development_requires_no_mfa_unless_configured(monkeypatch):
    monkeypatch.delenv("MDARIX_REQUIRE_MFA_ROLES", raising=False)
    monkeypatch.setenv("MDARIX_ENV", "development")
    assert mfa.required_roles() == set()
    monkeypatch.setenv("MDARIX_REQUIRE_MFA_ROLES", "admin, customer-administrator ,Reviewer")
    assert mfa.required_roles() == {PLATFORM_ADMIN, CUSTOMER_ADMIN, "REVIEWER"}


def test_an_unknown_email_still_spends_one_password_check(monkeypatch):
    calls = []
    real = service._verify
    monkeypatch.setattr(service, "_verify", lambda password, stored: calls.append(stored) or real(password, stored))
    response = TestClient(app).post(
        "/api/v1/auth/signin", json={"email": f"nobody-{uuid.uuid4().hex}@example.invalid", "password": "x" * 12}
    )
    assert response.status_code == 401 and len(calls) == 1
