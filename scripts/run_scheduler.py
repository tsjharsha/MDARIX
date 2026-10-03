"""Run MDARIX's scheduled jobs (backend/app/scheduler.py). One long-running process; a spare instance is safe.

python scripts/run_scheduler.py            # serve forever
python scripts/run_scheduler.py --once     # run every due job once and exit (for cron or a manual check)
python scripts/run_scheduler.py --list     # show the jobs and when each last ran
"""

from __future__ import annotations

import json
import signal
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.app.logging_setup import configure_logging  # noqa: E402


def main() -> int:
    configure_logging()
    from backend.app import scheduler

    if "--list" in sys.argv:
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
    if "--once" in sys.argv:
        print(json.dumps(scheduler.run_due_jobs(), indent=2, default=str))
        return 0
    stopping = {"now": False}

    def stop(*_args):
        stopping["now"] = True

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    scheduler.serve(stop=lambda: stopping["now"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
