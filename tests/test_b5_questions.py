"""B5 step 4: question rules C-1 to C-9, version 1 (pure). Each rule fires and does not; the material flag; material
questions block submit until answered."""

from __future__ import annotations

import pytest

from backend.app.case_challenge import questions as q
from backend.app.case_challenge import rules
from tests.test_b5_draft_rules import CHANGE, _complaint, _facts, _lot

pytestmark = pytest.mark.unit


def _hyp(n, status="PARTIALLY_SUPPORTED", statement="Something else.", contradicting=0, supporting=1):
    return {
        "id": f"h{n}",
        "business_id": f"HYP-{n:02d}",
        "statement": statement,
        "human_status": status,
        "human_status_label": status.replace("_", " ").capitalize() if status else None,
        "ai_status": None,
        "draft_rule": None,
        "supporting_count": supporting,
        "contradicting_count": contradicting,
    }


def _asked(facts):
    return q.questions(facts, rules.drafts(facts))


def _rules(asked):
    return [item["rule"] for item in asked]


LOTS = [_lot(1, made=60, genealogy=["kB"]), _lot(2, made=60), _lot(3, made=60)]
GOOD = [_complaint(n, lot=f"l{n % 3 + 1}", days_ago=10 + n) for n in range(1, 7)]
REV_A = [_complaint(20, version="vA", days_ago=30)]


def test_c1_and_c3_on_a_leading_hypothesis_naming_the_change():
    lead = _hyp(1, statement="The CHG-014 sensor reads high.")
    early = [*GOOD, _complaint(9, lot="l1", days_ago=55)]
    asked = _asked(_facts(early, LOTS, [CHANGE], hypotheses=[lead, _hyp(2, status="WEAKLY_SUPPORTED")], outside=REV_A))
    (c1,) = [item for item in asked if item["rule"] == "C-1"]
    assert c1["material"] and "Rev A" in c1["text"] and "HYP-01" in c1["text"]
    (c3,) = [item for item in asked if item["rule"] == "C-3"]
    assert c3["material"] and c3["text"].startswith("1 complaint happened before CHG-014")
    # A contradiction already linked to the leading hypothesis: no C-1.
    linked = {**lead, "contradicting_count": 1}
    assert "C-1" not in _rules(_asked(_facts(early, LOTS, [CHANGE], hypotheses=[linked, _hyp(2)], outside=REV_A)))
    # No hypothesis names the change: it is not suspected, so no C-3.
    assert "C-3" not in _rules(_asked(_facts(early, LOTS, [CHANGE], hypotheses=[_hyp(1), _hyp(2)])))


def test_c2_only_one_explanation():
    assert "C-2" in _rules(_asked(_facts(GOOD, LOTS, hypotheses=[_hyp(1)])))
    assert "C-2" not in _rules(_asked(_facts(GOOD, LOTS, hypotheses=[_hyp(1), _hyp(2)])))
    retired = _hyp(2, status="RETIRED")
    assert "C-2" in _rules(_asked(_facts(GOOD, LOTS, hypotheses=[_hyp(1), retired])))


@pytest.mark.parametrize("gaps,material", [(1, False), (2, True)])
def test_c4_material_above_twenty_percent(gaps, material):
    complaints = [_complaint(n, lot=None if n <= gaps else "l1", days_ago=10 + n) for n in range(1, 8)]
    (c4,) = [item for item in _asked(_facts(complaints, LOTS)) if item["rule"] == "C-4"]
    assert c4["material"] is material  # 1 of 7 is 14%, 2 of 7 is 29%


def test_c4_absent_when_versions_lots_and_units_are_known():
    assert "C-4" not in _rules(_asked(_facts(GOOD, LOTS)))


def test_c5_open_question_on_the_leading_hypothesis_only():
    facts = _facts(GOOD, LOTS, hypotheses=[_hyp(1), _hyp(2, status="WEAKLY_SUPPORTED")])
    facts["unknowns"] = [
        {"id": "u1", "ref": "UNK-1", "hypothesis_id": "h1", "open": True, "description": "Bench test?"},
        {"id": "u2", "ref": "UNK-2", "hypothesis_id": "h2", "open": True, "description": "Settings?"},
        {"id": "u3", "ref": "UNK-3", "hypothesis_id": "h1", "open": False, "description": "Done."},
    ]
    c5 = [item for item in _asked(facts) if item["rule"] == "C-5"]
    assert [item["key"] for item in c5] == ["C-5:u1"] and c5[0]["material"]


def test_c6_supplier_statement_only():
    facts = _facts(GOOD, LOTS, hypotheses=[_hyp(1), _hyp(2)])
    supplier = {"hypothesis_id": "h1", "relation": "support", "evidence_id": "e1", "ref": "EV-1"}
    facts["links"] = [{**supplier, "evidence_type": "supplier_statement", "source_reference": None}]
    (c6,) = [item for item in _asked(facts) if item["rule"] == "C-6"]
    assert not c6["material"]
    facts["links"].append({**supplier, "evidence_id": "e2", "evidence_type": "bench_test", "source_reference": "Lab"})
    assert "C-6" not in _rules(_asked(facts))


def test_c7_same_problem_outside_the_scope():
    (c7,) = [item for item in _asked(_facts(GOOD, LOTS, outside=REV_A)) if item["rule"] == "C-7"]
    assert c7["text"].startswith("Rev A also has 1 complaint") and not c7["material"]
    assert "C-7" not in _rules(_asked(_facts(GOOD, LOTS)))


def test_c8_small_numbers_or_units_unknown():
    assert "C-8" in _rules(_asked(_facts(GOOD[:4], LOTS)))
    assert "C-8" not in _rules(_asked(_facts(GOOD, LOTS)))
    unknown_units = [_lot(1, units=None, made=60), _lot(2, made=60), _lot(3, made=60)]
    assert "C-8" in _rules(_asked(_facts(GOOD, unknown_units)))


def test_c9_strong_words_unless_strongly_supported():
    facts = _facts(GOOD, LOTS, hypotheses=[_hyp(1), _hyp(2)])
    facts["conclusion"] = "The sensor is confirmed as the cause."
    (c9,) = [item for item in _asked(facts) if item["rule"] == "C-9"]
    assert "'confirmed'" in c9["text"] and "partially supported" in c9["text"] and not c9["material"]
    facts["hypotheses"][0]["human_status"] = "STRONGLY_SUPPORTED"
    assert "C-9" not in _rules(_asked(facts))


def test_material_questions_block_until_answered():
    asked = _asked(_facts(GOOD, LOTS, hypotheses=[_hyp(1)]))
    assert [item["rule"] for item in q.blocking(asked, {})] == ["C-2"]
    assert q.blocking(asked, {"C-2:h1": {"text": "short"}})  # under ten characters does not stand
    assert not q.blocking(asked, {"C-2:h1": {"text": "A ward setting; the lot data speaks against it."}})
    assert all(item["label"] == f"Question from rule {item['rule']} v1" for item in asked)
