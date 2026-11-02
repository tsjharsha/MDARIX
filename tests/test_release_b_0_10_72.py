"""Release B (0.10.72) of the "Simplicity and WoW" plan, "Show less, by default": the server half of each task.

B1: the market assessment's factual answers arrive from the complaint record, each with its source, for the person to
confirm or correct; judgement questions and the conclusion never do; Unknown is never read as No; each answer keeps
whether it was a confirmed suggestion, a corrected one or entered, on the signed record and in the audit trail.
"""

from __future__ import annotations

import pytest

from backend.app.reportability import markets

pytestmark = pytest.mark.unit

RV11 = {"death": False, "serious_injury": False, "malfunction": True, "patient_involved": True}


def test_b1_prefills_only_the_facts_the_record_states():
    assert markets.suggestions(markets.US_SET, RV11) == {
        "US1": {
            "answer": "NO",
            "source": "From the complaint record: no death was reported",
            "evidence": "Patient outcome fields",
        },
        **{
            key: {
                "answer": "NO",
                "source": "From the complaint record: no serious injury was reported",
                "evidence": "Patient outcome fields",
            }
            for key in ("US2A", "US2B", "US2C")
        },
        "US4": {
            "answer": "YES",
            "source": "From the complaint record: a malfunction was reported",
            "evidence": "Malfunction field",
        },
    }
    assert sorted(markets.suggestions(markets.IN_SET, RV11)) == ["IN2A", "IN2B", "IN2D", "IN2F"]
    # EU/NI and GB ask "might it have led to": a judgement, so nothing is suggested there.
    assert markets.suggestions(markets.EU_SET, RV11) == {} and markets.suggestions(markets.GB_SET, RV11) == {}


def test_b1_never_a_judgement_question():
    every = {"death": True, "serious_injury": False, "malfunction": False}
    for question_set in markets.QUESTION_SETS.values():
        assert not set(markets.suggestions(question_set, every)) & set(markets.JUDGEMENT_QUESTIONS)
    for question in ("US3", "US5", "US6", "IN1", "IN3"):
        assert question in markets.JUDGEMENT_QUESTIONS


def test_b1_unknown_is_never_turned_into_no():
    # The record silent (None) suggests nothing; a serious injury on the record suggests no criterion (a judgement).
    assert markets.suggestions(markets.US_SET, {"death": None, "serious_injury": None, "malfunction": None}) == {}
    assert (
        sorted(markets.suggestions(markets.US_SET, {"death": None, "serious_injury": True, "malfunction": None})) == []
    )
    found = markets.suggestions(markets.US_SET, {"death": True, "serious_injury": True, "malfunction": None})
    assert found == {
        "US1": {
            "answer": "YES",
            "source": "From the complaint record: a death was reported",
            "evidence": "Patient outcome fields",
        }
    }


def test_b1_confirmed_corrected_and_entered_are_recorded():
    offered = markets.suggestions(markets.US_SET, RV11)
    answers = {
        "US1": {"answer": "NO", "rationale": "x", "evidence": []},  # confirmed
        "US4": {"answer": "NO", "rationale": "x", "evidence": []},  # corrected (the record said Yes)
        "US2A": {"answer": "NO", "rationale": "x", "evidence": []},  # same as the record, but not confirmed: entered
        "US3": {"answer": "NO", "rationale": "x", "evidence": []},  # a judgement: entered
        "US5": {"answer": None, "rationale": "", "evidence": []},  # no answer: no origin
    }
    markets.mark_origins(answers, offered, {"US1"})
    assert markets.origins(answers) == {"US1": "CONFIRMED", "US4": "CORRECTED", "US2A": "ENTERED", "US3": "ENTERED"}
    assert answers["US4"]["suggested"] == "YES" and answers["US4"]["source"].startswith("From the complaint record")
