"""Tenant-safe cache and vector namespace primitives for AI services.

These helpers are backend-neutral so Redis, a hosted vector store, or an
in-process test double must use the same tenant-bound identifiers.
"""

import hashlib


def tenant_cache_key(tenant_id: str, prompt: str, context_hash: str = "") -> str:
    if not tenant_id:
        raise ValueError("tenant_id is required")
    digest = hashlib.sha256(f"{prompt}|{context_hash}".encode("utf-8")).hexdigest()
    return f"mdarix:ai:{tenant_id}:prompt:{digest}"


def tenant_vector_namespace(tenant_id: str, index_name: str = "regulatory") -> str:
    if not tenant_id:
        raise ValueError("tenant_id is required")
    if not index_name or ":" in index_name:
        raise ValueError("invalid index name")
    return f"mdarix:{tenant_id}:vectors:{index_name}"


def assert_tenant_key(key: str, tenant_id: str) -> None:
    expected = f"mdarix:ai:{tenant_id}:"
    if not key.startswith(expected):
        raise PermissionError("AI cache key is outside the authenticated tenant")


def assert_tenant_namespace(namespace: str, tenant_id: str) -> None:
    expected = f"mdarix:{tenant_id}:vectors:"
    if not namespace.startswith(expected):
        raise PermissionError("vector namespace is outside the authenticated tenant")
