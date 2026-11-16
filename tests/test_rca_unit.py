"""RCA tools rules without a database: the Pareto of confirmed causes, the signing checks and the payloads."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from pydantic import ValidationError

from backend.app.rca import pareto, rules

pytestmark = pytest.mark.unit


def _decision(category, day, attribution="DEVICE_RELATED", case="C1"):
    return {
        "decision_id": f"D-{category}-{day}",
        "decision_business_id": f"DEC-{day}",
        "investigation_id": case,
        "decided_at": datetime(2026, 11, day, tzinfo=timezone.utc),
        "category": category,
        "attribution": attribution,
    }


def _row(number, decisions=(), disposition=None, **extra):
    return {
        "complaint": {"id": f"c{number}", "business_id": f"CMP-{number}"},
        "cause": pareto.current_cause(list(decisions), disposition),
        **extra,
    }


def test_each_complaint_counts_once_under_its_latest_decision():
    rows = [
        _row(1, [_decision("METHOD", 1), _decision("MATERIAL", 5, case="C2")]),
        _row(2, [_decision("MATERIAL", 3)]),
        _row(3, [_decision("MATERIAL", 3)]),
        _row(4, [_decision("PEOPLE", 2)]),
    ]
    result = pareto.build(rows)
    bars = {bar["label"]: bar["count"] for bar in result["bars"]}
    assert bars == {"Material": 3, "People": 1, "No confirmed cause yet": 0}
    assert result["total"] == 4 and sum(bars.values()) == 4
    assert [bar["label"] for bar in result["bars"]][0] == "Material"  # largest first
    assert result["bars"][-1]["cumulative_share"] == 100.0
    assert result["unit"] == "complaints" and "rate" not in str(result["bars"]).lower()


def test_disposition_fallback_not_categorised_and_no_cause_bar():
    rows = [
        _row(1, [_decision(None, 1)]),  # signed before RCA: never rewritten
        _row(2, disposition={"attribution": "USE_RELATED"}),
        _row(3, disposition=None),
        _row(4, disposition={"attribution": None}),
    ]
    bars = {bar["label"]: bar for bar in pareto.build(rows)["bars"]}
    assert bars["Not categorised"]["count"] == 1
    assert bars["Service level: Use-related"]["count"] == 1
    assert bars["No confirmed cause yet"]["count"] == 2 and bars["No confirmed cause yet"]["confirmed"] is False
    assert list(bars)[-1] == "No confirmed cause yet"


def test_the_no_cause_bar_is_always_shown_and_shares_sum_to_100():
    empty = pareto.build([])
    assert [bar["label"] for bar in empty["bars"]] == ["No confirmed cause yet"]
    rows = [_row(n, [_decision("MATERIAL", 1)]) for n in range(3)] + [_row(9)]
    bars = pareto.build(rows, "attribution")["bars"]
    assert bars[0]["label"] == "Device-related" and bars[0]["cumulative_share"] == 75.0
    assert bars[-1]["cumulative_share"] == 100.0
    by_product = pareto.build([_row(1, [_decision("MATERIAL", 1)], product="OrbitCare 300")], "product")
    assert by_product["bars"][0]["label"] == "OrbitCare 300"
    with pytest.raises(ValueError):
        pareto.build(rows, "colour")


def test_signing_checks():
    ids = [uuid.uuid4()]
    check = rules.root_cause_problem
    assert (
        "choose the cause category"
        in check(outcome="ACCEPT_CONCLUSION", category=None, reason=None, ticked=[], methods_on=True).lower()
    )
    assert check(outcome="CLOSE_NO_FURTHER_ACTION", category=None, reason=None, ticked=[], methods_on=True) is None
    assert "category of the causes" in check(
        outcome="CLOSE_NO_FURTHER_ACTION", category=None, reason=None, ticked=ids, methods_on=True
    )
    assert "Not determined" in check(
        outcome="ACCEPT_CONCLUSION", category="NOT_DETERMINED", reason="short", ticked=[], methods_on=True
    )
    assert "untick" in check(
        outcome="ACCEPT_CONCLUSION",
        category="NOT_DETERMINED",
        reason="A long enough reason",
        ticked=ids,
        methods_on=True,
    )
    assert check(outcome="ACCEPT_CONCLUSION", category="MATERIAL", reason=None, ticked=ids, methods_on=True) is None
    assert "once" in check(
        outcome="ACCEPT_CONCLUSION", category="MATERIAL", reason=None, ticked=ids * 2, methods_on=True
    )
    assert check(outcome="ACCEPT_CONCLUSION", category=None, reason=None, ticked=[], methods_on=False) is None
    assert "switched off" in check(
        outcome="ACCEPT_CONCLUSION", category="MATERIAL", reason=None, ticked=[], methods_on=False
    )


def test_payloads_refuse_claims_and_bad_counts():
    with pytest.raises(ValidationError):
        rules.CauseCreatePayload(statement="This is the root cause of it all", cause_category="MATERIAL")
    with pytest.raises(ValidationError):
        rules.CauseCreatePayload(statement="Proven root cause: sensor drift", cause_category="MATERIAL")
    with pytest.raises(ValidationError):
        rules.CauseCreatePayload(statement="Sensor drift in lot 3", cause_category="MEASUREMENT")
    assert rules.CauseCreatePayload(statement="Sensor drift in lot 3", cause_category="material").cause_category == (
        "MATERIAL"
    )
    for count in (1, 8):
        with pytest.raises(ValidationError):
            rules.FiveWhysPayload(problem="Alarms", whys=[{"text": "Why it was"}] * count)
    with pytest.raises(ValidationError):
        rules.FiveWhysPayload(problem="Alarms", whys=[{"text": "Why it was", "state": "SUPPORTED"}] * 2)
    assert len(rules.FiveWhysPayload(problem="Alarms", whys=[{"text": "Why it was"}] * 7).whys) == 7


def test_software_column_only_for_software_products():
    assert rules.shows_software("SOFTWARE", set()) and rules.shows_software(None, {"SOFTWARE"})
    assert not rules.shows_software("REUSABLE", {"MATERIAL"})
    assert (
        rules.category_label(None) == "Not categorised" and rules.category_label("NOT_DETERMINED") == "Not determined"
    )
