"""Give legacy dedicated organization databases the workflow tables of migration md27.

    python scripts/add_workflow_tables_to_legacy_planes.py            # dry run: what would change
    python scripts/add_workflow_tables_to_legacy_planes.py --apply    # change them

A dedicated database built before migrations managed planes (scripts/migrate_data_planes.py reports it as LEGACY)
cannot be upgraded with Alembic, so it would lack the workflow tables the application now writes when a case is
opened or a decision recorded. This runs md27's own ``create_workflow_tables`` (the same steps, so the result is
identical) on each such database that does not have them yet, in one transaction per database. It needs md26's
business identifiers there first (scripts/add_business_ids_to_legacy_planes.py). Databases managed by migrations are
left to scripts/migrate_data_planes.py.
"""

from __future__ import annotations

import argparse
import importlib.util
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from alembic.operations import Operations  # noqa: E402
from alembic.runtime.migration import MigrationContext  # noqa: E402
from sqlalchemy import create_engine, inspect, text  # noqa: E402

from backend.app.db.data_plane import SHARED_CONTROL_DATA_PLANE, _secret_url  # noqa: E402
from backend.app.db.models.customer_lifecycle import TenantDataPlane  # noqa: E402
from backend.app.db.session import SessionLocal  # noqa: E402
from backend.app.db.tenant_scope import bind_system  # noqa: E402
from backend.app.db.tls import connect_args  # noqa: E402

VERSIONS = ROOT / "infrastructure" / "database" / "migrations" / "versions"
WORKFLOW_TABLES = ("user_additional_roles", "workflow_tasks", "workflow_task_events")
REQUIRED = ("tenants", "auth_users", "investigations", "business_id_counters")


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def state(url: str) -> tuple[bool, list[str], list[str]]:
    """(is legacy, workflow tables still missing, tables md27 needs that are absent)."""
    engine = create_engine(url, connect_args=connect_args())
    try:
        tables = set(inspect(engine).get_table_names())
        legacy, _ = _load("migrate_data_planes", ROOT / "scripts" / "migrate_data_planes.py").plane_state(url)
        missing = [table for table in WORKFLOW_TABLES if table not in tables]
        absent = [table for table in REQUIRED if table not in tables]
        return legacy == "LEGACY", missing, absent
    finally:
        engine.dispose()


def apply(url: str, md27) -> None:
    engine = create_engine(url, connect_args=connect_args())
    try:
        with engine.begin() as connection:
            # Older databases isolate by organization only (no system scope function); match their other tables.
            system_scope = bool(connection.execute(text("SELECT to_regproc('public.mdarix_system_scope')")).scalar())
            with Operations.context(MigrationContext.configure(connection)):
                md27.create_workflow_tables(system_scope)
            # The task numbering trigger calls md26's function; refuse to finish without it.
            if not connection.execute(text("SELECT to_regproc('public.mdarix_assign_business_id')")).scalar():
                raise RuntimeError("md26's numbering function is missing; run add_business_ids_to_legacy_planes.py")
    finally:
        engine.dispose()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--apply", action="store_true", help="change the databases (default: dry run)")
    args = parser.parse_args()
    md27 = _load("md27_workflow_foundation", VERSIONS / "md27_workflow_foundation.py")
    db = SessionLocal()
    try:
        bind_system(db, "add workflow tables to legacy organization databases")
        planes = (
            db.query(TenantDataPlane)
            .filter(
                TenantDataPlane.status == "ACTIVE", TenantDataPlane.connection_secret_ref != SHARED_CONTROL_DATA_PLANE
            )
            .all()
        )
    finally:
        db.close()
    failures = 0
    for plane in planes:
        label = f"{plane.database_ref} (tenant {plane.tenant_id})"
        url = os.getenv(f"{plane.connection_secret_ref}_OWNER", "").strip() or _secret_url(plane.connection_secret_ref)
        try:
            legacy, missing, absent = state(url)
            if not legacy:
                print(f"SKIP      {label}: managed by migrations (scripts/migrate_data_planes.py)")
            elif not missing:
                print(f"OK        {label}: workflow tables present")
            elif len(missing) != len(WORKFLOW_TABLES):
                failures += 1
                print(f"FAILED    {label}: only some workflow tables exist ({', '.join(missing)} missing); fix by hand")
            elif absent:
                failures += 1
                print(f"FAILED    {label}: needs {', '.join(absent)} first")
            elif not args.apply:
                print(f"PENDING   {label}: {', '.join(missing)} (dry run)")
            else:
                apply(url, md27)
                print(f"DONE      {label}: {', '.join(missing)} created")
        except Exception as exc:  # report every database, then fail
            failures += 1
            print(f"FAILED    {label}: {type(exc).__name__}: {exc}")
    if not planes:
        print("No dedicated organization databases are registered.")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
