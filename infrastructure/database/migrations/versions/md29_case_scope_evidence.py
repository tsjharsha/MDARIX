"""Investigation scope and evidence (Phase 3): case workflow states, versioned scope, evidence review, and evidence
requests to colleagues as well as suppliers.

- ``investigations``: ``workflow_state`` (OPEN, IN_PROGRESS, ON_HOLD, BRIEF_IN_REVIEW, READY_FOR_DECISION, DECIDED,
  CLOSED, CANCELLED), ``priority``, ``due_at``, ``state_changed_at``. ``status`` keeps meaning open/closed. Existing
  cases: closed -> CLOSED, owned -> IN_PROGRESS, else OPEN.
- ``investigation_scope_versions`` (new): every scope version; each existing case gets version 1 from its question and
  linked complaints.
- ``investigation_evidence``: ``review_status``, ``relationship`` and who reviewed it, why and when.
- ``evidence_review_events`` (new): the history of those reviews.
- ``supplier_evidence_requests``: also requests to a colleague or a role (``request_kind`` INTERNAL), linked to an
  unknown, with priority, due date, answer and the evidence accepted from it; ``recipient`` (a supplier's address) may
  be empty for internal requests.
The models are in backend/app/db/models/{foundation,stage3,case_scope}.py. Legacy dedicated organization databases
get the same changes from scripts/add_workflow_tables_to_legacy_planes.py, which runs ``apply_case_scope_changes``.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from infrastructure.database.migrations.helpers import forced_tables as _forced
from infrastructure.database.migrations.helpers import quoted as _quoted
from infrastructure.database.migrations.helpers import tenant_policy as _tenant_policy

revision = "md29casescope"
down_revision = "md28signals"
branch_labels = None
depends_on = None

STATES = ("OPEN", "IN_PROGRESS", "ON_HOLD", "BRIEF_IN_REVIEW", "READY_FOR_DECISION", "DECIDED", "CLOSED", "CANCELLED")
PRIORITIES = ("LOW", "MEDIUM", "HIGH", "CRITICAL")
REVIEW_STATUSES = ("UNREVIEWED", "ACCEPTED", "ACCEPTED_WITH_LIMITATION", "REJECTED", "QUARANTINED", "SUPERSEDED")
RELATIONSHIPS = ("SUPPORTING", "CONTRADICTING", "CONTEXTUAL", "UNRESOLVED", "UNRELATED", "UNREVIEWED")
NEW_TABLES = ("investigation_scope_versions", "evidence_review_events")
# Tables the backfill reads or writes; FORCE row-level security is lifted on them for the backfill only.
BACKFILL_TABLES = ("investigations", "investigation_complaints", "complaints")


def apply_case_scope_changes(system_scope: bool = True) -> None:
    """Every change of this migration (also used for legacy organization databases)."""
    connection = op.get_bind()

    # 1. Case workflow state, priority and due date.
    op.add_column("investigations", sa.Column("workflow_state", sa.String(30), server_default="OPEN", nullable=False))
    op.add_column("investigations", sa.Column("priority", sa.String(20), server_default="MEDIUM", nullable=False))
    op.add_column("investigations", sa.Column("due_at", sa.DateTime(timezone=True)))
    op.add_column("investigations", sa.Column("state_changed_at", sa.DateTime(timezone=True)))
    op.create_check_constraint(
        op.f("ck_investigations_workflow_state_known"), "investigations", f"workflow_state IN ({_quoted(STATES)})"
    )
    op.create_check_constraint(
        op.f("ck_investigations_priority_known"), "investigations", f"priority IN ({_quoted(PRIORITIES)})"
    )

    # 2. Scope versions.
    op.create_table(
        "investigation_scope_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("investigation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        *(
            sa.Column(name, postgresql.JSONB(), server_default=sa.text("'[]'::jsonb"), nullable=False)
            for name in (
                "product_version_ids",
                "included_complaint_ids",
                "excluded_complaints",
                "lot_ids",
                "markets",
                "failure_mode_ids",
            )
        ),
        sa.Column("date_from", sa.Date()),
        sa.Column("date_to", sa.Date()),
        sa.Column("objectives", sa.Text()),
        sa.Column("change_reason", sa.Text()),
        sa.Column("reviews_must_restart", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("conclusions_invalidated", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        sa.Column("created_by", sa.String(255), nullable=False),
        sa.Column("created_role", sa.String(60)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_investigation_scope_versions")),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name=op.f("fk_investigation_scope_versions_tenant_id_tenants")
        ),
        sa.UniqueConstraint("tenant_id", "investigation_id", "version", name="uq_investigation_scope_versions_version"),
        sa.ForeignKeyConstraint(
            ["tenant_id", "investigation_id"],
            ["investigations.tenant_id", "investigations.id"],
            name="fk_investigation_scope_versions_investigation",
            ondelete="CASCADE",
        ),
    )

    # 3. Existing cases: their state, and version 1 of their scope (question, linked complaints and their versions).
    lifted = _forced(connection, BACKFILL_TABLES)
    for table in lifted:
        op.execute(f"ALTER TABLE public.{table} NO FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        UPDATE public.investigations
           SET workflow_state = CASE
                   WHEN lower(coalesce(status, '')) IN ('closed', 'resolved', 'completed', 'cancelled', 'archived')
                       THEN 'CLOSED'
                   WHEN owner_ref IS NOT NULL AND btrim(owner_ref) <> '' THEN 'IN_PROGRESS'
                   ELSE 'OPEN'
               END,
               state_changed_at = coalesce(closed_at, opened_at, created_at)
        """
    )
    op.execute(
        """
        INSERT INTO public.investigation_scope_versions
            (tenant_id, investigation_id, version, question, included_complaint_ids, product_version_ids, created_by,
             created_at)
        SELECT i.tenant_id, i.id, 1, i.investigation_question,
               coalesce((SELECT jsonb_agg(ic.complaint_id::text ORDER BY ic.complaint_id::text)
                           FROM public.investigation_complaints ic
                          WHERE ic.tenant_id = i.tenant_id AND ic.investigation_id = i.id), '[]'::jsonb),
               coalesce((SELECT jsonb_agg(DISTINCT c.product_version_id::text)
                           FROM public.investigation_complaints ic
                           JOIN public.complaints c ON c.tenant_id = ic.tenant_id AND c.id = ic.complaint_id
                          WHERE ic.tenant_id = i.tenant_id AND ic.investigation_id = i.id
                            AND c.product_version_id IS NOT NULL), '[]'::jsonb),
               'system:md29', coalesce(i.opened_at, i.created_at, now())
          FROM public.investigations i
        """
    )
    for table in lifted:
        op.execute(f"ALTER TABLE public.{table} FORCE ROW LEVEL SECURITY")
    _tenant_policy("investigation_scope_versions", system_scope)

    # 4. Evidence review on the case's evidence links.
    op.add_column(
        "investigation_evidence",
        sa.Column("review_status", sa.String(30), server_default="UNREVIEWED", nullable=False),
    )
    op.add_column(
        "investigation_evidence",
        sa.Column("relationship", sa.String(30), server_default="UNREVIEWED", nullable=False),
    )
    op.add_column("investigation_evidence", sa.Column("review_reason", sa.Text()))
    op.add_column("investigation_evidence", sa.Column("limitation", sa.Text()))
    op.add_column("investigation_evidence", sa.Column("reviewed_by", sa.String(255)))
    op.add_column("investigation_evidence", sa.Column("reviewed_at", sa.DateTime(timezone=True)))
    op.add_column("investigation_evidence", sa.Column("linked_by", sa.String(255)))
    op.create_check_constraint(
        op.f("ck_investigation_evidence_review_status_known"),
        "investigation_evidence",
        f"review_status IN ({_quoted(REVIEW_STATUSES)})",
    )
    op.create_check_constraint(
        op.f("ck_investigation_evidence_relationship_known"),
        "investigation_evidence",
        f"relationship IN ({_quoted(RELATIONSHIPS)})",
    )

    op.create_table(
        "evidence_review_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("investigation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("evidence_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_type", sa.String(40), nullable=False),
        sa.Column("from_review_status", sa.String(30)),
        sa.Column("to_review_status", sa.String(30)),
        sa.Column("from_relationship", sa.String(30)),
        sa.Column("to_relationship", sa.String(30)),
        sa.Column("reason", sa.Text()),
        sa.Column("actor_ref", sa.String(255)),
        sa.Column("actor_role", sa.String(60)),
        sa.Column("details", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_evidence_review_events")),
        sa.ForeignKeyConstraint(
            ["tenant_id"], ["tenants.id"], name=op.f("fk_evidence_review_events_tenant_id_tenants")
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "investigation_id"],
            ["investigations.tenant_id", "investigations.id"],
            name="fk_evidence_review_events_investigation",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "evidence_id"],
            ["evidence.tenant_id", "evidence.id"],
            name="fk_evidence_review_events_evidence",
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_evidence_review_events_tenant_case", "evidence_review_events", ["tenant_id", "investigation_id"]
    )
    _tenant_policy("evidence_review_events", system_scope)

    # 5. Evidence requests to colleagues and roles as well as suppliers.
    op.alter_column("supplier_evidence_requests", "recipient", existing_type=sa.String(254), nullable=True)
    for column in (
        sa.Column("request_kind", sa.String(20), server_default="SUPPLIER", nullable=False),
        sa.Column("recipient_user_id", postgresql.UUID(as_uuid=True)),
        sa.Column("recipient_role", sa.String(60)),
        sa.Column("unknown_id", postgresql.UUID(as_uuid=True)),
        sa.Column("priority", sa.String(20), server_default="MEDIUM", nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True)),
        sa.Column("acknowledged_at", sa.DateTime(timezone=True)),
        sa.Column("responded_at", sa.DateTime(timezone=True)),
        sa.Column("response_note", sa.Text()),
        sa.Column("cannot_provide_reason", sa.Text()),
        sa.Column("reviewed_by", sa.String(255)),
        sa.Column("reviewed_at", sa.DateTime(timezone=True)),
        sa.Column("resolved_evidence_id", postgresql.UUID(as_uuid=True)),
    ):
        op.add_column("supplier_evidence_requests", column)
    op.create_check_constraint(
        op.f("ck_supplier_evidence_requests_request_kind_known"),
        "supplier_evidence_requests",
        "request_kind IN ('SUPPLIER', 'INTERNAL')",
    )
    op.create_check_constraint(
        op.f("ck_supplier_evidence_requests_priority_known"),
        "supplier_evidence_requests",
        f"priority IN ({_quoted(PRIORITIES)})",
    )
    op.create_check_constraint(
        op.f("ck_supplier_evidence_requests_has_recipient"),
        "supplier_evidence_requests",
        "recipient IS NOT NULL OR recipient_user_id IS NOT NULL OR recipient_role IS NOT NULL",
    )


def upgrade():
    apply_case_scope_changes()


def downgrade():
    for name in ("has_recipient", "priority_known", "request_kind_known"):
        op.drop_constraint(op.f(f"ck_supplier_evidence_requests_{name}"), "supplier_evidence_requests", type_="check")
    for column in (
        "resolved_evidence_id",
        "reviewed_at",
        "reviewed_by",
        "cannot_provide_reason",
        "response_note",
        "responded_at",
        "acknowledged_at",
        "due_at",
        "priority",
        "unknown_id",
        "recipient_role",
        "recipient_user_id",
        "request_kind",
    ):
        op.drop_column("supplier_evidence_requests", column)
    # Internal requests have no address; they cannot survive the old NOT NULL rule.
    lifted = _forced(op.get_bind(), ("supplier_evidence_requests",))
    for table in lifted:
        op.execute(f"ALTER TABLE public.{table} NO FORCE ROW LEVEL SECURITY")
    op.execute("DELETE FROM public.supplier_evidence_requests WHERE recipient IS NULL")
    for table in lifted:
        op.execute(f"ALTER TABLE public.{table} FORCE ROW LEVEL SECURITY")
    op.alter_column("supplier_evidence_requests", "recipient", existing_type=sa.String(254), nullable=False)
    op.drop_table("evidence_review_events")
    for name in ("relationship_known", "review_status_known"):
        op.drop_constraint(op.f(f"ck_investigation_evidence_{name}"), "investigation_evidence", type_="check")
    for column in ("linked_by", "reviewed_at", "reviewed_by", "limitation", "review_reason", "relationship"):
        op.drop_column("investigation_evidence", column)
    op.drop_column("investigation_evidence", "review_status")
    op.drop_table("investigation_scope_versions")
    for name in ("priority_known", "workflow_state_known"):
        op.drop_constraint(op.f(f"ck_investigations_{name}"), "investigations", type_="check")
    for column in ("state_changed_at", "due_at", "priority", "workflow_state"):
        op.drop_column("investigations", column)
