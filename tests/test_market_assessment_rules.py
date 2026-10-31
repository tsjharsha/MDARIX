"""The rules of the per-market seriousness and causation assessment and the harm-severity scale (T-G15S, T-G15H), and
the classification's coding rules (T-G39), without a database."""

from __future__ import annotations

from datetime import date

import pytest

from backend.app import standards
from backend.app.complaint_classification import rules as classification
from backend.app.reportability import markets
from backend.app.reportability import rules as watch_rules

pytestmark = pytest.mark.unit

WHY = "Read from the complaint record"


def answers(**values: str) -> dict:
    return {key: {"answer": value, "rationale": WHY, "evidence": []} for key, value in values.items()}


US_SERIOUS = dict(US1="NO", US2A="UNKNOWN", US2B="NO", US2C="YES", US3="YES", US4="YES", US5="YES", US6="NO")
US_NONE = dict(
    US1="NO", US2A="NO", US2B="NO", US2C="NO", US3="NOT_APPLICABLE", US4="NO", US5="NOT_APPLICABLE", US6="NO"
)


def test_every_question_shows_its_definition_its_clause_and_the_starter_mark():
    for question_set in markets.QUESTION_SETS.values():
        shown = question_set.as_dict()
        assert shown["starter_mark"] == standards.STARTER_MARK
        assert "awaiting regulatory confirmation" in shown["starter_mark"]
        for question in shown["questions"]:
            assert question["clause"] and question["definition"] and question["starter"] is True
            assert all(code in standards.BY_ID for code in question["basis"])
    assert [q.id for q in markets.US_SET.questions] == ["US1", "US2A", "US2B", "US2C", "US3", "US4", "US5", "US6"]
    assert markets.US_SET.version == "US-starter-1" and markets.EU_SET.version == "EU-starter-1"
    assert "Recurrence is presumed" in markets.US_SET.questions[6].note
    assert "Report when unsure" in markets.EU_SET.note and "Report when unsure" in markets.GB_SET.note


def test_the_us_serious_example_is_reportable_in_30_days_with_one_limb_unknown():
    found = markets.evaluate(markets.US, answers(**US_SERIOUS))
    assert found["suggested"] == markets.REPORTABLE and found["report_type"] == "US_30_DAY"
    assert "not the 5-work-day report" in found["notes"][0]


def test_the_five_work_day_report_only_for_remedial_action_or_fda_s_written_request():
    yes = markets.evaluate(markets.US, answers(**{**US_SERIOUS, "US6": "YES"}))
    assert yes["report_type"] == "US_5_WORK_DAY"
    unknown = markets.evaluate(markets.US, answers(**{**US_SERIOUS, "US6": "UNKNOWN"}))
    assert unknown["report_type"] == "US_30_DAY" and "a Yes makes it the 5-work-day report" in unknown["notes"][0]
    # Not reportable stays not reportable, whatever question 6 says.
    assert markets.evaluate(markets.US, answers(**{**US_NONE, "US6": "YES"}))["suggested"] == markets.NOT_REPORTABLE
    assert markets.REPORT_TYPES["US_5_WORK_DAY"].day_basis == watch_rules.WORK


def test_unknown_is_never_no():
    # The patient's outcome is Unknown and the malfunction's recurrence not yet judged: pending, never not reportable.
    pending = answers(US1="NO", US2A="UNKNOWN", US2B="UNKNOWN", US2C="UNKNOWN", US3="UNKNOWN", US4="YES")
    assert markets.evaluate(markets.US, pending)["suggested"] == markets.PENDING
    assert markets.evaluate(markets.US, answers(**US_NONE))["suggested"] == markets.NOT_REPORTABLE
    # One Unknown that could make it reportable keeps it pending.
    one = answers(**{**US_NONE, "US2A": "UNKNOWN", "US3": "YES"})
    assert markets.evaluate(markets.US, one)["suggested"] == markets.PENDING
    # An Unknown that cannot make it reportable does not: no harm and no malfunction leave causation moot.
    moot = answers(**{**US_NONE, "US3": "UNKNOWN", "US5": "UNKNOWN"})
    assert markets.evaluate(markets.US, moot)["suggested"] == markets.NOT_REPORTABLE
    problem = markets.conclusion_problem(markets.PENDING, markets.NOT_REPORTABLE, "We think it is fine really")
    assert "Unknown is never No" in problem


def test_a_malfunction_is_judged_as_if_it_recurred():
    malfunction = answers(**{**US_NONE, "US4": "YES", "US5": "YES"})
    assert markets.evaluate(markets.US, malfunction)["suggested"] == markets.REPORTABLE
    # A No on question 5 needs its reason.
    no_reason = {**answers(**{**US_NONE, "US4": "YES"}), "US5": {"answer": "NO", "rationale": "", "evidence": []}}
    problem = markets.answers_problem(markets.US_SET, no_reason, complete=True)
    assert problem.startswith("Question US5 is No")
    assert markets.answers_problem(markets.US_SET, no_reason, complete=False) is None


def test_signing_needs_every_question_answered_with_its_rationale():
    partial = answers(US1="NO")
    assert markets.answers_problem(markets.US_SET, partial, complete=False) is None
    assert markets.answers_problem(markets.US_SET, partial, complete=True).startswith("Answer question US2A")
    assert markets.answers_problem(markets.US_SET, answers(**US_SERIOUS), complete=True) is None
    cleaned = markets.clean_answers(markets.US_SET, {"US1": {"answer": "yes", "rationale": "  a  b "}, "XX": {}})
    assert cleaned == {"US1": {"answer": "YES", "rationale": "a b", "evidence": []}}


def test_an_override_needs_a_reason():
    assert markets.conclusion_problem(markets.REPORTABLE, markets.REPORTABLE, "") is None
    assert "override" in markets.conclusion_problem(markets.NOT_REPORTABLE, markets.REPORTABLE, "short")
    assert markets.conclusion_problem(markets.PENDING, markets.REPORTABLE, "Report when unsure, per QP-08") is None
    assert (
        markets.conclusion_problem(markets.REPORTABLE, markets.PENDING, "x" * 20)
        == "Conclude reportable or not reportable"
    )


def test_eu_and_gb_serious_incidents_and_their_periods():
    eu = dict(EU1="YES", EU2="NO", EU3A="YES", EU3B="NO", EU3C="NO", EU3D="NO", EU3E="NO", EU3F="NO", EU4="NO")
    found = markets.evaluate(markets.EU_NI, answers(**eu, EU5="YES", EU6="NO"))
    assert (found["suggested"], found["report_type"]) == (markets.REPORTABLE, "EU_15_DAY")
    assert markets.evaluate(markets.EU_NI, answers(**eu, EU5="YES", EU6="YES"))["report_type"] == "EU_10_DAY"
    assert markets.evaluate(markets.EU_NI, answers(**{**eu, "EU4": "YES"}, EU5="YES"))["report_type"] == "EU_2_DAY"
    assert markets.evaluate(markets.EU_NI, answers(**eu, EU5="UNKNOWN"))["suggested"] == markets.PENDING
    assert markets.evaluate(markets.EU_NI, answers(**eu, EU5="NO"))["suggested"] == markets.NOT_REPORTABLE
    gb = {key.replace("EU", "GB"): value for key, value in eu.items()}
    assert markets.evaluate(markets.GB, answers(**gb, GB5="YES", GB6="NO"))["report_type"] == "GB_15_DAY"
    india = dict(IN1="YES", IN2A="NO", IN2B="NO", IN2C="YES", IN2D="NO", IN2E="NO", IN2F="NO", IN3="YES")
    found = markets.evaluate(markets.IN, answers(**india))
    assert found["report_type"] == "IN_SERIOUS_ADVERSE_EVENT" and "unexpected" in found["notes"][0]


def test_the_scale_maps_the_qms_severity_and_marks_each_market_s_threshold():
    assert markets.level_of_severity("Critical") == markets.CRITICAL
    assert markets.level_of_severity(" critical ") == markets.CRITICAL
    assert markets.level_of_severity("Grade 3") is None  # not mapped: choose a level
    shown = markets.scale()
    assert shown["version"] == "scale-starter-1" and [level["code"] for level in shown["levels"]] == list(
        markets.LEVELS
    )
    serious = next(level for level in shown["levels"] if level["code"] == markets.SERIOUS)
    assert {item["market"] for item in serious["thresholds"]} == set(markets.MARKETS)
    # Death, life-threatening harm and permanent impairment sit at or above every threshold.
    for term in ("DEATH", "LIFE_THREATENING", "PERMANENT_IMPAIRMENT"):
        label, level, protected = markets.TERMS[term]
        assert protected and all(markets.rank(level) >= markets.rank(markets.THRESHOLDS[m]) for m in markets.MARKETS)


def test_a_protected_term_cannot_be_lowered_and_a_changed_level_needs_a_reason():
    assert "cannot be lowered" in markets.harm_problem("MINOR", "DEATH", "x" * 30, None, complete=True)
    assert markets.harm_problem("CATASTROPHIC", "DEATH", "", None, complete=True) is None
    assert "why you chose" in markets.harm_problem("SERIOUS", None, "", "Critical", complete=True)
    assert markets.harm_problem("SERIOUS", None, "Clinical notes show recovery", "Critical", complete=True) is None
    assert markets.harm_problem(None, None, "", "Grade 3", complete=False) is None
    assert "not mapped" in markets.harm_problem(None, None, "", "Grade 3", complete=True)


def test_an_answer_against_the_scale_is_found_and_the_scale_never_decides():
    no_injury = answers(**US_NONE)
    assert "at or above the US serious injury threshold" in markets.disagreement(
        markets.US, no_injury, markets.CRITICAL
    )
    assert markets.disagreement(markets.US, no_injury, markets.MINOR) is None
    # Unknown is not a No: it does not disagree.
    assert markets.disagreement(markets.US, answers(**{**US_NONE, "US2A": "UNKNOWN"}), markets.CRITICAL) is None
    # The level never changes the suggestion by itself.
    assert markets.evaluate(markets.US, no_injury)["suggested"] == markets.NOT_REPORTABLE


def test_markets_from_countries_and_windows_and_their_clocks():
    assert markets.market_of("France") == markets.EU_NI and markets.market_of("U.S.A.") == markets.US
    assert markets.market_of("Northern Ireland") == markets.EU_NI and markets.market_of("India") == markets.IN
    assert markets.market_of("Japan") is None and markets.market_of(None) is None
    templates = [watch_rules.clean_window(item) for item in watch_rules.TEMPLATES]
    fda, eu15, eu10 = templates[0], templates[1], templates[2]
    assert markets.enabled_markets([fda, eu15]) == [markets.US, markets.EU_NI]
    assert markets.enabled_markets([{**fda, "markets": []}]) == list(markets.MARKETS)
    aware, today = date(2026, 10, 1), date(2026, 10, 5)
    thirty = markets.market_clock(markets.US, markets.REPORTABLE, "US_30_DAY", [fda], aware, today)
    assert (thirty["due_date"], thirty["source"]) == ("2026-10-31", "WINDOW")
    five = markets.market_clock(markets.US, markets.REPORTABLE, "US_5_WORK_DAY", [fda], aware, today)
    assert (five["due_date"], five["source"]) == ("2026-10-08", "REGULATION")  # 5 work days, no window matches
    pending = markets.market_clock(markets.EU_NI, markets.PENDING, None, [fda, eu15, eu10], aware, today)
    assert pending["days"] == 10  # the shortest window of the market, still counting
    assert markets.market_clock(markets.EU_NI, markets.NOT_REPORTABLE, None, [eu15], aware, today) is None
    india = next(item for item in watch_rules.TEMPLATES if item["name"].startswith("India"))
    assert "Starter text" in india["note"] and india["basis"] == ["IN_MDR"]


def test_classification_codes_list_labels_and_keeps_any_other_source_value_as_unknown():
    assert classification.code_source_value("use_environment", "Intensive care unit") == (
        "INTENSIVE_CARE_UNIT",
        "Intensive care unit",
    )
    assert classification.code_source_value("use_environment", "Step-down unit") == ("UNKNOWN", "Step-down unit")
    assert classification.code_source_value("user_type", "") == ("UNKNOWN", None)
    assert "other" in classification.classification_problem("OTHER", "", "PATIENT", None)
    assert classification.classification_problem("HOME", None, "LAY_USER", None) is None
    assert classification.CODING_CRITERIA_VERSION == "coding-starter-1"
