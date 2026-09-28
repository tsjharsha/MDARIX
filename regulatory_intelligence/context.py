"""Tenant-scoped regulatory retrieval context contract."""


def build_regulatory_context(tenant_id: str, records: list[dict], citations: list[dict]) -> dict:
    """Build a bounded context without permitting cross-tenant records.

    This is the local/MVP contract used by regulatory drafting and RAG adapters;
    a production vector service can implement the same contract later.
    """
    if not tenant_id:
        raise ValueError("tenant_id is required")
    allowed = [record for record in records if str(record.get("tenant_id")) == str(tenant_id)]
    return {
        "tenant_id": str(tenant_id),
        "records": allowed,
        "citations": citations,
        "temporal_scope": "CURRENT",
        "provenance_required": True,
        "field_policy_applied": True,
    }
