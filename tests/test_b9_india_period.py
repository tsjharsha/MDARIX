"""B9 step 2 (B9-D1, scenarios B9-01, B9-02, B9-29): IN-floor-2 gives India's serious adverse event report its 15
calendar days (India MDR 2017 Rule 26(ii), starter, for your consultant to confirm) and changes nothing else. No
database."""

from __future__ import annotations

import itertools
import json
from datetime import datetime, timezone

import pytest

from backend.app.intake import rules as intake
from backend.app.reportability import markets, rules
from backend.app.rule_register import engine, register

pytestmark = pytest.mark.unit

THREE = ("YES", "NO", "UNKNOWN")
AWARE = datetime(2027, 1, 4, 6, 30, tzinfo=timezone.utc)  # 4 Jan in India: day 1; day 15 is 18 Jan
REPORTABLE = {"IN1": "YES", "IN2A": "YES"}


def _window(days: int, basis: str = rules.CALENDAR) -> dict:
    return rules.clean_window(
        {"name": f"India {days}", "markets": ["India"], "triggers": ["DEATH"], "days": days, "day_basis": basis}
    )


def _clock(state, windows, answers=REPORTABLE, floor=None):
    floor = floor or register.get("IN-floor-2")
    found = engine.evaluate(floor["content"], {k: {"answer": v} for k, v in answers.items()})
    return markets.market_clock(
        "IN",
        state,
        found["report_type"],
        windows,
        AWARE,
        AWARE,
        "Asia/Kolkata",
        if_reportable=found["report_type_if_reportable"],
        floor=floor,
    )


def test_version_two_is_a_correction_from_the_start_with_only_the_period_changed():
    one, two = register.get("IN-floor-1"), register.get("IN-floor-2")
    assert two["change"] == {**two["change"], "kind": "CORRECTION", "corrects": "IN-floor-1"}
    assert (two["effective_from"], two["effective_to"]) == (one["effective_from"], one["effective_to"]) == (None, None)
    assert two["review"]["note"] == one["review"]["note"]  # the starter mark
    kind = two["content"]["report_types"]["IN_SERIOUS_ADVERSE_EVENT"]
    assert (kind["days"], kind["basis"]) == (15, "CALENDAR") and "starter" in kind["label"]
    rest = {key: value for key, value in two["content"].items() if key != "report_types"}
    assert rest == {key: value for key, value in one["content"].items() if key != "report_types"}


def test_every_yes_no_unknown_answer_set_gives_the_same_result_under_both_versions():
    """3^8: suggestion, report type, notes and folding identical (B9-29)."""
    one, two = register.get("IN-floor-1")["content"], register.get("IN-floor-2")["content"]
    ids = [question["id"] for question in one["question_set"]["questions"]]
    count = 0
    for combination in itertools.product(THREE, repeat=len(ids)):
        answers = {key: {"answer": value} for key, value in zip(ids, combination)}
        assert json.dumps(engine.evaluate(one, answers), sort_keys=True) == json.dumps(
            engine.evaluate(two, answers), sort_keys=True
        )
        assert engine.applied(one, answers) == engine.applied(two, answers)
        count += 1
    assert count == 3**8


def test_the_switch_picks_the_version(monkeypatch):
    assert register.floor("IN")["code"] == "IN-floor-2"
    monkeypatch.setenv("MDARIX_B9_INDIA", "off")
    assert register.floor("IN")["code"] == "IN-floor-1"
    assert register.get("IN-floor-2") is not None  # a record that names it still reads it
    assert markets.REPORT_TYPES["IN_SERIOUS_ADVERSE_EVENT"].days is None


def test_a_reportable_conclusion_with_a_longer_window_is_due_in_15_days_from_the_regulation():
    """B9-01: a 30-day India window no longer gives a later date; the awareness day is day 1."""
    clock = _clock(markets.REPORTABLE, [_window(30)])
    assert (clock["source"], clock["days"], clock["due_date"]) == ("REGULATION", 15, "2027-01-18")
    assert "Rule 26" in clock["window"]


def test_a_reportable_conclusion_with_an_exact_15_day_window_takes_the_window():
    """B9-02."""
    clock = _clock(markets.REPORTABLE, [_window(30), _window(15)])
    assert (clock["source"], clock["window"], clock["due_date"]) == ("WINDOW", "India 15", "2027-01-18")
    # 15 work days is not the regulation's period: the regulation applies.
    assert _clock(markets.REPORTABLE, [_window(15, rules.WORK)])["source"] == "REGULATION"


def test_pending_takes_the_earliest_of_the_windows_and_15_days():
    pending = {"IN1": "YES", "IN2A": "UNKNOWN"}
    assert _clock(markets.PENDING, [_window(30)], pending)["due_date"] == "2027-01-18"
    assert _clock(markets.PENDING, [_window(10)], pending)["window"] == "India 10"


def test_version_one_kept_the_window_of_any_length():
    """Signed conclusions under IN-floor-1 keep their date: version 1 still reads the window (B9-04 at the clock)."""
    clock = _clock(markets.REPORTABLE, [_window(30)], floor=register.get("IN-floor-1"))
    assert (clock["source"], clock["days"]) == ("WINDOW", 30)


def test_triage_dates_do_not_move(monkeypatch):
    """Triage already used 15 days for India; its provisional deadlines are the same with the switch on and off."""

    def run():
        return json.dumps(
            [
                intake.provisional_deadlines(AWARE, ["IN"], level, AWARE, False, own="IN", org_zone="Asia/Kolkata")
                for level in intake.TIER_LABELS
            ],
            sort_keys=True,
            default=str,
        )

    on = run()
    monkeypatch.setenv("MDARIX_B9_INDIA", "off")
    assert run() == on


def test_the_legal_limit_now_warns_for_a_longer_india_window(monkeypatch):
    assert [item["market"] for item in markets.longer_than_law([_window(30)])] == ["IN"]
    monkeypatch.setenv("MDARIX_B9_INDIA", "off")
    assert markets.longer_than_law([_window(30)]) == []
