"""Manage the AcmeCare demo workspace.

Usage (from the repository root, owner database credentials in .env):
    python scripts/demo_tenant.py setup    # register the workspace and create the demo team (MDARIX_DEMO_PASSWORD)
    python scripts/demo_tenant.py reset    # delete everything the demo created and reload the original story
    python scripts/demo_tenant.py status   # what the workspace holds and who can sign in
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.app.db.session import SessionLocal  # noqa: E402
from backend.app.demo_workspace import DemoWorkspaceError, reset_demo, setup_demo, status  # noqa: E402


def main() -> int:
    command = sys.argv[1] if len(sys.argv) > 1 else "status"
    if command not in {"setup", "reset", "status"}:
        print(__doc__)
        return 2
    started = time.monotonic()
    db = SessionLocal()
    try:
        if command == "setup":
            result = setup_demo(db, os.getenv("MDARIX_DEMO_PASSWORD", ""))
        elif command == "reset":
            result = reset_demo(db)
        else:
            result = status(db)
    except DemoWorkspaceError as exc:
        print(f"Demo workspace: {exc}")
        return 1
    finally:
        db.close()
    print(json.dumps(result, indent=2, default=str))
    print(f"{command} finished in {time.monotonic() - started:.1f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
