import pytest

from security.encryption_policy import create_envelope_metadata, validate_encryption_policy


def test_envelope_metadata_is_tenant_bound_and_versioned():
    item = create_envelope_metadata("tenant-a", "tenant/tenant-a/encryption/key-1", 2)
    assert item.algorithm == "AES-256-GCM"
    assert item.key_version == 2
    with pytest.raises(ValueError):
        create_envelope_metadata("tenant-a", "tenant/tenant-b/encryption/key-1", 1)


def test_encryption_policy_requires_all_protection_controls():
    result = validate_encryption_policy({"tls_application": True, "tls_database": True})
    assert result["valid"] is False
    assert "backup_encryption" in result["missing"]
    assert (
        validate_encryption_policy(
            {
                key: True
                for key in (
                    "tls_application",
                    "tls_database",
                    "database_at_rest",
                    "backup_encryption",
                    "object_storage_encryption",
                    "key_rotation",
                )
            }
        )["valid"]
        is True
    )
