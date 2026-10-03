"""System scope needs a secret; accounts get row-level security.

Before: every tenant policy let a transaction through when ``app.rls_bypass = 'on'``, a setting the runtime role can
set itself, so one SQL injection would read every tenant's rows. Now system scope requires the secret token from
``MDARIX_RLS_SYSTEM_TOKEN``: the API sets ``app.rls_bypass`` to the token, and ``mdarix_system_scope()`` (SECURITY
DEFINER, owner-only table) compares its SHA-256 with the stored hash. The runtime role can call the function but can
neither read the hash nor learn the token, so it cannot enter system scope by SQL alone. The policy wraps the call in
a sub-select, so Postgres evaluates it once per query, not once per row.

``auth_users`` (password hashes, MFA secrets) now has the same tenant policy: an account row is visible only to its
own tenant, or in system scope (sign-in, platform administration).

The token's hash is taken from MDARIX_RLS_SYSTEM_TOKEN in the environment running this migration; without it the
local development token is stored, and a staging or production API refuses to start until
``scripts/set_rls_system_token.py`` stores the real one.
"""

import hashlib
import os

from alembic import op

revision = "md15rlssystemtoken"
down_revision = "md14ratelimits"
branch_labels = None
depends_on = None

LOCAL_TOKEN = "mdarix-local-development-rls-system-scope"
_TENANT = "NULLIF(current_setting('app.tenant_id', true), '')::uuid"
_OLD_SYSTEM = "current_setting('app.rls_bypass', true) = 'on'"
_NEW_SYSTEM = "(SELECT public.mdarix_system_scope())"


def _token_hash() -> str:
    token = os.getenv("MDARIX_RLS_SYSTEM_TOKEN", "").strip() or LOCAL_TOKEN
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _rewrite_policies(system_clause: str) -> None:
    op.execute(f"""
    DO $$
    DECLARE r record;
    BEGIN
      FOR r IN SELECT tablename FROM pg_policies
               WHERE schemaname = 'public' AND policyname = 'mdarix_tenant_isolation'
      LOOP
        EXECUTE format('DROP POLICY mdarix_tenant_isolation ON public.%I', r.tablename);
        EXECUTE format(
          'CREATE POLICY mdarix_tenant_isolation ON public.%I '
          'USING (tenant_id = {_TENANT.replace("'", "''")} OR {system_clause.replace("'", "''")}) '
          'WITH CHECK (tenant_id = {_TENANT.replace("'", "''")} OR {system_clause.replace("'", "''")})',
          r.tablename
        );
      END LOOP;
    END $$;
    """)


def upgrade():
    op.execute("""
    CREATE TABLE IF NOT EXISTS public.mdarix_rls_secret (
        id integer PRIMARY KEY CHECK (id = 1),
        token_hash text NOT NULL,
        updated_at timestamptz NOT NULL DEFAULT now()
    )
    """)
    op.execute("REVOKE ALL ON public.mdarix_rls_secret FROM PUBLIC")
    op.execute(
        "DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'mdarix_runtime') THEN "
        "REVOKE ALL ON public.mdarix_rls_secret FROM mdarix_runtime; END IF; "
        "IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'mdarix_readonly') THEN "
        "REVOKE ALL ON public.mdarix_rls_secret FROM mdarix_readonly; END IF; END $$;"
    )
    op.execute(
        "INSERT INTO public.mdarix_rls_secret (id, token_hash) VALUES (1, '" + _token_hash() + "') "
        "ON CONFLICT (id) DO NOTHING"
    )
    op.execute("""
    CREATE OR REPLACE FUNCTION public.mdarix_system_scope() RETURNS boolean
    LANGUAGE sql STABLE SECURITY DEFINER
    SET search_path = pg_catalog, public
    AS $$
      SELECT coalesce(current_setting('app.rls_bypass', true), '') NOT IN ('', 'off', 'on')
         AND encode(sha256(convert_to(current_setting('app.rls_bypass', true), 'UTF8')), 'hex')
             = (SELECT token_hash FROM public.mdarix_rls_secret WHERE id = 1)
    $$
    """)
    op.execute("REVOKE ALL ON FUNCTION public.mdarix_system_scope() FROM PUBLIC")
    op.execute(
        "DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'mdarix_runtime') THEN "
        "GRANT EXECUTE ON FUNCTION public.mdarix_system_scope() TO mdarix_runtime; END IF; "
        "IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'mdarix_readonly') THEN "
        "GRANT EXECUTE ON FUNCTION public.mdarix_system_scope() TO mdarix_readonly; END IF; END $$;"
    )
    op.execute("ALTER TABLE public.auth_users ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE public.auth_users FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY mdarix_tenant_isolation ON public.auth_users "
        f"USING (tenant_id = {_TENANT} OR {_OLD_SYSTEM}) WITH CHECK (tenant_id = {_TENANT} OR {_OLD_SYSTEM})"
    )
    _rewrite_policies(_NEW_SYSTEM)


def downgrade():
    _rewrite_policies(_OLD_SYSTEM)
    op.execute("DROP POLICY IF EXISTS mdarix_tenant_isolation ON public.auth_users")
    op.execute("ALTER TABLE public.auth_users NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE public.auth_users DISABLE ROW LEVEL SECURITY")
    op.execute("DROP FUNCTION IF EXISTS public.mdarix_system_scope()")
    op.execute("DROP TABLE IF EXISTS public.mdarix_rls_secret")
