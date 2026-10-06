"""Archive expired audit events, one compressed file per organization.

This deliberately does not delete audit rows. It produces a compressed, tenant-scoped archive that can be inspected
or copied to approved storage. "Expired" is the rule the administrator's retention status uses
(``GET /api/v1/admin/retention-status``): ``retention_until`` before now. The database fills ``retention_until``
(seven years from the event, migration md23) when the application leaves it empty, so every event has one.
Runs in system scope with the database owner's credentials: row-level security would otherwise hide every event.

    python scripts/archive_expired_audit_events.py [--archive-dir DIR] [--tenant TENANT_ID ...]
"""

from __future__ import annotations

import argparse
import json
import sys
import uuid
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.app.db.models.foundation import AuditEvent  # noqa: E402
from backend.app.db.session import SessionLocal  # noqa: E402
from backend.app.db.tenant_scope import bind_system  # noqa: E402
from backend.app.retention import archive_expired_audit_events  # noqa: E402


def expired_events(db, now: datetime, tenant_ids=None) -> dict[str, list[AuditEvent]]:
    """Expired events grouped by organization, oldest first (the same predicate as the retention status)."""
    query = db.query(AuditEvent).filter(AuditEvent.retention_until < now)
    if tenant_ids:
        query = query.filter(AuditEvent.tenant_id.in_([uuid.UUID(str(value)) for value in tenant_ids]))
    grouped: dict[str, list[AuditEvent]] = defaultdict(list)
    for event in query.order_by(AuditEvent.tenant_id, AuditEvent.created_at).all():
        grouped[str(event.tenant_id)].append(event)
    return grouped


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--archive-dir", default="artifacts/audit-archives")
    parser.add_argument("--tenant", action="append", default=[], metavar="TENANT_ID", help="limit to this organization")
    args = parser.parse_args(argv)
    now = datetime.now(timezone.utc)
    db = SessionLocal()
    try:
        bind_system(db, "archive expired audit events")
        grouped = expired_events(db, now, args.tenant or None)
        results = [
            archive_expired_audit_events(items, archive_dir=Path(args.archive_dir), now=now)
            for items in grouped.values()
        ]
    finally:
        db.close()
    summary = {
        "status": "PASS",
        "tenants_with_expired_events": len(results),
        "archived": sum(item["archived"] for item in results),
        "archives": {item["tenant_id"]: item["archive_path"] for item in results if item["status"] == "ARCHIVED"},
        "archive_dir": args.archive_dir,
        "checked_at": now.isoformat(),
    }
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
