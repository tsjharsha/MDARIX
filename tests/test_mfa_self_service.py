"""Two-factor sign-in that the person manages themselves (My Account, Security): new recovery codes, and replacing the
authenticator app. Both need the current password AND a fresh authenticator code, even from a fully signed-in
session; both are audited and reported to the person by email; the old codes or the old authenticator stop working
in the same transaction."""

import hashlib
import secrets
import time

import pytest
from fastapi.testclient import TestClient

from auth import totp
from backend.app.db.models.foundation import AuthUser
from backend.app.db.session import SessionLocal
from backend.app.db.tenant_scope import bind_system
from backend.app.main import app
from tests.test_auth_audit_events import _assert_nothing_secret, _events, _notices
from tests.test_auth_hardening import PASSWORD, _client_for, _user


@pytest.fixture
def clock(monkeypatch):
    """The authenticator's clock, held still: each code below belongs to a known 30-second step."""
    state = {"step": int(time.time() // 30)}
    monkeypatch.setattr(totp, "_step", lambda at=None: state["step"])
    return state


def _code(clock, secret: str) -> str:
    """A fresh code: the next step, so it was never used before."""
    clock["step"] += 1
    return totp.current_code(secret)


def _enrolled(clock, role: str = "Investigator"):
    user = _user(role=role)
    client, token = _client_for(user)
    secret = client.post("/api/v1/auth/mfa/enroll").json()["secret"]
    done = client.post("/api/v1/auth/mfa/verify-enrollment", json={"code": totp.current_code(secret)})
    assert done.status_code == 200, done.text
    return user, client, token, secret, done.json()["recovery_codes"]


def _sign_in(user) -> TestClient:
    client = TestClient(app)
    response = client.post("/api/v1/auth/signin", json={"email": user.username, "password": PASSWORD})
    assert response.status_code == 200 and response.json()["mfa_required"], response.text
    return client


def _stored_hashes(user) -> list[str]:
    with SessionLocal() as db:
        bind_system(db, "test: recovery code hashes")
        return list(db.get(AuthUser, user.id).mfa_recovery_hashes or [])


# ------------------------------------------------------------------------------------------- recovery codes


def test_new_recovery_codes_replace_the_old_ones_and_each_works_once(clock):
    user, client, _token, secret, old_codes = _enrolled(clock)
    response = client.post(
        "/api/v1/auth/mfa/recovery-codes", json={"password": PASSWORD, "mfa_code": _code(clock, secret)}
    )
    assert response.status_code == 200, response.text
    body = response.json()
    new_codes = body["recovery_codes"]
    assert body["status"] == "RECOVERY_CODES_ISSUED" and len(new_codes) == 8 and len(set(new_codes)) == 8
    assert not set(new_codes) & set(old_codes)
    assert response.headers["cache-control"] == "no-store"

    # Only hashes are stored, never the codes themselves.
    stored = _stored_hashes(user)
    assert stored == [hashlib.sha256(code.encode()).hexdigest() for code in new_codes]
    assert not any(code in " ".join(stored) for code in new_codes)

    # An old code no longer signs in; a new one does, once.
    assert _sign_in(user).post("/api/v1/auth/mfa/verify", json={"code": old_codes[0]}).status_code == 403
    fresh = _sign_in(user)
    used = fresh.post("/api/v1/auth/mfa/verify", json={"code": new_codes[0]})
    assert used.status_code == 200 and used.json()["recovery_codes_left"] == 7
    assert _sign_in(user).post("/api/v1/auth/mfa/verify", json={"code": new_codes[0]}).status_code == 403

    assert _events(user.id, "MFA_RECOVERY_CODES_REGENERATED")[-1].details == {"recovery_codes": 8}
    assert [notice["kind"] for notice in _notices(user.id)] == ["MFA_ENROLLED", "MFA_RECOVERY_CODES_REGENERATED"]
    _assert_nothing_secret(user, secret, PASSWORD, *old_codes, *new_codes)


def test_new_recovery_codes_are_refused_without_both_the_password_and_an_authenticator_code(clock):
    user, client, _token, secret, old_codes = _enrolled(clock)
    before = _stored_hashes(user)
    code = _code(clock, secret)
    attempts = [
        ({}, "REAUTHENTICATION_REQUIRED"),
        ({"password": PASSWORD}, "REAUTHENTICATION_REQUIRED"),
        ({"mfa_code": code}, "REAUTHENTICATION_REQUIRED"),
        ({"password": "Not the password 2026", "mfa_code": code}, "REAUTHENTICATION_FAILED"),
        ({"password": PASSWORD, "mfa_code": "000000" if code != "000000" else "111111"}, "REAUTHENTICATION_FAILED"),
        # A recovery code is not an authenticator code here.
        ({"password": PASSWORD, "mfa_code": old_codes[0]}, "REAUTHENTICATION_FAILED"),
    ]
    for body, expected in attempts:
        refused = client.post("/api/v1/auth/mfa/recovery-codes", json=body)
        assert refused.status_code == 403 and refused.json()["detail"]["code"] == expected, body
        assert "recovery_codes" not in refused.json()
    assert _stored_hashes(user) == before  # nothing changed, and the recovery code tried was not spent
    assert _events(user.id, "MFA_RECOVERY_CODES_REGENERATED") == []
    assert [event.details for event in _events(user.id, "MFA_FAILED")] == [{"step": "REAUTHENTICATION"}] * 3


def test_wrong_reauthentication_attempts_lock_the_account_for_a_while(clock):
    _user_row, client, _token, secret, _codes = _enrolled(clock)
    for _ in range(5):
        wrong = client.post(
            "/api/v1/auth/mfa/recovery-codes", json={"password": "Not the password 2026", "mfa_code": "123456"}
        )
        assert wrong.status_code == 403
    locked = client.post(
        "/api/v1/auth/mfa/recovery-codes", json={"password": PASSWORD, "mfa_code": _code(clock, secret)}
    )
    assert locked.status_code == 429 and locked.json()["detail"]["code"] == "MFA_TEMPORARILY_LOCKED"


def test_changes_to_two_factor_sign_in_are_rate_limited_per_account(clock, monkeypatch):
    monkeypatch.setenv("MDARIX_RATE_LIMITS_ENABLED", "true")
    monkeypatch.setenv("MDARIX_RATE_LIMIT_SALT", secrets.token_hex(16))
    _user_row, client, _token, secret, _codes = _enrolled(clock)
    statuses = [
        client.post(
            "/api/v1/auth/mfa/recovery-codes", json={"password": PASSWORD, "mfa_code": _code(clock, secret)}
        ).status_code
        for _ in range(11)
    ]
    assert statuses[:8] == [200] * 8 and statuses[-1] == 429


def test_a_session_that_still_owes_its_code_cannot_change_two_factor_sign_in(clock):
    user, _client, _token, secret, _codes = _enrolled(clock)
    pending = _sign_in(user)
    proof = {"password": PASSWORD, "mfa_code": _code(clock, secret)}
    for path in ("/api/v1/auth/mfa/recovery-codes", "/api/v1/auth/mfa/enroll"):
        refused = pending.post(path, json=proof)
        assert refused.status_code == 403 and refused.json()["detail"]["code"] == "MFA_REQUIRED", path
    assert pending.get("/api/v1/auth/mfa/status").json()["detail"]["code"] == "MFA_REQUIRED"


# ------------------------------------------------------------------------------------------- status


def test_status_says_whether_two_factor_sign_in_is_on_and_never_shows_a_secret(clock, monkeypatch):
    monkeypatch.setenv("MDARIX_REQUIRE_MFA_ROLES", "APPROVER")
    plain = _user(role="Investigator")
    off = _client_for(plain)[0].get("/api/v1/auth/mfa/status")
    assert off.status_code == 200 and off.json() == {
        "enrolled": False,
        "enrolled_at": None,
        "recovery_codes_left": 0,
        "required_for_role": False,
        "replacement_pending": False,
    }
    _user_row, client, _token, secret, _codes = _enrolled(clock, role="Approver")
    on = client.get("/api/v1/auth/mfa/status").json()
    assert on["enrolled"] is True and on["enrolled_at"] and on["recovery_codes_left"] == 8
    assert on["required_for_role"] is True and on["replacement_pending"] is False
    assert secret not in str(on)


# ------------------------------------------------------------------------------------------- replacing the app


def test_an_enrolled_person_replaces_the_authenticator_after_reauthentication(clock):
    user, client, token, old_secret, old_codes = _enrolled(clock)
    other, other_token = _client_for(user)  # another fully signed-in session (a second browser)

    # "Set up MFA" again does not hand out a second secret: it needs the password and a current code first.
    refused = client.post("/api/v1/auth/mfa/enroll")
    assert refused.status_code == 403 and refused.json()["detail"]["code"] == "REAUTHENTICATION_REQUIRED"
    assert "secret" not in refused.json()
    started = client.post("/api/v1/auth/mfa/enroll", json={"password": PASSWORD, "mfa_code": _code(clock, old_secret)})
    assert started.status_code == 200, started.text
    new_secret = started.json()["secret"]
    assert new_secret != old_secret
    assert _events(user.id, "MFA_REPLACEMENT_STARTED")[-1].details == {"method": "AUTHENTICATOR"}

    # Until the new app is confirmed, the old one is still the only one that signs in.
    assert client.get("/api/v1/auth/mfa/status").json()["replacement_pending"] is True
    assert _sign_in(user).post("/api/v1/auth/mfa/verify", json={"code": _code(clock, new_secret)}).status_code == 403
    assert _sign_in(user).post("/api/v1/auth/mfa/verify", json={"code": _code(clock, old_secret)}).status_code == 200

    confirmed = client.post("/api/v1/auth/mfa/verify-enrollment", json={"code": _code(clock, new_secret)})
    assert confirmed.status_code == 200, confirmed.text
    new_codes = confirmed.json()["recovery_codes"]
    assert len(new_codes) == 8 and not set(new_codes) & set(old_codes)
    details = _events(user.id, "MFA_ENROLLED")[-1].details
    assert details["replaced"] is True and details["recovery_codes"] == 8
    assert details["other_sessions_signed_out"] >= 2  # the second browser and the sign-in above

    # The old app and the old recovery codes stop working; the new ones work. This session stays, the other ends.
    assert _sign_in(user).post("/api/v1/auth/mfa/verify", json={"code": _code(clock, old_secret)}).status_code == 403
    assert _sign_in(user).post("/api/v1/auth/mfa/verify", json={"code": old_codes[1]}).status_code == 403
    assert _sign_in(user).post("/api/v1/auth/mfa/verify", json={"code": _code(clock, new_secret)}).status_code == 200
    assert _sign_in(user).post("/api/v1/auth/mfa/verify", json={"code": new_codes[0]}).status_code == 200
    assert client.get("/api/v1/auth/session").status_code == 200
    assert other.get("/api/v1/auth/session").status_code == 401
    status = client.get("/api/v1/auth/mfa/status").json()
    assert status["enrolled"] is True and status["replacement_pending"] is False

    assert [notice["kind"] for notice in _notices(user.id)] == ["MFA_ENROLLED", "MFA_REPLACED"]
    _assert_nothing_secret(user, old_secret, new_secret, PASSWORD, *old_codes, *new_codes)
    assert token and other_token


def test_with_the_phone_lost_a_recovery_code_and_the_password_replace_the_authenticator(clock):
    user, client, _token, _old_secret, old_codes = _enrolled(clock)
    wrong_password = client.post(
        "/api/v1/auth/mfa/enroll", json={"password": "Not the password 2026", "mfa_code": old_codes[0]}
    )
    assert wrong_password.status_code == 403
    assert len(_stored_hashes(user)) == 8  # a mistyped password does not spend the recovery code
    started = client.post("/api/v1/auth/mfa/enroll", json={"password": PASSWORD, "mfa_code": old_codes[0]})
    assert started.status_code == 200, started.text
    assert _events(user.id, "MFA_REPLACEMENT_STARTED")[-1].details == {"method": "RECOVERY_CODE"}
    assert _events(user.id, "MFA_RECOVERY_CODE_USED")[-1].details == {
        "recovery_codes_left": 7,
        "step": "REAUTHENTICATION",
    }
    # The code is spent: it can be used neither again here nor to sign in.
    again = client.post("/api/v1/auth/mfa/enroll", json={"password": PASSWORD, "mfa_code": old_codes[0]})
    assert again.status_code == 403
    assert _sign_in(user).post("/api/v1/auth/mfa/verify", json={"code": old_codes[0]}).status_code == 403
    confirmed = client.post("/api/v1/auth/mfa/verify-enrollment", json={"code": _code(clock, started.json()["secret"])})
    assert confirmed.status_code == 200, confirmed.text


def test_a_first_authenticator_is_still_set_up_without_reauthentication(clock):
    user = _user(role="Investigator")
    client, _token = _client_for(user)
    started = client.post("/api/v1/auth/mfa/enroll")
    assert started.status_code == 200 and started.json()["secret"]
    done = client.post("/api/v1/auth/mfa/verify-enrollment", json={"code": totp.current_code(started.json()["secret"])})
    assert done.status_code == 200
    assert _events(user.id, "MFA_ENROLLED")[-1].details == {"replaced": False, "recovery_codes": 8}
    assert _events(user.id, "MFA_REPLACEMENT_STARTED") == []
