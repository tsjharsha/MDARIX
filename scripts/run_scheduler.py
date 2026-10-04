"""Run MDARIX's scheduled jobs (backend/app/scheduler.py). One long-running process; a spare instance is safe.

python scripts/run_scheduler.py            # serve forever (SIGTERM/SIGINT stop it at once, after the current job)
python scripts/run_scheduler.py --once     # run every due job once and exit (cron, CI, a manual check); exit 1 if any failed
python scripts/run_scheduler.py --list     # show the jobs and when each last ran

Staging and production refuse to start with a missing or unsafe configuration (backend/app/config_check.py), the
same gate the API applies.
"""

from __future__ import annotations

import json
import signal
import sys
import threading
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.app.logging_setup import configure_logging  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    configure_logging()
    from backend.app.config_check import enforce

    enforce()
    from backend.app import scheduler

    if "--list" in argv:
        from backend.app.db.models.stage2 import SchedulerRun
        from backend.app.db.session import SessionLocal
        from backend.app.db.tenant_scope import bind_system

        db = SessionLocal()
        try:
            bind_system(db, "scheduler: list job runs")
            rows = {row.job: row for row in db.query(SchedulerRun).all()}
        finally:
            db.close()
        for job in scheduler.JOBS:
            row = rows.get(job.name)
            print(
                f"{job.name:24} every {job.every}  last: "
                + (f"{row.last_status} at {row.last_finished_at}" if row and row.last_finished_at else "never")
            )
        return 0
    if "--once" in argv:
        outcomes = scheduler.run_due_jobs()
        print(json.dumps(outcomes, indent=2, default=str))
        return 1 if any(item["status"] == "FAILED" for item in outcomes) else 0
    shutdown = threading.Event()

    def stop(*_args):
        shutdown.set()

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    scheduler.serve(shutdown=shutdown)
    return 0


if __name__ == "__main__":
    sys.exit(main())
