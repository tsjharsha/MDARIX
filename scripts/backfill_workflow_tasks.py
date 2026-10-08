"""Create workflow tasks for work that existed before tasks did (open cases, decisions awaiting approval, supplier
requests awaiting a reply), for every organization or one.

    python scripts/backfill_workflow_tasks.py                      # dry run: what would be created
    python scripts/backfill_workflow_tasks.py --apply              # create them
    python scripts/backfill_workflow_tasks.py --tenant <id|key>    # one organization only

Organizations on the shared plane are read from the control database, each bound to its own organization (row-level
security); organizations with a dedicated database are read from it the way
scripts/add_workflow_tables_to_legacy_planes.py connects (the ``<secret>_OWNER`` URL when set). A database without the
workflow tables is reported and skipped (run migrations, or add_workflow_tables_to_legacy_planes.py, first). The work
itself is backend/app/workflow/backfill.py; it is idempotent, so running it again creates nothing new. One
transaction per organization.
"""

from __future__ import annotations

import argparse
import os
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sqlalchemy import create_engine, inspect  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from backend.app.db.data_plane import SHARED_CONTROL_DATA_PLANE, _secret_url  # noqa: E402
from backend.app.db.models.customer_lifecycle import TenantDataPlane  # noqa: E402
from backend.app.db.models.foundation import Tenant  # noqa: E402
from backend.app.db.session import SessionLocal, engine as control_engine  # noqa: E402
from backend.app.db.tenant_scope import bind_system, bind_tenant  # noqa: E402
from backend.app.db.tls import connect_args  # noqa: E402
from backend.app.workflow.backfill import backfill_tenant  # noqa: E402

WORKFLOW_TABLES = ("workflow_tasks", "workflow_task_events")
SKIPPED_TENANT_STATUSES = ("ARCHIVED", "PURGING")


def _planes(only: str | None) -> list[tuple[uuid.UUID, str, str, str]]:
    """(tenant id, tenant key, plane's database_ref, connection_secret_ref) of every organization to visit."""
    db = SessionLocal()
    try:
        bind_system(db, "backfill workflow tasks: list organizations and their data planes")
        query = (
            db.query(Tenant.id, Tenant.tenant_key, TenantDataPlane.database_ref, TenantDataPlane.connection_secret_ref)
            .join(TenantDataPlane, TenantDataPlane.tenant_id == Tenant.id)
            .filter(TenantDataPlane.status == "ACTIVE", Tenant.status.notin_(SKIPPED_TENANT_STATUSES))
        )
        if only:
            key = None
            try:
                key = uuid.UUID(only)
            except ValueError:
                pass
            query = query.filter(Tenant.id == key) if key else query.filter(Tenant.tenant_key == only)
        return [tuple(row) for row in query.order_by(Tenant.tenant_key).all()]
    finally:
        db.close()


def _has_tables(bind) -> bool:
    tables = set(inspect(bind).get_table_names())
    return all(table in tables for table in WORKFLOW_TABLES)


def _run(data: Session, control: Session, tenant_id, apply: bool) -> dict:
    try:
        result = backfill_tenant(data, control, tenant_id, apply=apply)
        if apply:
            data.commit()
        else:
            data.rollback()
        return result
    except Exception:
        data.rollback()
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--apply", action="store_true", help="create the tasks (default: dry run)")
    parser.add_argument("--tenant", help="only this organization (its id or tenant key)")
    args = parser.parse_args()
    planes = _planes(args.tenant)
    if not planes:
        print("No matching organization with an active data plane.")
        return 1 if args.tenant else 0
    shared_ready = _has_tables(control_engine)
    failures = 0
    for tenant_id, tenant_key, database_ref, secret_ref in planes:
        label = f"{tenant_key} ({tenant_id})"
        try:
            control = SessionLocal()
            try:
                bind_tenant(control, tenant_id)
                if secret_ref == SHARED_CONTROL_DATA_PLANE:
                    if not shared_ready:
                        failures += 1
                        print(f"FAILED    {label}: the control database lacks the workflow tables; migrate it first")
                        continue
                    result = _run(control, control, tenant_id, args.apply)
                else:
                    url = os.getenv(f"{secret_ref}_OWNER", "").strip() or _secret_url(secret_ref)
                    plane_engine = create_engine(url, connect_args=connect_args())
                    try:
                        if not _has_tables(plane_engine):
                            failures += 1
                            print(
                                f"FAILED    {label}: {database_ref} lacks the workflow tables; run "
                                "scripts/migrate_data_planes.py or scripts/add_workflow_tables_to_legacy_planes.py"
                            )
                            continue
                        data = Session(bind=plane_engine, autoflush=False, future=True)
                        try:
                            bind_tenant(data, tenant_id)
                            result = _run(data, control, tenant_id, args.apply)
                        finally:
                            data.close()
                    finally:
                        plane_engine.dispose()
            finally:
                control.close()
        except Exception as exc:  # report every organization, then fail
            failures += 1
            print(f"FAILED    {label}: {type(exc).__name__}: {exc}")
            continue
        counts = ", ".join(
            f"{name} {result[name]}" for name in ("INVESTIGATION", "DECISION_APPROVAL", "EVIDENCE_REQUEST")
        )
        state = "DONE     " if args.apply else "PENDING  "
        print(
            f"{state} {label}: {counts}; {result['skipped']} already had a task" + ("" if args.apply else " (dry run)")
        )
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
