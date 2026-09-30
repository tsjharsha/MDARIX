"""Single local command for the deterministic validation stack."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    env = os.environ.copy()
    env.setdefault("MDARIX_ENV", "test")
    env.setdefault("DAY35_FIXTURE_PASSWORD", "TestOnly-MDARIX-2026!")
    env["DAY35_FIXTURE_APPLY"] = "1"
    services = [
        "postgres",
        "mailpit",
        "minio",
        "mdarix-outbox-worker",
        "trackwise-simulator",
        "plm-simulator",
        "erp-simulator",
        "supplier-simulator",
        "veeva-qms-simulator",
        "teamcenter-simulator",
        "oracle-erp-simulator",
        "coupa-simulator",
    ]
    subprocess.run(["docker", "compose", "up", "-d", *services], cwd=ROOT, check=True)
    commands = [
        [sys.executable, "scripts/prepare_test_environment.py"],
        [sys.executable, "scripts/validate_local_stack.py"],
        [sys.executable, "-m", "pytest", "-q"],
        ["npm.cmd", "--prefix", "frontend", "run", "build"],
        ["npm.cmd", "--prefix", "frontend", "test", "--", "--run"],
    ]
    for command in commands:
        if subprocess.run(command, cwd=ROOT, env=env).returncode != 0:
            return 1
    print("VALIDATION_STACK_PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
