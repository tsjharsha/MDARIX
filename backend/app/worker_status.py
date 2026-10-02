"""Background worker heartbeat: the worker records one every cycle, the platform console reads it.

A worker that has not written for STALE_AFTER_SECONDS is reported as stopped; one that never wrote is not reported.
"""

from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from backend.app.db.models.stage2 import WorkerHeartbeat

OUTBOX_WORKER = "mdarix-outbox-worker"
# The worker cycles every few seconds (MDARIX_OUTBOX_INTERVAL_SECONDS, default 5); a minute of silence means it stopped.
STALE_AFTER_SECONDS = 60


def record_heartbeat(db: Session, service: str, instance_id: str, started_at: datetime, metrics: dict) -> None:
    now = datetime.now(timezone.utc)
    statement = insert(WorkerHeartbeat).values(
        service=service, instance_id=instance_id, started_at=started_at, updated_at=now, metrics=metrics
    )
    db.execute(
        statement.on_conflict_do_update(
            index_elements=[WorkerHeartbeat.service],
            set_={
                "instance_id": statement.excluded.instance_id,
                "started_at": statement.excluded.started_at,
                "updated_at": statement.excluded.updated_at,
                "metrics": statement.excluded.metrics,
            },
        )
    )
    db.commit()


def worker_status(db: Session, service: str = OUTBOX_WORKER, *, with_metrics: bool = False) -> dict:
    """{state: RUNNING | STOPPED | NOT_REPORTED, last_seen_at, seconds_since, started_at[, metrics]}."""
    row = db.get(WorkerHeartbeat, service)
    if row is None:
        return {"state": "NOT_REPORTED", "last_seen_at": None, "seconds_since": None, "started_at": None}
    seconds = max(0, int((datetime.now(timezone.utc) - row.updated_at).total_seconds()))
    status = {
        "state": "RUNNING" if seconds <= STALE_AFTER_SECONDS else "STOPPED",
        "last_seen_at": row.updated_at.isoformat(),
        "seconds_since": seconds,
        "started_at": row.started_at.isoformat(),
    }
    if with_metrics:
        status["metrics"] = row.metrics or {}
    return status
