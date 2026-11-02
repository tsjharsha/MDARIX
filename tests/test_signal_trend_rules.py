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


# ------------------------------------------------------------------------------------- units and new versions (md43)


def test_unit_days_count_each_lot_from_its_release_for_its_quantity():
    from datetime import date

    start, end = date(2026, 1, 1), date(2026, 1, 30)
    # 100 units in the field all window long, 50 more from day 21 (10 days): 3000 + 500.
    lots = [(date(2025, 12, 1), 100), (date(2026, 1, 21), 50), (date(2026, 2, 5), 999)]
    assert trend.unit_days(lots, start, end) == 3500
    assert trend.unit_days([(date(2025, 12, 1), None)], start, end) is None  # a quantity not known: the calendar
    assert trend.unit_days([(None, 100)], start, end) is None
    assert trend.unit_days([], start, end) is None
    assert trend.unit_days([(date(2026, 3, 1), 100)], start, end) is None  # nothing in the field yet
    assert trend.unit_days(lots, end, start) is None


def test_a_scale_by_units_replaces_the_calendar():
    by_time = trend.check(recent=4, history=6, days_of_history=180)
    assert by_time.basis == trend.TIME and by_time.expected == pytest.approx(1.0)
    # The installed base doubled: twice the unit-days in the recent window per day, so twice the expected number.
    by_units = trend.check(recent=4, history=6, days_of_history=180, scale=2 * 30 / 180)
    assert by_units.basis == trend.UNITS and by_units.expected == pytest.approx(2.0)
    assert by_units.p_value > by_time.p_value
    assert by_units.as_dict()["basis"] == "UNITS"
    assert trend.sentence("Pump Rev B", by_units).endswith("Scaled by the units in the field (lot quantities).")
    assert "Scaled by" not in trend.sentence("Pump Rev B", by_time)


def test_a_new_version_is_compared_with_the_one_it_replaced():
    found = trend.check(
        recent=6, history=4, days_of_history=180, baseline=trend.PREVIOUS_VERSION, baseline_name="Pump Rev A"
    )
    assert found.result == trend.SIGNIFICANT
    shown = found.as_dict()
    assert shown["label"] == "Rate significantly higher than the previous version"
    assert shown["baseline"] == "PREVIOUS_VERSION" and shown["baseline_name"] == "Pump Rev A"
    text = trend.sentence("Pump Rev B", found)
    assert "expected from Pump Rev A over the 180 days before this version's release (4 complaints)" in text
    # Own history keeps its label and sentence exactly as before.
    own = trend.check(recent=6, history=6, days_of_history=180)
    assert own.as_dict()["label"] == "Rate significantly higher than its history"
    assert own.as_dict()["baseline"] == "OWN_HISTORY" and own.as_dict()["baseline_name"] is None


# ------------------------------------------------------------------------------------- 0.10.63: trend statistics


@pytest.mark.parametrize(
    "observed,expected,probability,rel",
    [
        (5, 0.7, 0.000785535, 1e-6),
        (3, 0.5, 0.0143877, 1e-5),
        (12, 4.0, 0.000915229, 1e-6),
        (60, 40.0, 0.00187963, 1e-5),
        (900, 800.0, 0.000275913, 1e-5),
        (1000, 760.0, 5.746e-17, 1e-3),
        (800, 746.0, 0.0260645, 1e-5),
    ],
)
def test_the_poisson_tail_keeps_exact_values_and_never_underflows(observed, expected, probability, rel):
    """S1: from exp(-expected) the tail was 1.0 for any count once the expected number passed ~745."""
    assert trend.poisson_tail(observed, expected) == pytest.approx(probability, rel=rel)


def test_a_large_rise_is_significant_however_many_complaints_are_expected():
    # 2,000 in 30 days against 800 expected (4,800 in 180 days) read "In line" before 0.10.63.
    found = trend.check(2000, 4800, 180)
    assert found.expected == pytest.approx(800.0)
    assert found.result == trend.SIGNIFICANT and found.p_value < 1e-100


def test_a_version_younger_than_the_window_is_expected_only_its_own_days():
    """S3: a version released 11 days ago (release day included) is expected 11 days of complaints, not 30."""
    young = trend.check(4, 18, 180, baseline=trend.PREVIOUS_VERSION, baseline_name="Pump Rev A", recent_days=11)
    assert young.expected == pytest.approx(18 * 11 / 180)
    assert young.result == trend.ELEVATED  # p 0.026; against 30 days (3.0 expected) it read "In line" (p 0.35)
    assert young.as_dict()["recent_days"] == 11
    assert "4 complaints in the 11 days since its release against 1.1 expected" in trend.sentence("Pump Rev B", young)
    assert trend.check(4, 18, 180, recent_days=99).recent_days == 30


def test_the_adjusted_value_allows_for_every_group_tested_at_once():
    """S4: Benjamini-Hochberg over the groups tested on one board; the label follows the adjusted value."""
    checks = [
        trend.check(5, 6, 180),  # p 0.0037: significant on its own
        trend.check(3, 6, 180),  # p 0.080
        trend.check(3, 6, 180),
        trend.check(3, 6, 180),
        trend.check(2, 6, 180),  # too few: not tested
    ]
    assert checks[0].result == trend.SIGNIFICANT
    adjusted = trend.adjust(checks)
    first = adjusted[0]
    assert first.groups_tested == 4 and first.p_value == checks[0].p_value
    assert first.p_adjusted == pytest.approx(checks[0].p_value * 4)
    assert first.result == trend.ELEVATED  # 0.0146: not significant once four groups are allowed for
    assert adjusted[1].p_adjusted == pytest.approx(min(1.0, checks[1].p_value * 4 / 4))
    assert adjusted[4] is checks[4] and adjusted[4].p_adjusted is None
    shown = first.as_dict()
    assert shown["p_value"] == round(checks[0].p_value, 4) and shown["p_adjusted"] == round(first.p_adjusted, 4)
    assert "allowing for the 4 groups assessed" in trend.sentence("Pump Rev B", first)
    # The textbook example: 0.01, 0.04, 0.03, 0.005 adjust to 0.02, 0.04, 0.04, 0.02.
    raw = [trend.Check(9, 1, 180, 1.0, p, 9.0, trend.STEADY) for p in (0.01, 0.04, 0.03, 0.005)]
    assert [item.p_adjusted for item in trend.adjust(raw)] == pytest.approx([0.02, 0.04, 0.04, 0.02])
    # One group alone: the adjusted value is the raw one.
    alone = trend.adjust([checks[0]])[0]
    assert alone.p_adjusted == alone.p_value and alone.result == trend.SIGNIFICANT
    assert "allowing for" not in trend.sentence("X", alone)


def test_a_lasting_rise_since_the_change_stays_visible_against_the_version_it_replaced():
    """J26: once a new version has its own history, its rise since release is in that history too; compared with both
    baselines, the stronger comparison is reported, saying which."""
    own = trend.check(6, 34, 170)  # 6 against 6.0 expected from its own (already high) history
    previous = trend.check(6, 6, 180, baseline=trend.PREVIOUS_VERSION, baseline_name="Pump Rev A")
    assert own.result == trend.STEADY and previous.result == trend.SIGNIFICANT
    found = trend.stronger(own, previous)
    assert found.baseline == trend.PREVIOUS_VERSION and found.result == trend.SIGNIFICANT
    assert found.also_compared == "its own history"
    assert "Also compared with its own history; the stronger comparison is shown." in trend.sentence("Rev B", found)
    # The other way round: own history is stronger and names the previous version.
    reverse = trend.stronger(
        trend.check(6, 6, 180), trend.check(6, 34, 170, baseline=trend.PREVIOUS_VERSION, baseline_name="Pump Rev A")
    )
    assert reverse.baseline == trend.OWN_HISTORY and reverse.also_compared == "Pump Rev A"
    # A version too young for its own history: the previous version, with nothing else to name.
    young = trend.stronger(trend.check(6, 2, 40), previous)
    assert young.baseline == trend.PREVIOUS_VERSION and young.also_compared is None
    assert trend.stronger(own, None) is own


def test_single_use_products_are_named_by_their_words():
    """J27: a single-use or consumable product's units are used up; the board counts it by calendar days."""
    assert trend.single_use("Infusion set, single-use")
    assert trend.single_use("GlucoCheck", "Diabetes care", "Blood glucose test strip, IVD")
    assert trend.single_use(None, "Disposable syringes")
    assert not trend.single_use(
        "OrbitCare 300 Infusion Pump (Sample)", "Infusion therapy", "General-purpose infusion pump"
    )
    assert not trend.single_use("PulseWatch 410 Patient Monitor (Sample)", "Patient monitoring", None)
    by_time = trend.check(6, 12, 180, basis_note=trend.SINGLE_USE_NOTE)
    assert by_time.basis == trend.TIME and by_time.as_dict()["basis_note"] == trend.SINGLE_USE_NOTE
    assert trend.sentence("Set Rev A", by_time).endswith(trend.SINGLE_USE_NOTE)


def test_a_tiny_chance_reads_under_0_001_not_0_000():
    # 0.10.63 review: the signal's trend line said "chance ... if nothing changed: 0.000" beside "p < 0.001".
    item = trend.check(9, 6, 180, scale=0.16)
    assert "if nothing changed: under 0.001" in trend.sentence("Rev B", item)
