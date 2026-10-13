"""Phase 4 rules without a database: the brief's first draft (problem statement, actions), the case AI run's view and
staleness, and the signal summary's wording check."""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from backend.app.case_ai import runner
from backend.app.decision_brief import rules as brief_rules
from backend.app.signals.insight import CAUSAL_WORDING


def test_the_ai_brief_next_steps_become_recommended_actions():
    content = {
        "ai_brief": {
            "headline": "Alarms rose after release B.",
            "sections": {
                "next_steps": [
                    {"statement": "  Review the  release B change record "},
                    {"statement": "Review the release B change record"},
                    {"statement": ""},
                    "not a step",
                    {"statement": "Ask the supplier for the sensor lot data"},
                ]
            },
        }
    }
    assert brief_rules.ai_draft_actions(content) == [
        "Review the release B change record",
        "Ask the supplier for the sensor lot data",
    ]
    assert brief_rules.ai_draft_actions({"executive_summary": {"text": "Rules only"}}) == []
    assert brief_rules.ai_draft_actions(None) == []
    many = {"ai_brief": {"sections": {"next_steps": [{"statement": f"Step {i}"} for i in range(30)]}}}
    assert len(brief_rules.ai_draft_actions(many)) == brief_rules.ACTIONS_MAX


def test_the_problem_statement_is_the_case_question():
    assert brief_rules.problem_statement_from("  Why do  alarms rise\non Rev B? ") == "Why do alarms rise on Rev B?"
    assert brief_rules.problem_statement_from(None) == ""


def _run(**fields):
    now = datetime.now(timezone.utc)
    base = {
        "id": uuid.uuid4(),
        "status": "COMPLETED",
        "trigger": "AUTO",
        "as_of": now,
        "requested_at": now,
        "started_at": now,
        "finished_at": now,
        "error": None,
        "steps": [{"step": "ANALYSIS", "status": "DONE", "author": "RULES"}],
    }
    return SimpleNamespace(**{**base, **fields})


def test_the_run_view_lists_every_step_in_order_with_pending_ones():
    view = runner.view(_run())
    assert [step["step"] for step in view["steps"]] == [code for code, _ in runner.STEPS]
    assert view["steps"][0] == {
        "step": "ANALYSIS",
        "label": "Analysis of the evidence",
        "status": "DONE",
        "author": "RULES",
    }
    assert {step["status"] for step in view["steps"][1:]} == {"PENDING"}
    assert runner.view(None) is None


def test_a_run_stuck_for_half_an_hour_is_shown_as_stopped():
    old = datetime.now(timezone.utc) - timedelta(minutes=45)
    stuck = _run(status="RUNNING", started_at=old, requested_at=old)
    assert runner.is_stale(stuck)
    assert runner.view(stuck)["status"] == "FAILED" and "start it again" in runner.view(stuck)["error"]
    assert not runner.is_stale(_run(status="RUNNING"))
    assert not runner.is_stale(_run(status="COMPLETED", started_at=old))


@pytest.mark.parametrize(
    "text,causal",
    [
        ("Three complaints describe an occlusion alarm.", False),
        ("Two complaints come from lot L-0101.", False),
        ("The alarm was caused by the firmware.", True),
        ("Failures are due to the new adhesive.", True),
        ("Stops occurred because the battery drained.", True),
        ("This led to delayed therapy.", True),
        ("The root-cause is the sensor.", True),
    ],
)
def test_the_signal_summary_drops_causal_wording(text, causal):
    assert bool(CAUSAL_WORDING.search(text)) is causal
