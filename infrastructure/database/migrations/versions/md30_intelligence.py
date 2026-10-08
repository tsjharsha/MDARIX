"""Intelligence alignment (Phase 4): people's judgements next to AI output, manual items when AI is off, and an
explicit kind for every observation.

- ``hypotheses``: ``human_status`` (PROPOSED, HYPOTHESIZED, PARTIALLY_SUPPORTED, STRONGLY_SUPPORTED, WEAKLY_SUPPORTED,
  CONTRADICTED, RETIRED) with reason, who and when; ``created_by`` for hypotheses a person adds (origin "human").
- ``hypothesis_evidence``: ``created_by`` and withdrawal (``retracted_*``) instead of deletion.
- ``unknowns``: ``origin`` (system/ai/human), ``created_by``, who changed the status and when.
- ``failure_chains``: ``origin``, ``created_by``, ``source_ai_execution_id``; ``failure_chain_edges``: who changed a
  link state and when.
- ``evidence_observations``: ``epistemic_type`` (FACT, SOURCE_ASSERTION, DERIVED_OBSERVATION, AI_INTERPRETATION),
  ``origin`` (HUMAN, AI, SYSTEM), ``created_by``, ``investigation_id``; existing rows are labelled from how they were
  extracted.
- ``intelligence_events`` (new): the history of those judgements. Tenant-isolated.
AI output in ``ai_executions`` is not changed. Legacy dedicated organization databases get the same changes from
scripts/add_workflow_tables_to_legacy_planes.py, which runs ``apply_intelligence_changes``.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

from infrastructure.database.migrations.helpers import quoted as _quoted
from infrastructure.database.migrations.helpers import tenant_policy as _tenant_policy

revision = "md30intelligence"
down_revision = "md29casescope"
branch_labels = None
depends_on = None

HUMAN_STATUSES = (
    "PROPOSED",
    "HYPOTHESIZED",
    "PARTIALLY_SUPPORTED",
    "STRONGLY_SUPPORTED",
    "WEAKLY_SUPPORTED",
    "CONTRADICTED",
    "RETIRED",
)
EPISTEMIC_TYPES = ("FACT", "SOURCE_ASSERTION", "DERIVED_OBSERVATION", "AI_INTERPRETATION")
ORIGINS = ("HUMAN", "AI", "SYSTEM")


def _forced(connection, table: str) -> bool:
    return bool(
        connection.execute(
            sa.text("SELECT relforcerowsecurity FROM pg_class WHERE oid = to_regclass(:name)"),
            {"name": f"public.{table}"},
        ).scalar()
    )


def apply_intelligence_changes(system_scope: bool = True) -> None:
    """Every change of this migration (also used for legacy organization databases)."""
    connection = op.get_bind()

    op.add_column("hypotheses", sa.Column("human_status", sa.String(30)))
    op.add_column("hypotheses", sa.Column("status_reason", sa.Text()))
    op.add_column("hypotheses", sa.Column("status_changed_by", sa.String(255)))
    op.add_column("hypotheses", sa.Column("status_changed_at", sa.DateTime(timezone=True)))
    op.add_column("hypotheses", sa.Column("created_by", sa.String(255)))
    op.create_check_constraint(
        op.f("ck_hypotheses_human_status_known"),
        "hypotheses",
        f"human_status IS NULL OR human_status IN ({_quoted(HUMAN_STATUSES)})",
    )

    op.add_column("hypothesis_evidence", sa.Column("created_by", sa.String(255)))
    op.add_column("hypothesis_evidence", sa.Column("retracted_at", sa.DateTime(timezone=True)))
    op.add_column("hypothesis_evidence", sa.Column("retracted_by", sa.String(255)))
    op.add_column("hypothesis_evidence", sa.Column("retraction_reason", sa.Text()))

    op.add_column("unknowns", sa.Column("origin", sa.String(20), server_default="system", nullable=False))
    op.add_column("unknowns", sa.Column("created_by", sa.String(255)))
    op.add_column("unknowns", sa.Column("status_changed_by", sa.String(255)))
    op.add_column("unknowns", sa.Column("status_changed_at", sa.DateTime(timezone=True)))

    op.add_column("failure_chains", sa.Column("origin", sa.String(20), server_default="system", nullable=False))
    op.add_column("failure_chains", sa.Column("created_by", sa.String(255)))
    op.add_column("failure_chains", sa.Column("source_ai_execution_id", postgresql.UUID(as_uuid=True)))
    op.add_column("failure_chain_edges", sa.Column("updated_by", sa.String(255)))
    op.add_column("failure_chain_edges", sa.Column("updated_at", sa.DateTime(timezone=True)))

    op.add_column("evidence_observations", sa.Column("epistemic_type", sa.String(30)))
    op.add_column("evidence_observations", sa.Column("origin", sa.String(20)))
    op.add_column("evidence_observations", sa.Column("created_by", sa.String(255)))
    op.add_column("evidence_observations", sa.Column("investigation_id", postgresql.UUID(as_uuid=True)))
    op.create_check_constraint(
        op.f("ck_evidence_observations_epistemic_type_known"),
        "evidence_observations",
        f"epistemic_type IS NULL OR epistemic_type IN ({_quoted(EPISTEMIC_TYPES)})",
    )
    op.create_check_constraint(
        op.f("ck_evidence_observations_origin_known"),
        "evidence_observations",
        f"origin IS NULL OR origin IN ({_quoted(ORIGINS)})",
    )
    # Existing observations: a deterministic structured extraction is a fact from the source; a statement quoted from
    # the source is a source assertion (extracted by AI or by rules); anything else an AI produced is its
    # interpretation, and anything else rules produced is a derived observation.
    forced = _forced(connection, "evidence_observations")
    if forced:
        op.execute("ALTER TABLE public.evidence_observations NO FORCE ROW LEVEL SECURITY")
    op.execute(
        """
        UPDATE public.evidence_observations
           SET origin = CASE WHEN upper(coalesce(extraction_method, '')) IN ('GENAI', 'AI', 'MODEL', 'LLM')
                             THEN 'AI' ELSE 'SYSTEM' END,
               epistemic_type = CASE
                   WHEN upper(coalesce(observation_type, '')) = 'STRUCTURED_EXTRACTION'
                        AND upper(coalesce(extraction_method, '')) NOT IN ('GENAI', 'AI', 'MODEL', 'LLM')
                       THEN 'FACT'
                   WHEN upper(coalesce(observation_type, '')) IN ('EXPLICIT_SOURCE_STATEMENT', 'STRUCTURED_EXTRACTION')
                       THEN 'SOURCE_ASSERTION'
                   WHEN upper(coalesce(extraction_method, '')) IN ('GENAI', 'AI', 'MODEL', 'LLM')
                       THEN 'AI_INTERPRETATION'
                   ELSE 'DERIVED_OBSERVATION'
               END
         WHERE epistemic_type IS NULL
        """
    )
    if forced:
        op.execute("ALTER TABLE public.evidence_observations FORCE ROW LEVEL SECURITY")

    op.create_table(
        "intelligence_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), server_default=sa.text("gen_random_uuid()"), nullable=False),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("investigation_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("object_type", sa.String(40), nullable=False),
        sa.Column("object_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("event_type", sa.String(40), nullable=False),
        sa.Column("from_value", sa.String(60)),
        sa.Column("to_value", sa.String(60)),
        sa.Column("reason", sa.Text()),
        sa.Column("actor_ref", sa.String(255)),
        sa.Column("actor_role", sa.String(60)),
        sa.Column("details", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_intelligence_events")),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"], name=op.f("fk_intelligence_events_tenant_id_tenants")),
        sa.ForeignKeyConstraint(
            ["tenant_id", "investigation_id"],
            ["investigations.tenant_id", "investigations.id"],
            name="fk_intelligence_events_investigation",
            ondelete="CASCADE",
        ),
    )
    op.create_index("ix_intelligence_events_tenant_case", "intelligence_events", ["tenant_id", "investigation_id"])
    op.create_index(
        "ix_intelligence_events_tenant_object", "intelligence_events", ["tenant_id", "object_type", "object_id"]
    )
    _tenant_policy("intelligence_events", system_scope)


def upgrade():
    apply_intelligence_changes()


def downgrade():
    op.drop_table("intelligence_events")
    for name in ("origin_known", "epistemic_type_known"):
        op.drop_constraint(op.f(f"ck_evidence_observations_{name}"), "evidence_observations", type_="check")
    for column in ("investigation_id", "created_by", "origin", "epistemic_type"):
        op.drop_column("evidence_observations", column)
    for column in ("updated_at", "updated_by"):
        op.drop_column("failure_chain_edges", column)
    for column in ("source_ai_execution_id", "created_by", "origin"):
        op.drop_column("failure_chains", column)
    for column in ("status_changed_at", "status_changed_by", "created_by", "origin"):
        op.drop_column("unknowns", column)
    for column in ("retraction_reason", "retracted_by", "retracted_at", "created_by"):
        op.drop_column("hypothesis_evidence", column)
    op.drop_constraint(op.f("ck_hypotheses_human_status_known"), "hypotheses", type_="check")
    for column in ("created_by", "status_changed_at", "status_changed_by", "status_reason", "human_status"):
        op.drop_column("hypotheses", column)
