"""Intelligence values (Phase 4): widen four check constraints so people's judgements can be stored. Every value that
was allowed before stays allowed.

- ``hypothesis_evidence.relation_type``: adds ``contextual`` and ``unresolved`` (to ``support``, ``contradict``).
- ``failure_chain_edges.edge_status``: adds SUPPORTED, PARTIALLY_SUPPORTED, HYPOTHESIZED, UNKNOWN, CONTRADICTED (to
  ``established_fact``, ``hypothesized``, ``contradicted``).
- ``evidence_observations.observation_type``: adds HUMAN_OBSERVATION; ``extraction_method``: adds HUMAN.
Legacy dedicated organization databases get the same change from scripts/add_workflow_tables_to_legacy_planes.py,
which runs ``widen_intelligence_values``.
"""

from alembic import op

revision = "md31intelligencevalues"
down_revision = "md30intelligence"
branch_labels = None
depends_on = None

# (table, constraint name, widened rule, original rule)
RULES = (
    (
        "hypothesis_evidence",
        "ck_hypothesis_evidence_hypothesis_evidence_relation_allowed",
        "relation_type in ('support','contradict','contextual','unresolved')",
        "relation_type in ('support','contradict')",
    ),
    (
        "failure_chain_edges",
        "ck_failure_chain_edges_failure_chain_edge_status_allowed",
        "edge_status in ('established_fact','hypothesized','contradicted',"
        "'SUPPORTED','PARTIALLY_SUPPORTED','HYPOTHESIZED','UNKNOWN','CONTRADICTED')",
        "edge_status in ('established_fact','hypothesized','contradicted')",
    ),
    (
        "evidence_observations",
        "ck_evidence_observations_evidence_obs_type_allowed",
        "observation_type in ('EXPLICIT_SOURCE_STATEMENT','STRUCTURED_EXTRACTION','DETERMINISTIC_DERIVATION',"
        "'AI_EXTRACTED_OBSERVATION','HUMAN_OBSERVATION')",
        "observation_type in ('EXPLICIT_SOURCE_STATEMENT','STRUCTURED_EXTRACTION','DETERMINISTIC_DERIVATION',"
        "'AI_EXTRACTED_OBSERVATION')",
    ),
    (
        "evidence_observations",
        "ck_evidence_observations_evidence_obs_method_allowed",
        "extraction_method in ('DETERMINISTIC','GENAI','HUMAN')",
        "extraction_method in ('DETERMINISTIC','GENAI')",
    ),
)


def _replace(table: str, name: str, rule: str) -> None:
    op.execute(f"ALTER TABLE public.{table} DROP CONSTRAINT IF EXISTS {name}")
    op.execute(f"ALTER TABLE public.{table} ADD CONSTRAINT {name} CHECK ({rule})")


def widen_intelligence_values(system_scope: bool = True) -> None:
    """The widened rules (also used for legacy organization databases; ``system_scope`` is not needed here)."""
    for table, name, widened, _original in RULES:
        _replace(table, name, widened)


def upgrade():
    widen_intelligence_values()


def downgrade():
    # Rows using a new value would break the original rules; they must be changed or removed first.
    for table, name, _widened, original in RULES:
        _replace(table, name, original)
