"""Create (or update) the read-only login the backup job uses, so backups need neither the owner nor a superuser.

Row-level security is forced on every tenant table, for the schema owner too, so pg_dump can only read every row as a
role with BYPASSRLS. This script creates ``MDARIX_BACKUP_DB_USER`` (default ``mdarix_backup``) with
``MDARIX_BACKUP_DB_PASSWORD`` (at least 24 characters, never printed): it may log in and read every table and sequence
in the owner's schemas, now and later (default privileges), and nothing else: no writes, no schema changes, no roles.

BYPASSRLS needs a superuser, or on PostgreSQL 16 a CREATEROLE account that has BYPASSRLS itself. Managed providers
differ: where the owner may not grant it, the role is still created without it and the backup job reads through the
application's system scope instead (``MDARIX_RLS_SYSTEM_TOKEN``; infrastructure/docker/backup/backup.sh checks which
applies on every run). Run with the owner's credentials, i.e. in the migrate job; safe to run again (it also rotates
the password):

    docker compose -f docker-compose.prod.yml --env-file .env.production run --rm migrate python scripts/configure_backup_role.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import text  # noqa: E402
from sqlalchemy.exc import DBAPIError  # noqa: E402

INSUFFICIENT_PRIVILEGE = "42501"


def _sqlstate(exc: DBAPIError) -> str | None:
    """The SQLSTATE of a pg8000 error (its first argument is the server's error fields)."""
    fields = exc.orig.args[0] if exc.orig is not None and exc.orig.args else None
    return fields.get("C") if isinstance(fields, dict) else None


def grant_bypass(connection, role: str) -> bool:
    """Give ``role`` BYPASSRLS when this login may; False (and nothing changed) when the server refuses."""
    savepoint = connection.begin_nested()
    try:
        connection.execute(text(f'ALTER ROLE "{role}" BYPASSRLS'))
    except DBAPIError as exc:
        savepoint.rollback()
        if _sqlstate(exc) == INSUFFICIENT_PRIVILEGE:
            return False
        raise
    savepoint.commit()
    return True


def configure(connection, role: str, password: str) -> dict:
    """Create or update the backup login and its read grants; returns its flags and whether BYPASSRLS was granted."""
    quoted = connection.execute(text("SELECT quote_literal(:password)"), {"password": password}).scalar_one()
    exists = connection.execute(
        text("SELECT rolsuper, rolcreatedb, rolcreaterole FROM pg_roles WHERE rolname = :role"), {"role": role}
    ).first()
    if exists is None:
        # New roles start without SUPERUSER, CREATEDB and CREATEROLE.
        connection.execute(text(f'CREATE ROLE "{role}" WITH LOGIN NOINHERIT PASSWORD {quoted}'))
    else:
        # Name only what must be taken away: PostgreSQL 16 lets only a superuser even name SUPERUSER in ALTER ROLE.
        removals = "".join(
            f"{name} "
            for name, held in (
                ("NOSUPERUSER", exists.rolsuper),
                ("NOCREATEDB", exists.rolcreatedb),
                ("NOCREATEROLE", exists.rolcreaterole),
            )
            if held
        )
        connection.execute(text(f'ALTER ROLE "{role}" WITH {removals}LOGIN NOINHERIT PASSWORD {quoted}'))
    bypass = grant_bypass(connection, role)
    database = connection.execute(text("SELECT current_database()")).scalar_one()
    connection.execute(text(f'GRANT CONNECT ON DATABASE "{database}" TO "{role}"'))
    # Every schema the owner (this login) holds: public, and md_master when present.
    schemas = connection.execute(
        text(
            "SELECT nspname FROM pg_namespace WHERE nspowner = (SELECT oid FROM pg_roles WHERE rolname = current_user) "
            "AND nspname NOT LIKE 'pg\\_%' AND nspname <> 'information_schema' ORDER BY nspname"
        )
    ).scalars()
    granted = []
    for schema in list(schemas) + ["public"]:
        if schema in granted:
            continue
        granted.append(schema)
        connection.execute(text(f'GRANT USAGE ON SCHEMA "{schema}" TO "{role}"'))
        connection.execute(text(f'GRANT SELECT ON ALL TABLES IN SCHEMA "{schema}" TO "{role}"'))
        connection.execute(text(f'GRANT SELECT ON ALL SEQUENCES IN SCHEMA "{schema}" TO "{role}"'))
        # Tables later migrations create are readable too, without running this again.
        connection.execute(text(f'ALTER DEFAULT PRIVILEGES IN SCHEMA "{schema}" GRANT SELECT ON TABLES TO "{role}"'))
        connection.execute(text(f'ALTER DEFAULT PRIVILEGES IN SCHEMA "{schema}" GRANT SELECT ON SEQUENCES TO "{role}"'))
    has_scope_function = connection.execute(
        text("SELECT to_regprocedure('public.mdarix_system_scope()') IS NOT NULL")
    ).scalar_one()
    if has_scope_function:
        # Without BYPASSRLS the dump opens the system scope, which this function checks.
        connection.execute(text(f'GRANT EXECUTE ON FUNCTION public.mdarix_system_scope() TO "{role}"'))
    flags = connection.execute(
        text("SELECT rolsuper, rolbypassrls, rolcanlogin FROM pg_roles WHERE rolname = :role"), {"role": role}
    ).one()
    return {
        "role": role,
        "created": not exists,
        "bypass_rls": bool(flags.rolbypassrls),
        "bypass_granted_now": bypass,
        "superuser": bool(flags.rolsuper),
        "login": bool(flags.rolcanlogin),
        "schemas": granted,
    }


def main() -> int:
    role = os.getenv("MDARIX_BACKUP_DB_USER", "").strip() or "mdarix_backup"
    password = os.getenv("MDARIX_BACKUP_DB_PASSWORD", "")
    if len(password) < 24:
        print("Set MDARIX_BACKUP_DB_PASSWORD (at least 24 characters) in .env.migrate first.", file=sys.stderr)
        return 2
    if not role.replace("_", "").isalnum():
        print("MDARIX_BACKUP_DB_USER must be a plain role name.", file=sys.stderr)
        return 2
    from backend.app.db.session import engine

    with engine.begin() as connection:
        result = configure(connection, role, password)
    print(
        f"{result['role']}: {'created' if result['created'] else 'updated'}; login={result['login']} "
        f"superuser={result['superuser']} bypass_rls={result['bypass_rls']}; may read {', '.join(result['schemas'])}."
    )
    if not result["bypass_rls"]:
        print(
            "This database does not let the owner grant BYPASSRLS (usual on managed services). Backups still read "
            "every row, through the system scope: keep MDARIX_RLS_SYSTEM_TOKEN in .env.production. To use BYPASSRLS "
            f'instead, have the provider\'s admin run: ALTER ROLE "{role}" BYPASSRLS;'
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
