"""Design-partner readiness: legal hold, audit retention by default, erasure log, support and client-error reports,
AI off for new organizations.

- ``tenants.legal_hold``: while set, the organization's data cannot be purged or retired by retention
  (backend/app/tenant_purge.py, backend/app/trial/retention.py).
- ``audit_events.retention_until`` is set by the database (seven years from the event) whenever the application
  leaves it empty, so retention status and archiving see every event. Existing empty values are filled in.
- ``erasure_log``: every personal-data erasure and organization purge, so a restore from backup can re-apply them
  (scripts/reapply_erasures.py).
- ``support_problem_reports``: "Report a problem" from the help menu, kept in the application with the request id.
- ``client_error_reports``: browser-side errors caught by the application's error boundaries.
- New organizations start with AI processing off; an administrator switches it on with a recorded reason
  (backend/app/ai_settings.py). Existing organizations keep their current setting.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "md23pilotreadiness"
down_revision = "md22dataplanecascade"
branch_labels = None
depends_on = None

_TENANT = "NULLIF(current_setting('app.tenant_id', true), '')::uuid"
_SYSTEM = "(SELECT public.mdarix_system_scope())"
_GRANT = (
    "DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'mdarix_runtime') THEN "
    "GRANT SELECT, INSERT, UPDATE, DELETE ON public.{table} TO mdarix_runtime; END IF; END $$;"
)

RETENTION_TRIGGER = """
CREATE OR REPLACE FUNCTION public.mdarix_audit_retention_default() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NEW.retention_until IS NULL THEN
    NEW.retention_until := COALESCE(NEW.created_at, now()) + interval '7 years';
  END IF;
  RETURN NEW;
END;
$$;
"""


def _tenant_policy(table: str, tenant_column: str = "tenant_id", nullable: bool = False) -> None:
    """Rows are visible to their organization and to system scope (platform administration)."""
    match = f"{tenant_column} = {_TENANT}"
    if nullable:
        match = f"({tenant_column} IS NULL OR {match})"
    op.execute(f"ALTER TABLE public.{table} ENABLE ROW LEVEL SECURITY")
    op.execute(f"ALTER TABLE public.{table} FORCE ROW LEVEL SECURITY")
    op.execute(
        f"CREATE POLICY mdarix_tenant_isolation ON public.{table} "
        f"USING ({match} OR {_SYSTEM}) WITH CHECK ({match} OR {_SYSTEM})"
    )
    op.execute(_GRANT.format(table=table))


def upgrade():
    # 1. Legal hold.
    op.add_column("tenants", sa.Column("legal_hold", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("tenants", sa.Column("legal_hold_reason", sa.Text()))
    op.add_column("tenants", sa.Column("legal_hold_set_at", sa.DateTime(timezone=True)))
    op.add_column("tenants", sa.Column("legal_hold_set_by", sa.String(255)))

    # 2. Audit retention by default. The immutability trigger refuses updates, so it is paused for the backfill;
    #    retention_until is not part of the hash chain (md18), so the chain stays valid.
    op.execute(RETENTION_TRIGGER)
    op.execute(
        "CREATE TRIGGER audit_events_retention BEFORE INSERT ON public.audit_events "
        "FOR EACH ROW EXECUTE FUNCTION public.mdarix_audit_retention_default()"
    )
    op.execute("ALTER TABLE public.audit_events DISABLE TRIGGER audit_events_immutable")
    op.execute(
        "UPDATE public.audit_events SET retention_until = created_at + interval '7 years' WHERE retention_until IS NULL"
    )
    op.execute("ALTER TABLE public.audit_events ENABLE TRIGGER audit_events_immutable")

    # 3. Erasure log.
    op.create_table(
        "erasure_log",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("kind", sa.String(40), nullable=False),  # PERSON_ERASED | TENANT_PURGED
        sa.Column("subject_ref", sa.String(255), nullable=False),  # the user id or tenant id affected
        sa.Column("performed_by", sa.String(255), nullable=False),
        sa.Column("reason", sa.Text()),
        sa.Column("details", postgresql.JSONB()),
        sa.Column("performed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("reapplied_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_erasure_log_tenant_performed", "erasure_log", ["tenant_id", "performed_at"])
    _tenant_policy("erasure_log")

    # 4. Problem reports from the help menu.
    op.create_table(
        "support_problem_reports",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True)),
        sa.Column("reporter_ref", sa.String(255), nullable=False),
        sa.Column("summary", sa.String(200), nullable=False),
        sa.Column("details", sa.Text(), nullable=False),
        sa.Column("path", sa.String(512)),
        sa.Column("request_id", sa.String(64)),
        sa.Column("user_agent", sa.String(512)),
        sa.Column("status", sa.String(20), nullable=False, server_default="OPEN"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("closed_at", sa.DateTime(timezone=True)),
        sa.Column("closed_by", sa.String(255)),
        sa.Column("resolution", sa.Text()),
        sa.CheckConstraint("status IN ('OPEN', 'CLOSED')", name="ck_support_problem_reports_status"),
    )
    op.create_index("ix_support_problem_reports_tenant_created", "support_problem_reports", ["tenant_id", "created_at"])
    op.create_index("ix_support_problem_reports_status", "support_problem_reports", ["status"])
    _tenant_policy("support_problem_reports")

    # 5. Browser-side errors. tenant_id is empty for errors on the public site or before sign-in.
    op.create_table(
        "client_error_reports",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True)),
        sa.Column("user_id", postgresql.UUID(as_uuid=True)),
        sa.Column("path", sa.String(512), nullable=False),
        sa.Column("message", sa.String(1000), nullable=False),
        sa.Column("stack", sa.Text()),
        sa.Column("component", sa.String(200)),
        sa.Column("user_agent", sa.String(512)),
        sa.Column("request_id", sa.String(64)),
        sa.Column("release", sa.String(80)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_client_error_reports_created", "client_error_reports", ["created_at"])
    _tenant_policy("client_error_reports", nullable=True)

    # 6. AI off for new organizations.
    op.alter_column("tenants", "ai_processing_allowed", server_default=sa.false())


def downgrade():
    op.alter_column("tenants", "ai_processing_allowed", server_default=sa.true())
    for table in ("client_error_reports", "support_problem_reports", "erasure_log"):
        op.execute(f"DROP POLICY IF EXISTS mdarix_tenant_isolation ON public.{table}")
    op.drop_index("ix_client_error_reports_created", table_name="client_error_reports")
    op.drop_table("client_error_reports")
    op.drop_index("ix_support_problem_reports_status", table_name="support_problem_reports")
    op.drop_index("ix_support_problem_reports_tenant_created", table_name="support_problem_reports")
    op.drop_table("support_problem_reports")
    op.drop_index("ix_erasure_log_tenant_performed", table_name="erasure_log")
    op.drop_table("erasure_log")
    op.execute("DROP TRIGGER IF EXISTS audit_events_retention ON public.audit_events")
    op.execute("DROP FUNCTION IF EXISTS public.mdarix_audit_retention_default()")
    for column in ("legal_hold_set_by", "legal_hold_set_at", "legal_hold_reason", "legal_hold"):
        op.drop_column("tenants", column)
