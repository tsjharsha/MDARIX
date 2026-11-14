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
