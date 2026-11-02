"""Day 0 is calm: the sample shows only the story's alerts (quality plan stage 3, J2, J30).

Before 0.10.64 a new trial's bell held 12 alerts (ten triage targets due within the day, a QMS-complaint task
"overdue 6 days" and more), and the next day every one of them escalated to every Leader. Now the sample author has
already done what the story does not need open:

- **Triage:** every flagged sample record has a finished triage record, except the urgent intake SAMPLE-URG-01 and
  the flagship SAMPLE-RV-11 (the story's two triage steps).
- **Tasks:** the first-contact tasks the sample author left (SAMPLE-CALL-02's QMS complaint never linked, the
  follow-ups) are due two working days from the story's day, never overdue on day 0. The overdue reply on SAMPLE-RV-08
  stays: it is the story's escalation, and it goes to the trial owner (oversight/service.py).
- **RV-09:** the finished US report's event was signed ready to close and its decision record filed before it was
  closed, so it is "Closed in the QMS", not "closed before it was ready".

Every row is marked ``MDARIX_SAMPLE`` or hangs off a sample record, so sample removal takes it. Idempotent (the RV-09
closure is the marker); flushes but never commits.
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from backend.app.trial.sample_data import FLAGSHIP, SAMPLE_SOURCE

logger = logging.getLogger("mdarix.trial.sample_calm")
# The story's own triage steps: they stay open.
STORY_TRIAGE = ("SAMPLE-URG-01", FLAGSHIP)
CLOSED_EVENT = "SAMPLE-RV-09"
TASK_DAYS = 2


def _rv09(db: Session, tenant_id):
    from backend.app.db.models.foundation import Complaint

    return (
        db.query(Complaint)
        .filter(
            Complaint.tenant_id == tenant_id,
            Complaint.source_system == SAMPLE_SOURCE,
            Complaint.complaint_identifier == CLOSED_EVENT,
        )
        .first()
    )


def has_calm_story(db: Session, tenant_id) -> bool:
    from backend.app.db.models.oversight import EventClosure

    complaint = _rv09(db, tenant_id)
    return (
        complaint is None
        or db.query(EventClosure.id)
        .filter(EventClosure.tenant_id == tenant_id, EventClosure.complaint_id == complaint.id)
        .first()
        is not None
    )


def stage_calm_story(db: Session, tenant_id, now: datetime | None = None) -> dict:
    """Finish what the story does not need open (see the module docstring)."""
    now = now or datetime.now(timezone.utc)
    if has_calm_story(db, tenant_id):
        return {"created": False, "why": "ALREADY_STAGED"}
    savepoint = db.begin_nested()
    try:
        counts = {"triage_records": _finish_triage(db, tenant_id, now), "tasks": _tasks_due_later(db, tenant_id, now)}
        counts["closed_ready"] = _rv09_closed_ready(db, tenant_id, now)
        db.flush()
        savepoint.commit()
    except Exception:
        savepoint.rollback()
        logger.exception("The calm sample story could not be staged")
        return {"created": False, "why": "ERROR"}
    return {"created": True, **counts}


def _finish_triage(db: Session, tenant_id, now: datetime) -> int:
    from backend.app.db.models.intake import TriageRecord
    from backend.app.intake import rules, service
    from backend.app.trial.sample_decision import sample_author

    author = str(sample_author(db, tenant_id, now).id)
    records = service.triage_records(db, tenant_id)
    done = 0
    for key, subject in service.subjects(db, tenant_id, records, now).items():
        name = subject.get("identifier") or subject["ref"]
        if not subject.get("sample") or name in STORY_TRIAGE or not service._listed(subject, records.get(key)):
            continue
        opened = min(subject["available_at"], now)
        record = records.get(key)
        if record is None:
            record = TriageRecord(
                tenant_id=tenant_id,
                subject_kind=key[0],
                subject_id=key[1],
                opened_at=opened,
                target_hours=rules.TRIAGE_TARGET_HOURS,
                source_system=SAMPLE_SOURCE,
                created_by=author,
                created_at=opened,
            )
            db.add(record)
        elif record.completed_at is not None:
            continue
        record.event_owner = record.event_owner or author
        record.triage_owner = record.triage_owner or author
        record.no_action_reason = record.no_action_reason or (
            "Sample: triaged by the MDARIX sample author; no immediate action needed beyond the complaint's own steps."
        )
        record.completed_by, record.completed_at, record.updated_at = author, now, now
        done += 1
    db.flush()
    return done


def _tasks_due_later(db: Session, tenant_id, now: datetime) -> int:
    """The sample author's first-contact tasks are due two working days from now (never overdue on day 0)."""
    from backend.app.db.models.intake import IntakeEvent
    from backend.app.db.models.workflow import OPEN_TASK_STATUSES, WorkflowTask
    from backend.app.intake import service
    from backend.app.oversight.service import calendar_of

    events = [
        row.id
        for row in db.query(IntakeEvent.id).filter(
            IntakeEvent.tenant_id == tenant_id, IntakeEvent.source_system == SAMPLE_SOURCE
        )
    ]
    if not events:
        return 0
    due = calendar_of(db, tenant_id).working_day_end(now, TASK_DAYS)
    moved = 0
    for task in db.query(WorkflowTask).filter(
        WorkflowTask.tenant_id == tenant_id,
        WorkflowTask.source_entity_id.in_(events),
        WorkflowTask.task_type.in_(list(service.TASK_TYPES)),
        WorkflowTask.status.in_(list(OPEN_TASK_STATUSES)),
    ):
        if task.due_at is None or task.due_at < due:
            task.due_at = due
            moved += 1
    db.flush()
    return moved


def _rv09_closed_ready(db: Session, tenant_id, now: datetime) -> int:
    from backend.app.db.models.foundation import SignedApprovalRecord
    from backend.app.db.models.oversight import EventClosure
    from backend.app.human_decision.rules import signature_hash
    from backend.app.oversight import closure
    from backend.app.trial.sample_decision import SAMPLE_AUTHOR_ROLE, sample_author

    complaint = _rv09(db, tenant_id)
    if complaint is None:
        return 0
    author = str(sample_author(db, tenant_id, now).id)
    # Signed ready to close the day before it was closed (its report is the finished US example, sample_reports.py).
    signed = (complaint.updated_at or now) - timedelta(days=1)
    row = EventClosure(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        complaint_id=complaint.id,
        owner_id=author,
        owner_set_by=author,
        owner_set_at=signed,
        version=1,
        source_system=SAMPLE_SOURCE,
        updated_at=signed,
    )
    db.add(row)
    db.flush()
    print_ = closure.fingerprint(complaint.id, [])
    record = SignedApprovalRecord(
        id=uuid.uuid4(),
        tenant_id=tenant_id,
        object_type=closure.OBJECT_TYPE,
        object_id=row.id,
        object_version="v1",
        decision_type=closure.DECISION_TYPE,
        decision="APPROVED",
        remarks="Sample: a finished example signed by the MDARIX sample author",
        signer_user_id=author,
        signer_role=SAMPLE_AUTHOR_ROLE,
        signature_meaning=closure.signature_meaning(complaint.complaint_identifier, 1, 0),
        content_fingerprint=print_,
        signature_hash=signature_hash(print_, author, "v1"),
        status="SIGNED",
        signed_at=signed,
        created_at=signed,
    )
    db.add(record)
    row.ready_state, row.checklist, row.content_fingerprint = "READY", [], print_
    row.signed_record_id, row.signed_by, row.signed_at = record.id, author, signed
    row.qms_filing_ref, row.filed_by, row.filed_at = "QMS-CLOSE-SAMPLE-09 (Sample)", author, signed
    db.flush()
    return 1
