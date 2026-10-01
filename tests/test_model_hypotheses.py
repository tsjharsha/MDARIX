"""Competing hypotheses written by the language model, checked by MDARIX rules, with the templates as fallback."""

import json

from backend.app.db.models.foundation import Hypothesis as HypothesisRow, Unknown
from backend.app.db.session import SessionLocal
from genai.provider import GenAIResult
from hypothesis_engine.model_engine import ModelHypothesisEngine
from hypothesis_engine.schemas import HypothesisSetRequest
from hypothesis_engine.service import CompetingHypothesisService
from investigator.model_provider import ModelInvestigatorProvider
from investigator.service import EvidenceGroundedInvestigatorService
from tests.test_day11_ai_investigator import context
from tests.test_model_investigator import FakeModel, _good_reply


def _hypotheses_reply(ids, tag="A"):
    first, second = ids[0], ids[1]
    return json.dumps(
        {
            "hypotheses": [
                {
                    "statement": f"Hypothesis {tag}1: the supplier change may be associated with the shutdowns.",
                    "scope": "Supplier Change!",
                    "supporting": [{"evidence": first, "why": "The change came first."}],
                    "contradicting": [{"evidence": second, "why": "Shutdowns existed before."}],
                    "unknowns": [f"Unknown {tag}: lot-level rates."],
                    "tests": ["Compare shutdown rates for lots with and without the new process."],
                    "alternatives": ["Firmware behaviour may explain the same pattern."],
                },
                {
                    "statement": f"Hypothesis {tag}2: lot variation may explain part of the pattern.",
                    "scope": "lot_variation",
                    "supporting": [
                        {"evidence": second, "why": "Two lots lack traceability."},
                        {"evidence": "EV-INVENTED-1", "why": "Made up."},
                    ],
                    "contradicting": [],
                    "unknowns": [],
                    "tests": ["Complete the genealogy for the untraced lots."],
                    "alternatives": [],
                },
                {"statement": "Hypothesis: the capacitor is the root cause.", "supporting": [{"evidence": first}]},
                {"statement": "Hypothesis: nothing supports this.", "supporting": []},
            ]
        }
    )


class TwoStepModel(FakeModel):
    """Writes the analysis, then the hypotheses, from what it was given."""

    def __init__(self, tag="A", hypotheses=None):
        super().__init__(_good_reply)
        self.tag, self.hypotheses = tag, hypotheses

    def complete(self, prompt, context=None, *, system=None, json_output=False, max_output_tokens=None):
        if "competing explanations" not in (system or ""):
            return super().complete(
                prompt, context, system=system, json_output=json_output, max_output_tokens=max_output_tokens
            )
        reply = self.hypotheses if self.hypotheses is not None else _hypotheses_reply(context["evidence_ids"], self.tag)
        return GenAIResult("groq", "openai/gpt-oss-120b", "test", {"answer": reply}, 100, 50, 0.0, 10)


def _generate(model, persist=False):
    tenant_id, investigation_id = context()
    investigator = EvidenceGroundedInvestigatorService(model_provider=ModelInvestigatorProvider(model))
    service = CompetingHypothesisService(investigator_service=investigator, model_engine=ModelHypothesisEngine(model))
    db = SessionLocal()
    try:
        request = HypothesisSetRequest(tenant_id=tenant_id, investigation_id=investigation_id, persist=persist)
        return service.generate(db, request).hypothesis_set
    finally:
        db.close()


def test_the_model_writes_competing_hypotheses_and_the_rules_check_them():
    result = _generate(TwoStepModel())
    assert result.provenance["author"] == "LANGUAGE_MODEL"
    assert [h.statement.split(":")[0] for h in result.hypotheses] == ["Hypothesis A1", "Hypothesis A2"]
    first, second = result.hypotheses
    assert first.status == "MIXED_EVIDENCE" and first.contradicting_evidence  # contradiction kept visible
    assert second.status == "UNDER_INVESTIGATION" and len(second.supporting_evidence) == 1
    assert first.scope == "supplier_change"
    reasons = sorted(item["reason"] for item in result.provenance["checks_dropped"])
    assert reasons == ["CITES_UNKNOWN_EVIDENCE", "NO_VALID_SUPPORTING_EVIDENCE", "STATEMENT_NOT_ALLOWED"]
    for hypothesis in result.hypotheses:
        for relation in hypothesis.supporting_evidence + hypothesis.contradicting_evidence:
            assert all(ref.evidence_id and ref.source_anchor for ref in relation.source_references)
    assert result.rejected_hypotheses == [] and result.status == "MIXED_EVIDENCE"


def test_templates_take_over_when_the_model_cannot_give_two_usable_hypotheses():
    only_one = json.dumps({"hypotheses": [{"statement": "Hypothesis: one idea.", "supporting": []}]})
    result = _generate(TwoStepModel(hypotheses=only_one))
    assert result.provenance["author"] == "RULES"
    assert result.provenance["fallback_reason"] == "MODEL_OUTPUT_FAILED_CHECKS"
    assert result.hypotheses  # the template hypotheses


def test_without_a_model_the_templates_write_the_hypotheses():
    result = _generate(None)
    assert result.provenance["author"] == "RULES"
    assert result.provenance["fallback_reason"] == "ANALYSIS_NOT_MODEL_WRITTEN"


def test_a_new_model_set_retires_the_previous_unreviewed_one():
    tenant_id, investigation_id = context()
    _generate(TwoStepModel(tag="OLD"), persist=True)
    _generate(TwoStepModel(tag="NEW"), persist=True)
    db = SessionLocal()
    try:
        rows = {
            row.statement.split(":")[0]: row
            for row in db.query(HypothesisRow).filter_by(tenant_id=tenant_id, investigation_id=investigation_id)
            if row.statement.startswith(("Hypothesis OLD", "Hypothesis NEW"))
        }
        assert rows["Hypothesis OLD1"].status == "superseded" and rows["Hypothesis OLD1"].origin == "ai"
        assert rows["Hypothesis NEW1"].status == "mixed_evidence"
        old_unknown = db.query(Unknown).filter_by(hypothesis_id=rows["Hypothesis OLD1"].id).first()
        assert old_unknown is not None and old_unknown.status == "superseded"
    finally:
        for row in (
            db.query(HypothesisRow)
            .filter_by(tenant_id=tenant_id, investigation_id=investigation_id, origin="ai")
            .filter(HypothesisRow.statement.like("Hypothesis %"))
        ):
            from backend.app.db.models.foundation import HypothesisEvidence

            db.query(HypothesisEvidence).filter_by(hypothesis_id=row.id).delete()
            db.query(Unknown).filter_by(hypothesis_id=row.id).delete()
            db.delete(row)
        db.commit()
        db.close()
