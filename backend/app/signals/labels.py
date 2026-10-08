"""Signal statuses, origins, dispositions and history events with the labels people read, and the detection rule's
code, label and defaults. The status, priority and origin codes themselves are in backend/app/db/models/signals.py.
"""

from __future__ import annotations

from backend.app.db.models.signals import OPEN_SIGNAL_STATUSES, SIGNAL_PRIORITIES, SIGNAL_STATUSES

# Task source type of a signal's SIGNAL_TRIAGE task (workflow_tasks.source_entity_type), and the task type.
SIGNAL_SOURCE = "Signal"
TRIAGE_TASK = "SIGNAL_TRIAGE"
# Who changed a signal when no person did (the scheduler, an import, the demo seeding).
DETECTION_ACTOR = "system:signal-detection"

STATUS_LABELS: dict[str, str] = {
    "NEW": "New",
    "TRIAGE": "In triage",
    "MONITOR": "Monitoring",
    "NO_ACTION": "No action",
    "DUPLICATE": "Duplicate",
    "MERGED": "Merged",
    "INVESTIGATION_REQUIRED": "Investigation required",
    "ESCALATED": "Escalated",
    "INVESTIGATION_OPEN": "Investigation open",
    "DECISION_RECORDED": "Decision recorded",
    "CLOSED": "Closed",
}

ORIGIN_LABELS: dict[str, str] = {
    "MANUAL": "Created by a person",
    "THRESHOLD_RULE": "Complaint threshold rule",
    "AI_SUGGESTED": "Suggested by AI",
    "IMPORT": "Imported",
}

# Statuses still waiting for someone to triage them (the due date and "overdue" are about triage).
AWAITING_TRIAGE = ("NEW", "TRIAGE")
# What a triage decision can be, and the statuses it may be taken from (an escalated signal can only go on to a case).
DISPOSITIONS = ("MONITOR", "NO_ACTION", "DUPLICATE", "INVESTIGATION_REQUIRED", "ESCALATED")
DISPOSITION_FROM = ("NEW", "TRIAGE", "MONITOR")
ESCALATED_NEXT = ("INVESTIGATION_REQUIRED",)
# A case can be opened from a signal in these statuses (a second case from one signal included).
CASE_FROM = ("INVESTIGATION_REQUIRED", "ESCALATED", "INVESTIGATION_OPEN")

# Most urgent first; due dates of a new signal by priority (days after it is created).
PRIORITY_RANK = {"CRITICAL": 4, "HIGH": 3, "MEDIUM": 2, "LOW": 1}
DUE_DAYS = {"CRITICAL": 1, "HIGH": 3, "MEDIUM": 5, "LOW": 10}

# Severities as quality systems record them, ranked; a severity in HIGH_SEVERITIES makes a signal HIGH priority.
SEVERITY_RANK = {
    "CRITICAL": 6,
    "SEVERE": 5,
    "SERIOUS": 5,
    "HIGH": 4,
    "MAJOR": 4,
    "MODERATE": 3,
    "MEDIUM": 3,
    "MINOR": 2,
    "LOW": 1,
    "NEGLIGIBLE": 0,
}
HIGH_SEVERITIES = frozenset({"HIGH", "CRITICAL", "SERIOUS", "MAJOR", "SEVERE"})

# History events (signal_events.event_type) and the audit action each change writes.
EVENT_LABELS: dict[str, str] = {
    "CREATED": "Created",
    "TRIAGE_STARTED": "Triage started",
    "PRIORITY_SET": "Priority set",
    "DISPOSITIONED": "Dispositioned",
    "DUPLICATE_LINKED": "Duplicate linked",
    "MERGED_INTO": "Merged into another signal",
    "MERGED_FROM": "Signals merged into this one",
    "COMPLAINTS_ADDED": "Complaints added",
    "MONITOR_TRIGGERED": "New complaints while monitoring",
    "MONITOR_REVIEW_DUE": "Monitoring review due",
    "INVESTIGATION_CREATED": "Investigation opened",
    "DECISION_RECORDED": "Decision signed",
    "CLOSED": "Closed",
    "REOPENED": "Investigation reopened",
}

# The complaint threshold rule: N complaints of one problem on one product version within a window of days.
THRESHOLD_RULE = "COMPLAINT_THRESHOLD"
THRESHOLD_DEFAULTS = {"min_complaints": 3, "window_days": 30}
RULES: dict[str, dict[str, str]] = {
    THRESHOLD_RULE: {
        "label": "Complaint threshold",
        "description": (
            "Raises a signal when at least the set number of complaints about the same problem on the same product "
            "version occur within the window, and adds later complaints to the open signal."
        ),
    }
}

__all__ = [
    "AWAITING_TRIAGE",
    "CASE_FROM",
    "DETECTION_ACTOR",
    "DISPOSITIONS",
    "DISPOSITION_FROM",
    "DUE_DAYS",
    "ESCALATED_NEXT",
    "EVENT_LABELS",
    "HIGH_SEVERITIES",
    "OPEN_SIGNAL_STATUSES",
    "ORIGIN_LABELS",
    "PRIORITY_RANK",
    "RULES",
    "SEVERITY_RANK",
    "SIGNAL_PRIORITIES",
    "SIGNAL_SOURCE",
    "SIGNAL_STATUSES",
    "STATUS_LABELS",
    "THRESHOLD_DEFAULTS",
    "THRESHOLD_RULE",
    "TRIAGE_TASK",
]
