"""Phase 4 (intelligence alignment), without a database: Ask's record-based composition, the model's structured reply
validated and its citations limited to the records it was given (fake provider), the labels on AI responses and the
notice when rules answered, and the AI status reasons."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

import pytest

from genai.epistemic import AIEpistemicLabel, fallback_notice, reason_code_for
from genai.provider import GenAIResult
from genai.structured_answer import (
    AI_NOTE_USED,
    CaseRecords,
    SourceRef,
    StructuredAnswer,
    compose,
    evidence_texts,
    merge,
    plain_text,
    read_model_reply,
    render_markdown,
    structured_ask_prompt,
)

pytestmark = pytest.mark.unit

NOW = datetime(2026, 10, 6, 12, 0, tzinfo=timezone.utc)
EV1 = SourceRef(business_id="EVD-000001", title="Service report", evidence_identifier="EV-ONE-1")
EV2 = SourceRef(business_id="EVD-000002", title="Batch record", evidence_identifier="EV-TWO-2")


def _records(**overrides) -> CaseRecords:
    values = {
        "investigation_scoped": True,
        "facts": [
            {"statement": "Alarm reproduced at 4 psi.", "epistemic_type": "FACT", "origin": "SYSTEM", "source": EV1},
            {
                "statement": "The supplier states the seal changed in May.",
                "epistemic_type": "SOURCE_ASSERTION",
                "origin": "HUMAN",
                "source": EV2,
            },
            # Not facts: they never appear among known facts.
            {"statement": "Seal wear may explain it.", "epistemic_type": "AI_INTERPRETATION", "source": EV1},
            {"statement": "Rate rose 3x.", "epistemic_type": "DERIVED_OBSERVATION", "source": EV1},
        ],
        "links": [
            {
                "relation": "support",
                "statement": 'Service report supports the hypothesis "Hypothesis: the seal may leak"',
                "origin": "HUMAN",
                "epistemic_type": "DERIVED_OBSERVATION",
                "source": EV1,
                "hypothesis_business_id": "HYP-000001",
            },
            {
                "relation": "contradict",
                "statement": "Batch record was reviewed as contradicting evidence for this case",
                "origin": "HUMAN",
                "source": EV2,
            },
        ],
        "unknowns": [
            {
                "statement": "Was lot 7 sterilized in the validated cycle?",
                "business_id": "UNK-000001",
                "status": "open",
                "origin": "HUMAN",
                "evidence_needed": "Sterilization record of lot 7",
            }
        ],
        "requests": [{"statement": "Seal drawings: revision B; revision C", "business_id": "REQ-000001"}],
        "limitations": ["Batch record: page 3 is missing", "Batch record: page 3 is missing"],
        "sources": [EV1],
        "unreviewed_evidence": 2,
        "hypotheses": 1,
        "case_evidence": 2,
    }
    values.update(overrides)
    return CaseRecords(**values)


# ------------------------------------------------------------------------------------------ record-based answer


def test_the_record_based_answer_keeps_facts_and_source_assertions_only_with_their_labels():
    answer = compose(_records())
    assert [(fact.statement, fact.epistemic_type, fact.origin) for fact in answer.known_facts] == [
        ("Alarm reproduced at 4 psi.", "FACT", "SYSTEM"),
        ("The supplier states the seal changed in May.", "SOURCE_ASSERTION", "HUMAN"),
    ]
    assert answer.known_facts[0].sources[0].business_id == "EVD-000001"
    assert answer.ai_used is False and answer.summary_origin == "SYSTEM"


def test_a_records_only_answer_that_found_nothing_says_plainly_what_it_searched():
    from genai.structured_answer import (
        NOTHING_FOUND_ALL,
        NOTHING_FOUND_CASE,
        SEARCH_FOUND_NOTHING,
        SEARCHED_ALL,
        SEARCHED_CASE,
        records_only_wording,
    )

    empty = compose(CaseRecords(investigation_scoped=False, limitations=[SEARCH_FOUND_NOTHING]))
    assert "0 records found" in empty.summary  # as composed; the records-only path rewords it
    answer = records_only_wording(empty, investigation_scoped=False)
    assert answer.summary == NOTHING_FOUND_ALL
    assert NOTHING_FOUND_ALL.startswith("No evidence record matches this question. Ask MDARIX searched the evidence")
    assert answer.limitations == [SEARCHED_ALL]
    assert "context-valid" not in " ".join(answer.limitations)
    assert "It does not count complaints" in SEARCHED_ALL and "Getting started › Automatic insights" in SEARCHED_ALL

    in_case = records_only_wording(
        compose(CaseRecords(investigation_scoped=True, limitations=[SEARCH_FOUND_NOTHING])), investigation_scoped=True
    )
    assert in_case.summary == NOTHING_FOUND_CASE == "No evidence record of this case matches this question."
    assert in_case.limitations[0] == SEARCHED_CASE

    # What was found stays as composed.
    found = compose(_records())
    assert records_only_wording(found, investigation_scoped=True) == found


def test_the_record_based_answer_sorts_links_unknowns_and_what_is_missing():
    answer = compose(_records())
    assert [item.hypothesis_business_id for item in answer.supporting_evidence] == ["HYP-000001"]
    assert answer.contradicting_evidence[0].sources == [EV2]
    assert [(item.business_id, item.status) for item in answer.unknowns] == [("UNK-000001", "open")]
    missing = {(item.statement, item.unknown_business_id, item.request_business_id) for item in answer.missing_evidence}
    assert missing == {
        ("Sterilization record of lot 7", "UNK-000001", None),
        ("Seal drawings: revision B; revision C", None, "REQ-000001"),
    }
    assert answer.limitations == ["Batch record: page 3 is missing"]
    # Sources: the search hits first, then the records the statements rest on, each once.
    assert [ref.business_id for ref in answer.sources] == ["EVD-000001", "EVD-000002"]
    assert any("open unknown" in step for step in answer.next_steps)
    assert any("not reviewed" in step for step in answer.next_steps)


def test_without_a_case_the_answer_is_the_search_and_its_facts():
    answer = compose(CaseRecords(investigation_scoped=False, sources=[EV1]))
    assert answer.unknowns == [] and answer.supporting_evidence == [] and answer.next_steps == []
    assert "1 record found" in answer.summary
    empty = compose(CaseRecords(investigation_scoped=False))
    assert empty.next_steps == ["Add or link evidence that answers the question."]
    assert "Add hypotheses by hand in Intelligence." in compose(_records(hypotheses=0)).next_steps


def test_text_fields_never_carry_raw_json():
    assert plain_text('{"lot": "7", "result": "pass"}') == "lot: 7; result: pass"
    assert plain_text({"a": 1, "b": [1, 2]}) == "a: 1; b: 1, 2"
    assert plain_text("  two\n  lines ") == "two lines"
    answer = compose(_records(facts=[{"statement": '{"lot": "7"}', "epistemic_type": "FACT", "source": EV1}]))
    assert answer.known_facts[0].statement == "lot: 7"


# ------------------------------------------------------------------------------------ the model's structured reply


class FakeProvider:
    """A configured model that returns a fixed reply (never contacts a service)."""

    def __init__(self, answer: str):
        self.answer = answer
        self.calls = []

    def complete(self, prompt, context=None, **kwargs):
        self.calls.append({"prompt": prompt, "context": context, **kwargs})
        return GenAIResult("test", "fake-model", "1", {"answer": self.answer, "limitations": []}, 10, 10, 0.0, 1)


REPLY = {
    "summary": "The seal changed in May and alarms rose afterwards [EV-ONE-1].",
    "known_facts": [
        {"statement": "Alarm reproduced at 4 psi", "sources": ["EV-ONE-1"]},
        {"statement": "Alarms rose after the change.", "sources": ["EV-ONE-1", "EV-NOT-GIVEN-9"]},
        {"statement": "Every unit is affected.", "sources": ["EV-NOT-GIVEN-9"]},
        {"statement": "Nobody cited this.", "sources": []},
    ],
    "supporting_evidence": [{"statement": "The timing is consistent with the change [EV-TWO-2].", "sources": []}],
    "contradicting_evidence": [{"statement": "The seal change caused the alarms.", "sources": ["EV-TWO-2"]}],
    "unknowns": ["Whether lot 7 was sterilized"],
    "missing_evidence": [{"statement": "Sterilization record of lot 7"}],
    "limitations": ["Only two records were given."],
    "next_steps": ["Ask the supplier for the seal drawings.", "Check lot 7.", "Compare lots.", "A fourth step."],
}
KNOWN = {"EV-ONE-1", "EV-TWO-2"}
TEXTS = {"EV-ONE-1": "Service visit. Alarm reproduced at 4 psi. Seal replaced.", "EV-TWO-2": "Batch record."}


def test_the_prompt_asks_for_the_sections_as_json():
    prompt = structured_ask_prompt("Did the seal change?")
    assert prompt.endswith("User question: Did the seal change?")
    for key in ("summary", "known_facts", "supporting_evidence", "contradicting_evidence", "missing_evidence"):
        assert f'"{key}"' in prompt


def test_a_valid_reply_keeps_only_citations_of_records_the_model_was_given():
    provider = FakeProvider(json.dumps(REPLY))
    result = provider.complete(structured_ask_prompt("Did the seal change?"), {})
    reading = read_model_reply(result.output["answer"], KNOWN, TEXTS)
    assert reading.status == "OK"
    facts = reading.sections["known_facts"]
    # The verbatim one is a source assertion; the paraphrase is an interpretation; its unknown citation is dropped.
    assert facts[0] == {
        "statement": "Alarm reproduced at 4 psi",
        "sources": ["EV-ONE-1"],
        "epistemic_type": "SOURCE_ASSERTION",
    }
    assert facts[1]["sources"] == ["EV-ONE-1"] and facts[1]["epistemic_type"] == "AI_INTERPRETATION"
    # A fact citing only a record it was not given, or citing none, is left out.
    assert len(facts) == 2
    # An inline citation counts and is taken out of the text.
    supporting = reading.sections["supporting_evidence"][0]
    assert supporting["statement"] == "The timing is consistent with the change." and supporting["sources"] == [
        "EV-TWO-2"
    ]
    # Causal wording is left out.
    assert reading.sections["contradicting_evidence"] == []
    assert reading.sections["unknowns"] == [
        {"statement": "Whether lot 7 was sterilized", "sources": [], "epistemic_type": "AI_INTERPRETATION"}
    ]
    assert reading.next_steps == ["Ask the supplier for the seal drawings.", "Check lot 7.", "Compare lots."]
    assert reading.dropped == 3
    assert reading.summary == "The seal changed in May and alarms rose afterwards."
    # The citation check still sees what the model cited, including what was dropped.
    assert "[EV-NOT-GIVEN-9]" in reading.check_text


def test_the_markdown_answer_is_rendered_from_the_checked_sections():
    reading = read_model_reply(json.dumps(REPLY), KNOWN, TEXTS)
    markdown = render_markdown(reading)
    for heading in ("## Answer", "## What the evidence shows", "## What is missing", "## Suggested next steps"):
        assert heading in markdown
    assert "Alarm reproduced at 4 psi [EV-ONE-1]" in markdown
    assert "EV-NOT-GIVEN-9" not in markdown and "{" not in markdown


def test_merge_labels_every_model_statement_ai_and_keeps_the_record_based_ones():
    reading = read_model_reply(json.dumps(REPLY), KNOWN, TEXTS)
    refs = {"EV-ONE-1": EV1, "EV-TWO-2": EV2}
    merged = merge(compose(_records()), reading, refs)
    assert merged.ai_used is True and merged.ai_note == AI_NOTE_USED and merged.summary_origin == "AI"
    origins = {(fact.statement, fact.origin) for fact in merged.known_facts}
    assert ("Alarm reproduced at 4 psi.", "SYSTEM") in origins and ("Alarms rose after the change.", "AI") in origins
    ai_supporting = [item for item in merged.supporting_evidence if item.origin == "AI"]
    assert ai_supporting and all(item.epistemic_type == "AI_INTERPRETATION" for item in ai_supporting)
    assert ai_supporting[0].sources == [EV2]
    assert any(item.origin == "AI" for item in merged.unknowns)
    assert any("left out" in text for text in merged.limitations)
    assert StructuredAnswer.model_validate(merged.model_dump(mode="json")) == merged


@pytest.mark.parametrize(
    "answer, status",
    [
        (None, "EMPTY"),
        ("   ", "EMPTY"),
        ("## Answer\nThe supplier changed its process [EV-ONE-1].", "NOT_JSON"),
        ('{"summary": "cut off', "INVALID"),
        ('["not", "an", "object"]', "INVALID"),
        (json.dumps({"known_facts": []}), "INVALID"),  # no summary
        (json.dumps({"summary": "S", "known_facts": "one fact"}), "INVALID"),
        (json.dumps({"summary": "S", "known_facts": [{"statement": '{"raw": "json"}'}]}), "INVALID"),
        ("```json\n" + json.dumps({"summary": "Fenced but fine."}) + "\n```", "OK"),
        ("Here you are: " + json.dumps({"summary": "Wrapped but fine."}), "OK"),
    ],
)
def test_reply_forms(answer, status):
    assert read_model_reply(answer, KNOWN, TEXTS).status == status


def test_a_summary_stating_a_cause_is_left_out():
    reading = read_model_reply(json.dumps({"summary": "The seal change caused the alarms."}), KNOWN)
    assert reading.status == "OK" and reading.summary is None and reading.dropped == 1
    assert "do not answer this directly" in render_markdown(reading)


def test_evidence_texts_cover_search_hits_and_case_records():
    texts = evidence_texts(
        {"evidence": [{"id": "EV-ONE-1", "text": "hit text"}]},
        {
            "evidence_context": [
                {
                    "evidence_identifier": "EV-ONE-1",
                    "chunks": [{"excerpt": "excerpt"}],
                    "observations": [{"statement": "observed"}],
                }
            ]
        },
    )
    assert texts == {"EV-ONE-1": "hit text\nexcerpt\nobserved"}


# ------------------------------------------------------------------------------------------- labels and notices


def _hypothesis_set(provenance: dict) -> dict:
    return {
        "hypothesis_set_id": str(uuid.uuid4()),
        "investigation_id": str(uuid.uuid4()),
        "source_analysis_id": str(uuid.uuid4()),
        "context_snapshot_id": "snapshot",
        "context_snapshot_version": "1",
        "status": "MIXED_EVIDENCE",
        "validation_summary": {},
        "guardrails": {},
        "provenance": provenance,
        "created_at": NOW.isoformat(),
    }


def test_stored_ai_responses_validate_unchanged_and_carry_the_ai_label():
    from hypothesis_engine.schemas import HypothesisSetResponse

    response = HypothesisSetResponse.model_validate(
        {"hypothesis_set": _hypothesis_set({"author": "LANGUAGE_MODEL"}), "persisted": True}
    )
    assert response.epistemic == AIEpistemicLabel()
    assert response.model_dump()["epistemic"] == {
        "origin": "AI",
        "type": "AI_INTERPRETATION",
        "human_review_required": True,
        "note": "AI interpretation — review before relying on it",
    }
    assert response.ai_notice is None
    # The set itself (stored AI output and model context) has no new field.
    assert (
        "epistemic" not in response.hypothesis_set.model_dump()
        and "ai_notice" not in response.hypothesis_set.model_dump()
    )


def test_a_rule_made_result_says_why_ai_did_not_help_and_what_to_do_by_hand():
    from challenger.schemas import ChallengeResponse
    from hypothesis_engine.schemas import HypothesisSetResponse

    switched_off = {
        "author": "RULES",
        "fallback_reason": "MODEL_CALL_FAILED",
        "model_attempt": {"error": "GENAI_DISABLED_FOR_ORGANIZATION"},
    }
    notice = HypothesisSetResponse.model_validate(
        {"hypothesis_set": _hypothesis_set(switched_off), "persisted": False}
    ).ai_notice
    assert notice.reason_code == "AI_DISABLED" and notice.refusal_code == "GENAI_DISABLED_FOR_ORGANIZATION"
    assert "Add hypotheses by hand in Intelligence" in notice.message

    challenge_set = {
        "investigation_id": str(uuid.uuid4()),
        "source_hypothesis_set_id": str(uuid.uuid4()),
        "context_snapshot_id": "snapshot",
        "context_snapshot_version": "1",
        "created_at": NOW.isoformat(),
        "provenance": {
            "author": "RULES",
            "fallback_reason": "HYPOTHESES_NOT_MODEL_WRITTEN",
            "live_provider_advisory": {"status": "REFUSED", "code": "GENAI_MONTHLY_BUDGET_REACHED"},
        },
    }
    challenge = ChallengeResponse.model_validate({"challenge_set": challenge_set, "persisted": False})
    assert challenge.ai_notice.reason_code == "BUDGET_EXHAUSTED"
    assert challenge.epistemic.type == "AI_INTERPRETATION"


@pytest.mark.parametrize(
    "provenance, expected",
    [
        ({"author": "LANGUAGE_MODEL", "live_provider_advisory": {"status": "REFUSED"}}, None),
        ({"author": "RULES", "fallback_reason": "MODEL_NOT_CONFIGURED"}, "PROVIDER_UNAVAILABLE"),
        (
            {
                "live_provider_advisory": {
                    "status": "PROVIDER_COMPLETED",
                    "provider_output": {"status": "PROVIDER_NOT_CONFIGURED"},
                }
            },
            "PROVIDER_UNAVAILABLE",
        ),
        ({"live_provider_advisory": {"status": "PROVIDER_COMPLETED", "provider_output": {"answer": "x"}}}, None),
        ({"model_attempt": {"error": "GENAI_PROVIDER_UNAVAILABLE: URLError"}}, "PROVIDER_UNAVAILABLE"),
        ({"author": "RULES", "fallback_reason": "MODEL_OUTPUT_FAILED_CHECKS"}, None),
        ("not a dict", None),
        (None, None),
    ],
)
def test_fallback_notice_reasons(provenance, expected):
    notice = fallback_notice("failure_chain", provenance)
    assert (notice.reason_code if notice else None) == expected
    if notice:
        assert notice.manual_alternative == "Build the failure chain by hand in Intelligence."


def test_reason_codes_for_genai_refusals():
    assert reason_code_for("GENAI_DISABLED_FOR_ORGANIZATION") == "AI_DISABLED"
    assert reason_code_for("GENAI_MONTHLY_BUDGET_REACHED") == "BUDGET_EXHAUSTED"
    assert reason_code_for("GENAI_PROVIDER_NOT_ALLOWED") == "PROVIDER_UNAVAILABLE"
    assert reason_code_for("GENAI_UNAVAILABLE") == "PROVIDER_UNAVAILABLE"
    assert reason_code_for(None) is None and reason_code_for("SOMETHING_ELSE") is None


def test_brief_and_counterfactual_responses_carry_the_label():
    from briefs.schemas import BriefResponse
    from counterfactual.schemas import CounterfactualResponse

    brief = BriefResponse.model_validate(
        {
            "id": str(uuid.uuid4()),
            "investigation_id": str(uuid.uuid4()),
            "brief_version": 1,
            "status": "DRAFT",
            "title": "Brief",
            "temporal_mode": "current",
            "temporal_cutoff": None,
            "human_review_state": "PENDING",
            "content": {"ai_brief": {"author": "RULES", "fallback_reason": "MODEL_NOT_CONFIGURED"}},
            "provenance": {},
            "limitations": None,
            "created_at": None,
        }
    )
    assert brief.epistemic.origin == "AI" and brief.ai_notice.reason_code == "PROVIDER_UNAVAILABLE"
    counterfactual = CounterfactualResponse(
        id=uuid.uuid4(), investigation_id=uuid.uuid4(), status="COMPLETED", result={}, created_at=None
    )
    assert counterfactual.epistemic.human_review_required is True


# ------------------------------------------------------------------------------------------------- AI status


@pytest.mark.parametrize(
    "allowed, models, used, limit, reason",
    [
        (False, [{"provider": "groq"}], 0, 100, "AI_DISABLED"),
        # No AI service here is said first: switching the organization on would change nothing.
        (False, [], 0, 100, "PROVIDER_UNAVAILABLE"),
        (True, [], 0, 100, "PROVIDER_UNAVAILABLE"),
        (True, [{"provider": "groq"}], 100, 100, "BUDGET_EXHAUSTED"),
        (True, [{"provider": "groq"}], 10, 100, None),
    ],
)
def test_ai_status_reasons(allowed, models, used, limit, reason):
    from backend.app.ai_settings import ai_status_for

    status = ai_status_for(
        {"ai_processing_allowed": allowed, "tokens_used": used, "monthly_token_budget": limit}, models
    )
    assert status["enabled"] is allowed and status["available"] is bool(models)
    assert status["budget"] == {"used": used, "limit": limit, "remaining": max(0, limit - used)}
    assert status["reason_code"] == reason and status["message"]
    assert status["manual_paths"] == {
        "hypotheses": True,
        "unknowns": True,
        "failure_chain": True,
        "observations": True,
        "ask": "record-based answers",
    }
