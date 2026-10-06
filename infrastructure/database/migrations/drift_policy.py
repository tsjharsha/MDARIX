"""Policy used by Alembic autogeneration and the CI schema-drift gate.

Most database objects are represented by SQLAlchemy metadata and must be compared by
``alembic check``.  A small set is intentionally migration-owned because it depends on
PostgreSQL features that are not part of the ORM lifecycle: the protected RLS secret
table, HNSW indexes, and operational indexes added by hardening migrations.

Keep this allowlist exact.  Unknown database-only objects remain visible to Alembic and
therefore fail the CI drift gate.
"""

MANAGED_SCHEMAS = frozenset({None, "public", "md_master"})

MIGRATION_OWNED_TABLES = frozenset({"mdarix_rls_secret"})

MIGRATION_OWNED_INDEXES = frozenset(
    {
        "ix_ai_interactions_tenant_user_created",
        "ix_audit_events_tenant_created",
        "ix_audit_events_tenant_hash",
        "uq_audit_events_tenant_chain",
        "ix_auth_sessions_tenant_expires",
        "ix_capas_tenant_product",
        "ix_client_error_reports_created",
        "ix_customers_directory",
        "ix_erasure_log_tenant_performed",
        "ix_event_outbox_claimed_at",
        "ix_evidence_attachments_tenant_request",
        "ix_chunk_embeddings_bge384_hnsw",
        "ix_chunk_embeddings_hash32_hnsw",
        "ix_evidence_embeddings_embedding_hnsw",
        "ix_inbound_provider_mapping_tenant",
        "ix_onboarding_requests_status",
        "ix_platform_incidents_status",
        "ix_provisioning_jobs_status",
        "ix_report_jobs_tenant_status",
        "ix_subscription_lifecycles_expiry",
        "ix_supplier_requests_tenant_created",
        "ix_support_problem_reports_status",
        "ix_support_problem_reports_tenant_created",
        "ix_tenant_environments_status",
        "ix_tenant_health_runs_status",
        "ix_tenants_customer_status_region",
    }
)


def include_name(name, type_, parent_names):
    """Reflect only schemas owned by MDARIX."""
    if type_ == "schema":
        return name in MANAGED_SCHEMAS
    if type_ == "table":
        return parent_names.get("schema_name") in MANAGED_SCHEMAS
    return True


def include_object(object_, name, type_, reflected, compare_to):
    """Exclude only exact, reviewed migration-owned objects from ORM comparison."""
    del object_
    if not reflected or compare_to is not None:
        return True
    if type_ == "table" and name in MIGRATION_OWNED_TABLES:
        return False
    if type_ == "index" and name in MIGRATION_OWNED_INDEXES:
        return False
    return True
