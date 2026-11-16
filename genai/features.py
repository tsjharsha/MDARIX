"""The AI features: what each is for, its risk level, and the switches that let it call a model.

Every model request names its feature (``GenAIProvider.complete(feature=...)``). A request without a known feature is
refused before any network code (``GENAI_FEATURE_UNKNOWN``), so new code cannot pass the switches by accident.

Risk levels (AI-R spec section 3): **LOW** = advisory text a person reads; **MEDIUM** = a proposal a person may turn
into a record. **HIGH** (AI decides) is not allowed: declaring a feature HIGH fails this module's import.

A feature may call a model only when every level allows it (all off by default):

* platform: ``MDARIX_AI_FEATURES`` lists it (comma-separated, default empty), read on every call;
* offered: ``decision_advisory`` (owner decision AI-D5) and ``regulatory_drafting`` (the regulatory copilot, owner
  decision of 14 Nov 2026: not offered until AI qualification) are not offered whatever the switches say;
* organisation: ``tenants.ai_processing_allowed`` and ``tenants.ai_features[feature]`` (``genai/governance.py``).
"""

from __future__ import annotations

import os
from dataclasses import dataclass

ALLOWED_RISKS = ("LOW", "MEDIUM")
FEATURES_SETTING = "MDARIX_AI_FEATURES"


@dataclass(frozen=True)
class Feature:
    key: str
    label: str
    intended_use: str
    risk: str
    never: str
    prompt_version: str
    offered: bool = True

    def public(self) -> dict:
        return {
            "key": self.key,
            "label": self.label,
            "intended_use": self.intended_use,
            "risk": self.risk,
            "never": self.never,
            "offered": self.offered,
        }


_DECLARED = (
    Feature(
        "ask",
        "Ask MDARIX",
        "Answer a question from the organisation's own records, with citations.",
        "LOW",
        "Answer without a cited record, or guess when the records are silent.",
        "ask-structured-1",
    ),
    Feature(
        "summaries",
        "Summaries",
        "Summarise a signal's complaints; explain why a second-look record may be a complaint.",
        "LOW",
        "Say a record is or is not a complaint, or reportable.",
        "summaries-1",
    ),
    Feature(
        "case_analysis",
        "Case analysis",
        "Propose an analysis, competing explanations and challenges for an investigation.",
        "MEDIUM",
        "State a root cause as fact, or rank explanations as decided.",
        "case-analysis-1",
    ),
    Feature(
        "drafting",
        "Drafting",
        "Draft the investigation brief from reviewed analysis.",
        "MEDIUM",
        "Enter a Decision Brief or a report unreviewed.",
        "drafting-1",
    ),
    Feature(
        "evidence_extraction",
        "Evidence extraction",
        "Propose observations from an evidence document, each with its source anchor.",
        "MEDIUM",
        "Become evidence before a person accepts it.",
        "evidence-extraction-1",
    ),
    Feature(
        "code_suggestions",
        "Code suggestions",
        "Propose IMDRF codes from the complaint text, from the loaded IMDRF release only.",
        "MEDIUM",
        "Be confirmed by 'Confirm all codes'.",
        "code-suggestions-1",
    ),
    Feature(
        "decision_advisory",
        "Decision advisory",
        "Advisory text beside a Decision Center or reporting decision.",
        "MEDIUM",
        "Be offered at all until the owner says so (AI-D5).",
        "decision-advisory-1",
        offered=False,
    ),
    Feature(
        "regulatory_drafting",
        "Regulatory drafting",
        "Draft regulatory document sections (such as an IFU) from a case, for a person to review.",
        "MEDIUM",
        "Be offered at all until AI is qualified (owner decision, 14 Nov 2026).",
        "regulatory-drafting-1",
        offered=False,
    ),
)


def _validate(features) -> dict[str, Feature]:
    """The declared features by key; refuses a HIGH (or unknown) risk and a duplicate key."""
    found: dict[str, Feature] = {}
    for item in features:
        if item.risk not in ALLOWED_RISKS:
            raise ValueError(f"AI feature {item.key} declares risk {item.risk}: AI may not decide (only LOW or MEDIUM)")
        if item.key in found:
            raise ValueError(f"AI feature {item.key} is declared twice")
        found[item.key] = item
    return found


FEATURES: dict[str, Feature] = _validate(_DECLARED)


def platform_features() -> frozenset[str]:
    """The features this server lets call a model (``MDARIX_AI_FEATURES``), read on every call."""
    return frozenset(
        name.strip().lower() for name in os.getenv(FEATURES_SETTING, "").split(",") if name.strip().lower() in FEATURES
    )


def unknown_platform_features() -> list[str]:
    """Names in ``MDARIX_AI_FEATURES`` that are not features (reported by the configuration check)."""
    return sorted(
        {name.strip().lower() for name in os.getenv(FEATURES_SETTING, "").split(",") if name.strip()} - set(FEATURES)
    )


def known(feature: str | None) -> Feature:
    """The feature, or ``GENAI_FEATURE_UNKNOWN`` (a missing or misspelt feature never reaches a model)."""
    from genai.provider import GenAIUnavailable

    item = FEATURES.get(str(feature or "").strip().lower())
    if item is None:
        raise GenAIUnavailable(f"GENAI_FEATURE_UNKNOWN: {feature!r}")
    return item


def check_platform(feature: Feature) -> None:
    """Refuse a feature that is not offered, or that this server does not list in ``MDARIX_AI_FEATURES``."""
    from genai.provider import GenAIUnavailable

    if not feature.offered:
        raise GenAIUnavailable(f"GENAI_FEATURE_NOT_OFFERED: {feature.key}")
    if feature.key not in platform_features():
        raise GenAIUnavailable(f"GENAI_FEATURE_OFF_ON_PLATFORM: {feature.key}")
