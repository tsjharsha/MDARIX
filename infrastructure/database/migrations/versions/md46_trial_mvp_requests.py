"""A free trial's request for an MVP conversation (backend/app/trial/mvp_request.py).

From Next steps in the trial workspace, anyone in the trial says what they expect from an MVP, the products, sites and
systems they have in mind, how to reach them and, only when the organization has removed the sample data and imported
its own, whether to move the trial data into the MVP. The MDARIX team sees it in Platform Admin (Demo and trial
requests) and by email, and marks it contacted or closed. A tenant table, so it gets the same row-level security policy
as ``trial_feedback``: a person sees only their organization's request; Platform Administrators read every one through
the system scope. It holds the requester's name and email, so it is deleted with the trial's data
(backend/app/tenant_purge.py finds it by its ``tenant_id``). One open request (NEW or CONTACTED) per organization, held
by a partial unique index. Control plane only.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from infrastructure.database.migrations.helpers import tenant_policy

revision = "md46trialmvp"
down_revision = "md45trialexit"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "trial_mvp_requests",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("requested_by", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("display_name", sa.String(120), nullable=False),
        sa.Column("email", sa.String(254), nullable=False),
        sa.Column("organization", sa.String(160), nullable=False),
        sa.Column("expectations", sa.String(2000), nullable=False),
        sa.Column("scope", sa.String(2000), nullable=True),
        sa.Column("phone", sa.String(30), nullable=True),
        sa.Column("contact_preference", sa.String(200), nullable=True),
        sa.Column("move_trial_data", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("status", sa.String(20), server_default="NEW", nullable=False),
        sa.Column("context", postgresql.JSONB(), nullable=True),
        sa.Column("handled_by", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("handled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("note", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], name=op.f("fk_trial_mvp_requests_tenant_id_tenants")),
        sa.CheckConstraint("status IN ('NEW', 'CONTACTED', 'CLOSED')", name="ck_trial_mvp_requests_status"),
    )
    op.create_index("ix_trial_mvp_requests_tenant", "trial_mvp_requests", ["tenant_id", "created_at"])
    op.create_index("ix_trial_mvp_requests_status", "trial_mvp_requests", ["status", "created_at"])
    op.create_index(
        "ux_trial_mvp_requests_open",
        "trial_mvp_requests",
        ["tenant_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('NEW', 'CONTACTED')"),
    )
    tenant_policy("trial_mvp_requests")


def downgrade():
    op.drop_index("ux_trial_mvp_requests_open", table_name="trial_mvp_requests")
    op.drop_index("ix_trial_mvp_requests_status", table_name="trial_mvp_requests")
    op.drop_index("ix_trial_mvp_requests_tenant", table_name="trial_mvp_requests")
    op.drop_table("trial_mvp_requests")
