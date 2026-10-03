"""Demo requests from the website: name, work email and phone of a visitor who wants a demo.

A platform table like onboarding_requests: it has no tenant, so it carries no row-level security policy, and only
Platform Administrators read it (through the API).
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "md12demorequests"
down_revision = "md11masterseedv2"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "demo_requests",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("display_name", sa.String(120), nullable=False),
        sa.Column("email", sa.String(254), nullable=False),
        sa.Column("phone", sa.String(30), nullable=False),
        sa.Column("status", sa.String(40), server_default="NEW", nullable=False),
        sa.Column("source_hash", sa.String(64)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("handled_by", postgresql.UUID(as_uuid=True)),
        sa.Column("handled_at", sa.DateTime(timezone=True)),
        sa.Column("note", sa.Text()),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_demo_requests_created", "demo_requests", ["created_at"])
    op.create_index("ix_demo_requests_email", "demo_requests", ["email"])
    op.create_index("ix_demo_requests_source", "demo_requests", ["source_hash", "created_at"])
    op.execute(
        "DO $$ BEGIN IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'mdarix_runtime') THEN "
        "GRANT SELECT, INSERT, UPDATE, DELETE ON public.demo_requests TO mdarix_runtime; END IF; END $$;"
    )


def downgrade():
    op.drop_index("ix_demo_requests_source", table_name="demo_requests")
    op.drop_index("ix_demo_requests_email", table_name="demo_requests")
    op.drop_index("ix_demo_requests_created", table_name="demo_requests")
    op.drop_table("demo_requests")
