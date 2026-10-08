"""After a restore from backup, erasures and purges are re-applied from the erasure log (scripts/reapply_erasures.py).

Each test builds a "restored-like" state: the erasure or purge really ran, then the subject's personal data is put
back exactly as an older backup would bring it back (and, for the person, the log row the backup never had is
removed and re-imported from the newer copy, as the runbook says).
"""

import json
import uuid
from datetime import datetime, timedelta, timezone

import pytest

from auth.service import _hash
from backend.app.db.models.foundation import AuthUser, Product, Tenant
from backend.app.db.models.pilot_support import ErasureLog
from backend.app.db.models.stage2 import AuthSession
from backend.app.db.session import SessionLocal
from backend.app.db.tenant_scope import bind_system
from backend.app.tenant_purge import erase_person, purge_tenant, reapply_erasures
from object_storage.service import ObjectStorageService
from scripts import reapply_erasures as reapply_script
from tests.conftest import authenticated_client
from tests.test_tenant_data import _count, _erasure_logs, _set_status, make_organization, use_local_storage


@pytest.fixture(autouse=True)
def storage_root(monkeypatch, tmp_path):
    return use_local_storage(monkeypatch, tmp_path)


@pytest.fixture
def platform():
    return authenticated_client()


@pytest.fixture
def organization(platform):
    return make_organization(platform)


EMAIL_SUFFIX = "@example.invalid"


def _restore_person(user_id, email: str) -> None:
    """What a backup taken before the erasure brings back: the identifiable account and a session."""
    now = datetime.now(timezone.utc)
    db = SessionLocal()
    bind_system(db, "test: simulate a restore")
    try:
        user = db.get(AuthUser, user_id)
        user.username, user.display_name, user.company = email, "Pat Person", "Purge Test"
        user.password_hash, user.status = _hash("Person password 2026!"), "OFFBOARDED"
        db.add(
            AuthSession(
                id=uuid.uuid4(),
                tenant_id=user.tenant_id,
                user_id=user.id,
                session_hash=uuid.uuid4().hex,
                expires_at=now + timedelta(hours=1),
                created_at=now,
                last_seen_at=now,
            )
        )
        db.commit()
    finally:
        db.close()


def _person(user_id) -> AuthUser:
    db = SessionLocal()
    bind_system(db, "test")
    try:
        user = db.get(AuthUser, user_id)
        db.expunge(user)
        return user
    finally:
        db.close()


def _sessions(user_id) -> int:
    return _count(AuthSession, user_id=user_id)


def test_a_restored_person_is_erased_again_from_the_imported_log(organization, tmp_path):
    tenant_id, user_id = organization["tenant_id"], organization["user_id"]
    email = _person(user_id).username
    db = SessionLocal()
    bind_system(db, "test")
    try:
        user = db.get(AuthUser, user_id)
        user.status = "OFFBOARDED"
        erase_person(db, user, "test", "Written request from the person, verified")
        db.commit()
    finally:
        db.close()
    [original] = _erasure_logs(tenant_id)

    # The newest copy of the database (the instance being replaced) exports its log ...
    log_file = tmp_path / "erasure_log.jsonl"
    assert reapply_script.main(["--export-log", str(log_file)]) == 0
    exported = [json.loads(line) for line in log_file.read_text(encoding="utf-8").splitlines()]
    assert str(original.id) in {row["id"] for row in exported}
    # ... and the restored database is from before the erasure: the person is back and the log row is not there.
    db = SessionLocal()
    bind_system(db, "test: simulate a restore")
    db.query(ErasureLog).filter(ErasureLog.id == original.id).delete()
    db.commit()
    db.close()
    _restore_person(user_id, email)
    assert _person(user_id).username == email and _sessions(user_id) == 1

    # The dry run imports the log in its own transaction, lists the erasure and changes nothing.
    assert reapply_script.main(["--import-log", str(log_file), "--dry-run", "--tenant", str(tenant_id)]) == 1
    assert _erasure_logs(tenant_id) == []
    assert _person(user_id).username == email and _sessions(user_id) == 1

    assert reapply_script.main(["--import-log", str(log_file), "--tenant", str(tenant_id)]) == 0
    person = _person(user_id)
    assert person.username.endswith("@removed.invalid") and person.display_name == "Removed user"
    assert person.password_hash == "!removed" and _sessions(user_id) == 0
    logs = _erasure_logs(tenant_id)
    restored_row = next(row for row in logs if row.id == original.id)
    assert restored_row.reapplied_at is not None
    # The re-application is logged as such, and a second run finds nothing to do.
    assert any(row.details.get("reapplied") is True for row in logs if row.id != original.id)
    db = SessionLocal()
    try:
        again = reapply_erasures(db, "test", tenant_ids=[tenant_id])
    finally:
        db.close()
    assert again["reapplied"] == [] and again["failed"] == []
    assert {item["why"] for item in again["skipped"]} == {"ALREADY_ERASED"}


def test_a_restored_organization_is_purged_again(organization):
    tenant_id, user_id = organization["tenant_id"], organization["user_id"]
    email = _person(user_id).username
    _set_status(tenant_id, "SUSPENDED")
    db = SessionLocal()
    try:
        evidence = {"export": "WAIVED", "export_waiver_reason": "Synthetic test organization"}
        assert purge_tenant(db, tenant_id, "test", reason="End of pilot", evidence=evidence)["status"] == "ARCHIVED"
    finally:
        db.close()
    [original] = _erasure_logs(tenant_id)

    # Restored-like: the organization is suspended again, with a record, an identifiable account and a file.
    _set_status(tenant_id, "SUSPENDED")
    now = datetime.now(timezone.utc)
    db = SessionLocal()
    bind_system(db, "test: simulate a restore")
    db.add(
        Product(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            product_identifier="P-RESTORED",
            name="Restored pump",
            source_identifier="P-RESTORED",
            created_at=now,
            updated_at=now,
        )
    )
    db.commit()
    db.close()
    _restore_person(user_id, email)
    ObjectStorageService().put(str(tenant_id), "evidence/restored.txt", b"restored evidence", internal=True)

    db = SessionLocal()
    try:
        plan = reapply_erasures(db, "test", dry_run=True, tenant_ids=[tenant_id])
    finally:
        db.close()
    [pending] = plan["pending"]
    assert pending["log_id"] == str(original.id) and "products" in pending["data_present"]["tables"]
    assert pending["data_present"]["accounts"] == 1 and pending["data_present"]["files"] == 1
    assert _count(Product, tenant_id=tenant_id) == 1  # the dry run changed nothing

    db = SessionLocal()
    try:
        done = reapply_erasures(db, "test", tenant_ids=[tenant_id])
    finally:
        db.close()
    assert [item["log_id"] for item in done["reapplied"]] == [str(original.id)] and done["failed"] == []
    assert _count(Product, tenant_id=tenant_id) == 0
    assert ObjectStorageService().list_tenant_objects(str(tenant_id)) == []
    assert _person(user_id).username.endswith("@removed.invalid") and _sessions(user_id) == 0
    db = SessionLocal()
    bind_system(db, "test")
    try:
        assert db.get(Tenant, tenant_id).status == "ARCHIVED"
        assert db.get(ErasureLog, original.id).reapplied_at is not None
    finally:
        db.close()
    db = SessionLocal()
    try:
        again = reapply_erasures(db, "test", tenant_ids=[tenant_id])
    finally:
        db.close()
    assert again["reapplied"] == [] and {item["why"] for item in again["skipped"]} == {"ALREADY_PURGED"}
