"""Delete free-trial data 30 days after a trial closes. Schedule daily (Windows Task Scheduler or cron).

Usage: python scripts/run_trial_retention.py [--dry-run]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.app.db.session import SessionLocal  # noqa: E402
from backend.app.db.tenant_scope import bind_system  # noqa: E402
from backend.app.trial.retention import run_retention, trials_due  # noqa: E402


def main() -> None:
    db = SessionLocal()
    bind_system(db, "trial retention: find and remove expired trials")
    try:
        if "--dry-run" in sys.argv:
            print(json.dumps({"due": trials_due(db)}, indent=2))
            return
        print(json.dumps(run_retention(db, "system:trial-retention"), indent=2))
    finally:
        db.close()


if __name__ == "__main__":
    main()
