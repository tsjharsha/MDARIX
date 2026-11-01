"""The rules of evidence review and evidence requests, without a database: the statuses, their labels, what a request
body must hold and what a person may do with a request. Imported by the routers and by the unit tests.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

from pydantic import BaseModel, Field, field_validator, model_validator

from backend.app.db.models.case_scope import EVIDENCE_RELATIONSHIPS, EVIDENCE_REVIEW_STATUSES

# ------------------------------------------------------------------------------------------------- evidence review

UNREVIEWED = "UNREVIEWED"
REVIEW_STATUS_LABELS: dict[str, str] = {
    "UNREVIEWED": "Not reviewed",
    "ACCEPTED": "Accepted",
    "ACCEPTED_WITH_LIMITATION": "Accepted with limitation",
    "REJECTED": "Rejected",
    "QUARANTINED": "Quarantined",
    "SUPERSEDED": "Superseded",
}
RELATIONSHIP_LABELS: dict[str, str] = {
    "SUPPORTING": "Supporting",
    "CONTRADICTING": "Contradicting",
    "CONTEXTUAL": "Context",
    "UNRESOLVED": "Unresolved",
    "UNRELATED": "Unrelated",
    "UNREVIEWED": "Not reviewed",
}
# A review always decides both: a status other than "not reviewed", and what the evidence means for the case.
REVIEWED_STATUSES = tuple(status for status in EVIDENCE_REVIEW_STATUSES if status != UNREVIEWED)
REVIEWED_RELATIONSHIPS = tuple(item for item in EVIDENCE_RELATIONSHIPS if item != UNREVIEWED)
# Setting evidence aside needs a reason; accepting it with a limitation needs the limitation.
REASON_REQUIRED_STATUSES = frozenset({"REJECTED", "QUARANTINED", "SUPERSEDED"})
LIMITATION_REQUIRED_STATUSES = frozenset({"ACCEPTED_WITH_LIMITATION"})
REASON_MIN = 10
REASON_MAX = 2000
# Where the evidence of a case comes from: linked from elsewhere, recorded on the case itself, or accepted from an
# evidence request.
ORIGINS = ("LINKED", "DIRECT", "REQUEST")
# A closed or cancelled case keeps its evidence as it was.
CLOSED_CASE_STATES = frozenset({"CLOSED", "CANCELLED"})

COUNT_KEYS = (
    "total",
    "unreviewed",
    "accepted",
    "accepted_with_limitation",
    "rejected",
    "quarantined",
    "superseded",
    "supporting",
    "contradicting",
    "contextual",
    "unresolved",
    "unrelated",
)


def case_closed(workflow_state: str | None, status: str | None = None) -> bool:
    """True for a CLOSED or CANCELLED case (also a case whose legacy status says closed)."""
    return str(workflow_state or "").upper() in CLOSED_CASE_STATES or str(status or "").strip().lower() == "closed"


def review_status_label(code: str | None) -> str | None:
    return REVIEW_STATUS_LABELS.get(str(code or "").upper(), code) if code else None


def relationship_label(code: str | None) -> str | None:
    return RELATIONSHIP_LABELS.get(str(code or "").upper(), code) if code else None


def _text(value) -> str | None:
    text = str(value or "").strip()
    return text or None


def review_problem(review_status: str, relationship: str, reason: str | None, limitation: str | None) -> str | None:
    """Why a review cannot be recorded as given, or None when it can."""
    if review_status not in REVIEWED_STATUSES:
        return f"Choose a review status: {', '.join(REVIEWED_STATUSES)}"
    if relationship not in REVIEWED_RELATIONSHIPS:
        return f"Choose what the evidence means for the case: {', '.join(REVIEWED_RELATIONSHIPS)}"
    if review_status in REASON_REQUIRED_STATUSES and len(reason or "") < REASON_MIN:
        return f"Say in at least {REASON_MIN} characters why the evidence is {review_status.lower()}"
    if review_status in LIMITATION_REQUIRED_STATUSES and not limitation:
        return "Describe the limitation of this evidence"
    return None


def evidence_counts(items: list[dict]) -> dict[str, int]:
    """How many inventory items have each review status and relationship."""
    counts = dict.fromkeys(COUNT_KEYS, 0)
    counts["total"] = len(items)
    for item in items:
        link = item.get("link") or {}
        for value in (link.get("review_status"), link.get("relationship")):
            key = str(value or "").lower()
            if key in counts and key != "total":
                counts[key] += 1
    # UNREVIEWED is both a status and a relationship: count the evidence, not the two fields.
    counts["unreviewed"] = sum(1 for item in items if (item.get("link") or {}).get("review_status") == UNREVIEWED)
    return counts


class EvidenceLinkPayload(BaseModel):
    """Evidence of the organization to add to a case. Linking twice changes nothing; nothing is ever unlinked (mark
    it SUPERSEDED or UNRELATED instead)."""

    evidence_ids: list[uuid.UUID] = Field(min_length=1, max_length=100)
    relationship: str = Field(default=UNREVIEWED, max_length=30)
    reason: str | None = Field(default=None, max_length=REASON_MAX)

    @field_validator("relationship")
    @classmethod
    def _relationship(cls, value: str) -> str:
        code = str(value or "").strip().upper() or UNREVIEWED
        if code not in EVIDENCE_RELATIONSHIPS:
            raise ValueError(f"Choose one of: {', '.join(EVIDENCE_RELATIONSHIPS)}")
        return code

    @field_validator("reason")
    @classmethod
    def _reason(cls, value: str | None) -> str | None:
        return _text(value)

    @field_validator("evidence_ids")
    @classmethod
    def _distinct(cls, value: list[uuid.UUID]) -> list[uuid.UUID]:
        return list(dict.fromkeys(value))


class EvidenceReviewPayload(BaseModel):
    """A case's judgement of one piece of evidence: its quality (review status) and its meaning (relationship)."""

    review_status: str = Field(max_length=30)
    relationship: str = Field(max_length=30)
    reason: str | None = Field(default=None, max_length=REASON_MAX)
    limitation: str | None = Field(default=None, max_length=REASON_MAX)

    @field_validator("review_status", "relationship")
    @classmethod
    def _code(cls, value: str) -> str:
        return str(value or "").strip().upper()

    @field_validator("reason", "limitation")
    @classmethod
    def _optional_text(cls, value: str | None) -> str | None:
        return _text(value)

    @model_validator(mode="after")
    def _rules(self):
        problem = review_problem(self.review_status, self.relationship, self.reason, self.limitation)
        if problem:
            raise ValueError(problem)
        return self


# ---------------------------------------------------------------------------------------------- evidence requests

KIND_INTERNAL = "INTERNAL"
KIND_SUPPLIER = "SUPPLIER"
REQUEST_KINDS = (KIND_INTERNAL, KIND_SUPPLIER)
PRIORITIES = ("LOW", "MEDIUM", "HIGH", "CRITICAL")
# Supplier requests keep the statuses of the existing supplier flow (PENDING_DELIVERY, SENT, REPLIED); requests to a
# colleague or a role move OPEN -> ACKNOWLEDGED -> RECEIVED (or CANNOT_PROVIDE). Either kind ends REVIEWED or
# CANCELLED.
INTERNAL_STATUSES = ("OPEN", "ACKNOWLEDGED", "RECEIVED", "REVIEWED", "CANNOT_PROVIDE", "CANCELLED")
# SAVED: a free trial's request, kept and never emailed (a trial sends nothing to suppliers, J33).
SUPPLIER_STATUSES = ("SAVED", "PENDING_DELIVERY", "SENT", "REPLIED", "REVIEWED", "CANCELLED")
STATUS_LABELS: dict[str, str] = {
    "OPEN": "Open",
    "ACKNOWLEDGED": "Acknowledged",
    "RECEIVED": "Answered",
    "REVIEWED": "Reviewed",
    "CANNOT_PROVIDE": "Cannot provide",
    "CANCELLED": "Cancelled",
    "SAVED": "Saved, not sent",
    "PENDING_DELIVERY": "Sent",
    "SENT": "Sent",
    "REPLIED": "Answered",
}
# Still waiting for the answer (these can be cancelled and become overdue).
WAITING_STATUSES = frozenset({"OPEN", "ACKNOWLEDGED", "SAVED", "PENDING_DELIVERY", "SENT"})
# Answered and waiting for the requester's review.
ANSWERED_STATUSES = frozenset({"RECEIVED", "REPLIED"})
# Nothing more happens to these.
FINISHED_STATUSES = frozenset({"REVIEWED", "CANNOT_PROVIDE", "CANCELLED"})
# The recipient may still answer these.
ANSWERABLE_STATUSES = frozenset({"OPEN", "ACKNOWLEDGED"})
BOXES = ("sent", "received", "all")
TITLE_MIN = 3
TITLE_MAX = 240
ITEMS_MAX = 20
ITEM_MAX = 240
NOTE_MAX = 5000
DEFAULT_EVIDENCE_TYPE = "EVIDENCE_REQUEST_RESPONSE"
EVIDENCE_SOURCE_SYSTEM = "MDARIX evidence request"
# Workflow task source types: supplier requests keep the Phase 1 source type, requests to colleagues have their own.
SUPPLIER_SOURCE_TYPE = "SupplierEvidenceRequest"
INTERNAL_SOURCE_TYPE = "EvidenceRequest"


def request_kind(value: str | None) -> str:
    return KIND_INTERNAL if str(value or "").upper() == KIND_INTERNAL else KIND_SUPPLIER


def task_source_type(kind: str | None) -> str:
    return INTERNAL_SOURCE_TYPE if request_kind(kind) == KIND_INTERNAL else SUPPLIER_SOURCE_TYPE


def status_label(status: str | None) -> str | None:
    if not status:
        return None
    code = str(status).upper()
    return STATUS_LABELS.get(code) or code.replace("_", " ").capitalize()


def as_utc(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def is_overdue(status: str | None, due_at: datetime | None, now: datetime | None = None) -> bool:
    """Past its due date and still waiting for the answer."""
    if due_at is None or str(status or "").upper() not in WAITING_STATUSES:
        return False
    return as_utc(due_at) < (now or datetime.now(timezone.utc))


def request_actions(
    *,
    kind: str | None,
    status: str | None,
    is_requester: bool,
    is_recipient: bool,
    can_assign: bool,
    can_review_evidence: bool,
) -> dict[str, bool]:
    """What the person may do with a request now. The recipient (the person asked, or anyone holding the role asked)
    acknowledges and answers a request to a colleague; its requester, or whoever assigns work, cancels a request still
    waiting; its requester, or anyone who reviews evidence, reviews an answered one."""
    code = str(status or "").upper()
    internal = request_kind(kind) == KIND_INTERNAL
    answering = internal and is_recipient and code in ANSWERABLE_STATUSES
    return {
        "can_acknowledge": internal and is_recipient and code == "OPEN",
        "can_respond": answering,
        "can_cannot_provide": answering,
        "can_cancel": code in WAITING_STATUSES and (is_requester or can_assign),
        "can_review": code in ANSWERED_STATUSES and (is_requester or can_review_evidence),
        "can_attach": code not in FINISHED_STATUSES and (is_requester or (internal and is_recipient)),
    }


class EvidenceRequestPayload(BaseModel):
    """A request for evidence on a case: to a colleague or a role (INTERNAL), or to a supplier (SUPPLIER, sent through
    the existing supplier request flow)."""

    kind: str = Field(max_length=20)
    title: str = Field(min_length=TITLE_MIN, max_length=TITLE_MAX)
    requested_items: list[str] = Field(min_length=1, max_length=ITEMS_MAX)
    rationale: str | None = Field(default=None, max_length=REASON_MAX)
    unknown_id: uuid.UUID | None = None
    due_at: datetime | None = None
    priority: str = Field(default="MEDIUM", max_length=20)
    recipient_user_id: uuid.UUID | None = None
    recipient_role: str | None = Field(default=None, max_length=60)
    supplier_id: uuid.UUID | None = None
    # The supplier's address; ``recipient_email`` is accepted as another name for it.
    recipient: str | None = Field(default=None, max_length=254)
    recipient_email: str | None = Field(default=None, max_length=254)

    @field_validator("kind")
    @classmethod
    def _kind(cls, value: str) -> str:
        code = str(value or "").strip().upper()
        if code not in REQUEST_KINDS:
            raise ValueError("Ask a colleague (INTERNAL) or a supplier (SUPPLIER)")
        return code

    @field_validator("title")
    @classmethod
    def _title(cls, value: str) -> str:
        text = " ".join(str(value or "").split())
        if len(text) < TITLE_MIN:
            raise ValueError(f"Give the request a title of at least {TITLE_MIN} characters")
        return text

    @field_validator("requested_items")
    @classmethod
    def _items(cls, items: list[str]) -> list[str]:
        cleaned = [" ".join(str(item or "").split()) for item in items]
        cleaned = [item for item in cleaned if item]
        if not cleaned or any(len(item) > ITEM_MAX for item in cleaned):
            raise ValueError(f"List what you need, up to {ITEM_MAX} characters each")
        return cleaned

    @field_validator("rationale", "recipient_role", "recipient", "recipient_email")
    @classmethod
    def _optional(cls, value: str | None) -> str | None:
        return _text(value)

    @field_validator("priority")
    @classmethod
    def _priority(cls, value: str) -> str:
        code = str(value or "").strip().upper() or "MEDIUM"
        if code not in PRIORITIES:
            raise ValueError(f"Choose one of: {', '.join(PRIORITIES)}")
        return code

    @field_validator("due_at")
    @classmethod
    def _due(cls, value: datetime | None) -> datetime | None:
        value = as_utc(value)
        if value is not None and value <= datetime.now(timezone.utc):
            raise ValueError("Choose a due date in the future")
        return value

    @model_validator(mode="after")
    def _recipient(self):
        if not self.recipient and self.recipient_email:
            self.recipient = self.recipient_email
        if self.kind == KIND_INTERNAL:
            if self.recipient_user_id is None and not self.recipient_role:
                raise ValueError("Name the colleague or the role you ask")
            if self.supplier_id is not None or self.recipient:
                raise ValueError("A request to a colleague has no supplier or email address")
        else:
            if self.supplier_id is None or not self.recipient:
                raise ValueError("Choose the supplier and the email address the request goes to")
            if self.recipient_user_id is not None or self.recipient_role:
                raise ValueError("A supplier request goes to an email address, not to a colleague or a role")
        return self


class RespondPayload(BaseModel):
    note: str = Field(min_length=1, max_length=NOTE_MAX)

    @field_validator("note")
    @classmethod
    def _note(cls, value: str) -> str:
        text = str(value or "").strip()
        if not text:
            raise ValueError("Describe the evidence you provide")
        return text


class ReasonPayload(BaseModel):
    reason: str = Field(min_length=REASON_MIN, max_length=REASON_MAX)

    @field_validator("reason")
    @classmethod
    def _reason(cls, value: str) -> str:
        text = str(value or "").strip()
        if len(text) < REASON_MIN:
            raise ValueError(f"Say in at least {REASON_MIN} characters why")
        return text


class RequestReviewPayload(BaseModel):
    """The requester's review of an answer: accept it as evidence of the case (with its review status and
    relationship), or reject it with a reason (no evidence is created)."""

    accept: bool
    title: str | None = Field(default=None, max_length=255)
    evidence_type: str | None = Field(default=None, max_length=80)
    review_status: str | None = Field(default=None, max_length=30)
    relationship: str | None = Field(default=None, max_length=30)
    reason: str | None = Field(default=None, max_length=REASON_MAX)
    limitation: str | None = Field(default=None, max_length=REASON_MAX)

    @field_validator("title", "reason", "limitation")
    @classmethod
    def _optional(cls, value: str | None) -> str | None:
        return _text(value)

    @field_validator("evidence_type")
    @classmethod
    def _type(cls, value: str | None) -> str | None:
        text = _text(value)
        if text is None:
            return None
        code = "_".join(text.upper().replace("-", " ").split())
        if not all(char.isalnum() or char == "_" for char in code):
            raise ValueError("Use letters, digits and underscores for the evidence type")
        return code

    @field_validator("review_status", "relationship")
    @classmethod
    def _code(cls, value: str | None) -> str | None:
        return str(value or "").strip().upper() or None

    @model_validator(mode="after")
    def _rules(self):
        if self.accept:
            problem = review_problem(self.review_status or "", self.relationship or "", self.reason, self.limitation)
            if problem:
                raise ValueError(problem)
        elif len(self.reason or "") < REASON_MIN:
            raise ValueError(f"Say in at least {REASON_MIN} characters why the answer is not accepted")
        return self
