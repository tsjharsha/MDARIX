"""Data exports, organization deletion and personal-data erasure (backend/app/tenant_export.py, tenant_purge.py)."""

import io
import json
import uuid
import zipfile
from datetime import datetime, timedelta, timezone

import pytest

from auth.service import _hash
from backend.app.db.models.foundation import AuditEvent, AuthUser, Product, Tenant, TenantMembership
from backend.app.db.models.stage2 import AuthSession, TenantExport
from backend.app.db.session import SessionLocal
from backend.app.db.tenant_scope import bind_system
from backend.app.tenant_export import expire_exports, run_export
from backend.app.tenant_purge import PurgeFailed, purge_tenant, tenant_tables
from object_storage.service import ObjectStorageService
from tests.conftest import authenticated_client

PASSWORD = "LegacyTestPassword123!"  # the shared platform-administrator test account (tests/conftest.py)


@pytest.fixture(autouse=True)
def storage_root(monkeypatch, tmp_path):
    monkeypatch.setenv("MDARIX_OBJECT_STORAGE_ROOT", str(tmp_path / "objects"))
    monkeypatch.setenv("MDARIX_OBJECT_STORAGE_PROVIDER", "local")
    monkeypatch.delenv("MDARIX_OBJECT_STORAGE_ENCRYPTION_KEY", raising=False)
    return tmp_path


@pytest.fixture
def platform():
    return authenticated_client()


@pytest.fixture
def organization(platform):
    """A fresh customer organization with a product, a user, a session, an audit event and a stored file."""
    code = f"PRG{uuid.uuid4().hex[:6].upper()}"
    created = platform.post(
        "/api/v1/platform-admin/customers",
        json={"company_name": f"Purge Test {code}", "tenant_code": code, "plan_code": "STARTER"},
    )
    assert created.status_code == 200, created.text
    tenant_id = uuid.UUID(created.json()["id"])
    now = datetime.now(timezone.utc)
    db = SessionLocal()
    bind_system(db, "test")
    user = AuthUser(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        username=f"person-{code.lower()}@example.invalid",
        display_name="Pat Person",
        company="Purge Test",
        password_hash=_hash("Person password 2026!"),
        role="Viewer",
        status="ACTIVE",
        email_verified=True,
        created_at=now,
        updated_at=now,
    )
    db.add(user)
    db.flush()
    user_id = user.id
    db.add(
        TenantMembership(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            user_id=user.id,
            status="ACTIVE",
            is_default=True,
            created_at=now,
            updated_at=now,
        )
    )
    db.add(
        Product(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            product_identifier=f"P-{code}",
            name="Pump",
            source_identifier=f"P-{code}",
            created_at=now,
            updated_at=now,
        )
    )
    db.add(
        AuditEvent(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            actor_ref=str(user_id),
            action="TEST_EVENT",
            entity_type="Test",
            created_at=now,
        )
    )
    db.commit()
    db.close()
    ObjectStorageService().put(str(tenant_id), "evidence/report.txt", b"stored evidence", internal=True)
    return {"tenant_id": tenant_id, "user_id": user_id, "tenant_key": created.json()["tenant_key"]}


def _count(model, **filters) -> int:
    db = SessionLocal()
    bind_system(db, "test")
    try:
        query = db.query(model)
        for key, value in filters.items():
            query = query.filter(getattr(model, key) == value)
        return query.count()
    finally:
        db.close()


def _set_status(tenant_id, status):
    db = SessionLocal()
    bind_system(db, "test")
    db.query(Tenant).filter(Tenant.id == tenant_id).update({"status": status})
    db.commit()
    db.close()


# ------------------------------------------------------------------------------------------------ purge


def test_the_purge_covers_every_tenant_table_it_finds():
    db = SessionLocal()
    try:
        tables = tenant_tables(db)
    finally:
        db.close()
    names = {name.split(".")[-1].strip('"') for name in tables}
    # Personal and business tables the old fixed list missed are included; kept tables are not.
    assert {
        "products",
        "event_outbox",
        "authentication_events",
        "user_invitations",
        "connector_configurations",
    } <= names
    assert not names & {"auth_users", "subscription_lifecycles", "audit_events", "trial_feedback"}


def test_deleting_an_organization_removes_its_data_files_and_trail(platform, organization):
    tenant_id = organization["tenant_id"]
    url = f"/api/v1/platform-admin/tenants/{tenant_id}/purge"
    body = {"reason": "Pilot ended; customer asked us to delete everything", "password": PASSWORD}
    # Guards: still active, wrong key, wrong password.
    assert platform.post(url, json={**body, "confirm_tenant_key": organization["tenant_key"]}).status_code == 409
    _set_status(tenant_id, "SUSPENDED")
    assert platform.post(url, json={**body, "confirm_tenant_key": "WRONG"}).status_code == 422
    wrong = {**body, "password": "not my password", "confirm_tenant_key": organization["tenant_key"]}
    assert platform.post(url, json=wrong).status_code == 403

    response = platform.post(url, json={**body, "confirm_tenant_key": organization["tenant_key"]})
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["deleted_records"]["products"] == 1 and result["files_deleted"] == 1
    assert result["audit_events_deleted"] >= 1 and result["users_pseudonymized"] == 1

    assert _count(Product, tenant_id=tenant_id) == 0
    assert ObjectStorageService().list_tenant_objects(str(tenant_id)) == []
    db = SessionLocal()
    bind_system(db, "test")
    try:
        assert db.get(Tenant, tenant_id).status == "ARCHIVED"
        person = db.get(AuthUser, organization["user_id"])
        assert person.username.endswith("@removed.invalid") and person.display_name == "Removed user"
        assert person.status == "REMOVED" and person.password_hash == "!removed"
        trail = db.query(AuditEvent).filter(AuditEvent.tenant_id == tenant_id).all()
        assert [event.action for event in trail] == ["TENANT_DATA_DELETED"] and trail[0].chain_seq == 1
    finally:
        db.close()


def test_a_purge_that_cannot_finish_changes_nothing(organization):
    tenant_id = organization["tenant_id"]

    class BrokenStorage:
        def delete_tenant(self, tenant):
            raise OSError("disk unavailable")

    db = SessionLocal()
    try:
        with pytest.raises(PurgeFailed):
            purge_tenant(db, tenant_id, "test", reason="Testing a failed purge", storage=BrokenStorage())
    finally:
        db.close()
    assert _count(Product, tenant_id=tenant_id) == 1
    assert _count(AuditEvent, tenant_id=tenant_id) >= 1
    db = SessionLocal()
    bind_system(db, "test")
    try:
        assert db.get(Tenant, tenant_id).status != "ARCHIVED"
    finally:
        db.close()


# ------------------------------------------------------------------------------------------------ erasure


def test_erasing_a_persons_data_requires_offboarding_and_removes_what_identifies_them(platform, organization):
    user_id = organization["user_id"]
    url = f"/api/v1/platform-admin/users/{user_id}/erase"
    reason = {"reason": "Written request from the person, verified by reply to their address"}
    assert platform.post(url, json=reason).status_code == 409  # still active
    db = SessionLocal()
    bind_system(db, "test")
    user = db.get(AuthUser, user_id)
    user.status = "OFFBOARDED"
    now = datetime.now(timezone.utc)
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
    db.close()

    response = platform.post(url, json=reason)
    assert response.status_code == 200, response.text
    db = SessionLocal()
    bind_system(db, "test")
    try:
        user = db.get(AuthUser, user_id)
        assert user.username.endswith("@removed.invalid") and "Pat" not in user.display_name
        assert user.mfa_secret_encrypted is None and user.password_hash == "!removed"
        assert db.query(AuthSession).filter(AuthSession.user_id == user_id).count() == 0
        assert (
            db.query(AuditEvent)
            .filter(AuditEvent.action == "PERSONAL_DATA_ERASED", AuditEvent.entity_id == user_id)
            .count()
            == 1
        )
    finally:
        db.close()


# ------------------------------------------------------------------------------------------------ export


def test_a_full_export_contains_records_files_and_manifest_but_no_secrets(platform, organization):
    tenant_id = organization["tenant_id"]
    base = f"/api/v1/platform-admin/tenants/{tenant_id}/exports"
    queued = platform.post(base, json={"reason": "Customer asked for a copy of its data"})
    assert queued.status_code == 202, queued.text
    assert platform.post(base, json={"reason": "A second one at the same time"}).status_code == 409
    export_id = queued.json()["id"]

    result = run_export(export_id)  # what the background worker does
    assert result["status"] == "READY" and result["summary"]["files"] == 1

    download = platform.get(f"{base}/{export_id}/download")
    assert download.status_code == 200 and download.headers["content-type"] == "application/zip"
    archive = zipfile.ZipFile(io.BytesIO(download.content))
    manifest = json.loads(archive.read("manifest.json"))
    assert manifest["tables"]["public.products"]["rows"] == 1 and manifest["audit_chain"]["valid"] is True
    assert archive.read("files/evidence/report.txt") == b"stored evidence"
    people = [json.loads(line) for line in archive.read("data/public.auth_users.jsonl").splitlines()]
    assert people and all("password_hash" not in person and "mfa_secret_encrypted" not in person for person in people)
    assert _count(AuditEvent, tenant_id=tenant_id, action="TENANT_EXPORT_DOWNLOADED") == 1


def test_exports_are_deleted_after_their_download_period(platform, organization):
    tenant_id = organization["tenant_id"]
    queued = platform.post(
        f"/api/v1/platform-admin/tenants/{tenant_id}/exports", json={"reason": "Copy for the customer"}
    )
    run_export(queued.json()["id"])
    db = SessionLocal()
    bind_system(db, "test")
    try:
        assert expire_exports(db, datetime.now(timezone.utc) + timedelta(days=8)) >= 1
        db.commit()
        row = db.get(TenantExport, uuid.UUID(queued.json()["id"]))
        assert row.status == "EXPIRED" and row.object_key is None
    finally:
        db.close()
    keys = ObjectStorageService().list_tenant_objects(str(tenant_id))
    assert not any("/exports/" in key for key in keys)


def test_only_administrators_export_or_delete(organization):
    from tests.test_business_permissions import _client_with_role

    investigator = _client_with_role("Investigator")
    tenant_id = organization["tenant_id"]
    assert investigator.post("/api/v1/admin/exports", json={"reason": "Not allowed for me"}).status_code in (401, 403)
    body = {"reason": "Not allowed for me at all", "password": "x", "confirm_tenant_key": "x"}
    assert investigator.post(f"/api/v1/platform-admin/tenants/{tenant_id}/purge", json=body).status_code in (401, 403)
