"""The rules of case reviews, without a database: the review policy, the labels people read, which outcome fits which
review, what a review means for the case's readiness, what a person may do with a review, the request bodies, and the
next steps that replace the old decision options. Imported by the routers, the readiness module and the unit tests.

Review policy (``review_policy``). MDARIX says when a review is required, never what its outcome is, and never
decides reportability:

- a risk review is required when the case priority is HIGH or CRITICAL, when any complaint in the case's current scope
  reports a serious injury or a death, or when a signal the case was opened for reports serious harm;
- a regulatory review is required when any complaint in the current scope reports a death, a serious injury or a
  malfunction, or when the case priority is CRITICAL.

Each rule that applies gives one reason in plain words ("2 complaints in scope report a serious injury").
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable, Mapping
from datetime import date, datetime, timezone
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

from backend.app.db.models.reviews import REGULATORY_OUTCOMES, REVIEW_TYPES, RISK_OUTCOMES

# ------------------------------------------------------------------------------------------------------ labels

RISK = "RISK"
REGULATORY = "REGULATORY"
TYPE_LABELS: dict[str, str] = {RISK: "Risk review", REGULATORY: "Regulatory review"}
# The policy and readiness keys of each review type.
TYPE_KEYS: dict[str, str] = {RISK: "risk", REGULATORY: "regulatory"}
# Who reviews: the permission of each review type and the task type (role queue) its request lands in.
TYPE_PERMISSIONS: dict[str, str] = {RISK: "risk.review", REGULATORY: "regulatory.review"}
TYPE_TASKS: dict[str, str] = {RISK: "RISK_REVIEW", REGULATORY: "REGULATORY_REVIEW"}
# Workflow tasks about a review (backend/app/workflow/labels.py SOURCE_LABELS).
SOURCE_TYPE = "CaseReview"

STATUS_LABELS: dict[str, str] = {
    "REQUESTED": "Requested",
    "IN_PROGRESS": "In progress",
    "COMPLETED": "Completed",
    "CANCELLED": "Cancelled",
    "SUPERSEDED": "Superseded",
}
# A review still to be done (one per type at a time), and the reviews a scope change restarts.
OPEN_STATUSES = ("REQUESTED", "IN_PROGRESS")
CURRENT_STATUSES = ("REQUESTED", "IN_PROGRESS", "COMPLETED")
FINISHED_STATUSES = ("COMPLETED", "CANCELLED", "SUPERSEDED")

OUTCOMES: dict[str, tuple[str, ...]] = {RISK: RISK_OUTCOMES, REGULATORY: REGULATORY_OUTCOMES}
OUTCOME_LABELS: dict[str, str] = {
    "NO_CHANGE_REQUIRED": "No change to the risk file required",
    "RISK_FILE_REASSESSMENT_REQUIRED": "Risk file reassessment required",
    "RISK_CONTROL_REVIEW_REQUIRED": "Risk control review required",
    "ADDITIONAL_EVIDENCE_REQUIRED": "Additional evidence required",
    "ESCALATE_SAFETY_CONCERN": "Escalated as a safety concern",
    "NO_REPORTABILITY_CONCERN_IDENTIFIED": "No reportability concern identified",
    "REPORTABILITY_ASSESSMENT_COMPLETE": "Reportability assessment complete",
    "REPORTING_REQUIRED": "Reporting required",
    "TREND_REPORTING_REVIEW_REQUIRED": "Trend reporting review required",
    "ESCALATE_REGULATORY": "Escalated for regulatory attention",
}
# Outcomes that send the case back: the case owner gets a follow-up, and readiness stays blocked until a new review
# of the same type is completed.
BLOCKING_OUTCOMES = frozenset({"ADDITIONAL_EVIDENCE_REQUIRED", "ESCALATE_SAFETY_CONCERN", "ESCALATE_REGULATORY"})

RATIONALE_MIN = 20
RATIONALE_MAX = 5000
REASON_MIN = 10
REASON_MAX = 2000
NOTES_MAX = 5000
MARKET_MAX = 120
DUE_SOON_DAYS = 7
NOT_REQUIRED_TEXT = "Not required by policy"
REGULATORY_NOTE = "Reportability and deadlines are determined by the reviewer"


def review_type_code(value: Any) -> str | None:
    code = str(value or "").strip().upper()
    return code if code in REVIEW_TYPES else None


def type_label(code: str | None) -> str | None:
    return TYPE_LABELS.get(str(code or "").upper(), code) if code else None


def status_label(code: str | None) -> str | None:
    return STATUS_LABELS.get(str(code or "").upper(), code) if code else None


def outcome_label(code: str | None) -> str | None:
    if not code:
        return None
    return OUTCOME_LABELS.get(str(code).upper()) or str(code).replace("_", " ").capitalize()


def is_blocking_outcome(outcome: str | None) -> bool:
    return str(outcome or "").upper() in BLOCKING_OUTCOMES


def outcome_problem(review_type: str | None, outcome: str | None) -> str | None:
    """Why ``outcome`` cannot conclude a review of ``review_type``, or None when it can."""
    code = review_type_code(review_type)
    if code is None:
        return "Unknown review type"
    allowed = OUTCOMES[code]
    if str(outcome or "").strip().upper() not in allowed:
        return f"Choose an outcome of a {TYPE_LABELS[code].lower()}: {', '.join(allowed)}"
    return None


def as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def is_overdue(status: str | None, due_at: datetime | None, now: datetime) -> bool:
    """Past its due date and still to be done."""
    return str(status or "").upper() in OPEN_STATUSES and due_at is not None and as_utc(due_at) < now


# ------------------------------------------------------------------------------------------------------ policy


def _plural(count: int, one: str, many: str | None = None) -> str:
    return f"{count} {one if count == 1 else (many or one + 's')}"


def _complaints_report(count: int, what: str) -> str:
    return f"{_plural(count, 'complaint')} in scope {'reports' if count == 1 else 'report'} {what}"


def _flag(item: Any, name: str) -> bool:
    value = item.get(name) if isinstance(item, Mapping) else getattr(item, name, None)
    return bool(value)


def _text(item: Any, name: str) -> str | None:
    value = item.get(name) if isinstance(item, Mapping) else getattr(item, name, None)
    return str(value) if value else None


def review_policy(priority: str | None, complaints: Iterable[Any], signals: Iterable[Any]) -> dict:
    """``{"risk": {"required", "reasons"}, "regulatory": {"required", "reasons"}}`` for a case of ``priority`` whose
    current scope holds ``complaints`` (each with ``serious_injury``, ``death``, ``malfunction``) and that was opened for
    ``signals`` (each with ``business_id``, ``serious_harm``). See the module docstring."""
    level = str(priority or "").strip().upper()
    complaints = list(complaints or ())
    injuries = sum(1 for item in complaints if _flag(item, "serious_injury"))
    deaths = sum(1 for item in complaints if _flag(item, "death"))
    malfunctions = sum(1 for item in complaints if _flag(item, "malfunction"))
    harmful = [item for item in signals or () if _flag(item, "serious_harm")]

    risk: list[str] = []
    if level in ("HIGH", "CRITICAL"):
        risk.append(f"The case priority is {level.lower()}")
    if injuries:
        risk.append(_complaints_report(injuries, "a serious injury"))
    if deaths:
        risk.append(_complaints_report(deaths, "a death"))
    if harmful:
        names = [_text(item, "business_id") for item in harmful]
        names = [name for name in names if name]
        if len(harmful) == 1:
            risk.append(f"Signal {names[0]} reports serious harm" if names else "A linked signal reports serious harm")
        else:
            risk.append(
                f"{len(harmful)} linked signals report serious harm" + (f" ({', '.join(names)})" if names else "")
            )

    regulatory: list[str] = []
    if level == "CRITICAL":
        regulatory.append("The case priority is critical")
    if deaths:
        regulatory.append(_complaints_report(deaths, "a death"))
    if injuries:
        regulatory.append(_complaints_report(injuries, "a serious injury"))
    if malfunctions:
        regulatory.append(_complaints_report(malfunctions, "a malfunction"))
    return {
        "risk": {"required": bool(risk), "reasons": risk},
        "regulatory": {"required": bool(regulatory), "reasons": regulatory},
    }


# --------------------------------------------------------------------------------------------------- readiness


def _lower_first(text: str) -> str:
    return text[:1].lower() + text[1:] if text and not text[:2].isupper() else text


def review_check(review_type: str, fact: Mapping) -> tuple[str, str]:
    """The readiness check of one review type: ``(result, rationale)``.

    ``fact`` is ``{"required", "reasons", "latest"}`` where ``latest`` is the newest review of the type that is
    requested, in progress or completed (cancelled and superseded reviews do not count), as ``{"business_id",
    "status", "outcome"}``, or None.

    - a completed review passes, unless its outcome asks for more evidence or escalates (blocked until a new review of
      the type is completed);
    - a requested or in-progress review is pending;
    - no review: blocked when the policy requires one (with the policy's reasons), else not required.
    """
    label = TYPE_LABELS[review_type]
    lower = label.lower()
    latest = fact.get("latest")
    if latest:
        business_id = latest.get("business_id") or ""
        name = f"{label} {business_id}".strip()
        status = str(latest.get("status") or "").upper()
        if status == "COMPLETED":
            outcome = outcome_label(latest.get("outcome")) or "Completed"
            if is_blocking_outcome(latest.get("outcome")):
                return "BLOCKED", f"{name} concluded: {outcome}. A new {lower} must be completed"
            return "PASS", f"{name} completed: {outcome}"
        if status == "IN_PROGRESS":
            return "PENDING", f"{name} is in progress"
        return "PENDING", f"{name} is requested and waits for a reviewer"
    if fact.get("required"):
        reasons = [_lower_first(str(reason)) for reason in fact.get("reasons") or ()]
        return "BLOCKED", f"Request a {lower}" + (f": required because {'; '.join(reasons)}" if reasons else "")
    return "NOT_REQUIRED", NOT_REQUIRED_TEXT


def review_step(results: Mapping[str, str]) -> tuple[str, str]:
    """The "Risk and regulatory review" step from the check results of each review type (``{"RISK": "PASS", ...}``):
    blocked when a review is missing or sent the case back, in progress while one is pending, otherwise done."""
    order = [code for code in (RISK, REGULATORY) if code in results]
    names = {code: TYPE_LABELS[code].lower() for code in order}

    def joined(codes: list[str]) -> str:
        text = " and ".join(names[code] for code in codes)
        return text[:1].upper() + text[1:]

    blocked = [code for code in order if results[code] == "BLOCKED"]
    if blocked:
        return "BLOCKED", f"{joined(blocked)} must be completed"
    pending = [code for code in order if results[code] == "PENDING"]
    if pending:
        return "IN_PROGRESS", f"{joined(pending)} in progress"
    if order and all(results[code] == "NOT_REQUIRED" for code in order):
        return "DONE", NOT_REQUIRED_TEXT
    parts = [
        f"{names[code]} {'completed' if results[code] == 'PASS' else 'not required'}"
        for code in order
        if results[code] in ("PASS", "NOT_REQUIRED")
    ]
    text = "; ".join(parts)
    return "DONE", text[:1].upper() + text[1:]


# ----------------------------------------------------------------------------------------------------- actions


def review_actions(
    *,
    status: str | None,
    holds_type_permission: bool,
    is_reviewer: bool,
    is_requester: bool,
    can_assign: bool,
    case_open: bool,
    task_taken_by_other: bool = False,
) -> dict[str, bool]:
    """What the person may do with a review now. Anyone holding the review type's permission starts a requested review
    (also the person who asked for it: reviews have no segregation of duties); only its reviewer completes it or
    recuses; its requester or whoever assigns work cancels an open review."""
    code = str(status or "").upper()
    return {
        "can_start": code == "REQUESTED" and holds_type_permission and case_open and not task_taken_by_other,
        "can_complete": code == "IN_PROGRESS" and is_reviewer and holds_type_permission and case_open,
        "can_recuse": code == "IN_PROGRESS" and is_reviewer,
        "can_cancel": code in OPEN_STATUSES and (is_requester or can_assign),
    }


# ---------------------------------------------------------------------------------------------------- payloads


def _clean(value: Any) -> str | None:
    text = " ".join(str(value or "").split())
    return text or None


def _future(value: datetime | None) -> datetime | None:
    value = as_utc(value)
    if value is not None and value <= datetime.now(timezone.utc):
        raise ValueError("Choose a due date in the future")
    return value


def market_list(values: Iterable[Any] | None) -> list[str]:
    """Distinct non-empty markets (compared without case), trimmed, in their first order."""
    result: list[str] = []
    seen: set[str] = set()
    for value in values or ():
        text = _clean(value)
        if text and text.lower() not in seen:
            seen.add(text.lower())
            result.append(text)
    return result


class ReviewRequestPayload(BaseModel):
    review_type: str = Field(max_length=20)
    reason: str | None = Field(default=None, max_length=REASON_MAX)
    due_at: datetime | None = None

    @field_validator("review_type")
    @classmethod
    def _type(cls, value: str) -> str:
        code = review_type_code(value)
        if code is None:
            raise ValueError(f"Choose one of: {', '.join(REVIEW_TYPES)}")
        return code

    @field_validator("reason")
    @classmethod
    def _reason(cls, value: str | None) -> str | None:
        return _clean(value)

    @field_validator("due_at")
    @classmethod
    def _due(cls, value: datetime | None) -> datetime | None:
        return _future(value)


# Risk-control effectiveness (T-G1aR, ISO 14971:2019 clause 10): each finding of a risk review is a risk-register entry
# already in the risk file (did its risk control work?) or a new failure mode or hazard (risk file update required).
CONTROL_ANSWERS = ("YES", "NO", "NOT_ASSESSABLE")
CONTROL_LABELS = {"YES": "Yes, it worked", "NO": "No, it did not work", "NOT_ASSESSABLE": "Not assessable"}
FINDINGS_MAX = 50
QMS_REFERENCE_MAX = 120


class FindingPayload(BaseModel):
    """One finding: ``risk_id`` names the register entry (or none: not in the risk file)."""

    risk_id: uuid.UUID | None = None
    description: str | None = Field(default=None, max_length=REASON_MAX)
    control_worked: str | None = Field(default=None, max_length=20)
    reason: str | None = Field(default=None, max_length=REASON_MAX)
    owner_user_id: uuid.UUID | None = None
    due_on: date | None = None
    qms_reference: str | None = Field(default=None, max_length=QMS_REFERENCE_MAX)


def findings_problem(risk_ids, findings, today: date) -> tuple[str | None, dict]:
    """Why a risk review's findings cannot be completed, and the findings as stored (keyed by finding: the risk id, or
    NEW-1, NEW-2...). Every assessed risk needs its answer; a "no" and a new failure mode each need a risk file update
    with an owner and a due date."""
    stored: dict[str, dict] = {}
    answered: set[str] = set()
    new = 0
    for item in findings:
        reason = _clean(item.reason) or ""
        update = None
        if item.risk_id is not None:
            key = str(item.risk_id)
            if key in answered:
                return "Answer each risk once", {}
            answered.add(key)
            answer = str(item.control_worked or "").strip().upper()
            if answer not in CONTROL_ANSWERS:
                return "For each risk in the risk file, say whether its risk control worked", {}
            if len(reason) < REASON_MIN:
                return f"Give the reason for each risk-control answer in at least {REASON_MIN} characters", {}
            entry = {"kind": "IN_RISK_FILE", "risk_id": key, "control_worked": answer, "reason": reason}
            needs_update = answer == "NO"
        else:
            new += 1
            key = f"NEW-{new}"
            description = _clean(item.description) or ""
            if len(description) < REASON_MIN:
                return f"Describe the new failure mode or hazard in at least {REASON_MIN} characters", {}
            entry = {"kind": "NOT_IN_RISK_FILE", "description": description, "reason": reason or None}
            needs_update = True
        if needs_update:
            if item.owner_user_id is None or item.due_on is None:
                return "A risk file update needs an owner and a due date", {}
            if item.due_on < today:
                return "The risk file update's due date cannot be in the past", {}
            update = {
                "owner_user_id": str(item.owner_user_id),
                "due_on": item.due_on.isoformat(),
                "qms_reference": _clean(item.qms_reference),
            }
        stored[key] = {**entry, "risk_file_update": update}
    if any(str(risk) not in answered for risk in risk_ids):
        return "Every risk you assessed needs its risk-control answer", {}
    return None, stored


class AssessedPayload(BaseModel):
    """What the reviewer looked at: risks of the case's product, markets, notes, and (risk reviews) each finding's
    risk-control answer."""

    risk_ids: list[uuid.UUID] = Field(default_factory=list, max_length=200)
    markets: list[str] = Field(default_factory=list, max_length=100)
    notes: str | None = Field(default=None, max_length=NOTES_MAX)
    findings: list[FindingPayload] = Field(default_factory=list, max_length=FINDINGS_MAX)

    @field_validator("risk_ids")
    @classmethod
    def _risks(cls, value: list[uuid.UUID]) -> list[uuid.UUID]:
        return list(dict.fromkeys(value))

    @field_validator("markets")
    @classmethod
    def _markets(cls, value: list[str]) -> list[str]:
        if any(len(str(item or "").strip()) > MARKET_MAX for item in value):
            raise ValueError(f"A market is named in at most {MARKET_MAX} characters")
        return market_list(value)

    @field_validator("notes")
    @classmethod
    def _notes(cls, value: str | None) -> str | None:
        text = str(value or "").strip()
        return text or None


class CompletePayload(BaseModel):
    outcome: str = Field(max_length=60)
    rationale: str = Field(min_length=RATIONALE_MIN, max_length=RATIONALE_MAX)
    assessed: AssessedPayload = Field(default_factory=AssessedPayload)

    @field_validator("outcome")
    @classmethod
    def _outcome(cls, value: str) -> str:
        return str(value or "").strip().upper()

    @field_validator("rationale")
    @classmethod
    def _rationale(cls, value: str) -> str:
        text = str(value or "").strip()
        if len(" ".join(text.split())) < RATIONALE_MIN:
            raise ValueError(f"Explain the outcome in at least {RATIONALE_MIN} characters")
        return text


class ReasonPayload(BaseModel):
    reason: str = Field(min_length=REASON_MIN, max_length=1000)

    @field_validator("reason")
    @classmethod
    def _reason(cls, value: str) -> str:
        text = _clean(value) or ""
        if len(text) < REASON_MIN:
            raise ValueError(f"Say in at least {REASON_MIN} characters why")
        return text


# -------------------------------------------------------------------------------------------------- next steps

CONTINUE_INVESTIGATION = "CONTINUE_INVESTIGATION"
NO_DECISION_YET = "NO_DECISION_YET"
REQUEST_RISK_REVIEW = "REQUEST_RISK_REVIEW"
REQUEST_REGULATORY_REVIEW = "REQUEST_REGULATORY_REVIEW"
REQUEST_ADDITIONAL_EVIDENCE = "REQUEST_ADDITIONAL_EVIDENCE"
REQUEST_ADDITIONAL_TESTING = "REQUEST_ADDITIONAL_TESTING"
REVIEW_SUPPLIER_CHANGE = "REVIEW_SUPPLIER_CHANGE"
REVIEW_PRODUCT_CHANGE = "REVIEW_PRODUCT_CHANGE"
ESCALATE_FOR_QUALITY_REVIEW = "ESCALATE_FOR_QUALITY_REVIEW"

# (action, label, description), in the order people see them.
NEXT_STEPS: tuple[tuple[str, str, str], ...] = (
    (
        CONTINUE_INVESTIGATION,
        "Continue the investigation",
        "Record why the investigation continues before a decision.",
    ),
    (
        REQUEST_ADDITIONAL_EVIDENCE,
        "Request additional evidence",
        "Ask a colleague or a role for evidence the case needs.",
    ),
    (
        REQUEST_ADDITIONAL_TESTING,
        "Request additional testing",
        "Ask a colleague or a role for tests and their results.",
    ),
    (
        REVIEW_SUPPLIER_CHANGE,
        "Review a supplier change",
        "Give the case owner (or a colleague or role) a follow-up to review a supplier change.",
    ),
    (
        REVIEW_PRODUCT_CHANGE,
        "Review a product change",
        "Give the case owner (or a colleague or role) a follow-up to review a product change.",
    ),
    (
        REQUEST_RISK_REVIEW,
        "Request a risk review",
        "Ask the risk reviewers to review the case.",
    ),
    (
        REQUEST_REGULATORY_REVIEW,
        "Request a regulatory review",
        "Ask the regulatory reviewers to review the case; reportability is theirs to determine.",
    ),
    (
        ESCALATE_FOR_QUALITY_REVIEW,
        "Escalate for quality review",
        "Quality review happens on the Decision Brief: prepare and submit it.",
    ),
    (
        NO_DECISION_YET,
        "No decision yet",
        "Record that no decision can be taken yet, and why.",
    ),
)
NEXT_STEP_CODES = tuple(code for code, _, _ in NEXT_STEPS)
NOTE_ACTIONS = frozenset({CONTINUE_INVESTIGATION, NO_DECISION_YET})
REVIEW_ACTIONS: dict[str, str] = {REQUEST_RISK_REVIEW: RISK, REQUEST_REGULATORY_REVIEW: REGULATORY}
EVIDENCE_ACTIONS = frozenset({REQUEST_ADDITIONAL_EVIDENCE, REQUEST_ADDITIONAL_TESTING})
CHANGE_ACTIONS: dict[str, str] = {REVIEW_SUPPLIER_CHANGE: "supplier", REVIEW_PRODUCT_CHANGE: "product"}
USE_DECISION_BRIEF = "Prepare and submit the Decision Brief for quality review"
TESTING_PREFIX = "Testing: "
EVIDENCE_TITLE_MAX = 240


def testing_title(title: str) -> str:
    """A testing request's title starts "Testing: " (once)."""
    text = _clean(title) or ""
    if text.lower().startswith(TESTING_PREFIX.strip().lower()):
        text = text[len(TESTING_PREFIX.strip()) :].strip()
    return (TESTING_PREFIX + text)[:EVIDENCE_TITLE_MAX]


def change_title(action: str, case_reference: str | None) -> str:
    kind = CHANGE_ACTIONS.get(action, "")
    return f"Review {kind} change for {case_reference}" if case_reference else f"Review {kind} change"


class NextStepPayload(BaseModel):
    action: str = Field(max_length=40)
    reason: str = Field(min_length=REASON_MIN, max_length=REASON_MAX)
    details: dict[str, Any] | None = None

    @field_validator("action")
    @classmethod
    def _action(cls, value: str) -> str:
        code = str(value or "").strip().upper()
        if code not in NEXT_STEP_CODES:
            raise ValueError(f"Choose one of: {', '.join(NEXT_STEP_CODES)}")
        return code

    @field_validator("reason")
    @classmethod
    def _reason(cls, value: str) -> str:
        text = str(value or "").strip()
        if len(" ".join(text.split())) < REASON_MIN:
            raise ValueError(f"Say in at least {REASON_MIN} characters why")
        return text


class ReviewStepDetails(BaseModel):
    due_at: datetime | None = None

    @field_validator("due_at")
    @classmethod
    def _due(cls, value: datetime | None) -> datetime | None:
        return _future(value)


class EvidenceStepDetails(BaseModel):
    """A request to a colleague (``recipient_user_id``) or a role (``recipient_role``) on the case; the evidence
    request rules (backend/app/evidence_workflow/rules.py) check the rest."""

    title: str = Field(min_length=3, max_length=EVIDENCE_TITLE_MAX)
    requested_items: list[str] = Field(min_length=1, max_length=20)
    recipient_user_id: uuid.UUID | None = None
    recipient_role: str | None = Field(default=None, max_length=60)
    due_at: datetime | None = None
    priority: str = Field(default="MEDIUM", max_length=20)
    unknown_id: uuid.UUID | None = None

    @field_validator("title")
    @classmethod
    def _title(cls, value: str) -> str:
        text = _clean(value) or ""
        if len(text) < 3:
            raise ValueError("Give the request a title of at least 3 characters")
        return text

    @field_validator("recipient_role")
    @classmethod
    def _role(cls, value: str | None) -> str | None:
        return _clean(value)

    @model_validator(mode="after")
    def _recipient(self):
        if self.recipient_user_id is None and not self.recipient_role:
            raise ValueError("Name the colleague or the role you ask")
        return self


class ChangeStepDetails(BaseModel):
    """Who reviews the change: a colleague (``assignee_user_id``), a role queue (``assigned_role``), or by default the
    case owner; and the follow-up's title (by default "Review supplier change for INV000147")."""

    assignee_user_id: uuid.UUID | None = None
    assigned_role: str | None = Field(default=None, max_length=60)
    title: str | None = Field(default=None, max_length=300)

    @field_validator("assigned_role", "title")
    @classmethod
    def _optional(cls, value: str | None) -> str | None:
        return _clean(value)


DETAIL_MODELS: dict[str, type[BaseModel]] = {
    REQUEST_RISK_REVIEW: ReviewStepDetails,
    REQUEST_REGULATORY_REVIEW: ReviewStepDetails,
    REQUEST_ADDITIONAL_EVIDENCE: EvidenceStepDetails,
    REQUEST_ADDITIONAL_TESTING: EvidenceStepDetails,
    REVIEW_SUPPLIER_CHANGE: ChangeStepDetails,
    REVIEW_PRODUCT_CHANGE: ChangeStepDetails,
}


def next_step_details(action: str, details: Mapping | None) -> BaseModel | None:
    """The validated details of a next step (pydantic ValidationError when they do not fit), or None for an action
    that takes none."""
    model = DETAIL_MODELS.get(action)
    if model is None:
        return None
    return model.model_validate(dict(details or {}))


def next_step_availability(
    action: str,
    *,
    can_work: bool,
    can_request_evidence: bool,
    case_open: bool,
    open_review_types: Iterable[str] = (),
) -> tuple[bool, str | None]:
    """Whether the person may take ``action`` on the case now, and why not."""
    if action == ESCALATE_FOR_QUALITY_REVIEW:
        return False, USE_DECISION_BRIEF
    if not can_work:
        return False, "Your role does not allow working on cases"
    if not case_open:
        return False, "The case is closed"
    if action in EVIDENCE_ACTIONS and not can_request_evidence:
        return False, "Your role does not allow requesting evidence"
    review_type = REVIEW_ACTIONS.get(action)
    if review_type is not None and review_type in set(open_review_types):
        return False, f"A {TYPE_LABELS[review_type].lower()} is already open"
    return True, None
