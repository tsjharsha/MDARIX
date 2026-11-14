"""Database-level defences of release DB-1 (MDARIX-planning/db-audit/report.md, defects DB-01, DB-02, DB-15).

These read the catalogue of the migrated test database, and act as the least-privilege runtime role (``SET ROLE
mdarix_runtime`` on an owner connection) bound to one organization, as a production request is.
"""

import uuid
from contextlib import contextmanager

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError

from backend.app.db.session import engine
from backend.app.db.tenant_scope import LOCAL_SYSTEM_TOKEN

RUNTIME = "mdarix_runtime"

# Tables without row-level security that the runtime role may still write, each with the reason. Adding one is a
# security review (DB-15). Everything else without row-level security is read only for the runtime role.
RUNTIME_WRITABLE_WITHOUT_RLS = {
    "auth_sessions": "sign-in sessions, resolved from the cookie before the organization is known",
    "login_throttles": "sign-in throttling, written before the organization is known",
    "rate_limit_counters": "request throttling, written before the organization is known",
    "onboarding_requests": "website demo and trial requests, before any organization exists",
    "demo_requests": "website demo requests, before any organization exists",
    "trial_exit_requests": "a trial's exit request (trial_tenant_id, DB-09: P3)",
    "domain_verifications": "customer domain checks, platform administration",
    "feature_entitlements": "the plan catalogue, platform administration",
    "plan_definitions": "the plan catalogue, platform administration",
    "packages": "the plan catalogue, platform administration",
    "identity_rules": "platform sign-in rules, platform administration",
    "configuration_baselines": "platform configuration baselines",
    "configuration_baseline_versions": "platform configuration baselines",
    "baseline_differences": "platform configuration baselines",
    "code_list_files": "the shared code lists, platform administration",
    "imdrf_codes": "the shared IMDRF code list",
    "reference_codes": "the shared reference codes",
    "master_mappings": "the shared mapping catalogue",
    "source_mappings": "the shared mapping catalogue",
    "genai_provider_rest": "AI provider state of the platform",
    "platform_incidents": "platform operations records",
    "provisioning_jobs": "platform onboarding jobs",
    "provisioning_job_steps": "steps of platform onboarding jobs",
    "scheduler_runs": "background job bookkeeping",
    "worker_heartbeats": "background worker bookkeeping",
}


@contextmanager
def as_runtime(tenant_id=None, *, system: bool = False):
    """A connection acting as the runtime role, bound to ``tenant_id`` (or system scope); always rolled back."""
    with engine.connect() as connection:
        transaction = connection.begin()
        try:
            connection.execute(text(f"SET LOCAL ROLE {RUNTIME}"))
            connection.execute(
                text("SELECT set_config('app.tenant_id', :t, true), set_config('app.rls_bypass', :b, true)"),
                {"t": str(tenant_id) if tenant_id else "", "b": LOCAL_SYSTEM_TOKEN if system else ""},
            )
            yield connection
        finally:
            transaction.rollback()


def _two_tenants(connection) -> tuple[uuid.UUID, uuid.UUID]:
    rows = connection.execute(text("SELECT id FROM tenants ORDER BY created_at, id LIMIT 2")).scalars().all()
    if len(rows) < 2:
        pytest.skip("the test database needs two organizations")
    return rows[0], rows[1]


def test_the_runtime_role_writes_no_table_without_row_level_security_beyond_the_reviewed_list():
    with engine.connect() as connection:
        writable = {
            row[0]
            for row in connection.execute(
                text(
                    "SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
                    "WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p') AND NOT c.relrowsecurity "
                    "AND (has_table_privilege(:r, c.oid, 'INSERT') OR has_table_privilege(:r, c.oid, 'UPDATE') "
                    "OR has_table_privilege(:r, c.oid, 'DELETE'))"
                ),
                {"r": RUNTIME},
            )
        }
    assert "alembic_version" not in writable and "business_id_counters" not in writable
    assert writable <= set(RUNTIME_WRITABLE_WITHOUT_RLS), "Review, then list or revoke: " + ", ".join(
        sorted(writable - set(RUNTIME_WRITABLE_WITHOUT_RLS))
    )


def test_an_organization_session_reads_but_cannot_change_the_data_plane_registry():
    with engine.connect() as connection:
        tenant_a, tenant_b = _two_tenants(connection)
    with as_runtime(tenant_a) as connection:
        assert connection.scalar(text("SELECT count(*) FROM tenant_data_planes")) >= 1
        changed = connection.execute(
            text("UPDATE tenant_data_planes SET status = status WHERE tenant_id = :b"), {"b": tenant_b}
        ).rowcount
        assert changed == 0
    with as_runtime(tenant_a) as connection:
        with pytest.raises(DBAPIError):
            connection.execute(text("UPDATE alembic_version SET version_num = version_num"))
    with as_runtime(tenant_a) as connection:
        with pytest.raises(DBAPIError):
            connection.execute(text("UPDATE business_id_counters SET last_value = last_value"))


def test_system_scope_still_changes_the_data_plane_registry():
    with as_runtime(system=True) as connection:
        assert connection.execute(text("UPDATE tenant_data_planes SET status = status")).rowcount >= 1


def test_a_business_identifier_is_still_assigned_under_the_runtime_role():
    """The counters are read only for the runtime role; the md26 trigger (SECURITY DEFINER) still numbers rows."""
    with engine.connect() as connection:
        tenant_a, _ = _two_tenants(connection)
    with as_runtime(tenant_a) as connection:
        business_id = connection.scalar(
            text(
                "INSERT INTO products (id, tenant_id, product_identifier, name, created_at, updated_at) "
                "VALUES (gen_random_uuid(), :t, :code, 'DB-1 probe', now(), now()) RETURNING business_id"
            ),
            {"t": tenant_a, "code": f"DB1-{uuid.uuid4().hex[:8]}"},
        )
        assert business_id and business_id.startswith("PROD")


# --- DB-01 and PV-1 F1: references between organization tables (tr22, tr23) -------------------------------------

# A reference between two organization tables that may leave out tenant_id, with the reason (DB-15).
SINGLE_COLUMN_ALLOWED = {
    "fk_provisioning_job_steps_provisioning_job_id_provisioning_jobs": "a step's tenant_id may be empty; the "
    "composite reference stands beside it",
}


def test_every_reference_between_organization_tables_includes_the_organization():
    with engine.connect() as connection:
        rows = connection.execute(
            text(
                """
                WITH owned AS (SELECT attrelid FROM pg_attribute WHERE attname = 'tenant_id' AND NOT attisdropped)
                SELECT con.conname,
                       EXISTS (SELECT 1 FROM unnest(con.conkey) k JOIN pg_attribute a
                               ON a.attrelid = con.conrelid AND a.attnum = k WHERE a.attname = 'tenant_id'),
                       EXISTS (SELECT 1 FROM unnest(con.confkey) k JOIN pg_attribute a
                               ON a.attrelid = con.confrelid AND a.attnum = k WHERE a.attname = 'tenant_id')
                FROM pg_constraint con JOIN pg_class parent ON parent.oid = con.confrelid
                JOIN pg_namespace n ON n.oid = parent.relnamespace
                WHERE con.contype = 'f' AND n.nspname = 'public' AND parent.relname <> 'tenants'
                  AND con.conrelid IN (SELECT attrelid FROM owned) AND con.confrelid IN (SELECT attrelid FROM owned)
                """
            )
        ).all()
    assert len(rows) > 100, "the catalogue was not read from a migrated database"
    missing = sorted(
        name for name, child, parent in rows if not (child and parent) and name not in SINGLE_COLUMN_ALLOWED
    )
    assert not missing, "Make these references composite (tenant_id, x_id): " + ", ".join(missing)


def _copy_row(connection, table: str, changes: dict) -> uuid.UUID | None:
    """Insert a copy of one existing row of ``table`` with ``changes`` (business_id is reassigned); None without one."""
    columns = list(
        connection.execute(
            text(
                "SELECT column_name FROM information_schema.columns WHERE table_schema = 'public' AND table_name = :t "
                "AND column_name NOT IN ('id', 'business_id') AND is_generated = 'NEVER' ORDER BY ordinal_position"
            ),
            {"t": table},
        ).scalars()
    )
    if not connection.execute(text(f"SELECT 1 FROM {table} LIMIT 1")).first():
        return None
    values = ", ".join(f":{name}" if name in changes else name for name in columns)
    return connection.execute(
        text(
            f"INSERT INTO {table} (id, {', '.join(columns)}) SELECT gen_random_uuid(), {values} FROM {table} "
            "LIMIT 1 RETURNING id"
        ),
        changes,
    ).scalar()


def test_an_organization_cannot_reference_another_organizations_row_even_under_the_runtime_role():
    """The reverse of db-audit t_crossfk.sql: tenant A's staged record pointing at B's ingestion run is refused."""
    with engine.connect() as connection:
        tenant_a, tenant_b = _two_tenants(connection)
        connection.rollback()
        with connection.begin():
            run_b = _copy_row(connection, "ingestion_runs", {"tenant_id": tenant_b})
    if run_b is None:
        pytest.skip("the test database has no ingestion run to copy")
    try:
        with as_runtime(system=True) as connection:
            # Copy as system scope (every row visible), then act as tenant A for the insert itself.
            source = connection.execute(text("SELECT * FROM staged_source_records LIMIT 1")).mappings().one()
        with as_runtime(tenant_a) as connection:
            columns = [c for c in source.keys() if c not in ("id", "business_id")]
            row = {
                **source,
                "tenant_id": tenant_a,
                "ingestion_run_id": run_b,
                "source_record_id": f"DB1-{uuid.uuid4()}",
            }
            with pytest.raises(DBAPIError) as refused:
                connection.execute(
                    text(
                        f"INSERT INTO staged_source_records ({', '.join(columns)}) "
                        f"VALUES ({', '.join(':' + c for c in columns)})"
                    ),
                    {c: row[c] for c in columns},
                )
            assert "fk_staged_source_records_ingestion_run_id_tenant" in str(refused.value)
    finally:
        with engine.begin() as connection:
            connection.execute(text("DELETE FROM ingestion_runs WHERE id = :id"), {"id": run_b})


def _versions_of_two_products(connection):
    """(tenant, product A, product B, a version of B), created in the caller's transaction."""
    tenant, _ = _two_tenants(connection)
    stamp = uuid.uuid4().hex[:8]
    products = [
        connection.scalar(
            text(
                "INSERT INTO products (id, tenant_id, product_identifier, name, created_at, updated_at) "
                "VALUES (gen_random_uuid(), :t, :code, :code, now(), now()) RETURNING id"
            ),
            {"t": tenant, "code": f"DB1-{stamp}-{suffix}"},
        )
        for suffix in ("A", "B")
    ]
    version_b = connection.scalar(
        text(
            "INSERT INTO product_versions (id, tenant_id, product_id, version_identifier, created_at, updated_at) "
            "VALUES (gen_random_uuid(), :t, :p, 'Rev B1', now(), now()) RETURNING id"
        ),
        {"t": tenant, "p": products[1]},
    )
    return tenant, products[0], products[1], version_b


def _row_of(connection, table: str, tenant) -> uuid.UUID:
    """A row of ``table`` moved to ``tenant`` with no product (checks off for the move), in the open transaction."""
    row = connection.scalar(text(f"SELECT id FROM {table} LIMIT 1"))
    if row is None:
        pytest.skip(f"the test database has no {table} row")
    connection.execute(text("SET LOCAL session_replication_role = replica"))
    connection.execute(
        text(f"UPDATE {table} SET tenant_id = :t, product_id = NULL, product_version_id = NULL WHERE id = :id"),
        {"t": tenant, "id": row},
    )
    connection.execute(text("SET LOCAL session_replication_role = origin"))
    return row


@pytest.mark.parametrize("table", ["complaints", "risks", "requirements"])
def test_a_records_version_must_be_a_version_of_its_product(table):
    with engine.connect() as connection:
        connection.begin()
        try:
            tenant, product_a, _product_b, version_b = _versions_of_two_products(connection)
            row = _row_of(connection, table, tenant)
            with pytest.raises(DBAPIError) as other_product, connection.begin_nested():
                connection.execute(
                    text(f"UPDATE {table} SET product_id = :p, product_version_id = :v WHERE id = :id"),
                    {"p": product_a, "v": version_b, "id": row},
                )
            assert f"fk_{table}_version_of_product" in str(other_product.value)
            with pytest.raises(DBAPIError) as no_product, connection.begin_nested():
                connection.execute(
                    text(f"UPDATE {table} SET product_id = NULL, product_version_id = :v WHERE id = :id"),
                    {"v": version_b, "id": row},
                )
            assert f"ck_{table}_version_needs_product" in str(no_product.value)
        finally:
            connection.rollback()


def test_every_table_with_a_product_and_a_version_has_the_version_rule():
    from infrastructure.database.migrations.tenant_references import PRODUCT_VERSION_TABLES

    with engine.connect() as connection:
        tables = set(
            connection.execute(
                text(
                    "SELECT table_name FROM information_schema.columns WHERE table_schema = 'public' "
                    "AND column_name = 'product_version_id' AND table_name IN (SELECT table_name FROM "
                    "information_schema.columns WHERE table_schema = 'public' AND column_name = 'product_id')"
                )
            ).scalars()
        )
        names = set(connection.execute(text("SELECT conname FROM pg_constraint")).scalars())
    # case_contexts is outside PV-1 F1's list (DB-1 open question to the owner).
    assert tables - {"case_contexts"} == set(PRODUCT_VERSION_TABLES)
    missing = [
        t for t in PRODUCT_VERSION_TABLES if {f"fk_{t}_version_of_product", f"ck_{t}_version_needs_product"} - names
    ]
    assert not missing, missing


def test_the_pre_check_counts_rows_that_break_the_rules():
    """tr22's count, on a row written with the reference checks switched off (as old data may be)."""
    from infrastructure.database.migrations.tenant_references import refusal, violation_counts

    with engine.connect() as connection:
        connection.begin()
        try:
            assert refusal(violation_counts(connection)) is None
            tenant, product_a, _product_b, version_b = _versions_of_two_products(connection)
            complaint = _row_of(connection, "complaints", tenant)
            connection.execute(text("SET LOCAL session_replication_role = replica"))
            connection.execute(
                text("UPDATE complaints SET product_id = :p, product_version_id = :v WHERE id = :id"),
                {"p": product_a, "v": version_b, "id": complaint},
            )
            counts = dict(violation_counts(connection))
            assert counts["complaints: a version of another product or organization, or none"] == 1
            message = refusal(list(counts.items()))
            assert message and "complaints: a version of another product" in message
        finally:
            connection.rollback()


# --- DB-05: indexes for the organization filter and references (tr24) ------------------------------------------


def test_the_organization_and_reference_indexes_exist_and_are_valid():
    from infrastructure.database.migrations.tenant_indexes import INDEXES

    with engine.connect() as connection:
        valid = dict(
            connection.execute(
                text(
                    "SELECT indexrelid::regclass::text, indisvalid FROM pg_index WHERE indexrelid::regclass::text = ANY(:n)"
                ),
                {"n": [name for name, _, _ in INDEXES]},
            ).all()
        )
    assert {name: valid.get(name) for name, _, _ in INDEXES if not valid.get(name)} == {}


def test_every_organization_table_has_an_index_that_starts_with_the_organization():
    with engine.connect() as connection:
        missing = (
            connection.execute(
                text(
                    "SELECT c.relname FROM pg_class c WHERE c.relnamespace = 'public'::regnamespace AND c.relkind = 'r' "
                    "AND EXISTS (SELECT 1 FROM pg_attribute a WHERE a.attrelid = c.oid AND a.attname = 'tenant_id') "
                    "AND NOT EXISTS (SELECT 1 FROM pg_index i JOIN pg_attribute a ON a.attrelid = i.indrelid "
                    "AND a.attnum = i.indkey[0] WHERE i.indrelid = c.oid AND a.attname = 'tenant_id') ORDER BY 1"
                )
            )
            .scalars()
            .all()
        )
    assert not missing, "Add an index starting with tenant_id on: " + ", ".join(missing)
