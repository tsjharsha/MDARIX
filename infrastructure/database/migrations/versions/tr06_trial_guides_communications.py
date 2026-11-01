"""The customer's own decision guide versions and the external communications log (release 0.10.59).

The fifth migration of the trial line's expert-feedback releases (TRIAL_FEEDBACK_PLAN.md section 7: T-G15, T-G30),
chained from ``tr05authorityreports``. Its revision id starts with ``tr`` so it never collides with an ``md`` revision
of ``mvp-1.0`` (``tr03pmssources`` stays reserved for proactive PMS); after the forward merge, ``mvp-1.0`` adds a merge
revision joining its head and this one.

Expand-only: four new tables, each with its indexes and the tenant row-level security policy. No existing table or
row changes. The downgrade removes only what this migration added.

- ``decision_guide_versions``: the organization's own versions of a market's guide (version 1 is MDARIX's starter, in
  code), with their questions, clauses, test cases and results, and the second person's approval;
- ``external_parties``: reporters, distributors, hospitals and service partners, each with a primary and a second
  contact;
- ``communication_entries``: each message sent or received, with its attempts, owner, reply due date and status;
- ``communication_settings``: the number of unanswered attempts before a request moves on.

The models are in backend/app/db/models/guides_communications.py. Legacy dedicated organization databases get the
same from scripts/add_workflow_tables_to_legacy_planes.py, which runs ``create_guide_communication_tables``.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from infrastructure.database.migrations.helpers import quoted
from infrastructure.database.migrations.helpers import tenant_policy as _tenant_policy

revision = "tr06guidescomms"
down_revision = "tr05authorityreports"
branch_labels = None
depends_on = None

TABLES = ("communication_entries", "external_parties", "decision_guide_versions", "communication_settings")
GUIDE_STATES = ("DRAFT", "AWAITING_APPROVAL", "PUBLISHED", "SUPERSEDED", "DISCARDED")
PARTY_TYPES = ("REPORTER", "DISTRIBUTOR", "HOSPITAL", "SERVICE_PARTNER")
DIRECTIONS = ("SENT", "RECEIVED")
PURPOSES = ("INFORMATION_REQUEST", "UPDATE", "RESPONSE")
STATUSES = ("OPEN", "ANSWERED", "UNRESOLVED", "CLOSED")
CONTACTS = ("PRIMARY", "SECOND")


def _uuid(name: str, nullable: bool = True) -> sa.Column:
    return sa.Column(name, postgresql.UUID(as_uuid=True), nullable=nullable)


def _tz(name: str, nullable: bool = True) -> sa.Column:
    return sa.Column(name, sa.DateTime(timezone=True), nullable=nullable)


def _jsonb(name: str, default: str | None = "'[]'::jsonb") -> sa.Column:
    if default is None:
        return sa.Column(name, postgresql.JSONB())
    return sa.Column(name, postgresql.JSONB(), server_default=sa.text(default), nullable=False)


def _common(table: str) -> list:
    return [
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        _uuid("tenant_id", False),
        sa.PrimaryKeyConstraint("id", name=op.f(f"pk_{table}")),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], name=op.f(f"fk_{table}_tenant_id_tenants")),
    ]


def _check(table: str, name: str, condition: str) -> sa.CheckConstraint:
    return sa.CheckConstraint(condition, name=op.f(f"ck_{table}_{name}"))


def create_guide_communication_tables(system_scope: bool = True) -> None:
    """The four tables and their isolation (also used for legacy organization databases)."""
    table = "decision_guide_versions"
    op.create_table(
        table,
        *_common(table),
        sa.Column("market", sa.String(10), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("code", sa.String(40), nullable=False),
        sa.Column("based_on", sa.String(40), nullable=False),
        sa.Column("state", sa.String(20), server_default="DRAFT", nullable=False),
        sa.Column("questions", postgresql.JSONB(), nullable=False),
        _jsonb("test_cases"),
        _jsonb("test_results", None),
        sa.Column("change_reason", sa.Text()),
        _jsonb("editors"),
        sa.Column("content_fingerprint", sa.String(64)),
        sa.Column("requested_by", sa.String(255)),
        _tz("requested_at"),
        sa.Column("approved_by", sa.String(255)),
        _tz("approved_at"),
        _uuid("signed_record_id"),
        _tz("published_at"),
        _tz("superseded_at"),
        sa.Column("source_system", sa.String(40)),
        sa.Column("created_by", sa.String(255), nullable=False),
        _tz("created_at", False),
        sa.Column("updated_by", sa.String(255), nullable=False),
        _tz("updated_at", False),
        sa.UniqueConstraint("tenant_id", "market", "version", name="uq_decision_guide_versions_version"),
        sa.UniqueConstraint("tenant_id", "code", name="uq_decision_guide_versions_code"),
        _check(table, "state_known", f"state IN ({quoted(GUIDE_STATES)})"),
        _check(table, "customer_version", "version >= 2"),
        _check(
            table,
            "published_signed",
            "state NOT IN ('PUBLISHED', 'SUPERSEDED') OR (approved_by IS NOT NULL AND signed_record_id IS NOT NULL)",
        ),
    )
    op.create_index(
        "uq_decision_guide_versions_open",
        table,
        ["tenant_id", "market"],
        unique=True,
        postgresql_where=sa.text("state IN ('DRAFT', 'AWAITING_APPROVAL')"),
    )
    op.create_index(
        "uq_decision_guide_versions_published",
        table,
        ["tenant_id", "market"],
        unique=True,
        postgresql_where=sa.text("state = 'PUBLISHED'"),
    )
    table = "external_parties"
    op.create_table(
        table,
        *_common(table),
        sa.Column("party_type", sa.String(20), nullable=False),
        sa.Column("name", sa.String(200), nullable=False),
        _uuid("complaint_id"),
        sa.Column("primary_name", sa.String(200)),
        sa.Column("primary_details", sa.String(300)),
        sa.Column("second_name", sa.String(200)),
        sa.Column("second_details", sa.String(300)),
        sa.Column("note", sa.Text()),
        sa.Column("source_system", sa.String(40)),
        sa.Column("created_by", sa.String(255), nullable=False),
        _tz("created_at", False),
        sa.Column("updated_by", sa.String(255), nullable=False),
        _tz("updated_at", False),
        sa.ForeignKeyConstraint(
            ["tenant_id", "complaint_id"],
            ["complaints.tenant_id", "complaints.id"],
            name="fk_external_parties_complaint",
            ondelete="CASCADE",
        ),
        _check(table, "party_type_known", f"party_type IN ({quoted(PARTY_TYPES)})"),
    )
    op.create_index("ix_external_parties_tenant_type", table, ["tenant_id", "party_type"])
    table = "communication_entries"
    op.create_table(
        table,
        *_common(table),
        _uuid("complaint_id"),
        _uuid("intake_event_id"),
        _uuid("party_id", False),
        sa.Column("direction", sa.String(10), nullable=False),
        sa.Column("purpose", sa.String(30), nullable=False),
        sa.Column("subject", sa.String(400), nullable=False),
        sa.Column("note", sa.Text()),
        sa.Column("channel", sa.String(20), nullable=False),
        _tz("occurred_at", False),
        _tz("logged_at", False),
        sa.Column("logged_by", sa.String(255), nullable=False),
        sa.Column("owner_id", sa.String(255)),
        sa.Column("reply_due_on", sa.Date()),
        sa.Column("status", sa.String(20), server_default="CLOSED", nullable=False),
        sa.Column("current_contact", sa.String(10), server_default="PRIMARY", nullable=False),
        _jsonb("attempts"),
        _jsonb("evidence"),
        sa.Column("qms_reference", sa.String(120)),
        _uuid("in_reply_to"),
        _jsonb("origin", None),
        _uuid("task_id"),
        _tz("closed_at"),
        sa.Column("closed_by", sa.String(255)),
        sa.Column("close_note", sa.Text()),
        sa.Column("source_system", sa.String(40)),
        _tz("updated_at", False),
        sa.ForeignKeyConstraint(
            ["tenant_id", "complaint_id"],
            ["complaints.tenant_id", "complaints.id"],
            name="fk_communication_entries_complaint",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["party_id"], ["external_parties.id"], name=op.f("fk_communication_entries_party_id_external_parties")
        ),
        sa.ForeignKeyConstraint(
            ["in_reply_to"],
            ["communication_entries.id"],
            name=op.f("fk_communication_entries_in_reply_to_communication_entries"),
        ),
        _check(table, "direction_known", f"direction IN ({quoted(DIRECTIONS)})"),
        _check(table, "purpose_known", f"purpose IN ({quoted(PURPOSES)})"),
        _check(table, "status_known", f"status IN ({quoted(STATUSES)})"),
        _check(table, "contact_known", f"current_contact IN ({quoted(CONTACTS)})"),
        _check(table, "has_subject", "complaint_id IS NOT NULL OR intake_event_id IS NOT NULL"),
    )
    op.create_index("ix_communication_entries_tenant_complaint", table, ["tenant_id", "complaint_id"])
    op.create_index("ix_communication_entries_tenant_status", table, ["tenant_id", "status"])
    table = "communication_settings"
    op.create_table(
        table,
        *_common(table),
        sa.Column("attempts_before_escalation", sa.Integer(), server_default=sa.text("3"), nullable=False),
        sa.Column("updated_by", sa.String(255)),
        _tz("updated_at", False),
        sa.UniqueConstraint("tenant_id", name="uq_communication_settings_tenant"),
        _check(table, "attempts_range", "attempts_before_escalation BETWEEN 1 AND 10"),
    )
    for name in TABLES:
        _tenant_policy(name, system_scope)


def upgrade():
    create_guide_communication_tables()


def downgrade():
    for name in TABLES:
        op.drop_table(name)
