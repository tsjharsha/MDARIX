"""MFA and stored-file encryption keys rotate with a keyring (security/keyring.py), as connector keys do.

A server that sets no new setting keeps sealing exactly as before (the unlabelled formats MDARIXMFA1 and MDARIXENC1) and
still opens what it stored before; once a key ID is set, new values name their key, older keys stay readable from
<name>S, and scripts/reseal_mfa_secrets.py and scripts/reencrypt_object_storage.py move everything to the current
key, so the old key can be removed.
"""

from __future__ import annotations

import base64
import os
import uuid

import pytest
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from auth import totp
from backend.app import config_check
from object_storage.service import ObjectStorageService, StorageError
from scripts import reencrypt_object_storage, reseal_mfa_secrets
from security import keyring as keys
from tests.test_config_check import production  # noqa: F401  (a complete production configuration)

OLD = base64.urlsafe_b64encode(os.urandom(32)).decode()
NEW = base64.urlsafe_b64encode(os.urandom(32)).decode()
MFA = "MDARIX_MFA_ENCRYPTION_KEY"
FILES = "MDARIX_OBJECT_STORAGE_ENCRYPTION_KEY"


def _raw(key: str) -> bytes:
    return base64.urlsafe_b64decode(key + "=" * (-len(key) % 4))


def _use(monkeypatch, setting: str, key: str, key_id: str | None = None, older: str = "") -> None:
    monkeypatch.setenv(setting, key)
    if key_id is None:
        monkeypatch.delenv(f"{setting}_ID", raising=False)
    else:
        monkeypatch.setenv(f"{setting}_ID", key_id)
    monkeypatch.setenv(f"{setting}S", older)


# The 0.10.46 code, as it sealed and opened values: what is stored on production today.
def _sealed_by_0_10_46(secret: str, user_id: str, key: str) -> str:
    nonce = os.urandom(12)
    sealed = AESGCM(_raw(key)).encrypt(nonce, secret.encode("ascii"), user_id.encode("ascii"))
    return base64.urlsafe_b64encode(b"MDARIXMFA1" + nonce + sealed).decode("ascii")


def _opened_by_0_10_46(token: str, user_id: str, key: str) -> str:
    blob = base64.urlsafe_b64decode(token.encode("ascii"))
    assert blob.startswith(b"MDARIXMFA1")
    return AESGCM(_raw(key)).decrypt(blob[10:22], blob[22:], user_id.encode("ascii")).decode("ascii")


def _file_by_0_10_46(content: bytes, object_key: str, key: str) -> bytes:
    nonce = os.urandom(12)
    return b"MDARIXENC1" + nonce + AESGCM(_raw(key)).encrypt(nonce, content, object_key.encode())


def _file_opened_by_0_10_46(body: bytes, object_key: str, key: str) -> bytes:
    assert body.startswith(b"MDARIXENC1")
    return AESGCM(_raw(key)).decrypt(body[10:22], body[22:], object_key.encode())


@pytest.fixture
def storage(monkeypatch, tmp_path):
    root = tmp_path / "objects"
    monkeypatch.setenv("MDARIX_OBJECT_STORAGE_PROVIDER", "local")
    monkeypatch.setenv("MDARIX_OBJECT_STORAGE_ROOT", str(root))
    return root


# ------------------------------------------------------------------------------------------------ MFA secrets


def test_with_no_new_setting_mfa_secrets_seal_and_open_exactly_as_before(monkeypatch):
    _use(monkeypatch, MFA, OLD)
    monkeypatch.delenv(f"{MFA}S")
    secret = totp.new_secret()
    stored_before = _sealed_by_0_10_46(secret, "user-1", OLD)
    assert totp.decrypt_secret(stored_before, "user-1") == secret
    sealed_now = totp.encrypt_secret(secret, "user-1")
    blob = base64.urlsafe_b64decode(sealed_now)
    assert blob.startswith(b"MDARIXMFA1") and len(blob) == len(base64.urlsafe_b64decode(stored_before))
    # 0.10.46 opens what this release seals, so going back a release loses nothing.
    assert _opened_by_0_10_46(sealed_now, "user-1", OLD) == secret
    assert totp.sealed_key_id(sealed_now) is None


def test_a_labelled_mfa_secret_names_its_key_and_stays_bound_to_its_account(monkeypatch):
    _use(monkeypatch, MFA, NEW, "k2")
    secret = totp.new_secret()
    sealed = totp.encrypt_secret(secret, "user-1")
    assert base64.urlsafe_b64decode(sealed).startswith(b"MDARIXMFA2\x02k2")
    assert totp.sealed_key_id(sealed) == "k2"
    assert totp.decrypt_secret(sealed, "user-1") == secret
    with pytest.raises(ValueError, match="MFA_SECRET_UNREADABLE"):
        totp.decrypt_secret(sealed, "user-2")
    # The key ID is part of what is authenticated: relabelling a value does not open it with another key.
    blob = base64.urlsafe_b64decode(sealed)
    _use(monkeypatch, MFA, NEW, "k3")
    relabelled = base64.urlsafe_b64encode(b"MDARIXMFA2\x02k3" + blob[13:]).decode()
    with pytest.raises(ValueError, match="MFA_SECRET_UNREADABLE"):
        totp.decrypt_secret(relabelled, "user-1")


def test_a_wrong_key_or_a_tampered_mfa_secret_is_refused(monkeypatch):
    _use(monkeypatch, MFA, OLD, "k1")
    sealed = totp.encrypt_secret(totp.new_secret(), "user-1")
    _use(monkeypatch, MFA, NEW, "k1")  # the same ID, another key
    with pytest.raises(ValueError, match="MFA_SECRET_UNREADABLE"):
        totp.decrypt_secret(sealed, "user-1")
    _use(monkeypatch, MFA, OLD, "k1")
    blob = bytearray(base64.urlsafe_b64decode(sealed))
    blob[-1] ^= 1
    with pytest.raises(ValueError, match="MFA_SECRET_UNREADABLE"):
        totp.decrypt_secret(base64.urlsafe_b64encode(bytes(blob)).decode(), "user-1")
    legacy = _sealed_by_0_10_46("JBSWY3DPEHPK3PXP", "user-1", OLD)
    _use(monkeypatch, MFA, NEW, "k2")  # the original key not listed: an unlabelled secret cannot be opened
    with pytest.raises(ValueError, match="MFA_SECRET_UNREADABLE"):
        totp.decrypt_secret(legacy, "user-1")
    _use(monkeypatch, MFA, NEW, "k2", older="k1:not-a-key")
    with pytest.raises(totp.MfaUnavailable, match=r"MDARIX_MFA_ENCRYPTION_KEYS\[k1\]"):
        totp.decrypt_secret(legacy, "user-1")


@pytest.fixture
def mfa_accounts():
    from backend.app.db.session import SessionLocal
    from tests.test_customer_admin_account_security import _tenant, _user

    db = SessionLocal()
    tenant = _tenant(db, "KEY")
    users = [_user(db, tenant, "Viewer", f"key-rotation-{index}") for index in range(3)]
    db.commit()
    yield db, users
    # The accounts stay (as other tests' do); their secrets, sealed with this test's keys, do not.
    db.rollback()
    for user in users:
        user = db.merge(user)
        user.mfa_secret_encrypted = user.mfa_pending_secret_encrypted = None
    db.commit()
    db.close()


@pytest.mark.db
def test_mfa_rotation_from_the_original_key_to_k2_and_removing_k1(monkeypatch, mfa_accounts):
    db, users = mfa_accounts
    ids = [user.id for user in users]
    secrets = {user.id: totp.new_secret() for user in users}
    # Before the rotation: secrets sealed by 0.10.46 with the original key (one account still setting up).
    _use(monkeypatch, MFA, OLD)
    users[0].mfa_secret_encrypted = _sealed_by_0_10_46(secrets[users[0].id], str(users[0].id), OLD)
    users[1].mfa_secret_encrypted = totp.encrypt_secret(secrets[users[1].id], str(users[1].id))
    users[2].mfa_pending_secret_encrypted = totp.encrypt_secret(secrets[users[2].id], str(users[2].id))
    db.commit()
    stored = {user.id: (user.mfa_secret_encrypted, user.mfa_pending_secret_encrypted) for user in users}

    # The new key is k2; the original key stays readable as k1. Everything still opens.
    _use(monkeypatch, MFA, NEW, "k2", older=f"k1:{OLD}")
    for user in users:
        assert totp.decrypt_secret(user.mfa_secret_encrypted or user.mfa_pending_secret_encrypted, str(user.id))

    lines: list[str] = []
    dry = reseal_mfa_secrets.reseal(db, apply=False, user_ids=ids, out=lines.append)
    db.rollback()
    assert dry == {"resealed": 3, "current": 0, "failed": 0} and lines == []
    for user in users:
        db.refresh(user)
        assert (user.mfa_secret_encrypted, user.mfa_pending_secret_encrypted) == stored[user.id]  # dry run: unchanged

    assert reseal_mfa_secrets.reseal(db, apply=True, user_ids=ids) == {"resealed": 3, "current": 0, "failed": 0}
    db.commit()
    # Idempotent: a second run finds everything on k2.
    assert reseal_mfa_secrets.reseal(db, apply=True, user_ids=ids) == {"resealed": 0, "current": 3, "failed": 0}
    db.commit()

    _use(monkeypatch, MFA, NEW, "k2")  # k1 removed
    for user in users:
        db.refresh(user)
        token = user.mfa_secret_encrypted or user.mfa_pending_secret_encrypted
        assert totp.sealed_key_id(token) == "k2"
        assert totp.decrypt_secret(token, str(user.id)) == secrets[user.id]
        with pytest.raises(ValueError):
            totp.decrypt_secret(token, str(users[(users.index(user) + 1) % 3].id))  # still bound to its account


@pytest.mark.db
def test_the_mfa_reseal_reports_a_secret_it_cannot_open_and_leaves_it(monkeypatch, mfa_accounts, capsys):
    db, users = mfa_accounts
    _use(monkeypatch, MFA, OLD)
    users[0].mfa_secret_encrypted = totp.encrypt_secret(totp.new_secret(), str(users[0].id))
    other = base64.urlsafe_b64encode(os.urandom(32)).decode()
    users[1].mfa_secret_encrypted = _sealed_by_0_10_46(totp.new_secret(), str(users[1].id), other)
    db.commit()
    unreadable = users[1].mfa_secret_encrypted
    _use(monkeypatch, MFA, NEW, "k2", older=f"k1:{OLD}")
    lines: list[str] = []
    counts = reseal_mfa_secrets.reseal(db, apply=True, user_ids=[users[0].id, users[1].id], out=lines.append)
    db.commit()
    assert counts == {"resealed": 1, "current": 0, "failed": 1}
    assert len(lines) == 1 and lines[0].startswith("UNREADABLE  account ") and "MFA_SECRET_UNREADABLE" in lines[0]
    db.refresh(users[1])
    assert users[1].mfa_secret_encrypted == unreadable


# ------------------------------------------------------------------------------------------------ stored files


def test_with_no_new_setting_files_are_written_and_read_exactly_as_before(monkeypatch, storage):
    _use(monkeypatch, FILES, OLD)
    monkeypatch.delenv(f"{FILES}S")
    service = ObjectStorageService()
    tenant = str(uuid.uuid4())
    key = f"{tenant}/attachments/old.pdf"
    (storage / tenant / "attachments").mkdir(parents=True)
    (storage / key).write_bytes(_file_by_0_10_46(b"%PDF-1.7 stored by 0.10.46", key, OLD))
    assert service.get(tenant, key) == b"%PDF-1.7 stored by 0.10.46"
    written = service.put(tenant, "attachments/new.txt", b"written by 0.10.47", content_type="text/plain")
    body = (storage / written["object_key"]).read_bytes()
    assert body.startswith(b"MDARIXENC1") and len(body) == 10 + 12 + len(b"written by 0.10.47") + 16
    assert _file_opened_by_0_10_46(body, written["object_key"], OLD) == b"written by 0.10.47"


def test_a_labelled_file_names_its_key_and_stays_bound_to_its_object_key(monkeypatch, storage):
    _use(monkeypatch, FILES, NEW, "k2")
    service = ObjectStorageService()
    tenant = str(uuid.uuid4())
    written = service.put(tenant, "a.txt", b"labelled", content_type="text/plain")
    path = storage / written["object_key"]
    assert path.read_bytes().startswith(b"MDARIXENC2\x02k2")
    assert service.get(tenant, written["object_key"]) == b"labelled"
    (storage / tenant / "b.txt").write_bytes(path.read_bytes())  # copied under another name: does not open
    with pytest.raises(StorageError, match="OBJECT_DECRYPTION_FAILED"):
        service.get(tenant, f"{tenant}/b.txt")


def test_file_rotation_from_the_original_key_to_k2_and_removing_k1(monkeypatch, storage, tmp_path):
    tenant = str(uuid.uuid4())
    _use(monkeypatch, FILES, OLD)
    before = ObjectStorageService()
    contents = {f"report-{index}.txt": f"report {index}".encode() for index in range(3)}
    for name, content in contents.items():
        before.put(tenant, name, content, content_type="text/plain")
    (storage / tenant / "plain.txt").write_bytes(b"stored without encryption")  # a key was not set back then
    marker = storage / tenant / "report-0.txt.retention"
    marker.write_text("2030-01-01T00:00:00", encoding="utf-8")
    os.chmod(storage / tenant / "report-1.txt", 0o640)
    mode = os.stat(storage / tenant / "report-1.txt").st_mode
    mtime = os.stat(storage / tenant / "report-1.txt").st_mtime_ns
    snapshot = {path: path.read_bytes() for path in storage.rglob("*") if path.is_file()}

    _use(monkeypatch, FILES, NEW, "k2", older=f"k1:{OLD}")
    for name, content in contents.items():
        assert ObjectStorageService().get(tenant, f"{tenant}/{name}") == content  # readable before the re-encryption

    assert reencrypt_object_storage.main(["--root", str(storage)]) == 0  # dry run
    assert {path: path.read_bytes() for path in storage.rglob("*") if path.is_file()} == snapshot

    counts = reencrypt_object_storage.reencrypt(storage, apply=True)
    assert counts == {"reencrypted": 3, "current": 0, "not_encrypted": 1, "failed": 0, "leftovers": 0}
    assert reencrypt_object_storage.reencrypt(storage, apply=True)["current"] == 3  # idempotent
    assert os.stat(storage / tenant / "report-1.txt").st_mode == mode
    assert os.stat(storage / tenant / "report-1.txt").st_mtime_ns == mtime
    assert marker.read_text(encoding="utf-8") == "2030-01-01T00:00:00"
    assert (storage / tenant / "plain.txt").read_bytes() == b"stored without encryption"
    assert not [path for path in storage.rglob("*") if path.name.endswith(".reencrypt-tmp")]

    _use(monkeypatch, FILES, NEW, "k2")  # k1 removed
    after = ObjectStorageService()
    for name, content in contents.items():
        assert (storage / tenant / name).read_bytes().startswith(b"MDARIXENC2\x02k2")
        assert after.get(tenant, f"{tenant}/{name}") == content
    assert sorted(after.list_tenant_objects(tenant)) == sorted(f"{tenant}/{name}" for name in [*contents, "plain.txt"])


def test_the_file_reencryption_reports_a_file_it_cannot_open_and_leaves_it(monkeypatch, storage, capsys):
    tenant = str(uuid.uuid4())
    _use(monkeypatch, FILES, OLD)
    ObjectStorageService().put(tenant, "good.txt", b"good", content_type="text/plain")
    (storage / tenant / "tampered.txt").write_bytes(_file_by_0_10_46(b"tampered", f"{tenant}/tampered.txt", OLD)[:-1])
    foreign = base64.urlsafe_b64encode(os.urandom(32)).decode()
    (storage / tenant / "foreign.txt").write_bytes(_file_by_0_10_46(b"foreign", f"{tenant}/foreign.txt", foreign))
    (storage / tenant / ".good.txt.reencrypt-tmp").write_bytes(b"left by an interrupted run")
    bad = {name: (storage / tenant / name).read_bytes() for name in ("tampered.txt", "foreign.txt")}

    _use(monkeypatch, FILES, NEW, "k2", older=f"k1:{OLD}")
    assert reencrypt_object_storage.main(["--root", str(storage), "--apply"]) == 1
    output = capsys.readouterr().out
    assert f"UNREADABLE  {tenant}/tampered.txt: ValueError OBJECT_UNREADABLE" in output
    assert f"UNREADABLE  {tenant}/foreign.txt: ValueError OBJECT_UNREADABLE" in output
    assert "Re-encrypted 1; already on key k2: 0;" in output and "unreadable: 2" in output
    assert "temporary files of an interrupted run: 1" in output
    assert "good" not in output.replace("good.txt", "")  # names, never content
    for name, body in bad.items():
        assert (storage / tenant / name).read_bytes() == body
    assert not (storage / tenant / ".good.txt.reencrypt-tmp").exists()
    with pytest.raises(StorageError, match="OBJECT_DECRYPTION_FAILED"):
        ObjectStorageService().get(tenant, f"{tenant}/foreign.txt")


def test_a_tampered_labelled_file_is_refused(monkeypatch, storage):
    _use(monkeypatch, FILES, NEW, "k2")
    service = ObjectStorageService()
    tenant = str(uuid.uuid4())
    written = service.put(tenant, "a.txt", b"labelled", content_type="text/plain")
    path = storage / written["object_key"]
    body = bytearray(path.read_bytes())
    body[-1] ^= 1
    path.write_bytes(bytes(body))
    with pytest.raises(StorageError, match="OBJECT_DECRYPTION_FAILED") as error:
        service.get(tenant, written["object_key"])
    assert isinstance(error.value.__cause__, ValueError)
    assert isinstance(error.value.__cause__.__cause__, InvalidTag)


# ------------------------------------------------------------------------------------------------ configuration


@pytest.mark.parametrize("setting", [MFA, FILES])
def test_the_configuration_gate_checks_each_keyring(production, setting):  # noqa: F811
    assert config_check.problems(offline=True) == [] and config_check.warnings() == []
    production.setenv(f"{setting}_ID", "k 2")
    assert f"{setting}_ID may use letters" in "\n".join(config_check.problems(offline=True))
    production.setenv(f"{setting}_ID", "k2")
    for older, problem in (
        ("k1", f"{setting}S entries must be <key id>:<base64 key>"),
        ("k1:bm90IGEga2V5", f"{setting}S[k1] must decode to 16, 24 or 32 bytes"),
        (f"k1:{OLD},k1:{NEW}", f"{setting}S lists the key ID k1 twice"),
        (f"k2:{OLD}", f"{setting}S must not list the current key ID k2"),
    ):
        production.setenv(f"{setting}S", older)
        assert problem in "\n".join(config_check.problems(offline=True)), older
    production.setenv(f"{setting}S", f"k1:{OLD}")
    assert config_check.problems(offline=True) == []
    assert config_check.warnings() == [
        f"{setting}S still holds older keys (k1): once everything is re-encrypted with the current key and no "
        "backup made with them is still kept, remove them (docs/runbooks/KEY_ROTATION.md)"
    ]
    production.setenv(f"{setting}S", "")
    assert config_check.warnings() == []


def test_the_configuration_gate_never_names_a_key(production):  # noqa: F811
    production.setenv(f"{MFA}_ID", "k2")
    production.setenv(f"{MFA}S", f"k1:{OLD},k1:{OLD}")
    production.setenv(f"{FILES}S", f"k1:{NEW[:-4]}")
    text = "\n".join(config_check.problems(offline=True) + config_check.warnings())
    assert OLD not in text and NEW[:-4] not in text and "twice" in text


def test_keyring_unlabelled_values_try_the_current_key_first():
    ring = keys.Keyring("X", b"c" * 32, "k2", {"k1": b"o" * 32, "k0": b"c" * 32})
    assert ring.unlabelled_candidates() == [b"c" * 32, b"o" * 32]
    assert ring.key_for("k2") == b"c" * 32 and ring.key_for("k1") == b"o" * 32 and ring.key_for("k9") is None
