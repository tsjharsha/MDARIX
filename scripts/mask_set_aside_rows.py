"""Mask the set-aside import rows stored before 0.10.62.

    python scripts/mask_set_aside_rows.py            # count what would change, per organization; change nothing
    python scripts/mask_set_aside_rows.py --apply    # mask them

From 0.10.56 the rows an import sets aside are stored for correction (import_quarantine_rows). Until 0.10.62 a value was
masked only when the import's second check flagged it, so names, phone numbers, ages and hospitals that masking finds
("Mr. John Smith", "98450 12345", "67-year-old male at Riverside Hospital") could be stored as sent, although the
set-aside view says personal details are kept only as placeholders (J7). This applies today's masking
(backend/app/trial/imports.py stored_value) to every stored row, open or re-processed, in every organization of the
database it connects to, and leaves out of each stored reason the words a check quoted. Identifiers stay as they are.

Running it twice changes nothing the second time (masked text masks to itself). Each organization is committed on its
own with an audit event (SET_ASIDE_ROWS_MASKED) that counts the rows changed and never holds their values. Run it once
per database that holds tenant data (the shared trial plane, and a pilot's own data plane if it has one), at deploy,
with the owner's explicit approval.
"""

from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sqlalchemy.orm import Session  # noqa: E402

from backend.app.db.session import SessionLocal  # noqa: E402


def masked_row(row) -> tuple[dict, list[str], bool]:
    """(stored values, stored reasons, whether either changed) for one stored row."""
    from backend.app import import_quarantine
    from backend.app.trial.imports import stored_value

    values = import_quarantine.stored_values(dict(row.row or {}), stored_value)
    problems = import_quarantine.stored_problems(list(row.problems or []))
    return values, problems, values != (row.row or {}) or problems != list(row.problems or [])


def mask_rows(db: Session, apply: bool, tenant_ids=None) -> dict[str, dict]:
    """{organization: {"rows": stored rows, "changed": rows masked}} for every organization with set-aside rows (or
    only those in ``tenant_ids``)."""
    from backend.app.db.models.foundation import Tenant
    from backend.app.db.models.ingestion import ImportQuarantineRow
    from backend.app.db.tenant_scope import bind_system
    from backend.app.enterprise_audit import make_audit_event

    bind_system(db, "mask the stored set-aside import rows (0.10.62)")
    names = dict(db.query(Tenant.id, Tenant.name).all())
    query = db.query(ImportQuarantineRow).order_by(ImportQuarantineRow.tenant_id, ImportQuarantineRow.created_at)
    if tenant_ids is not None:
        query = query.filter(ImportQuarantineRow.tenant_id.in_(list(tenant_ids)))
    by_tenant: dict = defaultdict(list)
    for row in query:
        by_tenant[row.tenant_id].append(row)
    summary: dict[str, dict] = {}
    for tenant_id, rows in by_tenant.items():
        changed = 0
        for row in rows:
            values, problems, differs = masked_row(row)
            if differs:
                changed += 1
                if apply:
                    row.row, row.problems = values, problems
        label = f"{names.get(tenant_id) or 'Unknown organization'} ({tenant_id})"
        summary[label] = {"rows": len(rows), "changed": changed}
        if apply and changed:
            db.add(
                make_audit_event(
                    tenant_id=tenant_id,
                    actor_ref="system:mask_set_aside_rows",
                    action="SET_ASIDE_ROWS_MASKED",
                    entity_type="ImportQuarantineRow",
                    entity_id=str(tenant_id),
                    details={"rows": len(rows), "masked": changed, "release": "0.10.62"},
                )
            )
            db.commit()
            bind_system(db, "mask the stored set-aside import rows (0.10.62)")
    if not apply:
        db.rollback()
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--apply", action="store_true", help="mask the rows (without it, only count them)")
    args = parser.parse_args(argv)
    with SessionLocal() as db:
        summary = mask_rows(db, args.apply)
    verb = "masked" if args.apply else "to mask"
    for organization, counts in summary.items():
        print(f"{organization}: {counts['rows']} set-aside rows, {counts['changed']} {verb}")
    total = sum(counts["changed"] for counts in summary.values())
    print(f"{len(summary)} organizations, {total} rows {verb}." + ("" if args.apply else " Nothing was changed."))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
