"""Wording of sample records written before 0.10.66, brought to today's wording in running trials (J18, V6).

``refresh_trial_story.py`` calls ``reword_sample`` with ``apply=False`` (it counts) and then ``apply=True``; it is
idempotent: a record already worded as today is left alone. Two kinds of record:

- the sample's open request to SAMPLE-RV-08's reporter, which named the US questions by code (US2A, US2B ...);
- a first contact's follow-up task, whose title listed every question ("ask about question 1, question 2, ...") and
  now says how many are open (the questions stay in the task's details);
- a reply-due task, whose title carried the MDARIX ID and the whole request ("Reply due from Reporter of SAMPLE-RV-08
  (ward nurse, fictional) on CMP000036: Ask the reporter: ...") and now names who owes the reply.

Reminders already raised (due_alerts) carry the title they were raised with, and are reworded the same way.
"""

from __future__ import annotations

import re

from sqlalchemy.orm import Session

from backend.app.business_ids import complaint_ref
from backend.app.communications.service import TASK_TYPE as REPLY_DUE
from backend.app.communications.service import reply_title
from backend.app.db.models.foundation import Complaint
from backend.app.db.models.guides_communications import CommunicationEntry
from backend.app.db.models.oversight import DueAlert
from backend.app.db.models.workflow import WorkflowTask
from backend.app.intake.service import FOLLOW_UP, SOURCE_TYPE
from backend.app.trial.sample_guides import RV08_REQUEST, RV08_REQUEST_BEFORE

_OLD_FOLLOW_UP = re.compile(
    r"^Follow up (?P<ref>.+) with the reporter: ask (?:about (?P<asks>.+)|whether any deficiency is alleged)$"
)


def follow_up_title(title: str) -> str | None:
    """The new title for an old follow-up task's title, or None when it is not one."""
    found = _OLD_FOLLOW_UP.match(title or "")
    if not found:
        return None
    if found.group("asks") is None:
        return f"Follow up {found.group('ref')} with the reporter: is a deficiency alleged?"
    count = len(found.group("asks").split(", "))
    return f"Follow up {found.group('ref')} with the reporter: {count} open question{'s' if count != 1 else ''}"


_OLD_REPLY = re.compile(r"^Reply due from (?P<party>.+?)(?: on (?P<ref>[^:]+))?: .+$")


def new_reply_title(title: str, ref: str | None) -> str | None:
    """The new title for an old reply-due title (with the request after a colon), or None when it is not one."""
    found = _OLD_REPLY.match(title or "")
    return reply_title(found.group("party"), ref) if found else None


def _title(db: Session, title: str, complaint_id) -> str | None:
    if (title or "").startswith("Reply due from "):
        complaint = db.get(Complaint, complaint_id) if complaint_id else None
        return new_reply_title(title, complaint_ref(complaint) if complaint is not None else None)
    return follow_up_title(title)


def reword_sample(db: Session, tenant_id, apply: bool) -> int:
    """How many records carry the old wording; with ``apply`` they are reworded (the caller commits)."""
    entries = (
        db.query(CommunicationEntry)
        .filter(CommunicationEntry.tenant_id == tenant_id, CommunicationEntry.subject == RV08_REQUEST_BEFORE)
        .all()
    )
    tasks = [
        (task, follow_up_title(task.title))
        for task in db.query(WorkflowTask).filter(
            WorkflowTask.tenant_id == tenant_id,
            WorkflowTask.task_type == FOLLOW_UP,
            WorkflowTask.source_entity_type == SOURCE_TYPE,
            WorkflowTask.title.like("Follow up % with the reporter: ask %"),
        )
    ]
    tasks = [(task, title) for task, title in tasks if title]
    replies = [
        (task, _title(db, task.title, (task.details or {}).get("complaint_id")))
        for task in db.query(WorkflowTask).filter(
            WorkflowTask.tenant_id == tenant_id,
            WorkflowTask.task_type == REPLY_DUE,
            WorkflowTask.title.like("Reply due from %: %"),
        )
    ]
    alerts = [
        (alert, _title(db, alert.title, alert.complaint_id))
        for alert in db.query(DueAlert).filter(
            DueAlert.tenant_id == tenant_id,
            (DueAlert.title.like("Reply due from %: %"))
            | (DueAlert.title.like("Follow up % with the reporter: ask %")),
        )
    ]
    tasks += [(row, title) for row, title in replies + alerts if title]
    if apply:
        for entry in entries:
            entry.subject = RV08_REQUEST
        for task, title in tasks:
            task.title = title
    return len(entries) + len(tasks)
