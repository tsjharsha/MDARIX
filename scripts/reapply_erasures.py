"""Re-apply personal-data erasures and organization purges after a database restore (backend/app/tenant_purge.py).

A backup taken before an erasure still holds the erased data. Every erasure and purge is written to ``erasure_log``,
so after a restore this script repeats each one whose subject is identifiable again: ``erase_person`` for an account
(PERSON_ERASED) and the full purge for an organization (TENANT_PURGED) whose rows, accounts or files are back. Each
re-applied log row gets ``reapplied_at``; the re-application is itself logged and audited. Subjects under a legal
hold are reported and left alone. Run with the database owner's credentials (system scope).

The restored database only knows erasures made before its backup was taken. Copy the newer ones in first, from the
database being replaced (point-in-time recovery leaves it running) or, if it is lost, from the newest backup:

    # against the newest copy (POSTGRES_HOST/POSTGRES_DB pointing at it)
    python scripts/reapply_erasures.py --export-log erasure_log.jsonl
    # against the restored database
    python scripts/reapply_erasures.py --import-log erasure_log.jsonl --dry-run
    python scripts/reapply_erasures.py --import-log erasure_log.jsonl

Exits 1 when anything failed or (with --dry-run) when something would be re-applied.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.app.db.session import SessionLocal  # noqa: E402
from backend.app.tenant_purge import export_erasure_log, import_erasure_log, reapply_erasures  # noqa: E402

ACTOR = "system:reapply-erasures"


def main(argv: list[str] | None = None, *, storage=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dry-run", action="store_true", help="list what would be re-applied; change nothing")
    parser.add_argument("--export-log", metavar="FILE", help="write this database's erasure log (JSON Lines) and stop")
    parser.add_argument(
        "--import-log", metavar="FILE", help="first add the erasure-log rows from FILE that are missing"
    )
    parser.add_argument("--tenant", action="append", default=[], metavar="TENANT_ID", help="limit to this organization")
    args = parser.parse_args(argv)
    db = SessionLocal()
    try:
        if args.export_log:
            rows = export_erasure_log(db)
            with open(args.export_log, "w", encoding="utf-8") as handle:
                for row in rows:
                    handle.write(json.dumps(row) + "\n")
            print(json.dumps({"exported": len(rows), "file": args.export_log}))
            return 0
        imported = 0
        if args.import_log:
            with open(args.import_log, encoding="utf-8") as handle:
                rows = [json.loads(line) for line in handle if line.strip()]
            # A dry run sees the imported rows in its own transaction and then rolls them back.
            imported = import_erasure_log(db, rows, commit=not args.dry_run)
        summary = reapply_erasures(db, ACTOR, dry_run=args.dry_run, tenant_ids=args.tenant or None, storage=storage)
        if args.dry_run:
            db.rollback()
    finally:
        db.close()
    summary["imported_log_rows"] = imported
    print(json.dumps(summary, indent=2, default=str))
    if summary["failed"]:
        return 1
    return 1 if args.dry_run and summary["pending"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
