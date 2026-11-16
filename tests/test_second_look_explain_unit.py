"""The second look's AI explanation checks (backend/app/complaint_review/explain.py), without a database: only
sentences whose quotes are the record's own words, and that neither decide nor state a cause, are kept."""

from __future__ import annotations

import pytest

from backend.app.complaint_review import explain

RECORD = {
    "description": "Customer says   the pump stopped and the patient choked",
    "status": "Cancelled",
    "complaint_type": "Inquiry",
    "problem_code": None,
    "severity": "",
    "death": False,
    "serious_injury": True,
    "malfunction": True,
}


def _sentence(text: str, *quotes: tuple[str, str]) -> dict:
    return {"text": text, "quotes": [{"field": field, "text": words} for field, words in quotes]}


def test_the_model_sees_only_filled_fields_with_harm_as_words():
    fields = explain.record_fields(RECORD)
    assert fields == {
        "description": "Customer says the pump stopped and the patient choked",
        "status": "Cancelled",
        "complaint_type": "Inquiry",
        "harm": "Serious injury reported. Malfunction reported.",
    }


def test_a_sentence_quoting_the_record_word_for_word_is_kept():
    kept, dropped = explain.check_sentences(
        {
            "sentences": [
                _sentence(
                    "The description alleges a stop during use; the record also flags harm.",
                    ("description", "THE PUMP  stopped"),
                    ("harm", "Serious injury reported."),
                )
            ]
        },
        explain.record_fields(RECORD),
    )
    assert dropped == []
    assert kept[0]["fields"] == ["description", "harm"]
    assert kept[0]["quotes"][0] == {"field": "description", "label": "Description", "text": "THE PUMP stopped"}


@pytest.mark.parametrize(
    "sentence, reason",
    [
        (_sentence("No quote at all."), "NO_QUOTE"),
        (_sentence("Mentions a fire.", ("description", "caught fire")), "QUOTE_NOT_IN_RECORD"),
        (_sentence("Quotes a field that is not given.", ("lot", "Cancelled")), "QUOTE_NOT_IN_RECORD"),
        (_sentence("Too short a quote.", ("status", "Ca")), "QUOTE_NOT_IN_RECORD"),
        (_sentence("This is a complaint.", ("status", "Cancelled")), "DECISION_CLAIM"),
        (_sentence("It is reportable to FDA.", ("description", "patient choked")), "DECISION_CLAIM"),
        (_sentence("It should be treated as a complaint.", ("status", "Cancelled")), "DECISION_CLAIM"),
        (_sentence("The pump stop caused the choking.", ("description", "patient choked")), "CAUSAL_CLAIM"),
        (_sentence("x" * (explain.SENTENCE_MAX + 1), ("status", "Cancelled")), "EMPTY_OR_TOO_LONG"),
    ],
)
def test_a_sentence_that_does_not_pass_is_dropped_with_why(sentence, reason):
    kept, dropped = explain.check_sentences({"sentences": [sentence]}, explain.record_fields(RECORD))
    assert kept == [] and dropped[0]["reason"] == reason


def test_hedged_wording_and_reasoning_words_stay():
    kept, _ = explain.check_sentences(
        {
            "sentences": [
                _sentence(
                    "It may meet the complaint definition because the customer reports a stop.",
                    ("description", "pump stopped"),
                ),
                _sentence("This may be a complaint about performance.", ("description", "pump stopped")),
            ]
        },
        explain.record_fields(RECORD),
    )
    assert len(kept) == 2


def test_at_most_three_sentences_are_kept():
    many = [_sentence(f"Sentence {n} quotes the status.", ("status", "Cancelled")) for n in range(5)]
    kept, dropped = explain.check_sentences({"sentences": many}, explain.record_fields(RECORD))
    assert len(kept) == explain.SENTENCES_MAX and [item["reason"] for item in dropped] == ["OVER_LIMIT", "OVER_LIMIT"]


def test_a_reply_that_is_not_the_requested_form_keeps_nothing():
    assert explain.check_sentences({"answer": "free text"}, explain.record_fields(RECORD)) == ([], [])
    assert explain.check_sentences([], explain.record_fields(RECORD)) == ([], [])


def test_the_explanation_request_lists_the_complaint_for_every_field_it_sends():
    from genai.provider import GenAIUnavailable

    seen = {}

    class Spy:
        def complete(self, *_args, **kwargs):
            seen.update(kwargs)
            raise GenAIUnavailable("GENAI_TRIAL_SAMPLE_ONLY: test")

    result = explain.explain(None, None, {**RECORD, "id": "c-1"}, {}, actor_ref="u", provider=Spy())
    assert result["ai"]["status"] == "REFUSED"
    blocks = {block["id"] for block in seen["evidence"]}
    assert {entry["evidence_id"] for entry in seen["records"]} == blocks
    assert {(entry["table"], entry["id"]) for entry in seen["records"]} == {("complaints", "c-1")}
