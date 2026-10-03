"""Per-organization AI controls and shared provider rest periods.

``tenants.ai_processing_allowed``: whether this organization's content may be sent to an AI model at all (customer
administrators switch it; off means rule-based answers only). ``tenants.ai_monthly_token_budget``: the most tokens
the organization may use per calendar month (NULL: the server default ``MDARIX_GENAI_TENANT_MONTHLY_TOKENS``).

``ai_usage_monthly``: tokens, requests and estimated cost per organization and month, checked against the budget
before every model call. Tenant data, so it has the same row-level security as every other tenant table.

``genai_provider_rest``: when a provider rate-limits or fails, every API, worker and scheduler process skips it
until ``rest_until`` (previously each process kept its own list). Platform-level, no tenant data.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "md17aicontrols"
down_revision = "md16schedulerruns"
branch_labels = None
depends_on = None

_TENANT = "NULLIF(current_setting('app.tenant_id', true), '')::uuid"
_SYSTEM = "(SELECT public.mdarix_system_scope())"


def _grant(table: str) -> None:
    op.execute(
        "DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'mdarix_runtime') THEN "
        f"GRANT SELECT, INSERT, UPDATE, DELETE ON public.{table} TO mdarix_runtime; END IF; END $$;"
    )


def upgrade():
    op.add_column("tenants", sa.Column("ai_processing_allowed", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.add_column("tenants", sa.Column("ai_monthly_token_budget", sa.BigInteger(), nullable=True))
    op.create_check_constraint(
        "ck_tenants_ai_budget_not_negative",
        "tenants",
        "ai_monthly_token_budget IS NULL OR ai_monthly_token_budget >= 0",
    )

    op.create_table(
        "ai_usage_monthly",
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id"), primary_key=True),
        sa.Column("month", sa.Date(), primary_key=True),
        sa.Column("requests", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("refused", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("input_tokens", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("output_tokens", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("estimated_cost", sa.Numeric(12, 4), nullable=False, server_default="0"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.execute("ALTER TABLE public.ai_usage_monthly ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE public.ai_usage_monthly FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY mdarix_tenant_isolation ON public.ai_usage_monthly "
        f"USING (tenant_id = {_TENANT} OR {_SYSTEM}) WITH CHECK (tenant_id = {_TENANT} OR {_SYSTEM})"
    )
    _grant("ai_usage_monthly")

    op.create_table(
        "genai_provider_rest",
        sa.Column("provider", sa.String(40), primary_key=True),
        sa.Column("rest_until", sa.DateTime(timezone=True), nullable=False),
        sa.Column("reason", sa.String(40), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    _grant("genai_provider_rest")


def downgrade():
    op.drop_table("genai_provider_rest")
    op.execute("DROP POLICY IF EXISTS mdarix_tenant_isolation ON public.ai_usage_monthly")
    op.drop_table("ai_usage_monthly")
    op.drop_constraint("ck_tenants_ai_budget_not_negative", "tenants", type_="check")
    op.drop_column("tenants", "ai_monthly_token_budget")
    op.drop_column("tenants", "ai_processing_allowed")
