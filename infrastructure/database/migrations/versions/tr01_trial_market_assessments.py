"""Per-market seriousness and causation assessments, complaint classifications and signer training (release 0.10.52).

The first migration of the trial maintenance line's expert-feedback releases (TRIAL_FEEDBACK_PLAN.md section 7). Its
revision id starts with ``tr`` so it never collides with the ``md49``-``md52`` revisions of ``mvp-1.0``; after the
forward merge, ``mvp-1.0`` adds a merge revision joining its head and this one (``md49`` is never re-pointed).

Expand-only: three new tables, their indexes and their tenant row-level security policies. No existing table changes:
``complaint_reportability`` keeps its one decision per complaint, and its rows stay readable as single decisions made
before per-market assessment. The downgrade drops only these three tables.

- ``complaint_market_assessments``: one market's assessment of one complaint, in versions (draft, then signed).
- ``complaint_classifications``: use environment and user type for trend analysis (screens in a later release).
- ``signer_training_records``: training (in a trial, a practice acknowledgement) on a document version.

The models are in backend/app/db/models/market_assessment.py. Legacy dedicated organization databases get the same
tables from scripts/add_workflow_tables_to_legacy_planes.py, which runs ``create_market_assessment_tables``.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from infrastructure.database.migrations.helpers import quoted
from infrastructure.database.migrations.helpers import tenant_policy as _tenant_policy

revision = "tr01marketassessments"
down_revision = "md48legalacceptance"
branch_labels = None
depends_on = None

TABLES = ("complaint_market_assessments", "complaint_classifications", "signer_training_records")
MARKETS = ("US", "EU_NI", "GB", "IN")
SUGGESTIONS = ("REPORTABLE", "PENDING_INFORMATION", "NOT_REPORTABLE")
CONCLUSIONS = ("REPORTABLE", "NOT_REPORTABLE")
USE_ENVIRONMENTS = (
    "HOSPITAL_WARD",
    "INTENSIVE_CARE_UNIT",
    "OPERATING_THEATRE",
    "HOME",
    "AMBULANCE",
    "CLINIC",
    "OTHER",
    "UNKNOWN",
)
USER_TYPES = ("HEALTHCARE_PROFESSIONAL", "LAY_USER", "PATIENT", "SERVICE_ENGINEER", "OTHER", "UNKNOWN")
STATES = ("PROPOSED", "CONFIRMED")


def _id() -> sa.Column:
    return sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False)


def _tenant(table: str):
    return (
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], name=op.f(f"fk_{table}_tenant_id_tenants")),
    )


def _now(name: str) -> sa.Column:
    return sa.Column(name, sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False)


def _complaint(table: str):
    return (
        sa.Column("complaint_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["tenant_id", "complaint_id"],
            ["complaints.tenant_id", "complaints.id"],
            name=f"fk_{table}_complaint",
            ondelete="CASCADE",
        ),
    )


def _check(table: str, name: str, sql: str) -> sa.CheckConstraint:
    return sa.CheckConstraint(sql, name=op.f(f"ck_{table}_{name}"))


def create_market_assessment_tables(system_scope: bool = True) -> None:
    """The three tables and their isolation (also used for legacy organization databases)."""
    table = "complaint_market_assessments"
    tenant_column, tenant_fk = _tenant(table)
    complaint_column, complaint_fk = _complaint(table)
    op.create_table(
        table,
        _id(),
        tenant_column,
        complaint_column,
        sa.Column("market", sa.String(10), nullable=False),
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("question_set", sa.String(40), nullable=False),
        sa.Column("answers", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("harm_level", sa.String(20)),
        sa.Column("harm_code", sa.String(60)),
        sa.Column("harm_level_reason", sa.Text()),
        sa.Column("scale_version", sa.String(40), nullable=False),
        sa.Column("scale_disagreement_reason", sa.Text()),
        sa.Column("suggested_conclusion", sa.String(30), nullable=False),
        sa.Column("conclusion", sa.String(30)),
        sa.Column("override_reason", sa.Text()),
        sa.Column("report_type", sa.String(40)),
        sa.Column("window_name", sa.String(160)),
        sa.Column("due_on", sa.Date()),
        sa.Column("filing_reference", sa.String(120)),
        sa.Column("filed_on", sa.Date()),
        sa.Column("signed_record_id", postgresql.UUID(as_uuid=True)),
        sa.Column("content_fingerprint", sa.String(64)),
        sa.Column("signed_by", sa.String(255)),
        sa.Column("signed_at", sa.DateTime(timezone=True)),
        sa.Column("superseded_by", postgresql.UUID(as_uuid=True)),
        sa.Column("source_system", sa.String(40)),
        sa.Column("created_by", sa.String(255), nullable=False),
        _now("created_at"),
        _now("updated_at"),
        sa.PrimaryKeyConstraint("id", name=op.f(f"pk_{table}")),
        tenant_fk,
        complaint_fk,
        sa.UniqueConstraint("tenant_id", "complaint_id", "market", "version", name=f"uq_{table}_version"),
        _check(table, "market_known", f"market IN ({quoted(MARKETS)})"),
        _check(table, "version_positive", "version >= 1"),
        _check(table, "suggestion_known", f"suggested_conclusion IN ({quoted(SUGGESTIONS)})"),
        _check(table, "conclusion_known", f"conclusion IS NULL OR conclusion IN ({quoted(CONCLUSIONS)})"),
        _check(
            table,
            "conclusion_signed",
            "conclusion IS NULL OR (signed_record_id IS NOT NULL AND signed_by IS NOT NULL AND signed_at IS NOT NULL)",
        ),
        _check(table, "filed_when_reportable", "filed_on IS NULL OR conclusion = 'REPORTABLE'"),
    )
    op.create_index(f"ix_{table}_tenant_complaint", table, ["tenant_id", "complaint_id"])
    _tenant_policy(table, system_scope)

    table = "complaint_classifications"
    tenant_column, tenant_fk = _tenant(table)
    complaint_column, complaint_fk = _complaint(table)
    op.create_table(
        table,
        _id(),
        tenant_column,
        complaint_column,
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("use_environment", sa.String(30), server_default="UNKNOWN", nullable=False),
        sa.Column("use_environment_text", sa.String(200)),
        sa.Column("user_type", sa.String(30), server_default="UNKNOWN", nullable=False),
        sa.Column("user_type_text", sa.String(200)),
        sa.Column("source_values", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("state", sa.String(20), server_default="PROPOSED", nullable=False),
        sa.Column("coding_criteria_version", sa.String(40), nullable=False),
        sa.Column("confirmed_by", sa.String(255)),
        sa.Column("confirmed_at", sa.DateTime(timezone=True)),
        sa.Column("signed_record_id", postgresql.UUID(as_uuid=True)),
        sa.Column("change_reason", sa.Text()),
        sa.Column("superseded_by", postgresql.UUID(as_uuid=True)),
        sa.Column("source_system", sa.String(40)),
        sa.Column("created_by", sa.String(255), nullable=False),
        _now("created_at"),
        sa.PrimaryKeyConstraint("id", name=op.f(f"pk_{table}")),
        tenant_fk,
        complaint_fk,
        sa.UniqueConstraint("tenant_id", "complaint_id", "version", name=f"uq_{table}_version"),
        _check(table, "version_positive", "version >= 1"),
        _check(table, "use_environment_known", f"use_environment IN ({quoted(USE_ENVIRONMENTS)})"),
        _check(table, "user_type_known", f"user_type IN ({quoted(USER_TYPES)})"),
        _check(table, "state_known", f"state IN ({quoted(STATES)})"),
        _check(table, "other_environment_text", "use_environment <> 'OTHER' OR use_environment_text IS NOT NULL"),
        _check(table, "other_user_type_text", "user_type <> 'OTHER' OR user_type_text IS NOT NULL"),
        _check(
            table,
            "confirmed_by_someone",
            "state <> 'CONFIRMED' OR (confirmed_by IS NOT NULL AND confirmed_at IS NOT NULL)",
        ),
    )
    _tenant_policy(table, system_scope)

    table = "signer_training_records"
    tenant_column, tenant_fk = _tenant(table)
    op.create_table(
        table,
        _id(),
        tenant_column,
        sa.Column("user_id", sa.String(255), nullable=False),
        sa.Column("document_code", sa.String(60), nullable=False),
        sa.Column("document_version", sa.String(60), nullable=False),
        sa.Column("trained_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("method", sa.String(200), nullable=False),
        sa.Column("trainer", sa.String(255)),
        sa.Column("evidence", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("recorded_by", sa.String(255), nullable=False),
        sa.Column("source_system", sa.String(40)),
        _now("created_at"),
        sa.PrimaryKeyConstraint("id", name=op.f(f"pk_{table}")),
        tenant_fk,
        sa.UniqueConstraint("tenant_id", "user_id", "document_code", "document_version", name=f"uq_{table}_version"),
    )
    op.create_index(f"ix_{table}_document", table, ["tenant_id", "document_code", "document_version"])
    _tenant_policy(table, system_scope)


def upgrade():
    create_market_assessment_tables()


def downgrade():
    for table in reversed(TABLES):
        op.drop_table(table)
