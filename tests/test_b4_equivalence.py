"""B4 step 4, the core proof (spec 5.3, DT-37, RR-01): version 1 of every floor, read by the rule engine, gives exactly
what today's hand-written code gives (``reportability/legacy_v1.py``, frozen), for every case, compared after
``json.dumps(..., sort_keys=True)``. No database.

The exhaustive EU/NI and GB runs (3^11 = 177,147 combinations each) and the 200,000 random five-valued combinations
are marked ``slow``; they ran once for the build (time in the B4 spec's build status).
"""

from __future__ import annotations

import itertools
import json
import random
from datetime import date, datetime, timedelta, timezone


import pytest

from backend.app import feature_set
from backend.app.decision_guides import rules as guides
from backend.app.intake import rules as intake
from backend.app.oversight.rules import zone_info
from backend.app.reportability import deadlines, legacy_v1, markets
from backend.app.rule_register import engine, register

THREE = ("YES", "NO", "UNKNOWN")
FIVE = ("YES", "NO", "UNKNOWN", "NOT_APPLICABLE", None)


# B6b B3: the scenarios this file verifies (requirements.csv, class A); file level, so every test here carries them.
pytestmark = pytest.mark.requirement("DT-33", "DT-37", "RR-01", "RR-03")


def _same(market: str, given: dict) -> None:
    answers = {key: {"answer": value} for key, value in given.items() if value is not None}
    content = _first(market)["content"]  # the oracle is valid for version 1 only (B4); B9 corrects IN and CA
    old = json.dumps(legacy_v1.evaluate(market, answers), sort_keys=True)
    new = json.dumps(engine.evaluate(content, answers), sort_keys=True)
    assert new == old, f"{market} {given}"


def _ids(market: str) -> list[str]:
    return [question["id"] for question in _first(market)["content"]["question_set"]["questions"]]


def _first(market: str) -> dict:
    return register.get(f"{register.FLOOR_RULES[market]}-1")


def _every(market: str, values) -> int:
    ids = _ids(market)
    count = 0
    for combination in itertools.product(values, repeat=len(ids)):
        _same(market, dict(zip(ids, combination)))
        count += 1
    return count


@pytest.mark.parametrize(("market", "cases"), [("US", 6561), ("IN", 6561), ("CA", 729)])
def test_every_yes_no_unknown_combination_us_india_canada(market, cases):
    assert _every(market, THREE) == cases


@pytest.mark.slow
@pytest.mark.parametrize("market", ["EU_NI", "GB"])
def test_every_yes_no_unknown_combination_eu_and_gb(market):
    assert _every(market, THREE) == 3**11


def test_every_five_valued_combination_canada():
    """Yes, No, Unknown, Not applicable and blank: 5^6."""
    assert _every("CA", FIVE) == 15_625


@pytest.mark.slow
@pytest.mark.parametrize("market", ["US", "EU_NI", "GB", "IN"])
def test_two_hundred_thousand_random_five_valued_combinations(market):
    rng = random.Random(f"b4-{market}")
    ids = _ids(market)
    for _ in range(200_000):
        _same(market, {question: rng.choice(FIVE) for question in ids})


@pytest.mark.parametrize("market", markets.MARKETS)
def test_every_mdarix_starter_test_row(market):
    for row in guides.starter_tests(market):
        _same(market, row["answers"])
        found = engine.evaluate(
            register.floor(market)["content"], {k: {"answer": v} for k, v in row["answers"].items()}
        )
        assert found["suggested"] == row["expected"], row["name"]


def test_a_quick_sample_of_eu_and_gb_runs_in_every_selection():
    """A fixed-seed 5,000 of the exhaustive EU/GB cases, so a run without ``slow`` still covers both markets."""
    rng = random.Random("b4-quick")
    for market in ("EU_NI", "GB"):
        ids = _ids(market)
        for _ in range(5_000):
            _same(market, {question: rng.choice(FIVE) for question in ids})


# ------------------------------------------------------------------- step 5: what the rest of the code reads


def _switch(monkeypatch, on: bool) -> None:
    monkeypatch.setenv("MDARIX_RULE_REGISTER", "on" if on else "off")


def _both(monkeypatch, run):
    """``run()`` with the register on and off, as canonical JSON."""
    found = []
    for on in (True, False):
        _switch(monkeypatch, on)
        found.append(json.dumps(run(), sort_keys=True, default=str))
    return found


@pytest.mark.parametrize("market", markets.MARKETS)
def test_question_sets_and_report_types_are_identical(market, monkeypatch):
    """Item 4: the question set (as the screens show it) and the report types of each market."""
    on, off = _both(monkeypatch, lambda: markets.QUESTION_SETS[market].as_dict())
    assert on == off
    assert markets.QUESTION_SETS[market] == markets.V1_QUESTION_SETS[market]
    on, off = _both(monkeypatch, lambda: {code: vars(kind) for code, kind in markets.REPORT_TYPES.items()})
    on, off = json.loads(on), json.loads(off)
    if feature_set.switched_on("MDARIX_B9_INDIA"):  # B9: IN-floor-2 gives India's report its 15 days, nothing else
        assert on.pop("IN_SERIOUS_ADVERSE_EVENT")["days"] == 15 and off.pop("IN_SERIOUS_ADVERSE_EVENT")["days"] is None
    if feature_set.switched_on("MDARIX_B9_CANADA"):  # B9: CA-floor-2 gives the foreign report its day, nothing else
        assert on.pop("CA_FOREIGN")["days"] == 1 and off.pop("CA_FOREIGN")["days"] is None
    for role_type in ("US_IMP_30_DAY", "US_UF_10_WORK_DAY"):  # B9: the role floors' own types, on only
        on.pop(role_type, None)
    assert on == off and len(on) in (10, 11, 12)  # less the types B9 corrects (India, Canada) while on
    # Version 1 of every floor, India included, explicitly (the oracle is valid for version 1 only).
    first = tuple(f"{rule}-1" for rule in register.FLOOR_RULES.values())
    v1 = {code: vars(kind) for code, kind in markets._in_force(str(register._DIRECTORY), first)[1].items()}
    assert v1 == {code: vars(kind) for code, kind in markets.V1_REPORT_TYPES.items()} and len(v1) == 12


def test_prefill_and_record_notes_for_every_record_combination(monkeypatch):
    """Item 5: death, malfunction and serious injury each True, False or None; three severities; every market."""
    cases = 0
    for market in markets.MARKETS:
        question_set = markets.V1_QUESTION_SETS[market]
        for death, malfunction, injury in itertools.product((True, False, None), repeat=3):
            for severity in (None, "Serious", "  minor   harm "):
                record = {"death": death, "malfunction": malfunction, "serious_injury": injury, "severity": severity}
                on, off = _both(
                    monkeypatch,
                    lambda: [markets.suggestions(question_set, record), markets.record_notes(question_set, record)],
                )
                assert on == off, (market, record)
                cases += 1
    assert cases == 5 * 27 * 3


ZONES = ("UTC", "Asia/Kolkata", "America/New_York", "Europe/London", "Australia/Sydney")
DAYS = (2, 5, 10, 15, 30)


def _transitions() -> list[datetime]:
    """Every daylight-saving change of 2026-2028 in the authority and organization zones (to the hour)."""
    found = set()
    for zone in {*ZONES, "Europe/Brussels"}:
        info = zone_info(zone)
        moment = datetime(2026, 1, 1, tzinfo=timezone.utc)
        offset = moment.astimezone(info).utcoffset()
        while moment.year < 2029:
            later = moment + timedelta(hours=1)
            if later.astimezone(info).utcoffset() != offset:
                found.add(later)
                offset = later.astimezone(info).utcoffset()
            moment = later
    return sorted(found)


def _deadline_cases(count: int) -> list[tuple]:
    rng = random.Random("b4-deadlines")
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    cases = [
        (
            start + timedelta(minutes=rng.randrange(3 * 366 * 24 * 60)),
            rng.choice((*markets.MARKETS, None)),
            rng.choice(ZONES),
            rng.choice(DAYS),
            rng.choice((deadlines.WORK, "CALENDAR")),
        )
        for _ in range(count)
    ]
    for change in _transitions():
        for minutes in range(-120, 121, 30):
            for market in markets.MARKETS:
                for zone in ZONES:
                    cases.append((change + timedelta(minutes=minutes), market, zone, 2, "CALENDAR"))
    # Day-only awareness (12:00 UTC) and a plain day.
    cases += [
        (datetime(2027, 3, 1, 12, tzinfo=timezone.utc), m, z, 5, deadlines.WORK) for m in markets.MARKETS for z in ZONES
    ]
    cases += [(date(2027, 3, 1), m, z, 10, "CALENDAR") for m in markets.MARKETS for z in ZONES]
    return cases


def _deadline_results(cases) -> list:
    return [
        (found.day, found.at, found.zone)
        for found in (deadlines.count(aware, days, basis, market, zone) for aware, market, zone, days, basis in cases)
    ]


@pytest.mark.slow
def test_deadlines_one_hundred_thousand_moments_and_every_daylight_saving_change(monkeypatch):
    """Item 6 (RG-11, RR-14): identical latest day, end and binding zone."""
    cases = _deadline_cases(100_000)
    _switch(monkeypatch, True)
    on = _deadline_results(cases)
    _switch(monkeypatch, False)
    assert on == _deadline_results(cases)


def test_deadlines_a_quick_sample_and_every_daylight_saving_change(monkeypatch):
    cases = _deadline_cases(2_000)
    _switch(monkeypatch, True)
    on = _deadline_results(cases)
    _switch(monkeypatch, False)
    assert on == _deadline_results(cases)


def test_triage_provisional_deadlines_every_market_tier_remedial_answered_and_ivd(monkeypatch):
    """Item 7."""
    aware = datetime(2026, 11, 6, 22, 30, tzinfo=timezone.utc)
    cases = 0
    for level in intake.TIER_LABELS:
        for remedial, answered, ivd in itertools.product((True, False), repeat=3):
            for own in (*markets.MARKETS, None):
                on, off = _both(
                    monkeypatch,
                    lambda: intake.provisional_deadlines(
                        aware,
                        list(markets.MARKETS),
                        level,
                        aware,
                        remedial,
                        own=own,
                        org_zone="Asia/Kolkata",
                        ivd=ivd,
                        answered=answered,
                    ),
                )
                assert on == off, (level, remedial, answered, ivd, own)
                cases += 1
    assert cases == 3 * 8 * 6
