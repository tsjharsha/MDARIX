"""Complaint review: the second look at possible hidden complaints, and each organization's settings for it and for
the complaint backlog board.

- ``complaint_settings``: one row per organization (backlog target days, the second look's word list), versioned.
- ``complaint_second_looks``: a person's decision on a flagged record (CONFIRMED: it is a complaint; DISMISSED: it is
  not), with the reason and what the second look showed. One current decision per record.

Both are tenant-isolated (FORCE row-level security) like md28's tables. The models are in
backend/app/db/models/complaint_review.py. Legacy dedicated organization databases get the same tables from
scripts/add_workflow_tables_to_legacy_planes.py, which runs this module's ``create_complaint_review_tables``.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from infrastructure.database.migrations.helpers import tenant_policy as _tenant_policy

revision = "md40complaintreview"
down_revision = "md39trialrequestprofile"
branch_labels = None
depends_on = None

TABLES = ("complaint_settings", "complaint_second_looks")


def _id() -> sa.Column:
    return sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False)


def _tenant(table: str):
    return (
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], name=op.f(f"fk_{table}_tenant_id_tenants")),
    )


def _now(name: str) -> sa.Column:
    return sa.Column(name, sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False)


def create_complaint_review_tables(system_scope: bool = True) -> None:
    """The two tables and their isolation (also used for legacy organization databases)."""
    tenant_column, tenant_fk = _tenant("complaint_settings")
    op.create_table(
        "complaint_settings",
        _id(),
        tenant_column,
        sa.Column("backlog_target_days", sa.Integer(), server_default=sa.text("30"), nullable=False),
        sa.Column("second_look_words", postgresql.JSONB()),
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("updated_by", sa.String(255)),
        _now("updated_at"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_complaint_settings")),
        tenant_fk,
        sa.UniqueConstraint("tenant_id", name="uq_complaint_settings_tenant"),
        sa.CheckConstraint(
            "backlog_target_days BETWEEN 1 AND 365", name=op.f("ck_complaint_settings_backlog_target_days_range")
        ),
    )
    _tenant_policy("complaint_settings", system_scope)

    tenant_column, tenant_fk = _tenant("complaint_second_looks")
    op.create_table(
        "complaint_second_looks",
        _id(),
        tenant_column,
        sa.Column("complaint_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("decision", sa.String(20), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("flagged", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("decided_by", sa.String(255), nullable=False),
        _now("decided_at"),
        _now("created_at"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_complaint_second_looks")),
        tenant_fk,
        sa.UniqueConstraint("tenant_id", "complaint_id", name="uq_complaint_second_looks_complaint"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "complaint_id"],
            ["complaints.tenant_id", "complaints.id"],
            name="fk_complaint_second_looks_complaint",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "decision IN ('CONFIRMED', 'DISMISSED')", name=op.f("ck_complaint_second_looks_decision_known")
        ),
    )
    _tenant_policy("complaint_second_looks", system_scope)


def upgrade():
    create_complaint_review_tables()


def downgrade():
    for table in reversed(TABLES):
        op.drop_table(table)
