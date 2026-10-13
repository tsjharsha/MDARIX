"""A free trial's request to end early (backend/app/trial/early_exit.py).

The trial owner asks to end the trial before its 30 days, with an optional reason and whether the data should be
deleted; a Platform Administrator approves (the trial ends, and its data is purged when asked) or declines with a note
to the owner. A platform table like ``demo_requests``: the organization is ``trial_tenant_id``, deliberately not
``tenant_id``, so the request (and the reason the organization gave) is kept as the record of the decision when the
organization's data is purged (backend/app/tenant_purge.py discovers tables by their ``tenant_id`` column). It holds no
name or email address. Control plane only.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "md45trialexit"
down_revision = "md44digestdemo"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "trial_exit_requests",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("trial_tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("organization", sa.String(160), nullable=False),
        sa.Column("requested_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("reason_code", sa.String(40), nullable=True),
        sa.Column("reason", sa.String(1000), nullable=True),
        sa.Column("delete_data", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("status", sa.String(20), server_default="PENDING", nullable=False),
        sa.Column("data_deleted", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("decided_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decision_note", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "status IN ('PENDING', 'APPROVED', 'DECLINED', 'WITHDRAWN')", name="ck_trial_exit_requests_status"
        ),
    )
    op.create_index("ix_trial_exit_requests_trial", "trial_exit_requests", ["trial_tenant_id", "created_at"])
    op.create_index("ix_trial_exit_requests_status", "trial_exit_requests", ["status", "created_at"])
    op.execute(
        "DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'mdarix_runtime') THEN "
        "GRANT SELECT, INSERT, UPDATE, DELETE ON public.trial_exit_requests TO mdarix_runtime; END IF; END $$;"
    )


def downgrade():
    op.drop_index("ix_trial_exit_requests_status", table_name="trial_exit_requests")
    op.drop_index("ix_trial_exit_requests_trial", table_name="trial_exit_requests")
    op.drop_table("trial_exit_requests")
