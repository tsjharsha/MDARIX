"""The rules of a case's intelligence, without a database: statuses and states with their labels, how AI output is
named, what a request body must hold. Imported by the router, the readiness checks and the unit tests.

AI output stays as the AI produced it. A person's judgement is recorded next to it (a hypothesis keeps the AI's status
and gets a ``human_status``), and nothing here ever claims proven causality: a failure chain link is at most
SUPPORTED by evidence, and no CONFIRMED state exists.
"""

from __future__ import annotations

import uuid

from pydantic import BaseModel, Field, field_validator, model_validator

from backend.app.db.models.intelligence import EPISTEMIC_TYPES, HYPOTHESIS_HUMAN_STATUSES, LINK_STATES

REASON_MIN = 10
REASON_MAX = 2000
STATEMENT_MIN = 10
OBSERVATION_MIN = 5
CHAIN_NAME_MIN = 3
CHAIN_NAME_MAX = 200
NODE_LABEL_MIN = 2
NODE_LABEL_MAX = 255
NODES_MIN = 2
NODES_MAX = 20
LINKS_MAX = 40
CATEGORY_MAX = 80

# ------------------------------------------------------------------------------------------------------ hypotheses

# hypotheses.origin as stored ("ai" for model-written, "system" for rule-written, "human" for a person's) and as shown.
ORIGIN_HUMAN = "human"
ORIGIN_CODES = {"ai": "AI", "system": "SYSTEM", "human": "HUMAN"}
# The AI's own status of a superseded hypothesis (replaced by a newer model-written set).
SUPERSEDED = "superseded"
# reviewer_disposition once a person has judged an AI hypothesis: AI re-runs never supersede it.
HUMAN_JUDGED = "HUMAN_JUDGED"
PROPOSED = "PROPOSED"
RETIRED = "RETIRED"
HUMAN_STATUSES = tuple(HYPOTHESIS_HUMAN_STATUSES)
HUMAN_STATUS_LABELS: dict[str, str] = {
    "PROPOSED": "Proposed",
    "HYPOTHESIZED": "Hypothesized",
    "PARTIALLY_SUPPORTED": "Partially supported",
    "STRONGLY_SUPPORTED": "Strongly supported",
    "WEAKLY_SUPPORTED": "Weakly supported",
    "CONTRADICTED": "Contradicted",
    "RETIRED": "Retired",
}
# The AI's statuses (hypothesis_engine HypothesisStatus, stored lowercase).
AI_STATUS_LABELS: dict[str, str] = {
    "proposed": "Proposed",
    "under_investigation": "Under investigation",
    "supported": "Supported by the evidence cited",
    "contradicted": "Contradicted",
    "mixed_evidence": "Mixed evidence",
    "insufficient_evidence": "Insufficient evidence",
    "requires_more_evidence": "Needs more evidence",
    "rejected": "Rejected",
    "human_review_required": "Needs human review",
    "no_currently_supportable_hypothesis": "No supportable hypothesis yet",
    "superseded": "Replaced by a newer AI run",
}
AI_INTERPRETATION = "AI interpretation"
SOMEONE = "a colleague"


def _readable(code: str) -> str:
    return code.replace("_", " ").strip().capitalize()


def origin_code(value: str | None) -> str:
    """AI, SYSTEM or HUMAN for a stored hypothesis origin."""
    text = str(value or "").strip().lower()
    return ORIGIN_CODES.get(text, text.upper() or "SYSTEM")


def human_status_label(code: str | None) -> str | None:
    if not code:
        return None
    text = str(code).upper()
    return HUMAN_STATUS_LABELS.get(text) or _readable(text)


def ai_status_label(code: str | None) -> str | None:
    if not code:
        return None
    text = str(code).lower()
    return AI_STATUS_LABELS.get(text) or _readable(text)


def kind_label(
    origin: str | None,
    human_status: str | None,
    *,
    created_by_name: str | None = None,
    judged_by_name: str | None = None,
) -> str:
    """What a hypothesis is to the reader: added by a person, judged by a person, or still the AI's interpretation."""
    if origin_code(origin) == "HUMAN":
        return f"Added by {created_by_name or SOMEONE}"
    if human_status:
        return f"Judged by {judged_by_name or SOMEONE}"
    return AI_INTERPRETATION


def counts_toward_case(ai_status: str | None, human_status: str | None) -> bool:
    """A hypothesis the case still considers: neither superseded by a newer AI run nor retired by a person."""
    return str(ai_status or "").lower() != SUPERSEDED and str(human_status or "").upper() != RETIRED


# ------------------------------------------------------------------------------------------- hypothesis evidence

RELATIONS = ("SUPPORTING", "CONTRADICTING", "CONTEXTUAL", "UNRESOLVED")
RELATION_TYPES: dict[str, str] = {
    "SUPPORTING": "support",
    "CONTRADICTING": "contradict",
    "CONTEXTUAL": "contextual",
    "UNRESOLVED": "unresolved",
}
RELATION_BUCKETS: dict[str, str] = {
    "support": "supporting",
    "contradict": "contradicting",
    "contextual": "contextual",
    "unresolved": "unresolved",
}
CONTRADICT = "contradict"
CREATED_BY_HUMAN = "human"
ADDED_BY_AI = "AI"


def relation_type(relation: str) -> str:
    """hypothesis_evidence.relation_type for a relation people choose (SUPPORTING -> support)."""
    return RELATION_TYPES[str(relation).upper()]


def relation_bucket(stored: str | None) -> str:
    """The list a stored link is shown in; anything unknown is unresolved."""
    return RELATION_BUCKETS.get(str(stored or "").lower(), "unresolved")


def link_is_human(created_by_type: str | None) -> bool:
    return str(created_by_type or "").lower() == CREATED_BY_HUMAN


# ---------------------------------------------------------------------------------------------------- unknowns

UNKNOWN_OPEN = "open"
UNKNOWN_IN_PROGRESS = "in_progress"
UNKNOWN_RESOLVED = "resolved"
UNKNOWN_ACCEPTED_LIMITATION = "accepted_limitation"
UNKNOWN_STATUSES = (UNKNOWN_OPEN, UNKNOWN_IN_PROGRESS, UNKNOWN_RESOLVED, UNKNOWN_ACCEPTED_LIMITATION)
# A person may also set an open or in-progress unknown aside as no longer relevant (superseded); a superseded unknown
# (set aside by a person or replaced by a newer AI run) never changes again.
UNKNOWN_SUPERSEDED = "superseded"
PERSON_UNKNOWN_STATUSES = (*UNKNOWN_STATUSES, UNKNOWN_SUPERSEDED)
SUPERSEDABLE_FROM = frozenset({UNKNOWN_OPEN, UNKNOWN_IN_PROGRESS})
# A reason given for these statuses is kept as the unknown's resolution (the answer, why it is accepted as is, or why
# it is no longer relevant).
RESOLUTION_STATUSES = frozenset({UNKNOWN_RESOLVED, UNKNOWN_ACCEPTED_LIMITATION, UNKNOWN_SUPERSEDED})
UNKNOWN_STATUS_LABELS: dict[str, str] = {
    "open": "Open",
    "in_progress": "In progress",
    "resolved": "Resolved",
    "accepted_limitation": "Accepted as a limitation",
    "superseded": "No longer relevant",
    "not_applicable": "Not applicable",
    "closed": "Closed",
}
# Where an unknown, an observation or a stored link came from, as shown.
ORIGIN_LABELS: dict[str, str] = {"HUMAN": "Person", "AI": "AI", "SYSTEM": "System"}


def unknown_transition_allowed(current: str | None, target: str) -> bool:
    """Whether a person may move an unknown from ``current`` to ``target`` (another status). Nothing leaves
    superseded; only an open or in-progress unknown is set aside as superseded."""
    code = str(current or "").lower()
    if code == UNKNOWN_SUPERSEDED or code == target:
        return False
    if target == UNKNOWN_SUPERSEDED:
        return code in SUPERSEDABLE_FROM
    return True


def unknown_status_label(code: str | None) -> str | None:
    if not code:
        return None
    text = str(code).lower()
    return UNKNOWN_STATUS_LABELS.get(text) or _readable(text)


def unknown_locked(status: str | None) -> bool:
    """A superseded unknown (its AI hypothesis was replaced) keeps its status."""
    return str(status or "").lower() == SUPERSEDED


def plain_origin(value: str | None) -> str:
    """HUMAN, AI or SYSTEM for a stored origin (unknowns, observations)."""
    text = str(value or "").strip().upper()
    return text if text in ORIGIN_LABELS else "SYSTEM"


def origin_label(code: str | None) -> str:
    return ORIGIN_LABELS.get(plain_origin(code), "System")


# --------------------------------------------------------------------------------------------- failure chains

CHAIN_ORIGIN_HUMAN = "human"
CHAIN_ORIGIN_ADOPTED = "ai_adopted"
CHAIN_ORIGIN_LABELS: dict[str, str] = {
    "HUMAN": "Built by a person",
    "AI_ADOPTED": "Adopted from an AI run",
    "SYSTEM": "System",
}
CHAIN_STATUS_DRAFT = "draft"
NODE_TYPE = "STATE"
LINK_STATE_CODES = tuple(LINK_STATES)
UNKNOWN_STATE = "UNKNOWN"
LINK_STATE_LABELS: dict[str, str] = {
    "SUPPORTED": "Supported by evidence",
    "PARTIALLY_SUPPORTED": "Partially supported",
    "HYPOTHESIZED": "Hypothesized",
    "UNKNOWN": "Unknown",
    "CONTRADICTED": "Contradicted",
}
# Link states stored before md30.
LEGACY_EDGE_STATES: dict[str, str] = {
    "established_fact": "SUPPORTED",
    "hypothesized": "HYPOTHESIZED",
    "contradicted": "CONTRADICTED",
}
# The AI's link epistemic status (failure_chain LinkStatus) as a stored link state. Anything else is UNKNOWN.
AI_LINK_STATES: dict[str, str] = {
    "OBSERVED_SOURCE_SUPPORTED": "SUPPORTED",
    "SUPPORTED": "SUPPORTED",
    "DETERMINISTICALLY_DERIVED": "PARTIALLY_SUPPORTED",
    "PARTIALLY_SUPPORTED": "PARTIALLY_SUPPORTED",
    "HYPOTHESIZED": "HYPOTHESIZED",
    "CONTRADICTED": "CONTRADICTED",
    "UNKNOWN_GAP": "UNKNOWN",
    "UNKNOWN": "UNKNOWN",
}


# A link a person calls (partially) supported names the evidence of the case it rests on.
EVIDENCE_STATES = frozenset({"SUPPORTED", "PARTIALLY_SUPPORTED"})
EVIDENCE_REQUIRED_MESSAGE = "A supported or partially supported link names the evidence it rests on"


def state_needs_evidence(state: str | None) -> bool:
    return str(state or "").upper() in EVIDENCE_STATES


def chain_origin(value: str | None) -> str:
    text = str(value or "").strip().upper()
    return text if text in CHAIN_ORIGIN_LABELS else "SYSTEM"


def chain_origin_label(value: str | None) -> str:
    return CHAIN_ORIGIN_LABELS[chain_origin(value)]


def link_state(stored: str | None) -> str:
    """The state of a stored link (states stored before md30 included); anything else is UNKNOWN."""
    text = str(stored or "").strip()
    if text.upper() in LINK_STATE_CODES:
        return text.upper()
    return LEGACY_EDGE_STATES.get(text.lower(), UNKNOWN_STATE)


def ai_link_state(epistemic_status: str | None) -> str:
    """The link state an adopted AI link keeps (never more than SUPPORTED)."""
    return AI_LINK_STATES.get(str(epistemic_status or "").strip().upper(), UNKNOWN_STATE)


def link_state_label(code: str | None) -> str:
    return LINK_STATE_LABELS.get(link_state(code), "Unknown")


# ------------------------------------------------------------------------------------------------ observations

HUMAN_EPISTEMIC_TYPES = tuple(item for item in EPISTEMIC_TYPES if item != "AI_INTERPRETATION")
EPISTEMIC_LABELS: dict[str, str] = {
    "FACT": "Fact",
    "SOURCE_ASSERTION": "Source assertion",
    "DERIVED_OBSERVATION": "Derived observation",
    "AI_INTERPRETATION": "AI interpretation",
}
OBSERVATION_ORIGIN_HUMAN = "HUMAN"
# evidence_observations.observation_type and extraction_method of what a person records (md31); its kind is in
# epistemic_type.
HUMAN_OBSERVATION_TYPE = "HUMAN_OBSERVATION"
HUMAN_EXTRACTION_METHOD = "HUMAN"
# A person's statement has not been through the extraction checks; it is not shown as VALIDATED.
HUMAN_QUALITY_STATUS = "HUMAN_RECORDED"
AI_EXTRACTION_METHODS = frozenset({"GENAI", "AI", "MODEL", "LLM"})


def observation_origin(origin: str | None, extraction_method: str | None) -> str:
    """HUMAN, AI or SYSTEM; rows without an origin are read from how they were extracted (as md30 labelled them)."""
    if origin:
        return plain_origin(origin)
    if str(extraction_method or "").upper() == HUMAN_EXTRACTION_METHOD:
        return "HUMAN"
    return "AI" if str(extraction_method or "").upper() in AI_EXTRACTION_METHODS else "SYSTEM"


def observation_kind(epistemic_type: str | None, observation_type: str | None, extraction_method: str | None) -> str:
    """FACT, SOURCE_ASSERTION, DERIVED_OBSERVATION or AI_INTERPRETATION (rows without one as md30 labelled them)."""
    if epistemic_type and str(epistemic_type).upper() in EPISTEMIC_TYPES:
        return str(epistemic_type).upper()
    kind = str(observation_type or "").upper()
    by_ai = str(extraction_method or "").upper() in AI_EXTRACTION_METHODS
    if kind == "STRUCTURED_EXTRACTION" and not by_ai:
        return "FACT"
    if kind in {"EXPLICIT_SOURCE_STATEMENT", "STRUCTURED_EXTRACTION"}:
        return "SOURCE_ASSERTION"
    return "AI_INTERPRETATION" if by_ai else "DERIVED_OBSERVATION"


def epistemic_label(code: str | None) -> str | None:
    return EPISTEMIC_LABELS.get(str(code or "").upper()) if code else None


# ------------------------------------------------------------------------------------------------------ history

OBJECT_HYPOTHESIS = "HYPOTHESIS"
OBJECT_HYPOTHESIS_EVIDENCE = "HYPOTHESIS_EVIDENCE"
OBJECT_UNKNOWN = "UNKNOWN"
OBJECT_FAILURE_CHAIN = "FAILURE_CHAIN"
OBJECT_FAILURE_CHAIN_LINK = "FAILURE_CHAIN_LINK"
OBJECT_OBSERVATION = "OBSERVATION"
EVENT_CREATED = "CREATED"
EVENT_STATUS_CHANGED = "STATUS_CHANGED"
EVENT_EVIDENCE_LINKED = "EVIDENCE_LINKED"
EVENT_EVIDENCE_RETRACTED = "EVIDENCE_RETRACTED"
EVENT_ADOPTED = "ADOPTED"
EVENT_STATE_CHANGED = "STATE_CHANGED"
EVENT_LABELS: dict[str, str] = {
    EVENT_CREATED: "Added",
    EVENT_STATUS_CHANGED: "Status changed",
    EVENT_EVIDENCE_LINKED: "Evidence linked",
    EVENT_EVIDENCE_RETRACTED: "Evidence link withdrawn",
    EVENT_ADOPTED: "Adopted from an AI run",
    EVENT_STATE_CHANGED: "Link state changed",
}
OBJECT_LABELS: dict[str, str] = {
    OBJECT_HYPOTHESIS: "Hypothesis",
    OBJECT_HYPOTHESIS_EVIDENCE: "Hypothesis evidence",
    OBJECT_UNKNOWN: "Unknown",
    OBJECT_FAILURE_CHAIN: "Failure chain",
    OBJECT_FAILURE_CHAIN_LINK: "Failure chain link",
    OBJECT_OBSERVATION: "Observation",
}
HISTORY_PAGE_SIZE_DEFAULT = 50
HISTORY_PAGE_SIZE_MAX = 200


def audit_action(event_type: str) -> str:
    return f"INTELLIGENCE_{event_type}"


def event_label(code: str | None) -> str | None:
    return EVENT_LABELS.get(str(code or "").upper()) or (_readable(str(code)) if code else None)


# ------------------------------------------------------------------------------------------------------ payloads


def _text(value) -> str | None:
    text = str(value or "").strip()
    return text or None


def _required(value, minimum: int, what: str) -> str:
    text = str(value or "").strip()
    if len(text) < minimum:
        raise ValueError(f"{what} needs at least {minimum} characters")
    return text


def _code(value, allowed, what: str) -> str:
    code = str(value or "").strip().upper()
    if code not in allowed:
        raise ValueError(f"Choose {what}: {', '.join(allowed)}")
    return code


class HypothesisCreatePayload(BaseModel):
    """A hypothesis a person adds (origin "human"): proposed, with the reasoning behind it."""

    statement: str = Field(min_length=STATEMENT_MIN, max_length=REASON_MAX)
    rationale: str | None = Field(default=None, max_length=REASON_MAX)

    @field_validator("statement")
    @classmethod
    def _statement(cls, value: str) -> str:
        return _required(value, STATEMENT_MIN, "The hypothesis")

    @field_validator("rationale")
    @classmethod
    def _rationale(cls, value: str | None) -> str | None:
        return _text(value)


class HypothesisStatusPayload(BaseModel):
    """A person's judgement of a hypothesis, with the reason."""

    human_status: str = Field(max_length=30)
    reason: str = Field(min_length=REASON_MIN, max_length=REASON_MAX)

    @field_validator("human_status")
    @classmethod
    def _status(cls, value: str) -> str:
        return _code(value, HUMAN_STATUSES, "a status")

    @field_validator("reason")
    @classmethod
    def _reason(cls, value: str) -> str:
        return _required(value, REASON_MIN, "The reason")


class HypothesisEvidencePayload(BaseModel):
    """Evidence of the case linked to a hypothesis by a person, with what it means for the hypothesis and why."""

    evidence_id: uuid.UUID
    relation: str = Field(max_length=30)
    rationale: str = Field(min_length=REASON_MIN, max_length=REASON_MAX)

    @field_validator("relation")
    @classmethod
    def _relation(cls, value: str) -> str:
        return _code(value, RELATIONS, "what the evidence means for the hypothesis")

    @field_validator("rationale")
    @classmethod
    def _rationale(cls, value: str) -> str:
        return _required(value, REASON_MIN, "The rationale")


class RetractPayload(BaseModel):
    reason: str = Field(min_length=REASON_MIN, max_length=REASON_MAX)

    @field_validator("reason")
    @classmethod
    def _reason(cls, value: str) -> str:
        return _required(value, REASON_MIN, "The reason")


class UnknownCreatePayload(BaseModel):
    """An unknown a person records (origin "human"), optionally about one hypothesis of the case."""

    description: str = Field(min_length=REASON_MIN, max_length=REASON_MAX)
    category: str | None = Field(default=None, max_length=CATEGORY_MAX)
    evidence_needed: str | None = Field(default=None, max_length=REASON_MAX)
    hypothesis_id: uuid.UUID | None = None

    @field_validator("description")
    @classmethod
    def _description(cls, value: str) -> str:
        return _required(value, REASON_MIN, "The unknown")

    @field_validator("category", "evidence_needed")
    @classmethod
    def _optional(cls, value: str | None) -> str | None:
        return _text(value)


class UnknownStatusPayload(BaseModel):
    """A new status for an unknown. The reason is required: for ``resolved`` it is the resolution, for
    ``accepted_limitation`` why the case accepts not knowing, for ``superseded`` why it is no longer relevant."""

    status: str = Field(max_length=30)
    reason: str = Field(min_length=REASON_MIN, max_length=REASON_MAX)

    @field_validator("status")
    @classmethod
    def _status(cls, value: str) -> str:
        code = str(value or "").strip().lower()
        if code not in PERSON_UNKNOWN_STATUSES:
            raise ValueError(f"Choose a status: {', '.join(PERSON_UNKNOWN_STATUSES)}")
        return code

    @field_validator("reason")
    @classmethod
    def _reason(cls, value: str) -> str:
        return _required(value, REASON_MIN, "The reason")


class ChainLinkInput(BaseModel):
    from_index: int = Field(ge=0, lt=NODES_MAX)
    to_index: int = Field(ge=0, lt=NODES_MAX)
    state: str = Field(max_length=30)
    evidence_id: uuid.UUID | None = None
    rationale: str | None = Field(default=None, max_length=REASON_MAX)

    @field_validator("state")
    @classmethod
    def _state(cls, value: str) -> str:
        return _code(value, LINK_STATE_CODES, "a link state")

    @field_validator("rationale")
    @classmethod
    def _rationale(cls, value: str | None) -> str | None:
        return _text(value)

    @model_validator(mode="after")
    def _evidence(self):
        if state_needs_evidence(self.state) and self.evidence_id is None:
            raise ValueError(EVIDENCE_REQUIRED_MESSAGE)
        return self


class FailureChainCreatePayload(BaseModel):
    """A failure chain a person builds: its steps in order and the links between them, each with its state."""

    name: str = Field(min_length=CHAIN_NAME_MIN, max_length=CHAIN_NAME_MAX)
    nodes: list[str] = Field(min_length=NODES_MIN, max_length=NODES_MAX)
    links: list[ChainLinkInput] = Field(min_length=1, max_length=LINKS_MAX)

    @field_validator("name")
    @classmethod
    def _name(cls, value: str) -> str:
        return _required(" ".join(str(value or "").split()), CHAIN_NAME_MIN, "The name")

    @field_validator("nodes")
    @classmethod
    def _nodes(cls, value: list[str]) -> list[str]:
        labels = [" ".join(str(item or "").split()) for item in value]
        if any(len(label) < NODE_LABEL_MIN or len(label) > NODE_LABEL_MAX for label in labels):
            raise ValueError(f"Name each step in {NODE_LABEL_MIN} to {NODE_LABEL_MAX} characters")
        return labels

    @model_validator(mode="after")
    def _links(self):
        count = len(self.nodes)
        pairs = set()
        for link in self.links:
            if link.from_index >= count or link.to_index >= count:
                raise ValueError("A link joins two steps of the chain")
            if link.from_index == link.to_index:
                raise ValueError("A link joins two different steps")
            pair = (link.from_index, link.to_index)
            if pair in pairs:
                raise ValueError("Two steps are joined once")
            pairs.add(pair)
        return self


class AdoptChainPayload(BaseModel):
    """An AI failure chain to copy into the case (its links keep the AI's epistemic status)."""

    ai_execution_id: uuid.UUID
    ai_chain_id: str = Field(min_length=1, max_length=64)

    @field_validator("ai_chain_id")
    @classmethod
    def _chain(cls, value: str) -> str:
        return str(value or "").strip().lower()


class LinkStatePayload(BaseModel):
    state: str = Field(max_length=30)
    reason: str = Field(min_length=REASON_MIN, max_length=REASON_MAX)
    evidence_id: uuid.UUID | None = None

    @field_validator("state")
    @classmethod
    def _state(cls, value: str) -> str:
        return _code(value, LINK_STATE_CODES, "a link state")

    @field_validator("reason")
    @classmethod
    def _reason(cls, value: str) -> str:
        return _required(value, REASON_MIN, "The reason")


class ObservationCreatePayload(BaseModel):
    """An observation a person records on evidence of the case. People record facts, source assertions and derived
    observations; an AI interpretation is only ever the AI's."""

    evidence_id: uuid.UUID
    statement: str = Field(min_length=OBSERVATION_MIN, max_length=REASON_MAX)
    epistemic_type: str = Field(max_length=30)
    rationale: str | None = Field(default=None, max_length=REASON_MAX)

    @field_validator("statement")
    @classmethod
    def _statement(cls, value: str) -> str:
        return _required(value, OBSERVATION_MIN, "The observation")

    @field_validator("epistemic_type")
    @classmethod
    def _kind(cls, value: str) -> str:
        code = str(value or "").strip().upper()
        if code == "AI_INTERPRETATION":
            raise ValueError("An AI interpretation is only recorded by the AI; choose another kind")
        return _code(code, HUMAN_EPISTEMIC_TYPES, "the kind of observation")

    @field_validator("rationale")
    @classmethod
    def _rationale(cls, value: str | None) -> str | None:
        return _text(value)
