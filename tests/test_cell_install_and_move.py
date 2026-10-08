"""A tenant cell is built from the platform's signed documents and licensed; an organization moves into one.

Each test creates its own empty database on the test server (the test login owns the server, locally and in CI),
installs it with scripts/cell_install.py exactly as an operator would, and drops it afterwards. The move test seeds
an organization with records in most business tables, people with an MFA secret, a connector credential, a stored
file and audit events, moves it with scripts/move_tenant_to_cell.py, and checks the cell holds the same rows with
the same ids, the audit chain verbatim, the secrets readable under the cell's own keys, and the source untouched.
"""

import argparse
import base64
import json
import os
import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from backend.app.cell_licence import apply_licence
from backend.app.cell_packages import PackageError, generate_keypair, verify
from backend.app.db.models.foundation import AuditEvent, AuthUser, ConnectorConfiguration, Tenant
from backend.app.db.session import SessionLocal, engine
from backend.app.db.tenant_scope import _APPLY, bind_system
from backend.app.db.tls import connect_args
from scripts import cell_install, cell_platform
from scripts import move_tenant_to_cell as mover
from scripts.migrate_data_planes import head_revision
from tests.conftest import with_signing_plan
from tests.test_mapping_release_self_approval import _admin, _organization

MFA_SECRET = "JBSWY3DPEHPK3PXP"
CONNECTOR_KEY = "sk-live-0123456789abcdef0123456789abcdef"
FILE_CONTENT = b"%PDF-1.4 supplier certificate for the move"
BUSINESS_TABLES = ("products", "product_versions", "complaints", "investigations", "evidence", "suppliers", "risks")


@pytest.fixture
def cell_database():
    """A brand-new empty database on the test server, dropped afterwards."""
    from sqlalchemy.pool import NullPool

    name = f"mdarix_cell_{uuid.uuid4().hex[:8]}"
    # CREATE and DROP DATABASE refuse to run inside a transaction: a dedicated, unpooled autocommit engine.
    admin = create_engine(engine.url, isolation_level="AUTOCOMMIT", poolclass=NullPool, connect_args=connect_args())
    with admin.connect() as connection:
        connection.execute(text(f'CREATE DATABASE "{name}"'))
    try:
        yield engine.url.set(database=name).render_as_string(hide_password=False)
    finally:
        with admin.connect() as connection:
            connection.execute(
                text(
                    "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = :n AND pid <> pg_backend_pid()"
                ),
                {"n": name},
            )
            connection.execute(text(f'DROP DATABASE IF EXISTS "{name}"'))
        admin.dispose()


@pytest.fixture(scope="module")
def signing():
    return generate_keypair()


def _tenant(tenant_id: str) -> Tenant:
    db = SessionLocal()
    try:
        bind_system(db, "test: read the organization")
        row = db.query(Tenant).filter(Tenant.id == uuid.UUID(tenant_id)).one()
        db.expunge(row)
        return row
    finally:
        db.close()


def _issue(tenant_key: str, private_key: str, tmp_path) -> tuple[str, str, dict, dict]:
    db = SessionLocal()
    try:
        enrollment, licence = cell_platform.issue(
            db,
            tenant_key,
            hosting_mode="MDARIX_MANAGED",
            admin_email="first.admin@cell.invalid",
            admin_name="First Admin",
            private_key=private_key,
        )
    finally:
        db.close()
    bundle, licence_file = tmp_path / "enrollment.json", tmp_path / "licence.json"
    bundle.write_text(json.dumps(enrollment), encoding="utf-8")
    licence_file.write_text(json.dumps(licence), encoding="utf-8")
    return str(bundle), str(licence_file), enrollment, licence


def _install_args(database_url: str, bundle: str, licence: str | None, public_key: str, env_out, **overrides):
    runtime_password = os.environ.get("MDARIX_DB_RUNTIME_PASSWORD") or None
    values = {
        "database_url": database_url,
        "bundle": bundle,
        "licence": licence,
        "no_licence": licence is None,
        "platform_public_key": public_key,
        "app_url": "https://cell.test",
        "env_out": str(env_out),
        # The runtime role is shared by every database of the test server: keep its password as it is.
        "runtime_password": runtime_password,
        "skip_runtime_role": runtime_password is None or len(runtime_password) < 24,
        "no_admin_invitation": False,
        "apply": True,
    }
    values.update(overrides)
    return argparse.Namespace(**values)


def _cell_connection(database_url: str, token: str):
    cell_engine = create_engine(database_url, future=True, connect_args=connect_args())
    connection = cell_engine.connect()
    connection.execute(_APPLY, {"tenant": "", "bypass": token})
    return cell_engine, connection


def _counts(connection, tenant_id, tables) -> dict[str, int]:
    return {
        table: int(
            connection.execute(text(f"SELECT count(*) FROM {table} WHERE tenant_id = :t"), {"t": tenant_id}).scalar()
        )
        for table in tables
    }


def test_a_cell_is_installed_from_signed_documents_and_licensed(cell_database, signing, tmp_path):
    private, public = signing
    organization = _tenant(_organization())
    bundle, licence, enrollment, licence_envelope = _issue(organization.tenant_key, private, tmp_path)
    assert verify(enrollment, public, kind="ENROLLMENT")["tenant"]["tenant_key"] == organization.tenant_key
    with pytest.raises(PackageError):
        verify(licence_envelope, generate_keypair()[1])  # another key: refused
    tampered = {**licence_envelope, "content": {**licence_envelope["content"], "status": "SUSPENDED"}}
    with pytest.raises(PackageError):
        verify(tampered, public)

    # Without --apply nothing is written; with it the cell is built.
    assert (
        cell_install.main(
            ["--database-url", cell_database, "--bundle", bundle, "--licence", licence, "--platform-public-key", public]
        )
        == 0
    )
    env_file = tmp_path / "cell.env"
    summary = cell_install.install(_install_args(cell_database, bundle, licence, public, env_file))
    assert summary["state_after"] == ("MANAGED", head_revision())
    assert summary["organization_created"] and summary["organizations_in_database"] == 1
    assert (
        summary["licence_applied"]["applied"]
        and summary["licence_applied"]["plan"] == licence_envelope["content"]["plan"]["code"]
    )
    assert summary["activation_link"].startswith("https://cell.test/activate-account?token=")
    settings = mover.read_env_file(str(env_file))
    assert settings["MDARIX_DEPLOYMENT_ROLE"] == "CELL"
    assert (
        settings["MDARIX_CELL_TENANT_ID"] == str(organization.id)
        and settings["MDARIX_CELL_TENANT_KEY"] == organization.tenant_key
    )
    assert settings["MDARIX_PLATFORM_SIGNING_PUBLIC_KEY"] == public
    for name in (
        "MDARIX_RLS_SYSTEM_TOKEN",
        "MDARIX_MFA_ENCRYPTION_KEY",
        "MDARIX_CONNECTOR_ENCRYPTION_KEY",
        "MDARIX_OBJECT_STORAGE_ENCRYPTION_KEY",
    ):
        assert len(settings[name]) >= 32
    assert len(base64.urlsafe_b64decode(settings["MDARIX_MFA_ENCRYPTION_KEY"])) == 32

    cell_engine, cell = _cell_connection(cell_database, settings["MDARIX_RLS_SYSTEM_TOKEN"])
    try:
        tenants = cell.execute(text("SELECT id, tenant_key, deployment_model, status FROM tenants")).all()
        assert len(tenants) == 1 and tenants[0].id == organization.id and tenants[0].deployment_model == "CELL"
        plane = cell.execute(
            text("SELECT connection_secret_ref, status FROM tenant_data_planes WHERE tenant_id = :t"),
            {"t": organization.id},
        ).one()
        assert plane.connection_secret_ref == "MDARIX_TRIAL_SHARED_CONTROL_PLANE" and plane.status == "ACTIVE"
        assert all(count == 0 for count in _counts(cell, organization.id, BUSINESS_TABLES).values())
        admin = cell.execute(
            text("SELECT role, status FROM auth_users WHERE tenant_id = :t"), {"t": organization.id}
        ).all()
        assert admin == [("CUSTOMER_ADMIN", "INVITED")]
        assert (
            cell.execute(
                text("SELECT count(*) FROM user_invitations WHERE tenant_id = :t"), {"t": organization.id}
            ).scalar()
            == 1
        )
        assert (
            cell.execute(text("SELECT status FROM cell_licences WHERE tenant_id = :t"), {"t": organization.id}).scalar()
            == "ACTIVE"
        )
        audit = cell.execute(
            text("SELECT action, chain_seq FROM audit_events WHERE tenant_id = :t ORDER BY chain_seq"),
            {"t": organization.id},
        ).all()
        assert audit == [("LICENCE_APPLIED", 1)]
        # The cell reads entitlements from the licence's rows, through the same rule as every deployment.
        from backend.app.access.plan_features import plan_includes

        with cell_install.environment(MDARIX_RLS_SYSTEM_TOKEN=settings["MDARIX_RLS_SYSTEM_TOKEN"]):
            session = sessionmaker(bind=cell_engine, future=True)()
            try:
                bind_system(session, "test: entitlements in the cell")
                assert plan_includes(session, organization.id, "DECISION_CENTER_SIGNATURES")
                assert plan_includes(session, organization.id, "ADMIN_CONTROL_PLANE")
                assert apply_licence(session, licence_envelope, public)["reason"] == "ALREADY_APPLIED"
            finally:
                session.close()
    finally:
        cell.close()
        cell_engine.dispose()


def _seed_source_organization(tenant: Tenant, source_objects_root) -> dict:
    """Records in most business tables, a person with an MFA secret, a connector credential, a file, audit events."""
    from access_control.connector_secrets import seal
    from auth.totp import encrypt_secret
    from backend.app.demo_workspace import load_story
    from object_storage.service import ObjectStorageService

    _, admin_id = _admin(str(tenant.id))
    now = datetime.now(timezone.utc)
    db = SessionLocal()
    try:
        bind_system(db, "test: seed the organization to move")
        row = db.query(Tenant).filter(Tenant.id == tenant.id).one()
        with_signing_plan(db, row)
        load_story(db, tenant.id, now)
        user = db.query(AuthUser).filter(AuthUser.id == admin_id).one()
        user.mfa_secret_encrypted = encrypt_secret(MFA_SECRET, str(user.id))
        connector = ConnectorConfiguration(
            id=uuid.uuid4(),
            tenant_id=tenant.id,
            code="TRACKWISE-MOVE",
            connector_type="REST",
            configuration={"endpoint": "https://source.example", "records_path": "records/complaints"},
            version="v1",
            status="ACTIVE",
            credential_set_at=now,
            created_at=now,
            updated_at=now,
        )
        connector.credential_encrypted = seal(CONNECTOR_KEY, tenant.id, connector.id)
        db.add(connector)
        for index in range(3):
            db.add(
                AuditEvent(
                    id=uuid.uuid4(),
                    tenant_id=tenant.id,
                    actor_ref=str(admin_id),
                    action=f"MOVE_TEST_EVENT_{index}",
                    entity_type="Test",
                    details={"index": index},
                    created_at=now,
                )
            )
        db.commit()
        connector_id = connector.id
    finally:
        db.close()
    stored = ObjectStorageService(root=str(source_objects_root)).put(
        str(tenant.id), "evidence/certificate.pdf", FILE_CONTENT, content_type="application/pdf", internal=True
    )
    return {"admin_id": admin_id, "connector_id": connector_id, "object_key": stored["object_key"]}


def test_an_organization_moves_into_its_cell_with_records_secrets_and_audit_trail(
    cell_database, signing, tmp_path, monkeypatch
):
    private, public = signing
    source_objects, target_objects = tmp_path / "source-objects", tmp_path / "target-objects"
    monkeypatch.setenv("MDARIX_OBJECT_STORAGE_PROVIDER", "local")
    monkeypatch.setenv("MDARIX_OBJECT_STORAGE_ENCRYPTION_KEY", base64.urlsafe_b64encode(os.urandom(32)).decode())
    organization = _tenant(_organization())
    seeded = _seed_source_organization(organization, source_objects)
    bundle, licence, _, licence_envelope = _issue(organization.tenant_key, private, tmp_path)

    # The cell: installed without a licence and without the first administrator (the move brings both).
    env_file = tmp_path / "cell.env"
    cell_install.install(_install_args(cell_database, bundle, None, public, env_file, no_admin_invitation=True))
    settings = mover.read_env_file(str(env_file))

    with engine.connect() as source:
        source.execute(
            _APPLY,
            {
                "tenant": "",
                "bypass": __import__("backend.app.db.tenant_scope", fromlist=["system_token"]).system_token(),
            },
        )
        before = _counts(
            source, organization.id, BUSINESS_TABLES + ("auth_users", "connector_configurations", "audit_events")
        )
        source_chain = source.execute(
            text("SELECT chain_seq, event_hash FROM audit_events WHERE tenant_id = :t ORDER BY chain_seq"),
            {"t": organization.id},
        ).all()
    assert all(before[table] > 0 for table in BUSINESS_TABLES) and before["audit_events"] >= 3

    common = [
        "--tenant-key",
        organization.tenant_key,
        "--target-url",
        cell_database,
        "--target-env",
        str(env_file),
        "--licence",
        licence,
        "--source-objects-root",
        str(source_objects),
        "--target-objects-root",
        str(target_objects),
    ]
    assert mover.main(common) == 0  # the plan: nothing written
    cell_engine, cell = _cell_connection(cell_database, settings["MDARIX_RLS_SYSTEM_TOKEN"])
    try:
        assert all(count == 0 for count in _counts(cell, organization.id, BUSINESS_TABLES).values())
    finally:
        cell.close()
    assert mover.main(common + ["--apply"]) == 0

    cell_engine, cell = _cell_connection(cell_database, settings["MDARIX_RLS_SYSTEM_TOKEN"])
    try:
        after = _counts(
            cell, organization.id, BUSINESS_TABLES + ("auth_users", "connector_configurations", "audit_events")
        )
        assert {table: after[table] for table in BUSINESS_TABLES + ("auth_users", "connector_configurations")} == {
            table: before[table] for table in BUSINESS_TABLES + ("auth_users", "connector_configurations")
        }
        # The audit trail verbatim, then the licence on top of it.
        assert after["audit_events"] == before["audit_events"] + 1
        cell_chain = cell.execute(
            text("SELECT chain_seq, event_hash, action FROM audit_events WHERE tenant_id = :t ORDER BY chain_seq"),
            {"t": organization.id},
        ).all()
        assert [(row.chain_seq, row.event_hash) for row in cell_chain[:-1]] == [tuple(row) for row in source_chain]
        assert cell_chain[-1].action == "LICENCE_APPLIED"
        chain = cell.execute(mover.VERIFY, {"t": organization.id}).one()
        assert chain.first_broken_seq is None and chain.checked == after["audit_events"]
        assert cell.execute(text("SELECT count(*) FROM tenants")).scalar() == 1
        assert (
            cell.execute(
                text("SELECT count(*) FROM auth_sessions WHERE tenant_id = :t"), {"t": organization.id}
            ).scalar()
            == 0
        )
        assert (
            cell.execute(text("SELECT status FROM cell_licences WHERE tenant_id = :t"), {"t": organization.id}).scalar()
            == "ACTIVE"
        )
        business_ids = (
            cell.execute(
                text("SELECT business_id FROM products WHERE tenant_id = :t ORDER BY 1"), {"t": organization.id}
            )
            .scalars()
            .all()
        )
        with engine.connect() as source:
            source.execute(
                _APPLY,
                {
                    "tenant": "",
                    "bypass": __import__("backend.app.db.tenant_scope", fromlist=["system_token"]).system_token(),
                },
            )
            assert (
                business_ids
                == source.execute(
                    text("SELECT business_id FROM products WHERE tenant_id = :t ORDER BY 1"), {"t": organization.id}
                )
                .scalars()
                .all()
            )
            # The source is as it was.
            assert (
                _counts(
                    source,
                    organization.id,
                    BUSINESS_TABLES + ("auth_users", "connector_configurations", "audit_events"),
                )
                == before
            )
        # Secrets open under the cell's keys, not the source's.
        from access_control.connector_secrets import open_sealed
        from auth.totp import decrypt_secret
        from object_storage.service import ObjectStorageService

        mfa = cell.execute(
            text("SELECT mfa_secret_encrypted FROM auth_users WHERE id = :u"), {"u": seeded["admin_id"]}
        ).scalar()
        sealed = cell.execute(
            text("SELECT credential_encrypted FROM connector_configurations WHERE id = :c"),
            {"c": seeded["connector_id"]},
        ).scalar()
        with pytest.raises(Exception):
            decrypt_secret(mfa, str(seeded["admin_id"]))  # the source's key does not open it
        with cell_install.environment(**{name: settings.get(name) for name in mover.KEY_SETTINGS}):
            assert decrypt_secret(mfa, str(seeded["admin_id"])) == MFA_SECRET
            assert open_sealed(sealed, organization.id, seeded["connector_id"]) == CONNECTOR_KEY
            assert (
                ObjectStorageService(root=str(target_objects)).get(str(organization.id), seeded["object_key"])
                == FILE_CONTENT
            )
    finally:
        cell.close()
        cell_engine.dispose()
