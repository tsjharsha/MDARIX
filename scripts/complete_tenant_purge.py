"""Finish organization purges left PURGING: delete the stored files and dedicated-plane rows that stage two of the
purge could not, then archive the organization (backend/app/tenant_purge.py, docs/runbooks/DATA_REQUESTS.md).

A purge deletes the database rows first and commits; if the file store or a dedicated database was unavailable, the
organization stays PURGING, the audit trail records TENANT_PURGE_INCOMPLETE and operations is alerted. Fix the cause
(storage credentials, network, the plane's database), then run this with the database owner's credentials (it works
in system scope). ARCHIVED is set only when nothing of the organization is left. Organizations under a legal hold are
reported and left alone. Exits 1 while any purge is still incomplete, so a scheduled run alerts.

    python scripts/complete_tenant_purge.py --dry-run          # what is pending, files still stored, last error
    python scripts/complete_tenant_purge.py                    # finish every pending purge
    python scripts/complete_tenant_purge.py --tenant <id> ...  # only these organizations
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.app.db.session import SessionLocal  # noqa: E402
from backend.app.tenant_purge import complete_pending_purges  # noqa: E402

ACTOR = "system:complete-tenant-purge"


def main(argv: list[str] | None = None, *, storage=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dry-run", action="store_true", help="report what is pending without deleting anything")
    parser.add_argument("--tenant", action="append", default=[], metavar="TENANT_ID", help="limit to this organization")
    args = parser.parse_args(argv)
    db = SessionLocal()
    try:
        summary = complete_pending_purges(
            db, ACTOR, dry_run=args.dry_run, tenant_ids=args.tenant or None, storage=storage
        )
    finally:
        db.close()
    print(json.dumps(summary, indent=2, default=str))
    return 1 if summary["incomplete"] or summary["failed"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
