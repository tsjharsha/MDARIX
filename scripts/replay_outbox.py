"""Put one dead-lettered outbox event back in the queue, from the command line (operators).

    python scripts/replay_outbox.py EVENT_UUID --reason "SMTP credentials fixed"

The console (Platform Admin > Operations > Dead letters > Retry) is the normal path; this does the same thing for an
operator without the console: the event gets a fresh set of retries, and an audit record in its organization names
the event (not its payload) and the reason. Only an event that is actually dead-lettered is replayed.
"""

from __future__ import annotations

import argparse
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.app.db.models.stage2 import OutboxEvent  # noqa: E402
from backend.app.db.session import SessionLocal  # noqa: E402
from backend.app.db.tenant_scope import bind_system  # noqa: E402
from backend.app.enterprise_audit import make_audit_event  # noqa: E402


def replay(db, event_id: uuid.UUID, reason: str, actor_ref: str = "operator:replay_outbox") -> OutboxEvent:
    """Re-queue the dead-lettered event with a fresh set of retries and audit it; raises ValueError otherwise."""
    bind_system(db, "replay a dead-lettered outbox event")
    row = db.query(OutboxEvent).filter(OutboxEvent.id == event_id).with_for_update().one_or_none()
    if row is None:
        raise ValueError("OUTBOX_EVENT_NOT_FOUND")
    if row.dead_lettered_at is None:
        raise ValueError("OUTBOX_EVENT_NOT_DEAD_LETTERED")
    now = datetime.now(timezone.utc)
    db.add(
        make_audit_event(
            tenant_id=row.tenant_id,
            actor_ref=actor_ref,
            action="OUTBOX_EVENTS_RETRIED",
            entity_type="OutboxEvent",
            entity_id=row.id,
            details={"source": "OPERATOR_SCRIPT", "count": 1, "event_name": row.event_name, "attempts": row.attempts},
            reason=reason,
            created_at=now,
        )
    )
    row.dead_lettered_at = None
    row.attempts = 0
    row.next_attempt_at = now
    row.last_error = None
    row.claimed_by = None
    row.claimed_at = None
    db.commit()
    return row


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Replay one dead-lettered outbox event.")
    parser.add_argument("event_id", type=uuid.UUID)
    parser.add_argument("--reason", required=True, help="why it is safe to retry now (at least 10 characters)")
    args = parser.parse_args(argv)
    if len(args.reason.strip()) < 10:
        parser.error("--reason must be at least 10 characters")
    db = SessionLocal()
    try:
        row = replay(db, args.event_id, args.reason.strip())
    except ValueError as exc:
        db.rollback()
        print({"status": "REFUSED", "code": str(exc)}, flush=True)
        return 1
    finally:
        db.close()
    print({"status": "REPLAY_QUEUED", "event_id": str(row.id)}, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
