"""The reportability watch's and the CAPA effectiveness check's rules, without a database
(backend/app/reportability/rules.py, backend/app/capa_effectiveness/rules.py)."""

from __future__ import annotations

from datetime import date

import pytest

from backend.app.capa_effectiveness import rules as capa
from backend.app.reportability import rules

FDA = rules.clean_window(rules.TEMPLATES[0])
EU_15 = rules.clean_window(rules.TEMPLATES[1])
EU_10 = rules.clean_window(rules.TEMPLATES[2])


def _record(**fields):
    base = {"country": "US", "death": None, "serious_injury": None, "malfunction": None, "patient_involved": None}
    return {**base, **fields}


# ------------------------------------------------------------------------------------------- reportability windows


def test_templates_are_valid_windows_and_nothing_is_set_by_default():
    assert rules.windows_problem([FDA, EU_15, EU_10]) is None
    assert FDA["days"] == 30 and FDA["day_basis"] == rules.CALENDAR
    assert set(FDA["triggers"]) == {rules.DEATH, rules.SERIOUS_INJURY, rules.MALFUNCTION}
    assert (EU_15["days"], EU_10["days"]) == (15, 10)
    assert EU_10["triggers"] == [rules.DEATH]


@pytest.mark.parametrize("country", ["US", "usa", "U.S.A.", "United States", " united  states of america "])
def test_a_market_matches_in_the_spellings_systems_use(country):
    assert rules.applies(FDA, _record(country=country, malfunction=True))


def test_a_window_needs_its_trigger_and_its_market():
    assert not rules.applies(FDA, _record(country="US"))  # nothing reported
    assert not rules.applies(FDA, _record(country="Germany", death=True))
    assert rules.applies(EU_15, _record(country="DE", serious_injury=True))
    assert not rules.applies(EU_15, _record(country="DE", malfunction=True))  # the reviewer judges a malfunction
    assert not rules.applies(FDA, _record(country=None, death=True))
    anywhere = {**FDA, "markets": []}
    assert rules.applies(anywhere, _record(country=None, death=True))


def test_window_lists_are_cleaned_and_checked():
    cleaned = rules.clean_window(
        {"name": "  My  window ", "markets": ["US", "us", " ", "U.S."], "triggers": ["death", "x"], "days": 5}
    )
    assert cleaned == {
        "name": "My window",
        "markets": ["US"],
        "triggers": [rules.DEATH],
        "days": 5,
        "day_basis": rules.CALENDAR,
        "note": None,
    }
    assert rules.windows_problem([{**cleaned, "triggers": []}]).endswith("(a death, a serious injury or a malfunction)")
    assert "whole number of days" in rules.windows_problem([{**cleaned, "days": 0}])
    assert "whole number of days" in rules.windows_problem([{**cleaned, "days": True}])
    assert "already called" in rules.windows_problem([cleaned, {**cleaned, "name": "MY WINDOW"}])
    assert "count calendar days or work days" in rules.windows_problem([{**cleaned, "day_basis": "HOURS"}])
    assert rules.windows_problem([cleaned] * 21) == "Keep at most 20 windows"


def test_due_dates_in_calendar_and_work_days():
    friday = date(2026, 10, 9)
    assert rules.due_date(friday, {"days": 30, "day_basis": rules.CALENDAR}) == date(2026, 11, 8)
    # Five work days after a Friday: the next Friday (the weekend is skipped).
    assert rules.due_date(friday, {"days": 5, "day_basis": rules.WORK}) == date(2026, 10, 16)
    assert rules.add_work_days(date(2026, 10, 10), 1) == date(2026, 10, 12)  # Saturday -> Monday


@pytest.mark.parametrize(
    "today,state",
    [
        (date(2026, 10, 1), rules.RUNNING),
        (date(2026, 10, 26), rules.DUE_SOON),  # 5 days left of a 30-day window
        (date(2026, 10, 31), rules.DUE_SOON),  # the due day itself
        (date(2026, 11, 1), rules.OVERDUE),
    ],
)
def test_clock_states(today, state):
    assert rules.clock_state(date(2026, 10, 31), today, 30) == state


def test_a_short_window_is_due_soon_for_half_its_length():
    assert rules.soon_days(30) == 5 and rules.soon_days(10) == 5 and rules.soon_days(5) == 2 and rules.soon_days(2) == 1


def test_clocks_list_the_earliest_due_first():
    aware, today = date(2026, 10, 1), date(2026, 10, 5)
    found = rules.clocks(_record(country="France", death=True), [EU_15, EU_10, FDA], aware, today)
    assert [clock.name for clock in found] == [EU_10["name"], EU_15["name"]]
    assert found[0].due == date(2026, 10, 11) and found[0].days_left == 6 and found[0].triggers == (rules.DEATH,)
    assert rules.clocks(_record(death=True), [FDA], None, today) == []


def test_follow_ups_name_the_missing_answers():
    patient = rules.follow_ups(_record(patient_involved=True, serious_injury=False), [FDA], True)
    assert [item["code"] for item in patient] == ["PATIENT_OUTCOME"]
    harm = rules.follow_ups(_record(country=None, death=True), [FDA], False)
    assert [item["code"] for item in harm] == ["NO_COUNTRY", "NO_AWARENESS_DATE"]
    assert rules.follow_ups(_record(death=True, serious_injury=False, patient_involved=True), [FDA], True) == []


def test_what_the_watch_follows():
    assert rules.watched(_record(malfunction=True))
    assert rules.watched(_record(patient_involved=True))  # outcome unknown
    assert not rules.watched(_record(patient_involved=True, serious_injury=False, death=False))
    assert not rules.watched(_record())


def test_watch_states():
    assert rules.watch_state(rules.OVERDUE, False, True, True) == rules.OVERDUE
    assert rules.watch_state(rules.RUNNING, False, True, True) == rules.IN_REVIEW
    assert rules.watch_state(rules.RUNNING, False, False, True) == rules.RUNNING
    assert rules.watch_state(None, False, False, True) == rules.NO_WINDOW
    assert rules.watch_state(None, False, False, False) == rules.FOLLOW_UP
    assert rules.watch_state(rules.OVERDUE, True, False, True) == rules.DECIDED


def test_a_decision_is_on_time_against_its_binding_due_date():
    assert rules.on_time(date(2026, 10, 30), date(2026, 10, 31)) is True
    assert rules.on_time(date(2026, 10, 31), date(2026, 10, 31)) is True
    assert rules.on_time(date(2026, 11, 1), date(2026, 10, 31)) is False
    assert rules.on_time(date(2026, 11, 1), None) is None


# ------------------------------------------------------------------------------------------- CAPA effectiveness


@pytest.mark.parametrize(
    "status,planned,state",
    [
        (None, None, capa.NOT_PLANNED),
        ("PLANNED", date(2026, 12, 31), capa.SCHEDULED),
        ("PLANNED", date(2026, 10, 27), capa.DUE_SOON),  # 14 days left
        ("PLANNED", date(2026, 10, 12), capa.OVERDUE),
        ("EFFECTIVE", date(2026, 10, 12), capa.EFFECTIVE),
        ("NOT_EFFECTIVE", date(2026, 10, 12), capa.NOT_EFFECTIVE),
    ],
)
def test_effectiveness_states(status, planned, state):
    assert capa.state_of(status, planned, date(2026, 10, 13)) == state


def test_cancelled_capas_need_no_check_but_closed_ones_do():
    assert capa.is_excluded("Cancelled") and capa.is_excluded("REJECTED")
    assert not capa.is_excluded("closed") and capa.is_closed("Closed") and capa.is_closed("COMPLETE")
    assert not capa.is_closed("Effectiveness check")


def test_a_plan_is_checked():
    today = date(2026, 10, 13)
    good = ("No new occlusion complaints for 90 days", date(2027, 1, 13), date(2026, 10, 13))
    assert capa.plan_problem(*good, today) is None
    assert "what will show" in capa.plan_problem("short", good[1], good[2], today)
    assert capa.plan_problem(good[0], date(2026, 10, 1), date(2026, 10, 13), today).startswith("The measurement starts")
    assert capa.plan_problem(good[0], date(2030, 1, 1), good[2], today) == "Plan the check within three years"


def test_recurrence_is_described_never_judged():
    fewer = capa.recurrence(before=12, before_days=90, after=1, after_days=60)
    assert fewer["before"] == {"complaints": 12, "days": 90, "per_30_days": 4.0}
    assert fewer["since"] == {"complaints": 1, "days": 60, "per_30_days": 0.5}
    assert fewer["direction"] == "FEWER" and fewer["too_early"] is False
    assert "not a statistical test" in fewer["note"]
    assert capa.recurrence(0, 30, 0, 30)["direction"] == "NONE"
    assert capa.recurrence(1, 30, 3, 30)["direction"] == "MORE"
    assert capa.recurrence(1, 30, 1, 10)["too_early"] is True


def test_the_baseline_period_matches_the_period_since():
    assert capa.baseline_days(5) == 30 and capa.baseline_days(120) == 120 and capa.baseline_days(900) == 365


def test_suggested_criteria_and_what_is_signed():
    assert capa.default_criteria("Pump", ["OCC", "ALM"]) == (
        "No new complaints with problem code OCC, ALM on Pump for 90 days after the action."
    )
    assert (
        capa.default_criteria(None, []) == "No recurrence of the problem on the product for 90 days after the action."
    )
    meaning = capa.signature_meaning("CAPA000012", 2, capa.NOT_EFFECTIVE)
    assert meaning.startswith("I have reviewed effectiveness check 2 of CAPA000012") and "not effective" in meaning
    assert all(len(code) <= 12 for code in capa.SIGNATURE_CODES.values())
