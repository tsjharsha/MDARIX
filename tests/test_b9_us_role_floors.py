"""B9 step 4 (B9-18, B9-19, B9-20, B9-26): the US importer and user facility floors, as data. Their questions are the
manufacturer's, word for word, by reference; Unknown is never No; no 5-work-day report for importers; no malfunction
for user facilities; 10 work days counted by the US rule; who must receive each report. No database."""

from __future__ import annotations

import itertools
from datetime import datetime, timezone

import pytest

from backend.app.reportability import markets
from backend.app.rule_register import engine, register

# B6b B3: scenarios this file verifies (its register row names it, or it is the group's own test file).
pytestmark = [pytest.mark.unit, pytest.mark.requirement("B9-13", "B9-17", "B9-18", "B9-19", "B9-20", "B9-23", "B9-33")]

VALUES = ("YES", "NO", None)  # None: Unknown (no answer)
IMPORTER_QS = ("US1", "US2A", "US2B", "US2C", "US3", "US4", "US5")
FACILITY_QS = ("US1", "US2A", "US2B", "US2C", "US3")


@pytest.fixture(autouse=True)
def _switches(monkeypatch):
    monkeypatch.delenv("MDARIX_B9_US_IMPORTER", raising=False)
    monkeypatch.setenv("MDARIX_B9_US_USER_FACILITY", "on")


def _answers(ids, values) -> dict:
    return {qid: {"answer": value} for qid, value in zip(ids, values) if value is not None}


def _floor(role: str) -> dict:
    return register.floor("US", role=role)


def test_the_role_picks_its_floor_and_an_off_switch_reads_manufacturer(monkeypatch):
    assert register.floor("US")["code"] == "US-floor-1"
    assert _floor("IMPORTER")["code"] == "US-IMP-floor-1"
    assert _floor("USER_FACILITY")["code"] == "US-UF-floor-1"
    assert register.floor("CA", role="IMPORTER") == register.floor("CA")  # no role floor: the market's own
    monkeypatch.setenv("MDARIX_B9_US_IMPORTER", "off")
    monkeypatch.delenv("MDARIX_B9_US_USER_FACILITY")  # its default: off
    assert _floor("IMPORTER")["code"] == "US-floor-1" and _floor("USER_FACILITY")["code"] == "US-floor-1"


def test_the_questions_are_the_manufacturers_word_for_word():
    wording = {q["id"]: q for q in register.floor("US")["content"]["question_set"]["questions"]}
    for role, ids in (("IMPORTER", IMPORTER_QS), ("USER_FACILITY", FACILITY_QS)):
        questions = _floor(role)["content"]["question_set"]["questions"]
        assert [q["id"] for q in questions] == list(ids)
        assert all(q == wording[q["id"]] for q in questions)
        assert markets.floor_question_set(_floor(role)).ids() == list(ids)


def test_importer_every_answer_set_matches_the_manufacturers_limbs_in_30_days_never_5():
    importer, maker = _floor("IMPORTER"), register.floor("US")
    assert set(importer["content"]["report_types"]) == {"US_IMP_30_DAY"}
    for values in itertools.product(VALUES, repeat=len(IMPORTER_QS)):
        answers = _answers(IMPORTER_QS, values)
        found = markets.evaluate("US", answers, importer)
        assert found["suggested"] == markets.evaluate("US", {**answers, "US6": {"answer": "NO"}}, maker)["suggested"]
        assert found["report_type"] in (None, "US_IMP_30_DAY")
        _never_no(answers, found, importer, IMPORTER_QS)


def test_user_facility_death_or_injury_caused_in_10_work_days_and_no_malfunction():
    facility, maker = _floor("USER_FACILITY"), register.floor("US")
    assert set(facility["content"]["report_types"]) == {"US_UF_10_WORK_DAY"}
    for values in itertools.product(VALUES, repeat=len(FACILITY_QS)):
        answers = _answers(FACILITY_QS, values)
        found = markets.evaluate("US", answers, facility)
        limb = {**answers, "US4": {"answer": "NO"}, "US6": {"answer": "NO"}}  # the manufacturer's death/injury limb
        assert found["suggested"] == markets.evaluate("US", limb, maker)["suggested"]
        _never_no(answers, found, facility, FACILITY_QS)
    # A malfunction alone is never a user facility report.
    malfunction = _answers(IMPORTER_QS, ("NO", "NO", "NO", "NO", None, "YES", "YES"))
    assert markets.evaluate("US", malfunction, facility)["suggested"] == engine.NOT_REPORTABLE


def _never_no(answers: dict, found: dict, floor: dict, ids) -> None:
    """Unknown is never No: when any Yes for the unanswered questions makes it reportable, it is not concluded No."""
    filled = {**answers, **{qid: {"answer": "YES"} for qid in ids if qid not in answers}}
    if markets.evaluate("US", filled, floor)["suggested"] == engine.REPORTABLE:
        assert found["suggested"] != engine.NOT_REPORTABLE


def test_ten_work_days_are_counted_by_the_us_rule():
    facility = _floor("USER_FACILITY")
    aware = datetime(2026, 11, 6, 15, tzinfo=timezone.utc)  # a Friday: day 1 is Monday 9 November
    clock = markets.market_clock(
        "US", engine.REPORTABLE, "US_UF_10_WORK_DAY", [], aware, aware, "America/New_York", floor=facility
    )
    assert (clock["due_date"], clock["source"]) == ("2026-11-20", "REGULATION")
    importer = markets.market_clock(
        "US", engine.REPORTABLE, "US_IMP_30_DAY", [], aware, aware, floor=_floor("IMPORTER")
    )
    assert importer["due_date"] == "2026-12-06"
    assert {"US_IMP_30_DAY", "US_UF_10_WORK_DAY"} <= set(markets.REPORT_TYPES)


def test_recipients_per_rule_are_kept_with_the_rules_applied():
    death = _answers(FACILITY_QS, ("YES", "NO", "NO", "NO", "YES"))
    assert engine.applied(_floor("USER_FACILITY")["content"], death)["rules"] == [
        {"id": "F-UF-1", "state": "APPLIES", "recipients": ["FDA", "MANUFACTURER"]}
    ]
    malfunction = _answers(IMPORTER_QS, ("NO", "NO", "NO", "NO", None, "YES", "YES"))
    assert engine.applied(_floor("IMPORTER")["content"], malfunction)["rules"] == [
        {"id": "F-IMP-2", "state": "APPLIES", "recipients": ["MANUFACTURER"]}
    ]
    # The manufacturer's floor lists none: its rules_applied are unchanged.
    assert "recipients" not in engine.applied(register.floor("US")["content"], malfunction)["rules"][0]


def test_triage_tiers_follow_the_role():
    assert {tier[0] for key, tier in _floor("IMPORTER")["content"]["provisional"].items() if key != "ruled_out"} == {30}
    assert {
        tuple(tier[:2]) for key, tier in _floor("USER_FACILITY")["content"]["provisional"].items() if key != "ruled_out"
    } == {(10, "WORK")}
