"""References between organization tables that include the organization (release DB-1: DB-01 and PV-1 F1).

PostgreSQL checks a foreign key as the table owner, without row-level security, so a single-column reference
``child.x_id -> parent.id`` lets a row of one organization point at a row of another (db-audit N1). ``tr23`` replaces
each one below with the composite ``(tenant_id, x_id) -> parent (tenant_id, id)``, and makes a record's product
version a version of the record's own product: ``(tenant_id, product_id, product_version_id) -> product_versions
(tenant_id, product_id, id)``, plus a check that a version is never set without its product (MATCH SIMPLE skips the
reference when ``product_id`` is empty).

``tr22`` counts the rows that would break these rules and refuses with the counts; ``scripts/check_tenant_references.py``
runs the same count on its own, read only (for example on a copy of a production backup). The lists are frozen for
tr22/tr23: a later migration that adds references writes its own.
"""

from __future__ import annotations

from typing import NamedTuple

import sqlalchemy as sa


class Reference(NamedTuple):
    child: str
    column: str
    parent: str
    old_name: str  # the single-column constraint tr23 replaces
    ondelete: str | None = None

    @property
    def new_name(self) -> str:
        return f"fk_{self.child}_{self.column}_tenant"

    @property
    def label(self) -> str:
        return f"{self.child}.{self.column} -> {self.parent}"


_CANONICAL = (
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

REFERENCES: tuple[Reference, ...] = tuple(
    Reference(table, "source_record_id", "source_records", f"fk_{table}_source_record_id_source_records")
    for table in _CANONICAL
) + (
    Reference(
        "staged_source_records",
        "ingestion_run_id",
        "ingestion_runs",
        "fk_staged_source_records_ingestion_run_id_ingestion_runs",
    ),
    Reference(
        "data_quality_issues",
        "ingestion_run_id",
        "ingestion_runs",
        "fk_data_quality_issues_ingestion_run_id_ingestion_runs",
    ),
    Reference(
        "data_quality_issues",
        "staged_source_record_id",
        "staged_source_records",
        "fk_data_quality_issues_staged_source_record_id_staged_s_64eb",
    ),
    Reference(
        "normalization_issues",
        "normalization_run_id",
        "normalization_runs",
        "fk_normalization_issues_normalization_run_id_normalization_runs",
    ),
    Reference(
        "normalization_issues",
        "staged_source_record_id",
        "staged_source_records",
        "fk_normalization_issues_staged_source_record_id_staged__d045",
    ),
    Reference(
        "source_canonical_links",
        "normalization_run_id",
        "normalization_runs",
        "fk_source_canonical_links_normalization_run_id_normaliz_f8ff",
    ),
    Reference(
        "source_canonical_links",
        "staged_source_record_id",
        "staged_source_records",
        "fk_source_canonical_links_staged_source_record_id_stage_bd30",
    ),
    Reference(
        "canonical_relationships",
        "normalization_run_id",
        "normalization_runs",
        "fk_canonical_relationships_normalization_run_id_normali_f41c",
    ),
    Reference(
        "canonical_relationships",
        "source_link_id",
        "source_canonical_links",
        "fk_canonical_relationships_source_link_id_source_canoni_2c97",
    ),
    Reference(
        "connector_source_records",
        "connector_run_id",
        "connector_runs",
        "fk_connector_source_records_connector_run_id_connector_runs",
    ),
    Reference(
        "connector_reconciliations",
        "connector_run_id",
        "connector_runs",
        "fk_connector_reconciliations_connector_run_id_connector_runs",
    ),
    Reference(
        "report_obligations",
        "assessment_id",
        "complaint_market_assessments",
        "fk_report_obligations_assessment_id_complaint_market_as_d49a",
    ),
    Reference(
        "report_obligations", "parent_id", "report_obligations", "fk_report_obligations_parent_id_report_obligations"
    ),
    Reference("report_snapshots", "obligation_id", "report_obligations", "fk_report_snapshots_obligation", "CASCADE"),
    Reference(
        "report_submissions", "obligation_id", "report_obligations", "fk_report_submissions_obligation", "CASCADE"
    ),
    Reference(
        "report_submissions", "snapshot_id", "report_snapshots", "fk_report_submissions_snapshot_id_report_snapshots"
    ),
    Reference("report_evidence", "submission_id", "report_submissions", "fk_report_evidence_submission", "CASCADE"),
    Reference("first_contact_checks", "intake_event_id", "intake_events", "fk_first_contact_checks_event", "CASCADE"),
    Reference(
        "communication_entries", "party_id", "external_parties", "fk_communication_entries_party_id_external_parties"
    ),
    Reference(
        "communication_entries",
        "in_reply_to",
        "communication_entries",
        "fk_communication_entries_in_reply_to_communication_entries",
    ),
    Reference("signing_grants", "user_id", "auth_users", "fk_signing_grants_user_id_auth_users"),
    Reference("user_additional_roles", "user_id", "auth_users", "fk_user_additional_roles_user_id_auth_users"),
    Reference(
        "provisioning_job_steps",
        "provisioning_job_id",
        "provisioning_jobs",
        "fk_provisioning_job_steps_provisioning_job_id_provisioning_jobs",
    ),
    Reference("cell_heartbeats", "cell_id", "cells", "fk_cell_heartbeats_cell_id_cells"),
)

# A step of a provisioning job may have no organization yet (tenant_id is nullable there), and MATCH SIMPLE does not
# check a composite reference with an empty column: the single-column reference stays beside the composite one.
KEEP_SINGLE_COLUMN = frozenset({"fk_provisioning_job_steps_provisioning_job_id_provisioning_jobs"})

# Targets that need UNIQUE (tenant_id, id) for a composite reference (the others already have it).
NEW_TARGET_UNIQUES = (
    "ingestion_runs",
    "staged_source_records",
    "normalization_runs",
    "source_canonical_links",
    "connector_runs",
    "complaint_market_assessments",
    "report_obligations",
    "report_snapshots",
    "report_submissions",
    "external_parties",
    "communication_entries",
    "provisioning_jobs",
)

# PV-1 F1: tables whose product version must be a version of their own product.
PRODUCT_VERSION_TABLES = (
    "complaints",
    "risks",
    "requirements",
    "signals",
    "intake_events",
    "decisions",
    "investigation_briefs",
    "assurance_results",
    "ai_interactions",
)
PRODUCT_VERSION_UNIQUE = "uq_product_versions_tenant_product_id"


def unique_name(table: str) -> str:
    return f"uq_{table}_tenant_id_id"


def version_fk_name(table: str) -> str:
    return f"fk_{table}_version_of_product"


def version_check_name(table: str) -> str:
    return f"ck_{table}_version_needs_product"


def _queries() -> list[tuple[str, str]]:
    queries = [
        (
            f"{ref.label}: another organization's row",
            f"SELECT count(*) FROM public.{ref.child} c JOIN public.{ref.parent} p ON p.id = c.{ref.column} "
            "WHERE c.tenant_id <> p.tenant_id",
        )
        for ref in REFERENCES
    ]
    for table in PRODUCT_VERSION_TABLES:
        queries += [
            (
                f"{table}: a version without a product",
                f"SELECT count(*) FROM public.{table} WHERE product_version_id IS NOT NULL AND product_id IS NULL",
            ),
            (
                f"{table}: a version of another product or organization, or none",
                f"SELECT count(*) FROM public.{table} r LEFT JOIN public.product_versions v "
                "ON v.id = r.product_version_id AND v.tenant_id = r.tenant_id AND v.product_id = r.product_id "
                "WHERE r.product_version_id IS NOT NULL AND r.product_id IS NOT NULL AND v.id IS NULL",
            ),
        ]
    return queries


def tables_read() -> list[str]:
    names = {ref.child for ref in REFERENCES} | {ref.parent for ref in REFERENCES}
    return sorted(names | set(PRODUCT_VERSION_TABLES) | {"product_versions"})


def violation_counts(connection) -> list[tuple[str, int]]:
    """Every rule with the number of rows that break it. The caller sees every row (owner without forced row-level
    security, or system scope)."""
    return [(label, int(connection.execute(sa.text(sql)).scalar() or 0)) for label, sql in _queries()]


def refusal(counts: list[tuple[str, int]]) -> str | None:
    broken = [(label, count) for label, count in counts if count]
    if not broken:
        return None
    lines = "\n".join(f"  {count:>8}  {label}" for label, count in broken)
    return (
        f"DB-1 pre-check: {sum(c for _, c in broken)} row(s) reference a row of another organization, or a product "
        f"version that is not a version of their product. Repair them, then upgrade again "
        f"(scripts/check_tenant_references.py lists the same counts):\n{lines}"
    )
