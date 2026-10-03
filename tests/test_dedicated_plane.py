"""A customer on a dedicated database (data plane): migrated like the control database, business records routed to
it and nowhere else, refused when its schema is behind, and included in export and deletion.

Needs an empty database the test may migrate: MDARIX_TEST_DATA_PLANE_URL (the CI job "Dedicated data plane" provides
one). Skipped otherwise.
"""

import io
import json
import os
import sys
import uuid
import zipfile
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

from backend.app.db import data_plane
from backend.app.db.models.customer_lifecycle import TenantDataPlane
from backend.app.db.models.foundation import Product
from backend.app.db.session import SessionLocal
from backend.app.db.tenant_scope import bind_system
from backend.app.tenant_export import run_export
from tests.conftest import authenticated_client

PLANE_URL = os.getenv("MDARIX_TEST_DATA_PLANE_URL", "").strip()
SECRET_REF = "MDARIX_DATA_PLANE_CITEST_DATABASE_URL"
PASSWORD = "LegacyTestPassword123!"

pytestmark = pytest.mark.skipif(not PLANE_URL, reason="MDARIX_TEST_DATA_PLANE_URL is not set")


def _reset_plane_caches():
    data_plane.session_factory.cache_clear()
    data_plane._SCHEMA_CHECKED.clear()


@pytest.fixture(scope="module")
def dedicated(tmp_path_factory):
    """A new customer moved onto the test plane, which is migrated to head by scripts/migrate_data_planes.py."""
    os.environ[SECRET_REF] = PLANE_URL
    # The migrations include the database hardening (roles, row-level security), applied to the plane on purpose.
    os.environ["MDARIX_DB_HARDENING_APPLY"] = "1"
    os.environ["MDARIX_OBJECT_STORAGE_ROOT"] = str(tmp_path_factory.mktemp("objects"))
    _reset_plane_caches()
    platform = authenticated_client()
    code = f"DPL{uuid.uuid4().hex[:6].upper()}"
    created = platform.post(
        "/api/v1/platform-admin/customers",
        json={"company_name": f"Dedicated {code}", "tenant_code": code, "plan_code": "STARTER"},
    )
    assert created.status_code == 200, created.text
    tenant_id = uuid.UUID(created.json()["id"])
    db = SessionLocal()
    bind_system(db, "test")
    plane = db.query(TenantDataPlane).filter(TenantDataPlane.tenant_id == tenant_id).one()
    plane.connection_secret_ref = SECRET_REF
    plane.database_ref = f"citest-{code.lower()}"
    db.commit()
    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
    from migrate_data_planes import head_revision, migrate, plane_state

    print(migrate(plane, head_revision(), apply=True))
    assert plane_state(PLANE_URL) == ("MANAGED", head_revision())
    db.close()
    _reset_plane_caches()
    yield {"tenant_id": tenant_id, "tenant_key": created.json()["tenant_key"], "platform": platform}
    os.environ.pop(SECRET_REF, None)
    _reset_plane_caches()


def _plane_count(sql: str, **params) -> int:
    engine = create_engine(PLANE_URL)
    try:
        with engine.connect() as connection:
            return int(connection.execute(text(sql), params).scalar() or 0)
    finally:
        engine.dispose()


def test_business_records_are_written_to_the_customers_own_database(dedicated):
    tenant_id = dedicated["tenant_id"]
    response = dedicated["platform"].post(
        "/api/v1/platform/product-configuration/products",
        json={"tenant_id": str(tenant_id), "product_identifier": "DP-1", "name": "Dedicated pump"},
    )
    assert response.status_code == 200, response.text
    assert _plane_count("SELECT count(*) FROM products WHERE tenant_id = :t", t=tenant_id) == 1
    db = SessionLocal()
    bind_system(db, "test")
    try:
        assert db.query(Product).filter(Product.tenant_id == tenant_id).count() == 0
    finally:
        db.close()
    view = dedicated["platform"].get(f"/api/v1/platform/product-configuration/{tenant_id}").json()
    assert [item["identifier"] for item in view["products"]] == ["DP-1"]


def test_the_plane_has_the_same_protections_as_the_control_database(dedicated):
    assert _plane_count("SELECT count(*) FROM pg_policies WHERE policyname = 'mdarix_tenant_isolation'") > 50
    assert (
        _plane_count("SELECT count(*) FROM pg_trigger WHERE tgname IN ('audit_events_chain', 'audit_events_immutable')")
        == 2
    )
    assert _plane_count("SELECT count(*) FROM tenants WHERE id = :t", t=dedicated["tenant_id"]) == 1


def test_a_plane_behind_the_code_refuses_requests(dedicated, monkeypatch):
    monkeypatch.setattr(data_plane, "schema_head", lambda: "a-newer-revision")
    _reset_plane_caches()
    try:
        assert data_plane.plane_schema_ok(f"citest-{dedicated['tenant_key'].lower()}", SECRET_REF) is False
        with pytest.raises(RuntimeError, match="DATA_PLANE_SCHEMA_OUTDATED"):
            with data_plane.open_tenant_data_session(dedicated["tenant_id"]):
                pass
    finally:
        _reset_plane_caches()


def test_export_and_deletion_cover_the_dedicated_database(dedicated):
    tenant_id = dedicated["tenant_id"]
    platform = dedicated["platform"]
    queued = platform.post(f"/api/v1/platform-admin/tenants/{tenant_id}/exports", json={"reason": "Return the data"})
    assert queued.status_code == 202, queued.text
    run_export(queued.json()["id"])
    content = platform.get(f"/api/v1/platform-admin/tenants/{tenant_id}/exports/{queued.json()['id']}/download").content
    manifest = json.loads(zipfile.ZipFile(io.BytesIO(content)).read("manifest.json"))
    assert manifest["tables"]["plane:public.products"]["rows"] >= 1

    db = SessionLocal()
    bind_system(db, "test")
    db.execute(text("UPDATE tenants SET status = 'SUSPENDED' WHERE id = :t"), {"t": tenant_id})
    db.commit()
    db.close()
    purged = platform.post(
        f"/api/v1/platform-admin/tenants/{tenant_id}/purge",
        json={
            "reason": "End of the pilot, data returned",
            "password": PASSWORD,
            "confirm_tenant_key": dedicated["tenant_key"],
        },
    )
    assert purged.status_code == 200, purged.text
    assert purged.json()["deleted_records"]["plane:products"] >= 1
    assert _plane_count("SELECT count(*) FROM products WHERE tenant_id = :t", t=tenant_id) == 0
