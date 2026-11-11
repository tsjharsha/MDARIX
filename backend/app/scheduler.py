"""Scheduled jobs: what runs, how often, and the run loop (``python scripts/run_scheduler.py``).

Each job runs when its interval has passed since it last finished. A Postgres advisory lock per job means two
scheduler instances never run the same job at once, so running a spare instance is safe. Every run is recorded in
``scheduler_runs`` (status, result, error type); a job that fails three times in a row raises an alert, and so does
its recovery. Jobs run in system scope and record their own audit events.

The loop itself is watched three ways: it touches a heartbeat file every cycle (``MDARIX_SCHEDULER_HEARTBEAT_FILE``,
the container health check reads it), it alerts when any job has not run within twice its interval (another
instance holding the lock, or one slow job starving the rest) and, when ``MDARIX_SCHEDULER_HEARTBEAT_URL`` is set,
the operations-alerts job pings that dead-man's-switch so an outside monitor notices a scheduler that stopped.
"""

from __future__ import annotations

import logging
import os
import threading
import time
import traceback
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable
from urllib import request as urlrequest

from sqlalchemy import text
from sqlalchemy.orm import Session

from backend.app.alerts import send_alert
from backend.app.db.models.stage2 import SchedulerRun
from backend.app.db.session import SessionLocal, engine
from backend.app.db.tenant_scope import bind_system
from backend.app.deployment_role import CELL, MULTI, PLATFORM, ROLES, deployment_role, served_tenants_clause

logger = logging.getLogger("mdarix.scheduler")
ACTOR = "system:scheduler"
ALERT_AFTER_FAILURES = 3
# A job that has not started or finished within this many of its intervals is "missed".
MISSED_AFTER_INTERVALS = 2
DEFAULT_HEARTBEAT_FILE = "/tmp/mdarix-scheduler-heartbeat"
# Which deployments run a job (backend/app/deployment_role.py): the platform owns customers, licences and trials,
# a cell owns its organization's records, and some jobs watch the deployment itself.
PLATFORM_JOBS = frozenset({MULTI, PLATFORM})
CELL_JOBS = frozenset({MULTI, CELL})


@dataclass(frozen=True)
class Job:
    name: str
    every: timedelta
    run: Callable[[Session, dict], dict]
    description: str
    roles: frozenset[str] = ROLES


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
    if result["failed"]:
        names = ", ".join(f"{item.get('tenant_key')} ({item['error']})" for item in result["failed"])
        send_alert(
            "Trial data could not be deleted",
            f"{len(result['failed'])} ended trial(s) still hold data past the retention period: {names}. "
            "Nothing was changed for them; see the scheduler log.",
        )
        raise RuntimeError(f"{len(result['failed'])} trial purge(s) failed")
    return {
        "purged": result["purged"],
        "tenants": [item.get("tenant_key") for item in result["trials"]],
        # Trial requests that never became a trial, erased after their 90 days (backend/app/trial/retention.py).
        "requests_erased": result["requests"]["erased"],
        # Trials kept because the organization asked to move their data into the MVP, and alerts sent about them.
        "held_for_mvp_request": sum(1 for item in result["skipped"] if item.get("why") == "MVP_REQUEST"),
        "hold_alerts": result.get("hold_alerts", 0),
        # Error reports sent before sign-in, deleted after their 90 days (backend/app/client_errors.py).
        "error_reports_deleted": result.get("error_reports_deleted", 0),
    }


def trial_reminders(db: Session, _state: dict) -> dict:
    from backend.app.notifications import queue_trial_reminders

    return {"queued": queue_trial_reminders(db)}


def trial_sample_clock(db: Session, _state: dict) -> dict:
    """Keep every running trial's sample story current: its events move with the trial's clock until a person works on
    it (backend/app/trial/sample_clock.py). Each trial is committed on its own."""
    from backend.app.trial.sample_clock import run_for_all_trials

    return run_for_all_trials(db)


def embedding_catch_up(db: Session, _state: dict) -> dict:
    """Embed evidence that has none yet (records imported while the API restarted, or a failed background step).
    An organization whose import's embeddings are still queued or under way in the outbox worker is left to that job
    (retrieval/record_evidence.py), so the two never embed the same records at once; a dead-lettered job no longer
    holds it back."""
    from backend.app.db.data_plane import open_tenant_data_session
    from backend.app.customer_lifecycle import customer_allows_access_clause
    from backend.app.db.models.foundation import Tenant
    from backend.app.db.models.stage2 import OutboxEvent
    from retrieval.record_evidence import EMBEDDINGS_EVENT
    from retrieval.service import TrustedRetrievalService

    service = TrustedRetrievalService()
    totals = {"tenants": 0, "indexed": 0, "failed": 0, "deferred": 0}
    queued = (
        db.query(OutboxEvent.tenant_id)
        .filter(
            OutboxEvent.event_name == EMBEDDINGS_EVENT,
            OutboxEvent.published_at.is_(None),
            OutboxEvent.dead_lettered_at.is_(None),
            OutboxEvent.tenant_id.is_not(None),  # a NULL would make NOT IN leave out every organization
        )
        .distinct()
    )
    tenant_ids = [
        row.id
        for row in db.query(Tenant.id)
        .filter(
            Tenant.status.in_(["ACTIVE", "active"]),
            customer_allows_access_clause(),
            served_tenants_clause(Tenant.id),
            Tenant.id.notin_(queued),
        )
        .all()
    ]
    for tenant_id in tenant_ids:
        with open_tenant_data_session(tenant_id) as data:
            result = service.index_evidence_chunks(data, tenant_id, limit=500)
        if result["indexed"] or result["failed"] or result["deferred"]:
            totals["tenants"] += 1
        for key in ("indexed", "failed", "deferred"):
            totals[key] += int(result.get(key) or 0)
    return totals


def _ping(url: str, timeout: float) -> None:
    """One GET to the dead-man's-switch URL. Separate so tests can replace the transport."""
    with urlrequest.urlopen(urlrequest.Request(url, headers={"User-Agent": "MDARIX-scheduler/1.0"}), timeout=timeout):
        pass


def ping_heartbeat_url() -> str:
    """Tell the outside monitor (healthchecks.io, Cronitor, ...) the scheduler ran. SENT, FAILED or NOT_CONFIGURED;
    a failure is logged and never fails the job, since the monitor firing is exactly what it is there for."""
    url = os.getenv("MDARIX_SCHEDULER_HEARTBEAT_URL", "").strip()
    if not url:
        return "NOT_CONFIGURED"
    try:
        _ping(url, float(os.getenv("MDARIX_ALERT_TIMEOUT_SECONDS", "10")))
        return "SENT"
    except Exception as exc:
        logger.warning("Scheduler heartbeat URL could not be reached (%s)", type(exc).__name__)
        return "FAILED"


def operations_alerts(db: Session, state: dict) -> dict:
    """Alert when the dead-letter count rises and when the worker stops or recovers; ping the dead-man's switch.

    The worker alerts per event as it dead-letters it; this job is the summary that also catches events dead-lettered
    while alerting itself was broken, so it compares the count with the one it saw last run (kept in ``state``, which
    lives in ``scheduler_runs``). The first run reports everything already in the queue, nothing is assumed seen.
    """
    from backend.app.worker_status import worker_status

    dead = int(db.execute(text("SELECT count(*) FROM event_outbox WHERE dead_lettered_at IS NOT NULL")).scalar() or 0)
    reported_dead = int(state.get("dead_letters") or 0)
    if dead > reported_dead:
        send_alert(
            "Dead-letter queue grew",
            f"{dead - reported_dead} more event(s) are dead-lettered since the last check ({dead} in total). "
            "Review them in Platform Admin > Operations > Dead letters.",
        )
    state["dead_letters"] = dead
    worker = worker_status(db)["state"]
    if worker == "STOPPED" and state.get("worker") != "STOPPED":
        send_alert("Background worker stopped", "No heartbeat from the background worker for over a minute.")
    if worker == "RUNNING" and state.get("worker") == "STOPPED":
        send_alert("Background worker recovered", "The background worker is sending heartbeats again.")
    state["worker"] = worker
    # The queue's lag and failing e-mail (0.10.88, DEV-13): alerted once when they start and once when they clear.
    from backend.app.readiness import OUTBOX_MAX_LAG, outbox_backlog

    backlog = outbox_backlog(db)
    lagging = backlog["lag_seconds"] > OUTBOX_MAX_LAG.total_seconds()
    if lagging != bool(state.get("lagging")):
        send_alert(
            "Outbox falling behind" if lagging else "Outbox caught up",
            f"The oldest event due to be published has waited {backlog['lag_seconds']} s ({backlog['waiting']} waiting)."
            if lagging
            else "Events are being published again without delay.",
        )
    failing = backlog["email_failing"] > 0
    if failing != bool(state.get("email_failing")):
        send_alert(
            "E-mail delivery failing" if failing else "E-mail delivery recovered",
            f"{backlog['email_failing']} e-mail(s) were refused by the provider and are being retried. Check the SMTP "
            "provider and its settings; the readiness check shows email as failing meanwhile."
            if failing
            else "The e-mails waiting to be retried have gone out.",
        )
    state["lagging"], state["email_failing"] = lagging, failing
    # B6a G19: the clock check (app vs database vs NTP within 1 s), alerted once and once when it clears.
    from backend.app import clock_check

    clock = clock_check.check()
    clock_check.alert(state, clock, send_alert)
    return {
        "dead_letters": dead,
        "worker": worker,
        "outbox": backlog,
        "clock": clock["state"],
        "heartbeat_url": ping_heartbeat_url(),
    }


def connector_sync(db: Session, _state: dict) -> dict:
    from backend.app.access.connector_sync import run_scheduled_syncs

    return run_scheduled_syncs(db)


def support_access_expiry(db: Session, _state: dict) -> dict:
    """Close support access whose window passed, audit it and email the organization that it ended. Access itself
    ends at the second it expires (support_access.evaluate); this records it and tells the customer."""
    from backend.app.support_access import expire

    return {"closed": expire(db)}


def export_expiry(db: Session, _state: dict) -> dict:
    from backend.app.tenant_export import expire_exports

    return {"expired": expire_exports(db)}


def purge_completion(db: Session, state: dict) -> dict:
    """Finish organization deletions left PURGING (files or a dedicated database that could not be deleted at the
    time; backend/app/tenant_purge.py). An organization under a legal hold is skipped, never forced. An operator is
    alerted once while a deletion stays incomplete, and again only if the list of incomplete deletions changes."""
    from backend.app.tenant_purge import complete_pending_purges

    summary = complete_pending_purges(db, "system:scheduler")
    stuck = sorted(
        str(item.get("tenant_id") or item) for item in summary.get("incomplete", []) + summary.get("failed", [])
    )
    if stuck and stuck != state.get("reported_incomplete"):
        send_alert(
            "Organization deletion still incomplete",
            f"{len(stuck)} organization deletion(s) could not be finished: {', '.join(stuck)}. "
            "Check object storage and dedicated databases, then run scripts/complete_tenant_purge.py "
            "(docs/runbooks/DATA_REQUESTS.md).",
        )
    state["reported_incomplete"] = stuck
    return {key: len(value) for key, value in summary.items() if isinstance(value, list)}


def audit_chain_verification(db: Session, state: dict) -> dict:
    """Recompute every organization's audit hash chain from its last verified anchor; alert on any break."""
    from backend.app.audit_chain import verify_all

    result = verify_all(db, state)
    reported = set(state.get("reported_broken") or [])
    new = [item for item in result["broken"] if f"{item['tenant_id']}:{item['seq']}" not in reported]
    if new:
        send_alert(
            "Audit trail integrity check failed",
            f"The audit hash chain of {len(new)} organization(s) no longer verifies: "
            + ", ".join(f"{item['tenant_id']} ({item['reason']} at #{item['seq']})" for item in new)
            + ". Treat as a security incident: preserve the database and logs and investigate before any change.",
        )
    state["reported_broken"] = sorted(reported | {f"{item['tenant_id']}:{item['seq']}" for item in result["broken"]})
    return result


def signal_detection(db: Session, _state: dict) -> dict:
    """The complaint threshold rule for every active organization, on the shared plane or its own database
    (backend/app/signals/detection.py); each organization is committed on its own."""
    from backend.app.signals.detection import run_for_all_tenants

    return run_for_all_tenants(db)


def late_evidence_sweep(db: Session, _state: dict) -> dict:
    """Impact assessments for evidence ingested for a decided or closed case after its decision was signed, for every
    active organization on the shared plane or its own database (backend/app/decision_followups/impact.py). Idempotent;
    each organization is committed on its own."""
    from backend.app.decision_followups.impact import run_for_all_tenants

    return run_for_all_tenants(db)


def reporting_reminders(db: Session, _state: dict) -> dict:
    """Reminder tasks for reporting clocks due soon or overdue and for CAPA effectiveness checks near their day, for
    every active organization (backend/app/reportability/reminders.py). Idempotent; each organization is committed on
    its own."""
    from backend.app.reportability.reminders import run_for_all_tenants

    return run_for_all_tenants(db)


def due_alerts(db: Session, _state: dict) -> dict:
    """Reminders and escalations of every dated item (triage, reporting deadlines, report obligations, replies due,
    guide approvals, tasks), raised and resolved for every active organization (backend/app/oversight/service.py).
    Idempotent; each organization is committed on its own."""
    from backend.app.oversight.service import run_for_all_tenants

    return run_for_all_tenants(db)


# A signature still PENDING this long after it was asked for is stuck (settlement normally runs every 10 minutes).
SIGNATURE_STUCK_AFTER = timedelta(minutes=30)


def _stuck_signatures(db: Session, older_than: timedelta = SIGNATURE_STUCK_AFTER) -> int:
    from backend.app.db.models.foundation import SignedApprovalRecord
    from backend.app.signing_commit import PENDING

    bind_system(db, "signature settlement: stuck signatures")
    cutoff = datetime.now(timezone.utc) - older_than
    return (
        db.query(SignedApprovalRecord.id)
        .filter(SignedApprovalRecord.status == PENDING, SignedApprovalRecord.created_at <= cutoff)
        .count()
    )


def signature_settlement(db: Session, state: dict) -> dict:
    """Complete or abandon every signature a dedicated plane's signing left PENDING (a restart, a lost connection
    between its two commits): backend/app/signing_commit.py. Idempotent. The operators are alerted once when a
    signature could not be settled or one stays PENDING over 30 minutes, and once when that clears (0.10.88, DEV-13)."""
    from backend.app.signing_commit import settle_pending

    result = settle_pending(db)
    result["stuck"] = _stuck_signatures(db)
    problem = bool(result["failed"]) or result["stuck"] > 0
    if problem and not state.get("alerted"):
        send_alert(
            "Signatures not settled",
            f"{len(result['failed'])} signature(s) could not be settled in this run and {result['stuck']} have been "
            "PENDING for over 30 minutes. A PENDING signature is never shown as valid; the person sees it as being "
            "completed. See the scheduler log (signature-settlement) and docs/runbooks/OUTBOX_AND_SCHEDULER.md.",
        )
    if not problem and state.get("alerted"):
        send_alert("Signatures settled again", "No signature is PENDING for over 30 minutes and none failed to settle.")
    state["alerted"] = problem
    return result


def readiness_digest(db: Session, _state: dict) -> dict:
    """The weekly readiness email for every active organization: queued once per ISO week, from Monday 06:00 UTC
    (backend/app/readiness_home/digest.py); the outbox worker sends it to the quality leads."""
    from backend.app.readiness_home.digest import run_for_all_tenants

    return run_for_all_tenants(db)


def deadline_list(db: Session, _state: dict) -> dict:
    """B6a G18a: each organization's open reporting deadlines, queued once a day from 06:00 organization time
    (backend/app/oversight/deadline_list.py); the outbox worker sends it."""
    from backend.app.oversight.deadline_list import run_for_all_tenants

    return run_for_all_tenants(db)


def platform_sync(db: Session, _state: dict) -> dict:
    """A cell reports to the platform and fetches its licence and packages (backend/app/cell_link.py)."""
    from backend.app import cell_link
    from backend.app.deployment_role import cell_tenant_id, cell_tenant_key

    return cell_link.sync(db, cell_tenant_id(), cell_tenant_key())


JOBS: tuple[Job, ...] = (
    Job(
        "platform-sync",
        timedelta(minutes=15),
        platform_sync,
        "Report to the platform and fetch its licence and packages",
        frozenset({CELL}),
    ),
    Job(
        "tenant-lifecycle",
        timedelta(minutes=15),
        tenant_lifecycle,
        "Apply scheduled tenant status changes",
        PLATFORM_JOBS,
    ),
    Job(
        "subscription-lifecycle",
        timedelta(hours=1),
        subscription_lifecycle,
        "Expiry, grace and renewal reminders",
        PLATFORM_JOBS,
    ),
    Job(
        "trial-reminders",
        timedelta(hours=6),
        trial_reminders,
        "Email trial owners before and when the trial ends",
        PLATFORM_JOBS,
    ),
    Job(
        "trial-retention",
        timedelta(hours=24),
        trial_retention,
        "Delete trial data 30 days after the trial ends (held while its move into the pilot is requested), and error "
        "reports sent before sign-in after 90 days",
        PLATFORM_JOBS,
    ),
    Job(
        "trial-sample-clock",
        timedelta(hours=1),
        trial_sample_clock,
        "Keep each trial's sample story current: its dates move with the trial's clock until someone works on it",
        PLATFORM_JOBS,
    ),
    Job(
        "embedding-catch-up",
        timedelta(minutes=15),
        embedding_catch_up,
        "Embed evidence that has no embedding yet",
        CELL_JOBS,
    ),
    Job(
        "support-access-expiry",
        timedelta(minutes=5),
        support_access_expiry,
        "Close support access whose time ran out and tell the organization",
        PLATFORM_JOBS,
    ),
    Job("operations-alerts", timedelta(minutes=5), operations_alerts, "Alert on dead letters and a stopped worker"),
    Job(
        "export-expiry", timedelta(hours=1), export_expiry, "Delete data exports after their download period", CELL_JOBS
    ),
    Job(
        "connector-sync", timedelta(minutes=15), connector_sync, "Sync connections that have a sync schedule", CELL_JOBS
    ),
    Job(
        "purge-completion",
        timedelta(hours=24),
        purge_completion,
        "Finish organization deletions left incomplete",
        CELL_JOBS,
    ),
    Job(
        "signal_detection",
        timedelta(minutes=60),
        signal_detection,
        "Raise and update signals from new complaints",
        CELL_JOBS,
    ),
    Job(
        "late_evidence_sweep",
        timedelta(minutes=60),
        late_evidence_sweep,
        "Ask for an impact assessment of evidence that reached a decided investigation",
        CELL_JOBS,
    ),
    Job(
        "reporting_reminders",
        timedelta(hours=6),
        reporting_reminders,
        "Remind reviewers of reporting clocks and CAPA effectiveness checks that are due",
        CELL_JOBS,
    ),
    Job(
        "due-alerts",
        timedelta(minutes=15),
        due_alerts,
        "Remind owners of items due soon and escalate overdue ones to their backup and the escalation role",
        CELL_JOBS,
    ),
    Job(
        "signature-settlement",
        timedelta(minutes=10),
        signature_settlement,
        "Complete or abandon signatures a dedicated plane's signing left half-way",
        CELL_JOBS,
    ),
    Job(
        "readiness-digest",
        timedelta(hours=6),
        readiness_digest,
        "Email each organization's quality leads their quality loop once a week",
        CELL_JOBS,
    ),
    Job(
        "deadline-list",
        timedelta(minutes=15),
        deadline_list,
        "Email each organization its open reporting deadlines once a day from 06:00 its time",
        CELL_JOBS,
    ),
    Job(
        "audit-chain-verification",
        timedelta(hours=24),
        audit_chain_verification,
        "Verify every organization's tamper-evident audit trail",
    ),
)


def active_jobs() -> tuple[Job, ...]:
    """The jobs this deployment runs (its role's share of JOBS)."""
    role = deployment_role()
    return tuple(job for job in JOBS if role in job.roles)


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


def _run_rows() -> dict[str, SchedulerRun]:
    db = SessionLocal()
    try:
        bind_system(db, "scheduler: which jobs are due")
        rows = {row.job: row for row in db.query(SchedulerRun).all()}
        db.expunge_all()
        return rows
    finally:
        db.close()


def run_due_jobs(now: datetime | None = None, jobs: tuple[Job, ...] | None = None) -> list[dict]:
    now = now or datetime.now(timezone.utc)
    rows = _run_rows()
    outcomes = []
    for job in active_jobs() if jobs is None else jobs:
        if _due(rows.get(job.name), job, now):
            outcome = run_job(job, now)
            if outcome is not None:
                outcomes.append(outcome)
    return outcomes


# ------------------------------------------------------------------------------------------- watchdog


def heartbeat_file() -> Path:
    return Path(os.getenv("MDARIX_SCHEDULER_HEARTBEAT_FILE", "").strip() or DEFAULT_HEARTBEAT_FILE)


def write_heartbeat(now: datetime | None = None) -> Path | None:
    """Record that the loop is alive: the file holds the time of the last cycle (nothing else), written atomically.
    The container health check compares its age with the poll interval. A failure to write is logged, never fatal."""
    path = heartbeat_file()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(path.name + ".tmp")
        temporary.write_text((now or datetime.now(timezone.utc)).isoformat(), encoding="utf-8")
        temporary.replace(path)
        return path
    except OSError as exc:
        logger.warning("Scheduler heartbeat file %s could not be written (%s)", path, type(exc).__name__)
        return None


def missed_jobs(
    rows: dict[str, SchedulerRun], now: datetime, jobs: tuple[Job, ...] | None = None
) -> list[tuple[Job, float]]:
    """Jobs whose last activity (start or finish) is older than MISSED_AFTER_INTERVALS times their interval, with the
    age in seconds. A job that has never run is not missed: it is due and runs on this cycle."""
    found = []
    for job in active_jobs() if jobs is None else jobs:
        row = rows.get(job.name)
        if row is None:
            continue
        seen = [stamp for stamp in (row.last_started_at, row.last_finished_at) if stamp is not None]
        if not seen:
            continue
        age = (now - max(seen)).total_seconds()
        if age > MISSED_AFTER_INTERVALS * job.every.total_seconds():
            found.append((job, age))
    return found


_missed_reported: set[str] = set()


def check_missed_jobs(now: datetime | None = None, jobs: tuple[Job, ...] | None = None, rows=None) -> list[str]:
    """Alert once when a job becomes missed and once more when it runs again; returns the names currently missed."""
    now = now or datetime.now(timezone.utc)
    rows = _run_rows() if rows is None else rows
    jobs = active_jobs() if jobs is None else jobs
    missed = {job.name: (job, age) for job, age in missed_jobs(rows, now, jobs)}
    for name, (job, age) in missed.items():
        if name not in _missed_reported:
            send_alert(
                f"Scheduled job missed: {name}",
                f"{job.description}. It runs every {job.every} but last ran {int(age // 60)} minutes ago. "
                "Check that the scheduler is running and that no other job is blocking the loop.",
            )
    for name in sorted(_missed_reported - set(missed)):
        job = next((item for item in jobs if item.name == name), None)
        if job is not None:
            send_alert(f"Scheduled job running again: {name}", f"{job.description} has run within its interval.")
    _missed_reported.clear()
    _missed_reported.update(missed)
    return sorted(missed)


def serve(
    poll_seconds: float = 30.0, shutdown: threading.Event | None = None, stop: Callable[[], bool] | None = None
) -> None:
    """Run due jobs every ``poll_seconds`` until ``shutdown`` is set (the signal handlers set it, so the loop ends at
    once instead of finishing a sleep) or ``stop()`` returns true. Every cycle writes the heartbeat file and checks
    for missed jobs; a cycle that fails (the database may be briefly unavailable) is logged and tried again."""
    shutdown = shutdown or threading.Event()
    logger.info(
        "Scheduler started as %s with %d jobs; heartbeat file %s",
        deployment_role(),
        len(active_jobs()),
        heartbeat_file(),
    )
    while not shutdown.is_set() and not (stop and stop()):
        try:
            run_due_jobs()
            check_missed_jobs()
        except Exception:
            logger.exception("Scheduler cycle failed")
        write_heartbeat()
        shutdown.wait(poll_seconds)
    logger.info("Scheduler stopped")
