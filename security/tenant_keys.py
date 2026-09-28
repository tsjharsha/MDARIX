"""Tenant-bound encryption-key lifecycle contract.

The module stores references and metadata only. Secret material belongs in a
KMS/Vault adapter and is never returned by this contract.
"""
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from secrets import token_urlsafe


@dataclass(frozen=True)
class TenantKeyVersion:
    tenant_id: str
    key_ref: str
    version: int
    status: str
    created_at: str
    retired_at: str | None = None


class TenantKeyRegistry:
    def __init__(self):
        self._keys: dict[str, list[TenantKeyVersion]] = {}

    def create(self, tenant_id: str) -> TenantKeyVersion:
        self._require_tenant(tenant_id)
        if tenant_id in self._keys and any(item.status == "ACTIVE" for item in self._keys[tenant_id]):
            raise ValueError("active tenant key already exists")
        return self._issue(tenant_id, 1)

    def rotate(self, tenant_id: str) -> TenantKeyVersion:
        self._require_tenant(tenant_id)
        current = self.active(tenant_id)
        now = datetime.now(timezone.utc).isoformat()
        self._keys[tenant_id] = [replace(item, status="RETIRED", retired_at=now) if item.status == "ACTIVE" else item for item in self._keys[tenant_id]]
        return self._issue(tenant_id, current.version + 1)

    def active(self, tenant_id: str) -> TenantKeyVersion:
        self._require_tenant(tenant_id)
        for item in reversed(self._keys.get(tenant_id, [])):
            if item.status == "ACTIVE":
                return item
        raise KeyError("no active tenant key")

    def authorize(self, key_ref: str, tenant_id: str) -> None:
        if not key_ref.startswith(f"tenant/{tenant_id}/"):
            raise PermissionError("key reference is outside the authenticated tenant")
        if key_ref != self.active(tenant_id).key_ref:
            raise PermissionError("key reference is not the active tenant key")

    def _issue(self, tenant_id: str, version: int) -> TenantKeyVersion:
        item = TenantKeyVersion(tenant_id, f"tenant/{tenant_id}/encryption/{token_urlsafe(18)}", version, "ACTIVE", datetime.now(timezone.utc).isoformat())
        self._keys.setdefault(tenant_id, []).append(item)
        return item

    @staticmethod
    def _require_tenant(tenant_id: str) -> None:
        if not tenant_id or "/" in tenant_id or ".." in tenant_id:
            raise ValueError("invalid tenant identifier")
