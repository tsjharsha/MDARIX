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
    # A complaint's reporting clock is due soon or overdue without a decision (md41); finished by the decision.
    "REPORTABILITY_DECISION": TaskType("Reportability decision", REGULATORY_REVIEW_PERMISSION, "REGULATORY_REVIEWER"),
    # A CAPA's effectiveness check is near or past its day (md41); finished by the signed result.
    "EFFECTIVENESS_CHECK": TaskType("Effectiveness check", QUALITY_REVIEW_PERMISSION, "REVIEWER"),
    # A first contact (tr04, G32): a follow-up with the reporter on what is unknown or not stated (a dated task until
    # the communications log, G30); the QMS complaint to create or link for a complaint, "both" or an urgent intake
    # (G20); the QA review of a "service only" decision (G32). Each is finished by the action it asks for.
    "FIRST_CONTACT_FOLLOW_UP": TaskType("First-contact follow-up", SIGNAL_TRIAGE_PERMISSION, "TRIAGE_LEAD"),
    "QMS_COMPLAINT": TaskType("Create or link the QMS complaint", SIGNAL_TRIAGE_PERMISSION, "TRIAGE_LEAD"),
    "SERVICE_ONLY_REVIEW": TaskType("QA review of a service-only call", QUALITY_REVIEW_PERMISSION, "REVIEWER"),
    # An information request to a reporter, distributor, hospital or service partner (tr06, G30): its owner's task
    # until it is answered, closed or unresolved after attempts.
    "EXTERNAL_REPLY_DUE": TaskType("Reply due from an external contact", SIGNAL_TRIAGE_PERMISSION, "TRIAGE_LEAD"),
    # A step of a complaint sent to a colleague from its page (0.10.68, "Send to"): always for a named person who
    # may sign that step; finished when that person has done it, or by hand.
    "COMPLAINT_STEP": TaskType("A step on a complaint", SIGNAL_TRIAGE_PERMISSION, "TRIAGE_LEAD"),
    # 0.10.93 (B2) triage: a "Not known yet" harm to find out (1 working day), the containment tasks (T-D11) and the
    # second person's approval of a downgrade of a fast-track triage (A6, the escalation role's queue).
    "TRIAGE_HARM_FOLLOW_UP": TaskType("Find out the harm", SIGNAL_TRIAGE_PERMISSION, "TRIAGE_LEAD"),
    "LOT_HOLD": TaskType("Lot impact: hold the lot?", SIGNAL_TRIAGE_PERMISSION, "TRIAGE_LEAD"),
    "FIELD_ACTION_DECISION": TaskType("Field action decision", SIGNAL_TRIAGE_PERMISSION, "TRIAGE_LEAD"),
    "TRIAGE_DOWNGRADE_APPROVAL": TaskType("Approve a triage downgrade", SIGNAL_TRIAGE_PERMISSION, "LEADER"),
}

# Task types a person finishes by hand (POST /api/v1/tasks/{id}/complete); every other type is finished by the
# action it asks for (a signature, a supplier's reply, closing the case ...).
MANUAL_COMPLETION_TYPES = frozenset({"FOLLOW_UP", "IMPACT_ASSESSMENT", "EVIDENCE_REVIEW", "COMPLAINT_STEP"})

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
    # Evidence that reached a case after its decision was signed (Phase 6): the owner's impact assessment task.
    "ImpactAssessment": "Impact assessment",
    # A follow-up action chosen while signing a decision (Phase 6): its owner's FOLLOW_UP task.
    "DecisionFollowUp": "Decision follow-up",
    # A complaint whose reportability needs a decision (md41): the regulatory reviewers' reminder.
    "Complaint": "Complaint",
    # A CAPA whose effectiveness check is due (md41): the quality reviewers' reminder.
    "Capa": "CAPA",
    # A logged contact or an urgent intake (tr04): its follow-ups, QMS-complaint task and QA review.
    "IntakeEvent": "Contact or urgent intake",
    # A request in the communications log (tr06): its owner's reply-due task.
    "CommunicationEntry": "Communication",
    # A report snapshot or decision guide version waiting for approval (0.10.64, workflow/approvals.py).
    "ReportSnapshot": "Report snapshot",
    "DecisionGuideVersion": "Decision guide version",
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
