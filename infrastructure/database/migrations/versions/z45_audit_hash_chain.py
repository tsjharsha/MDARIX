"""Add tenant-scoped tamper-evident audit hash fields."""
from alembic import op
import sqlalchemy as sa

revision = "z45audithashchain"
down_revision = "z44outboxclaims"
branch_labels = None
depends_on = None

def upgrade():
    op.add_column("audit_events", sa.Column("previous_hash", sa.String(64), nullable=True))
    op.add_column("audit_events", sa.Column("event_hash", sa.String(64), nullable=True))
    op.create_index("ix_audit_events_tenant_hash", "audit_events", ["tenant_id", "event_hash"])

def downgrade():
    op.drop_index("ix_audit_events_tenant_hash", table_name="audit_events")
    op.drop_column("audit_events", "event_hash")
    op.drop_column("audit_events", "previous_hash")
