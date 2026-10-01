"""Record the Platform Admin review of a public free-trial request.

A request stays PENDING_REVIEW until a Platform Admin approves it (which creates the trial workspace) or
declines it. These nullable columns record who decided, when, why, and which workspace an approval created.
Existing rows are untouched.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "md04trialrequestreview"
down_revision = "md03retireviewerauth"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("onboarding_requests", sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("onboarding_requests", sa.Column("reviewed_by", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("onboarding_requests", sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("onboarding_requests", sa.Column("decision_reason", sa.Text(), nullable=True))
    op.create_index("ix_onboarding_requests_status", "onboarding_requests", ["status", "created_at"])


def downgrade():
    op.drop_index("ix_onboarding_requests_status", table_name="onboarding_requests")
    op.drop_column("onboarding_requests", "decision_reason")
    op.drop_column("onboarding_requests", "reviewed_at")
    op.drop_column("onboarding_requests", "reviewed_by")
    op.drop_column("onboarding_requests", "tenant_id")
