"""Background services record a heartbeat in the database, so the platform console can show whether they run.

One row per service, replaced every cycle. The table holds no tenant data (no tenant_id), so the tenant row-level
security policy of md05 does not apply to it.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "md07workerheartbeats"
down_revision = "md06multimodelembeddings"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "worker_heartbeats",
        sa.Column("service", sa.String(80), primary_key=True),
        sa.Column("instance_id", sa.String(120), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("metrics", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
    )
    op.execute(
        "DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'mdarix_runtime') THEN "
        "GRANT SELECT, INSERT, UPDATE, DELETE ON worker_heartbeats TO mdarix_runtime; END IF; END $$;"
    )


def downgrade() -> None:
    op.drop_table("worker_heartbeats")
