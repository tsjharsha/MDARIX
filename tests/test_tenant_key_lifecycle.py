import pytest

from security.tenant_keys import TenantKeyRegistry


def test_tenant_key_create_rotate_and_retire():
    registry = TenantKeyRegistry()
    first = registry.create("tenant-a")
    second = registry.rotate("tenant-a")
    assert first.version == 1
    assert second.version == 2
    assert registry.active("tenant-a") == second
    registry.authorize(second.key_ref, "tenant-a")
    with pytest.raises(PermissionError):
        registry.authorize(first.key_ref, "tenant-a")


def test_key_reference_cannot_cross_tenants():
    registry = TenantKeyRegistry()
    key = registry.create("tenant-a")
    with pytest.raises(PermissionError):
        registry.authorize(key.key_ref, "tenant-b")


def test_duplicate_active_key_and_invalid_tenant_are_rejected():
    registry = TenantKeyRegistry()
    registry.create("tenant-a")
    with pytest.raises(ValueError):
        registry.create("tenant-a")
    with pytest.raises(ValueError):
        registry.create("tenant/other")
