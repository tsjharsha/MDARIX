"""The sample's absence, event owners and first reminders (T-G25, T-G28, T-G9; T-SAM for 0.10.60).

- **An away colleague:** the MDARIX sample author is away from two days ago for a week (a supplier audit, fictional),
  with the trial's first user as the backup: the sample author's items (the RV-07 EU report not started, the RV-10
  India report waiting for its correction, RV-08's unsigned US assessment) send their reminders and escalations to
  the backup while the absence lasts. Ownership stays with the sample author.
- **Two events with an owner:** SAMPLE-RV-08 (not ready to close: the US assessment unsigned, the reporter's reply
  overdue, the decision not signed) and SAMPLE-RT-03 (a service-level close whose checklist is clear: its owner signs
  "ready to close in the QMS"), both owned by the trial's first user.
- **The first reminders:** nothing is swept here (the trial's user is not active yet); the first visit to My Work or
  the oversight view raises them: the overdue reply on SAMPLE-RV-08 (escalated: nobody else can be reached until a
  colleague joins), the overdue QMS-complaint task of SAMPLE-CALL-02 (escalated to the Leader), and the triage items
  due within 24 hours.

No complaint is added: every count stays. The absence and the event rows are marked ``MDARIX_SAMPLE``; sample removal
takes them (the alerts with the complaints they name). Idempotent; flushes but never commits.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from backend.app.trial.sample_data import SAMPLE_SOURCE

logger = logging.getLogger("mdarix.trial.sample_oversight")
EVENTS = ("SAMPLE-RV-08", "SAMPLE-RT-03")
AWAY_NOTE = "Sample: at a supplier audit (fictional)."


def has_sample_oversight(db: Session, tenant_id) -> bool:
    from backend.app.db.models.oversight import UserAbsence

    return (
        db.query(UserAbsence.id)
        .filter(UserAbsence.tenant_id == tenant_id, UserAbsence.source_system == SAMPLE_SOURCE)
        .first()
        is not None
    )


def stage_sample_oversight(db: Session, tenant_id, now: datetime | None = None, owner_id: str | None = None) -> dict:
    """Add the sample's absence and event owners (see the module docstring)."""
    from backend.app.db.models.foundation import Complaint
    from backend.app.db.models.oversight import EventClosure, UserAbsence
    from backend.app.trial.sample_decision import sample_author
    from backend.app.trial.sample_guides import trial_owner

    now = now or datetime.now(timezone.utc)
    if has_sample_oversight(db, tenant_id):
        return {"created": False, "why": "ALREADY_STAGED"}
    owner = owner_id or trial_owner(db, tenant_id)
    if owner is None:
        return {"created": False, "why": "NO_TRIAL_USER"}
    savepoint = db.begin_nested()
    try:
        author = str(sample_author(db, tenant_id, now).id)
        today = now.date()
        db.add(
            UserAbsence(
                id=uuid.uuid4(),
                tenant_id=tenant_id,
                user_id=author,
                starts_on=today - timedelta(days=2),
                ends_on=today + timedelta(days=5),
                backup_id=owner,
                note=AWAY_NOTE,
                source_system=SAMPLE_SOURCE,
                created_by=author,
                created_at=now,
            )
        )
        events = 0
        for complaint in db.query(Complaint).filter(
            Complaint.tenant_id == tenant_id,
            Complaint.source_system == SAMPLE_SOURCE,
            Complaint.complaint_identifier.in_(EVENTS),
        ):
            db.add(
                EventClosure(
                    id=uuid.uuid4(),
                    tenant_id=tenant_id,
                    complaint_id=complaint.id,
                    owner_id=owner,
                    owner_set_by=author,
                    owner_set_at=now,
                    version=0,
                    source_system=SAMPLE_SOURCE,
                    updated_at=now,
                )
            )
            events += 1
        db.flush()
        savepoint.commit()
    except Exception:
        savepoint.rollback()
        logger.exception("Trial sample absence and events could not be staged")
        return {"created": False, "why": "ERROR"}
    return {"created": True, "events": events}
