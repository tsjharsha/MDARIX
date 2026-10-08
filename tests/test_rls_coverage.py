"""Every organization-owned table is protected by Postgres row-level security, not only by application code.

Pilots share one database, so a missing policy would let one organization's request read another's rows. These tests
read the catalogue of the migrated database: a new table with a ``tenant_id`` column fails here until it gets the
FORCEd ``mdarix_tenant_isolation`` policy (migrations md05/md15/md34), or a reviewed entry in ``EXEMPT``.
"""

from sqlalchemy import text

from backend.app.db.session import engine

POLICY = "mdarix_tenant_isolation"

# Tables with a tenant_id that the database does not filter, each with the reason. Adding one is a security review.
EXEMPT = {
    "auth_sessions": "resolved from the session cookie before the organization is known (auth/durable.py, "
    "request_context.py); listings filter by organization in code",
    "tenant_data_planes": "routing: read to choose the organization's database before a request is bound "
    "(backend/app/db/data_plane.py)",
    "onboarding_requests": "website demo and trial requests, made before any organization exists (tenant_id is "
    "empty until approval); platform administration and the trial flow only",
    "platform_incidents": "platform operations records; no organization-facing route",
    "provisioning_jobs": "platform onboarding jobs; platform administration only",
    "provisioning_job_steps": "steps of platform onboarding jobs; platform administration only",
}
# The organization and its customer, which have no tenant_id column of their own (md34).
ORGANIZATION_TABLES = ("tenants", "customers", "customer_contacts", "customer_domains", "customer_onboarding_drafts")
MASTER_POLICIES = {"mdarix_master_read", "mdarix_master_insert", "mdarix_master_update", "mdarix_master_delete"}


def _tables(sql: str) -> dict[str, tuple]:
    with engine.connect() as connection:
        return {row[0]: tuple(row[1:]) for row in connection.execute(text(sql))}


def _public_tables() -> dict[str, tuple]:
    """name -> (row security enabled, forced, has the isolation policy, has a tenant_id column)."""
    return _tables(
        f"""
        SELECT c.relname, c.relrowsecurity, c.relforcerowsecurity,
               EXISTS (SELECT 1 FROM pg_policies p WHERE p.schemaname = 'public' AND p.tablename = c.relname
                       AND p.policyname = '{POLICY}'),
               EXISTS (SELECT 1 FROM information_schema.columns k WHERE k.table_schema = 'public'
                       AND k.table_name = c.relname AND k.column_name = 'tenant_id')
        FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'public' AND c.relkind IN ('r', 'p')
        """
    )


def test_every_table_with_a_tenant_id_has_forced_row_level_security():
    tables = _public_tables()
    owned = {name: flags for name, flags in tables.items() if flags[3]}
    assert len(owned) > 100, "the catalogue was not read from a migrated database"
    unprotected = sorted(
        name for name, (enabled, forced, policy, _) in owned.items() if not (enabled and forced and policy)
    )
    assert set(unprotected) <= set(EXEMPT), (
        "Add the forced mdarix_tenant_isolation policy (or a reviewed EXEMPT entry) for: "
        + ", ".join(sorted(set(unprotected) - set(EXEMPT)))
    )


def test_the_exemptions_are_still_needed():
    """An exempt table that gained a policy, or was dropped, comes off the list so the list stays a true record."""
    tables = _public_tables()
    stale = sorted(
        name for name in EXEMPT if name not in tables or (tables[name][0] and tables[name][1] and tables[name][2])
    )
    assert not stale, "Remove from EXEMPT: " + ", ".join(stale)


def test_the_organization_and_customer_tables_are_protected():
    tables = _public_tables()
    missing = [name for name in ORGANIZATION_TABLES if tables.get(name, (False,) * 4)[:3] != (True, True, True)]
    assert not missing, "No forced isolation policy on: " + ", ".join(missing)


def test_master_data_is_writable_only_in_system_scope():
    """md_master is the same for every organization: everyone reads it, only system scope writes it (md34)."""
    tables = _tables(
        """
        SELECT c.relname, c.relrowsecurity,
               ARRAY(SELECT p.policyname::text FROM pg_policies p
                     WHERE p.schemaname = 'md_master' AND p.tablename = c.relname)
        FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'md_master' AND c.relkind IN ('r', 'p')
        """
    )
    assert tables, "no md_master tables found"
    unprotected = sorted(name for name, (enabled, policies) in tables.items() if not enabled)
    incomplete = sorted(name for name, (_, policies) in tables.items() if not MASTER_POLICIES <= set(policies))
    assert not unprotected and not incomplete, f"md_master without RLS: {unprotected}; without policies: {incomplete}"
