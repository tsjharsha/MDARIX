"""The customer's own decision guides (T-G15, MVP G15), as plain functions over the starter question sets of
backend/app/reportability/markets.py: the one engine, never a second one.

- Version 1 of each market's guide is MDARIX's starter (``US-starter-1`` ...), read-only. A customer version
  (``US-v2`` ...) starts as a copy of the current version.
- In a customer version the **core questions** (the starter's) may be reworded and clarified: their text, definition,
  help note, clause and basis. They cannot be removed or reordered, and the conclusion logic (``markets.evaluate``) stays
  fixed, so a reworded guide still points to the same conclusion for the same answers. **Extra questions** (at most
  ``EXTRA_MAX``) are the customer's own: recorded and printed with the answer, never required and never part of the
  conclusion; they may be reordered.
- **Every question carries its regulation clause** (a reference text) **and its basis** in the standards catalog
  (backend/app/standards.py, the trial's source register); a version with a question lacking either cannot be published.
- **Test cases:** a set of answers and the outcome they must point to (reportable, with its report type when given; not
  reportable; pending information). A missing answer is Unknown, never No. Publication needs every test passing on the
  version's current content; the results are kept with the version.

MDARIX never decides: a guide points to a conclusion, and a person confirms or overrides it and signs.
"""

from __future__ import annotations

import re

from backend.app import standards
from backend.app.reportability import markets

TEXT_MIN, TEXT_MAX = 5, 400
DEFINITION_MAX, NOTE_MAX, CLAUSE_MAX = 2000, 600, 200
EXTRA_MAX, TESTS_MAX, NAME_MAX = 10, 30, 160
REASON_MIN = 10
PREFIX = {markets.US: "US", markets.EU_NI: "EU", markets.GB: "GB", markets.IN: "IN"}
EXPECTED = (markets.REPORTABLE, markets.NOT_REPORTABLE, markets.PENDING)
_EXTRA_ID = re.compile(r"^X\d{1,2}$")

DRAFT, AWAITING, PUBLISHED, SUPERSEDED, DISCARDED = (
    "DRAFT",
    "AWAITING_APPROVAL",
    "PUBLISHED",
    "SUPERSEDED",
    "DISCARDED",
)
STATE_LABELS = {
    DRAFT: "Draft",
    AWAITING: "Waiting for approval",
    PUBLISHED: "Published: in use",
    SUPERSEDED: "Superseded",
    DISCARDED: "Discarded",
}
OPEN_STATES = (DRAFT, AWAITING)
ADMINISTRATOR_ROLES = frozenset({"PLATFORM_ADMIN", "ADMIN", "ADMINISTRATOR", "CUSTOMER_ADMIN"})


def version_code(market: str, version: int) -> str:
    return f"{PREFIX[market]}-v{version}"


def starter(market: str) -> markets.QuestionSet:
    return markets.QUESTION_SETS[market]


def _clean(value, limit: int) -> str:
    text = " ".join(str(value or "").split())
    return text[:limit]


def question_dict(question: markets.Question) -> dict:
    """A question as a customer version stores it."""
    return {
        "id": question.id,
        "text": question.text,
        "definition": question.definition,
        "note": question.note or "",
        "clause": question.clause,
        "basis": list(question.basis),
        "extra": question.extra,
    }


def _is_starter_wording(item: dict, core: markets.Question) -> bool:
    return question_dict(core) == {**item, "extra": False}


def build(market: str, code: str, items: list[dict], title: str | None = None) -> markets.QuestionSet:
    """The question set of a customer version: the core questions as worded, then the extra questions."""
    base = starter(market)
    core = {question.id: question for question in base.questions}
    questions = []
    for item in items:
        found = core.get(item["id"])
        questions.append(
            markets.Question(
                item["id"],
                item["text"],
                item.get("definition") or "",
                item.get("clause") or "",
                tuple(item.get("basis") or ()),
                serious=found.serious if found is not None else False,
                note=item.get("note") or "",
                starter=found is not None and _is_starter_wording(item, found),
                extra=found is None,
            )
        )
    return markets.QuestionSet(market, code, title or base.title, tuple(questions), note=base.note, basis=base.basis)


def clean_questions(market: str, raw: list[dict]) -> tuple[list[dict] | None, str | None]:
    """``(questions as stored, None)`` or ``(None, why not)``. Every core question once, in the starter's order, then
    the extra questions in the order given (new ones get the next free ``X`` id)."""
    base = starter(market)
    core_ids = base.ids()
    given: dict[str, dict] = {}
    extras: list[dict] = []
    for item in raw or []:
        if not isinstance(item, dict):
            return None, "Each question needs its text"
        question_id = str(item.get("id") or "").strip().upper()
        cleaned = {
            "id": question_id,
            "text": _clean(item.get("text"), TEXT_MAX + 1),
            "definition": _clean(item.get("definition"), DEFINITION_MAX + 1),
            "note": _clean(item.get("note"), NOTE_MAX + 1),
            "clause": _clean(item.get("clause"), CLAUSE_MAX + 1),
            "basis": standards.known(item.get("basis") or []),
        }
        label = question_id or "a new question"
        if len(cleaned["text"]) < TEXT_MIN:
            return None, f"Question {label}: write the question in at least {TEXT_MIN} characters"
        for key, limit in (
            ("text", TEXT_MAX),
            ("definition", DEFINITION_MAX),
            ("note", NOTE_MAX),
            ("clause", CLAUSE_MAX),
        ):
            if len(cleaned[key]) > limit:
                return None, f"Question {label}: keep the {key} to {limit} characters"
        if question_id in core_ids:
            if question_id in given:
                return None, f"Question {question_id} appears twice"
            given[question_id] = {**cleaned, "extra": False}
        else:
            extras.append({**cleaned, "extra": True})
    missing = [question_id for question_id in core_ids if question_id not in given]
    if missing:
        return None, (f"Question {missing[0]} drives the conclusion: reword it, but it cannot be removed")
    if len(extras) > EXTRA_MAX:
        return None, f"Add at most {EXTRA_MAX} extra questions"
    taken = {item["id"] for item in extras if _EXTRA_ID.match(item["id"])}
    used: set[str] = set()
    number = 1
    for item in extras:
        if not _EXTRA_ID.match(item["id"]) or item["id"] in used:
            while f"X{number}" in taken or f"X{number}" in used:
                number += 1
            item["id"] = f"X{number}"
        used.add(item["id"])
    return [given[question_id] for question_id in core_ids] + extras, None


def clean_tests(market: str, raw: list[dict]) -> tuple[list[dict] | None, str | None]:
    """``(test cases as stored, None)`` or ``(None, why not)``. Answers name core questions only: extra questions never
    drive a conclusion."""
    core_ids = starter(market).ids()
    kinds = [kind for kind in markets.REPORT_TYPES if kind.startswith(PREFIX[market] + "_")]
    found: list[dict] = []
    if len(raw or []) > TESTS_MAX:
        return None, f"Keep to {TESTS_MAX} test cases"
    for index, item in enumerate(raw or [], 1):
        if not isinstance(item, dict):
            return None, f"Test {index}: give its answers and expected outcome"
        name = _clean(item.get("name"), NAME_MAX + 1)
        if len(name) < 3 or len(name) > NAME_MAX:
            return None, f"Test {index}: name it in 3 to {NAME_MAX} characters"
        answers = {}
        for question_id, answer in (item.get("answers") or {}).items():
            question_id = str(question_id).strip().upper()
            answer = str(answer or "").strip().upper()
            if not answer:
                continue
            if question_id not in core_ids:
                return None, f"Test {index}: {question_id} is not a question that drives the conclusion"
            if answer not in markets.ANSWERS:
                return None, f"Test {index}, {question_id}: answer Yes, No, Unknown or Not applicable"
            answers[question_id] = answer
        expected = str(item.get("expected") or "").strip().upper()
        if expected not in EXPECTED:
            return None, f"Test {index}: choose reportable, not reportable or pending information"
        kind = str(item.get("expected_report_type") or "").strip().upper() or None
        if kind is not None and (expected != markets.REPORTABLE or kind not in kinds):
            return None, f"Test {index}: a report type goes with an expected reportable outcome of this market"
        found.append(
            {"id": f"T{index}", "name": name, "answers": answers, "expected": expected, "expected_report_type": kind}
        )
    return found, None


def run(market: str, tests: list[dict]) -> list[dict]:
    """Each test with the outcome the fixed logic points to, and whether it is the expected one."""
    results = []
    for test in tests:
        found = markets.evaluate(market, {key: {"answer": value} for key, value in test["answers"].items()})
        passed = found["suggested"] == test["expected"] and (
            test.get("expected_report_type") is None or found["report_type"] == test["expected_report_type"]
        )
        results.append(
            {
                "id": test["id"],
                "name": test["name"],
                "expected": test["expected"],
                "expected_report_type": test.get("expected_report_type"),
                "actual": found["suggested"],
                "actual_report_type": found["report_type"],
                "passed": passed,
            }
        )
    return results


def content(market: str, code: str, questions: list[dict], tests: list[dict]) -> dict:
    """What a version's test results and approval are bound to (its fingerprint)."""
    return {"market": market, "code": code, "questions": questions, "test_cases": tests}


def publish_problems(questions: list[dict], tests: list[dict], results: dict | None, fingerprint: str) -> list[str]:
    """Why the version cannot be published yet: every reason, in order (empty when it can be)."""
    problems = []
    for item in questions:
        if not item.get("clause"):
            problems.append(f"Question {item['id']} has no regulation clause")
        if not item.get("basis"):
            problems.append(f"Question {item['id']} has no basis from the standards catalog")
    if not tests:
        problems.append("Add at least one test case")
    elif not results or results.get("fingerprint") != fingerprint:
        problems.append("Run the test cases on this version's current content")
    elif results.get("failed"):
        problems.append(f"{results['failed']} of {len(results['results'])} test cases fail: fix them, then run again")
    return problems


def approver_problem(approver: str, role: str | None, editors: set[str]) -> str | None:
    """Why this person may not approve the version, or None: never an editor of it, never an administrator (as a
    report snapshot's approval, 0.10.58)."""
    if (role or "").upper() in ADMINISTRATOR_ROLES:
        return "An administrator cannot approve a decision guide"
    if approver in editors:
        return "You edited this version: a second person must approve it"
    return None


def signature_meaning(code: str, title: str) -> str:
    return (
        f"I approve {code} of the {title} for use: its questions, clauses and test results as shown. Assessments "
        "started after publication use it. The guide points to a conclusion; a person concludes and signs."
    )


# ------------------------------------------------------------------------------------------- the starter tests


def _answers(market: str, default: str, **given: str) -> dict:
    """Every core question answered ``default`` except those given (in a test case of MDARIX's own)."""
    return {question_id: given.get(question_id, default) for question_id in starter(market).ids()}


def _test(name: str, answers: dict, expected: str, kind: str | None = None) -> dict:
    return {"name": name, "answers": answers, "expected": expected, "expected_report_type": kind}


def _vigilance_tests(market: str) -> list[dict]:
    p = PREFIX[market]
    return [
        _test(
            "A death the device may have caused: the 10-day report",
            _answers(market, "NO", **{f"{p}1": "YES", f"{p}2": "YES", f"{p}5": "YES"}),
            markets.REPORTABLE,
            f"{p}_10_DAY",
        ),
        _test(
            "A serious public health threat: the 2-day report",
            _answers(market, "NO", **{f"{p}1": "YES", f"{p}4": "YES", f"{p}5": "YES"}),
            markets.REPORTABLE,
            f"{p}_2_DAY",
        ),
        _test(
            "A serious deterioration that was anticipated: the 15-day report",
            _answers(market, "NO", **{f"{p}1": "YES", f"{p}3A": "YES", f"{p}5": "YES"}),
            markets.REPORTABLE,
            f"{p}_15_DAY",
        ),
        _test(
            "An incident with no serious outcome possible: not reportable",
            _answers(market, "NO", **{f"{p}1": "YES", f"{p}5": "YES"}),
            markets.NOT_REPORTABLE,
        ),
        _test(
            "The patient's outcome is unknown: pending information (Unknown is never No)",
            _answers(market, "NO", **{f"{p}1": "YES", f"{p}3A": "UNKNOWN", f"{p}5": "YES"}),
            markets.PENDING,
        ),
    ]


STARTER_TESTS: dict[str, list[dict]] = {
    markets.US: [
        _test(
            "A death the device caused or contributed to: the 30-day report",
            _answers(markets.US, "NO", US1="YES", US3="YES"),
            markets.REPORTABLE,
            "US_30_DAY",
        ),
        _test(
            "Serious injury, part (c), caused by the device: the 30-day report",
            _answers(markets.US, "NO", US2C="YES", US3="YES"),
            markets.REPORTABLE,
            "US_30_DAY",
        ),
        _test(
            "No injury, a malfunction likely to cause serious injury if it recurred: the 30-day report",
            _answers(markets.US, "NO", US4="YES", US5="YES"),
            markets.REPORTABLE,
            "US_30_DAY",
        ),
        _test(
            "The same, with remedial action needed for public health: the 5-work-day report",
            _answers(markets.US, "NO", US4="YES", US5="YES", US6="YES"),
            markets.REPORTABLE,
            "US_5_WORK_DAY",
        ),
        _test(
            "A malfunction that would not cause serious harm if it recurred: not reportable",
            _answers(markets.US, "NO", US4="YES"),
            markets.NOT_REPORTABLE,
        ),
        _test(
            "The patient's outcome is unknown: pending information (Unknown is never No)",
            _answers(markets.US, "NO", US2B="UNKNOWN", US3="YES"),
            markets.PENDING,
        ),
    ],
    markets.EU_NI: _vigilance_tests(markets.EU_NI),
    markets.GB: _vigilance_tests(markets.GB),
    markets.IN: [
        _test(
            "A serious adverse event the device is suspected of: reportable",
            _answers(markets.IN, "NO", IN1="YES", IN2F="YES"),
            markets.REPORTABLE,
            "IN_SERIOUS_ADVERSE_EVENT",
        ),
        _test(
            "An adverse event that is not serious: not reportable",
            _answers(markets.IN, "NO", IN1="YES"),
            markets.NOT_REPORTABLE,
        ),
        _test(
            "Whether it needed hospitalisation is unknown: pending information (Unknown is never No)",
            _answers(markets.IN, "NO", IN1="YES", IN2C="UNKNOWN"),
            markets.PENDING,
        ),
    ],
}


def starter_tests(market: str) -> list[dict]:
    tests, problem = clean_tests(market, STARTER_TESTS[market])
    assert problem is None, problem
    return tests
