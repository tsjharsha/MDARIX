"""Reporting and CAPA: the reportability watch and CAPA effectiveness checks.

- ``reportability_settings``: one row per organization: its reporting windows (from its own procedure) and how far
  back the watch looks, versioned.
- ``complaint_reportability``: a person's reportability decision on a complaint (REPORTED with the report's reference
  and filing day, or NOT_REPORTABLE), with the rationale and the binding window at the time. One current decision per
  complaint.
- ``capa_effectiveness_checks``: the effectiveness check of a CAPA in rounds: the plan (criteria, check day,
  measurement start) and the signed result (EFFECTIVE or NOT_EFFECTIVE) with the evidence seen.

All three are tenant-isolated (FORCE row-level security) like md40's tables. The models are in
backend/app/db/models/reportability.py and backend/app/db/models/capa_effectiveness.py. Legacy dedicated organization
databases get the same tables from scripts/add_workflow_tables_to_legacy_planes.py, which runs this module's
``create_reporting_and_capa_tables``.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from infrastructure.database.migrations.helpers import tenant_policy as _tenant_policy

revision = "md41reportingcapa"
down_revision = "md40complaintreview"
branch_labels = None
depends_on = None

TABLES = ("reportability_settings", "complaint_reportability", "capa_effectiveness_checks")


def _id() -> sa.Column:
    return sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False)


def _tenant(table: str):
    return (
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], name=op.f(f"fk_{table}_tenant_id_tenants")),
    )


def _now(name: str) -> sa.Column:
    return sa.Column(name, sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False)


def create_reporting_and_capa_tables(system_scope: bool = True) -> None:
    """The three tables and their isolation (also used for legacy organization databases)."""
    tenant_column, tenant_fk = _tenant("reportability_settings")
    op.create_table(
        "reportability_settings",
        _id(),
        tenant_column,
        sa.Column("windows", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("lookback_days", sa.Integer(), server_default=sa.text("365"), nullable=False),
        sa.Column("version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("updated_by", sa.String(255)),
        _now("updated_at"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_reportability_settings")),
        tenant_fk,
        sa.UniqueConstraint("tenant_id", name="uq_reportability_settings_tenant"),
        sa.CheckConstraint(
            "lookback_days BETWEEN 30 AND 3650", name=op.f("ck_reportability_settings_lookback_days_range")
        ),
    )
    _tenant_policy("reportability_settings", system_scope)

    tenant_column, tenant_fk = _tenant("complaint_reportability")
    op.create_table(
        "complaint_reportability",
        _id(),
        tenant_column,
        sa.Column("complaint_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("decision", sa.String(20), nullable=False),
        sa.Column("rationale", sa.Text(), nullable=False),
        sa.Column("report_reference", sa.String(120)),
        sa.Column("reported_on", sa.Date()),
        sa.Column("window_name", sa.String(100)),
        sa.Column("due_on", sa.Date()),
        sa.Column("decided_by", sa.String(255), nullable=False),
        _now("decided_at"),
        _now("created_at"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_complaint_reportability")),
        tenant_fk,
        sa.UniqueConstraint("tenant_id", "complaint_id", name="uq_complaint_reportability_complaint"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "complaint_id"],
            ["complaints.tenant_id", "complaints.id"],
            name="fk_complaint_reportability_complaint",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "decision IN ('REPORTED', 'NOT_REPORTABLE')", name=op.f("ck_complaint_reportability_decision_known")
        ),
        sa.CheckConstraint(
            "decision <> 'REPORTED' OR (report_reference IS NOT NULL AND reported_on IS NOT NULL)",
            name=op.f("ck_complaint_reportability_report_recorded"),
        ),
    )
    _tenant_policy("complaint_reportability", system_scope)

    tenant_column, tenant_fk = _tenant("capa_effectiveness_checks")
    op.create_table(
        "capa_effectiveness_checks",
        _id(),
        tenant_column,
        sa.Column("capa_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("round", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("status", sa.String(20), server_default="PLANNED", nullable=False),
        sa.Column("criteria", sa.Text(), nullable=False),
        sa.Column("planned_on", sa.Date(), nullable=False),
        sa.Column("measured_from", sa.Date(), nullable=False),
        sa.Column("plan_version", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column("planned_by", sa.String(255), nullable=False),
        _now("planned_at"),
        sa.Column("result_summary", sa.Text()),
        sa.Column("evidence", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("signature_id", postgresql.UUID(as_uuid=True)),
        sa.Column("content_fingerprint", sa.String(64)),
        sa.Column("signed_by", sa.String(255)),
        sa.Column("signer_role", sa.String(60)),
        sa.Column("signed_at", sa.DateTime(timezone=True)),
        _now("created_at"),
        _now("updated_at"),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_capa_effectiveness_checks")),
        tenant_fk,
        sa.UniqueConstraint("tenant_id", "capa_id", "round", name="uq_capa_effectiveness_checks_round"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "capa_id"],
            ["capas.tenant_id", "capas.id"],
            name="fk_capa_effectiveness_checks_capa",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "status IN ('PLANNED', 'EFFECTIVE', 'NOT_EFFECTIVE')",
            name=op.f("ck_capa_effectiveness_checks_status_known"),
        ),
        sa.CheckConstraint("round >= 1", name=op.f("ck_capa_effectiveness_checks_round_positive")),
        sa.CheckConstraint(
            "measured_from <= planned_on", name=op.f("ck_capa_effectiveness_checks_measured_before_check")
        ),
        sa.CheckConstraint(
            "status = 'PLANNED' OR (signed_by IS NOT NULL AND signed_at IS NOT NULL AND result_summary IS NOT NULL)",
            name=op.f("ck_capa_effectiveness_checks_result_signed"),
        ),
    )
    _tenant_policy("capa_effectiveness_checks", system_scope)


def upgrade():
    create_reporting_and_capa_tables()


def downgrade():
    for table in reversed(TABLES):
        op.drop_table(table)
