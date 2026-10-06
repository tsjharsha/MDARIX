"""Task types, the permission each needs and the role queue it lands in, with the labels people read.

A person sees a role queue, claims a task from it and may be assigned one only when they hold the task type's
permission (backend/app/access/permissions.py). The default role is the queue a task lands in when nobody in
particular is asked to do it.
"""

from __future__ import annotations

from typing import NamedTuple

from backend.app.role_codes import is_administrator_role, role_code


class TaskType(NamedTuple):
    label: str
    permission: str
    queue_role: str


# Permission names of the shared contract (the constants live in backend/app/access/permissions.py).
SIGNAL_TRIAGE_PERMISSION = "signal.triage"
INVESTIGATION_WORK_PERMISSION = "investigation.work"
EVIDENCE_REVIEW_PERMISSION = "evidence.review"
EVIDENCE_REQUEST_PERMISSION = "evidence.request"
RISK_REVIEW_PERMISSION = "risk.review"
REGULATORY_REVIEW_PERMISSION = "regulatory.review"
QUALITY_REVIEW_PERMISSION = "quality.review"
DECISION_SIGN_PERMISSION = "decision.sign"
INVESTIGATION_ASSIGN_PERMISSION = "investigation.assign"

TASK_TYPES: dict[str, TaskType] = {
    "SIGNAL_TRIAGE": TaskType("Signal triage", SIGNAL_TRIAGE_PERMISSION, "TRIAGE_LEAD"),
    "INVESTIGATION": TaskType("Investigation", INVESTIGATION_WORK_PERMISSION, "INVESTIGATOR"),
    "EVIDENCE_REQUEST": TaskType("Evidence request", INVESTIGATION_WORK_PERMISSION, "INVESTIGATOR"),
    "EVIDENCE_REVIEW": TaskType("Evidence review", EVIDENCE_REVIEW_PERMISSION, "INVESTIGATOR"),
    "RISK_REVIEW": TaskType("Risk review", RISK_REVIEW_PERMISSION, "RISK_REVIEWER"),
    "REGULATORY_REVIEW": TaskType("Regulatory review", REGULATORY_REVIEW_PERMISSION, "REGULATORY_REVIEWER"),
    "QUALITY_REVIEW": TaskType("Quality review", QUALITY_REVIEW_PERMISSION, "REVIEWER"),
    "DECISION_APPROVAL": TaskType("Decision approval", DECISION_SIGN_PERMISSION, "APPROVER"),
    "IMPACT_ASSESSMENT": TaskType("Impact assessment", INVESTIGATION_WORK_PERMISSION, "INVESTIGATOR"),
    "FOLLOW_UP": TaskType("Follow-up", INVESTIGATION_WORK_PERMISSION, "INVESTIGATOR"),
    # A colleague (or anyone holding the role) asked for evidence on a case (Phase 3); finished by answering.
    "EVIDENCE_RESPONSE": TaskType("Provide evidence", EVIDENCE_REQUEST_PERMISSION, "INVESTIGATOR"),
}

# Task types a person finishes by hand (POST /api/v1/tasks/{id}/complete); every other type is finished by the
# action it asks for (a signature, a supplier's reply, closing the case ...).
MANUAL_COMPLETION_TYPES = frozenset({"FOLLOW_UP", "IMPACT_ASSESSMENT", "EVIDENCE_REVIEW"})

# The records a task can be about, as stored in workflow_tasks.source_entity_type.
SOURCE_LABELS: dict[str, str] = {
    "Investigation": "Investigation",
    "Decision": "Decision",
    "Risk": "Risk",
    "SupplierEvidenceRequest": "Supplier evidence request",
    "Signal": "Signal",
    "EvidenceRequest": "Evidence request",
    # A version of a case's controlled Decision Brief (Phase 5): its quality review and decision tasks.
    "DecisionBriefVersion": "Decision brief",
    # A risk or regulatory review of a case (Phase 5): its reviewers' queue task and the owner's follow-up.
    "CaseReview": "Case review",
}

# Used only when backend/app/role_codes.py does not carry ROLE_LABELS (an older build).
_FALLBACK_ROLE_LABELS: dict[str, str] = {
    "TRIAGE_LEAD": "PMS / Signal Triage Lead",
    "INVESTIGATOR": "Quality Investigator",
    "RISK_REVIEWER": "Risk Reviewer",
    "REGULATORY_REVIEWER": "Regulatory Reviewer",
    "REVIEWER": "Quality Reviewer",
    "APPROVER": "Authorized Decision Maker",
    "LEADER": "Leader (Quality Manager)",
    "VIEWER": "Viewer",
}


def task_type(code: str) -> TaskType:
    """The definition of a task type; ValueError for a type nobody defined."""
    found = TASK_TYPES.get(str(code or "").strip().upper())
    if found is None:
        raise ValueError(f"Unknown task type {code!r}")
    return found


def task_type_label(code: str | None) -> str | None:
    found = TASK_TYPES.get(str(code or "").strip().upper())
    return found.label if found else code


def role_labels() -> dict[str, str]:
    from backend.app import role_codes

    labels = getattr(role_codes, "ROLE_LABELS", None)
    return {**_FALLBACK_ROLE_LABELS, **dict(labels)} if labels else dict(_FALLBACK_ROLE_LABELS)


def role_label(code: str | None) -> str | None:
    if not code:
        return None
    normalized = role_code(code)
    return role_labels().get(normalized) or str(code)


def known_role(code: str | None) -> bool:
    """A workflow role a task queue can belong to (administrator roles never hold case work)."""
    return bool(code) and not is_administrator_role(code) and role_code(code) in role_labels()
