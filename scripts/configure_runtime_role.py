"""Give the least-privilege application role a login, so the API runs under row-level security.

Run with the database owner credentials (POSTGRES_USER / POSTGRES_PASSWORD). The runtime role's password comes from
MDARIX_DB_RUNTIME_PASSWORD and is never printed. The role is always left without superuser or RLS-bypass rights.

Usage: python scripts/configure_runtime_role.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import text  # noqa: E402

from backend.app.db.session import engine  # noqa: E402

ROLE = os.getenv("MDARIX_DB_RUNTIME_USER", "mdarix_runtime")


def _removals(current) -> str:
    """The attributes to take away, named only when the role has them.

    PostgreSQL 16 lets only a superuser even name SUPERUSER or BYPASSRLS in ALTER ROLE (and only a CREATEDB account
    name CREATEDB), so repeating "NOSUPERUSER NOBYPASSRLS ..." on every run would fail on a managed database whose
    owner is not a superuser, although nothing needs changing. A role that does hold one of them still fails here,
    loudly, unless a superuser runs this.
    """
    flags = (
        ("NOSUPERUSER", current.rolsuper),
        ("NOBYPASSRLS", current.rolbypassrls),
        ("NOCREATEDB", current.rolcreatedb),
        ("NOCREATEROLE", current.rolcreaterole),
    )
    return "".join(f"{name} " for name, held in flags if held)


def main() -> None:
    password = os.getenv("MDARIX_DB_RUNTIME_PASSWORD", "")
    if len(password) < 24:
        raise SystemExit("Set MDARIX_DB_RUNTIME_PASSWORD (at least 24 characters) before running this script.")
    if not ROLE.replace("_", "").isalnum():
        raise SystemExit("MDARIX_DB_RUNTIME_USER must be a plain role name.")
    with engine.begin() as connection:
        exists = connection.execute(text("SELECT 1 FROM pg_roles WHERE rolname = :role"), {"role": ROLE}).first()
        if exists is None:
            raise SystemExit(f"Role {ROLE} does not exist; apply the database migrations first.")
        quoted = connection.execute(text("SELECT quote_literal(:password)"), {"password": password}).scalar_one()
        current = connection.execute(
            text("SELECT rolsuper, rolbypassrls, rolcreatedb, rolcreaterole FROM pg_roles WHERE rolname = :role"),
            {"role": ROLE},
        ).one()
        connection.execute(text(f'ALTER ROLE "{ROLE}" WITH {_removals(current)}LOGIN PASSWORD {quoted}'))
        flags = connection.execute(
            text("SELECT rolsuper, rolbypassrls, rolcanlogin FROM pg_roles WHERE rolname = :role"), {"role": ROLE}
        ).one()
    print(f"{ROLE}: login={flags.rolcanlogin} superuser={flags.rolsuper} bypass_rls={flags.rolbypassrls}")
    if flags.rolsuper or flags.rolbypassrls:
        raise SystemExit(f"{ROLE} must have neither SUPERUSER nor BYPASSRLS: row-level security would not apply.")


if __name__ == "__main__":
    main()
