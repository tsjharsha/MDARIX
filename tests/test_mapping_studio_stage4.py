from pathlib import Path

import pytest

from backend.app.db.session import SessionLocal
from backend.app.main import app
from backend.app.master_data import catalog
from backend.app.mapping_catalog_router import source_fields, canonical_fields


@pytest.fixture
def catalog_db(monkeypatch):
    """Real test-database session (Master Data seed) with the platform-admin guard bypassed."""
    from backend.app import mapping_catalog_router

    monkeypatch.setattr(mapping_catalog_router, "_platform_admin", lambda db, ctx: None)
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


def _admin_db():
    class Db:
        def query(self, model):
            class Q:
                def filter(self, *args):
                    return self

                def first(self):
                    return type("User", (), {"role": "Administrator", "status": "ACTIVE"})()

            return Q()

    return Db()


def _ctx():
    return type(
        "Ctx",
        (),
        {"user_id": "00000000-0000-0000-0000-000000000000", "tenant_id": "00000000-0000-0000-0000-000000000000"},
    )()


def test_stage4_application_objects_are_scoped_to_application(catalog_db):
    for application in catalog.applications(catalog_db):
        objects = catalog.application_objects(catalog_db, application["application_id"])
        assert objects
        assert all(item["source_object_id"].startswith(application["application_id"] + ":") for item in objects)


def test_stage4_catalogs_and_protected_fields_are_available(catalog_db):
    # The catalog is extensible: new provider simulators may be added without
    # invalidating the Stage 4 contract. Keep the original minimum coverage.
    assert len(catalog.applications(catalog_db)) >= 12
    for entity in catalog.canonical_entities(catalog_db):
        fields = canonical_fields(entity["entity_id"], catalog_db, _ctx())
        assert fields
        assert all("mapping_allowed" in field and "required" in field for field in fields)
    fields = source_fields("TRACKWISE:COMPLAINT", catalog_db, _ctx())
    assert any(field["field_group"] == "IDENTIFIERS" for field in fields)
    assert any(field["field_group"] == "DATES" for field in fields)


def test_stage4_required_routes_and_ci_contract_are_present():
    paths = set(app.openapi()["paths"])
    required = {
        "/api/v1/admin/mapping/applications",
        "/api/v1/admin/mapping/applications/{application_id}/objects",
        "/api/v1/admin/mapping/objects/{source_object_id}/fields",
        "/api/v1/admin/mapping/canonical/entities/{entity_id}/fields",
        "/api/v1/admin/mapping/dry-run",
        "/api/v1/admin/mapping/validate",
        "/api/v1/admin/mapping/schema-discovery",
        "/api/v1/admin/mapping/compare",
        "/api/v1/admin/mapping/impact-history",
        "/api/v1/admin/mapping/suggestions",
    }
    assert required <= paths
    assert Path(".github/workflows/ci.yml").exists()


def test_stage4_final_evidence_never_contains_secrets():
    evidence = Path("evidence/mapping-studio")
    if not evidence.exists():
        return
    prohibited = {"password", "api_key", "token", "secret", "credential"}
    for path in evidence.rglob("*"):
        if path.is_file():
            text = path.read_text(encoding="utf-8").lower()
            assert not any(f"{word}=" in text or f"{word}:" in text for word in prohibited), path
