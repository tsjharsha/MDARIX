"""Scheduled jobs: what runs, how often, and the run loop (``python scripts/run_scheduler.py``).

Each job runs when its interval has passed since it last finished. A Postgres advisory lock per job means two
scheduler instances never run the same job at once, so running a spare instance is safe. Every run is recorded in
``scheduler_runs`` (status, result, error type); a job that fails three times in a row raises an alert, and so does
its recovery. Jobs run in system scope and record their own audit events.
"""

from __future__ import annotations

import logging
import time
import traceback
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable

from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.app.alerts import send_alert
from backend.app.db.models.stage2 import SchedulerRun
from backend.app.db.session import SessionLocal, engine
from backend.app.db.tenant_scope import bind_system

logger = logging.getLogger("mdarix.scheduler")
ACTOR = "system:scheduler"
ALERT_AFTER_FAILURES = 3


@dataclass(frozen=True)
class Job:
    name: str
    every: timedelta
    run: Callable[[Session, dict], dict]
    description: str


# ------------------------------------------------------------------------------------------- jobs


def tenant_lifecycle(db: Session, _state: dict) -> dict:
    from backend.app.access.platform_tenants import run_scheduled_lifecycle_job

    return run_scheduled_lifecycle_job(db, ACTOR)


def subscription_lifecycle(db: Session, _state: dict) -> dict:
    from backend.app.access.platform_subscriptions import run_subscription_lifecycle_job

    return run_subscription_lifecycle_job(db, ACTOR)


def trial_retention(db: Session, _state: dict) -> dict:
    from backend.app.trial.retention import run_retention

    result = run_retention(db, ACTOR)
    return {"purged": result["purged"], "tenants": [item.get("tenant_key") for item in result["trials"]]}


def trial_reminders(db: Session, _state: dict) -> dict:
    from backend.app.notifications import queue_trial_reminders

    return {"queued": queue_trial_reminders(db)}


def embedding_catch_up(db: Session, _state: dict) -> dict:
    """Embed evidence that has none yet (records imported while the API restarted, or a failed background step)."""
    from backend.app.db.data_plane import open_tenant_data_session
    from backend.app.db.models.foundation import Tenant
    from retrieval.service import TrustedRetrievalService

    service = TrustedRetrievalService()
    totals = {"tenants": 0, "indexed": 0, "failed": 0, "deferred": 0}
    tenant_ids = [row.id for row in db.query(Tenant.id).filter(Tenant.status.in_(["ACTIVE", "active"])).all()]
    for tenant_id in tenant_ids:
        with open_tenant_data_session(tenant_id) as data:
            result = service.index_evidence_chunks(data, tenant_id, limit=500)
        if result["indexed"] or result["failed"] or result["deferred"]:
            totals["tenants"] += 1
        for key in ("indexed", "failed", "deferred"):
            totals[key] += int(result.get(key) or 0)
    return totals


def operations_alerts(db: Session, state: dict) -> dict:
    """Alert on new dead-lettered events and on the worker stopping or recovering. State keeps what was reported."""
    from backend.app.worker_status import worker_status

    dead = int(db.execute(text("SELECT count(*) FROM event_outbox WHERE dead_lettered_at IS NOT NULL")).scalar() or 0)
    reported_dead = int(state.get("dead_letters", dead if "dead_letters" not in state else 0))
    if dead > reported_dead:
        send_alert(
            "Events could not be delivered",
            f"{dead - reported_dead} new event(s) were dead-lettered ({dead} in total). "
            "Review them in Platform Admin > Operations > Dead letters.",
        )
    state["dead_letters"] = dead
    worker = worker_status(db)["state"]
    if worker == "STOPPED" and state.get("worker") != "STOPPED":
        send_alert("Background worker stopped", "No heartbeat from the background worker for over a minute.")
    if worker == "RUNNING" and state.get("worker") == "STOPPED":
        send_alert("Background worker recovered", "The background worker is sending heartbeats again.")
    state["worker"] = worker
    return {"dead_letters": dead, "worker": worker}


JOBS: tuple[Job, ...] = (
    Job("tenant-lifecycle", timedelta(minutes=15), tenant_lifecycle, "Apply scheduled tenant status changes"),
    Job("subscription-lifecycle", timedelta(hours=1), subscription_lifecycle, "Expiry, grace and renewal reminders"),
    Job("trial-reminders", timedelta(hours=6), trial_reminders, "Email trial owners before and when the trial ends"),
    Job("trial-retention", timedelta(hours=24), trial_retention, "Delete trial data 30 days after the trial ends"),
    Job("embedding-catch-up", timedelta(minutes=15), embedding_catch_up, "Embed evidence that has no embedding yet"),
    Job("operations-alerts", timedelta(minutes=5), operations_alerts, "Alert on dead letters and a stopped worker"),
)


# ------------------------------------------------------------------------------------------- run loop


def _lock_key(job: str) -> str:
    return f"mdarix-job:{job}"


def _due(row: SchedulerRun | None, job: Job, now: datetime) -> bool:
    if row is None or row.last_finished_at is None:
        return True
    return now - row.last_finished_at >= job.every


def run_job(job: Job, now: datetime | None = None) -> dict | None:
    """Run ``job`` if no other scheduler is running it. Returns the run record, or None when another holds the lock."""
    now = now or datetime.now(timezone.utc)
    with engine.connect() as lock_connection:
        got = lock_connection.execute(
            text("SELECT pg_try_advisory_lock(hashtext(:key))"), {"key": _lock_key(job.name)}
        ).scalar()
        lock_connection.commit()
        if not got:
            return None
        try:
            return _run_locked(job, now)
        finally:
            lock_connection.execute(text("SELECT pg_advisory_unlock(hashtext(:key))"), {"key": _lock_key(job.name)})
            lock_connection.commit()


def _run_locked(job: Job, now: datetime) -> dict:
    db = SessionLocal()
    try:
        bind_system(db, f"scheduled job {job.name}")
        row = db.get(SchedulerRun, job.name)
        if row is None:
            row = SchedulerRun(job=job.name, consecutive_failures=0, state={})
            db.add(row)
        row.last_started_at = now
        state = dict(row.state or {})
        db.commit()
        started = time.perf_counter()
        try:
            result = job.run(db, state) or {}
            db.commit()
            status, error = "OK", None
        except Exception as exc:
            db.rollback()
            result, status = {}, "FAILED"
            error = f"{type(exc).__name__}: {str(exc)[:300]}"
            logger.error("Scheduled job %s failed\n%s", job.name, traceback.format_exc())
        bind_system(db, f"scheduled job {job.name}: record the run")
        row = db.get(SchedulerRun, job.name)
        previous_failures = row.consecutive_failures or 0
        row.last_finished_at = datetime.now(timezone.utc)
        row.last_status = status
        row.last_result = _jsonable(result)
        row.last_error = error
        row.consecutive_failures = previous_failures + 1 if status == "FAILED" else 0
        if status == "OK":
            row.state = state
        db.commit()
        duration = round(time.perf_counter() - started, 2)
        logger.info("Scheduled job %s %s in %ss", job.name, status, duration)
        if status == "FAILED" and row.consecutive_failures == ALERT_AFTER_FAILURES:
            send_alert(
                f"Scheduled job failing: {job.name}", f"{job.description}. Failed {ALERT_AFTER_FAILURES} times: {error}"
            )
        if status == "OK" and previous_failures >= ALERT_AFTER_FAILURES:
            send_alert(f"Scheduled job recovered: {job.name}", f"{job.description} succeeded again.")
        return {"job": job.name, "status": status, "result": row.last_result, "error": error, "seconds": duration}
    finally:
        db.close()


def _jsonable(value):
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def run_due_jobs(now: datetime | None = None) -> list[dict]:
    now = now or datetime.now(timezone.utc)
    db = SessionLocal()
    try:
        bind_system(db, "scheduler: which jobs are due")
        rows = {row.job: row for row in db.query(SchedulerRun).all()}
    finally:
        db.close()
    outcomes = []
    for job in JOBS:
        if _due(rows.get(job.name), job, now):
            outcome = run_job(job, now)
            if outcome is not None:
                outcomes.append(outcome)
    return outcomes


def serve(poll_seconds: float = 30.0, stop=None) -> None:
    """Run due jobs every ``poll_seconds`` until ``stop()`` returns true (forever by default)."""
    logger.info("Scheduler started with %d jobs", len(JOBS))
    while not (stop and stop()):
        try:
            run_due_jobs()
        except Exception:  # the database may be briefly unavailable; try again next cycle
            logger.exception("Scheduler cycle failed")
        time.sleep(poll_seconds)
