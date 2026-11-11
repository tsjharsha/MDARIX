"""B9 step 20 (B9-D6, G15): CA-floor-2, a correction of CA-floor-1 from the start. A foreign incident's preliminary report
is due by the end of the day after the corrective-action decision day, counted from awareness until that day is known
(provisional: awareness is day 0, so the end of the next day); while "in Canada" (CA5) is Unknown and CA6 is Yes, that
foreign clock applies (the shortest not ruled out). Every other answer set reads as version 1. Behind MDARIX_B9_CANADA;
signed records keep version 1. No database."""

from __future__ import annotations

import itertools
import json
from datetime import date, datetime, timezone
from types import SimpleNamespace

import pytest

from backend.app.reportability import assessments, markets
from backend.app.rule_register import engine, register

pytestmark = pytest.mark.unit

THREE = ("YES", "NO", "UNKNOWN")
AWARE = datetime(2027, 1, 4, 15, 0, tzinfo=timezone.utc)  # 4 Jan in Toronto (10:00): day 0; due the end of 5 Jan
ZONE = "America/Toronto"


@pytest.fixture(autouse=True)
def _canada_on(monkeypatch):
    monkeypatch.delenv("MDARIX_B9_CANADA", raising=False)  # its default: on


def test_version_two_is_a_correction_from_the_start_behind_the_canada_switch(monkeypatch):
    one, two = register.get("CA-floor-1"), register.get("CA-floor-2")
    assert two["change"]["kind"] == "CORRECTION" and two["change"]["corrects"] == "CA-floor-1"
    assert (two["effective_from"], two["effective_to"]) == (one["effective_from"], one["effective_to"]) == (None, None)
    assert two["switch"] == "MDARIX_B9_CANADA" and two["review"] == one["review"]  # starter
    assert register.floor("CA")["code"] == "CA-floor-2"
    assert register.pick("CA-floor", date(2019, 1, 1))["code"] == "CA-floor-2"  # from the start
    monkeypatch.setenv("MDARIX_B9_CANADA", "off")
    assert register.floor("CA")["code"] == "CA-floor-1"


def test_every_answer_set_reads_as_version_one_except_unknown_in_canada_with_ca6_yes():
    one, two = register.get("CA-floor-1")["content"], register.get("CA-floor-2")["content"]
    ids = [question["id"] for question in one["question_set"]["questions"]]
    changed = 0
    for combination in itertools.product(THREE, repeat=len(ids)):
        given = dict(zip(ids, combination))
        answers = {key: {"answer": value} for key, value in given.items()}
        old, new = engine.evaluate(one, answers), engine.evaluate(two, answers)
        assert new["suggested"] == old["suggested"], given
        foreign = given["CA5"] == "UNKNOWN" and given["CA6"] == "YES"
        if foreign:  # the foreign clock, shorter than the 10 days version 1 gave (OD-3)
            assert new["report_type_if_reportable"] == "CA_FOREIGN", given
            assert old["report_type_if_reportable"] in ("CA_10_DAY", "CA_30_DAY"), given
            changed += 1
        else:
            assert new["report_type_if_reportable"] == old["report_type_if_reportable"], given
        if new["report_type_if_reportable"] != "CA_FOREIGN":
            assert json.dumps(new, sort_keys=True) == json.dumps(old, sort_keys=True), given
    assert changed == 3**4


def test_the_foreign_report_is_due_by_the_end_of_the_day_after_awareness_provisionally():
    floor = register.get("CA-floor-2")
    kind = floor["content"]["report_types"]["CA_FOREIGN"]
    assert (kind["days"], kind["basis"]) == (1, "CALENDAR") and "starter" in kind["label"]
    answers = {"CA1": "YES", "CA2": "YES", "CA3": "YES", "CA5": "NO", "CA6": "YES"}
    found = engine.evaluate(floor["content"], {key: {"answer": value} for key, value in answers.items()})
    assert found["report_type"] == "CA_FOREIGN"
    assert any("Provisional" in note and "corrective-action decision" in note for note in found["notes"])
    clock = markets.market_clock("CA", "REPORTABLE", "CA_FOREIGN", [], AWARE, AWARE, ZONE, floor=floor)
    assert clock["days"] == 1 and clock["due_date"] == "2027-01-05", clock
    # Version 1 held no period: its clock fell back to the organization's Canada windows (none here).
    assert register.get("CA-floor-1")["content"]["report_types"]["CA_FOREIGN"]["days"] is None


def test_a_conclusion_signed_under_version_one_keeps_it():
    two = register.get("CA-floor-2")
    signed = SimpleNamespace(floor_code="CA-floor-1")
    assert assessments.signed_floor("CA", signed, two)["code"] == "CA-floor-1"
    before = SimpleNamespace(floor_code=None)  # signed before the register: version 1
    assert assessments.signed_floor("CA", before, two)["code"] == "CA-floor-1"


def test_every_floors_report_type_label_fits_the_window_name_column():
    """A pending or signed clock stores the label as the window's name (complaint_market_assessments.window_name, 160):
    the first CA-floor-2 label did not fit, and saving a foreign incident failed."""
    for path in sorted(register._DIRECTORY.glob("*floor-*.json")):
        content = json.loads(path.read_text(encoding="utf-8")).get("content") or {}
        for code, kind in (content.get("report_types") or {}).items():
            assert len(kind["label"]) <= 160, (path.name, code)
