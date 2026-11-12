"""Data exports, organization deletion and personal-data erasure (backend/app/tenant_export.py, tenant_purge.py)."""

import io
import json
import uuid
import zipfile
from datetime import datetime, timedelta, timezone

import pytest

from auth.service import _hash
from backend.app.db.models.foundation import AuditEvent, AuthUser, Product, Tenant, TenantMembership
from backend.app.db.models.pilot_support import ErasureLog
from backend.app.db.models.stage2 import AuthSession, TenantExport
from backend.app.db.session import SessionLocal
from backend.app.db.tenant_scope import bind_system
from backend.app.tenant_export import expire_exports, run_export
from backend.app.tenant_purge import PurgeFailed, purge_tenant, tenant_tables
from object_storage.service import ObjectStorageService
from tests.conftest import authenticated_client

PASSWORD = "LegacyTestPassword123!"  # the shared platform-administrator test account (tests/conftest.py)


def use_local_storage(monkeypatch, tmp_path):
    """Stored files go to a fresh local folder (shared with the other data-governance test modules)."""
    monkeypatch.setenv("MDARIX_OBJECT_STORAGE_ROOT", str(tmp_path / "objects"))
    monkeypatch.setenv("MDARIX_OBJECT_STORAGE_PROVIDER", "local")
    monkeypatch.delenv("MDARIX_OBJECT_STORAGE_ENCRYPTION_KEY", raising=False)
    return tmp_path


@pytest.fixture(autouse=True)
def storage_root(monkeypatch, tmp_path):
    return use_local_storage(monkeypatch, tmp_path)


@pytest.fixture
def platform():
    return authenticated_client()


@pytest.fixture
def organization(platform):
    return make_organization(platform)


def make_organization(platform, *, support_access: bool = True) -> dict:
    """A fresh customer organization with a product, a user, a session, an audit event and a stored file.

    The creating platform administrator holds support access the customer approved (every area, with changes),
    since the tests using it are about what staff do with the data; ``support_access=False`` leaves it out
    (the approval itself: tests/test_support_access_customer_approval.py)."""
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
    if support_access:
        from tests.support_grants import grant_for

        grant_for(platform, tenant_id)
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
    """Move the organization to ``status``; a suspension is stamped now, as the lifecycle transition does."""
    db = SessionLocal()
    bind_system(db, "test")
    changes = {"status": status}
    if status == "SUSPENDED":
        changes["suspended_at"] = datetime.now(timezone.utc)
    db.query(Tenant).filter(Tenant.id == tenant_id).update(changes)
    db.commit()
    db.close()


def _erasure_logs(tenant_id) -> list[ErasureLog]:
    db = SessionLocal()
    bind_system(db, "test")
    try:
        return db.query(ErasureLog).filter(ErasureLog.tenant_id == tenant_id).order_by(ErasureLog.performed_at).all()
    finally:
        db.close()


def _export(platform, tenant_id) -> str:
    queued = platform.post(f"/api/v1/platform-admin/tenants/{tenant_id}/exports", json={"reason": "Hand the data back"})
    assert queued.status_code == 202, queued.text
    assert run_export(queued.json()["id"])["status"] == "READY"
    return queued.json()["id"]


# The hand-back record a direct purge_tenant call needs for a customer organization (RSK-066).
WAIVED = {"export": "WAIVED", "export_waiver_reason": "Synthetic test organization"}
PURGE_BODY = {"reason": "Pilot ended; customer asked us to delete everything", "password": PASSWORD}


class BrokenStorage:
    """A file store that is down: every deletion fails."""

    def __init__(self):
        self.calls = 0

    def delete_tenant(self, tenant):
        self.calls += 1
        raise OSError("disk unavailable")

    def list_tenant_objects(self, tenant):
        return ObjectStorageService().list_tenant_objects(tenant)


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
    assert not names & {"auth_users", "subscription_lifecycles", "audit_events", "trial_feedback", "erasure_log"}


def test_deleting_an_organization_removes_its_data_files_and_trail(platform, organization):
    tenant_id = organization["tenant_id"]
    url = f"/api/v1/platform-admin/tenants/{tenant_id}/purge"
    confirmed = {**PURGE_BODY, "confirm_tenant_key": organization["tenant_key"]}
    # Guards: still active, wrong key, wrong password.
    assert platform.post(url, json=confirmed).status_code == 409
    _set_status(tenant_id, "SUSPENDED")
    assert platform.post(url, json={**PURGE_BODY, "confirm_tenant_key": "WRONG"}).status_code == 422
    assert platform.post(url, json={**confirmed, "password": "not my password"}).status_code == 403

    # The customer's data is handed back first: an export prepared after the suspension satisfies the rule.
    export_id = _export(platform, tenant_id)
    response = platform.post(url, json=confirmed)
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["status"] == "ARCHIVED" and result["export"]["id"] == export_id
    # The evidence file and the export archive itself are both deleted.
    assert result["deleted_records"]["products"] == 1 and result["files_deleted"] == 2
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
        assert trail[0].details["export"]["id"] == export_id
    finally:
        db.close()
    # The erasure log survives the purge (a restore re-applies it) and names the export that was handed back.
    [log] = _erasure_logs(tenant_id)
    assert log.kind == "TENANT_PURGED" and log.details["completed"] is True
    assert log.details["export"]["id"] == export_id


def test_a_purge_needs_an_export_made_after_the_suspension_or_a_recorded_waiver(platform, organization):
    tenant_id = organization["tenant_id"]
    url = f"/api/v1/platform-admin/tenants/{tenant_id}/purge"
    confirmed = {**PURGE_BODY, "confirm_tenant_key": organization["tenant_key"]}
    _export(platform, tenant_id)  # made while the organization was still active: it is not the hand-back
    _set_status(tenant_id, "SUSPENDED")

    refused = platform.post(url, json=confirmed)
    assert refused.status_code == 409 and refused.json()["detail"]["code"] == "EXPORT_REQUIRED"
    assert _count(Product, tenant_id=tenant_id) == 1 and _erasure_logs(tenant_id) == []
    # A waiver must say why (at least ten characters).
    assert platform.post(url, json={**confirmed, "export_waiver_reason": "no"}).status_code == 422

    waiver = "Customer declined a copy in writing (ticket 4711)"
    response = platform.post(url, json={**confirmed, "export_waiver_reason": waiver})
    assert response.status_code == 200, response.text
    assert response.json()["export"] == "WAIVED"
    [log] = _erasure_logs(tenant_id)
    assert log.details["export"] == "WAIVED" and log.details["export_waiver_reason"] == waiver


def test_no_caller_deletes_a_customer_organizations_trail_without_the_hand_back(organization):
    """RSK-066: the hand-back rule is in purge_tenant itself, not only in the API route. Without an export, a waiver
    or a re-applied purge record, a customer organization's audit trail (inside its retention date) stays."""
    tenant_id = organization["tenant_id"]
    _set_status(tenant_id, "SUSPENDED")
    db = SessionLocal()
    try:
        with pytest.raises(PurgeFailed, match="^EXPORT_REQUIRED$"):
            purge_tenant(db, tenant_id, "test", reason="A direct call without the hand-back")
        with pytest.raises(PurgeFailed, match="^EXPORT_REQUIRED$"):
            purge_tenant(db, tenant_id, "test", reason="Other evidence is not the hand-back", evidence={"note": "x"})
    finally:
        db.close()
    assert _count(AuditEvent, tenant_id=tenant_id, action="TEST_EVENT") == 1
    assert _count(Product, tenant_id=tenant_id) == 1 and _erasure_logs(tenant_id) == []
    db = SessionLocal()
    bind_system(db, "test")
    try:
        tenant = db.get(Tenant, tenant_id)
        assert tenant.status == "SUSPENDED"
        trail = db.query(AuditEvent).filter(AuditEvent.tenant_id == tenant_id).all()
        assert trail and all(event.retention_until > datetime.now(timezone.utc) for event in trail)
    finally:
        db.close()


def test_a_purge_whose_rows_cannot_all_be_deleted_changes_nothing(organization, monkeypatch):
    from backend.app import tenant_purge

    tenant_id = organization["tenant_id"]
    _set_status(tenant_id, "SUSPENDED")
    real_delete_rows = tenant_purge.delete_rows

    def one_table_refuses(db, tables, tenant):
        deleted, remaining = real_delete_rows(db, tables, tenant)  # the deletes really run in the transaction
        return deleted, [*remaining, '"public"."stubborn_table"']

    monkeypatch.setattr(tenant_purge, "delete_rows", one_table_refuses)
    db = SessionLocal()
    try:
        with pytest.raises(PurgeFailed, match="ROWS_REMAIN:"):
            purge_tenant(db, tenant_id, "test", reason="Testing an incomplete database stage", evidence=WAIVED)
    finally:
        db.close()
    # Stage one is all-or-nothing: rows, trail, people, status and files are exactly as before.
    assert _count(Product, tenant_id=tenant_id) == 1
    assert _count(AuditEvent, tenant_id=tenant_id, action="TEST_EVENT") == 1
    assert _erasure_logs(tenant_id) == []
    db = SessionLocal()
    bind_system(db, "test")
    try:
        assert db.get(Tenant, tenant_id).status == "SUSPENDED"
        assert db.get(AuthUser, organization["user_id"]).display_name == "Pat Person"
    finally:
        db.close()
    assert ObjectStorageService().list_tenant_objects(str(tenant_id)) != []


def test_a_purge_with_an_unavailable_file_store_stays_purging_alerts_and_is_finished_by_the_script(
    organization, monkeypatch
):
    from scripts import complete_tenant_purge

    tenant_id = organization["tenant_id"]
    _set_status(tenant_id, "SUSPENDED")
    alerts = []
    monkeypatch.setattr("backend.app.alerts.send_alert", lambda subject, body: alerts.append((subject, body)) or {})
    storage = BrokenStorage()
    db = SessionLocal()
    try:
        incomplete = purge_tenant(
            db, tenant_id, "test", reason="Testing a failed file deletion", storage=storage, evidence=WAIVED
        )
    finally:
        db.close()
    # The database rows are committed (stage one) before the file store is touched; the files step is retried.
    assert incomplete["status"] == "PURGING" and set(incomplete["incomplete"]) == {"files"}
    assert storage.calls == 3
    assert _count(Product, tenant_id=tenant_id) == 0
    assert ObjectStorageService().list_tenant_objects(str(tenant_id)) != []
    assert len(alerts) == 1 and "complete_tenant_purge.py" in alerts[0][1]
    assert _count(AuditEvent, tenant_id=tenant_id, action="TENANT_PURGE_INCOMPLETE") == 1
    [log] = _erasure_logs(tenant_id)
    assert log.details["completed"] is False and "files" in log.details["incomplete"]
    db = SessionLocal()
    bind_system(db, "test")
    try:
        assert db.get(Tenant, tenant_id).status == "PURGING"
    finally:
        db.close()

    # The operator's dry run reports what is left and changes nothing.
    assert complete_tenant_purge.main(["--dry-run", "--tenant", str(tenant_id)]) == 0
    assert ObjectStorageService().list_tenant_objects(str(tenant_id)) != []
    # A run while the store is still down keeps the organization PURGING and exits 1 (a scheduled run alerts).
    assert complete_tenant_purge.main(["--tenant", str(tenant_id)], storage=BrokenStorage()) == 1
    assert len(alerts) == 2
    # Once the store is back, the script finishes the purge and only then archives the organization.
    assert complete_tenant_purge.main(["--tenant", str(tenant_id)]) == 0
    assert ObjectStorageService().list_tenant_objects(str(tenant_id)) == []
    db = SessionLocal()
    bind_system(db, "test")
    try:
        assert db.get(Tenant, tenant_id).status == "ARCHIVED"
        actions = [event.action for event in db.query(AuditEvent).filter(AuditEvent.tenant_id == tenant_id)]
        assert actions.count("TENANT_DATA_DELETED") == 1
    finally:
        db.close()
    [log] = _erasure_logs(tenant_id)
    assert log.details["completed"] is True and log.details["files_deleted"] == 1
    # Nothing is pending any more.
    assert complete_tenant_purge.main(["--tenant", str(tenant_id)]) == 0


def test_a_purge_left_purging_is_resumed_from_the_screen_without_asking_for_the_export_again(
    platform, organization, monkeypatch
):
    monkeypatch.setattr("backend.app.alerts.send_alert", lambda subject, body: {})
    tenant_id = organization["tenant_id"]
    _set_status(tenant_id, "SUSPENDED")
    db = SessionLocal()
    try:
        evidence = {"export": "WAIVED", "export_waiver_reason": "Synthetic test organization"}
        first = purge_tenant(db, tenant_id, "test", reason="First attempt", storage=BrokenStorage(), evidence=evidence)
    finally:
        db.close()
    assert first["status"] == "PURGING"
    response = platform.post(
        f"/api/v1/platform-admin/tenants/{tenant_id}/purge",
        json={**PURGE_BODY, "confirm_tenant_key": organization["tenant_key"]},
    )
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "ARCHIVED" and response.json()["export"] == "WAIVED"
    assert ObjectStorageService().list_tenant_objects(str(tenant_id)) == []


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
    # The erasure is logged by account id only, so a restore from an older backup can repeat it.
    [log] = _erasure_logs(organization["tenant_id"])
    assert log.kind == "PERSON_ERASED" and log.subject_ref == str(user_id) and log.reapplied_at is None
    assert "Pat" not in str(log.details) and "person-" not in str(log.details)


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


def _customer_admin(tenant_id):
    """A signed-in administrator of the customer organization (not the platform administrator who asked)."""
    import secrets

    from fastapi.testclient import TestClient

    from auth.durable import persist_session
    from backend.app.main import app

    now = datetime.now(timezone.utc)
    db = SessionLocal()
    bind_system(db, "test: a customer administrator")
    try:
        user = AuthUser(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            username=f"export-admin-{uuid.uuid4().hex[:8]}@example.invalid",
            display_name="Customer admin",
            company="Purge Test",
            password_hash=_hash("Customer admin 2026!"),
            role="CUSTOMER_ADMIN",
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
                tenant_id=tenant_id,
                user_id=user.id,
                status="ACTIVE",
                is_default=True,
                created_at=now,
                updated_at=now,
            )
        )
        db.commit()
        token = secrets.token_urlsafe(32)
        persist_session(db, token, user.id, tenant_id)
    finally:
        db.close()
    client = TestClient(app)
    client.cookies.set("mdarix_session", token)
    return client


def test_only_the_person_who_asked_downloads_an_export_and_a_refusal_is_audited(platform, organization):
    """RSK-036 (PT-13): another administrator of the organization sees the export but cannot take it."""
    tenant_id = organization["tenant_id"]
    export_id = _export(platform, tenant_id)
    admin = _customer_admin(tenant_id)

    [listed] = [row for row in admin.get("/api/v1/admin/exports").json()["exports"] if row["id"] == export_id]
    assert listed["status"] == "READY" and listed["yours"] is False
    refused = admin.get(f"/api/v1/admin/exports/{export_id}/download")
    assert refused.status_code == 403 and refused.json()["detail"]["code"] == "EXPORT_NOT_REQUESTER"
    assert _count(AuditEvent, tenant_id=tenant_id, action="TENANT_EXPORT_DOWNLOAD_REFUSED") == 1
    assert _count(AuditEvent, tenant_id=tenant_id, action="TENANT_EXPORT_DOWNLOADED") == 0

    base = f"/api/v1/platform-admin/tenants/{tenant_id}/exports"
    [mine] = [row for row in platform.get(base).json()["exports"] if row["id"] == export_id]
    assert mine["yours"] is True
    assert platform.get(f"{base}/{export_id}/download").status_code == 200


def test_an_export_past_its_download_period_is_refused_before_the_hourly_job_deletes_it(platform, organization):
    """RSK-036 (PT-11): the period is enforced at download, not only when export-expiry runs."""
    tenant_id = organization["tenant_id"]
    export_id = _export(platform, tenant_id)
    db = SessionLocal()
    bind_system(db, "test: the download period ends")
    try:
        row = db.get(TenantExport, uuid.UUID(export_id))
        row.expires_at = datetime.now(timezone.utc) - timedelta(minutes=1)
        db.commit()
        assert row.status == "READY"  # the job has not run yet
    finally:
        db.close()
    refused = platform.get(f"/api/v1/platform-admin/tenants/{tenant_id}/exports/{export_id}/download")
    assert refused.status_code == 410 and refused.json()["detail"]["code"] == "EXPORT_EXPIRED"
    assert _count(AuditEvent, tenant_id=tenant_id, action="TENANT_EXPORT_DOWNLOAD_REFUSED") == 1
    assert _count(AuditEvent, tenant_id=tenant_id, action="TENANT_EXPORT_DOWNLOADED") == 0


def test_only_administrators_export_or_delete(organization):
    from tests.test_business_permissions import _client_with_role

    investigator = _client_with_role("Investigator")
    tenant_id = organization["tenant_id"]
    assert investigator.post("/api/v1/admin/exports", json={"reason": "Not allowed for me"}).status_code in (401, 403)
    body = {"reason": "Not allowed for me at all", "password": "x", "confirm_tenant_key": "x"}
    assert investigator.post(f"/api/v1/platform-admin/tenants/{tenant_id}/purge", json=body).status_code in (401, 403)
