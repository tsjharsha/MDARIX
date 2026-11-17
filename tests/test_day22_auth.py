"""Password hashing and the password rules (auth/service.py)."""

import hashlib
import secrets

import pytest

from auth import service
from auth.service import _hash, _verify, needs_rehash, password_problem


def test_hash_verifies_the_password_and_does_not_contain_it():
    stored = _hash("Strong password 123")
    assert stored.startswith("scrypt$")
    assert "Strong password" not in stored
    assert _verify("Strong password 123", stored)
    assert not _verify("Strong password 124", stored)


def test_each_hash_has_its_own_salt():
    assert _hash("Same password 1234") != _hash("Same password 1234")


def test_legacy_hashes_still_verify_and_are_upgraded(monkeypatch):
    import hashlib
    import secrets

    salt = secrets.token_bytes(16)
    legacy = salt.hex() + ":" + hashlib.scrypt(b"Legacy password 99", salt=salt, n=2**14, r=8, p=1).hex()
    assert _verify("Legacy password 99", legacy)
    assert needs_rehash(legacy)


def test_a_lower_cost_hash_needs_rehash_when_the_cost_rises(monkeypatch):
    monkeypatch.setenv("MDARIX_PASSWORD_SCRYPT_LOG2_N", "12")
    cheap = _hash("Cost upgrade 12345")
    monkeypatch.setenv("MDARIX_PASSWORD_SCRYPT_LOG2_N", "14")
    assert needs_rehash(cheap)
    assert not needs_rehash(_hash("Cost upgrade 12345"))
    assert _verify("Cost upgrade 12345", cheap)  # the old hash keeps working until it is replaced


def test_a_value_that_is_not_a_hash_is_refused():
    with pytest.raises(ValueError):
        _verify("anything", "not-a-hash")


@pytest.mark.parametrize(
    ("password", "email", "problem"),
    [
        ("short", None, "PASSWORD_TOO_SHORT"),
        ("x" * 129, None, "PASSWORD_TOO_LONG"),
        ("aaaaaaaaaaaaaa", None, "PASSWORD_TOO_SIMPLE"),
        ("password1234", None, "PASSWORD_BREACHED"),
        ("Password1234", None, "PASSWORD_BREACHED"),  # case does not matter
        ("jordan.smith-2026-river", "jordan.smith@example.com", "PASSWORD_CONTAINS_EMAIL"),
        ("correct horse battery staple 77", "person@example.com", None),
    ],
)
def test_password_rules(password, email, problem):
    assert password_problem(password, email=email) == problem


def test_the_breached_password_list_is_shipped():
    assert len(service._breached_passwords()) > 10000


def test_unknown_email_spends_the_time_of_a_password_check(monkeypatch):
    calls = []
    original = service._verify
    monkeypatch.setattr(service, "_verify", lambda password, stored: calls.append(stored) or original(password, stored))
    service.burn_verification_time("whatever password")
    assert calls


# OWASP Password Storage Cheat Sheet: scrypt at N=2^17, r=8, p=1 or one of its listed equivalents.
OWASP_SCRYPT = {(17, 8, 1), (16, 8, 2), (15, 8, 3), (14, 8, 5), (13, 8, 10)}


def test_the_default_cost_is_an_owasp_scrypt_setting(monkeypatch):
    """P7 (owner, 17 Nov 2026): N=2^15, r=8, p=3, an OWASP equivalent of the minimum, under a second per hash."""
    monkeypatch.delenv("MDARIX_PASSWORD_SCRYPT_LOG2_N", raising=False)
    stored = _hash("Default cost 12345")
    log2_n, r, p = (int(part) for part in stored.split("$")[1:4])
    assert (log2_n, r, p) == (15, 8, 3)
    assert (log2_n, r, p) in OWASP_SCRYPT
    assert _verify("Default cost 12345", stored) and not needs_rehash(stored)


def test_a_hash_at_the_old_cost_still_verifies_and_is_rehashed_at_sign_in(monkeypatch):
    """Hashes written at N=2^17, r=8, p=1 (until 0.10.97) keep working and move to the new cost on the next sign-in."""
    monkeypatch.delenv("MDARIX_PASSWORD_SCRYPT_LOG2_N", raising=False)
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(b"Old cost 1234567", salt=salt, n=2**17, r=8, p=1, maxmem=256 * 8 * 2**17 + 2**20)
    old = f"scrypt$17$8$1${salt.hex()}${digest.hex()}"
    assert _verify("Old cost 1234567", old)
    assert not _verify("Old cost 7654321", old)
    assert needs_rehash(old)
