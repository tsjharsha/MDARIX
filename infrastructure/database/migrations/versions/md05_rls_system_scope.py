"""Tenant row-level security with an explicit system scope, ready for the non-superuser runtime role.

Every tenant-owned table gets the same policy: a row is visible or writable only when its tenant_id equals the
transaction's app.tenant_id, or when the transaction runs in system scope (app.rls_bypass = 'on'). The application
sets both per transaction (backend/app/db/tenant_scope.py): a signed-in request is bound to its tenant; system scope
is reserved for platform-administrator actions and pre-authentication steps (sign-in, activation, password reset).
With neither set, nothing is visible: it fails closed.

Five tenant tables created after ab44 had no policy and now get one. Platform-owned tables are excluded on purpose.
The runtime role also receives access to the md_master reference schema. While the application still connects as
the owner (a superuser), behaviour is unchanged; the policies take effect once it connects as mdarix_runtime.
"""

from alembic import op

revision = "md05rlssystemscope"
down_revision = "md04trialrequestreview"
branch_labels = None
depends_on = None

# Platform-owned: read before a tenant is known, or only by platform administrators.
EXCLUDED = (
    "auth_users",
    "auth_sessions",
    "onboarding_requests",
    "provisioning_jobs",
    "provisioning_job_steps",
    "platform_incidents",
    "tenant_data_planes",
)
_EXCLUDED_SQL = ", ".join(f"'{name}'" for name in EXCLUDED)
_TENANT = "NULLIF(current_setting(''app.tenant_id'', true), '''')::uuid"
_SYSTEM = "current_setting(''app.rls_bypass'', true) = ''on''"


def upgrade() -> None:
    op.execute(f"""
    DO $$
    DECLARE r record;
    BEGIN
      FOR r IN
        SELECT DISTINCT c.table_name
        FROM information_schema.columns c
        JOIN information_schema.tables t USING (table_schema, table_name)
        WHERE c.table_schema = 'public' AND c.column_name = 'tenant_id' AND t.table_type = 'BASE TABLE'
          AND c.table_name NOT IN ({_EXCLUDED_SQL})
      LOOP
        EXECUTE format('ALTER TABLE public.%I ENABLE ROW LEVEL SECURITY', r.table_name);
        EXECUTE format('ALTER TABLE public.%I FORCE ROW LEVEL SECURITY', r.table_name);
        EXECUTE format('DROP POLICY IF EXISTS mdarix_tenant_isolation ON public.%I', r.table_name);
        EXECUTE format(
          'CREATE POLICY mdarix_tenant_isolation ON public.%I '
          'USING (tenant_id = {_TENANT} OR {_SYSTEM}) '
          'WITH CHECK (tenant_id = {_TENANT} OR {_SYSTEM})',
          r.table_name
        );
      END LOOP;
    END $$;
    """)
    op.execute("""
    DO $$
    BEGIN
      IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'mdarix_runtime') THEN
        GRANT USAGE ON SCHEMA public TO mdarix_runtime;
        GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO mdarix_runtime;
        GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA public TO mdarix_runtime;
        IF EXISTS (SELECT 1 FROM pg_namespace WHERE nspname = 'md_master') THEN
          GRANT USAGE ON SCHEMA md_master TO mdarix_runtime;
          GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA md_master TO mdarix_runtime;
          GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA md_master TO mdarix_runtime;
          ALTER DEFAULT PRIVILEGES IN SCHEMA md_master GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO mdarix_runtime;
          ALTER DEFAULT PRIVILEGES IN SCHEMA md_master GRANT USAGE, SELECT, UPDATE ON SEQUENCES TO mdarix_runtime;
        END IF;
      END IF;
    END $$;
    """)


def downgrade() -> None:
    # Restore the ab44 policy (tenant match only) and remove RLS from the five tables this migration added.
    op.execute(f"""
    DO $$
    DECLARE r record;
    BEGIN
      FOR r IN
        SELECT DISTINCT c.table_name
        FROM information_schema.columns c
        JOIN information_schema.tables t USING (table_schema, table_name)
        WHERE c.table_schema = 'public' AND c.column_name = 'tenant_id' AND t.table_type = 'BASE TABLE'
          AND c.table_name NOT IN ({_EXCLUDED_SQL})
      LOOP
        EXECUTE format('DROP POLICY IF EXISTS mdarix_tenant_isolation ON public.%I', r.table_name);
        IF r.table_name IN ('regulatory_documents', 'regulatory_document_versions', 'report_jobs',
                            'mfa_challenges', 'password_history') THEN
          EXECUTE format('ALTER TABLE public.%I NO FORCE ROW LEVEL SECURITY', r.table_name);
          EXECUTE format('ALTER TABLE public.%I DISABLE ROW LEVEL SECURITY', r.table_name);
        ELSE
          EXECUTE format(
            'CREATE POLICY mdarix_tenant_isolation ON public.%I '
            'USING (tenant_id = {_TENANT}) WITH CHECK (tenant_id = {_TENANT})',
            r.table_name
          );
        END IF;
      END LOOP;
    END $$;
    """)
