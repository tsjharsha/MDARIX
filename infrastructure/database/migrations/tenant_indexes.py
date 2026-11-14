"""Indexes added by migration tr24 (DB-1, defect DB-05). Migration-owned: drift_policy.py excludes them by name.

Every row-level security policy filters on ``tenant_id``, and a reference is checked (and a parent row deleted)
through the referencing columns, so:

- each reference made or added by tr23 gets an index on its columns, where none starts with them;
- the most-used references the audit listed without an index (db-audit N6) get one;
- each organization table with no index starting with ``tenant_id`` gets ``(tenant_id, created_at)`` (or
  ``(tenant_id)`` without ``created_at``).

Frozen for tr24; a later migration that needs more indexes lists its own.
"""

from __future__ import annotations

_TENANT_REFERENCE_INDEXES = (
    ("canonical_relationships", ("tenant_id", "normalization_run_id")),
    ("canonical_relationships", ("tenant_id", "source_link_id")),
    ("cell_heartbeats", ("tenant_id", "cell_id")),
    ("communication_entries", ("tenant_id", "in_reply_to")),
    ("communication_entries", ("tenant_id", "party_id")),
    ("connector_reconciliations", ("tenant_id", "connector_run_id")),
    ("connector_source_records", ("tenant_id", "connector_run_id")),
    ("data_quality_issues", ("tenant_id", "ingestion_run_id")),
    ("data_quality_issues", ("tenant_id", "staged_source_record_id")),
    ("normalization_issues", ("tenant_id", "normalization_run_id")),
    ("normalization_issues", ("tenant_id", "staged_source_record_id")),
    ("provisioning_job_steps", ("tenant_id", "provisioning_job_id")),
    ("report_obligations", ("tenant_id", "assessment_id")),
    ("report_obligations", ("tenant_id", "parent_id")),
    ("report_submissions", ("tenant_id", "snapshot_id")),
    ("source_canonical_links", ("tenant_id", "normalization_run_id")),
    ("staged_source_records", ("tenant_id", "ingestion_run_id")),
) + tuple(
    (table, ("tenant_id", "source_record_id"))
    for table in (
        "capas",
        "changes",
        "complaints",
        "components",
        "controls",
        "evidence",
        "failure_modes",
        "hypotheses",
        "investigations",
        "lot_batches",
        "manufacturing_sites",
        "product_versions",
        "products",
        "requirements",
        "risks",
        "scenarios",
        "suppliers",
    )
)

_VERSION_INDEXES = tuple(
    (table, ("tenant_id", "product_id", "product_version_id"))
    for table in (
        "ai_interactions",
        "assurance_results",
        "complaints",
        "decisions",
        "intake_events",
        "investigation_briefs",
        "requirements",
        "risks",
    )
)

_AUDIT_TOP_REFERENCES = (
    ("complaints", ("tenant_id", "lot_batch_id")),
    ("complaints", ("tenant_id", "product_version_id")),
    ("evidence_embeddings", ("tenant_id", "evidence_id")),
    ("evidence_chunk_embeddings", ("tenant_id", "evidence_id")),
    ("evidence_observations", ("tenant_id", "chunk_id")),
    ("evidence_observations", ("tenant_id", "ai_execution_id")),
    ("evidence_entity_links", ("tenant_id", "observation_id")),
    ("evidence_proposition_relations", ("tenant_id", "observation_id")),
    ("investigation_complaints", ("tenant_id", "complaint_id")),
    ("investigation_evidence", ("tenant_id", "evidence_id")),
    ("external_parties", ("tenant_id", "complaint_id")),
    ("ai_executions", ("tenant_id", "investigation_id")),
)

_TENANT_LEADING = tuple(
    (table, ("tenant_id", "created_at"))
    for table in (
        "ai_interaction_feedback",
        "ai_interaction_sessions",
        "approval_authorities",
        "authentication_events",
        "client_error_reports",
        "failure_chain_edges",
        "inbound_email_events",
        "lot_components",
        "mapping_impact_history",
        "onboarding_requests",
        "platform_incidents",
        "product_suppliers",
        "segregation_of_duties_policies",
        "tenant_plan_assignments",
    )
) + (("event_outbox", ("tenant_id",)),)


def index_name(table: str, columns: tuple[str, ...]) -> str:
    if columns == ("tenant_id", "product_id", "product_version_id"):
        return f"ix_{table}_tenant_version"
    return f"ix_{table}_{'_'.join(columns)}"


INDEXES: tuple[tuple[str, str, tuple[str, ...]], ...] = tuple(
    (index_name(table, columns), table, columns)
    for table, columns in _TENANT_REFERENCE_INDEXES + _VERSION_INDEXES + _AUDIT_TOP_REFERENCES + _TENANT_LEADING
)
INDEX_NAMES = frozenset(name for name, _, _ in INDEXES)

assert len(INDEX_NAMES) == len(INDEXES), "duplicate index name"
assert all(len(name) <= 63 for name in INDEX_NAMES), "an index name is longer than PostgreSQL allows"
