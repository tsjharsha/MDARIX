"""Challenges and the investigation brief written by the language model, checked by MDARIX rules."""

import json
from datetime import datetime, timezone

import pytest

from backend.app.db.models.foundation import Hypothesis as HypothesisRow, HypothesisEvidence, Unknown
from backend.app.db.session import SessionLocal
from briefs.model_writer import ModelBriefWriter, check_brief
from briefs.schemas import BriefCreateRequest
from briefs.service import BriefService
from challenger.model_engine import ModelChallenger
from challenger.schemas import ChallengeRequest
from challenger.service import ChallengerService
from genai.provider import GenAIResult
from hypothesis_engine.model_engine import ModelHypothesisEngine
from hypothesis_engine.service import CompetingHypothesisService
from investigator.model_provider import ModelInvestigatorProvider
from investigator.service import EvidenceGroundedInvestigatorService
from tests.test_day11_ai_investigator import context
from tests.test_model_hypotheses import TwoStepModel


@pytest.fixture(autouse=True)
def _ai_features_on_platform(monkeypatch):
    # These tests exercise the provider itself: every offered feature is on the platform list (genai/features.py).
    monkeypatch.setenv(
        "MDARIX_AI_FEATURES", "ask,summaries,case_analysis,drafting,evidence_extraction,code_suggestions"
    )


def _challenges_reply(context):
    first = context["hypotheses"][0]
    evidence = first["supporting"][0]["evidence"]
    return json.dumps(
        {
            "challenges": [
                {
                    "hypothesis": "H1",
                    "type": "INSUFFICIENT_COMPARATIVE_EVIDENCE",
                    "statement": "No side-by-side test compares the old and new process.",
                    "why": "Without it the association cannot be separated from lot effects.",
                    "evidence": [evidence],
                    "missing": ["Comparative bench test of both processes."],
                    "severity": "HIGH",
                },
                {"hypothesis": "H9", "type": "CAUSAL_LEAP", "statement": "Unknown hypothesis.", "missing": ["x"]},
                {"hypothesis": "H1", "type": "MADE_UP_TYPE", "statement": "Bad type.", "missing": ["x"]},
                {
                    "hypothesis": "H2",
                    "type": "CAUSAL_LEAP",
                    "statement": "The lots caused the shutdowns.",
                    "missing": ["x"],
                },
                {
                    "hypothesis": "H2",
                    "type": "TRACEABILITY_GAP",
                    "statement": "Cites nothing.",
                    "evidence": ["EV-NONE"],
                },
            ]
        }
    )


def _brief_reply(context):
    evidence = context["observations"][0]["evidence"][0]
    return json.dumps(
        {
            "headline": "The supplier change is a lead, not a conclusion; lot data is missing.",
            "what_we_know": [
                {"statement": "The process change came before the new component.", "evidence": [evidence]},
                {"statement": "An invented record agrees.", "evidence": ["EV-INVENTED"]},
            ],
            "what_conflicts": [{"statement": "Validation passed despite complaints.", "evidence": [evidence]}],
            "what_is_missing": [{"statement": "Lot-level shutdown rates.", "evidence": []}],
            "leading_hypotheses": [
                {"statement": "The supplier change may be associated with the shutdowns.", "evidence": [evidence]},
                {"statement": "The capacitor is the root cause.", "evidence": [evidence]},
            ],
            "next_steps": [{"statement": "Request the lot genealogy for the untraced lots.", "evidence": []}],
        }
    )


class FullModel(TwoStepModel):
    """Writes analysis, hypotheses, challenges and the brief from what it was given."""

    def complete(
        self,
        prompt,
        context=None,
        *,
        system=None,
        json_output=False,
        response_schema=None,
        max_output_tokens=None,
        **_switches,
    ):
        if "sceptical reviewer" in (system or ""):
            reply = _challenges_reply(context)
        elif "one-page investigation brief" in (system or ""):
            reply = _brief_reply(context)
        else:
            return super().complete(
                prompt,
                context,
                system=system,
                json_output=json_output,
                max_output_tokens=max_output_tokens,
                feature="ask",
            )
        return GenAIResult("groq", "openai/gpt-oss-120b", "test", {"answer": reply}, 100, 50, 0.0, 10)


def _services(model):
    investigator = EvidenceGroundedInvestigatorService(model_provider=ModelInvestigatorProvider(model))
    hypotheses = CompetingHypothesisService(
        investigator_service=investigator, model_engine=ModelHypothesisEngine(model)
    )
    return ChallengerService(hypothesis_service=hypotheses, model_engine=ModelChallenger(model))


@pytest.fixture
def cleanup_ai_hypotheses():
    yield
    tenant_id, investigation_id = context()
    db = SessionLocal()
    try:
        for row in db.query(HypothesisRow).filter_by(
            tenant_id=tenant_id, investigation_id=investigation_id, origin="ai"
        ):
            db.query(HypothesisEvidence).filter_by(hypothesis_id=row.id).delete()
            db.query(Unknown).filter_by(hypothesis_id=row.id).delete()
            db.delete(row)
        db.commit()
    finally:
        db.close()


def _challenge(model, persist):
    tenant_id, investigation_id = context()
    db = SessionLocal()
    try:
        request = ChallengeRequest(tenant_id=tenant_id, investigation_id=investigation_id, persist=persist)
        return _services(model).generate(db, request).challenge_set
    finally:
        db.close()


@pytest.mark.db
def test_the_model_challenges_each_hypothesis_and_the_rules_check_them(cleanup_ai_hypotheses):
    result = _challenge(FullModel(), persist=False)
    assert result.provenance["author"] == "LANGUAGE_MODEL"
    assert len(result.challenges) == 1
    challenge = result.challenges[0]
    assert challenge.challenge_type == "INSUFFICIENT_COMPARATIVE_EVIDENCE" and challenge.severity == "HIGH"
    assert challenge.materiality == "MATERIAL" and challenge.status == "REQUIRES_MORE_EVIDENCE"
    assert challenge.evidence_references and challenge.evidence_references[0].source_anchor
    reasons = sorted(item["reason"] for item in result.provenance["checks_dropped"])
    assert reasons == [
        "CAUSAL_OR_DECISION_CLAIM",
        "CITES_UNKNOWN_EVIDENCE",
        "UNKNOWN_CHALLENGE_TYPE",
        "UNKNOWN_HYPOTHESIS",
    ]


@pytest.mark.db
def test_without_model_hypotheses_the_rule_challenges_are_used(cleanup_ai_hypotheses):
    result = _challenge(None, persist=False)
    assert result.provenance["author"] == "RULES" and result.challenges


@pytest.mark.db
def test_the_brief_is_drafted_from_the_checked_results(cleanup_ai_hypotheses):
    model = FullModel()
    _challenge(model, persist=True)  # persists the model analysis, hypotheses and challenges
    tenant_id, investigation_id = context()
    db = SessionLocal()
    try:
        brief = BriefService(model_writer=ModelBriefWriter(model)).generate(
            db, tenant_id, investigation_id, BriefCreateRequest()
        )
    finally:
        db.close()
    content = brief["content"]
    assert brief["provenance"]["drafted_by"] == "LANGUAGE_MODEL"
    assert content["executive_summary"]["text"].startswith("The supplier change is a lead")
    sections = content["ai_brief"]["sections"]
    assert [item["statement"] for item in sections["what_we_know"]] == [
        "The process change came before the new component."
    ]
    assert len(sections["leading_hypotheses"]) == 1
    reasons = sorted(item["reason"] for item in content["ai_brief"]["checks_dropped"])
    assert reasons == ["CAUSAL_OR_DECISION_CLAIM", "CITES_UNKNOWN_EVIDENCE"]
    assert content["ai_challenger_findings"] and content["supporting_evidence"]
    assert content["ai_advisory"]["status"] == "NOT_NEEDED"


@pytest.mark.db
def test_a_brief_is_drafted_only_from_an_analysis_of_the_same_point_in_time(cleanup_ai_hypotheses):
    tenant_id, investigation_id = context()
    as_of = datetime(2026, 2, 15, tzinfo=timezone.utc)
    model = FullModel()
    db = SessionLocal()
    try:
        request = ChallengeRequest(
            tenant_id=tenant_id, investigation_id=investigation_id, temporal_mode="event", as_of=as_of
        )
        _services(model).generate(db, request)  # analysis, hypotheses and challenges as of 15 Feb
        service = BriefService(model_writer=ModelBriefWriter(model))
        same = service.generate(db, tenant_id, investigation_id, BriefCreateRequest(temporal_mode="event", as_of=as_of))
        other = service.generate(
            db,
            tenant_id,
            investigation_id,
            BriefCreateRequest(temporal_mode="event", as_of=datetime(2026, 1, 1, tzinfo=timezone.utc)),
        )
    finally:
        db.close()
    assert same["provenance"]["drafted_by"] == "LANGUAGE_MODEL"
    assert other["provenance"]["drafted_by"] == "RULES"
    assert other["content"]["ai_brief"] == {"author": "RULES", "fallback_reason": "ANALYSIS_FOR_ANOTHER_TIME"}


@pytest.mark.db
def test_a_model_drafted_brief_is_saved_as_an_ai_result_with_its_trust_check(cleanup_ai_hypotheses):
    from trust_engine import auto

    model = FullModel()
    _challenge(model, persist=True)  # persists the model analysis, hypotheses and challenges
    tenant_id, investigation_id = context()
    db = SessionLocal()
    try:
        brief = BriefService(model_writer=ModelBriefWriter(model)).generate(
            db, tenant_id, investigation_id, BriefCreateRequest()
        )
        execution_id = brief["ai_execution_id"]
        assert execution_id and brief["content"]["ai_brief"]["ai_execution_id"] == str(execution_id)
        trust = auto.latest(db, tenant_id, execution_id)
        analysis = EvidenceGroundedInvestigatorService().latest(db, tenant_id, investigation_id)
        analysis_trust = auto.latest(db, tenant_id, analysis.analysis.ai_execution_id)
    finally:
        db.close()
    assert trust["author"] == auto.AI and trust["status"] in (auto.STATUS_PASS, auto.STATUS_LIMITED), trust
    assert "Written by groq openai/gpt-oss-120b." in [check["message"] for check in trust["checks"]]
    # The analysis the brief was drafted from was checked as it was saved, by the same policy.
    assert analysis_trust["author"] == auto.AI and analysis_trust["policy"] == auto.POLICY
    assert analysis_trust["status"] != auto.NOT_CHECKED


def test_brief_checks():
    brief, dropped = check_brief(
        {
            "headline": "Root cause is not established yet.",
            "what_we_know": [{"statement": "Fact.", "evidence": []}],
            "next_steps": "not a list",
        },
        {"EV-1"},
    )
    assert brief["headline"] == "Root cause is not established yet."
    assert brief["sections"]["what_we_know"] == [] and dropped[0]["reason"] == "NO_CITATION"
    assert brief["sections"]["next_steps"] == []


class RecordingModel(FullModel):
    """FullModel that keeps the feature and the records= list of every request."""

    def __init__(self):
        super().__init__()
        self.calls = []

    def complete(self, prompt, context=None, **kwargs):
        self.calls.append((kwargs.get("feature"), kwargs.get("records"), context))
        return super().complete(prompt, context, **kwargs)


@pytest.mark.db
def test_every_case_analysis_and_drafting_request_lists_the_records_it_carries(cleanup_ai_hypotheses):
    model = RecordingModel()
    _challenge(model, persist=True)
    tenant_id, investigation_id = context()
    db = SessionLocal()
    try:
        BriefService(model_writer=ModelBriefWriter(model)).generate(
            db, tenant_id, investigation_id, BriefCreateRequest()
        )
    finally:
        db.close()
    features = [feature for feature, _records, _context in model.calls]
    assert features.count("case_analysis") == 3 and features.count("drafting") == 1
    for _feature, records, _context in model.calls:
        assert records[0] == {"table": "investigations", "id": str(investigation_id)}
        assert any(entry["table"] == "evidence" and entry["evidence_id"] for entry in records[1:])
    _feature, records, sent = model.calls[0]
    listed = {entry["evidence_id"] for entry in records if entry["table"] == "evidence"}
    assert listed == {entry["id"] for entry in sent["evidence"]}
