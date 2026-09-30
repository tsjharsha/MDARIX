"""Provider-neutral encryption policy and envelope metadata for the MVP."""

from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass(frozen=True)
class EnvelopeMetadata:
    tenant_id: str
    key_ref: str
    key_version: int
    algorithm: str = "AES-256-GCM"
    created_at: str = ""


def create_envelope_metadata(tenant_id: str, key_ref: str, key_version: int) -> EnvelopeMetadata:
    if not tenant_id or not key_ref.startswith(f"tenant/{tenant_id}/"):
        raise ValueError("envelope key must be tenant-bound")
    if key_version < 1:
        raise ValueError("key_version must be positive")
    return EnvelopeMetadata(tenant_id, key_ref, key_version, created_at=datetime.now(timezone.utc).isoformat())


def validate_encryption_policy(config: dict) -> dict:
    """Validate deployment declarations without claiming infrastructure proof."""
    required = {
        "tls_application",
        "tls_database",
        "database_at_rest",
        "backup_encryption",
        "object_storage_encryption",
        "key_rotation",
    }
    missing = sorted(key for key in required if config.get(key) is not True)
    return {"valid": not missing, "missing": missing, "scope": "DECLARATION_ONLY"}
