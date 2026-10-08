"""Case reviews without a database: the review policy and its reasons, which outcome fits which review, the review
checks of readiness (and their step), what a person may do with a review (no segregation of duties), the next-step
rules and request bodies, the task source, the routes with their guards, and hooks that never raise."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from backend.app.case_reviews import hooks, rules, service
from backend.app.case_workflow import readiness
from backend.app.db.models.reviews import REGULATORY_OUTCOMES, RISK_OUTCOMES

pytestmark = pytest.mark.unit

REASON = "The service reports point at the supplier change"
RATIONALE = "The complaints do not change the risk estimate of the occlusion hazard"


def _complaint(**flags) -> dict:
    return {"serious_injury": False, "death": False, "malfunction": False, **flags}


# ------------------------------------------------------------------------------------------------------ policy


def test_no_review_is_required_for_a_medium_case_without_harm():
    policy = rules.review_policy("MEDIUM", [_complaint(), _complaint()], [])
    assert policy == {
        "risk": {"required": False, "reasons": []},
        "regulatory": {"required": False, "reasons": []},
    }
    assert rules.review_policy(None, [], None)["risk"]["required"] is False


def test_priority_drives_the_risk_review_and_critical_also_the_regulatory_review():
    high = rules.review_policy("HIGH", [], [])
    assert high["risk"] == {"required": True, "reasons": ["The case priority is high"]}
    assert high["regulatory"] == {"required": False, "reasons": []}
    critical = rules.review_policy("critical", [], [])
    assert critical["risk"]["reasons"] == ["The case priority is critical"]
    assert critical["regulatory"] == {"required": True, "reasons": ["The case priority is critical"]}
    assert not rules.review_policy("LOW", [], [])["risk"]["required"]


def test_injuries_and_deaths_require_both_reviews_with_counted_reasons():
    policy = rules.review_policy(
        "MEDIUM", [_complaint(serious_injury=True), _complaint(serious_injury=True), _complaint(death=True)], []
    )
    assert policy["risk"]["reasons"] == [
        "2 complaints in scope report a serious injury",
        "1 complaint in scope reports a death",
    ]
    assert policy["regulatory"]["reasons"] == [
        "1 complaint in scope reports a death",
        "2 complaints in scope report a serious injury",
    ]
    assert policy["risk"]["required"] and policy["regulatory"]["required"]


def test_a_malfunction_requires_only_the_regulatory_review():
    policy = rules.review_policy("MEDIUM", [_complaint(malfunction=True), _complaint(malfunction=None)], [])
    assert policy["risk"] == {"required": False, "reasons": []}
    assert policy["regulatory"] == {"required": True, "reasons": ["1 complaint in scope reports a malfunction"]}


def test_a_linked_signal_with_serious_harm_requires_the_risk_review():
    harmful = SimpleNamespace(business_id="SIG000004", serious_harm=True)
    harmless = {"business_id": "SIG000005", "serious_harm": False}
    one = rules.review_policy("MEDIUM", [], [harmful, harmless])
    assert one["risk"] == {"required": True, "reasons": ["Signal SIG000004 reports serious harm"]}
    assert not one["regulatory"]["required"]
    two = rules.review_policy("LOW", [], [harmful, {"business_id": "SIG000009", "serious_harm": True}])
    assert two["risk"]["reasons"] == ["2 linked signals report serious harm (SIG000004, SIG000009)"]


def test_every_rule_that_applies_gives_its_reason():
    policy = rules.review_policy(
        "CRITICAL",
        [_complaint(serious_injury=True, death=True, malfunction=True)],
        [{"business_id": "SIG000001", "serious_harm": True}],
    )
    assert policy["risk"]["reasons"] == [
        "The case priority is critical",
        "1 complaint in scope reports a serious injury",
        "1 complaint in scope reports a death",
        "Signal SIG000001 reports serious harm",
    ]
    assert policy["regulatory"]["reasons"] == [
        "The case priority is critical",
        "1 complaint in scope reports a death",
        "1 complaint in scope reports a serious injury",
        "1 complaint in scope reports a malfunction",
    ]


# ----------------------------------------------------------------------------------------------------- outcomes


def test_each_review_type_has_its_own_outcomes():
    for outcome in RISK_OUTCOMES:
        assert rules.outcome_problem("RISK", outcome) is None
        assert rules.outcome_label(outcome) and "_" not in rules.outcome_label(outcome)
    for outcome in REGULATORY_OUTCOMES:
        assert rules.outcome_problem("REGULATORY", outcome) is None
        assert rules.outcome_label(outcome) and "_" not in rules.outcome_label(outcome)
    assert rules.outcome_problem("RISK", "REPORTING_REQUIRED")
    assert rules.outcome_problem("REGULATORY", "NO_CHANGE_REQUIRED")
    assert rules.outcome_problem("RISK", "ESCALATE_REGULATORY")
    assert rules.outcome_problem("RISK", None) and rules.outcome_problem("QUALITY", "NO_CHANGE_REQUIRED")
    # Both review types can ask for more evidence; those outcomes and the escalations send the case back.
    assert rules.outcome_problem("RISK", "additional_evidence_required") is None
    assert rules.outcome_problem("REGULATORY", "ADDITIONAL_EVIDENCE_REQUIRED") is None
    assert rules.BLOCKING_OUTCOMES == {"ADDITIONAL_EVIDENCE_REQUIRED", "ESCALATE_SAFETY_CONCERN", "ESCALATE_REGULATORY"}
    assert rules.is_blocking_outcome("escalate_safety_concern") and not rules.is_blocking_outcome("REPORTING_REQUIRED")


def test_the_completion_body():
    body = rules.CompletePayload(
        outcome=" no_change_required ",
        rationale=RATIONALE,
        assessed={"risk_ids": [str(uuid.UUID(int=1))] * 2, "markets": ["EU", "eu", " US "], "notes": "  "},
    )
    assert body.outcome == "NO_CHANGE_REQUIRED"
    assert body.assessed.risk_ids == [uuid.UUID(int=1)]
    assert body.assessed.markets == ["EU", "US"] and body.assessed.notes is None
    assert rules.CompletePayload(outcome="NO_CHANGE_REQUIRED", rationale=RATIONALE).assessed.risk_ids == []
    for bad in (
        {"outcome": "NO_CHANGE_REQUIRED", "rationale": "Too short"},
        {"outcome": "NO_CHANGE_REQUIRED", "rationale": "x" * 5001},
        {"outcome": "NO_CHANGE_REQUIRED", "rationale": RATIONALE, "assessed": {"markets": ["x" * 121]}},
        {"outcome": "NO_CHANGE_REQUIRED", "rationale": RATIONALE, "assessed": {"risk_ids": ["not-an-id"]}},
    ):
        with pytest.raises(ValidationError):
            rules.CompletePayload(**bad)


def test_the_request_and_reason_bodies():
    request = rules.ReviewRequestPayload(review_type="risk", reason="  Serious   injury reported  ")
    assert request.review_type == "RISK" and request.reason == "Serious injury reported" and request.due_at is None
    future = datetime.now(timezone.utc) + timedelta(days=3)
    assert rules.ReviewRequestPayload(review_type="REGULATORY", due_at=future).due_at == future
    for bad in (
        {"review_type": "QUALITY"},
        {"review_type": "RISK", "due_at": datetime.now(timezone.utc) - timedelta(days=1)},
    ):
        with pytest.raises(ValidationError):
            rules.ReviewRequestPayload(**bad)
    assert rules.ReasonPayload(reason="  Not my area of expertise ").reason == "Not my area of expertise"
    with pytest.raises(ValidationError):
        rules.ReasonPayload(reason="short")


# --------------------------------------------------------------------------------------------------- readiness


def _facts(reviews) -> dict:
    return {
        "workflow_state": "IN_PROGRESS",
        "question": True,
        "scope": {"version": 1, "question": True, "included": 1},
        "evidence": {"total": 1, "unreviewed": 0},
        "requests": {"open": 0, "blocking": 0},
        "unknowns": {"total": 0, "open": 0},
        "analysis_run": True,
        "people_analysis": 0,
        "hypotheses": 1,
        "contradictions": {"total": 0, "undocumented": []},
        "brief": {"latest_version": None},
        "decision": {"count": 0, "signed": 0},
        "reviews": reviews,
    }


def _fact(required=False, reasons=(), latest=None) -> dict:
    return {"required": required, "reasons": list(reasons), "latest": latest}


def _latest(status: str, outcome: str | None = None, business_id: str = "REV000007") -> dict:
    return {"business_id": business_id, "status": status, "outcome": outcome}


def _review_result(reviews) -> tuple[dict, dict, dict]:
    result = readiness.evaluate(_facts(reviews))
    checks = {check["key"]: check for check in result["checks"]}
    step = next(step for step in result["steps"] if step["key"] == "risk_regulatory")
    return checks["risk_review"], checks["regulatory_review"], step


def test_a_required_review_nobody_asked_for_blocks_the_case():
    risk, regulatory, step = _review_result(
        {
            "RISK": _fact(True, ["The case priority is high", "2 complaints in scope report a serious injury"]),
            "REGULATORY": _fact(False),
        }
    )
    assert risk["result"] == "BLOCKED"
    assert risk["rationale"] == (
        "Request a risk review: required because the case priority is high; "
        "2 complaints in scope report a serious injury"
    )
    assert regulatory["result"] == "NOT_REQUIRED" and regulatory["rationale"] == "Not required by policy"
    assert step["status"] == "BLOCKED" and step["detail"] == "Risk review must be completed"


def test_requested_and_in_progress_reviews_are_pending():
    risk, regulatory, step = _review_result(
        {
            "RISK": _fact(True, ["The case priority is high"], _latest("REQUESTED")),
            "REGULATORY": _fact(False, latest=_latest("IN_PROGRESS", business_id="REV000008")),
        }
    )
    assert risk["result"] == regulatory["result"] == "PENDING"
    assert risk["rationale"] == "Risk review REV000007 is requested and waits for a reviewer"
    assert regulatory["rationale"] == "Regulatory review REV000008 is in progress"
    assert step["status"] == "IN_PROGRESS" and step["detail"] == "Risk review and regulatory review in progress"


def test_a_completed_review_passes_and_one_asking_for_more_blocks():
    risk, regulatory, step = _review_result(
        {
            "RISK": _fact(True, ["x"], _latest("COMPLETED", "RISK_CONTROL_REVIEW_REQUIRED")),
            "REGULATORY": _fact(True, ["y"], _latest("COMPLETED", "REPORTING_REQUIRED", "REV000009")),
        }
    )
    assert risk["result"] == regulatory["result"] == "PASS"
    assert risk["rationale"] == "Risk review REV000007 completed: Risk control review required"
    assert regulatory["rationale"] == "Regulatory review REV000009 completed: Reporting required"
    assert step == {
        "key": "risk_regulatory",
        "label": "Risk and regulatory review",
        "status": "DONE",
        "detail": "Risk review completed; regulatory review completed",
    }
    for outcome in ("ADDITIONAL_EVIDENCE_REQUIRED", "ESCALATE_SAFETY_CONCERN"):
        risk, _, step = _review_result(
            {"RISK": _fact(False, latest=_latest("COMPLETED", outcome)), "REGULATORY": _fact(False)}
        )
        assert risk["result"] == "BLOCKED" and step["status"] == "BLOCKED"
        assert risk["rationale"] == (
            f"Risk review REV000007 concluded: {rules.outcome_label(outcome)}. A new risk review must be completed"
        )
    _, regulatory, _ = _review_result(
        {"RISK": _fact(False), "REGULATORY": _fact(False, latest=_latest("COMPLETED", "ESCALATE_REGULATORY"))}
    )
    assert regulatory["result"] == "BLOCKED"


def test_reviews_not_required_by_policy():
    risk, regulatory, step = _review_result({"RISK": _fact(False), "REGULATORY": _fact(False)})
    assert risk["result"] == regulatory["result"] == "NOT_REQUIRED"
    assert step["status"] == "DONE" and step["detail"] == "Not required by policy"


def test_reviews_that_could_not_be_read_are_pending():
    risk, regulatory, step = _review_result(None)
    assert risk["result"] == regulatory["result"] == "PENDING"
    assert risk["rationale"] == regulatory["rationale"] == readiness.UNREADABLE
    assert step["status"] == "NOT_STARTED" and step["detail"] == readiness.UNREADABLE
    risk, regulatory, step = _review_result({"RISK": _fact(False)})
    assert risk["result"] == "NOT_REQUIRED" and regulatory["result"] == "PENDING"
    assert step["status"] == "IN_PROGRESS"
    # The other checks keep their own rules.
    result = readiness.evaluate(_facts({"RISK": _fact(True), "REGULATORY": _fact(True)}))
    checks = {check["key"]: check["result"] for check in result["checks"]}
    assert checks["scope_complete"] == "PASS" and checks["unknowns"] == "PASS" and checks["decision"] == "PENDING"
    assert {check["result"] for check in result["checks"]} <= set(readiness.CHECK_RESULTS)
    assert {step["status"] for step in result["steps"]} <= set(readiness.STEP_STATUSES)


# ----------------------------------------------------------------------------------------------------- actions


def test_what_a_person_may_do_with_a_review():
    def actions(**overrides):
        values = {
            "status": "REQUESTED",
            "holds_type_permission": True,
            "is_reviewer": False,
            "is_requester": False,
            "can_assign": False,
            "case_open": True,
        }
        return rules.review_actions(**{**values, **overrides})

    assert actions() == {"can_start": True, "can_complete": False, "can_recuse": False, "can_cancel": False}
    # No segregation of duties: whoever asked for the review may review it when they hold the permission.
    assert actions(is_requester=True)["can_start"] and actions(is_requester=True)["can_cancel"]
    assert not actions(holds_type_permission=False)["can_start"]
    assert not actions(case_open=False)["can_start"] and not actions(task_taken_by_other=True)["can_start"]
    working = actions(status="IN_PROGRESS", is_reviewer=True)
    assert working == {"can_start": False, "can_complete": True, "can_recuse": True, "can_cancel": False}
    assert not actions(status="IN_PROGRESS", is_reviewer=False)["can_complete"]
    assert actions(status="IN_PROGRESS", can_assign=True)["can_cancel"]
    for finished in ("COMPLETED", "CANCELLED", "SUPERSEDED"):
        assert not any(actions(status=finished, is_reviewer=True, is_requester=True, can_assign=True).values())


def test_overdue_reviews():
    now = datetime(2026, 10, 6, 12, 0, tzinfo=timezone.utc)
    yesterday = now - timedelta(days=1)
    assert rules.is_overdue("REQUESTED", yesterday, now) and rules.is_overdue("IN_PROGRESS", yesterday, now)
    assert not rules.is_overdue("COMPLETED", yesterday, now) and not rules.is_overdue("REQUESTED", None, now)
    assert not rules.is_overdue("REQUESTED", now + timedelta(days=1), now)
    assert rules.is_overdue("REQUESTED", yesterday.replace(tzinfo=None), now)


# -------------------------------------------------------------------------------------------------- next steps


def test_the_old_decision_options_are_all_next_steps():
    old = {
        "CONTINUE_INVESTIGATION",
        "REQUEST_ADDITIONAL_EVIDENCE",
        "REQUEST_ADDITIONAL_TESTING",
        "REVIEW_SUPPLIER_CHANGE",
        "REVIEW_PRODUCT_CHANGE",
        "ESCALATE_FOR_QUALITY_REVIEW",
        "NO_DECISION_YET",
    }
    assert old <= set(rules.NEXT_STEP_CODES)
    assert {"REQUEST_RISK_REVIEW", "REQUEST_REGULATORY_REVIEW"} <= set(rules.NEXT_STEP_CODES)
    assert len(rules.NEXT_STEP_CODES) == len(set(rules.NEXT_STEP_CODES)) == 9
    assert all(label and description for _, label, description in rules.NEXT_STEPS)


def test_the_next_step_body():
    body = rules.NextStepPayload(action=" continue_investigation ", reason=REASON)
    assert body.action == "CONTINUE_INVESTIGATION" and body.details is None
    for bad in (
        {"action": "APPROVE", "reason": REASON},
        {"action": "NO_DECISION_YET", "reason": "short"},
        {"action": "NO_DECISION_YET", "reason": "x" * 2001},
    ):
        with pytest.raises(ValidationError):
            rules.NextStepPayload(**bad)


def test_the_details_of_each_next_step():
    assert rules.next_step_details("CONTINUE_INVESTIGATION", {"anything": 1}) is None
    assert rules.next_step_details("REQUEST_RISK_REVIEW", None).due_at is None
    with pytest.raises(ValidationError):
        rules.next_step_details("REQUEST_REGULATORY_REVIEW", {"due_at": "2020-01-01T00:00:00Z"})
    evidence = rules.next_step_details(
        "REQUEST_ADDITIONAL_EVIDENCE",
        {"title": "  Lot   history ", "requested_items": ["Batch record"], "recipient_role": "INVESTIGATOR"},
    )
    assert evidence.title == "Lot history" and evidence.priority == "MEDIUM" and evidence.recipient_user_id is None
    for bad in (
        {"title": "Lot history", "requested_items": ["Batch record"]},
        {"title": "Lot history", "requested_items": [], "recipient_role": "INVESTIGATOR"},
        {"title": "x", "requested_items": ["Batch record"], "recipient_role": "INVESTIGATOR"},
    ):
        with pytest.raises(ValidationError):
            rules.next_step_details("REQUEST_ADDITIONAL_TESTING", bad)
    change = rules.next_step_details("REVIEW_SUPPLIER_CHANGE", {"assigned_role": " INVESTIGATOR "})
    assert change.assigned_role == "INVESTIGATOR" and change.assignee_user_id is None and change.title is None
    assert rules.next_step_details("REVIEW_PRODUCT_CHANGE", {}).assigned_role is None


def test_next_step_titles():
    assert rules.testing_title("Burst pressure on lot 42") == "Testing: Burst pressure on lot 42"
    assert rules.testing_title("testing: Burst pressure") == "Testing: Burst pressure"
    assert len(rules.testing_title("x" * 300)) == rules.EVIDENCE_TITLE_MAX
    assert rules.change_title("REVIEW_SUPPLIER_CHANGE", "INV000147") == "Review supplier change for INV000147"
    assert rules.change_title("REVIEW_PRODUCT_CHANGE", "INV000147") == "Review product change for INV000147"


def test_which_next_steps_a_person_may_take():
    def available(action, **overrides):
        values = {"can_work": True, "can_request_evidence": True, "case_open": True, "open_review_types": ()}
        return rules.next_step_availability(action, **{**values, **overrides})

    assert available("CONTINUE_INVESTIGATION") == (True, None)
    assert available("ESCALATE_FOR_QUALITY_REVIEW") == (False, rules.USE_DECISION_BRIEF)
    assert rules.USE_DECISION_BRIEF == "Prepare and submit the Decision Brief for quality review"
    assert available("NO_DECISION_YET", can_work=False)[0] is False
    assert available("REQUEST_RISK_REVIEW", case_open=False) == (False, "The case is closed")
    assert available("REQUEST_ADDITIONAL_TESTING", can_request_evidence=False)[0] is False
    assert available("REVIEW_PRODUCT_CHANGE", can_request_evidence=False) == (True, None)
    assert available("REQUEST_RISK_REVIEW", open_review_types={"RISK"}) == (False, "A risk review is already open")
    assert available("REQUEST_REGULATORY_REVIEW", open_review_types={"RISK"}) == (True, None)


# ------------------------------------------------------------------------------------------- tasks and routes


def test_reviews_are_a_task_source_with_their_queues():
    from backend.app.workflow.labels import SOURCE_LABELS, TASK_TYPES
    from backend.app.workflow.router import _source_models

    assert SOURCE_LABELS[rules.SOURCE_TYPE] == "Case review"
    assert _source_models()[rules.SOURCE_TYPE].__tablename__ == "case_reviews"
    assert TASK_TYPES[rules.TYPE_TASKS["RISK"]].permission == rules.TYPE_PERMISSIONS["RISK"] == "risk.review"
    assert TASK_TYPES[rules.TYPE_TASKS["REGULATORY"]].queue_role == "REGULATORY_REVIEWER"
    assert TASK_TYPES[rules.TYPE_TASKS["REGULATORY"]].permission == "regulatory.review"
    review = SimpleNamespace(review_type="RISK")
    assert hooks.task_title(review, "INV000147") == "Risk review of INV000147"


def test_review_hooks_and_the_scope_restart_never_raise(caplog):
    class _BrokenSession:
        def __init__(self):
            self.rolled_back = False

        def begin_nested(self):
            raise RuntimeError("database unavailable")

        def rollback(self):
            self.rolled_back = True

        def commit(self):  # pragma: no cover - never reached
            raise AssertionError("nothing to commit")

    review = SimpleNamespace(
        id=uuid.uuid4(),
        tenant_id=uuid.uuid4(),
        investigation_id=uuid.uuid4(),
        business_id="REV000001",
        review_type="RISK",
        reviewer_user_id=uuid.uuid4(),
        outcome="ADDITIONAL_EVIDENCE_REQUIRED",
        rationale=RATIONALE,
        due_at=None,
    )
    case = SimpleNamespace(
        id=review.investigation_id, tenant_id=review.tenant_id, business_id="INV000001", owner_ref=None, priority="HIGH"
    )
    session = _BrokenSession()
    with caplog.at_level(logging.ERROR):
        hooks.on_review_requested(session, review, actor_user_id=uuid.uuid4(), case_reference="INV000001")
        hooks.on_review_started(session, review, actor_user_id=uuid.uuid4())
        hooks.on_review_completed(session, None, review, case, actor_user_id=uuid.uuid4())
        hooks.on_review_recused(session, review, actor_user_id=uuid.uuid4(), reason=REASON)
        hooks.on_review_cancelled(session, review, actor_user_id=uuid.uuid4(), reason=REASON)
        assert service.restart_reviews(_BrokenSession(), case, version=3, actor_ref="someone") == 0
    assert session.rolled_back
    assert "Workflow task hook" in caplog.text and "could not be restarted" in caplog.text


def test_the_review_routes_are_registered_and_guarded():
    from backend.app.main import app
    from backend.app.request_context import get_request_context
    from tests.route_inventory import api_routes

    def needs_session(dependant) -> bool:
        return any(dep.call is get_request_context or needs_session(dep) for dep in dependant.dependencies)

    def guarded(route) -> bool:
        return any("require_permission" in getattr(dep.dependency, "__qualname__", "") for dep in route.dependencies)

    ordered = [(method, path) for path, route in api_routes(app) for method in sorted(route.methods)]
    routes = {(method, path): route for path, route in api_routes(app) for method in route.methods}
    expected = {
        ("GET", "/api/v1/investigations/{investigation_id}/reviews/policy"),
        ("GET", "/api/v1/investigations/{investigation_id}/reviews"),
        ("POST", "/api/v1/investigations/{investigation_id}/reviews"),
        ("GET", "/api/v1/case-reviews/summary"),
        ("GET", "/api/v1/case-reviews"),
        ("GET", "/api/v1/case-reviews/{review_id}"),
        ("POST", "/api/v1/case-reviews/{review_id}/start"),
        ("POST", "/api/v1/case-reviews/{review_id}/complete"),
        ("POST", "/api/v1/case-reviews/{review_id}/recuse"),
        ("POST", "/api/v1/case-reviews/{review_id}/cancel"),
        ("GET", "/api/v1/investigations/{investigation_id}/next-steps/options"),
        ("POST", "/api/v1/investigations/{investigation_id}/next-steps"),
    }
    assert expected <= set(routes)
    assert all(needs_session(routes[key].dependant) for key in expected)
    assert guarded(routes[("POST", "/api/v1/investigations/{investigation_id}/reviews")])
    assert guarded(routes[("POST", "/api/v1/investigations/{investigation_id}/next-steps")])
    # The fixed path is matched before the review id in the same place.
    assert ordered.index(("GET", "/api/v1/case-reviews/summary")) < ordered.index(
        ("GET", "/api/v1/case-reviews/{review_id}")
    )
    # The decision endpoints stay as they were.
    assert ("POST", "/api/v1/investigations/{investigation_id}/decisions") in routes
