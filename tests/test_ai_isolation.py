import pytest

from genai.isolation import (
    assert_tenant_key,
    assert_tenant_namespace,
    tenant_cache_key,
    tenant_vector_namespace,
)


def test_prompt_cache_keys_are_tenant_bound_and_deterministic():
    a = tenant_cache_key("tenant-a", "summarize", "ctx-1")
    b = tenant_cache_key("tenant-b", "summarize", "ctx-1")
    assert a != b
    assert tenant_cache_key("tenant-a", "summarize", "ctx-1") == a
    assert_tenant_key(a, "tenant-a")
    with pytest.raises(PermissionError):
        assert_tenant_key(a, "tenant-b")


def test_vector_namespaces_are_tenant_bound():
    namespace = tenant_vector_namespace("tenant-a", "regulatory")
    assert namespace == "mdarix:tenant-a:vectors:regulatory"
    assert_tenant_namespace(namespace, "tenant-a")
    with pytest.raises(PermissionError):
        assert_tenant_namespace(namespace, "tenant-b")

