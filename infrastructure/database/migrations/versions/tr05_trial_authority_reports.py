"""Authority report worksheets, the obligation lifecycle and the submission record (release 0.10.58).

The fourth migration of the trial line's expert-feedback releases (TRIAL_FEEDBACK_PLAN.md section 7: T-G2c, T-G2b),
chained from ``tr04intaketriage``. Its revision id starts with ``tr`` so it never collides with an ``md`` revision of
``mvp-1.0`` (``tr03pmssources`` stays reserved for proactive PMS); after the forward merge, ``mvp-1.0`` adds a merge
revision joining its head and this one.

Expand-only: four new tables, each with its indexes and the tenant row-level security policy. No existing table or
row changes. The downgrade removes only what this migration added.

- ``report_obligations``: one report owed to one authority for one complaint, or a response to a request for
  information, with its deadline, G2b's state and the worksheet entries made by a person;
- ``report_snapshots``: the worksheet frozen for a second person's approval, in versions;
- ``report_submissions``: each attempt as the person recorded it after submitting outside MDARIX;
- ``report_evidence``: the evidence of an attempt (submitted content, receipts, acknowledgements, acceptance,
  rejection), each with an optional small file.

The models are in backend/app/db/models/authority_reports.py. Legacy dedicated organization databases get the same
from scripts/add_workflow_tables_to_legacy_planes.py, which runs ``create_report_tables``.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from infrastructure.database.migrations.helpers import quoted
from infrastructure.database.migrations.helpers import tenant_policy as _tenant_policy

revision = "tr05authorityreports"
down_revision = "tr04intaketriage"
branch_labels = None
depends_on = None

TABLES = ("report_evidence", "report_submissions", "report_snapshots", "report_obligations")
KINDS = ("INITIAL", "RESPONSE")
STATES = (
    "DRAFT",
    "CORRECTION_REQUIRED",
    "APPROVED",
    "SUBMITTED_PENDING",
    "ACCEPTED",
    "SUBMITTED_NO_ACK",
    "FOLLOW_UP_DUE",
    "COMPLETE",
)
SNAPSHOT_STATES = ("PENDING", "APPROVED", "SUPERSEDED")
RESULTS = ("PENDING", "ACCEPTED", "REJECTED", "NO_ACK_EXPECTED")
OUTCOMES = ("CONTENT", "RECEIPT", "ACCEPTED", "REJECTED")


def _uuid(name: str, nullable: bool = True) -> sa.Column:
    return sa.Column(name, postgresql.UUID(as_uuid=True), nullable=nullable)


def _tz(name: str, nullable: bool = True) -> sa.Column:
    return sa.Column(name, sa.DateTime(timezone=True), nullable=nullable)


def _common(table: str) -> list:
    return [
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        _uuid("tenant_id", False),
        sa.PrimaryKeyConstraint("id", name=op.f(f"pk_{table}")),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], name=op.f(f"fk_{table}_tenant_id_tenants")),
    ]


def create_report_tables(system_scope: bool = True) -> None:
    """The four tables and their isolation (also used for legacy organization databases)."""
    op.create_table(
        "report_obligations",
        *_common("report_obligations"),
        _uuid("complaint_id", False),
        sa.Column("market", sa.String(10), nullable=False),
        sa.Column("kind", sa.String(20), server_default="INITIAL", nullable=False),
        _uuid("parent_id"),
        _uuid("assessment_id"),
        sa.Column("form_code", sa.String(40), nullable=False),
        sa.Column("form_version", sa.String(40), nullable=False),
        sa.Column("report_type", sa.String(40)),
        sa.Column("due_on", sa.Date()),
        sa.Column("due_provisional", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("state", sa.String(30), server_default="DRAFT", nullable=False),
        sa.Column("entries", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("request_text", sa.Text()),
        sa.Column("request_received_on", sa.Date()),
        sa.Column("note", sa.Text()),
        sa.Column("follow_up_due_on", sa.Date()),
        sa.Column("source_system", sa.String(40)),
        sa.Column("created_by", sa.String(255), nullable=False),
        _tz("created_at", False),
        _tz("updated_at", False),
        sa.ForeignKeyConstraint(
            ["tenant_id", "complaint_id"],
            ["complaints.tenant_id", "complaints.id"],
            name="fk_report_obligations_complaint",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["parent_id"], ["report_obligations.id"], name=op.f("fk_report_obligations_parent_id_report_obligations")
        ),
        sa.ForeignKeyConstraint(
            ["assessment_id"],
            ["complaint_market_assessments.id"],
            name=op.f("fk_report_obligations_assessment_id_complaint_market_assessments"),
        ),
        sa.CheckConstraint(f"kind IN ({quoted(KINDS)})", name=op.f("ck_report_obligations_kind_known")),
        sa.CheckConstraint(f"state IN ({quoted(STATES)})", name=op.f("ck_report_obligations_state_known")),
        sa.CheckConstraint(
            "kind = 'INITIAL' OR parent_id IS NOT NULL", name=op.f("ck_report_obligations_response_has_parent")
        ),
    )
    op.create_index("ix_report_obligations_tenant_complaint", "report_obligations", ["tenant_id", "complaint_id"])
    op.create_index(
        "uq_report_obligations_initial",
        "report_obligations",
        ["tenant_id", "complaint_id", "market"],
        unique=True,
        postgresql_where=sa.text("kind = 'INITIAL'"),
    )
    op.create_table(
        "report_snapshots",
        *_common("report_snapshots"),
        _uuid("obligation_id", False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("form_version", sa.String(40), nullable=False),
        sa.Column("fields", postgresql.JSONB(), nullable=False),
        sa.Column("content_fingerprint", sa.String(64), nullable=False),
        sa.Column("preparers", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("state", sa.String(20), server_default="PENDING", nullable=False),
        sa.Column("requested_by", sa.String(255), nullable=False),
        _tz("requested_at", False),
        sa.Column("approved_by", sa.String(255)),
        _tz("approved_at"),
        _uuid("signed_record_id"),
        sa.Column("source_system", sa.String(40)),
        sa.ForeignKeyConstraint(
            ["obligation_id"], ["report_obligations.id"], name="fk_report_snapshots_obligation", ondelete="CASCADE"
        ),
        sa.UniqueConstraint("obligation_id", "version", name="uq_report_snapshots_version"),
        sa.CheckConstraint(f"state IN ({quoted(SNAPSHOT_STATES)})", name=op.f("ck_report_snapshots_state_known")),
        sa.CheckConstraint(
            "state <> 'APPROVED' OR (approved_by IS NOT NULL AND approved_at IS NOT NULL AND signed_record_id IS NOT "
            "NULL)",
            name=op.f("ck_report_snapshots_approved_signed"),
        ),
    )
    op.create_index("ix_report_snapshots_tenant_obligation", "report_snapshots", ["tenant_id", "obligation_id"])
    op.create_table(
        "report_submissions",
        *_common("report_submissions"),
        _uuid("obligation_id", False),
        _uuid("snapshot_id"),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("route", sa.String(40), nullable=False),
        _tz("submitted_at", False),
        sa.Column("content_note", sa.Text()),
        sa.Column("differences", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("authority_reference", sa.String(120)),
        sa.Column("result", sa.String(20), server_default="PENDING", nullable=False),
        _tz("result_at"),
        sa.Column("late", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("recorded_by", sa.String(255), nullable=False),
        _tz("recorded_at", False),
        sa.Column("source_system", sa.String(40)),
        sa.ForeignKeyConstraint(
            ["obligation_id"], ["report_obligations.id"], name="fk_report_submissions_obligation", ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["snapshot_id"], ["report_snapshots.id"], name=op.f("fk_report_submissions_snapshot_id_report_snapshots")
        ),
        sa.UniqueConstraint("obligation_id", "attempt", name="uq_report_submissions_attempt"),
        sa.CheckConstraint(f"result IN ({quoted(RESULTS)})", name=op.f("ck_report_submissions_result_known")),
    )
    op.create_index("ix_report_submissions_tenant_obligation", "report_submissions", ["tenant_id", "obligation_id"])
    op.create_table(
        "report_evidence",
        *_common("report_evidence"),
        _uuid("submission_id", False),
        sa.Column("kind", sa.String(30), nullable=False),
        sa.Column("outcome", sa.String(20), nullable=False),
        sa.Column("note", sa.Text()),
        sa.Column("file_name", sa.String(200)),
        sa.Column("content_type", sa.String(120)),
        sa.Column("size", sa.Integer()),
        sa.Column("sha256", sa.String(64)),
        sa.Column("content", sa.LargeBinary()),
        _tz("received_at", False),
        sa.Column("recorded_by", sa.String(255), nullable=False),
        _tz("recorded_at", False),
        sa.Column("source_system", sa.String(40)),
        sa.ForeignKeyConstraint(
            ["submission_id"], ["report_submissions.id"], name="fk_report_evidence_submission", ondelete="CASCADE"
        ),
        sa.CheckConstraint(f"outcome IN ({quoted(OUTCOMES)})", name=op.f("ck_report_evidence_outcome_known")),
        sa.CheckConstraint("note IS NOT NULL OR content IS NOT NULL", name=op.f("ck_report_evidence_note_or_file")),
    )
    op.create_index("ix_report_evidence_tenant_submission", "report_evidence", ["tenant_id", "submission_id"])
    for table in TABLES:
        _tenant_policy(table, system_scope)


def upgrade():
    create_report_tables()


def downgrade():
    for table in TABLES:
        op.drop_table(table)
