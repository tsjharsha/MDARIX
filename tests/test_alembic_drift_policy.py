from pathlib import Path

from infrastructure.database.migrations.business_ids import COUNTER_TABLE, INDEX_NAMES
from infrastructure.database.migrations.drift_policy import (
    MIGRATION_OWNED_INDEXES,
    MIGRATION_OWNED_TABLES,
    include_name,
    include_object,
)

ROOT = Path(__file__).resolve().parents[1]


def test_schema_filter_includes_all_and_only_mdarix_schemas():
    assert include_name(None, "schema", {}) is True
    assert include_name("public", "schema", {}) is True
    assert include_name("md_master", "schema", {}) is True
    assert include_name("information_schema", "schema", {}) is False
    assert include_name("products", "table", {"schema_name": "public"}) is True
    assert include_name("pg_class", "table", {"schema_name": "pg_catalog"}) is False


def test_only_exact_migration_owned_objects_are_excluded():
    assert include_object(object(), "mdarix_rls_secret", "table", True, None) is False
    assert include_object(object(), "ix_audit_events_tenant_hash", "index", True, None) is False
    assert include_object(object(), "unexpected_table", "table", True, None) is True
    assert include_object(object(), "unexpected_index", "index", True, None) is True
    assert include_object(object(), "ix_audit_events_tenant_hash", "index", False, None) is True


def test_drift_allowlist_objects_are_owned_by_versioned_migrations():
    versions = ROOT / "infrastructure" / "database" / "migrations" / "versions"
    migration_text = "\n".join(path.read_text(encoding="utf-8") for path in versions.glob("*.py"))
    # The business-id counter table and per-table indexes are named in one shared module, which md26 imports to
    # create them; every other allowlisted object must be spelled out in a migration.
    business_id_migration = (versions / "md26_business_ids.py").read_text(encoding="utf-8")
    assert "from infrastructure.database.migrations.business_ids import COUNTER_TABLE" in business_id_migration
    assert "CREATE UNIQUE INDEX {item.index_name}" in business_id_migration
    generated = {COUNTER_TABLE} | INDEX_NAMES
    for name in (MIGRATION_OWNED_TABLES | MIGRATION_OWNED_INDEXES) - generated:
        assert name in migration_text, f"{name} is allowlisted but is not created by a migration"


def test_ci_runs_alembic_check_after_applying_migrations():
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")
    upgrade_position = workflow.index("run: alembic upgrade head")
    check_position = workflow.index("run: alembic check")
    assert upgrade_position < check_position
