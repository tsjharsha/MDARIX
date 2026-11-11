"""DEV-09 (0.10.87): the decision tables of docs/compliance/REGULATORY_DECISION_TABLES.md, run as behavioural tests.

The tables are the input: every row of a machine-read table is a case here, named by its row ID, so the document
cannot state an outcome the code does not give. The tests check the current starter rules against what the tables say;
they are not regulatory qualification, and the expert review of the rules is an external sign-off still pending.
"""

from __future__ import annotations

import functools
import itertools
import re
from datetime import date, datetime
from pathlib import Path

import pytest

from backend.app import feature_set
from backend.app.authority_reports import forms
from backend.app.complaint_classification.rules import CODING_CRITERIA_VERSION
from backend.app.complaint_disposition import rules as disposition
from backend.app.complaint_disposition.service import routine_offer
from backend.app.rule_register import register
from backend.app.reportability import deadlines, facts, markets

pytestmark = pytest.mark.unit

ROOT = Path(__file__).resolve().parents[1]
TABLES = ROOT / "docs" / "compliance" / "REGULATORY_DECISION_TABLES.md"
SUGGESTED = {"REPORTABLE": markets.REPORTABLE, "PENDING": markets.PENDING, "NOT_REPORTABLE": markets.NOT_REPORTABLE}
RATIONALE = "Read from the complaint record and the reporter's own words"


def _tables(kind: str) -> list[dict]:
    """Every row of the tables marked ``<!-- table: kind -->``, as {header: cell}."""
    rows: list[dict] = []
    lines = TABLES.read_text(encoding="utf-8").splitlines()
    for index, line in enumerate(lines):
        if line.strip() != f"<!-- table: {kind} -->":
            continue
        block = []
        for item in lines[index + 1 :]:
            if not item.startswith("|"):
                break
            block.append([cell.strip() for cell in item.strip().strip("|").split("|")])
        header, body = block[0], block[2:]
        rows += [dict(zip(header, cells)) for cells in body]
    assert rows, f"no {kind} table in {TABLES.name}"
    return rows


def _cases(kind: str):
    return [pytest.param(row, id=row["ID"]) for row in _tables(kind)]


def _ids(cell: str) -> list[str]:
    return cell.split()


def _pairs(cell: str) -> dict[str, str]:
    """ "US1=YES country=" -> {"US1": "YES", "country": ""}."""
    return dict(item.split("=", 1) for item in cell.split() if "=" in item)


def _answered(market: str, row: dict) -> dict:
    """The answers of an evaluate row: every core question No, except those the row lists."""
    found = {question_id: markets.NO for question_id in markets.QUESTION_SETS[market].ids()}
    for column, answer in (
        ("Yes", markets.YES),
        ("Unknown", markets.UNKNOWN),
        ("Not applicable", markets.NOT_APPLICABLE),
    ):
        found.update({question_id: answer for question_id in _ids(row[column])})
    for question_id in _ids(row["Not answered"]):
        found.pop(question_id)
    return {question_id: {"answer": answer, "rationale": RATIONALE} for question_id, answer in found.items()}


def test_every_row_id_is_unique_and_every_question_named_exists():
    seen: list[str] = []
    for kind in "evaluate fold market facts conclusion answers deadline routine linked version".split():
        seen += [row["ID"] for row in _tables(kind)]
    assert len(seen) == len(set(seen)), sorted(item for item in seen if seen.count(item) > 1)
    for row in _tables("evaluate"):
        known = set(markets.QUESTION_SETS[row["Market"]].ids())
        named = {*_ids(row["Yes"]), *_ids(row["Unknown"]), *_ids(row["Not applicable"]), *_ids(row["Not answered"])}
        assert named <= known, (row["ID"], named - known)


@pytest.mark.parametrize("row", _cases("evaluate"))
def test_evaluate(row):
    market = row["Market"]
    found = markets.evaluate(market, _answered(market, row))
    expected = SUGGESTED[row["Suggested"]]
    assert found["suggested"] == expected
    assert found["report_type_if_reportable"] == row["Type if reportable"]
    assert found["report_type"] == (row["Type if reportable"] if expected == markets.REPORTABLE else None)
    if expected == markets.PENDING:
        assert any("Unknown" in note for note in found["notes"])


@pytest.mark.parametrize("row", _cases("fold"))
def test_fold(row):
    answers = {key: {"answer": value} for key, value in _pairs(row["Answers"]).items()}
    assert sorted(markets.not_asked(row["Market"], answers)) == sorted(_ids(row["Not asked"]))


@pytest.mark.parametrize("row", _cases("market"))
def test_market(row):
    assert markets.markets_of(row["Country cell"]) == _ids(row["Markets"])


def _record(cell: str) -> dict:
    values = {"YES": True, "NO": False}
    record = {"death": None, "serious_injury": None, "patient_involved": None, "malfunction": None, "country": None}
    record.update({key: values.get(value, value) for key, value in _pairs(cell).items()})
    return record


@pytest.mark.parametrize("row", _cases("facts"))
def test_facts(row):
    needs = facts.needed(_record(row["Record"]), awareness_given=row["Awareness given"] == "YES")
    assert [item["fact"] for item in needs] == _ids(row["Needs"])


REFUSALS = {
    "Unknown is never No": "Unknown is never No",
    "an override needs its reason": "You override the suggestion",
    "conclude reportable or not reportable": "Conclude reportable or not reportable",
    "answer question US5": "Answer question US5",
    "question US5 is No, say why": "Question US5 is No",
    "give the rationale": "give the rationale",
}


def _check_signing(problem: str | None, signing: str) -> None:
    if signing.startswith("Allowed"):
        assert problem is None
        return
    why = signing.removeprefix("Refused: ")
    assert why in REFUSALS, f"add {why!r} to REFUSALS"
    assert problem is not None and REFUSALS[why] in problem, problem


@pytest.mark.parametrize("row", _cases("conclusion"))
def test_conclusion(row):
    reason = "The investigation shows otherwise" if row["Reason given"] == "YES" else ""
    problem = markets.conclusion_problem(SUGGESTED[row["Suggested"]], SUGGESTED[row["Conclusion"]], reason)
    _check_signing(problem, row["Signing"])


@pytest.mark.parametrize("row", _cases("answers"))
def test_answers(row):
    short = set(_ids(row["Short rationale"]))
    answers = {
        key: {"answer": value, "rationale": "Too short" if key in short else RATIONALE, "evidence": []}
        for key, value in _pairs(row["Answers"]).items()
    }
    problem = markets.answers_problem(markets.QUESTION_SETS[row["Market"]], answers, complete=True)
    _check_signing(problem, row["Signing"])


@pytest.mark.parametrize("row", _cases("deadline"))
def test_deadline(row):
    text = row["Awareness"]
    aware = datetime.fromisoformat(text) if "T" in text else date.fromisoformat(text)
    due = deadlines.count(aware, int(row["Days"]), row["Basis"], row["Market"], row["Organization zone"])
    assert (due.day.isoformat(), due.at.isoformat(), due.zone) == (
        row["Latest day"],
        row["Ends (UTC)"],
        row["Binding zone"],
    )


@pytest.mark.parametrize("row", _cases("routine"))
def test_routine(row):
    record = {} if row["Record"].startswith("(") else _record(row["Record"])
    unrecorded = disposition.routine_unrecorded(record)
    assert [item["code"] for item in unrecorded] == _ids(row["Not recorded"])
    assert routine_offer(False, None, [], unrecorded)["offered"] is (row["Routine path"] == "Offered")


VERSIONS = {
    **{f"VR-{index}": markets.QUESTION_SETS[market].version for index, market in enumerate(markets.MARKETS, 1)},
    "VR-6": markets.SCALE_VERSION,
    "VR-7": disposition.RULES_VERSION,
    "VR-8": CODING_CRITERIA_VERSION,
    **{
        f"VR-{index}": forms.BY_MARKET[market].version
        for index, market in enumerate((markets.US, markets.IN, markets.EU_NI, markets.GB, markets.CA), 9)
    },
    # B4: each market's floor in the rule register (market order, as VR-1 to VR-5).
    **{f"VR-{index}": register.floor(market)["code"] for index, market in enumerate(markets.MARKETS, 14)},
}


@pytest.mark.parametrize("row", _cases("version"))
def test_version(row):
    # Market order: VR-1 US, VR-2 EU/NI, VR-3 GB, VR-4 India, VR-5 Canada (markets.MARKETS).
    if row["ID"] == "VR-17" and not feature_set.switched_on("MDARIX_B9_INDIA"):  # B9 off: India is back on version 1
        row = {**row, "Version": "IN-floor-1"}
    assert VERSIONS[row["ID"]] == row["Version"]


@pytest.mark.parametrize("row", _cases("linked"))
def test_linked(row):
    """Each linked row names a behavioural test that exists."""
    path, name = row["Test"].split("::")
    source = (ROOT / path).read_text(encoding="utf-8")
    assert re.search(rf"^def {re.escape(name)}\(", source, re.M), row["Test"]


# ----------------------------------------------------------------------------------- every combination, not only rows


def _combinations(market: str, unknowns: int):
    """Every answer set of the market's core questions with Yes or No, and at most ``unknowns`` Unknowns."""
    ids = markets.QUESTION_SETS[market].ids()
    for count in range(unknowns + 1):
        for chosen in itertools.combinations(ids, count):
            rest = [question_id for question_id in ids if question_id not in chosen]
            for values in itertools.product((markets.YES, markets.NO), repeat=len(rest)):
                yield {**dict(zip(rest, values)), **dict.fromkeys(chosen, markets.UNKNOWN)}


def _evaluate(market: str, plain: dict) -> dict:
    return _evaluated(market, tuple(sorted(plain.items())))


@functools.lru_cache(maxsize=None)
def _evaluated(market: str, items: tuple) -> dict:
    return markets.evaluate(market, {key: {"answer": value} for key, value in items})


def _resolutions(plain: dict):
    """The answer set with each Unknown resolved to Yes or No, every way."""
    unknown = [key for key, value in plain.items() if value == markets.UNKNOWN]
    for values in itertools.product((markets.YES, markets.NO), repeat=len(unknown)):
        yield {**plain, **dict(zip(unknown, values))}


# How many Unknowns at once: the EU and GB sets have 11 questions (2,048 Yes/No sets each); a scratch run to three
# Unknowns everywhere (about 177,000 answer sets) found no exception, too slow for every run.
DEPTH = {markets.US: 2, markets.EU_NI: 1, markets.GB: 1, markets.IN: 2, markets.CA: 3}
DAYS = {code: kind.days or 0 for code, kind in markets.REPORT_TYPES.items()}


@pytest.mark.parametrize("market", markets.MARKETS)
def test_unknown_is_never_no_in_any_combination(market):
    """A definite suggestion holds whatever the Unknowns turn out to be; "pending information" means they could still
    go either way. Reportable with an Unknown that sets the type takes a type some resolution gives, the shortest for
    the EU, Great Britain and the US (Canada: owner decision OD-3)."""
    for plain in _combinations(market, DEPTH[market]):
        found = _evaluate(market, plain)
        resolved = [_evaluate(market, item) for item in _resolutions(plain)]
        outcomes = {item["suggested"] for item in resolved}
        if found["suggested"] == markets.PENDING:
            assert outcomes == {markets.REPORTABLE, markets.NOT_REPORTABLE}, plain
        else:
            assert outcomes == {found["suggested"]}, plain
        kinds = {item["report_type"] for item in resolved if item["suggested"] == markets.REPORTABLE}
        if found["suggested"] != markets.NOT_REPORTABLE and kinds:
            assert found["report_type_if_reportable"] in kinds, plain
            if market != markets.CA:
                shortest = min(DAYS[kind] or 999 for kind in kinds)
                assert (DAYS[found["report_type_if_reportable"]] or 999) == shortest, plain


@pytest.mark.parametrize("market", markets.MARKETS)
def test_folded_questions_never_change_the_outcome(market):
    """A question shown as "not asked" can take any answer, or none, without changing the suggestion or the type. An
    Unknown never folds a question, so one Unknown at a time covers the folds."""
    for plain in _combinations(market, 1):
        found = _evaluate(market, plain)
        for question_id in markets.not_asked(market, {key: {"answer": value} for key, value in plain.items()}):
            # Unknown and no answer read the same (markets._value).
            for other in (markets.YES, markets.NO, None):
                changed = {key: value for key, value in plain.items() if key != question_id}
                if other is not None:
                    changed[question_id] = other
                again = _evaluate(market, changed)
                assert (again["suggested"], again["report_type"]) == (found["suggested"], found["report_type"]), (
                    plain,
                    question_id,
                    other,
                )


@pytest.mark.parametrize("market", markets.MARKETS)
def test_every_starter_report_type_is_reached_by_a_table_row(market):
    reached = {row["Type if reportable"] for row in _tables("evaluate") if row["Market"] == market}
    own = {code for code in markets.REPORT_TYPES if code.startswith(disposition_prefix(market))}
    assert own <= reached, own - reached


def disposition_prefix(market: str) -> str:
    return {markets.EU_NI: "EU_"}.get(market, f"{market}_")


def test_fact_patient_outcome_unknown_asks_for_the_awareness_date_and_the_country_before_signing():
    """Table FACTS, row FA-5: a complaint on the watch only because a patient's outcome is unknown (no death, serious
    injury or malfunction recorded) is assessed and signed like any other. Before 0.10.87 it needed no fact, so a market
    conclusion was signed with no incident country and with its clock counted from the date MDARIX recorded it."""
    record = {"patient_involved": True, "serious_injury": None, "death": None, "malfunction": False, "country": ""}
    assert [item["fact"] for item in facts.needed(record, awareness_given=False)] == [facts.COUNTRY, facts.AWARENESS]
    assert facts.needed({**record, "country": "India"}, awareness_given=True) == []
    # Off the watch: nothing to ask (a known outcome, no harm, no malfunction).
    assert facts.needed({**record, "serious_injury": False, "death": False}, awareness_given=False) == []
