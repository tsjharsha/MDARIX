"""Tamper-evident audit-chain helpers.

The chain is tenant-scoped and hashes canonical redacted event content. It is
complementary to database append-only protections and external WORM storage.
"""

import hashlib
import json
from typing import Any


def canonical_audit_payload(event: dict[str, Any], previous_hash: str | None = None) -> dict[str, Any]:
    return {
        "previous_hash": previous_hash,
        **{
            key: event.get(key)
            for key in (
                "tenant_id",
                "actor_ref",
                "action",
                "entity_type",
                "entity_id",
                "correlation_id",
                "details",
                "source_ip",
                "user_agent",
                "reason",
                "old_values",
                "new_values",
                "created_at",
            )
        },
    }


def audit_event_hash(event: dict[str, Any], previous_hash: str | None = None) -> str:
    payload = canonical_audit_payload(event, previous_hash)
    return hashlib.sha256(json.dumps(payload, sort_keys=True, default=str, separators=(",", ":")).encode()).hexdigest()


def verify_audit_chain(events: list[dict[str, Any]]) -> dict[str, Any]:
    previous = None
    failures = []
    for index, event in enumerate(events):
        expected = audit_event_hash(event, previous)
        if event.get("previous_hash") != previous or event.get("event_hash") != expected:
            failures.append({"index": index, "event_id": event.get("id")})
        previous = event.get("event_hash")
    return {"valid": not failures, "checked": len(events), "failures": failures, "last_hash": previous}
