"""The evidence extractor's AI execution record names who really wrote the result: the model's own provider, model
and version, or RULES for the rule-based fallback (whose observations are not AI observations)."""

import json
import uuid
from types import SimpleNamespace

import ai.extractor as extractor_module
from ai.extractor import RULES_PROVENANCE, AIEvidenceExtractor
from genai.provider import GenAIProvider, GenAIResult, GenAIUnavailable

TEXT = "Validation test VT-204 passed after 1000 h.\n\nShutdown complaints increased after Rev D."


class _Model(GenAIProvider):
    def __init__(self, answer=None, error=None):
        super().__init__(max_input_tokens=4000)
        self.answer, self.error = answer, error

    def health(self):
        return {"configured": True}

    def complete(self, prompt, context=None, **kwargs):
        if self.error:
            raise self.error
        return GenAIResult("anthropic", "claude-sonnet-5-5", "2026-09", {"answer": self.answer}, 10, 5, 0.0, 12)


def _recorded(monkeypatch, model):
    calls = []
    monkeypatch.setattr(
        extractor_module,
        "record_ai_execution",
        lambda **kwargs: calls.append(kwargs) or SimpleNamespace(id=uuid.uuid4()),
    )
    result, _ = AIEvidenceExtractor(provider_client=model).extract_evidence(
        db=None, tenant_id=uuid.uuid4(), evidence_id=uuid.uuid4(), evidence_title="Report", evidence_content=TEXT
    )
    return result, calls[0]


def test_a_model_extraction_records_the_real_provider_model_and_version(monkeypatch):
    answer = json.dumps(
        {
            "observations": [
                {
                    "statement": "Validation test VT-204 passed after 1000 h.",
                    "observation_type": "EXPLICIT_SOURCE_STATEMENT",
                    "source_anchor": {"paragraph_index": 0, "excerpt": "Validation test VT-204 passed after 1000 h."},
                }
            ],
            "extraction_status": "COMPLETED",
            # A model cannot claim to be the rules: the extractor sets the method itself.
            "extraction_method": "DETERMINISTIC",
        }
    )
    result, record = _recorded(monkeypatch, _Model(answer=answer))
    assert (record["provider"], record["model_name"], record["model_version"]) == (
        "anthropic",
        "claude-sonnet-5-5",
        "2026-09",
    )
    assert result.extraction_method == "GENAI"
    assert result.model_provenance == {
        "provider": "anthropic",
        "model": "claude-sonnet-5-5",
        "model_version": "2026-09",
    }


def test_the_rule_fallback_is_recorded_as_rules_not_as_ai(monkeypatch):
    result, record = _recorded(monkeypatch, _Model(error=GenAIUnavailable("GENAI_DISABLED_FOR_ORGANIZATION")))
    assert record["provider"] == "RULES" and record["model_name"] == RULES_PROVENANCE["model"]
    assert result.extraction_method == "DETERMINISTIC" and result.model_provenance == RULES_PROVENANCE
    assert result.observations
    assert {obs.observation_type for obs in result.observations} <= {
        "DETERMINISTIC_DERIVATION",
        "EXPLICIT_SOURCE_STATEMENT",
    }


def test_controlled_mode_uses_the_rules(monkeypatch):
    monkeypatch.setenv("MDARIX_GENAI_PROVIDER", "controlled")
    result, record = _recorded(monkeypatch, GenAIProvider())
    assert record["provider"] == "RULES" and result.extraction_method == "DETERMINISTIC"
