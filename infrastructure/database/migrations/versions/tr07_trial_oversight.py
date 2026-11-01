"""Reminders and escalation, the working calendar, absences and the event's closure (release 0.10.60).

The sixth migration of the trial line's expert-feedback releases (TRIAL_FEEDBACK_PLAN.md section 7: T-G25, T-G28,
T-G9), chained from ``tr06guidescomms``. Its revision id starts with ``tr`` so it never collides with an ``md``
revision of ``mvp-1.0`` (``tr03pmssources`` stays reserved for proactive PMS); after the forward merge, ``mvp-1.0``
adds a merge revision joining its head and this one.

Expand-only: four new tables, each with its indexes and the tenant row-level security policy. No existing table or
row changes. The downgrade removes only what this migration added.

- ``oversight_settings``: the working calendar and the simple escalation rule;
- ``user_absences``: a person's absence with the colleague who covers it;
- ``due_alerts``: each reminder and escalation of a dated item for one person, with its read state;
- ``event_closures``: a complaint's event owner, its signed "ready to close in the QMS" and the QMS filing reference
  of its event decision record.

The models are in backend/app/db/models/oversight.py. Legacy dedicated organization databases get the same from
scripts/add_workflow_tables_to_legacy_planes.py, which runs ``create_oversight_tables``.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from infrastructure.database.migrations.helpers import quoted
from infrastructure.database.migrations.helpers import tenant_policy as _tenant_policy

revision = "tr07oversight"
down_revision = "tr06guidescomms"
branch_labels = None
depends_on = None

TABLES = ("oversight_settings", "user_absences", "due_alerts", "event_closures")
ALERT_TIERS = ("REMINDER", "ESCALATION")
READY_STATES = ("READY", "READY_WITH_REASON")


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


def _check(table: str, name: str, condition: str) -> sa.CheckConstraint:
    return sa.CheckConstraint(condition, name=op.f(f"ck_{table}_{name}"))


def create_oversight_tables(system_scope: bool = True) -> None:
    """The four tables and their isolation (also used for legacy organization databases)."""
    table = "oversight_settings"
    op.create_table(
        table,
        *_common(table),
        sa.Column("time_zone", sa.String(60), server_default="UTC", nullable=False),
        sa.Column("work_days", postgresql.JSONB(), server_default=sa.text("'[0, 1, 2, 3, 4]'::jsonb"), nullable=False),
        sa.Column("holidays", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False),
        sa.Column("reminder_hours", sa.Integer(), server_default=sa.text("24"), nullable=False),
        sa.Column("escalation_role", sa.String(60), server_default="LEADER", nullable=False),
        _tz("swept_at"),
        sa.Column("updated_by", sa.String(255)),
        _tz("updated_at", False),
        sa.UniqueConstraint("tenant_id", name="uq_oversight_settings_tenant"),
        _check(table, "reminder_range", "reminder_hours BETWEEN 1 AND 168"),
    )
    table = "user_absences"
    op.create_table(
        table,
        *_common(table),
        sa.Column("user_id", sa.String(255), nullable=False),
        sa.Column("starts_on", sa.Date(), nullable=False),
        sa.Column("ends_on", sa.Date(), nullable=False),
        sa.Column("backup_id", sa.String(255), nullable=False),
        sa.Column("note", sa.Text()),
        sa.Column("source_system", sa.String(40)),
        sa.Column("created_by", sa.String(255), nullable=False),
        _tz("created_at", False),
        sa.Column("cancelled_by", sa.String(255)),
        _tz("cancelled_at"),
        _check(table, "dates_ordered", "starts_on <= ends_on"),
        _check(table, "backup_other", "backup_id <> user_id"),
    )
    op.create_index("ix_user_absences_tenant_user", table, ["tenant_id", "user_id"])
    table = "due_alerts"
    op.create_table(
        table,
        *_common(table),
        sa.Column("item_key", sa.String(200), nullable=False),
        sa.Column("tier", sa.String(20), nullable=False),
        sa.Column("recipient_id", sa.String(255), nullable=False),
        sa.Column("reason", sa.String(30), nullable=False),
        sa.Column("category", sa.String(30), nullable=False),
        sa.Column("title", sa.String(400), nullable=False),
        sa.Column("ref", sa.String(120)),
        _uuid("complaint_id"),
        sa.Column("owner_id", sa.String(255)),
        _tz("due_at", False),
        sa.Column("opens", postgresql.JSONB()),
        _tz("raised_at", False),
        _tz("read_at"),
        _tz("resolved_at"),
        sa.UniqueConstraint("tenant_id", "item_key", "tier", "recipient_id", name="uq_due_alerts_item"),
        _check(table, "tier_known", f"tier IN ({quoted(ALERT_TIERS)})"),
    )
    op.create_index("ix_due_alerts_tenant_recipient", table, ["tenant_id", "recipient_id"])
    table = "event_closures"
    op.create_table(
        table,
        *_common(table),
        _uuid("complaint_id", False),
        sa.Column("owner_id", sa.String(255)),
        sa.Column("owner_set_by", sa.String(255)),
        _tz("owner_set_at"),
        sa.Column("version", sa.Integer(), server_default=sa.text("0"), nullable=False),
        sa.Column("ready_state", sa.String(20)),
        sa.Column("ready_reason", sa.Text()),
        sa.Column("checklist", postgresql.JSONB()),
        sa.Column("content_fingerprint", sa.String(64)),
        _uuid("signed_record_id"),
        sa.Column("signed_by", sa.String(255)),
        _tz("signed_at"),
        sa.Column("qms_filing_ref", sa.String(120)),
        sa.Column("filed_by", sa.String(255)),
        _tz("filed_at"),
        sa.Column("source_system", sa.String(40)),
        _tz("updated_at", False),
        sa.UniqueConstraint("tenant_id", "complaint_id", name="uq_event_closures_complaint"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "complaint_id"],
            ["complaints.tenant_id", "complaints.id"],
            name="fk_event_closures_complaint",
            ondelete="CASCADE",
        ),
        _check(table, "ready_known", f"ready_state IS NULL OR ready_state IN ({quoted(READY_STATES)})"),
        _check(
            table,
            "ready_signed",
            "ready_state IS NULL OR (signed_record_id IS NOT NULL AND signed_by IS NOT NULL AND signed_at IS NOT NULL)",
        ),
        _check(table, "reason_given", "ready_state <> 'READY_WITH_REASON' OR ready_reason IS NOT NULL"),
    )
    for name in TABLES:
        _tenant_policy(name, system_scope)


def upgrade():
    create_oversight_tables()


def downgrade():
    for name in reversed(TABLES):
        op.drop_table(name)
