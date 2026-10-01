"""The language model drafts the investigation brief from the checked analysis, hypotheses and challenges.

It writes for a quality leader: a headline, what we know, what conflicts, what is missing, the leading hypotheses and
next steps. Every statement that makes a claim must cite evidence of this investigation; MDARIX rules drop uncited or
invented citations and any causal, certainty or regulatory-decision wording. The brief is only drafted when the
analysis was model-written; otherwise the rule-assembled brief is used unchanged.
"""

from __future__ import annotations

from typing import Any

from genai.provider import GenAIProvider, GenAIUnavailable
from investigator.model_provider import (
    MAX_STATEMENT,
    ModelAnalysisUnavailable,
    asserts_causality_or_decision,
    parse_json_reply,
)

PROMPT_TEMPLATE_VERSION = "R1-MVP-P3-Brief-v1"
# section: (must cite evidence, at most this many items)
SECTIONS = {
    "what_we_know": (True, 5),
    "what_conflicts": (True, 3),
    "what_is_missing": (False, 4),
    "leading_hypotheses": (True, 3),
    "next_steps": (False, 3),
}

SYSTEM = """You are MDARIX, drafting a one-page investigation brief for a medical-device quality leader.
Use only the checked analysis, hypotheses and challenges given. Short, plain sentences; no jargon.
- headline: one sentence, at most 25 words, saying where the investigation stands.
- what_we_know / what_conflicts / leading_hypotheses: each item cites evidence IDs copied exactly from the input.
- what_is_missing and next_steps: concrete records or checks; they may cite nothing.
Never state a root cause or that something caused something as fact; hypotheses use "may".
No regulatory decisions (reporting, recall, release, closure) - those belong to people.

Reply with JSON only:
{"headline": "...",
 "what_we_know": [{"statement": "...", "evidence": ["EV-..."]}],
 "what_conflicts": [{"statement": "...", "evidence": ["EV-..."]}],
 "what_is_missing": [{"statement": "...", "evidence": []}],
 "leading_hypotheses": [{"statement": "...", "evidence": ["EV-..."]}],
 "next_steps": [{"statement": "...", "evidence": []}]}"""


def check_brief(parsed: dict[str, Any], known: set[str]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    sections: dict[str, list[dict[str, Any]]] = {}
    dropped: list[dict[str, Any]] = []
    for name, (needs_citation, limit) in SECTIONS.items():
        items: list[dict[str, Any]] = []
        raw_items = parsed.get(name)
        for raw in raw_items if isinstance(raw_items, list) else []:
            if not isinstance(raw, dict):
                continue
            statement = str(raw.get("statement") or "").strip()
            cited = list(dict.fromkeys(str(ref).strip() for ref in (raw.get("evidence") or []) if str(ref).strip()))
            reason = None
            if not statement or len(statement) > MAX_STATEMENT:
                reason = "EMPTY_OR_TOO_LONG"
            elif asserts_causality_or_decision(statement):
                reason = "CAUSAL_OR_DECISION_CLAIM"
            elif any(ref not in known for ref in cited):
                reason = "CITES_UNKNOWN_EVIDENCE"
            elif needs_citation and not cited:
                reason = "NO_CITATION"
            elif len(items) >= limit:
                reason = "OVER_LIMIT"
            if reason:
                dropped.append({"section": name, "statement": statement[:MAX_STATEMENT], "reason": reason})
                continue
            items.append({"statement": statement, "evidence": cited})
        sections[name] = items
    headline = parsed.get("headline")
    headline = headline.strip()[:MAX_STATEMENT] if isinstance(headline, str) and headline.strip() else None
    if headline and asserts_causality_or_decision(headline):
        dropped.append({"section": "headline", "statement": headline, "reason": "CAUSAL_OR_DECISION_CLAIM"})
        headline = None
    return {"headline": headline, "sections": sections}, dropped


class ModelBriefWriter:
    def __init__(self, provider: GenAIProvider | None = None) -> None:
        self.provider = provider or GenAIProvider()

    def draft(self, analysis, hypothesis_set, challenge_set, known_evidence: set[str]) -> dict[str, Any]:
        if analysis is None or analysis.analysis_author != "LANGUAGE_MODEL":
            raise ModelAnalysisUnavailable("ANALYSIS_NOT_MODEL_WRITTEN")
        if not self.provider.health().get("configured"):
            raise ModelAnalysisUnavailable("MODEL_NOT_CONFIGURED")

        def cited(items):
            return [
                {"statement": item.statement, "evidence": [r.evidence_identifier for r in item.source_references]}
                for item in items
            ]

        context: dict[str, Any] = {
            "summary": analysis.summary,
            "observations": cited(analysis.observations),
            "contradictions": cited(analysis.contradictions),
            "missing_information": [item.statement for item in analysis.missing_information],
            "questions": [item.statement for item in analysis.questions_to_investigate],
        }
        if hypothesis_set is not None:
            context["hypotheses"] = [
                {
                    "statement": item.statement,
                    "supporting": [r.source_references[0].evidence_identifier for r in item.supporting_evidence],
                    "contradicting": [r.source_references[0].evidence_identifier for r in item.contradicting_evidence],
                }
                for item in hypothesis_set.hypotheses
            ]
        if challenge_set is not None:
            context["challenges"] = [
                {"type": item.challenge_type, "statement": item.statement, "severity": item.severity}
                for item in challenge_set.challenges
            ]
        try:
            result = self.provider.complete(
                "Draft the investigation brief.", context, system=SYSTEM, json_output=True, max_output_tokens=3000
            )
        except GenAIUnavailable as exc:
            raise ModelAnalysisUnavailable("MODEL_CALL_FAILED", {"error": str(exc)}) from exc
        brief, dropped = check_brief(parse_json_reply(result.output.get("answer")), known_evidence)
        if not brief["headline"] or not brief["sections"]["what_we_know"]:
            raise ModelAnalysisUnavailable("MODEL_OUTPUT_FAILED_CHECKS", {"dropped": dropped})
        return {
            "author": "LANGUAGE_MODEL",
            **brief,
            "checks_dropped": dropped,
            "model": {
                "provider": result.provider,
                "model": result.model,
                "model_version": result.model_version,
                "prompt_template_version": PROMPT_TEMPLATE_VERSION,
                "input_tokens": result.input_tokens,
                "output_tokens": result.output_tokens,
                "latency_ms": result.latency_ms,
            },
        }
