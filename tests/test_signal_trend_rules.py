"""The statistical trend check's rules, without a database (backend/app/signals/trend_rules.py)."""

from __future__ import annotations

import math

import pytest

from backend.app.signals import trend_rules as trend


@pytest.mark.parametrize(
    "observed,expected,probability",
    [
        (0, 2.0, 1.0),
        (1, 2.0, 1 - math.exp(-2.0)),
        (3, 1.0, 1 - math.exp(-1.0) * (1 + 1 + 0.5)),
        (5, 0.5, 1 - math.exp(-0.5) * (1 + 0.5 + 0.125 + 0.5**3 / 6 + 0.5**4 / 24)),
    ],
)
def test_the_poisson_tail_is_exact(observed, expected, probability):
    assert trend.poisson_tail(observed, expected) == pytest.approx(probability, rel=1e-9)


def test_the_poisson_tail_is_bounded():
    assert trend.poisson_tail(3, 0.0) == 0.0
    assert 0.0 <= trend.poisson_tail(200, 150.0) <= 1.0
    assert trend.poisson_tail(10, 10.0) == pytest.approx(0.5420702855281478, rel=1e-9)


def test_history_never_reaches_before_the_release():
    assert trend.history_days(None) == 180
    assert trend.history_days(1000) == 180
    assert trend.history_days(120) == 90
    assert trend.history_days(20) == 0


def test_a_clear_rise_is_significant():
    found = trend.check(recent=6, history=6, days_of_history=180)  # expected 1.0 in 30 days
    assert found.result == trend.SIGNIFICANT
    assert found.expected == pytest.approx(1.0) and found.ratio == pytest.approx(6.0)
    assert found.p_value < 0.01
    assert found.as_dict()["label"] == "Rate significantly higher than its history"


def test_a_moderate_rise_is_elevated_and_a_usual_month_is_steady():
    assert trend.check(recent=6, history=12, days_of_history=180).result == trend.ELEVATED  # expected 2.0, p 0.017
    assert trend.check(recent=5, history=12, days_of_history=180).result == trend.STEADY  # p 0.053
    assert trend.check(recent=4, history=24, days_of_history=180).result == trend.STEADY  # expected 4.0


def test_small_numbers_and_short_histories_are_not_assessed():
    assert trend.check(recent=2, history=0, days_of_history=180).result == trend.TOO_FEW
    short = trend.check(recent=9, history=0, days_of_history=45)
    assert short.result == trend.SHORT_HISTORY and short.p_value is None


def test_no_history_assumes_one_complaint_so_the_expected_number_is_never_zero():
    first = trend.check(recent=3, history=0, days_of_history=180)
    assert first.expected == pytest.approx(30 / 180)
    assert first.result == trend.SIGNIFICANT  # 3 in a month after none in six is a real change
    assert trend.check(recent=3, history=0, days_of_history=60).expected == pytest.approx(0.5)


def test_the_sentence_says_what_was_compared():
    text = trend.sentence("Pump Rev B", trend.check(recent=6, history=6, days_of_history=180))
    assert text.startswith(
        "Pump Rev B: 6 complaints in the last 30 days against 1.0 expected from the previous 180 days"
    )
    assert "chance of at least this many if nothing changed" in text
    assert "too few" in trend.sentence("X", trend.check(2, 5, 180))
    assert "not compared" in trend.sentence("X", trend.check(5, 5, 30))
