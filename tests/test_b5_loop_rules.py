"""B5 step 8: the closed-loop statistics (backend/app/closed_loop/rules.py), at the boundaries of spec 3.4: 89 vs 90
days, expected 4.9 vs 5, p exactly 0.05, all units unknown, one lot unknown, the zero-after bound, BH, no verdicts."""

from __future__ import annotations

from datetime import date

import pytest

from backend.app.closed_loop import rules

pytestmark = pytest.mark.unit

ACTION = date(2026, 1, 1)


def _lot(released=date(2025, 1, 1), units=1000, shipments=None):
    return {"released_on": released, "units": units, "shipments": shipments or []}


def test_windows_are_equal_and_too_early_under_90_days():
    window = rules.windows(ACTION, date(2026, 3, 31))  # 1 Jan .. 31 Mar: 90 days
    assert window["after_days"] == 90 and window["days"] == 90
    assert window["before"] == (date(2025, 10, 3), date(2025, 12, 31))
    assert rules.windows(ACTION, date(2026, 3, 30))["after_days"] == 89
    assert rules.word(89, 50, 0.001, None) == rules.TOO_EARLY
    assert rules.word(90, 50, 0.001, None) == rules.FEWER
    # At most 365 days; a field action settles 30 days first.
    assert rules.windows(ACTION, date(2028, 1, 1))["after_days"] == 365
    settled = rules.windows(ACTION, date(2026, 6, 30), rules.SETTLING_DAYS["FIELD_ACTION"])
    assert settled["after"][0] == date(2026, 1, 31) and settled["before"][1] == date(2025, 12, 31)


def test_too_few_below_an_expected_five_and_the_p_limit_is_inclusive():
    assert rules.word(120, 4.9, 0.0001, None) == rules.TOO_FEW
    assert rules.word(120, 5.0, 0.0001, None) == rules.FEWER
    assert rules.word(120, 5.0, 0.05, 0.97) == rules.FEWER
    assert rules.word(120, 5.0, 0.0500001, 0.05) == rules.MORE
    assert rules.word(120, 5.0, 0.2, 0.8) == rules.NO_CHANGE


def test_denominator_order_shipped_then_released_then_unknown_never_partial():
    start, end = date(2025, 1, 1), date(2025, 1, 10)
    shipped = rules.exposure([_lot(shipments=[(date(2025, 1, 6), 100)])], start, end)
    assert shipped == {"basis": rules.SHIPPED, "unit_days": 500.0, "unknown_lots": 0, "lots": 1}
    # One lot without shipments: units released for all lots (never a mix).
    mixed = rules.exposure([_lot(shipments=[(date(2025, 1, 6), 100)]), _lot(units=10)], start, end)
    assert mixed["basis"] == rules.RELEASED and mixed["unit_days"] == 10_100.0
    # One lot with units unknown: the whole group is "units unknown".
    unknown = rules.exposure([_lot(), _lot(units=None)], start, end)
    assert unknown == {"basis": rules.UNKNOWN, "unit_days": None, "unknown_lots": 1, "lots": 2}
    assert rules.exposure([], start, end)["basis"] == rules.UNKNOWN


def test_units_unknown_gives_counts_only_by_calendar_days_and_no_rate():
    window = rules.windows(ACTION, date(2026, 6, 30))
    unknown = {"basis": rules.UNKNOWN, "unit_days": None, "unknown_lots": 1, "lots": 3}
    known = {"basis": rules.RELEASED, "unit_days": 1e6, "unknown_lots": 0, "lots": 3}
    found = rules.compare(20, 4, window, unknown, known)
    assert found["counts_only"] and found["rate_before"] is None and found["rate_after"] is None
    assert found["word"].endswith("(by calendar days)") and found["per_30_days_before"] > found["per_30_days_after"]
    assert found["result"] == rules.FEWER and found["unknown_lots"] == 1


def test_the_conditional_test_and_the_rate_per_thousand_unit_months():
    window = rules.windows(ACTION, date(2026, 6, 30))
    same = {"basis": rules.RELEASED, "unit_days": 300_000.0, "unknown_lots": 0, "lots": 2}
    found = rules.compare(30, 10, window, same, same)
    assert found["expected_after"] == 20.0 and found["result"] == rules.FEWER
    assert found["rate_before"] == 3.0 and found["rate_after"] == 1.0
    more = rules.compare(10, 30, window, same, same)
    assert more["result"] == rules.MORE and more["p_more"] < 0.05
    steady = rules.compare(20, 20, window, same, same)
    assert steady["result"] == rules.NO_CHANGE
    lower, upper = rules.binomial_tails(5, 10, 0.5)
    assert lower == pytest.approx(0.623046875) and upper == pytest.approx(0.623046875)
    big_lower, _ = rules.binomial_tails(0, 5000, 0.5)  # log space: no underflow error
    assert 0 <= big_lower < 1e-300 or big_lower == 0.0


def test_zero_after_states_an_upper_bound_never_eliminated():
    window = rules.windows(ACTION, date(2026, 6, 30))
    same = {"basis": rules.SHIPPED, "unit_days": 300_000.0, "unknown_lots": 0, "lots": 2}
    found = rules.compare(12, 0, window, same, same)
    assert found["upper_bound_after"] == pytest.approx(2.9957 / 10_000 * 1000, rel=1e-3)
    words = " ".join(rules.WORDS.values()) + rules.NOTICE + " ".join(rules.LIMITS)
    assert "eliminated" not in words.lower() and "confirmed" not in words.lower()
    assert "effective" not in " ".join(rules.WORDS.values()).lower()


def test_benjamini_hochberg_across_the_groups_of_one_view():
    window = rules.windows(ACTION, date(2026, 6, 30))
    same = {"basis": rules.RELEASED, "unit_days": 300_000.0, "unknown_lots": 0, "lots": 1}
    rows = [rules.compare(b, a, window, same, same) for b, a in ((18, 8), (20, 20), (20, 20), (1, 1))]
    assert rows[0]["result"] == rules.FEWER and rows[3]["result"] == rules.TOO_FEW
    adjusted = rules.adjust(rows)
    assert adjusted[0]["p_fewer_adjusted"] == pytest.approx(min(1.0, rows[0]["p_fewer"] * 3))
    assert adjusted[0]["result"] == rules.NO_CHANGE  # the raw "fewer" does not survive three groups
    assert adjusted[3] == rows[3]
