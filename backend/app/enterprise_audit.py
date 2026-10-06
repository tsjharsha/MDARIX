"""Safe audit event construction using the existing AuditEvent model."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from backend.app.db.models.foundation import AuditEvent

SECRET_TERMS = ("password", "token", "secret", "credential", "api_key", "authorization")


def change_diff(before: dict[str, Any] | None, after: dict[str, Any] | None) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return only changed, redacted fields for a consistent audit diff."""
    old = before or {}
    new = after or {}
    keys = set(old) | set(new)
    changed = {key for key in keys if old.get(key) != new.get(key)}
    return safe_details({key: old.get(key) for key in changed}), safe_details({key: new.get(key) for key in changed})


def safe_details(details: dict[str, Any] | None) -> dict[str, Any]:
    """Redact sensitive keys recursively before persisting audit evidence."""
    if not details:
        return {}

    def clean(value: Any) -> Any:
        if isinstance(value, dict):
            return {
                str(key): clean(item)
                for key, item in value.items()
                if not any(term in str(key).lower() for term in SECRET_TERMS)
            }
        if isinstance(value, list):
            return [clean(item) for item in value]
        return value

    return clean(details)


AUDIT_RETENTION_YEARS = 7


def retention_until(created_at: datetime) -> datetime:
    """Seven calendar years after the event, the same date the database trigger sets when none is given (md23:
    ``created_at + interval '7 years'``; 29 February becomes 28 February)."""
    try:
        return created_at.replace(year=created_at.year + AUDIT_RETENTION_YEARS)
    except ValueError:
        return created_at.replace(year=created_at.year + AUDIT_RETENTION_YEARS, day=28)


def make_audit_event(
    *,
    tenant_id,
    actor_ref,
    action: str,
    entity_type: str,
    entity_id=None,
    correlation_id: str | None = None,
    details: dict[str, Any] | None = None,
    created_at=None,
    request=None,
    reason: str | None = None,
    old_values: dict[str, Any] | None = None,
    new_values: dict[str, Any] | None = None,
) -> AuditEvent:
    now = created_at or datetime.now(timezone.utc)
    source_ip = user_agent = None
    if request is not None:
        from backend.app.client_ip import client_ip

        # The address our own proxy saw (MDARIX_TRUSTED_PROXY_HOPS); client-written forwarding entries are ignored.
        source_ip = client_ip(request)
        # Cut to the audit_events.user_agent column (512): an over-long header must never fail the audited action.
        user_agent = (request.headers.get("user-agent") or "")[:512] or None
    payload = {
        "tenant_id": tenant_id,
        "actor_ref": actor_ref,
        "action": action,
        "entity_type": entity_type,
        "entity_id": entity_id,
        "correlation_id": correlation_id,
        "details": safe_details(details),
        "source_ip": source_ip,
        "user_agent": user_agent,
        "reason": reason,
        "old_values": safe_details(old_values),
        "new_values": safe_details(new_values),
        "created_at": now,
    }
    # The database chains the event (chain_seq, previous_hash, event_hash) when it is inserted (migration md18).
    return AuditEvent(id=None, **payload, retention_until=retention_until(now))
