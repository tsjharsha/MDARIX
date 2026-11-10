"""The rules of decision follow-ups, impact assessments and case closure, without a database: labels, request bodies,
what a person may do with a follow-up or an assessment, the idempotency key of late evidence and the closure criteria
of a case in the Decision Brief flow. Imported by the services and routers and by the unit tests.
"""

from __future__ import annotations

import re
from collections import Counter
import uuid
from datetime import date, datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from backend.app.db.models.decision_outcomes import FIELD_ACTION_KINDS, FOLLOW_UP_ACTIONS, IMPACT_CONCLUSIONS
from backend.app.role_codes import role_code

INVESTIGATION_WORK = "investigation.work"
INVESTIGATION_ASSIGN = "investigation.assign"

# Audit entity types, and the workflow task source of an impact assessment (backend/app/workflow/labels.py).
FOLLOW_UP_ENTITY = "DecisionFollowUp"
IMPACT_ENTITY = "ImpactAssessment"
IMPACT_SOURCE_TYPE = "ImpactAssessment"
FOLLOW_UP_TASK = "FOLLOW_UP"
IMPACT_TASK = "IMPACT_ASSESSMENT"

ACTION_LABELS: dict[str, str] = {
    "CAPA_REQUIRED": "CAPA required",
    "PRODUCT_CHANGE_REQUIRED": "Product change required",
    "FIELD_ACTION_REVIEW_REQUIRED": "Field action review required",
    "RISK_REASSESSMENT_REQUIRED": "Risk reassessment required",
    "REGULATORY_ACTION_REQUIRED": "Regulatory action required",
}
STATUS_LABELS: dict[str, str] = {
    "OPEN": "Open",
    "IN_PROGRESS": "In progress",
    "DONE": "Done",
    "CANCELLED": "Cancelled",
}
# A follow-up still to be done (it can be started, completed or cancelled).
OPEN_FOLLOW_UP_STATUSES = ("OPEN", "IN_PROGRESS")

TRIGGER_LABELS: dict[str, str] = {
    "EVIDENCE_LINKED": "Evidence linked to the investigation",
    "EVIDENCE_REVIEWED": "Evidence reviewed",
    "EVIDENCE_REQUEST_ACCEPTED": "Evidence request answer accepted",
    "EVIDENCE_INGESTED": "Evidence received for the investigation",
}
CONCLUSION_LABELS: dict[str, str] = {
    "NO_IMPACT": "No impact on the decision",
    "MATERIAL_IMPACT": "Material impact: the decision must be reconsidered",
}
IMPACT_STATUS_LABELS: dict[str, str] = {"OPEN": "Open", "COMPLETED": "Completed"}

# The signed human decision on a Decision Brief (md33). Only the current one (not superseded) counts.
BRIEF_KIND = "BRIEF"
SIGNED_STATUS = "SIGNED"
# Outcomes that let a case close; REJECT_CONCLUSION means the work goes on.
CLOSING_OUTCOMES = ("ACCEPT_CONCLUSION", "ACCEPT_WITH_CONDITIONS", "CLOSE_NO_FURTHER_ACTION")
# Evidence reaching a case in these states after its decision was signed needs an impact assessment; a material
# impact moves a case in these states back to IN_PROGRESS.
DECIDED_STATES = ("DECIDED", "CLOSED")
URGENT_PRIORITIES = ("HIGH", "CRITICAL")
OPEN_REVIEW_STATUSES = ("REQUESTED", "IN_PROGRESS")

NOTE_MIN = 10
NOTE_MAX = 5000
REASON_MIN = 10
REASON_MAX = 1000
RATIONALE_MIN = 20
RATIONALE_MAX = 5000
CAPA_TITLE_MIN = 5
CAPA_TITLE_MAX = 255
CAPA_ACTION_TYPE = "CORRECTIVE"
CAPA_SOURCE_TYPE = "INVESTIGATION_DECISION"
CAPA_SOURCE_SYSTEM = "MDARIX"
CAPA_STATUS = "open"
# The number the customer's QMS gave the CAPA (J22): letters, numbers, spaces and . _ / # : - (up to 120).
QMS_REFERENCE_MAX = 120
_QMS_REFERENCE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9 ._/#:-]*$")


def capa_qms_words(capa) -> str | None:
    """Where a CAPA stands in the customer's QMS (J22), wherever the CAPA shows: "QMS reference CAPA-0450" once
    known; "to raise in your QMS" for one MDARIX recorded without it yet; None for a CAPA that came from the QMS (its
    own identifier is the QMS's)."""
    if getattr(capa, "qms_reference", None):
        return f"QMS reference {capa.qms_reference}"
    if getattr(capa, "source_system", None) == CAPA_SOURCE_SYSTEM:
        return "to raise in your QMS"
    return None


def _qms_reference(value: str | None) -> str | None:
    text = " ".join(str(value or "").split())
    if not text:
        return None
    if not _QMS_REFERENCE.match(text):
        raise ValueError("Use letters, numbers, spaces or . _ / # : - for the QMS reference")
    return text


PASS = "PASS"
BLOCKED = "BLOCKED"
NOT_REQUIRED = "NOT_REQUIRED"
CLOSURE_LABELS: dict[str, str] = {
    "CASE_OPEN": "The investigation is open",
    "DECISIONS_REVIEWED": "No decision awaits its human review",
    "SIGNED_DECISION": "A signed decision that lets the investigation close",
    "IMPACT_ASSESSMENTS": "Late evidence assessed",
    "CASE_REVIEWS": "Risk and regulatory reviews finished",
    "EVIDENCE_REQUESTS": "No urgent evidence request open",
    "FOLLOW_UPS": "Follow-up actions recorded",
    "CLOSURE_REASON": "Reason for closing",
}


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def action_label(code: str | None) -> str | None:
    return ACTION_LABELS.get(str(code or "").upper(), code) if code else None


def status_label(code: str | None) -> str | None:
    return STATUS_LABELS.get(str(code or "").upper(), code) if code else None


def trigger_label(code: str | None) -> str | None:
    return TRIGGER_LABELS.get(str(code or "").upper(), code) if code else None


def conclusion_label(code: str | None) -> str | None:
    return CONCLUSION_LABELS.get(str(code or "").upper(), code) if code else None


def is_overdue(status: str | None, due_at: datetime | None, now: datetime | None = None) -> bool:
    """An open follow-up whose due date has passed."""
    due = as_utc(due_at)
    return bool(due is not None and str(status or "").upper() in OPEN_FOLLOW_UP_STATUSES and due < (now or now_utc()))


def chosen_actions(follow_up_actions) -> list[str]:
    """The follow-up action types a decision maker chose while signing (``decisions.follow_up_actions``), in order,
    one entry per follow-up. Each item is an action code or an object carrying it (``action_type``, else ``type`` or
    ``action``); anything else is ignored."""
    found: list[str] = []
    for item in follow_up_actions or ():
        if isinstance(item, dict):
            code = item.get("action_type") or item.get("type") or item.get("action")
        else:
            code = item
        code = str(code or "").strip().upper()
        if code in FOLLOW_UP_ACTIONS:
            found.append(code)
    return found


def late_evidence_key(decision_id, evidence_id) -> tuple[str, str]:
    """What makes an impact assessment unique: one per signed decision and piece of evidence, whatever brought the
    evidence to the case (linking, reviewing, a request answer, ingestion) and however often."""
    return (str(decision_id), str(evidence_id))


def capa_identifier(case_business_id: str, taken) -> str:
    """``CAPA-<case business id>-<n>`` with the first ``n`` not yet taken in the organization."""
    used = set(taken or ())
    number = 1
    while f"CAPA-{case_business_id}-{number}" in used:
        number += 1
    return f"CAPA-{case_business_id}-{number}"


# ---------------------------------------------------------------------------------------------- who may do what


def is_responsible(
    *, assignee_user_id, assigned_role: str | None, user_uuid, role_codes, holds_work: bool = False
) -> bool:
    """Who works on a follow-up: the person it is assigned to; when nobody is named, anyone holding its role; when
    neither is set, anyone who works on cases."""
    if assignee_user_id is not None:
        return user_uuid is not None and str(assignee_user_id) == str(user_uuid)
    if assigned_role:
        return role_code(assigned_role) in {role_code(item) for item in role_codes or () if item}
    return bool(holds_work)


def follow_up_actions(
    *, status: str | None, action_type: str | None, capa_id, responsible: bool, can_assign: bool, can_work: bool
) -> dict[str, bool]:
    status = str(status or "").upper()
    still_open = status in OPEN_FOLLOW_UP_STATUSES
    return {
        "can_start": responsible and status == "OPEN",
        "can_complete": responsible and still_open,
        "can_cancel": can_assign and still_open,
        "can_create_capa": can_work
        and str(action_type or "").upper() == "CAPA_REQUIRED"
        and capa_id is None
        and status != "CANCELLED",
        "can_set_qms_reference": can_work and capa_id is not None,
    }


def impact_actions(*, status: str | None, can_work: bool) -> dict[str, bool]:
    return {"can_complete": bool(can_work) and str(status or "").upper() == "OPEN"}


# ------------------------------------------------------------------------------------------------ request bodies


def _text(value: str | None) -> str:
    return " ".join(str(value or "").split()) if value is not None else ""


class FollowUpCompletePayload(BaseModel):
    note: str = Field(min_length=NOTE_MIN, max_length=NOTE_MAX)
    # B5b (tr26), all optional: the customer's reference (field action, CAPA step or change order); for a field action
    # its kind, effective date and the lots or versions it covers; for a product change the new version.
    action_reference: str | None = Field(default=None, max_length=120)
    action_kind: Literal[FIELD_ACTION_KINDS] | None = None  # type: ignore[valid-type]
    action_effective_on: date | None = None
    lot_ids: list[uuid.UUID] = Field(default_factory=list, max_length=500)
    version_ids: list[uuid.UUID] = Field(default_factory=list, max_length=100)
    new_version_id: uuid.UUID | None = None

    def action_fields(self) -> dict:
        """The B5b fields given, as stored (empty when none is)."""
        found = {}
        if self.action_reference and self.action_reference.strip():
            found["action_reference"] = self.action_reference.strip()
        if self.action_kind:
            found["action_kind"] = self.action_kind
        if self.action_effective_on:
            found["action_effective_on"] = self.action_effective_on
        scope = {
            key: [str(item) for item in dict.fromkeys(value)]
            for key, value in (("lot_ids", self.lot_ids), ("version_ids", self.version_ids))
            if value
        }
        if self.new_version_id:
            scope["new_version_id"] = str(self.new_version_id)
        if scope:
            found["action_scope"] = scope
        return found

    @field_validator("note")
    @classmethod
    def _note(cls, value: str) -> str:
        if len(value.strip()) < NOTE_MIN:
            raise ValueError(f"Say in at least {NOTE_MIN} characters what was done")
        return value.strip()


class ReasonPayload(BaseModel):
    reason: str = Field(min_length=REASON_MIN, max_length=REASON_MAX)

    @field_validator("reason")
    @classmethod
    def _reason(cls, value: str) -> str:
        if len(value.strip()) < REASON_MIN:
            raise ValueError(f"Say in at least {REASON_MIN} characters why")
        return value.strip()


class CapaPayload(BaseModel):
    title: str = Field(min_length=CAPA_TITLE_MIN, max_length=CAPA_TITLE_MAX)
    due_at: datetime | None = None
    qms_reference: str | None = Field(default=None, max_length=QMS_REFERENCE_MAX)

    @field_validator("qms_reference")
    @classmethod
    def _qms(cls, value: str | None) -> str | None:
        return _qms_reference(value)

    @field_validator("title")
    @classmethod
    def _title(cls, value: str) -> str:
        text = _text(value)
        if len(text) < CAPA_TITLE_MIN:
            raise ValueError(f"Give the CAPA a title of at least {CAPA_TITLE_MIN} characters")
        return text

    @field_validator("due_at")
    @classmethod
    def _due(cls, value: datetime | None) -> datetime | None:
        return as_utc(value)


class QmsReferencePayload(BaseModel):
    """The QMS reference of a CAPA MDARIX recorded; blank clears it."""

    qms_reference: str | None = Field(default=None, max_length=QMS_REFERENCE_MAX)

    @field_validator("qms_reference")
    @classmethod
    def _qms(cls, value: str | None) -> str | None:
        return _qms_reference(value)


class ImpactCompletePayload(BaseModel):
    conclusion: str = Field(pattern="^(" + "|".join(IMPACT_CONCLUSIONS) + ")$")
    rationale: str = Field(min_length=RATIONALE_MIN, max_length=RATIONALE_MAX)

    @field_validator("rationale")
    @classmethod
    def _rationale(cls, value: str) -> str:
        if len(value.strip()) < RATIONALE_MIN:
            raise ValueError(f"Explain the conclusion in at least {RATIONALE_MIN} characters")
        return value.strip()


# ------------------------------------------------------------------------------------------------------ closure


def _criterion(key: str, result: str, rationale: str) -> dict:
    return {"key": key, "label": CLOSURE_LABELS[key], "result": result, "rationale": rationale}


def _follow_up_criterion(decision: dict | None, chosen: list[str], recorded: list[dict]) -> dict:
    if decision is None:
        return _criterion("FOLLOW_UPS", NOT_REQUIRED, "There is no signed decision whose follow-ups could be checked")
    if not chosen:
        return _criterion("FOLLOW_UPS", NOT_REQUIRED, "The decision asked for no follow-up actions")
    have = Counter(str(item.get("action_type") or "").upper() for item in recorded if item.get("has_task"))
    missing: list[str] = []
    for code, wanted in Counter(chosen).items():
        if have.get(code, 0) < wanted:
            missing.append(ACTION_LABELS.get(code, code))
    if missing:
        return _criterion(
            "FOLLOW_UPS",
            BLOCKED,
            "These follow-ups chosen in the decision have no record or no task yet: " + ", ".join(sorted(missing)),
        )
    return _criterion(
        "FOLLOW_UPS",
        PASS,
        f"All {len(chosen)} follow-up(s) chosen in the decision are recorded with a task; they may still be open",
    )


def closure_criteria(facts: dict) -> list[dict]:
    """The closure criteria of a case from its ``facts``: ``closed``, ``awaiting_review`` (a decision awaits its human
    review), ``applies`` (the case is in the Decision Brief flow), and for those cases ``decision`` (the current signed
    brief decision: ``business_id``, ``outcome``; None when there is none), ``open_assessments``, ``open_reviews``,
    ``urgent_requests`` (open evidence requests of HIGH or CRITICAL priority), ``chosen`` (the follow-up action types
    of the decision), ``recorded`` (its follow-ups: ``action_type``, ``has_task``) and ``reason`` (the closing
    reason; None when not given yet). A case outside the Decision Brief flow keeps today's two rules."""
    criteria = [
        _criterion("CASE_OPEN", BLOCKED, "The investigation is already closed")
        if facts.get("closed")
        else _criterion("CASE_OPEN", PASS, "The investigation is open"),
        _criterion(
            "DECISIONS_REVIEWED",
            BLOCKED,
            "A decision on this investigation still awaits its human review; finish it first",
        )
        if facts.get("awaiting_review")
        else _criterion("DECISIONS_REVIEWED", PASS, "No decision on this investigation awaits its human review"),
    ]
    if not facts.get("applies"):
        return criteria
    decision = facts.get("decision")
    if decision is None:
        criteria.append(_criterion("SIGNED_DECISION", BLOCKED, "No signed decision on the Decision Brief yet"))
    elif str(decision.get("outcome") or "").upper() not in CLOSING_OUTCOMES:
        criteria.append(
            _criterion(
                "SIGNED_DECISION",
                BLOCKED,
                f"Decision {decision.get('business_id')} rejects the conclusion; the investigation needs more work and a new "
                "decision",
            )
        )
    else:
        criteria.append(
            _criterion(
                "SIGNED_DECISION",
                PASS,
                f"Decision {decision.get('business_id')} is signed with an outcome that allows closing",
            )
        )
    open_assessments = int(facts.get("open_assessments") or 0)
    criteria.append(
        _criterion(
            "IMPACT_ASSESSMENTS",
            BLOCKED,
            f"{open_assessments} impact assessment(s) of late evidence are still open",
        )
        if open_assessments
        else _criterion("IMPACT_ASSESSMENTS", PASS, "No impact assessment is open")
    )
    open_reviews = int(facts.get("open_reviews") or 0)
    criteria.append(
        _criterion("CASE_REVIEWS", BLOCKED, f"{open_reviews} risk or regulatory review(s) are requested or in progress")
        if open_reviews
        else _criterion("CASE_REVIEWS", PASS, "No risk or regulatory review is requested or in progress")
    )
    urgent = int(facts.get("urgent_requests") or 0)
    criteria.append(
        _criterion("EVIDENCE_REQUESTS", BLOCKED, f"{urgent} evidence request(s) of high or critical priority are open")
        if urgent
        else _criterion("EVIDENCE_REQUESTS", PASS, "No evidence request of high or critical priority is open")
    )
    criteria.append(_follow_up_criterion(decision, list(facts.get("chosen") or ()), list(facts.get("recorded") or ())))
    reason = facts.get("reason")
    if reason is None:
        criteria.append(
            _criterion("CLOSURE_REASON", PASS, "Give the reason for closing when you close the investigation")
        )
    elif len(str(reason).strip()) < REASON_MIN:
        criteria.append(
            _criterion("CLOSURE_REASON", BLOCKED, f"Give a reason for closing of at least {REASON_MIN} characters")
        )
    else:
        criteria.append(_criterion("CLOSURE_REASON", PASS, "A reason for closing is given"))
    return criteria


def closure_result(facts: dict) -> dict:
    """``{can_close, applies, criteria}``: the case can close when no criterion is BLOCKED."""
    criteria = closure_criteria(facts)
    return {
        "can_close": all(item["result"] != BLOCKED for item in criteria),
        "applies": bool(facts.get("applies")),
        "criteria": criteria,
    }


def blocked(criteria: list[dict]) -> list[dict]:
    return [item for item in criteria if item["result"] == BLOCKED]
