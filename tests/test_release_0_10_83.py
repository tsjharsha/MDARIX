"""Trial release 0.10.83, round D2 "Decide and report", the server half of each item.

D2.1-D2.3, the tree is the questionnaire: "serious injury" is a judgement, never pre-filled, with the record's words
beside it; questions earlier answers make unnecessary fold away with why, and are not required to sign; the Decision
trees tab lists the complaints still to assess, not only those already walked.
"""

from __future__ import annotations

import pytest

from backend.app.reportability import markets
from tests.test_market_assessment_api import (
    _acknowledge,
    _answers,
    _market,
    _save,
    _sign,
    _url,
    org,  # noqa: F401 (the module's organization fixture)
)
from tests.test_reporting_capa_api import PASSWORD, _complaint

RV11 = {"death": False, "serious_injury": False, "malfunction": True, "patient_involved": True, "severity": "No harm"}


def _a(**values: str) -> dict:
    return {key: {"answer": value, "rationale": "", "evidence": []} for key, value in values.items()}


# --------------------------------------------------------------------------------------------- D2.1-D2.3 (unit)


@pytest.mark.unit
def test_serious_injury_is_a_judgement_never_prefilled_with_the_records_words_beside_it():
    offered = markets.suggestions(markets.US_SET, RV11)
    assert sorted(offered) == ["US1", "US4"]
    assert not {"IN2B", "IN2D", "IN2F"} & set(markets.suggestions(markets.IN_SET, RV11))
    notes = markets.record_notes(markets.US_SET, RV11)
    assert sorted(notes) == ["US2A", "US2B", "US2C"]
    assert notes["US2A"] == ("The record says no serious injury was reported · severity “No harm”.")
    assert set(markets.record_notes(markets.IN_SET, RV11)) == {"IN2B", "IN2D", "IN2F"}
    for question in ("US2A", "US2B", "US2C", "IN2B", "IN2D", "IN2F"):
        assert question in markets.JUDGEMENT_QUESTIONS


@pytest.mark.unit
def test_questions_earlier_answers_make_unnecessary_fold_away_with_why():
    assert markets.not_asked(markets.US, {}) == {}
    no_harm = _a(US1="NO", US2A="NO", US2B="NO", US2C="NO")
    assert markets.not_asked(markets.US, no_harm) == {"US3": "Not asked: no death and no serious injury"}
    nothing = _a(US1="NO", US2A="NO", US2B="NO", US2C="NOT_APPLICABLE", US4="NO")
    assert markets.not_asked(markets.US, nothing) == {
        "US3": "Not asked: no death and no serious injury",
        "US5": "Not asked: no malfunction",
        "US6": "Not needed: not reportable on the answers above",
    }
    # Unknown never folds a question away: it is never No.
    assert markets.not_asked(markets.US, _a(US1="UNKNOWN", US2A="NO", US2B="NO", US2C="NO")) == {}
    assert set(markets.not_asked(markets.EU_NI, _a(EU1="NO"))) == {
        "EU2",
        *(f"EU3{letter}" for letter in "ABCDEF"),
        "EU4",
        "EU5",
        "EU6",
    }
    assert markets.not_asked(markets.CA, _a(CA1="YES", CA2="YES", CA3="YES", CA5="YES")) == {
        "CA4": "Not needed: it already led to death or a serious deterioration",
        "CA6": "Not asked: the incident occurred in Canada",
    }
    assert markets.evaluate(markets.US, no_harm)["not_asked"] == {"US3": "Not asked: no death and no serious injury"}


@pytest.mark.unit
def test_a_folded_question_is_not_required_to_sign():
    answers = {
        key: {"answer": value, "rationale": "Read from the record and the reporter's call", "evidence": []}
        for key, value in dict(US1="NO", US2A="NO", US2B="NO", US2C="NO", US4="NO").items()
    }
    assert markets.answers_problem(markets.US_SET, answers, complete=True) is None
    del answers["US4"]
    assert markets.answers_problem(markets.US_SET, answers, complete=True).startswith("Answer question US4")


# --------------------------------------------------------------------------------------------- D2.1-D2.3 (API)


@pytest.mark.db
def test_the_tree_lists_complaints_still_to_assess_and_signs_without_folded_questions(org):  # noqa: F811
    regulatory = org["regulatory"]
    complaint = _complaint(
        org["tenant_id"],
        org["product"],
        country="US",
        patient_involved=True,
        serious_injury=False,
        death=False,
        malfunction=True,
        severity="No harm",
    )
    trees = regulatory.get("/api/v1/decision-trees").json()
    listed = next(item for item in trees["complaints"] if item["id"] == complaint)
    assert listed["markets"] == [] and listed["signed"] == []

    detail = regulatory.get(_url(complaint)).json()
    us = _market(detail, "US")
    assert sorted(us["suggestions"]) == ["US1", "US4"]
    assert us["record_notes"]["US2B"].startswith("The record says no serious injury was reported")

    _acknowledge(regulatory, "US")
    # A malfunction with no harm that would not harm if it recurred: questions 3 and 6 fold away.
    item = _save(
        regulatory,
        complaint,
        "US",
        _answers(US1="NO", US2A="NO", US2B="NO", US2C="NO", US4="YES", US5="NO"),
        harm_level="NEGLIGIBLE",
    )
    assert item["evaluation"]["suggested"] == "NOT_REPORTABLE"
    assert item["evaluation"]["not_asked"] == {
        "US3": "Not asked: no death and no serious injury",
        "US6": "Not needed: not reportable on the answers above",
    }
    signed = _sign(regulatory, complaint, "US", item, "NOT_REPORTABLE", password=PASSWORD)
    assert signed.status_code == 200, signed.text
    path = regulatory.get(f"/api/v1/decision-trees?complaint_id={complaint}").json()["paths"]["US"]
    assert {node["id"]: node["not_asked"] for node in path["nodes"] if node["not_asked"]} == {
        "US3": "Not asked: no death and no serious injury",
        "US6": "Not needed: not reportable on the answers above",
    }
