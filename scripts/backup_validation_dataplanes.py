"""Create and validate local synthetic data-plane backups.

This is a repeatable MVP validation command. Production backup encryption,
WAL/PITR targets, retention schedules, and restore environments remain
deployment responsibilities.
"""
from __future__ import annotations

import argparse
import subprocess
from datetime import datetime, timezone
from pathlib import Path

PLANES = {
    "tenant-a": ("mdarix-r1-tenant-a-data-1", "mdarix_tenant_a"),
    "tenant-b": ("mdarix-r1-tenant-b-data-1", "mdarix_tenant_b"),
    "tenant-c": ("mdarix-r1-tenant-c-data-1", "mdarix_tenant_c"),
    "tenant-d": ("mdarix-r1-tenant-d-data-1", "mdarix_tenant_d"),
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default="artifacts/data-plane-backups")
    args = parser.parse_args()
    root = Path(args.output); root.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    for name, (container, database) in PLANES.items():
        target = root / f"{name}-{stamp}.dump"
        result = subprocess.run(
            ["docker", "exec", container, "pg_dump", "-U", "mdarix_data", "-d", database, "--format=custom", "--no-owner", "--no-privileges"],
            check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        target.write_bytes(result.stdout)
        listing = subprocess.run(["pg_restore", "--list", str(target)], check=True, stdout=subprocess.PIPE, text=True)
        if not listing.stdout.strip():
            raise SystemExit(f"BACKUP_EMPTY {name}")
        print(f"BACKUP_VALIDATED {name} {target} bytes={target.stat().st_size}")


if __name__ == "__main__":
    main()
