"""Bring every dedicated customer database (data plane) to the application's schema with the same Alembic migrations
as the control database, so planes get identical tables, row-level security, triggers, functions and grants.

For each ACTIVE dedicated plane in the control database's registry (``tenant_data_planes``):

1. ``alembic upgrade head`` against the plane (``MDARIX_MIGRATION_DATABASE_URL``), using the owner connection string
   in ``<secret ref>_OWNER`` when set (the application's own connection string otherwise);
2. copies the organization's ``customers`` and ``tenants`` rows from the control database (business tables reference
   them), updating them on later runs;
3. grants the least-privilege runtime role its data access, and makes identity and platform tables read-only for it:
   accounts, sessions, invitations, plans and subscriptions live in the control database only;
4. records the migration head as the plane's ``schema_version`` in the registry.

A plane that already has tables but no Alembic history was built by the older scripts (initialize/upgrade/expand
data planes). It is reported as LEGACY and left alone: rebuild it from an empty database with this script and move
its data across. The API refuses legacy planes outside local development (backend/app/db/data_plane.py).

    python scripts/migrate_data_planes.py            # dry run: what would happen
    python scripts/migrate_data_planes.py --apply
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from sqlalchemy import MetaData, Table, create_engine, inspect, text  # noqa: E402
from sqlalchemy.dialects.postgresql import insert  # noqa: E402

from backend.app.db.data_plane import SHARED_CONTROL_DATA_PLANE, _secret_url  # noqa: E402
from backend.app.db.models.customer_lifecycle import TenantDataPlane  # noqa: E402
from backend.app.db.session import SessionLocal, engine as control_engine  # noqa: E402
from backend.app.db.tenant_scope import bind_connection_system, bind_system  # noqa: E402
from backend.app.db.tls import connect_args  # noqa: E402

ROLE = re.compile(r"^[a-z][a-z0-9_]{2,62}$")

# Tables that belong to the control database. They exist on a plane (same migrations) but stay empty there, and the
# application role may not write them on a plane.
CONTROL_ONLY = (
    "auth_users",
    "auth_sessions",
    "authentication_events",
    "mfa_challenges",
    "password_history",
    "password_reset_requests",
    "user_invitations",
    "tenant_memberships",
    "role_assignments",
    "persona_assignments",
    "onboarding_requests",
    "demo_requests",
    "trial_exit_requests",
    "trial_feedback",
    "trial_mvp_requests",
    "subscription_lifecycles",
    "subscription_versions",
    "plan_definitions",
    "tenant_plan_assignments",
    "plan_version_assignments",
    "tenant_data_planes",
    "rate_limit_counters",
    "scheduler_runs",
    "worker_heartbeats",
    "genai_provider_rest",
    "ai_usage_monthly",
    "tenant_exports",
)


def head_revision() -> str:
    from alembic.config import Config
    from alembic.script import ScriptDirectory

    return ScriptDirectory.from_config(Config(str(ROOT / "alembic.ini"))).get_current_head()


def plane_state(url: str) -> tuple[str, str | None]:
    """("EMPTY" | "MANAGED" | "LEGACY", current revision).

    MANAGED needs a recorded revision: the older plane scripts left an empty ``alembic_version`` table behind, and a
    plane with tables but no revision must never be upgraded from the start (it would collide with what is there)."""
    engine = create_engine(url, connect_args=connect_args())
    try:
        tables = set(inspect(engine).get_table_names(schema="public"))
        revision = None
        if "alembic_version" in tables:
            with engine.connect() as connection:
                revision = connection.execute(text("SELECT version_num FROM alembic_version")).scalar()
        if revision:
            return "MANAGED", revision
        return ("LEGACY" if tables - {"alembic_version"} else "EMPTY"), None
    finally:
        engine.dispose()


def _copy_rows(table_name: str, column: str, value, plane_engine) -> int:
    source = Table(table_name, MetaData(), autoload_with=control_engine)
    with control_engine.connect() as connection:
        bind_connection_system(connection)  # organization rows are protected by row-level security (md34)
        rows = [dict(row._mapping) for row in connection.execute(source.select().where(source.c[column] == value))]
    if not rows:
        return 0
    target = Table(table_name, MetaData(), autoload_with=plane_engine)
    shared = [name for name in rows[0] if name in target.c]
    # The copy carries the control database's business identifier (md26). Business identifiers refuse to change, so
    # this owner-only sync lifts that one trigger for its own transaction to correct a copy numbered on the plane.
    guard = f"{table_name}_business_id_immutable" if "business_id" in shared else None
    with plane_engine.begin() as connection:
        bind_connection_system(connection)
        if guard and _has_trigger(connection, table_name, guard):
            connection.execute(text(f'ALTER TABLE public."{table_name}" DISABLE TRIGGER "{guard}"'))
        else:
            guard = None
        for row in rows:
            values = {name: row[name] for name in shared}
            statement = insert(target).values(**values)
            connection.execute(
                statement.on_conflict_do_update(
                    index_elements=[target.c.id], set_={name: values[name] for name in shared if name != "id"}
                )
            )
        if guard:
            # Deferred constraint triggers (tenants_default_data_plane) queue events until commit, and a table with
            # pending events cannot be altered: run them now, then restore the guard.
            connection.execute(text("SET CONSTRAINTS ALL IMMEDIATE"))
            connection.execute(text(f'ALTER TABLE public."{table_name}" ENABLE TRIGGER "{guard}"'))
    return len(rows)


def _has_trigger(connection, table_name: str, trigger: str) -> bool:
    return bool(
        connection.execute(
            text("SELECT 1 FROM pg_trigger WHERE tgrelid = to_regclass(:table) AND tgname = :trigger"),
            {"table": f"public.{table_name}", "trigger": trigger},
        ).scalar()
    )


def _grants(plane_engine) -> None:
    runtime = os.getenv("MDARIX_DB_RUNTIME_USER", "").strip() or "mdarix_runtime"
    # The role is written into GRANT/REVOKE text, so it must be a plain name, as in the other role scripts.
    if not ROLE.match(runtime):
        raise SystemExit("MDARIX_DB_RUNTIME_USER must be a plain lower-case role name")
    with plane_engine.begin() as connection:
        exists = connection.execute(text("SELECT 1 FROM pg_roles WHERE rolname = :r"), {"r": runtime}).first()
        if not exists:
            return
        connection.execute(text(f'GRANT USAGE ON SCHEMA public TO "{runtime}"'))
        connection.execute(text(f'GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO "{runtime}"'))
        connection.execute(text(f'GRANT USAGE, SELECT, UPDATE ON ALL SEQUENCES IN SCHEMA public TO "{runtime}"'))
        connection.execute(text(f'REVOKE ALL ON public.mdarix_rls_secret FROM "{runtime}"'))
        # No row-level security on these, so read only (DB-1, tr21).
        connection.execute(text(f'REVOKE INSERT, UPDATE, DELETE ON public.alembic_version FROM "{runtime}"'))
        connection.execute(text(f'REVOKE INSERT, UPDATE, DELETE ON public.business_id_counters FROM "{runtime}"'))
        present = set(inspect(connection).get_table_names(schema="public"))
        for table in CONTROL_ONLY:
            if table in present:
                connection.execute(text(f'REVOKE INSERT, UPDATE, DELETE ON public."{table}" FROM "{runtime}"'))


def migrate(plane: TenantDataPlane, head: str, apply: bool) -> str:
    url = os.getenv(f"{plane.connection_secret_ref}_OWNER", "").strip() or _secret_url(plane.connection_secret_ref)
    state, current = plane_state(url)
    label = f"{plane.database_ref} (tenant {plane.tenant_id})"
    if state == "LEGACY":
        return f"LEGACY    {label}: built without migrations; rebuild it from an empty database"
    if state == "MANAGED" and current == head:
        action = "CURRENT"
    else:
        action = f"UPGRADE   {current or 'empty'} -> {head}"
    if not apply:
        return f"{action}  {label} (dry run)"
    environment = {**os.environ, "MDARIX_MIGRATION_DATABASE_URL": url}
    subprocess.run([sys.executable, "-m", "alembic", "upgrade", "head"], cwd=ROOT, env=environment, check=True)
    plane_engine = create_engine(url, connect_args=connect_args())
    try:
        with control_engine.connect() as connection:
            bind_connection_system(connection)
            customer_id = connection.execute(
                text("SELECT customer_id FROM tenants WHERE id = :t"), {"t": plane.tenant_id}
            ).scalar()
        _copy_rows("customers", "id", customer_id, plane_engine)
        _copy_rows("tenants", "id", plane.tenant_id, plane_engine)
        _grants(plane_engine)
    finally:
        plane_engine.dispose()
    return f"{action}  {label}: done"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--apply", action="store_true", help="change the planes (default: dry run)")
    args = parser.parse_args()
    head = head_revision()
    db = SessionLocal()
    try:
        bind_system(db, "migrate data planes")
        planes = (
            db.query(TenantDataPlane)
            .filter(
                TenantDataPlane.status == "ACTIVE", TenantDataPlane.connection_secret_ref != SHARED_CONTROL_DATA_PLANE
            )
            .all()
        )
        failures = 0
        for plane in planes:
            try:
                print(migrate(plane, head, args.apply))
                if args.apply:
                    plane.schema_version = head
                    db.commit()
            except Exception as exc:  # report every plane, then fail
                failures += 1
                print(f"FAILED   {plane.database_ref}: {type(exc).__name__}: {exc}")
        if not planes:
            print("No dedicated data planes are registered.")
        return 1 if failures else 0
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
