"""Trial feedback: a free-trial user's questionnaire answers and their consent for showing them on the website.

A tenant table, so it gets the same row-level security policy as every other tenant table: a person sees only their
organization's rows; Platform Administrators read across tenants through the system scope.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "md13trialfeedback"
down_revision = "md12demorequests"
branch_labels = None
depends_on = None

_TENANT = "NULLIF(current_setting('app.tenant_id', true), '')::uuid"
_SYSTEM = "current_setting('app.rls_bypass', true) = 'on'"


def upgrade():
    op.create_table(
        "trial_feedback",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization_name", sa.String(160), nullable=False),
        sa.Column("role_area", sa.String(40)),
        sa.Column("job_title", sa.String(120)),
        sa.Column("rating_overall", sa.Integer(), nullable=False),
        sa.Column("rating_ease", sa.Integer()),
        sa.Column("rating_usefulness", sa.Integer()),
        sa.Column("rating_ai_trust", sa.Integer()),
        sa.Column("rating_speed", sa.Integer()),
        sa.Column("rating_import", sa.Integer()),
        sa.Column("recommend_score", sa.Integer()),
        sa.Column("features_used", postgresql.JSONB(), server_default="[]", nullable=False),
        sa.Column("liked", sa.Text()),
        sa.Column("improve", sa.Text()),
        sa.Column("missing", sa.Text()),
        sa.Column("adoption", sa.String(40)),
        sa.Column("quote", sa.Text()),
        sa.Column("publish_consent", sa.String(20), server_default="PRIVATE", nullable=False),
        sa.Column("consent_text", sa.Text(), nullable=False),
        sa.Column("consent_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("contact_ok", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("publication_status", sa.String(20), server_default="NOT_REQUESTED", nullable=False),
        sa.Column("reviewed_by", postgresql.UUID(as_uuid=True)),
        sa.Column("reviewed_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("publish_consent IN ('NAMED', 'ANONYMOUS', 'PRIVATE')", name="ck_trial_feedback_consent"),
        sa.CheckConstraint(
            "publication_status IN ('NOT_REQUESTED', 'PENDING', 'PUBLISHED', 'HIDDEN')",
            name="ck_trial_feedback_publication",
        ),
        sa.CheckConstraint("rating_overall BETWEEN 1 AND 5", name="ck_trial_feedback_overall"),
        sa.CheckConstraint(
            "recommend_score IS NULL OR recommend_score BETWEEN 0 AND 10", name="ck_trial_feedback_recommend"
        ),
    )
    op.create_index("ix_trial_feedback_tenant_user", "trial_feedback", ["tenant_id", "user_id"])
    op.create_index("ix_trial_feedback_publication", "trial_feedback", ["publication_status"])
    op.execute("ALTER TABLE public.trial_feedback ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE public.trial_feedback FORCE ROW LEVEL SECURITY")
    op.execute(
        "CREATE POLICY mdarix_tenant_isolation ON public.trial_feedback "
        f"USING (tenant_id = {_TENANT} OR {_SYSTEM}) WITH CHECK (tenant_id = {_TENANT} OR {_SYSTEM})"
    )
    op.execute(
        "DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'mdarix_runtime') THEN "
        "GRANT SELECT, INSERT, UPDATE, DELETE ON public.trial_feedback TO mdarix_runtime; END IF; END $$;"
    )


def downgrade():
    op.drop_index("ix_trial_feedback_publication", table_name="trial_feedback")
    op.drop_index("ix_trial_feedback_tenant_user", table_name="trial_feedback")
    op.drop_table("trial_feedback")
