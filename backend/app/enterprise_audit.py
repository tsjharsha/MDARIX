"""Safe audit event construction using the existing AuditEvent model."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any

from backend.app.db.models.foundation import AuditEvent
from backend.app.audit_chain import audit_event_hash

SECRET_TERMS = ("password", "token", "secret", "credential", "api_key", "authorization")
def change_diff(before: dict[str, Any] | None, after: dict[str, Any] | None) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return only changed, redacted fields for a consistent audit diff."""
    old = before or {}; new = after or {}
    keys = set(old) | set(new)
    changed = {key for key in keys if old.get(key) != new.get(key)}
    return safe_details({key: old.get(key) for key in changed}), safe_details({key: new.get(key) for key in changed})
def safe_details(details: dict[str, Any] | None) -> dict[str, Any]:
    """Redact sensitive keys recursively before persisting audit evidence."""
    if not details: return {}
    def clean(value: Any) -> Any:
        if isinstance(value, dict):
            return {str(key): clean(item) for key, item in value.items() if not any(term in str(key).lower() for term in SECRET_TERMS)}
        if isinstance(value, list): return [clean(item) for item in value]
        return value
    return clean(details)

def make_audit_event(*, tenant_id, actor_ref, action: str, entity_type: str, entity_id=None, correlation_id: str | None = None, details: dict[str, Any] | None = None, created_at=None, request=None, reason: str | None = None, old_values: dict[str, Any] | None = None, new_values: dict[str, Any] | None = None, previous_hash: str | None = None) -> AuditEvent:
    now = created_at or datetime.now(timezone.utc)
    source_ip = user_agent = None
    if request is not None:
        # Only trust forwarding headers when the deployment explicitly opts in.
        # This keeps local clients and untrusted proxies from spoofing audit origin.
        if request.client:
            source_ip = request.client.host
        if str(__import__('os').environ.get('MDARIX_TRUST_PROXY_HEADERS', '')).lower() in {'1', 'true', 'yes'}:
            forwarded = request.headers.get('x-forwarded-for', '').split(',')[0].strip()
            if forwarded:
                source_ip = forwarded
        user_agent = request.headers.get("user-agent")
    payload = {"tenant_id": tenant_id, "actor_ref": actor_ref, "action": action, "entity_type": entity_type, "entity_id": entity_id, "correlation_id": correlation_id, "details": safe_details(details), "source_ip": source_ip, "user_agent": user_agent, "reason": reason, "old_values": safe_details(old_values), "new_values": safe_details(new_values), "created_at": now}
    return AuditEvent(id=None, **payload, previous_hash=previous_hash, event_hash=audit_event_hash(payload, previous_hash), retention_until=now + timedelta(days=365 * 7))
