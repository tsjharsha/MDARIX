"""Background worker heartbeat: each worker instance records one every cycle, the platform console reads them.

A service is RUNNING when at least one of its instances wrote within STALE_AFTER_SECONDS, STOPPED when none did, and
NOT_REPORTED when no instance ever wrote. Heartbeats of instances silent for a day are removed.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from backend.app.db.models.stage2 import WorkerHeartbeat

OUTBOX_WORKER = "mdarix-outbox-worker"
# The worker cycles every few seconds (MDARIX_OUTBOX_INTERVAL_SECONDS, default 5); a minute of silence means it stopped.
STALE_AFTER_SECONDS = 60
FORGET_AFTER = timedelta(days=1)


def record_heartbeat(db: Session, service: str, instance_id: str, started_at: datetime, metrics: dict) -> None:
    now = datetime.now(timezone.utc)
    statement = insert(WorkerHeartbeat).values(
        service=service, instance_id=instance_id, started_at=started_at, updated_at=now, metrics=metrics
    )
    db.execute(
        statement.on_conflict_do_update(
            index_elements=[WorkerHeartbeat.service, WorkerHeartbeat.instance_id],
            set_={
                "started_at": statement.excluded.started_at,
                "updated_at": statement.excluded.updated_at,
                "metrics": statement.excluded.metrics,
            },
        )
    )
    db.query(WorkerHeartbeat).filter(
        WorkerHeartbeat.service == service, WorkerHeartbeat.updated_at < now - FORGET_AFTER
    ).delete(synchronize_session=False)
    db.commit()


def worker_status(db: Session, service: str = OUTBOX_WORKER, *, with_metrics: bool = False) -> dict:
    """{state: RUNNING | STOPPED | NOT_REPORTED, last_seen_at, seconds_since, started_at, instances[, metrics]}."""
    rows = db.query(WorkerHeartbeat).filter(WorkerHeartbeat.service == service).all()
    if not rows:
        return {
            "state": "NOT_REPORTED",
            "last_seen_at": None,
            "seconds_since": None,
            "started_at": None,
            "instances": 0,
        }
    now = datetime.now(timezone.utc)
    latest = max(rows, key=lambda row: row.updated_at)
    seconds = max(0, int((now - latest.updated_at).total_seconds()))
    live = sum(1 for row in rows if (now - row.updated_at).total_seconds() <= STALE_AFTER_SECONDS)
    status = {
        "state": "RUNNING" if live else "STOPPED",
        "last_seen_at": latest.updated_at.isoformat(),
        "seconds_since": seconds,
        "started_at": latest.started_at.isoformat(),
        "instances": live,
    }
    if with_metrics:
        status["metrics"] = latest.metrics or {}
    return status
