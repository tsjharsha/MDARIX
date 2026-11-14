"""Labels on AI results, and the notice shown when MDARIX rules answered because AI could not.

* ``AIEpistemicLabel``: every AI result (analysis, hypotheses, challenges, unknowns, failure chains, counterfactual,
  brief) says what it is - an AI interpretation that a person reviews before relying on it. The label sits on the
  API response models only, never on the result objects themselves: those are also the stored AI output and the
  context sent to models, which must not change.
* ``AIFallbackNotice`` / ``fallback_notice``: when AI is switched off for the organization, its monthly allowance is
  used up or no AI service is available, a result produced by rules says so in plain words with a stable
  ``reason_code`` (AI_DISABLED, BUDGET_EXHAUSTED, PROVIDER_UNAVAILABLE) and the manual way to do the work.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

AI_DISABLED, BUDGET_EXHAUSTED, PROVIDER_UNAVAILABLE = "AI_DISABLED", "BUDGET_EXHAUSTED", "PROVIDER_UNAVAILABLE"
AI_INTERPRETATION_NOTE = "AI interpretation — review before relying on it"


class AIEpistemicLabel(BaseModel):
    """What an AI result is: the model's (or the AI workflow's) interpretation, for a person to review."""

    origin: str = "AI"
    type: str = "AI_INTERPRETATION"
    human_review_required: bool = True
    note: str = AI_INTERPRETATION_NOTE


def ai_label_field() -> Any:
    """A response field holding the default AI label (stored and older responses validate unchanged)."""
    return Field(default_factory=AIEpistemicLabel)


class AIFallbackNotice(BaseModel):
    """Why AI did not contribute to a result, and what a person can do by hand instead."""

    reason_code: str
    refusal_code: str | None = None
    message: str
    manual_alternative: str


# The manual way to do each AI action (the Intelligence screens of a case).
MANUAL_ALTERNATIVES = {
    "analysis": "Record observations by hand in Intelligence.",
    "hypotheses": "Add hypotheses by hand in Intelligence.",
    "challenges": "Challenge hypotheses by hand: link contradicting evidence to them in Intelligence.",
    "unknowns": "Record unknowns by hand in Intelligence.",
    "failure_chain": "Build the failure chain by hand in Intelligence.",
    "brief": "The brief is assembled from the case records; add your own conclusions by hand.",
    "decision_advisory": "Record the decision with your own rationale; the readiness checks above still apply.",
    "ask": "Ask MDARIX still answers from your records.",
}

_REASON_SENTENCES = {
    AI_DISABLED: "AI processing is switched off for your organization, so MDARIX rules produced this result.",
    BUDGET_EXHAUSTED: "Your organization's monthly AI allowance is used up, so MDARIX rules produced this result.",
    PROVIDER_UNAVAILABLE: "No AI service is available right now, so MDARIX rules produced this result.",
}


def reason_code_for(refusal_code: str | None) -> str | None:
    """The screen's reason (AI_DISABLED, BUDGET_EXHAUSTED, PROVIDER_UNAVAILABLE) for a genai refusal code."""
    if not refusal_code:
        return None
    code = str(refusal_code).split(":", 1)[0].strip().upper()
    if code in (
        "GENAI_DISABLED_FOR_ORGANIZATION",
        "GENAI_OFF_FOR_FREE_TRIAL",
        "GENAI_FEATURE_OFF_FOR_ORGANIZATION",
        "GENAI_FEATURE_OFF_ON_PLATFORM",
        "GENAI_FEATURE_NOT_OFFERED",
        "GENAI_USER_AI_INACTIVE",
        "GENAI_TRIAL_SAMPLE_ONLY",
    ):
        return AI_DISABLED
    if code == "GENAI_MONTHLY_BUDGET_REACHED":
        return BUDGET_EXHAUSTED
    if code == "GENAI_INSUFFICIENT_EVIDENCE":
        return None  # nothing went wrong with AI: the records do not answer the question
    if code.startswith("GENAI_"):
        return PROVIDER_UNAVAILABLE
    return None


def notice(feature: str, refusal_code: str | None) -> AIFallbackNotice | None:
    """The notice for ``feature`` when ``refusal_code`` (a genai code) means AI could not be used, else None."""
    reason = reason_code_for(refusal_code)
    if reason is None:
        return None
    manual = MANUAL_ALTERNATIVES.get(feature, "Do this step by hand in Intelligence.")
    return AIFallbackNotice(
        reason_code=reason,
        refusal_code=str(refusal_code).split(":", 1)[0].strip().upper(),
        message=f"{_REASON_SENTENCES[reason]} {manual}",
        manual_alternative=manual,
    )


def _advisory_code(advisory: Any) -> str | None:
    """The refusal code of a live advisory (genai.grounding.advisory), or None when it answered or was not needed."""
    if not isinstance(advisory, dict):
        return None
    if advisory.get("status") == "REFUSED":
        return str(advisory.get("code") or "GENAI_UNAVAILABLE")
    output = advisory.get("provider_output")
    if isinstance(output, dict) and output.get("status") == "PROVIDER_NOT_CONFIGURED":
        return "GENAI_PROVIDER_NOT_CONFIGURED"
    return None


def fallback_notice(feature: str, provenance: Any, *, author_key: str = "author") -> AIFallbackNotice | None:
    """The notice for a rule-produced result, read from its provenance (never raises).

    The model attempt's own error comes first (``model_attempt.error``, a genai refusal), then a provider that is not
    configured (``fallback_reason: MODEL_NOT_CONFIGURED``), then the live advisory's refusal. A result the language
    model wrote has no notice."""
    try:
        if not isinstance(provenance, dict) or provenance.get(author_key) == "LANGUAGE_MODEL":
            return None
        attempt = provenance.get("model_attempt")
        error = attempt.get("error") if isinstance(attempt, dict) else None
        for candidate in (
            error if isinstance(error, str) and error.upper().startswith("GENAI_") else None,
            "GENAI_PROVIDER_NOT_CONFIGURED" if provenance.get("fallback_reason") == "MODEL_NOT_CONFIGURED" else None,
            _advisory_code(provenance.get("live_provider_advisory")),
        ):
            found = notice(feature, candidate)
            if found is not None:
                return found
    except Exception:  # a label must never break a response
        return None
    return None
