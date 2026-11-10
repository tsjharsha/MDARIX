"""The routine complaint path, Case attachments and e-mail intake (backlog item B7, after the WHIF freeze).

When DB-1 (tr24tenantindexes) lands, set down_revision to tr24tenantindexes.

The twenty-fifth migration of the trial line, chained from ``tr19casesescalation`` (the single head on the B7 branch
base; DB-1's tr21-tr24 are not built yet). Expand-only: two new tables, new nullable columns or columns with a default,
one widened check constraint and one partial unique index. Nothing is dropped or renamed.

- ``inbound_messages`` (B7b): one e-mail received on an organization's intake address, waiting for a person to decide
  (make it a Case, add it to a Case, or not a case). An e-mail is never a complaint by itself.
- ``case_attachments``: a file on a Case (uploaded, or from an e-mail), virus-scanned; an infected file is never stored.
- ``event_closures``: the native closure in MDARIX Complete (``closed_at``, ``closed_by``) and the reopening.
- ``oversight_settings``: the opt-in urgent e-mail alert, the allowed sender domains and the daily e-mail limit.
- ``case_addenda``: the kinds ``TRANSLATION`` and ``EMAIL``.
- ``intake_events``: a Case import's key (source + ``case_id``) is unique per organization.

New tables get the forced tenant row-level security policy; references between tenant tables are composite. The
models are in backend/app/db/models/intake.py and oversight.py. Legacy dedicated organization databases get the same
from scripts/add_workflow_tables_to_legacy_planes.py, which runs ``add_routine_path``.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from infrastructure.database.migrations.helpers import quoted
from infrastructure.database.migrations.helpers import tenant_policy as _tenant_policy

revision = "tr25routinepath"
down_revision = "tr19casesescalation"
branch_labels = None
depends_on = None

NEW_TABLES = ("inbound_messages", "case_attachments")
MESSAGE_STATES = ("NEW", "MADE_CASE", "ADDED_TO_CASE", "NOT_A_CASE", "PURGED")
ATTACHMENT_SOURCES = ("EMAIL", "UPLOAD")
OLD_ADDENDUM_KINDS = ("STATEMENT", "WITHDRAWAL", "TECHNICIAN_FINDING", "CORRECTION_BY_REPORTER")
ADDENDUM_KINDS = (*OLD_ADDENDUM_KINDS, "TRANSLATION", "EMAIL")
CLOSURE_COLUMNS = ("closed_at", "closed_by", "reopened_at", "reopened_by", "reopen_reason")
SETTINGS_COLUMNS = ("urgent_email", "mail_allowed_domains", "mail_daily_limit")


def _uuid(name: str, nullable: bool = True) -> sa.Column:
    return sa.Column(name, postgresql.UUID(as_uuid=True), nullable=nullable)


def _tz(name: str, nullable: bool = True) -> sa.Column:
    return sa.Column(name, sa.DateTime(timezone=True), nullable=nullable)


def _jsonb(name: str, default: str) -> sa.Column:
    return sa.Column(name, postgresql.JSONB(), nullable=False, server_default=sa.text(f"'{default}'::jsonb"))


def _common(table: str) -> list:
    return [
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        _uuid("tenant_id", False),
        sa.PrimaryKeyConstraint("id", name=op.f(f"pk_{table}")),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], name=op.f(f"fk_{table}_tenant_id_tenants")),
        sa.UniqueConstraint("tenant_id", "id", name=f"uq_{table}_tenant_id_id"),
    ]


def _case_fk(table: str) -> sa.ForeignKeyConstraint:
    return sa.ForeignKeyConstraint(
        ["tenant_id", "intake_event_id"],
        ["intake_events.tenant_id", "intake_events.id"],
        name=f"fk_{table}_case",
    )


def _messages() -> None:
    table = "inbound_messages"
    op.create_table(
        table,
        *_common(table),
        sa.Column("message_id", sa.String(998), nullable=False),
        sa.Column("in_reply_to", sa.String(998)),
        _jsonb("references", "[]"),
        sa.Column("subject_masked", sa.Text()),
        sa.Column("from_domain", sa.String(255)),
        _tz("received_at", False),
        _jsonb("header_dates", "[]"),
        sa.Column("body_sha256", sa.String(64)),
        sa.Column("raw_object_key", sa.String(500)),
        sa.Column("raw_size", sa.Integer()),
        _jsonb("attachments", "[]"),
        _jsonb("flags", "{}"),
        _jsonb("draft", "{}"),
        sa.Column("state", sa.String(20), nullable=False, server_default="NEW"),
        sa.Column("reason", sa.Text()),
        _uuid("intake_event_id"),
        sa.Column("decided_by", sa.String(255)),
        _tz("decided_at"),
        _tz("purge_after"),
        sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1")),
        _tz("created_at", False),
        _case_fk(table),
        sa.UniqueConstraint("tenant_id", "message_id", name="uq_inbound_messages_message"),
        sa.CheckConstraint(f"state IN ({quoted(MESSAGE_STATES)})", name=op.f(f"ck_{table}_state_known")),
        sa.CheckConstraint("version >= 1", name=op.f(f"ck_{table}_version_positive")),
        sa.CheckConstraint("raw_size IS NULL OR raw_size >= 0", name=op.f(f"ck_{table}_raw_size_positive")),
    )
    op.create_index("ix_inbound_messages_tenant_state", table, ["tenant_id", "state", "received_at"])
    op.create_index("ix_inbound_messages_tenant_case", table, ["tenant_id", "intake_event_id"])


def _attachments() -> None:
    table = "case_attachments"
    op.create_table(
        table,
        *_common(table),
        _uuid("intake_event_id"),
        _uuid("inbound_message_id"),
        sa.Column("object_key", sa.String(500)),
        sa.Column("filename_masked", sa.String(255), nullable=False),
        sa.Column("content_type", sa.String(120), nullable=False),
        sa.Column("size", sa.Integer(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.Column("usable", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("unusable_reason", sa.Text()),
        sa.Column("source", sa.String(10), nullable=False),
        sa.Column("created_by", sa.String(255), nullable=False),
        _tz("created_at", False),
        _case_fk(table),
        sa.ForeignKeyConstraint(
            ["tenant_id", "inbound_message_id"],
            ["inbound_messages.tenant_id", "inbound_messages.id"],
            name="fk_case_attachments_message",
        ),
        sa.CheckConstraint(f"source IN ({quoted(ATTACHMENT_SOURCES)})", name=op.f(f"ck_{table}_source_known")),
        sa.CheckConstraint("size >= 0", name=op.f(f"ck_{table}_size_positive")),
        # A usable file is stored; an unusable one (infected, refused) is recorded without its content, with the reason.
        sa.CheckConstraint(
            "(usable AND object_key IS NOT NULL) OR (NOT usable AND unusable_reason IS NOT NULL)",
            name=op.f(f"ck_{table}_usable_stored"),
        ),
        sa.CheckConstraint(
            "intake_event_id IS NOT NULL OR inbound_message_id IS NOT NULL", name=op.f(f"ck_{table}_has_owner")
        ),
    )
    op.create_index("ix_case_attachments_tenant_case", table, ["tenant_id", "intake_event_id"])
    op.create_index("ix_case_attachments_tenant_message", table, ["tenant_id", "inbound_message_id"])


def _closures() -> None:
    table = "event_closures"
    for name in ("closed_at", "reopened_at"):
        op.add_column(table, sa.Column(name, sa.DateTime(timezone=True)))
    for name in ("closed_by", "reopened_by"):
        op.add_column(table, sa.Column(name, sa.String(255)))
    op.add_column(table, sa.Column("reopen_reason", sa.Text()))
    op.create_check_constraint(
        op.f("ck_event_closures_closed_signed"),
        table,
        "closed_at IS NULL OR (closed_by IS NOT NULL AND ready_state IS NOT NULL)",
    )
    op.create_check_constraint(
        op.f("ck_event_closures_reopen_reason"), table, "reopened_at IS NULL OR reopen_reason IS NOT NULL"
    )


def _settings() -> None:
    table = "oversight_settings"
    op.add_column(table, sa.Column("urgent_email", sa.Boolean(), nullable=False, server_default=sa.text("false")))
    op.add_column(table, _jsonb("mail_allowed_domains", "[]"))
    op.add_column(table, sa.Column("mail_daily_limit", sa.Integer(), nullable=False, server_default=sa.text("200")))
    op.create_check_constraint(
        op.f("ck_oversight_settings_mail_limit_range"), table, "mail_daily_limit BETWEEN 1 AND 5000"
    )


def _addenda(kinds) -> None:
    op.drop_constraint(op.f("ck_case_addenda_kind_known"), "case_addenda", type_="check")
    op.create_check_constraint(op.f("ck_case_addenda_kind_known"), "case_addenda", f"kind IN ({quoted(kinds)})")


def _case_import_key() -> None:
    # No row has this source before this migration, so the index builds over nothing.
    op.create_index(
        "ix_intake_events_case_import_key",
        "intake_events",
        ["tenant_id", "source_identifier"],
        unique=True,
        postgresql_where=sa.text("source_system = 'CASE_IMPORT'"),
    )


def add_routine_path(system_scope: bool = True) -> None:
    """Every change of this migration (also used for legacy organization databases)."""
    _messages()
    _attachments()
    _closures()
    _settings()
    _addenda(ADDENDUM_KINDS)
    _case_import_key()
    for table in NEW_TABLES:
        _tenant_policy(table, system_scope)


def upgrade():
    add_routine_path()


def downgrade():
    op.drop_index("ix_intake_events_case_import_key", table_name="intake_events")
    # Addenda of the new kinds cannot stay under the old check: it is restored as NOT VALID, so they are kept
    # (regulated records are never deleted) while new rows meet the old list.
    op.drop_constraint(op.f("ck_case_addenda_kind_known"), "case_addenda", type_="check")
    op.execute(
        "ALTER TABLE case_addenda ADD CONSTRAINT ck_case_addenda_kind_known "
        f"CHECK (kind IN ({quoted(OLD_ADDENDUM_KINDS)})) NOT VALID"
    )
    op.drop_constraint(op.f("ck_oversight_settings_mail_limit_range"), "oversight_settings", type_="check")
    for column in reversed(SETTINGS_COLUMNS):
        op.drop_column("oversight_settings", column)
    op.drop_constraint(op.f("ck_event_closures_reopen_reason"), "event_closures", type_="check")
    op.drop_constraint(op.f("ck_event_closures_closed_signed"), "event_closures", type_="check")
    for column in reversed(CLOSURE_COLUMNS):
        op.drop_column("event_closures", column)
    for table in reversed(NEW_TABLES):
        op.drop_table(table)
