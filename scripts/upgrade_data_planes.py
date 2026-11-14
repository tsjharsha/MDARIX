"""Bring every dedicated customer database (data plane) up to the application's schema, without removing anything.

For each ACTIVE plane in the control database's registry (tenant_data_planes, not the shared control plane):
- creates the tables the application has and the plane lacks (public schema only);
- adds the columns the plane lacks (nullable, or with the model's server default);
- with MDARIX_DATA_PLANE_RUNTIME_USER and _PASSWORD set, creates that login role without superuser or RLS bypass
  and grants it data access only, so the application need not connect as the plane's owner;
- records the control database's migration head as the plane's schema_version in the registry.

Nothing is dropped, renamed or rewritten. Dry run by default: lists what it would do. Run with --apply to change.
Usage:  python scripts/upgrade_data_planes.py [--apply]
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import create_engine, inspect, text  # noqa: E402

import backend.app.db.models  # noqa: E402,F401  (registers every model)
from backend.app.db.base import Base  # noqa: E402
from backend.app.db.data_plane import SHARED_CONTROL_DATA_PLANE, _secret_url  # noqa: E402
from backend.app.db.models.customer_lifecycle import TenantDataPlane  # noqa: E402
from backend.app.db.session import SessionLocal  # noqa: E402
from backend.app.db.tenant_scope import bind_system  # noqa: E402

ROLE = re.compile(r"^[a-z][a-z0-9_]{2,62}$")


def plan_for(engine) -> tuple[list, list[tuple[str, str, str]]]:
    """Tables to create and (table, column, ALTER statement) to add on one plane."""
    inspector = inspect(engine)
    existing = set(inspector.get_table_names(schema="public"))
    tables = [table for table in Base.metadata.sorted_tables if table.schema is None]
    missing_tables = [table for table in tables if table.name not in existing]
    columns: list[tuple[str, str, str]] = []
    for table in tables:
        if table.name not in existing:
            continue
        present = {column["name"] for column in inspector.get_columns(table.name, schema="public")}
        for column in table.columns:
            if column.name in present:
                continue
            kind = column.type.compile(dialect=engine.dialect)
            default = ""
            if column.server_default is not None and hasattr(column.server_default, "arg"):
                arg = column.server_default.arg
                default = f" DEFAULT {arg.text if hasattr(arg, 'text') else repr(str(arg)).replace(chr(34), chr(39))}"
            not_null = " NOT NULL" if (not column.nullable and default) else ""
            columns.append(
                (
                    table.name,
                    column.name,
                    f'ALTER TABLE public."{table.name}" ADD COLUMN "{column.name}" {kind}{default}{not_null}',
                )
            )
    return missing_tables, columns


def grant_runtime_role(connection, role: str, password: str) -> None:
    if not ROLE.match(role):
        raise ValueError("The runtime role must be a plain lower-case role name")
    exists = connection.scalar(text("SELECT 1 FROM pg_roles WHERE rolname = :role"), {"role": role})
    # PostgreSQL takes no bound parameters in CREATE/ALTER ROLE: the server quotes the password as a literal first,
    # as scripts/configure_runtime_role.py does.
    quoted = connection.scalar(text("SELECT quote_literal(:pw)"), {"pw": password})
    if not exists:
        connection.execute(
            text(f'CREATE ROLE "{role}" LOGIN NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE PASSWORD {quoted}')
        )
    else:
        connection.execute(text(f'ALTER ROLE "{role}" NOSUPERUSER NOBYPASSRLS PASSWORD {quoted}'))
    for statement in (
        f'GRANT USAGE ON SCHEMA public TO "{role}"',
        f'GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO "{role}"',
        f'GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA public TO "{role}"',
        f'ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO "{role}"',
        f'ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT, UPDATE ON SEQUENCES TO "{role}"',
    ):
        connection.execute(text(statement))
    # No row-level security on these, so read only (DB-1, tr21); a legacy plane may lack them.
    for table in ("alembic_version", "business_id_counters"):
        if connection.scalar(text("SELECT to_regclass(:t) IS NOT NULL"), {"t": f"public.{table}"}):
            connection.execute(text(f'REVOKE INSERT, UPDATE, DELETE ON public."{table}" FROM "{role}"'))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--apply", action="store_true", help="make the changes (default: only list them)")
    args = parser.parse_args()
    role = os.getenv("MDARIX_DATA_PLANE_RUNTIME_USER", "").strip()
    password = os.getenv("MDARIX_DATA_PLANE_RUNTIME_PASSWORD", "")
    if role and not ROLE.match(role):
        print("MDARIX_DATA_PLANE_RUNTIME_USER must be a plain lower-case role name")
        return 2
    with SessionLocal() as control:
        bind_system(control, "upgrade dedicated data planes")
        head = control.execute(text("SELECT version_num FROM alembic_version")).scalar()
        planes = (
            control.query(TenantDataPlane)
            .filter(
                TenantDataPlane.status == "ACTIVE", TenantDataPlane.connection_secret_ref != SHARED_CONTROL_DATA_PLANE
            )
            .all()
        )
        if not planes:
            print("No dedicated data planes are registered; every tenant uses the shared plane.")
            return 0
        for plane in planes:
            engine = create_engine(_secret_url(plane.connection_secret_ref), pool_pre_ping=True)
            tables, columns = plan_for(engine)
            print(
                f"{plane.database_ref}: {len(tables)} tables to create, {len(columns)} columns to add, schema {plane.schema_version} -> {head}"
            )
            for table in tables:
                print(f"  + table {table.name}")
            for table, column, _ in columns:
                print(f"  + column {table}.{column}")
            if args.apply:
                Base.metadata.create_all(engine, tables=tables, checkfirst=True)
                with engine.begin() as connection:
                    for _, _, statement in columns:
                        connection.execute(text(statement))
                    if role and password:
                        grant_runtime_role(connection, role, password)
                        print(f"  runtime role {role}: data access only (no superuser, no RLS bypass)")
                plane.schema_version = head
            engine.dispose()
        if args.apply:
            control.commit()
            print("Applied.")
        else:
            print("Dry run: nothing changed. Run with --apply to make these changes.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
