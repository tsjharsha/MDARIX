"""Prepare a deterministic test database; writes are explicitly test-gated.

Usage (from the repository root, with MDARIX_ENV=test and DAY35_FIXTURE_PASSWORD set):

    python scripts/prepare_test_environment.py              # migrate + seed existing DB
    python scripts/prepare_test_environment.py --recreate   # drop/create, then migrate + seed

POSTGRES_DB defaults to ``mdarix_r1_test`` (the database the pytest suite uses
locally). ``--recreate`` is refused for any database whose name does not end
in ``_test`` so the demo database can never be dropped by this script.

Order matters: the golden AcmeCare dataset is ingested before the Day 35
fixtures and demo expansion, because the demo seed attaches its products to
the golden tenant when it exists.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(*args: str, env: dict[str, str] | None = None) -> None:
    subprocess.run(args, cwd=ROOT, env=env, check=True)


def recreate_database(name: str) -> None:
    if not name.endswith("_test"):
        raise SystemExit(f"Refusing to recreate {name!r}: only *_test databases may be dropped")
    sys.path.insert(0, str(ROOT))
    from sqlalchemy import create_engine, text

    from backend.app.db.session import database_url

    admin_url = database_url().set(database="postgres")
    engine = create_engine(admin_url, isolation_level="AUTOCOMMIT", future=True)
    with engine.connect() as connection:
        connection.execute(text(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)'))
        connection.execute(text(f'CREATE DATABASE "{name}"'))
    engine.dispose()
    print(f"TEST_DATABASE_RECREATED {name}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--recreate", action="store_true", help="drop and recreate the *_test database first")
    args = parser.parse_args()
    if os.getenv("MDARIX_ENV") != "test":
        raise SystemExit("Refusing test database writes: set MDARIX_ENV=test")
    env = os.environ.copy()
    env.setdefault("POSTGRES_DB", "mdarix_r1_test")
    env.setdefault("MDARIX_DB_HARDENING_APPLY", "1")
    env["DAY35_FIXTURE_APPLY"] = "1"
    env["PYTHONPATH"] = str(ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    if not env.get("DAY35_FIXTURE_PASSWORD"):
        raise SystemExit("DAY35_FIXTURE_PASSWORD is required and must be test-only")
    if args.recreate:
        os.environ["POSTGRES_DB"] = env["POSTGRES_DB"]
        recreate_database(env["POSTGRES_DB"])
    run(sys.executable, "-m", "alembic", "upgrade", "head", env=env)
    run(sys.executable, "-m", "ingestion.services.ingestion_service", env=env)
    run(sys.executable, "-m", "ingestion.normalization.cli", env=env)
    run(sys.executable, "scripts/provision_day35_fixture.py", env=env)
    run(sys.executable, "scripts/seed_demo_expansion.py", env=env)
    print("TEST_ENVIRONMENT_READY")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
