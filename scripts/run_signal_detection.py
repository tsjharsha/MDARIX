"""Run signal detection (the complaint threshold rule) now, for every organization or one.

    python scripts/run_signal_detection.py                      # dry run: what would be created or updated
    python scripts/run_signal_detection.py --apply              # create and update the signals
    python scripts/run_signal_detection.py --tenant <id|key>    # one organization only

The scheduler runs the same detection every hour (job ``signal_detection``); this script is for a first run after an
upgrade, or after a large import. Organizations on the shared plane are read from the control database, each bound
to its own organization (row-level security); organizations with a dedicated database are read from it the way
scripts/backfill_workflow_tasks.py connects (the ``<secret>_OWNER`` URL when set). A database without the signal
tables is reported and skipped (run migrations, or add_workflow_tables_to_legacy_planes.py, first). The work itself is
backend/app/signals/detection.py; it is idempotent, so running it again creates nothing new. One transaction per
organization.
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
from backend.app.db.session import SessionLocal, engine as control_engine  # noqa: E402
from backend.app.db.models.customer_lifecycle import TenantDataPlane  # noqa: E402
from backend.app.db.models.foundation import Tenant  # noqa: E402
from backend.app.db.tenant_scope import bind_system, bind_tenant  # noqa: E402
from backend.app.db.tls import connect_args  # noqa: E402
from backend.app.signals.detection import detect  # noqa: E402

SIGNAL_TABLES = ("signals", "signal_complaints", "signal_events", "investigation_signals", "signal_rules")
WORKFLOW_TABLES = ("workflow_tasks", "workflow_task_events")
SKIPPED_TENANT_STATUSES = ("ARCHIVED", "PURGING")


def _planes(only: str | None) -> list[tuple[uuid.UUID, str, str, str]]:
    """(tenant id, tenant key, plane's database_ref, connection_secret_ref) of every organization to visit."""
    db = SessionLocal()
    try:
        bind_system(db, "signal detection: list organizations and their data planes")
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
    return all(table in tables for table in (*SIGNAL_TABLES, *WORKFLOW_TABLES))


def _run(data: Session, tenant_id, apply: bool) -> dict:
    try:
        result = detect(data, tenant_id, apply=apply)
        if apply:
            data.commit()
        else:
            data.rollback()
        return result
    except Exception:
        data.rollback()
        raise


def _report(label: str, result: dict, apply: bool) -> None:
    state = "DONE     " if apply else "PENDING  "
    rule = (
        f"rule v{result['rule_version']} ({result['min_complaints']} in {result['window_days']} days"
        + ("" if result["enabled"] else ", disabled")
        + ")"
    )
    print(
        f"{state} {label}: {rule}; {len(result['created'])} new, {len(result['updated'])} updated, "
        f"{len(result['monitor_reopened'])} back from monitoring" + ("" if apply else " (dry run)")
    )
    for title in result["created"]:
        print(f"          {'created' if apply else 'would create'}: {title}")
    for business_id in result["updated"]:
        print(f"          {'updated' if apply else 'would update'}: {business_id}")
    for business_id in result["monitor_reopened"]:
        print(f"          {'back to triage' if apply else 'would go back to triage'}: {business_id}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--apply", action="store_true", help="create and update signals (default: dry run)")
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
            if secret_ref == SHARED_CONTROL_DATA_PLANE:
                if not shared_ready:
                    failures += 1
                    print(f"FAILED    {label}: the control database lacks the signal tables; migrate it first")
                    continue
                data = SessionLocal()
                try:
                    bind_tenant(data, tenant_id)
                    result = _run(data, tenant_id, args.apply)
                finally:
                    data.close()
            else:
                url = os.getenv(f"{secret_ref}_OWNER", "").strip() or _secret_url(secret_ref)
                plane_engine = create_engine(url, connect_args=connect_args())
                try:
                    if not _has_tables(plane_engine):
                        failures += 1
                        print(
                            f"FAILED    {label}: {database_ref} lacks the signal tables; run "
                            "scripts/migrate_data_planes.py or scripts/add_workflow_tables_to_legacy_planes.py"
                        )
                        continue
                    data = Session(bind=plane_engine, autoflush=False, future=True)
                    try:
                        bind_tenant(data, tenant_id)
                        result = _run(data, tenant_id, args.apply)
                    finally:
                        data.close()
                finally:
                    plane_engine.dispose()
        except Exception as exc:  # report every organization, then fail
            failures += 1
            print(f"FAILED    {label}: {type(exc).__name__}: {exc}")
            continue
        _report(label, result, args.apply)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
