"""Give legacy dedicated organization databases the business identifiers of migration md26.

    python scripts/add_business_ids_to_legacy_planes.py            # dry run: what would change
    python scripts/add_business_ids_to_legacy_planes.py --apply    # change them

A dedicated database built before migrations managed planes (scripts/migrate_data_planes.py reports it as LEGACY)
cannot be upgraded with Alembic, so it would lack the ``business_id`` columns the application now reads. This runs
md26's own steps (the same functions, so the result is identical) on each such database: the counter table and the
assigning function, then every md26 object table that exists there and has no ``business_id`` yet. Each database
changes in one transaction. Databases managed by migrations are left to scripts/migrate_data_planes.py.
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
from infrastructure.database.migrations.business_ids import COUNTER_TABLE, OBJECTS  # noqa: E402

MIGRATION = ROOT / "infrastructure" / "database" / "migrations" / "versions" / "md26_business_ids.py"
REJECT_FUNCTION = (
    "CREATE OR REPLACE FUNCTION public.mdarix_reject_immutable_identifier() RETURNS trigger "
    "LANGUAGE plpgsql AS $fn$ BEGIN RAISE EXCEPTION 'IMMUTABLE_IDENTIFIER'; END $fn$"
)


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _md26():
    spec = importlib.util.spec_from_file_location("md26_business_ids", MIGRATION)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def pending(url: str) -> tuple[bool, list[str]]:
    """(is legacy, the object tables there that still lack business_id)."""
    engine = create_engine(url, connect_args=connect_args())
    try:
        inspector = inspect(engine)
        tables = set(inspector.get_table_names())
        missing = [
            item.table
            for item in OBJECTS
            if item.table in tables and "business_id" not in {c["name"] for c in inspector.get_columns(item.table)}
        ]
        # The same rule as scripts/migrate_data_planes.py: tables but no recorded migration revision.
        state, _ = _load("migrate_data_planes", ROOT / "scripts" / "migrate_data_planes.py").plane_state(url)
        return state == "LEGACY", missing
    finally:
        engine.dispose()


def apply(url: str, md26) -> list[str]:
    engine = create_engine(url, connect_args=connect_args())
    try:
        with engine.begin() as connection:
            inspector = inspect(connection)
            tables = set(inspector.get_table_names())
            context = MigrationContext.configure(connection)
            done = []
            with Operations.context(context):
                connection.execute(text(REJECT_FUNCTION))
                if COUNTER_TABLE not in tables:
                    md26.create_counter_and_function()
                for item in OBJECTS:
                    if item.table not in tables:
                        continue
                    if "business_id" in {c["name"] for c in inspector.get_columns(item.table)}:
                        continue
                    md26.add_business_id(connection, item)
                    done.append(item.table)
            return done
    finally:
        engine.dispose()


def sync_copies(url: str, tenant_id) -> int:
    """The plane's copies of its customer and tenant rows carry the control database's business identifiers (the
    plane numbered its copies on its own); scripts/migrate_data_planes.py does the same for managed planes."""
    migrate = _load("migrate_data_planes", ROOT / "scripts" / "migrate_data_planes.py")
    engine = create_engine(url, connect_args=connect_args())
    try:
        with migrate.control_engine.connect() as connection:
            customer_id = connection.execute(
                text("SELECT customer_id FROM tenants WHERE id = :t"), {"t": tenant_id}
            ).scalar()
        return migrate._copy_rows("customers", "id", customer_id, engine) + migrate._copy_rows(
            "tenants", "id", tenant_id, engine
        )
    finally:
        engine.dispose()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--apply", action="store_true", help="change the databases (default: dry run)")
    args = parser.parse_args()
    md26 = _md26()
    db = SessionLocal()
    try:
        bind_system(db, "add business identifiers to legacy organization databases")
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
            legacy, missing = pending(url)
            if not legacy:
                print(f"SKIP      {label}: managed by migrations (scripts/migrate_data_planes.py)")
            elif not args.apply:
                state = f"{len(missing)} table(s): {', '.join(missing)}" if missing else "columns present"
                print(f"PENDING   {label}: {state}; customer and tenant copies re-synced on --apply (dry run)")
            else:
                done = apply(url, md26) if missing else []
                synced = sync_copies(url, plane.tenant_id)
                print(f"DONE      {label}: {len(done)} table(s) numbered, {synced} control copies re-synced")
        except Exception as exc:  # report every database, then fail
            failures += 1
            print(f"FAILED    {label}: {type(exc).__name__}: {exc}")
    if not planes:
        print("No dedicated organization databases are registered.")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
