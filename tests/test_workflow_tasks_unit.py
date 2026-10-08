"""Workflow tasks without a database: the task-type contract, the actions offered on a task, request validation, and
the rule that a task hook can never break the action that triggered it."""

from __future__ import annotations

import logging
import uuid
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from backend.app.workflow import hooks, tasks
from backend.app.workflow.labels import (
    MANUAL_COMPLETION_TYPES,
    TASK_TYPES,
    known_role,
    role_label,
    task_type,
    task_type_label,
)
from backend.app.workflow.router import Actor, CompleteRequest, ReasonRequest, ReassignRequest, _actions

pytestmark = pytest.mark.unit

# The shared contract: task type -> (permission to see the queue / claim / be assigned, default queue role).
CONTRACT = {
    "SIGNAL_TRIAGE": ("signal.triage", "TRIAGE_LEAD"),
    "INVESTIGATION": ("investigation.work", "INVESTIGATOR"),
    "EVIDENCE_REQUEST": ("investigation.work", "INVESTIGATOR"),
    "EVIDENCE_REVIEW": ("evidence.review", "INVESTIGATOR"),
    "RISK_REVIEW": ("risk.review", "RISK_REVIEWER"),
    "REGULATORY_REVIEW": ("regulatory.review", "REGULATORY_REVIEWER"),
    "QUALITY_REVIEW": ("quality.review", "REVIEWER"),
    "DECISION_APPROVAL": ("decision.sign", "APPROVER"),
    "IMPACT_ASSESSMENT": ("investigation.work", "INVESTIGATOR"),
    "FOLLOW_UP": ("investigation.work", "INVESTIGATOR"),
    # Phase 3: a colleague or a role asked for evidence answers it.
    "EVIDENCE_RESPONSE": ("evidence.request", "INVESTIGATOR"),
}


def test_every_task_type_matches_the_contract():
    assert {code: (item.permission, item.queue_role) for code, item in TASK_TYPES.items()} == CONTRACT
    assert MANUAL_COMPLETION_TYPES == {"FOLLOW_UP", "IMPACT_ASSESSMENT", "EVIDENCE_REVIEW"}
    assert all(task_type_label(code) for code in TASK_TYPES)
    with pytest.raises(ValueError):
        task_type("NOT_A_TYPE")


def test_task_permissions_are_real_permissions():
    from backend.app.access.permissions import ALL

    assert {item.permission for item in TASK_TYPES.values()} <= ALL
    assert "investigation.assign" in ALL


def test_role_labels_and_queue_roles():
    assert role_label("APPROVER") == "Authorized Decision Maker"
    assert role_label("Investigator") == "Quality Investigator"
    assert role_label(None) is None
    assert all(known_role(item.queue_role) for item in TASK_TYPES.values())
    # Administrators never hold case work, so no task queue belongs to them.
    assert not known_role("CUSTOMER_ADMIN") and not known_role("PLATFORM_ADMIN") and not known_role("NOBODY")


def test_titles_are_shortened_to_one_line():
    assert tasks.shorten("  Why do\nalarms rise?  ", 100) == "Why do alarms rise?"
    long = tasks.shorten("word " * 100, 40)
    assert len(long) <= 40 and long.endswith("…")
    assert tasks.shorten(None, 10) == ""


def test_an_unknown_task_type_is_refused_before_anything_is_written():
    with pytest.raises(ValueError):
        tasks.create_task(
            None,
            uuid.uuid4(),
            task_type="NOT_A_TYPE",
            title="x",
            source_type="Investigation",
            source_id=uuid.uuid4(),
            created_by="someone",
        )


def _task(**values):
    defaults = {
        "task_type": "INVESTIGATION",
        "status": "NEW",
        "assigned_user_id": None,
        "assigned_role": "INVESTIGATOR",
        "details": {},
    }
    return SimpleNamespace(**{**defaults, **values})


def _actor(*permissions, user=None):
    user = user or uuid.uuid4()
    return Actor(user_id=str(user), user_uuid=user, tenant_id=uuid.uuid4(), permissions=frozenset(permissions))


def test_a_queue_task_can_be_claimed_only_with_its_permission():
    assert _actions(_actor("investigation.work"), _task())["can_claim"] is True
    assert _actions(_actor(), _task())["can_claim"] is False
    assert _actions(_actor("decision.sign"), _task())["can_claim"] is False


def test_nobody_claims_the_approval_of_their_own_decision():
    me = _actor("decision.sign")
    own = _task(task_type="DECISION_APPROVAL", assigned_role="APPROVER", details={"decision_author_ref": me.user_id})
    other = _task(task_type="DECISION_APPROVAL", assigned_role="APPROVER", details={"decision_author_ref": "x"})
    assert _actions(me, own)["can_claim"] is False
    assert _actions(me, other)["can_claim"] is True


def test_a_follow_up_sent_to_a_role_can_be_taken_by_that_roles_holders():
    # Risk Reviewers hold no investigation.work, yet a decision maker may send them a risk reassessment follow-up.
    user = uuid.uuid4()
    risk_reviewer = Actor(
        user_id=str(user),
        user_uuid=user,
        tenant_id=uuid.uuid4(),
        permissions=frozenset({"risk.review"}),
        roles=["RISK_REVIEWER"],
    )
    sent_to_risk = _task(task_type="FOLLOW_UP", assigned_role="RISK_REVIEWER")
    sent_to_investigators = _task(task_type="FOLLOW_UP", assigned_role="INVESTIGATOR")
    assert _actions(risk_reviewer, sent_to_risk)["can_claim"] is True
    assert _actions(risk_reviewer, sent_to_investigators)["can_claim"] is False
    # Any other task type still needs its permission.
    assert (
        _actions(risk_reviewer, _task(task_type="INVESTIGATION", assigned_role="RISK_REVIEWER"))["can_claim"] is False
    )


def test_nobody_claims_the_review_or_decision_of_a_brief_they_wrote():
    me = _actor("quality.review", "decision.sign")
    wrote = {"brief_version": 2, "brief_author_refs": ["someone-else", me.user_id]}
    review = _task(task_type="QUALITY_REVIEW", assigned_role="REVIEWER", details=wrote)
    decide = _task(task_type="DECISION_APPROVAL", assigned_role="APPROVER", details=wrote)
    assert _actions(me, review)["can_claim"] is False
    assert _actions(me, decide)["can_claim"] is False
    others = {"brief_version": 2, "brief_author_refs": ["someone-else"], "brief_author_ref": "someone-else"}
    assert _actions(me, _task(task_type="QUALITY_REVIEW", assigned_role="REVIEWER", details=others))["can_claim"]


def test_only_the_assignee_accepts_declines_releases_and_completes():
    me = _actor("investigation.work")
    mine = _task(status="ASSIGNED", assigned_user_id=me.user_uuid)
    actions = _actions(me, mine)
    assert actions["can_accept"] and actions["can_decline"] and actions["can_release"]
    assert not actions["can_complete"]  # an investigation task ends with the case, not by hand
    assert not actions["can_claim"] and not actions["can_reassign"]
    someone_else = _actions(_actor("investigation.work"), mine)
    assert not any(someone_else[key] for key in ("can_accept", "can_decline", "can_release", "can_complete"))
    follow_up = _task(task_type="FOLLOW_UP", status="ACCEPTED", assigned_user_id=me.user_uuid, assigned_role=None)
    actions = _actions(me, follow_up)
    assert actions["can_complete"] and not actions["can_release"]  # no queue to release a personal task to


def test_reassigning_needs_investigation_assign_and_an_open_task():
    assigner = _actor("investigation.assign")
    assert _actions(assigner, _task(status="ASSIGNED", assigned_user_id=uuid.uuid4()))["can_reassign"]
    assert not _actions(assigner, _task(status="COMPLETED"))["can_reassign"]


def test_request_validation():
    with pytest.raises(ValidationError):
        ReasonRequest(reason="too short")
    with pytest.raises(ValidationError):
        ReasonRequest(reason="          x          ")
    with pytest.raises(ValidationError):
        ReassignRequest(reason="Moving this to the right person")
    assert ReassignRequest(reason="Moving this to the right queue", assigned_role="RISK_REVIEWER").assigned_role
    with pytest.raises(ValidationError):
        CompleteRequest(outcome="x" * 61)
    assert CompleteRequest().outcome is None


class _BrokenSession:
    """A session whose every use fails, to show a hook failure never escapes."""

    def __init__(self):
        self.rolled_back = False

    def begin_nested(self):
        raise RuntimeError("database unavailable")

    def rollback(self):
        self.rolled_back = True


def test_a_failing_hook_is_logged_and_never_raises(caplog):
    session = _BrokenSession()
    decision = SimpleNamespace(id=uuid.uuid4(), tenant_id=uuid.uuid4(), investigation_id=uuid.uuid4())
    with caplog.at_level(logging.ERROR, logger="mdarix.workflow"):
        hooks.on_decision_signed(session, decision, decision_value="APPROVE", actor_user_id=str(uuid.uuid4()))
        hooks.on_decision_material_change(session, decision, actor_user_id=str(uuid.uuid4()))
    assert session.rolled_back
    assert "Workflow task hook" in " ".join(record.getMessage() for record in caplog.records)
    assert tasks.run_hook(None, "nothing", lambda db: 1) is None


class _RecordingSession:
    def __init__(self):
        self.calls = []

    def begin_nested(self):
        calls = self.calls

        class _Savepoint:
            def __enter__(self):
                calls.append("savepoint")

            def __exit__(self, kind, value, traceback):
                calls.append("release" if kind is None else "rollback to savepoint")
                return False

        return _Savepoint()

    def commit(self):
        self.calls.append("commit")

    def rollback(self):
        self.calls.append("rollback")


def test_a_hook_runs_in_a_savepoint_then_commits():
    session = _RecordingSession()
    assert tasks.run_hook(session, "ok", lambda db, value: value * 2, 21) == 42
    assert session.calls == ["savepoint", "release", "commit"]

    def fails(db):
        raise ValueError("bad task")

    failing = _RecordingSession()
    assert tasks.run_hook(failing, "fails", fails) is None
    assert failing.calls == ["savepoint", "rollback to savepoint", "rollback"]


def test_case_business_id_never_raises():
    assert hooks.case_business_id(None, uuid.uuid4(), uuid.uuid4()) is None
    assert hooks.case_business_id(_BrokenSession(), uuid.uuid4(), None) is None


def test_the_task_routes_are_registered_and_need_a_session():
    from backend.app.main import app
    from backend.app.request_context import get_request_context
    from tests.route_inventory import api_routes

    def needs_session(dependant) -> bool:
        return any(dep.call is get_request_context or needs_session(dep) for dep in dependant.dependencies)

    routes = {
        (method, path): route
        for path, route in api_routes(app)
        if path.startswith("/api/v1/tasks")
        for method in route.methods
    }
    expected = {
        ("GET", "/api/v1/tasks"),
        ("GET", "/api/v1/tasks/summary"),
        ("GET", "/api/v1/tasks/{task_id}"),
        *(
            ("POST", f"/api/v1/tasks/{{task_id}}/{action}")
            for action in ("accept", "decline", "claim", "release", "reassign", "complete")
        ),
    }
    assert expected <= set(routes)
    assert all(needs_session(routes[key].dependant) for key in expected)
