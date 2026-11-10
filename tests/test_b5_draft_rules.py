"""B5 step 3: draft rules H-0 to H-5, version 1 (pure). Each condition at its boundary, IV-14 timing, duplicates
noted, and no draft carries a score, rank or probability."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

import pytest

from backend.app.case_challenge import rules

pytestmark = pytest.mark.unit

AS_OF = datetime(2026, 11, 1, tzinfo=timezone.utc)
TODAY = AS_OF.date()


def _day(days_ago: int) -> date:
    return TODAY - timedelta(days=days_ago)


def _complaint(n, version="vB", lot=None, days_ago=10, code=None, country=None, problem="ALARM"):
    return {
        "id": f"c{n}",
        "ref": f"CMP-{n:03d}",
        "version_id": version,
        "lot_id": lot,
        "problem": problem,
        "event_on": _day(days_ago),
        "harm": False,
        "country": country,
        "returned": None,
        "service_status": None,
        "code_class": code,
        "origin": "MDARIX",
    }


def _lot(n, version="vB", units=100, made=200, genealogy=()):
    return {
        "id": f"l{n}",
        "ref": f"LOT-{n:03d}",
        "version_id": version,
        "released": _day(made),
        "units_released": units,
        "units_shipped": None,
        "genealogy": list(genealogy),
    }


def _facts(complaints, lots=(), changes=(), hypotheses=(), outside=(), versions=None, pattern=None):
    versions = versions or {
        "vA": {
            "id": "vA",
            "ref": "Rev A",
            "released": _day(400),
            "predecessor_id": None,
            "in_scope": False,
            "components": ["kA"],
        },
        "vB": {
            "id": "vB",
            "ref": "Rev B",
            "released": _day(300),
            "predecessor_id": "vA",
            "in_scope": True,
            "components": ["kB"],
        },
    }
    return {
        "as_of": AS_OF,
        "scope_version": 1,
        "complaints": list(complaints),
        "outside": list(outside),
        "versions": versions,
        "components": {
            "kA": {"id": "kA", "ref": "C-A", "name": "Sensor A", "suppliers": [{"id": "sA", "name": "Precision"}]},
            "kB": {"id": "kB", "ref": "C-B", "name": "Sensor B", "suppliers": [{"id": "sB", "name": "Nova"}]},
        },
        "lots": {lot["id"]: lot for lot in lots},
        "changes": list(changes),
        "pattern": pattern,
        "entity_evidence": {},
        "hypotheses": list(hypotheses),
        "links": [],
        "unknowns": [],
        "conclusion": None,
    }


CHANGE = {
    "id": "ch1",
    "ref": "CHG-014",
    "kind": "Supplier change",
    "title": "Sensor from Nova",
    "effective_on": _day(50),
    "component_ids": ["kB"],
    "whole_product": False,
    "version_ids": ["vB"],
}


def _rules_of(facts):
    return [item["rule"] for item in rules.drafts(facts)]


def test_h0_when_too_few_complaints_or_none_has_version_or_lot():
    assert _rules_of(_facts([_complaint(1), _complaint(2)])) == ["H-0"]
    blind = [_complaint(n, version=None, lot=None) for n in range(1, 5)]
    (draft,) = rules.drafts(_facts(blind))
    assert draft["rule"] == "H-0" and any("Version unknown on 4" in item["text"] for item in draft["missing"])
    assert _rules_of(_facts([_complaint(n) for n in range(1, 4)])) == []  # testable, nothing fires


def test_h1_fires_on_a_change_before_a_complaint_and_counts_earlier_ones_against_it():
    lots = [_lot(1, units=100, made=60, genealogy=["kB"]), _lot(2, units=100, made=200)]
    complaints = [
        _complaint(1, lot="l1", days_ago=50),
        _complaint(2, lot="l1", days_ago=20),
        _complaint(3, lot="l2", days_ago=80),
    ]
    rev_a = [_complaint(9, version="vA", days_ago=30)]
    (draft,) = [d for d in rules.drafts(_facts(complaints, lots, [CHANGE], outside=rev_a)) if d["rule"] == "H-1"]
    # The complaint on the effective day counts after the change.
    assert "after: 2 complaints" in draft["for"][0]["text"]
    assert any("built with the changed part" in item["text"] for item in draft["for"])
    against = " ".join(item["text"] for item in draft["against"])
    assert "1 complaint with the same problem on Rev A" in against and "Precision" in against
    # IV-14: the complaint 80 days ago came before the change: against it, never for it.
    assert "1 scope complaint happened before CHG-014" in against
    assert all("c3" not in [r["id"] for r in item["records"]] for item in draft["for"])
    assert any("Genealogy" in item["text"] for item in draft["missing"])
    assert any("No inspection or other evidence" in item["text"] for item in draft["missing"])
    assert draft["label"] == "Drafted by rule H-1 v1 from your records. Not a finding."


def test_h1_does_not_fire_when_every_complaint_came_before_the_change():
    complaints = [_complaint(n, lot="l1", days_ago=60 + n) for n in range(1, 4)]
    assert "H-1" not in _rules_of(_facts(complaints, [_lot(1)], [CHANGE]))


@pytest.mark.parametrize("top_units,fires", [(400, True), (401, False)])
def test_h2_sixty_percent_of_complaints_in_at_most_forty_percent_of_units(top_units, fires):
    lots = [_lot(1, units=top_units), _lot(2, units=1000 - top_units)]
    complaints = [_complaint(n, lot="l1") for n in range(1, 4)] + [_complaint(n, lot="l2") for n in range(4, 6)]
    assert ("H-2" in _rules_of(_facts(complaints, lots))) is fires


@pytest.mark.parametrize("lot_count,fires", [(3, True), (2, False)])
def test_h2_with_units_unknown_uses_a_third_of_the_lots(lot_count, fires):
    lots = [_lot(n, units=None) for n in range(1, lot_count + 1)]
    complaints = [_complaint(n, lot="l1") for n in range(1, 4)] + [_complaint(n, lot="l2") for n in range(4, 6)]
    found = [d for d in rules.drafts(_facts(complaints, lots)) if d["rule"] == "H-2"]
    assert bool(found) is fires
    if found:
        assert any("Units unknown for" in item["text"] for item in found[0]["missing"])


def test_h3_needs_a_higher_rate_spread_over_lots():
    lots = [_lot(1, made=250), _lot(2, made=250), _lot(3, version="vA", made=390)]
    spread = [_complaint(n, lot="l1" if n % 2 else "l2") for n in range(1, 7)]
    assert "H-3" in _rules_of(_facts(spread, lots, outside=[_complaint(20, version="vA", lot="l3")]))
    concentrated = [_complaint(n, lot="l1") for n in range(1, 6)] + [_complaint(6, lot="l2")]
    assert "H-3" not in _rules_of(_facts(concentrated, lots))


@pytest.mark.parametrize("coded,fires", [(1, True), (0, False)])
def test_h4_a_third_coded_no_fault_found_or_user_error(coded, fires):
    complaints = [
        _complaint(1, lot="l1", code="NO_FAULT_FOUND" if coded else None),
        _complaint(2, lot="l2"),
        _complaint(3, lot="l3"),
    ]
    lots = [_lot(1), _lot(2), _lot(3)]
    assert ("H-4" in _rules_of(_facts(complaints, lots))) is fires


def test_h4_on_a_country_cluster_without_a_lot_cluster():
    lots = [_lot(n) for n in range(1, 4)]
    complaints = [_complaint(n, lot=f"l{n % 3 + 1}", country="DE" if n < 5 else "FR") for n in range(1, 7)]
    assert "H-4" in _rules_of(_facts(complaints, lots))


def test_h5_follows_the_supplier_pattern():
    pattern = {
        "found": True,
        "window_days": 90,
        "supplier": "Nova",
        "supplier_id": "sB",
        "versions": [
            {
                "version_id": "vB",
                "product": "Pump",
                "version": "Rev B",
                "recent": 3,
                "per_1000": 2.0,
                "units_unknown_lots": 0,
            },
            {
                "version_id": "vX",
                "product": "Monitor",
                "version": "Rev 2",
                "recent": 2,
                "per_1000": None,
                "units_unknown_lots": 1,
            },
        ],
        "part_versions": [
            {"id": "vB", "ref": "Rev B", "product": "Pump"},
            {"id": "vY", "ref": "Rev 3", "product": "Monitor"},
        ],
    }
    complaints = [_complaint(n, lot="l1") for n in range(1, 4)]
    (draft,) = [d for d in rules.drafts(_facts(complaints, [_lot(1)], pattern=pattern)) if d["rule"] == "H-5"]
    assert len(draft["for"]) == 2 and "1 version with Nova parts" in draft["against"][0]["text"]
    assert draft["missing"] and "Units unknown for 1 lot" in draft["missing"][0]["text"]


def test_duplicates_are_noted_never_merged_and_no_draft_is_scored():
    lots = [_lot(1, made=60)]
    complaints = [_complaint(n, lot="l1", days_ago=10 + n) for n in range(1, 4)]
    mine = {
        "id": "h1",
        "business_id": "HYP-12",
        "statement": "The CHG-014 sensors read high.",
        "human_status": "PARTIALLY_SUPPORTED",
        "draft_rule": None,
    }
    found = rules.drafts(_facts(complaints, lots, [CHANGE], hypotheses=[mine]))
    (draft,) = [d for d in found if d["rule"] == "H-1"]
    assert draft["duplicate_of"] == "HYP-12"
    forbidden = {"score", "rank", "probability", "confidence", "likelihood"}
    assert all(not (forbidden & set(item)) for item in found)
    # Every fact cites its records or says what is missing; rule order only.
    order = [item["rule"] for item in found]
    assert order == sorted(order)
