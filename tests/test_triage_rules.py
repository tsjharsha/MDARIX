"""0.10.93 (B2): triage at two speeds as plain rules (intake/triage_rules.py): TR-01, TR-03, TR-18, TR-25 to TR-30, the
floor, the A6 downgrade test, the A1 acknowledgement window and the T-D7 reopening triggers."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from backend.app.intake import rules, triage_rules as tr
from backend.app.oversight.rules import Calendar

pytestmark = pytest.mark.unit

FRIDAY_EVENING = datetime(2026, 11, 6, 19, 0, tzinfo=timezone.utc)


def _flag(code, **extra):
    return {"code": code, "label": code, **extra}


def _answer(question, answer):
    return _flag("FIRST_CONTACT", question=question, answer=answer)


def test_no_harm_no_malfunction_is_routine_with_the_prefill():  # TR-25
    facts = tr.facts([])
    assert tr.speed(facts) == tr.ROUTINE and tr.why_fast(facts) == "Routine: no harm alleged"
    assert tr.ROUTINE_PREFILL["harm_now_label"] == "No health consequence"


def test_malfunction_goes_fast_only_when_its_potential_harm_is_serious_or_above():  # TR-18, TR-26
    # A recorded malfunction or question 6 Yes: it could cause serious harm if it recurred, so fast by the facts.
    assert tr.speed(tr.facts([_flag("MALFUNCTION")])) == tr.FAST
    assert tr.speed(tr.facts([_answer("Q6", rules.YES)])) == tr.FAST
    facts = tr.facts([_answer("Q6", rules.UNKNOWN)])  # a malfunction alleged, its potential not known
    assert facts["malfunction"] and not facts["serious_potential"]
    assert tr.speed(facts, potential="MINOR") == tr.ROUTINE
    assert tr.speed(facts, potential="SERIOUS") == tr.FAST
    assert tr.why_fast(facts, potential="CRITICAL") == "Fast track: a malfunction that could cause serious harm"


@pytest.mark.parametrize(
    "flags",
    [
        [_answer("Q4", rules.YES)],  # TR-27 minor harm alleged
        [_flag("SERIOUS_INJURY")],  # TR-28
        [_flag("DEATH")],  # TR-30
        [_flag("URGENT_INTAKE")],
        [_flag("HARM_UNKNOWN")],
        [_answer("Q5", rules.UNKNOWN)],
        [_flag("MANUAL")],
    ],
)
def test_harm_death_urgent_unknown_or_manual_is_fast(flags):
    assert tr.speed(tr.facts(flags)) == tr.FAST


def test_not_known_yet_keeps_the_fast_track_and_a_threat_or_reopening_too():  # TR-01, TR-31
    assert tr.speed(tr.facts([]), severity=tr.NOT_KNOWN) == tr.FAST
    assert tr.speed(tr.facts([], threat=True)) == tr.FAST
    assert tr.speed(tr.facts([]), reopened=True) == tr.FAST


def test_the_floor_from_the_facts():  # TR-28, TR-30
    assert tr.floor(tr.facts([_flag("DEATH")])) == ("CATASTROPHIC", ["At least Catastrophic: a death is recorded"])
    assert tr.floor(tr.facts([_answer("Q5", rules.YES)]))[0] == "SERIOUS"
    assert tr.floor(tr.facts([])) == (None, [])


def test_below_the_floor_is_refused_and_lowering_needs_a_reason():  # TR-03
    assert tr.severity_problem("SERIOUS", "CATASTROPHIC", None, "")[0] == "BELOW_FLOOR"
    assert tr.severity_problem(tr.NOT_KNOWN, "SERIOUS", None, "")[0] == "BELOW_FLOOR"
    assert tr.severity_problem("BAD", None, None, "")[0] == "SEVERITY_NEEDED"
    assert tr.severity_problem("MINOR", None, "SERIOUS", "short")[0] == "REASON_NEEDED"
    assert tr.severity_problem("MINOR", None, "SERIOUS", "The nurse confirmed a bruise only.") is None
    assert tr.severity_problem(tr.NOT_KNOWN, None, None, "") is None


def test_a_downgrade_is_only_of_a_fast_track_triage():  # A6
    fast = {"speed": tr.FAST, "severity": "CRITICAL", "potential_severity": "CRITICAL"}
    assert tr.is_downgrade(fast, {**fast, "severity": "SERIOUS"})
    assert tr.is_downgrade(fast, {**fast, "potential_severity": "MINOR"})
    assert tr.is_downgrade(fast, {**fast, "speed": tr.ROUTINE})
    assert not tr.is_downgrade(fast, {**fast, "severity": "CATASTROPHIC"})
    assert not tr.is_downgrade({**fast, "speed": tr.ROUTINE}, {**fast, "speed": tr.ROUTINE, "severity": "MINOR"})


def test_fast_counts_clock_hours_through_the_weekend_and_routine_the_next_working_day():  # OD-7, 5.3
    calendar = Calendar()
    assert tr.due(tr.FAST, FRIDAY_EVENING, 4, calendar) == FRIDAY_EVENING + timedelta(hours=4)
    routine = tr.due(tr.ROUTINE, FRIDAY_EVENING, 4, calendar)
    assert routine.weekday() == 0 and routine > FRIDAY_EVENING  # Monday's end, not Saturday's


def test_the_acknowledgement_is_due_within_the_window_never_after_the_target():  # A1
    assert tr.ack_due(FRIDAY_EVENING, FRIDAY_EVENING + timedelta(hours=4)) == FRIDAY_EVENING + timedelta(hours=1)
    soon = FRIDAY_EVENING + timedelta(minutes=30)
    assert tr.ack_due(FRIDAY_EVENING, soon) == soon


def test_reopening_triggers():  # T-D7, TR-11, TR-19
    before = tr.facts([])
    assert tr.reopen_trigger(before, tr.facts([_flag("DEATH")]), None, "CATASTROPHIC") == "DEATH"
    assert tr.reopen_trigger(before, tr.facts([_answer("Q4", rules.YES)]), None, None) == "MORE_HARM"
    assert tr.reopen_trigger(before, tr.facts([], threat=True), None, None) == "THREAT"
    assert (
        tr.reopen_trigger(tr.facts([_flag("DEATH")]), tr.facts([_flag("DEATH")]), "CATASTROPHIC", "CATASTROPHIC")
        is None
    )
    assert tr.reopen_trigger(None, tr.facts([_flag("DEATH")]), None, None) is None


def test_a_backup_is_needed_on_the_fast_track_with_two_people():  # TR-09, TR-17
    assert tr.backup_problem(tr.FAST, 2, "") == "Name a backup: two or more people are active"
    assert tr.backup_problem(tr.FAST, 1, "") is None
    assert tr.backup_problem(tr.ROUTINE, 3, "") is None


def test_containment_keeps_known_choices_once():  # T-D11
    assert tr.containment(["HOLD_LOT", "HOLD_LOT", "BOGUS", "FIELD_ACTION"]) == ["HOLD_LOT", "FIELD_ACTION"]
