"""The rule engine (B4): one small reader of a market's floor, held as data (``rule_register/data``).

A condition is one of:

- ``"US3"``: a question's answer, three-valued: Yes is True; No and Not applicable are False; Unknown, or no answer,
  is None (never False: floor F3, "Unknown is never No").
- ``{"any": [...]}``, ``{"all": [...]}``: Kleene's logic over three values (True wins ``any``, False wins ``all``,
  otherwise an undecided part keeps the result undecided).
- ``{"ref": "name"}``: a named condition of the floor's ``defs``, or ``"reportable"`` (any of the floor's rules).
- ``{"is_yes": c}``, ``{"is_no": c}``, ``{"is_unknown": c}``, ``{"maybe": c}`` (not No): a two-valued test of ``c``.
- ``{"type": "US_30_DAY"}``: the report type the type rows chose (notes only).

``evaluate`` gives what ``reportability/legacy_v1.py`` gave for version 1, byte for byte (tests/test_b4_equivalence.py):
the suggestion is Reportable when any rule applies, pending information when any could, else Not reportable; the report
type is the first matching type row; every matching note in file order; folding in file order, the first reason for a
question kept.
"""

from __future__ import annotations

YES, NO, NOT_APPLICABLE = "YES", "NO", "NOT_APPLICABLE"
REPORTABLE, PENDING, NOT_REPORTABLE = "REPORTABLE", "PENDING_INFORMATION", "NOT_REPORTABLE"
OPERATORS = frozenset({"any", "all", "ref", "is_yes", "is_no", "is_unknown", "maybe", "type"})


def answer_value(answers: dict, question_id: str) -> bool | None:
    answer = (answers.get(question_id) or {}).get("answer")
    if answer == YES:
        return True
    if answer in (NO, NOT_APPLICABLE):
        return False
    return None


def kleene_any(values) -> bool | None:
    values = list(values)
    if True in values:
        return True
    return None if None in values else False


def kleene_all(values) -> bool | None:
    values = list(values)
    if False in values:
        return False
    return None if None in values else True


class _Context:
    def __init__(self, content: dict, answers: dict):
        self.content, self.answers, self.refs, self.type = content, answers, {}, None

    def value(self, condition) -> bool | None:
        if isinstance(condition, str):
            return answer_value(self.answers, condition)
        (operator, argument), *rest = condition.items()
        if rest or operator not in OPERATORS:
            raise ValueError(f"unknown condition {condition!r}")
        if operator == "any":
            return kleene_any(self.value(part) for part in argument)
        if operator == "all":
            return kleene_all(self.value(part) for part in argument)
        if operator == "ref":
            if argument not in self.refs:
                found = (
                    kleene_any(self.value(rule["if"]) for rule in self.content["rules"])
                    if argument == "reportable"
                    else self.value(self.content["defs"][argument])
                )
                self.refs[argument] = found
            return self.refs[argument]
        if operator == "type":
            return self.type == argument
        found = self.value(argument)
        return {
            "is_yes": found is True,
            "is_no": found is False,
            "is_unknown": found is None,
            "maybe": found is not False,
        }[operator]

    def holds(self, row: dict) -> bool:
        """A row without ``if`` always holds (the last type row)."""
        return "if" not in row or self.value(row["if"]) is True


def _suggestion(reportable: bool | None) -> str:
    return {True: REPORTABLE, None: PENDING, False: NOT_REPORTABLE}[reportable]


def not_asked(content: dict, answers: dict) -> dict[str, str]:
    """The questions earlier answers make unnecessary, each with why (the floor's ``folding``)."""
    context, found = _Context(content, answers), {}
    for row in content["folding"]:
        if context.holds(row):
            for question_id in row["fold"]:
                found.setdefault(question_id, row["why"])
    return found


def evaluate(content: dict, answers: dict) -> dict:
    """The suggestion, report type and notes of a market's answers (as ``markets.evaluate``)."""
    context = _Context(content, answers)
    reportable = context.value({"ref": "reportable"})
    context.type = kind = next(row["type"] for row in content["type_rows"] if context.holds(row))
    return {
        "suggested": _suggestion(reportable),
        "report_type": kind if reportable else None,
        "report_type_if_reportable": kind,
        "notes": [row["text"] for row in content["notes"] if context.holds(row)],
        "not_asked": not_asked(content, answers),
    }


def applied(content: dict, answers: dict) -> dict:
    """The rules that apply (True) or could apply (None) to these answers, and the type row chosen: kept on a market
    conclusion (``rules_applied``) so an auditor sees which rules decided it."""
    context = _Context(content, answers)
    states = {True: "APPLIES", None: "COULD_APPLY"}
    rules = [
        {"id": rule["id"], "state": states[found]}
        for rule in content["rules"]
        if (found := context.value(rule["if"])) is not False
    ]
    row = next(row for row in content["type_rows"] if context.holds(row))
    return {"rules": rules, "type_row": row["id"]}


def check(content: dict) -> list[str]:
    """What is wrong with a floor's logic: unknown operators, questions or names (the register's build check)."""
    questions = {question["id"] for question in content["question_set"]["questions"]}
    problems: list[str] = []

    def walk(condition, where: str) -> None:
        if isinstance(condition, str):
            if condition not in questions:
                problems.append(f"{where}: unknown question {condition}")
            return
        if not isinstance(condition, dict) or len(condition) != 1:
            problems.append(f"{where}: a condition is a question id or one operator")
            return
        ((operator, argument),) = condition.items()
        if operator not in OPERATORS:
            problems.append(f"{where}: unknown operator {operator}")
        elif operator in ("any", "all"):
            for part in argument:
                walk(part, where)
        elif operator == "ref":
            if argument != "reportable" and argument not in content.get("defs", {}):
                problems.append(f"{where}: unknown name {argument}")
        elif operator == "type":
            if argument not in content["report_types"]:
                problems.append(f"{where}: unknown report type {argument}")
        else:
            walk(argument, where)

    for name, condition in content.get("defs", {}).items():
        walk(condition, f"defs.{name}")
    for part in ("rules", "type_rows", "notes", "folding"):
        for index, row in enumerate(content[part]):
            if "if" in row:
                walk(row["if"], f"{part}[{index}]")
    for row in content["type_rows"]:
        if row["type"] not in content["report_types"]:
            problems.append(f"type_rows: unknown report type {row['type']}")
    if not content["type_rows"] or "if" in content["type_rows"][-1]:
        problems.append("type_rows: the last row has no condition (the default)")
    for row in content["folding"]:
        problems += [f"folding: unknown question {q}" for q in row["fold"] if q not in questions]
    if set(content["precedence"]) != set(content["report_types"]):
        problems.append("precedence: lists every report type once")
    return problems
