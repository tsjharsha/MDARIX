"""Prepare a deterministic test database; writes are explicitly test-gated."""
from __future__ import annotations
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def run(*args: str, env: dict[str, str] | None = None) -> None:
    subprocess.run(args, cwd=ROOT, env=env, check=True)

def main() -> int:
    if os.getenv('MDARIX_ENV') != 'test':
        raise SystemExit('Refusing test database writes: set MDARIX_ENV=test')
    env = os.environ.copy()
    env['DAY35_FIXTURE_APPLY'] = '1'
    if not env.get('DAY35_FIXTURE_PASSWORD'):
        raise SystemExit('DAY35_FIXTURE_PASSWORD is required and must be test-only')
    run(sys.executable, '-m', 'alembic', 'upgrade', 'head', env=env)
    run(sys.executable, 'scripts/provision_day35_fixture.py', env=env)
    run(sys.executable, 'scripts/seed_demo_expansion.py', env=env)
    print('TEST_ENVIRONMENT_READY')
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
