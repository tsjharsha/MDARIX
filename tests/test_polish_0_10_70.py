"""0.10.70, "Polish before proof": the stage 8 leftovers, as unit tests (no database).

- Item 1: the disposition, the escalation triggers and the Readiness rows say "investigation", and name a trigger in
  words, never by its code.
- Item 4 and 8: the event's stage line does not say "Investigation: not needed" before the decision; a finished event
  (closed in the QMS, ready to close signed, its checklist as signed) has no current stage.
- Item 8: the investigation's history names a record kind in words ("Investigation scope", not "Investigationscope");
  the second look's problem-code sign carries the customer's code for the screen to show with its IMDRF term.

The database tests are in test_flagship_walkthrough.py (the flagship, its investigation and RV-09).
"""

from __future__ import annotations

import re
from types import SimpleNamespace

import pytest

from backend.app.case_audit import rules as audit_rules
from backend.app.complaint_disposition import rules, triggers
from backend.app.complaint_review import rules as review_rules
from backend.app.oversight import closure

pytestmark = pytest.mark.unit

CASE_WORDS = re.compile(r"\b(cases?|signals?)\b", re.IGNORECASE)


def test_triggers_are_named_in_words_with_one_word_per_thing():
    assert triggers.words(["REPORTABLE", "NEW_FAILURE_MODE"]) == "reportable outcome, new failure mode"
    assert triggers.LABELS[triggers.RECURRENCE] == "Recurrence no investigation covers"
    for text in [*triggers.LABELS.values(), *triggers.DEFINITIONS.values()]:
        assert not CASE_WORDS.search(text), text


class _Query:
    """A query that finds nothing: no earlier complaint with the code, no open investigation covering it."""

    def __getattr__(self, name):
        return lambda *args, **kwargs: self

    def first(self):
        return None

    def all(self):
        return []


def test_a_new_failure_modes_fact_says_investigation():
    complaint = SimpleNamespace(id=1, product_id=2, problem_code="SPO2_READING_HIGH")
    facts = triggers.Facts(complaint, "SAMPLE-RV-11", "PulseWatch 410", ["US"])
    (met,) = triggers.new_failure_mode(SimpleNamespace(query=lambda *args: _Query()), "tenant", facts)
    assert met["fact"].endswith("and no open investigation covers it")
    assert not CASE_WORDS.search(met["fact"])


def test_the_disposition_asks_why_the_investigation_is_needed():
    problem = rules.branch_problem(rules.ESCALATED_BY_TRIGGER, True, [], None, "short", "")
    assert problem == f"Say why the investigation is needed in at least {rules.REASON_MIN} characters"
    assert "investigation opens" in rules.branch_problem(rules.SERVICE_LEVEL, True, [], None, "", "")
    answers = rules.answers_of(
        rules.ESCALATED_BY_TRIGGER, [{"code": "REPORTABLE", "fact": "US reportable"}], [], "x", ""
    )
    assert answers["KNOWN_ISSUE"]["rationale"] == "Closed: a trigger is met"
    assert rules.BRANCH_LABELS[rules.KNOWN_ISSUE] == "Known issue, linked to an open investigation"


def test_a_class_name_reads_as_words_in_the_history():
    assert audit_rules.readable("InvestigationScope") == "Investigation scope"
    assert audit_rules.readable("DecisionBriefVersion") == "Decision brief version"
    assert audit_rules.readable("CASE_REVIEW_COMPLETED") == "Case review completed"


def test_the_second_looks_problem_code_sign_carries_the_customers_code():
    signs, _ = review_rules.signs_of({"problem_code": "SPO2_DROPOUT_HARM"}, ())
    assert signs == [{"code": "PROBLEM_CODE", "label": "Problem code: SPO2_DROPOUT_HARM", "value": "SPO2_DROPOUT_HARM"}]


def _items(**results):
    return [{"code": code, "result": result, "detail": f"{code} {result}"} for code, result in results.items()]


def _stages(found, items, row=None):
    return {stage["code"]: stage["state"] for stage in closure.stage_line(found, items, row)}


def test_the_investigation_stage_is_later_until_the_decision_is_signed():
    complaint = SimpleNamespace(id="c1", status="open")
    undecided = _stages({"complaint": complaint, "cases": []}, _items(TRIAGE="PASS", DECISION="BLOCKED"))
    assert undecided["INVESTIGATION"] == "LATER" and undecided["DECISION"] == "CURRENT"
    resolved = _stages({"complaint": complaint, "cases": []}, _items(TRIAGE="PASS", DECISION="PASS"))
    assert resolved["INVESTIGATION"] == "NOT_NEEDED"


def test_a_finished_event_asks_for_nothing_until_its_checklist_changes():
    complaint = SimpleNamespace(id="c9", status="Closed")
    items = _items(TRIAGE="PASS", DECISION="BLOCKED")
    row = SimpleNamespace(ready_state="READY_WITH_REASON", content_fingerprint=closure.fingerprint("c9", items))
    assert closure.settled(complaint, items, row)
    assert "CURRENT" not in _stages({"complaint": complaint, "cases": []}, items, row).values()
    # A change since signing (a new open item) asks again.
    changed = _items(TRIAGE="BLOCKED", DECISION="BLOCKED")
    assert not closure.settled(complaint, changed, row)
    # Open in the QMS, or not signed ready, is not finished.
    assert not closure.settled(SimpleNamespace(id="c9", status="open"), items, row)
    assert not closure.settled(complaint, items, None)
