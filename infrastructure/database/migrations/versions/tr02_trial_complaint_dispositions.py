"""Complaint dispositions and the case decision's root-cause attribution (release 0.10.53).

The second migration of the trial maintenance line's expert-feedback releases (TRIAL_FEEDBACK_PLAN.md section 7),
chained from tr01. Its revision id starts with ``tr`` so it never collides with an ``md`` revision of ``mvp-1.0``;
after the forward merge, ``mvp-1.0`` adds a merge revision joining its head and this one.

Expand-only: one new table with its index and tenant row-level security policy, and two nullable columns on
``decisions`` (``root_cause_attribution``, ``attribution_reason``). No existing row changes: the signing route requires
the attribution for new signatures only. The downgrade removes only what this migration added.

The model is in backend/app/db/models/complaint_disposition.py. Legacy dedicated organization databases get the same
from scripts/add_workflow_tables_to_legacy_planes.py, which runs ``create_disposition_tables``.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from infrastructure.database.migrations.helpers import quoted
from infrastructure.database.migrations.helpers import tenant_policy as _tenant_policy

revision = "tr02complaintdispositions"
down_revision = "tr01marketassessments"
branch_labels = None
depends_on = None

TABLE = "complaint_dispositions"
BRANCHES = ("ESCALATED_BY_TRIGGER", "KNOWN_ISSUE", "SERVICE_LEVEL", "ESCALATED_BY_CHOICE")
ATTRIBUTIONS = ("DEVICE_RELATED", "USE_RELATED", "ENVIRONMENT_RELATED", "UNDETERMINED")


def _check(name: str, sql: str) -> sa.CheckConstraint:
    return sa.CheckConstraint(sql, name=op.f(f"ck_{TABLE}_{name}"))


def create_disposition_tables(system_scope: bool = True) -> None:
    """The table, its isolation and the decision columns (also used for legacy organization databases)."""
    op.create_table(
        TABLE,
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("complaint_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("branch", sa.String(30), nullable=False),
        sa.Column("triggers", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("answers", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("service_record", postgresql.JSONB()),
        sa.Column("attribution", sa.String(30)),
        sa.Column("attribution_reason", sa.Text()),
        sa.Column("investigation_id", postgresql.UUID(as_uuid=True)),
        sa.Column("routine_path", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("hands_on_seconds", sa.Integer()),
        sa.Column("change_reason", sa.Text()),
        sa.Column("signed_record_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("content_fingerprint", sa.String(64), nullable=False),
        sa.Column("signed_by", sa.String(255), nullable=False),
        sa.Column("signed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("superseded_by", postgresql.UUID(as_uuid=True)),
        sa.Column("source_system", sa.String(40)),
        sa.Column("created_by", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f(f"pk_{TABLE}")),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], name=op.f(f"fk_{TABLE}_tenant_id_tenants")),
        sa.ForeignKeyConstraint(
            ["tenant_id", "complaint_id"],
            ["complaints.tenant_id", "complaints.id"],
            name=f"fk_{TABLE}_complaint",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint("tenant_id", "complaint_id", "version", name=f"uq_{TABLE}_version"),
        _check("version_positive", "version >= 1"),
        _check("branch_known", f"branch IN ({quoted(BRANCHES)})"),
        _check("attribution_known", f"attribution IS NULL OR attribution IN ({quoted(ATTRIBUTIONS)})"),
        _check(
            "service_level_complete",
            "branch <> 'SERVICE_LEVEL' OR (attribution IS NOT NULL AND service_record IS NOT NULL)",
        ),
        _check("undetermined_reason", "attribution <> 'UNDETERMINED' OR attribution_reason IS NOT NULL"),
        _check(
            "case_linked",
            "branch NOT IN ('KNOWN_ISSUE', 'ESCALATED_BY_TRIGGER', 'ESCALATED_BY_CHOICE') OR investigation_id IS NOT NULL",
        ),
    )
    op.create_index(f"ix_{TABLE}_tenant_complaint", TABLE, ["tenant_id", "complaint_id"])
    _tenant_policy(TABLE, system_scope)
    op.add_column("decisions", sa.Column("root_cause_attribution", sa.String(30)))
    op.add_column("decisions", sa.Column("attribution_reason", sa.Text()))


def upgrade():
    create_disposition_tables()


def downgrade():
    op.drop_column("decisions", "attribution_reason")
    op.drop_column("decisions", "root_cause_attribution")
    op.drop_table(TABLE)
