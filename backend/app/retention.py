"""Fail-closed retention and disposition decision rules."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import gzip
import json
from pathlib import Path


@dataclass(frozen=True)
class DispositionDecision:
    status: str
    reason: str
    audit_required: bool = True


def evaluate_disposition(
    *,
    tenant_id: str,
    record_tenant_id: str | None,
    retention_expired: bool,
    active_hold: bool,
    authorized: bool,
    now: datetime | None = None,
) -> DispositionDecision:
    if not tenant_id or record_tenant_id != tenant_id:
        return DispositionDecision("DENIED", "TENANT_CONTEXT_MISMATCH")
    if not authorized:
        return DispositionDecision("DENIED", "AUTHORIZATION_REQUIRED")
    if not retention_expired:
        return DispositionDecision("NOT_ELIGIBLE", "RETENTION_PERIOD_NOT_REACHED")
    if active_hold:
        return DispositionDecision("BLOCKED", "ACTIVE_HOLD")
    return DispositionDecision("ELIGIBLE_FOR_REVIEW", "RETENTION_PERIOD_REACHED")


def record_disposition_result(decision: DispositionDecision, *, execution_succeeded: bool) -> DispositionDecision:
    if decision.status != "ELIGIBLE_FOR_REVIEW":
        return decision
    return DispositionDecision(
        "DISPOSED" if execution_succeeded else "FAILED",
        "CONTROLLED_DISPOSITION_COMPLETED" if execution_succeeded else "CONTROLLED_DISPOSITION_FAILED",
    )


def archive_expired_audit_events(events, *, archive_dir: str | Path, now: datetime | None = None) -> dict:
    """Write expired audit events to an append-only compressed archive.

    Events are never deleted here. The caller must separately apply an approved
    disposition policy; this function provides durable operational archival and
    a deterministic manifest for monitoring and restore checks.
    """
    checked_at = now or datetime.now(timezone.utc)
    expired = [event for event in events if event.retention_until and event.retention_until < checked_at]
    target = Path(archive_dir)
    target.mkdir(parents=True, exist_ok=True)
    if not expired:
        return {"status": "NO_WORK", "archived": 0, "checked_at": checked_at.isoformat()}
    tenant_ids = {str(event.tenant_id) for event in expired}
    if len(tenant_ids) != 1:
        raise ValueError("ARCHIVE_REQUIRES_SINGLE_TENANT_SCOPE")
    tenant_id = next(iter(tenant_ids))
    path = target / f"audit-{tenant_id}-{checked_at.strftime('%Y%m%dT%H%M%SZ')}.jsonl.gz"
    with gzip.open(path, "wt", encoding="utf-8") as stream:
        for event in expired:
            stream.write(
                json.dumps(
                    {
                        "id": str(event.id),
                        "tenant_id": str(event.tenant_id),
                        "actor_ref": event.actor_ref,
                        "action": event.action,
                        "entity_type": event.entity_type,
                        "entity_id": str(event.entity_id) if event.entity_id else None,
                        "details": event.details,
                        "source_ip": event.source_ip,
                        "user_agent": event.user_agent,
                        "reason": event.reason,
                        "old_values": event.old_values,
                        "new_values": event.new_values,
                        "retention_until": event.retention_until.isoformat() if event.retention_until else None,
                        "created_at": event.created_at.isoformat() if event.created_at else None,
                    }
                )
                + "\n"
            )
    return {
        "status": "ARCHIVED",
        "archived": len(expired),
        "tenant_id": tenant_id,
        "archive_path": str(path),
        "checked_at": checked_at.isoformat(),
    }
