"""B9b step 2: the generic floor for a country outside the five markets (OTHER-floor-1, decision B9b-N1).

Reportable when death, a serious deterioration, a serious public health threat, or a malfunction that could lead to
death or serious deterioration were it to happen again, is Yes; an Unknown that could make it reportable keeps it
pending (OC-03, floor F3); use error and "marketed in this country" are notes only and never change the outcome.
"""

from __future__ import annotations

import itertools

import pytest

from backend.app import standards
from backend.app.rule_register import engine, register

# B6b B3: the scenarios this file verifies (requirements.csv, class A); file level, so every test here carries them.
pytestmark = [pytest.mark.unit, pytest.mark.requirement("OC-03", "OC-04", "OC-09", "OC-12", "OC-19")]

QUESTIONS = ("OT1", "OT2", "OT3", "OT4", "OT5", "OT6", "OT7")
VALUES = ("YES", "NO", "UNKNOWN")
GENERIC = "Generic starter questions, not this country's law: confirm with your consultant."


def _content() -> dict:
    return register.get("OTHER-floor-1")["content"]


def _answers(values) -> dict:
    return {question: {"answer": value} for question, value in zip(QUESTIONS, values)}


def _expected(values) -> bool:
    found = dict(zip(QUESTIONS, values))
    return any(found[q] == "YES" for q in ("OT1", "OT2", "OT4")) or (found["OT5"] == found["OT3"] == "YES")


def test_the_floor_loads_with_its_hash_its_switch_and_a_starter_source():
    entry = register.get("OTHER-floor-1")
    assert (
        entry["market"] == "OTHER" and entry["kind"] == "REPORTABILITY_FLOOR" and entry["switch"] == "MDARIX_B9B_OTHER"
    )
    assert entry["content_hash"] == register.content_hash(entry["content"])
    assert [source["catalog"] for source in entry["source"]] == ["IMDRF_GHTF_COMMON"]
    assert standards.BY_ID["IMDRF_GHTF_COMMON"].starter
    assert [q["id"] for q in entry["content"]["question_set"]["questions"]] == list(QUESTIONS)
    # No legal period in MDARIX: the reporting window naming the country, or the date the customer enters.
    assert entry["content"]["report_types"]["OTHER_REPORT"]["days"] is None
    # No authority zone: the organization's, as Canada.
    assert entry["content"]["counting"]["authority_zone"] is None
    assert engine.check(entry["content"]) == []


def test_every_answer_set_follows_n1_and_unknown_never_gives_not_reportable():
    content, checked = _content(), 0
    for values in itertools.product(VALUES, repeat=len(QUESTIONS)):
        result = engine.evaluate(content, _answers(values))
        unknown = [i for i, value in enumerate(values) if value == "UNKNOWN"]
        completions = [
            _expected([fill[unknown.index(i)] if i in unknown else value for i, value in enumerate(values)])
            for fill in itertools.product(("YES", "NO"), repeat=len(unknown))
        ]
        if all(completions):
            assert result["suggested"] == engine.REPORTABLE, values
        elif any(completions):
            # OC-03: an Unknown that could make it reportable keeps it pending, never Not reportable.
            assert result["suggested"] == engine.PENDING, values
        else:
            assert result["suggested"] == engine.NOT_REPORTABLE, values
        assert GENERIC in result["notes"]
        checked += 1
    assert checked == 3**7


def test_use_error_and_marketed_never_change_the_outcome():
    content = _content()
    for values in itertools.product(VALUES, repeat=5):
        outcomes = {
            engine.evaluate(content, _answers((*values, use, marketed)))["suggested"]
            for use in VALUES
            for marketed in VALUES
        }
        assert len(outcomes) == 1, values


def test_notes_and_folding():
    content = _content()
    notes = engine.evaluate(content, _answers(("NO",) * 5 + ("YES", "NO")))["notes"]
    assert any("use error" in note for note in notes) and any("not marketed" in note for note in notes)
    assert engine.not_asked(content, _answers(("YES", "NO", "NO", "NO", "NO", "NO", "YES"))) == {
        "OT2": "Not needed: it led to a death",
        "OT3": "Not needed: no malfunction or deterioration of the device",
    }
    # An Unknown never folds a question away.
    assert engine.not_asked(content, _answers(("UNKNOWN",) * 7)) == {}


def test_the_switch_off_hides_the_floor_but_a_record_still_reads_it(monkeypatch):
    monkeypatch.setenv("MDARIX_B9B_OTHER", "on")  # on/off/on whatever the run's environment says
    assert register.floor("OTHER")["code"] == "OTHER-floor-1"
    monkeypatch.setenv("MDARIX_B9B_OTHER", "off")
    assert register.floor("OTHER") is None
    assert register.get("OTHER-floor-1") is not None


def test_other_stays_out_of_the_five_markets():
    from backend.app.reportability import markets

    assert "OTHER" not in markets.MARKETS and "OTHER" not in register.FLOOR_RULES
