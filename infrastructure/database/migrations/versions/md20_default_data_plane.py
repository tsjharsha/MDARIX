"""Every organization has a data-plane registry row, so routing can fail closed.

Requests for business data resolve the organization's plane from ``tenant_data_planes``; until now an organization
without a row silently used the control database (and tests relied on that). From here an organization always has a
row: existing ones without one are registered on the shared plane (archived ones as RETIRED), and a deferred
trigger registers each new organization on the shared plane at commit, unless the transaction that created it
registered a plane itself (trial approval, customer provisioning, a dedicated plane). The application then refuses
business-data requests for an organization without an ACTIVE plane (backend/app/db/data_plane.py).
"""

from alembic import op

revision = "md20defaultdataplane"
down_revision = "md19tenantexports"
branch_labels = None
depends_on = None

SHARED = "MDARIX_TRIAL_SHARED_CONTROL_PLANE"


def upgrade():
    op.execute(f"""
    INSERT INTO public.tenant_data_planes
      (id, tenant_id, database_ref, connection_secret_ref, region, residency_region, schema_version, status,
       created_at, updated_at)
    SELECT gen_random_uuid(), t.id, 'shared-control:' || t.tenant_key, '{SHARED}',
           COALESCE(t.primary_region, 'UNSPECIFIED'), COALESCE(t.residency_region, 'UNSPECIFIED'), 'control-plane',
           CASE WHEN upper(t.status) = 'ARCHIVED' THEN 'RETIRED' ELSE 'ACTIVE' END, now(), now()
      FROM public.tenants t
     WHERE NOT EXISTS (SELECT 1 FROM public.tenant_data_planes p WHERE p.tenant_id = t.id)
    ON CONFLICT DO NOTHING
    """)
    op.execute(f"""
    CREATE OR REPLACE FUNCTION public.mdarix_default_data_plane() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN
      INSERT INTO public.tenant_data_planes
        (id, tenant_id, database_ref, connection_secret_ref, region, residency_region, schema_version, status,
         created_at, updated_at)
      SELECT gen_random_uuid(), NEW.id, 'shared-control:' || NEW.tenant_key, '{SHARED}',
             COALESCE(NEW.primary_region, 'UNSPECIFIED'), COALESCE(NEW.residency_region, 'UNSPECIFIED'),
             'control-plane', 'ACTIVE', now(), now()
       WHERE NOT EXISTS (SELECT 1 FROM public.tenant_data_planes p WHERE p.tenant_id = NEW.id)
      ON CONFLICT DO NOTHING;
      RETURN NULL;
    END $$;
    """)
    op.execute(
        "CREATE CONSTRAINT TRIGGER tenants_default_data_plane AFTER INSERT ON public.tenants "
        "DEFERRABLE INITIALLY DEFERRED FOR EACH ROW EXECUTE FUNCTION public.mdarix_default_data_plane()"
    )


def downgrade():
    op.execute("DROP TRIGGER IF EXISTS tenants_default_data_plane ON public.tenants")
    op.execute("DROP FUNCTION IF EXISTS public.mdarix_default_data_plane()")
