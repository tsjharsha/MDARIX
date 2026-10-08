"""The transactional-outbox worker: claims due events one at a time, delivers them and records the outcome.

Each event is handled in its own transaction: the row is locked (``FOR UPDATE SKIP LOCKED``, so two workers never
take the same event), delivered, updated and committed before the next one is touched. A worker killed mid-batch
therefore never re-sends what it already sent, and a shutdown request is honoured between events, after the current
one is finished.

Retries back off exponentially from ``MDARIX_OUTBOX_BASE_DELAY_SECONDS`` (30 s) doubling to
``MDARIX_OUTBOX_MAX_DELAY_SECONDS`` (1 hour), for ``MDARIX_OUTBOX_MAX_ATTEMPTS`` (12) attempts in all, about five
hours, long enough to ride out a mail provider outage. After the last attempt the event is dead-lettered and
alerted once (backend/app/alerts.py); platform administrators retry or discard dead letters from the console.
"""

import logging
import os
import threading
import time
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone

from backend.app.db.models.stage2 import OutboxEvent
from backend.app.db.session import SessionLocal
from backend.app.db.tenant_scope import bind_system
from backend.app.deployment_role import served_tenants_clause

logger = logging.getLogger(__name__)

DEFAULT_MAX_ATTEMPTS = 12
DEFAULT_BASE_DELAY_SECONDS = 30
DEFAULT_MAX_DELAY_SECONDS = 3600


def _env_int(name: str, default: int, minimum: int = 1) -> int:
    try:
        return max(minimum, int(os.getenv(name, "").strip() or default))
    except ValueError:
        return default


def describe_failure(exc: Exception) -> str:
    """What went wrong, for the operator: the error type and its message with anything secret-like removed."""
    from genai.provider import SENSITIVE

    message = SENSITIVE.sub(lambda match: match.group(1) + ": [REDACTED]", str(exc)).strip()
    return f"{type(exc).__name__}: {message[:300]}" if message else type(exc).__name__


@dataclass
class WorkerMetrics:
    cycles: int = 0
    published: int = 0
    failed: int = 0
    dead_lettered: int = 0
    last_cycle_at: str | None = None
    last_error: str | None = None
    heartbeat_at: str | None = None
    stale_recovered: int = 0

    def snapshot(self):
        return asdict(self)


def _due_filter(now: datetime):
    return (
        OutboxEvent.published_at.is_(None),
        OutboxEvent.dead_lettered_at.is_(None),
        (OutboxEvent.next_attempt_at.is_(None) | (OutboxEvent.next_attempt_at <= now)),
    )


class OutboxWorker:
    def __init__(
        self,
        publisher,
        max_attempts: int | None = None,
        base_delay_seconds: int | None = None,
        alert=None,
        max_delay_seconds: int | None = None,
        should_stop=None,
    ):
        self.max_attempts = (
            max_attempts if max_attempts is not None else _env_int("MDARIX_OUTBOX_MAX_ATTEMPTS", DEFAULT_MAX_ATTEMPTS)
        )
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be positive")
        self.publisher = publisher
        self.base_delay_seconds = (
            base_delay_seconds
            if base_delay_seconds is not None
            else _env_int("MDARIX_OUTBOX_BASE_DELAY_SECONDS", DEFAULT_BASE_DELAY_SECONDS)
        )
        self.max_delay_seconds = (
            max_delay_seconds
            if max_delay_seconds is not None
            else _env_int("MDARIX_OUTBOX_MAX_DELAY_SECONDS", DEFAULT_MAX_DELAY_SECONDS)
        )
        self.alert = alert
        # Checked between events: a SIGTERM finishes the event in hand, then stops (scripts/run_outbox_worker.py).
        self.should_stop = should_stop or (lambda: False)
        self.metrics = WorkerMetrics()
        self.worker_id = str(uuid.uuid4())

    def retry_delay(self, attempts: int) -> timedelta:
        """How long to wait after the ``attempts``-th failure: base, 2x base, 4x base ... capped at the maximum."""
        return timedelta(seconds=min(self.max_delay_seconds, self.base_delay_seconds * 2 ** max(0, attempts - 1)))

    def process_once(self, limit=50):
        """Deliver up to ``limit`` due events, each in its own transaction. Returns the cycle's counts."""
        db = SessionLocal()
        bind_system(db, "outbox worker: claim and deliver due events of every tenant")
        now = datetime.now(timezone.utc)
        stats = {"published": 0, "failed": 0, "dead_lettered": 0, "stale_recovered": 0}
        try:
            # Candidates first, without locks: each is re-checked and locked on its own when its turn comes, so a
            # row another worker took meanwhile is simply skipped.
            candidates = [
                row[0]
                for row in db.query(OutboxEvent.id)
                # A cell delivers its own organization's events only (backend/app/deployment_role.py).
                .filter(*_due_filter(now), served_tenants_clause(OutboxEvent.tenant_id))
                .order_by(OutboxEvent.occurred_at)
                .limit(limit)
                .all()
            ]
            db.commit()
            for event_id in candidates:
                if self.should_stop():
                    break
                self._deliver_one(db, event_id, stats)
            self.metrics.cycles += 1
            self.metrics.published += stats["published"]
            self.metrics.failed += stats["failed"]
            self.metrics.dead_lettered += stats["dead_lettered"]
            self.metrics.last_cycle_at = now.isoformat()
            self.metrics.heartbeat_at = now.isoformat()
            return stats
        finally:
            db.close()

    def _deliver_one(self, db, event_id, stats: dict) -> None:
        now = datetime.now(timezone.utc)
        row = (
            db.query(OutboxEvent)
            .filter(OutboxEvent.id == event_id, *_due_filter(now))
            .with_for_update(skip_locked=True)
            .one_or_none()
        )
        if row is None:  # delivered, dead-lettered or locked by another worker since we listed it
            db.rollback()
            return
        row.claimed_by = self.worker_id
        row.claimed_at = now
        try:
            self.publisher(row.event_name, row.payload)
        except Exception as exc:
            self._record_failure(row, exc, now, stats)
        else:
            row.published_at = now
            row.next_attempt_at = None
            row.last_error = None
            row.claimed_by = None
            row.claimed_at = None
            stats["published"] += 1
        # One event, one commit: whatever happens next, this outcome is on record and cannot be redone.
        db.commit()

    def _record_failure(self, row, exc: Exception, now: datetime, stats: dict) -> None:
        row.attempts += 1
        row.last_error = describe_failure(exc)
        stats["failed"] += 1
        self.metrics.last_error = row.last_error
        logger.warning("outbox delivery failed event=%s attempt=%s", row.id, row.attempts)
        if row.attempts < self.max_attempts:
            row.next_attempt_at = now + self.retry_delay(row.attempts)
            return
        row.dead_lettered_at = now
        row.next_attempt_at = None
        row.claimed_by = None
        row.claimed_at = None
        stats["dead_lettered"] += 1
        logger.error("outbox dead-letter alert event=%s attempts=%s", row.id, row.attempts)
        if self.alert is None:
            return
        try:
            self.alert(
                {
                    "type": "OUTBOX_DEAD_LETTERED",
                    "event_id": str(row.id),
                    "event_name": row.event_name,
                    "attempts": row.attempts,
                    "error": row.last_error,
                }
            )
        except Exception as alert_exc:
            self.metrics.last_error = f"{type(alert_exc).__name__}: alert delivery failed"
            logger.exception("outbox alert delivery failed event=%s", row.id)

    def recover_stale_claims(self, timeout_seconds: int = 300) -> int:
        """Return abandoned claims to the queue after a crashed worker."""
        if timeout_seconds < 1:
            raise ValueError("timeout_seconds must be positive")
        db = SessionLocal()
        bind_system(db, "outbox worker: return abandoned claims to the queue")
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(seconds=timeout_seconds)
        try:
            rows = (
                db.query(OutboxEvent)
                .filter(
                    OutboxEvent.published_at.is_(None),
                    OutboxEvent.dead_lettered_at.is_(None),
                    OutboxEvent.claimed_at.is_not(None),
                    OutboxEvent.claimed_at < cutoff,
                )
                .with_for_update(skip_locked=True)
                .all()
            )
            for row in rows:
                row.claimed_by = None
                row.claimed_at = None
                row.next_attempt_at = now
                row.last_error = "STALE_WORKER_CLAIM_RECOVERED"
            db.commit()
            self.metrics.stale_recovered += len(rows)
            self.metrics.heartbeat_at = now.isoformat()
            return len(rows)
        finally:
            db.close()

    def run_forever(self, *, limit=50, interval_seconds=5, stop=None, shutdown: threading.Event | None = None):
        """Drain the outbox until ``shutdown`` is set (immediately, even mid-wait) or ``stop()`` returns true."""
        shutdown = shutdown or threading.Event()
        stopped = stop or (lambda: False)
        previous_should_stop = self.should_stop
        self.should_stop = lambda: shutdown.is_set() or stopped() or previous_should_stop()
        logger.info("outbox worker started batch_size=%s interval_seconds=%s", limit, interval_seconds)
        try:
            while not self.should_stop():
                started = time.monotonic()
                self.recover_stale_claims()
                stats = self.process_once(limit=limit)
                logger.info(
                    "outbox metrics=%s cycle_published=%s cycle_failed=%s cycle_dead_lettered=%s duration_ms=%s",
                    self.metrics.snapshot(),
                    stats["published"],
                    stats["failed"],
                    stats["dead_lettered"],
                    int((time.monotonic() - started) * 1000),
                )
                if self.should_stop():
                    break
                shutdown.wait(max(0, interval_seconds))
        finally:
            self.should_stop = previous_should_stop
        logger.info("outbox worker stopped gracefully")

    @staticmethod
    def replay(db, event_id):
        """Make one dead-lettered event eligible for a controlled replay."""
        row = db.query(OutboxEvent).filter(OutboxEvent.id == event_id).with_for_update().one_or_none()
        if row is None:
            raise ValueError("OUTBOX_EVENT_NOT_FOUND")
        row.dead_lettered_at = None
        row.next_attempt_at = datetime.now(timezone.utc)
        row.last_error = None
        row.claimed_by = None
        row.claimed_at = None
        db.commit()
        logger.warning("outbox replay requested event=%s", event_id)
        return row
