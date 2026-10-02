"""TOTP codes match RFC 6238 (so any authenticator app produces the same codes) and secrets are sealed at rest."""

import base64

import pytest

from auth import totp


def test_rfc_6238_sha1_test_vector():
    # RFC 6238 appendix B: key "12345678901234567890", T = 59 s -> 94287082 (8 digits); MDARIX uses the last 6.
    secret = base64.b32encode(b"12345678901234567890").decode().rstrip("=")
    assert totp.code_at(secret, 59 // 30) == "287082"
    assert totp.code_at(secret, 1111111109 // 30) == "081804"


def test_a_code_matches_within_one_step_and_only_once():
    secret = totp.new_secret()
    now = 1_800_000_000
    code = totp.code_at(secret, now // 30)
    step = totp.matching_step(secret, code, None, at=now + 25)
    assert step == now // 30
    assert totp.matching_step(secret, code, step, at=now + 25) is None  # replay refused
    assert totp.matching_step(secret, code, None, at=now + 95) is None  # too old
    assert totp.matching_step(secret, "12345", None, at=now) is None
    assert totp.matching_step(secret, "abcdef", None, at=now) is None


def test_secrets_are_encrypted_and_bound_to_their_account():
    secret = totp.new_secret()
    sealed = totp.encrypt_secret(secret, "user-1")
    assert secret not in sealed
    assert totp.decrypt_secret(sealed, "user-1") == secret
    with pytest.raises(Exception):
        totp.decrypt_secret(sealed, "user-2")  # a sealed secret copied to another account does not open


def test_outside_local_development_a_missing_key_fails_closed(monkeypatch):
    monkeypatch.setenv("MDARIX_ENV", "production")
    monkeypatch.delenv("MDARIX_MFA_ENCRYPTION_KEY", raising=False)
    with pytest.raises(totp.MfaUnavailable):
        totp.encrypt_secret(totp.new_secret(), "user-1")
