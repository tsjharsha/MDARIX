"""B4 step 2: the rule engine's operators, Kleene logic, type rows, notes and folding (spec 5.1), without a database."""

from __future__ import annotations

import itertools

import pytest

from backend.app.rule_register import engine

VALUES = {"YES": True, "NO": False, "NOT_APPLICABLE": False, "UNKNOWN": None, None: None}


def _answers(**given) -> dict:
    return {key: {"answer": value} for key, value in given.items() if value is not None}


def _content(**parts) -> dict:
    content = {
        "question_set": {"questions": [{"id": q} for q in ("A", "B", "C")]},
        "report_types": {"SHORT": {}, "LONG": {}},
        "precedence": ["SHORT", "LONG"],
        "defs": {"either": {"any": ["A", "B"]}},
        "rules": [{"id": "R-1", "if": {"all": [{"ref": "either"}, "C"]}}],
        "type_rows": [{"id": "T-1", "if": {"is_no": "B"}, "type": "LONG"}, {"id": "T-2", "type": "SHORT"}],
        "notes": [],
        "folding": [],
    }
    content.update(parts)
    return content


def test_an_answer_is_three_valued_and_unknown_is_never_no():
    for answer, expected in VALUES.items():
        assert engine.answer_value(_answers(A=answer), "A") is expected
    assert engine.answer_value({}, "A") is None


@pytest.mark.parametrize("a, b", list(itertools.product([True, False, None], repeat=2)))
def test_kleene_truth_tables(a, b):
    assert engine.kleene_any([a, b]) == (True if True in (a, b) else None if None in (a, b) else False)
    assert engine.kleene_all([a, b]) == (False if False in (a, b) else None if None in (a, b) else True)


@pytest.mark.parametrize("answer", list(VALUES))
def test_the_two_valued_tests(answer):
    value = VALUES[answer]
    context = engine._Context(_content(), _answers(A=answer))
    assert context.value({"is_yes": "A"}) is (value is True)
    assert context.value({"is_no": "A"}) is (value is False)
    assert context.value({"is_unknown": "A"}) is (value is None)
    assert context.value({"maybe": "A"}) is (value is not False)


def test_the_suggestion_follows_the_rules_and_the_type_the_first_matching_row():
    content = _content()
    assert engine.evaluate(content, _answers(A="YES", C="YES", B="NO")) == {
        "suggested": "REPORTABLE",
        "report_type": "LONG",
        "report_type_if_reportable": "LONG",
        "notes": [],
        "not_asked": {},
    }
    pending = engine.evaluate(content, _answers(A="YES"))
    assert pending["suggested"] == "PENDING_INFORMATION" and pending["report_type"] is None
    assert pending["report_type_if_reportable"] == "SHORT"  # B Unknown: never read as No
    assert engine.evaluate(content, _answers(A="NO", B="NO"))["suggested"] == "NOT_REPORTABLE"


def test_every_matching_note_in_file_order_and_the_type_condition():
    content = _content(
        notes=[
            {"if": {"type": "SHORT"}, "text": "short"},
            {"if": {"is_unknown": {"ref": "reportable"}}, "text": "pending"},
            {"if": {"is_yes": "A"}, "text": "a"},
        ]
    )
    assert engine.evaluate(content, _answers(A="YES"))["notes"] == ["short", "pending", "a"]
    assert engine.evaluate(content, _answers(A="NO", B="NO"))["notes"] == []


def test_folding_keeps_the_first_reason_for_a_question():
    content = _content(
        folding=[
            {"if": {"is_no": "A"}, "fold": ["B", "C"], "why": "first"},
            {"if": {"is_no": "A"}, "fold": ["C"], "why": "second"},
            {"if": {"is_unknown": "A"}, "fold": ["C"], "why": "never: Unknown folds nothing here"},
        ]
    )
    assert engine.not_asked(content, _answers(A="NO")) == {"B": "first", "C": "first"}


def test_rules_applied_lists_what_applies_or_could_and_the_type_row():
    content = _content(rules=[{"id": "R-1", "if": "A"}, {"id": "R-2", "if": "B"}, {"id": "R-3", "if": "C"}])
    found = engine.applied(content, _answers(A="YES", B="NO"))
    assert found == {
        "rules": [{"id": "R-1", "state": "APPLIES"}, {"id": "R-3", "state": "COULD_APPLY"}],
        "type_row": "T-1",
    }


def test_the_check_names_unknown_questions_operators_names_and_types():
    content = _content(
        rules=[{"id": "R-1", "if": {"nope": "A"}}, {"id": "R-2", "if": "Z"}, {"id": "R-3", "if": {"ref": "missing"}}],
        notes=[{"if": {"type": "NONE"}, "text": "x"}],
        type_rows=[{"id": "T-1", "if": "A", "type": "SHORT"}],
    )
    problems = engine.check(content)
    assert "rules[0]: unknown operator nope" in problems
    assert "rules[1]: unknown question Z" in problems
    assert "rules[2]: unknown name missing" in problems
    assert "notes[0]: unknown report type NONE" in problems
    assert "type_rows: the last row has no condition (the default)" in problems
    assert engine.check(_content()) == []
    with pytest.raises(ValueError):
        engine.evaluate(_content(rules=[{"id": "R", "if": {"nope": "A"}}]), {})
