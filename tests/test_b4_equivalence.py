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

import pytest

from backend.app.decision_guides import rules as guides
from backend.app.reportability import legacy_v1, markets
from backend.app.rule_register import engine, register

THREE = ("YES", "NO", "UNKNOWN")
FIVE = ("YES", "NO", "UNKNOWN", "NOT_APPLICABLE", None)


def _same(market: str, given: dict) -> None:
    answers = {key: {"answer": value} for key, value in given.items() if value is not None}
    content = register.floor(market)["content"]
    old = json.dumps(legacy_v1.evaluate(market, answers), sort_keys=True)
    new = json.dumps(engine.evaluate(content, answers), sort_keys=True)
    assert new == old, f"{market} {given}"


def _ids(market: str) -> list[str]:
    return [question["id"] for question in register.floor(market)["content"]["question_set"]["questions"]]


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
