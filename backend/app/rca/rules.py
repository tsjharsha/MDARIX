"""The rules of the root-cause tools (RCA spec, approved 12 Nov 2026). No AI anywhere: MDARIX structures the
investigation; a person finds and signs the cause.

- Fishbone (3.2): each possible cause is a hypothesis with a ``cause_category``; seven categories (RCA-D3), Software
  shown only for software products or when a cause already uses it.
- 5 Whys (3.1): a failure chain with ``method = FIVE_WHYS``; node 1 is the problem, then 2 to 7 whys. The last why is
  never a root cause; it may name the hypothesis it is.
- Confirmed cause (3.3): only a signed decision in which the signer ticks the accepted hypotheses and the category
  (RCA-D1). Required on an accepted conclusion, "Not determined" with a reason allowed (RCA-D4).
"""

from __future__ import annotations

import uuid

from pydantic import BaseModel, Field, field_validator, model_validator

PEOPLE, PROCESS, METHOD, MATERIAL, MACHINE, ENVIRONMENT, SOFTWARE = (
    "PEOPLE",
    "PROCESS",
    "METHOD",
    "MATERIAL",
    "MACHINE",
    "ENVIRONMENT",
    "SOFTWARE",
)
CAUSE_CATEGORIES = (PEOPLE, PROCESS, METHOD, MATERIAL, MACHINE, ENVIRONMENT, SOFTWARE)
NOT_DETERMINED = "NOT_DETERMINED"
CATEGORY_LABELS = {
    PEOPLE: "People",
    PROCESS: "Process",
    METHOD: "Method",
    MATERIAL: "Material",
    MACHINE: "Machine",
    ENVIRONMENT: "Environment",
    SOFTWARE: "Software",
    NOT_DETERMINED: "Not determined",
}
NOT_CATEGORISED = "Not categorised"
NO_CONFIRMED_CAUSE = "No confirmed cause yet"
NOT_IN_FMEA = "Not in your FMEA: consider a risk-file update"

CHAIN = "CHAIN"
FIVE_WHYS = "FIVE_WHYS"
WHYS_MIN = 2
WHYS_MAX = 7
UNKNOWN_WHY = "Unknown: what would show it?"
WHY_LINK_OBJECT = "HYPOTHESIS"

REASON_MIN = 10
TEXT_MAX = 2000
LABEL_MAX = 255
STATEMENT_MIN = 10
TICKED_MAX = 20

# Outcomes that accept a conclusion: the cause category is required (RCA-D4).
ACCEPTING_OUTCOMES = ("ACCEPT_CONCLUSION", "ACCEPT_WITH_CONDITIONS")
# Statuses a person rules a cause out with (spec 3.2): it stays visible, struck through, with the reason.
RULED_OUT = ("CONTRADICTED", "RETIRED")


def category_label(code: str | None) -> str:
    return CATEGORY_LABELS.get(str(code or "").upper(), NOT_CATEGORISED)


def shows_software(device_category: str | None, used: set[str]) -> bool:
    """Software is a fishbone column for software products (SaMD) or when a cause already uses it."""
    return str(device_category or "").upper() == SOFTWARE or SOFTWARE in used


def causal_claim(statement: str) -> str | None:
    """The wording that makes a possible cause read as an established one; the hypothesis validator's own lists."""
    from hypothesis_engine.validator import CAUSAL_FACT_PHRASES, FORBIDDEN_NUMERIC_TERMS

    lowered = " ".join(str(statement or "").lower().split())
    return next((phrase for phrase in (*CAUSAL_FACT_PHRASES, *FORBIDDEN_NUMERIC_TERMS) if phrase in lowered), None)


def _clean(value) -> str:
    return " ".join(str(value or "").split())


def _category(value) -> str:
    code = _clean(value).upper()
    if code not in CAUSE_CATEGORIES:
        raise ValueError(f"Choose a category: {', '.join(CATEGORY_LABELS[item] for item in CAUSE_CATEGORIES)}")
    return code


class CauseCreatePayload(BaseModel):
    """A fishbone quick add: one line, a category, optionally the FMEA failure mode it names."""

    statement: str = Field(max_length=TEXT_MAX)
    cause_category: str = Field(max_length=20)
    failure_mode_id: uuid.UUID | None = None

    @field_validator("statement")
    @classmethod
    def _statement(cls, value: str) -> str:
        text = _clean(value)
        if len(text) < STATEMENT_MIN:
            raise ValueError(f"Describe the possible cause in at least {STATEMENT_MIN} characters")
        claim = causal_claim(text)
        if claim:
            raise ValueError(f"A possible cause is not yet a finding: remove “{claim}”")
        return text

    @field_validator("cause_category")
    @classmethod
    def _cat(cls, value: str) -> str:
        return _category(value)


class CauseUpdatePayload(BaseModel):
    """A cause's category or failure mode changed by a person, with the reason."""

    cause_category: str = Field(max_length=20)
    failure_mode_id: uuid.UUID | None = None
    reason: str = Field(max_length=TEXT_MAX)

    @field_validator("cause_category")
    @classmethod
    def _cat(cls, value: str) -> str:
        return _category(value)

    @field_validator("reason")
    @classmethod
    def _reason(cls, value: str) -> str:
        text = _clean(value)
        if len(text) < REASON_MIN:
            raise ValueError(f"Say why in at least {REASON_MIN} characters")
        return text


class WhyInput(BaseModel):
    """One why: its answer, the state of its link to the step before, and optionally the evidence it rests on."""

    text: str = Field(max_length=LABEL_MAX)
    state: str = Field(default="UNKNOWN", max_length=30)
    evidence_id: uuid.UUID | None = None

    @field_validator("text")
    @classmethod
    def _text(cls, value: str) -> str:
        text = _clean(value)
        if len(text) < 3:
            raise ValueError("Write each why in at least 3 characters")
        return text

    @model_validator(mode="after")
    def _state(self):
        from backend.app.case_intelligence.rules import (
            EVIDENCE_REQUIRED_MESSAGE,
            LINK_STATE_CODES,
            state_needs_evidence,
        )

        self.state = _clean(self.state).upper()
        if self.state not in LINK_STATE_CODES:
            raise ValueError(f"Choose a link state: {', '.join(LINK_STATE_CODES)}")
        if state_needs_evidence(self.state) and self.evidence_id is None:
            raise ValueError(EVIDENCE_REQUIRED_MESSAGE)
        return self


class FiveWhysPayload(BaseModel):
    """A 5 Whys: the problem, then 2 to 7 whys."""

    problem: str = Field(max_length=LABEL_MAX)
    whys: list[WhyInput] = Field(max_length=20)

    @field_validator("problem")
    @classmethod
    def _problem(cls, value: str) -> str:
        text = _clean(value)
        if len(text) < 3:
            raise ValueError("Describe the problem in at least 3 characters")
        return text

    @field_validator("whys")
    @classmethod
    def _count(cls, value: list[WhyInput]) -> list[WhyInput]:
        if not WHYS_MIN <= len(value) <= WHYS_MAX:
            raise ValueError(f"A 5 Whys has {WHYS_MIN} to {WHYS_MAX} whys")
        return value


class WhyLinkPayload(BaseModel):
    """The hypothesis the last why is (never a root cause)."""

    hypothesis_id: uuid.UUID


def root_cause_problem(
    *, outcome: str, category: str | None, reason: str | None, ticked: list[uuid.UUID], methods_on: bool
) -> str | None:
    """Why the confirmed-cause fields of a signing cannot be accepted (RCA-D1, D4), or None."""
    if not methods_on:
        if category or ticked:
            return "The root-cause tools are switched off: sign without a cause category"
        return None
    if category is not None and category not in (*CAUSE_CATEGORIES, NOT_DETERMINED):
        return "Choose the cause category, or Not determined"
    if len(set(ticked)) != len(ticked):
        return "Tick each hypothesis once"
    if category is None and ticked:
        return "Choose the category of the causes you ticked"
    if category is None and outcome in ACCEPTING_OUTCOMES:
        return "Accepting the conclusion: choose the cause category, or Not determined with a reason"
    if category == NOT_DETERMINED:
        if ticked:
            return "Not determined: untick the hypotheses, or choose their category"
        if len(_clean(reason)) < REASON_MIN:
            return f"Not determined: say in at least {REASON_MIN} characters why the cause cannot be determined"
    if len(_clean(reason)) > TEXT_MAX:
        return f"Keep the reason under {TEXT_MAX} characters"
    return None
