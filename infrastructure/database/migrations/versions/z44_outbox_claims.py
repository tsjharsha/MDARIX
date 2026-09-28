"""Add durable worker claims for stale-job recovery and observability."""
from alembic import op
import sqlalchemy as sa

revision = "z44outboxclaims"
down_revision = "z43regulatorydocuments"
branch_labels = None
depends_on = None

def upgrade():
    op.add_column("event_outbox", sa.Column("claimed_by", sa.String(120), nullable=True))
    op.add_column("event_outbox", sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_event_outbox_claimed_at", "event_outbox", ["claimed_at"])

def downgrade():
    op.drop_index("ix_event_outbox_claimed_at", table_name="event_outbox")
    op.drop_column("event_outbox", "claimed_at")
    op.drop_column("event_outbox", "claimed_by")
