"""Archive expired audit events for local MVP operations.

This deliberately does not delete audit rows. It produces a compressed,
tenant-scoped archive that can be inspected or copied to approved storage.
"""
from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.app.db.models.foundation import AuditEvent
from backend.app.db.session import SessionLocal
from backend.app.retention import archive_expired_audit_events


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--archive-dir", default="artifacts/audit-archives")
    args = parser.parse_args()
    db = SessionLocal()
    try:
        events = db.query(AuditEvent).all()
        grouped = defaultdict(list)
        for event in events:
            grouped[str(event.tenant_id)].append(event)
        results = [archive_expired_audit_events(items, archive_dir=Path(args.archive_dir)) for items in grouped.values()]
        archived = sum(item["archived"] for item in results)
        print({"status": "PASS", "tenants_checked": len(results), "archived": archived, "archive_dir": args.archive_dir})
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
