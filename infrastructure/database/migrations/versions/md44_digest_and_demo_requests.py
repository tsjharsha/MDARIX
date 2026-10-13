"""The weekly readiness email and the one-to-one demo booked from a trial.

- ``auth_users.email_preferences``: a person's email choices (JSON, empty by default); ``{"weekly_readiness": false}``
  stops the weekly readiness email (backend/app/readiness_home/digest.py). Control plane only.
- ``demo_requests``: where a request came from (``source``: WEBSITE or TRIAL) and, for a request made inside a free
  trial, the trial organization (``trial_tenant_id``; deliberately not ``tenant_id``, which marks tenant-owned business
  data for isolation and purges), its name, the times that suit the person and the trial's progress through the story
  (``context``). The website form keeps working unchanged. Legacy dedicated organization databases get the same columns from
scripts/add_workflow_tables_to_legacy_planes.py, which runs ``add_digest_and_demo_columns``.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "md44digestdemo"
down_revision = "md43lotquantity"
branch_labels = None
depends_on = None


def add_digest_and_demo_columns(system_scope: bool = True) -> None:
    """The columns (also used for legacy organization databases, which keep copies of these tables; ``system_scope``
    is not needed: no new table, no new isolation)."""
    op.add_column(
        "auth_users",
        sa.Column("email_preferences", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
    )
    op.add_column("demo_requests", sa.Column("source", sa.String(20), server_default="WEBSITE", nullable=False))
    op.add_column("demo_requests", sa.Column("trial_tenant_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("demo_requests", sa.Column("organization", sa.String(160), nullable=True))
    op.add_column("demo_requests", sa.Column("preferred_time", sa.String(200), nullable=True))
    op.add_column("demo_requests", sa.Column("context", postgresql.JSONB(), nullable=True))
    op.create_check_constraint("ck_demo_requests_source_known", "demo_requests", "source IN ('WEBSITE', 'TRIAL')")
    op.create_index("ix_demo_requests_trial_tenant", "demo_requests", ["trial_tenant_id", "created_at"])


def upgrade():
    add_digest_and_demo_columns()


def downgrade():
    op.drop_index("ix_demo_requests_trial_tenant", table_name="demo_requests")
    op.drop_constraint("ck_demo_requests_source_known", "demo_requests", type_="check")
    for column in ("context", "preferred_time", "organization", "trial_tenant_id", "source"):
        op.drop_column("demo_requests", column)
    op.drop_column("auth_users", "email_preferences")
