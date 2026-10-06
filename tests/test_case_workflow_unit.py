"""Case workflow without a database: the transition rules and the open/closed status that goes with each state,
due dates by priority, the scope rules (diff, warnings, conflicts, request validation), the readiness evaluation, and
the rule that starting a case from its task never breaks taking the task."""

from __future__ import annotations

import logging
import uuid
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from backend.app.case_workflow import readiness, scope, states
from backend.app.db.models.case_scope import INVESTIGATION_STATES

pytestmark = pytest.mark.unit

NOW = datetime(2026, 10, 6, 12, 0, tzinfo=timezone.utc)
REASON = "Reason recorded for the audit trail"


# ------------------------------------------------------------------------------------------------------ states


def test_the_manual_transition_matrix():
    allowed = {
        (current, target)
        for current in INVESTIGATION_STATES
        for target in INVESTIGATION_STATES
        if states.transition_refusal(current, target) is None
    }
    assert allowed == {
        ("OPEN", "IN_PROGRESS"),
        ("OPEN", "ON_HOLD"),
        ("OPEN", "CANCELLED"),
        ("IN_PROGRESS", "ON_HOLD"),
        ("IN_PROGRESS", "CANCELLED"),
        ("ON_HOLD", "IN_PROGRESS"),
        ("ON_HOLD", "CANCELLED"),
        ("CANCELLED", "IN_PROGRESS"),
    }
    # The review and decision states are set by their own steps; closing stays with managing the case.
    for target in ("BRIEF_IN_REVIEW", "READY_FOR_DECISION", "DECIDED"):
        assert "not by hand" in states.transition_refusal("IN_PROGRESS", target)
    assert "Close a case" in states.transition_refusal("IN_PROGRESS", "CLOSED")
    assert "already on hold" in states.transition_refusal("ON_HOLD", "ON_HOLD")
    assert states.transition_refusal("CLOSED", "IN_PROGRESS")
    assert states.transition_refusal("OPEN", "SOMETHING")


def test_each_manual_move_needs_its_permission():
    assert states.required_permission("IN_PROGRESS") == "investigation.work"
    assert states.required_permission("ON_HOLD") == "investigation.work"
    assert states.required_permission("CANCELLED") == "investigation.assign"
    for target in ("OPEN", "CLOSED", "BRIEF_IN_REVIEW", "READY_FOR_DECISION", "DECIDED"):
        assert states.required_permission(target) is None


def test_status_follows_the_workflow_state():
    assert {state: states.status_for(state) for state in INVESTIGATION_STATES} == {
        "OPEN": "open",
        "IN_PROGRESS": "open",
        "ON_HOLD": "open",
        "BRIEF_IN_REVIEW": "open",
        "READY_FOR_DECISION": "open",
        "DECIDED": "open",
        "CLOSED": "closed",
        "CANCELLED": "closed",
    }
    assert set(states.STATE_LABELS) == set(INVESTIGATION_STATES)


def test_the_state_is_read_defensively():
    assert states.effective_state("IN_PROGRESS", "open") == "IN_PROGRESS"
    # An imported closed case whose workflow state was never set is closed.
    assert states.effective_state("OPEN", "closed") == "CLOSED"
    assert states.effective_state("CANCELLED", "Closed") == "CANCELLED"
    # An open case is never closed or cancelled, and an unknown state reads as OPEN.
    assert states.effective_state("CLOSED", "open") == "OPEN"
    assert states.effective_state(None, None) == "OPEN"
    assert states.effective_state("nonsense", "open") == "OPEN"


def _case(**values):
    base = {"workflow_state": "OPEN", "status": "open", "closed_at": None, "state_changed_at": None, "updated_at": None}
    return SimpleNamespace(**{**base, **values})


def test_set_state_keeps_status_and_closed_at_in_step():
    case = _case()
    states.set_state(case, "CANCELLED", NOW)
    assert (case.workflow_state, case.status, case.closed_at, case.state_changed_at) == (
        "CANCELLED",
        "closed",
        NOW,
        NOW,
    )
    later = NOW + timedelta(hours=1)
    # Already closed: closing again keeps the original closed_at.
    states.set_state(case, "CLOSED", later)
    assert case.closed_at == NOW and case.state_changed_at == later
    states.set_state(case, "IN_PROGRESS", later)
    assert (case.workflow_state, case.status, case.closed_at) == ("IN_PROGRESS", "open", None)
    with pytest.raises(ValueError):
        states.set_state(case, "UNKNOWN", later)


def test_due_dates_follow_the_priority():
    assert {priority: states.due_at_for(priority, NOW) - NOW for priority in states.PRIORITIES} == {
        "CRITICAL": timedelta(days=15),
        "HIGH": timedelta(days=30),
        "MEDIUM": timedelta(days=60),
        "LOW": timedelta(days=90),
    }
    assert states.normalize_priority(None) == "MEDIUM" and states.normalize_priority("high") == "HIGH"
    assert states.normalize_priority("URGENT") == "MEDIUM"
    assert states.due_at_for(None, NOW) == NOW + timedelta(days=60)
    assert states.overdue(NOW - timedelta(days=1), "IN_PROGRESS", NOW)
    assert not states.overdue(NOW - timedelta(days=1), "CLOSED", NOW)
    assert not states.overdue(None, "OPEN", NOW)


def test_starting_a_case_moves_only_an_open_case():
    added = []
    session = SimpleNamespace(add=added.append)
    case = SimpleNamespace(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        workflow_state="OPEN",
        status="open",
        closed_at=None,
        state_changed_at=None,
        updated_at=None,
    )
    assert states.start_case(session, case, actor_ref="someone", reason="Task accepted")
    assert case.workflow_state == "IN_PROGRESS" and case.status == "open"
    assert len(added) == 1 and added[0].action == "INVESTIGATION_STATE_CHANGED"
    assert added[0].old_values == {"workflow_state": "OPEN"} and added[0].new_values == {
        "workflow_state": "IN_PROGRESS"
    }
    for state in ("IN_PROGRESS", "ON_HOLD"):
        assert not states.start_case(session, _case(workflow_state=state), actor_ref="someone", reason="Again")
    assert not states.start_case(session, None, actor_ref="someone", reason="No case")
    assert len(added) == 1


class _BrokenSession:
    def begin_nested(self):
        raise RuntimeError("database unavailable")


def test_starting_the_case_from_its_task_never_breaks_taking_the_task(caplog):
    task = SimpleNamespace(
        id=uuid.uuid4(), tenant_id=uuid.uuid4(), task_type="INVESTIGATION", investigation_id=uuid.uuid4()
    )
    with caplog.at_level(logging.ERROR, logger="mdarix.case_workflow"):
        states.on_task_taken(_BrokenSession(), task, actor_ref="someone", how="accepted")
    assert "Starting the case of task" in " ".join(record.getMessage() for record in caplog.records)
    # Other tasks, and tasks without a case, are left alone (the session is never used).
    other = SimpleNamespace(id=uuid.uuid4(), task_type="EVIDENCE_REVIEW", investigation_id=uuid.uuid4())
    states.on_task_taken(None, other, actor_ref="someone", how="accepted")
    states.on_task_taken(
        None, SimpleNamespace(task_type="INVESTIGATION", investigation_id=None), actor_ref="x", how="y"
    )


# ------------------------------------------------------------------------------------------------------- scope


def _ids(count: int) -> list[str]:
    return [str(uuid.uuid4()) for _ in range(count)]


def test_scope_lists_are_cleaned():
    a, b = _ids(2)
    assert scope.id_list([a, a.upper(), "not an id", None, b]) == [a, b]
    assert scope.excluded_list(
        [{"complaint_id": a, "reason": "  Duplicate   report "}, {"complaint_id": a, "reason": "again"}, {}]
    ) == [{"complaint_id": a, "reason": "Duplicate report"}]
    assert scope.text_list([" EU ", "eu", "", "United  States"]) == ["EU", "United States"]


def test_a_complaint_cannot_be_both_included_and_excluded():
    a, b, c = _ids(3)
    assert scope.conflicting_complaints([a, b], [{"complaint_id": b, "reason": "Duplicate"}]) == [b]
    assert scope.conflicting_complaints([a], [{"complaint_id": c, "reason": "Duplicate"}]) == []


def test_the_scope_diff():
    a, b, c, d = _ids(4)
    v1, v2 = _ids(2)
    previous = {
        "question": "Why do alarms rise?",
        "included_complaint_ids": [a, b],
        "excluded_complaints": [{"complaint_id": d, "reason": "Duplicate"}],
        "product_version_ids": [v1],
    }
    current = {
        "question": "Why  do alarms rise after release B?",
        "included_complaint_ids": [a, c],
        "excluded_complaints": [{"complaint_id": b, "reason": "Wrong product"}, {"complaint_id": d, "reason": "Dup"}],
        "product_version_ids": [v2],
    }
    diff = scope.scope_diff(previous, current)
    assert diff == {
        "added_complaints": [c],
        "removed_complaints": [b],
        "newly_excluded": [b],
        "versions_added": [v2],
        "versions_removed": [v1],
        "question_changed": True,
    }
    assert scope.diff_counts(diff) == {
        "added_complaints": 1,
        "removed_complaints": 1,
        "newly_excluded": 1,
        "versions_added": 1,
        "versions_removed": 1,
        "question_changed": True,
    }
    # Only spacing differs: the question did not change.
    same = scope.scope_diff(previous, {**previous, "question": " Why do   alarms rise? "})
    assert not same["question_changed"] and not any(same[key] for key in same if key != "question_changed")
    first = scope.scope_diff(None, current)
    assert first["added_complaints"] == [a, c] and not first["question_changed"]


def test_scope_warnings_for_versions_and_dates():
    v1, v2 = _ids(2)
    complaints = [
        {"label": "CMP000001", "product_version_id": v1, "date": datetime(2026, 3, 1, tzinfo=timezone.utc)},
        {"label": "CMP000002", "product_version_id": v2, "date": datetime(2025, 12, 1, tzinfo=timezone.utc)},
        {"label": "CMP000003", "product_version_id": None, "date": None},
    ]
    warnings = scope.scope_warnings(complaints, [v1], date(2026, 1, 1), date(2026, 2, 1))
    assert warnings == [
        "CMP000001 is dated 2026-03-01, after the scope ends (2026-02-01)",
        "CMP000002 is on a product version outside the chosen versions",
        "CMP000002 is dated 2025-12-01, before the scope starts (2026-01-01)",
    ]
    assert scope.scope_warnings(complaints, [], None, None) == []


def test_the_creator_of_a_version_is_named():
    someone = str(uuid.uuid4())
    names = {someone: "Ada Investigator"}
    assert scope.creator_name(names, someone) == "Ada Investigator"
    assert scope.creator_name(names, "system:md29") == "MDARIX"
    assert scope.creator_name(names, None) is None
    assert scope.creator_name(names, str(uuid.uuid4())) is None


def test_scope_and_transition_requests_are_validated():
    from backend.app.case_workflow.router import ScopeRequest, TransitionRequest

    assert TransitionRequest(to_state="ON_HOLD", reason=f"  {REASON}  ").reason == REASON
    for body in (
        {"to_state": "ON_HOLD", "reason": "too short"},
        {"to_state": "ON_HOLD", "reason": "          x          "},
        {"to_state": "on_hold", "reason": REASON},
        {"to_state": "PAUSED", "reason": REASON},
    ):
        with pytest.raises(ValidationError):
            TransitionRequest(**body)

    complaint = str(uuid.uuid4())
    made = ScopeRequest(
        question="Why do occlusion alarms rise after release B?",
        markets=[" EU ", "eu", "US"],
        excluded_complaints=[{"complaint_id": complaint, "reason": "Duplicate report"}],
        date_from="2026-01-01",
        date_to="2026-02-01",
    )
    assert made.markets == ["EU", "US"] and made.change_reason is None and not made.reviews_must_restart
    for body in (
        {"question": "Too short"},
        {"question": "Why do alarms rise after release B?", "date_from": "2026-02-01", "date_to": "2026-01-01"},
        {"question": "Why do alarms rise after release B?", "change_reason": "short"},
        {
            "question": "Why do alarms rise after release B?",
            "excluded_complaints": [{"complaint_id": complaint, "reason": "no"}],
        },
        {"question": "Why do alarms rise after release B?", "markets": ["x" * 121]},
    ):
        with pytest.raises(ValidationError):
            ScopeRequest(**body)


# --------------------------------------------------------------------------------------------------- readiness


def _facts(**overrides) -> dict:
    facts = {
        "workflow_state": "IN_PROGRESS",
        "question": True,
        "scope": {"version": 2, "question": True, "included": 3},
        "evidence": {"total": 4, "unreviewed": 0},
        "requests": {"open": 1, "blocking": 0},
        "unknowns": {"total": 2, "open": 0},
        "analysis_run": True,
        "hypotheses": 2,
        "brief": {"latest_version": 1},
        "decision": {"count": 1, "signed": 1},
    }
    return {**facts, **overrides}


def _by_key(items: list[dict], field: str) -> dict:
    return {item["key"]: item[field] for item in items}


def test_readiness_steps_and_checks_are_in_order():
    result = readiness.evaluate(_facts())
    assert result["workflow_state"] == "IN_PROGRESS"
    assert [step["key"] for step in result["steps"]] == [
        "overview",
        "scope",
        "evidence",
        "analysis",
        "hypotheses",
        "gaps",
        "risk_regulatory",
        "brief",
        "human_review",
    ]
    assert [check["key"] for check in result["checks"]] == [
        "scope_complete",
        "evidence_reviewed",
        "analysis_run",
        "hypotheses_present",
        "unknowns",
        "no_blocking_request",
        "risk_review",
        "regulatory_review",
        "brief_ready",
        "decision",
    ]
    assert all(set(step) == {"key", "label", "status", "detail"} for step in result["steps"])
    assert all(set(check) == {"key", "label", "result", "rationale"} for check in result["checks"])
    assert {step["status"] for step in result["steps"]} <= set(readiness.STEP_STATUSES)
    assert {check["result"] for check in result["checks"]} <= set(readiness.CHECK_RESULTS)


def test_a_case_with_everything_done():
    result = readiness.evaluate(_facts())
    assert _by_key(result["steps"], "status") == {
        "overview": "DONE",
        "scope": "DONE",
        "evidence": "DONE",
        "analysis": "DONE",
        "hypotheses": "DONE",
        "gaps": "DONE",
        "risk_regulatory": "NOT_AVAILABLE",
        "brief": "DONE",
        "human_review": "DONE",
    }
    checks = _by_key(result["checks"], "result")
    assert checks == {
        "scope_complete": "PASS",
        "evidence_reviewed": "PASS",
        "analysis_run": "PASS",
        "hypotheses_present": "PASS",
        "unknowns": "PASS",
        "no_blocking_request": "PASS",
        "risk_review": "NOT_AVAILABLE",
        "regulatory_review": "NOT_AVAILABLE",
        "brief_ready": "PENDING",
        "decision": "PASS",
    }
    rationale = _by_key(result["checks"], "rationale")
    assert rationale["risk_review"] == "Recorded once risk and regulatory reviews are available"
    assert rationale["brief_ready"] == "Brief version 1 waits for its review"


def test_a_new_case_has_its_work_ahead():
    result = readiness.evaluate(
        _facts(
            scope={"version": 1, "question": True, "included": 0},
            evidence={"total": 0, "unreviewed": 0},
            requests={"open": 0, "blocking": 0},
            unknowns={"total": 0, "open": 0},
            analysis_run=False,
            hypotheses=0,
            brief={"latest_version": None},
            decision={"count": 0, "signed": 0},
        )
    )
    steps = _by_key(result["steps"], "status")
    assert steps["scope"] == "IN_PROGRESS" and steps["evidence"] == "NOT_STARTED" and steps["gaps"] == "NOT_STARTED"
    assert steps["analysis"] == steps["hypotheses"] == steps["brief"] == steps["human_review"] == "NOT_STARTED"
    checks = _by_key(result["checks"], "result")
    assert checks["scope_complete"] == "PENDING" and checks["evidence_reviewed"] == "PENDING"
    assert checks["brief_ready"] == "PENDING" and checks["decision"] == "PENDING" and checks["unknowns"] == "PASS"
    assert _by_key(result["checks"], "rationale")["evidence_reviewed"] == "No evidence on this case yet"


def test_unreviewed_evidence_open_questions_and_urgent_requests():
    result = readiness.evaluate(
        _facts(
            evidence={"total": 5, "unreviewed": 2},
            unknowns={"total": 3, "open": 2},
            requests={"open": 2, "blocking": 1},
            decision={"count": 1, "signed": 0},
        )
    )
    steps = _by_key(result["steps"], "status")
    assert steps["evidence"] == "BLOCKED" and steps["gaps"] == "IN_PROGRESS" and steps["human_review"] == "IN_PROGRESS"
    checks = _by_key(result["checks"], "result")
    assert checks["evidence_reviewed"] == "PENDING" and checks["unknowns"] == "PENDING"
    assert checks["no_blocking_request"] == "BLOCKED" and checks["decision"] == "PENDING"
    rationale = _by_key(result["checks"], "rationale")
    assert rationale["evidence_reviewed"] == "2 of 5 pieces of evidence are not reviewed yet"
    assert rationale["unknowns"] == "2 open questions still to answer"
    assert rationale["no_blocking_request"] == "1 high or critical evidence request still open"
    without_block = readiness.evaluate(_facts(evidence={"total": 5, "unreviewed": 2}))
    assert _by_key(without_block["steps"], "detail")["evidence"] == "2 of 5 still to review"


def test_facts_that_could_not_be_read_are_pending():
    result = readiness.evaluate(
        _facts(
            scope=None,
            evidence=None,
            requests=None,
            unknowns=None,
            analysis_run=None,
            hypotheses=None,
            brief=None,
            decision=None,
        )
    )
    checks = [check for check in result["checks"] if check["key"] not in ("risk_review", "regulatory_review")]
    assert all(check["result"] == "PENDING" for check in checks)
    assert all(check["rationale"] == readiness.UNREADABLE for check in checks)
    # Words people understand: no internal stage names.
    text = " ".join(
        [step["label"] + step["detail"] for step in result["steps"]]
        + [check["label"] + check["rationale"] for check in result["checks"]]
    ).lower()
    assert "phase" not in text and "stage" not in text


def test_the_evidence_request_and_unknown_rules():
    a, b, c = _ids(3)
    # Direct evidence counts as unreviewed unless the case has reviewed it through a link.
    assert readiness.evidence_counts([(a, "ACCEPTED"), (b, "UNREVIEWED")], [a, c]) == (3, 2)
    assert readiness.evidence_counts([], []) == (0, 0)
    assert readiness.request_is_open("SENT") and readiness.request_is_open("RECEIVED")
    assert not readiness.request_is_open("REVIEWED") and not readiness.request_is_open("CANCELLED")
    assert not readiness.request_is_open("CANNOT_PROVIDE") and not readiness.request_is_open("SENT", NOW)
    assert readiness.request_is_answered("REPLIED") and readiness.request_is_answered("OPEN", NOW)
    assert not readiness.request_is_answered("ACKNOWLEDGED")
    assert readiness.unknown_is_open("open") and readiness.unknown_is_open("REQUIRES_EXTERNAL_EVIDENCE")
    assert not readiness.unknown_is_open("RESOLVED") and not readiness.unknown_is_open("not_applicable")


# ------------------------------------------------------------------------------------------------------ routes


def test_the_case_workflow_routes_are_registered_and_need_a_session():
    from backend.app.main import app
    from backend.app.request_context import get_request_context
    from tests.route_inventory import api_routes

    def needs_session(dependant) -> bool:
        return any(dep.call is get_request_context or needs_session(dep) for dep in dependant.dependencies)

    ordered = [(method, path) for path, route in api_routes(app) for method in sorted(route.methods)]
    routes = {(method, path): route for path, route in api_routes(app) for method in route.methods}
    expected = {
        ("GET", "/api/v1/investigations/mine/summary"),
        ("POST", "/api/v1/investigations/{investigation_id}/transition"),
        ("GET", "/api/v1/investigations/{investigation_id}/scope"),
        ("PUT", "/api/v1/investigations/{investigation_id}/scope"),
        ("GET", "/api/v1/investigations/{investigation_id}/scope/versions/{version}"),
        ("GET", "/api/v1/investigations/{investigation_id}/readiness"),
    }
    assert expected <= set(routes)
    assert all(needs_session(routes[key].dependant) for key in expected)
    guards = [dep.dependency for dep in routes[("PUT", "/api/v1/investigations/{investigation_id}/scope")].dependencies]
    assert any("require_permission" in getattr(guard, "__qualname__", "") for guard in guards)
    # The fixed path is matched before any GET route that takes a case id in the same place.
    mine = ordered.index(("GET", "/api/v1/investigations/mine/summary"))
    assert all(
        index > mine
        for index, (method, path) in enumerate(ordered)
        if method == "GET" and path.startswith("/api/v1/investigations/{investigation_id}/")
    )
