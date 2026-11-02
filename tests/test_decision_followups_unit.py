"""What follows a signed decision, without a database: the closure rules of a case in the Decision Brief flow (and the
unchanged rules of any other case), impact conclusions and their rationale, the idempotency key of late evidence, the
follow-up actions a person may take and their request bodies, the CAPA numbering, the routes with their guards, the
scheduler job, the task source, retention and erasure of the two tables, and hooks that never raise."""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from backend.app.decision_followups import rules

pytestmark = pytest.mark.unit

RATIONALE = "The late service report repeats the known sensor drift"


def _facts(**changes) -> dict:
    """A case in the Decision Brief flow that meets every closure criterion, changed by ``changes``."""
    facts = {
        "closed": False,
        "awaiting_review": False,
        "applies": True,
        "decision": {"id": str(uuid.uuid4()), "business_id": "DEC000001", "outcome": "ACCEPT_CONCLUSION"},
        "open_assessments": 0,
        "open_reviews": 0,
        "urgent_requests": 0,
        "chosen": ["CAPA_REQUIRED"],
        "recorded": [{"action_type": "CAPA_REQUIRED", "has_task": True}],
        "reason": None,
    }
    facts.update(changes)
    return facts


def _results(facts: dict) -> dict[str, str]:
    return {item["key"]: item["result"] for item in rules.closure_criteria(facts)}


# ------------------------------------------------------------------------------------------------------ closure


def test_a_case_outside_the_brief_flow_keeps_todays_closing_rules():
    result = rules.closure_result({"closed": False, "awaiting_review": False, "applies": False})
    assert result["applies"] is False and result["can_close"] is True
    assert [item["key"] for item in result["criteria"]] == ["CASE_OPEN", "DECISIONS_REVIEWED"]
    waiting = rules.closure_result({"closed": False, "awaiting_review": True, "applies": False})
    assert waiting["can_close"] is False
    assert _results({"closed": False, "awaiting_review": True, "applies": False})["DECISIONS_REVIEWED"] == "BLOCKED"
    assert rules.closure_result({"closed": True, "applies": False})["can_close"] is False


def test_a_brief_case_meeting_every_criterion_can_close():
    result = rules.closure_result(_facts())
    assert result == {"can_close": True, "applies": True, "criteria": result["criteria"]}
    assert [item["key"] for item in result["criteria"]] == [
        "CASE_OPEN",
        "DECISIONS_REVIEWED",
        "SIGNED_DECISION",
        "IMPACT_ASSESSMENTS",
        "CASE_REVIEWS",
        "EVIDENCE_REQUESTS",
        "FOLLOW_UPS",
        "CLOSURE_REASON",
    ]
    for item in result["criteria"]:
        assert item["label"] == rules.CLOSURE_LABELS[item["key"]] and item["rationale"]
        assert item["result"] in ("PASS", "NOT_REQUIRED")
    for outcome in ("ACCEPT_CONCLUSION", "ACCEPT_WITH_CONDITIONS", "CLOSE_NO_FURTHER_ACTION"):
        decision = {"business_id": "DEC000002", "outcome": outcome}
        assert rules.closure_result(_facts(decision=decision))["can_close"] is True


def test_closure_needs_a_signed_decision_that_accepts_the_conclusion():
    assert _results(_facts(decision=None))["SIGNED_DECISION"] == "BLOCKED"
    assert _results(_facts(decision=None))["FOLLOW_UPS"] == "NOT_REQUIRED"
    rejected = _facts(decision={"business_id": "DEC000003", "outcome": "REJECT_CONCLUSION"})
    assert _results(rejected)["SIGNED_DECISION"] == "BLOCKED"
    assert rules.closure_result(rejected)["can_close"] is False


@pytest.mark.parametrize(
    ("change", "key"),
    [
        ({"open_assessments": 1}, "IMPACT_ASSESSMENTS"),
        ({"open_reviews": 2}, "CASE_REVIEWS"),
        ({"urgent_requests": 1}, "EVIDENCE_REQUESTS"),
        ({"reason": "too short"}, "CLOSURE_REASON"),
        ({"awaiting_review": True}, "DECISIONS_REVIEWED"),
        ({"closed": True}, "CASE_OPEN"),
    ],
)
def test_each_open_item_blocks_closure(change, key):
    facts = _facts(**change)
    assert _results(facts)[key] == "BLOCKED"
    result = rules.closure_result(facts)
    assert result["can_close"] is False
    assert [item["key"] for item in rules.blocked(result["criteria"])] == [key]


def test_every_follow_up_chosen_needs_its_record_and_task_but_may_stay_open():
    chosen = ["CAPA_REQUIRED", "CAPA_REQUIRED", "RISK_REASSESSMENT_REQUIRED"]
    one_capa = [
        {"action_type": "CAPA_REQUIRED", "has_task": True},
        {"action_type": "RISK_REASSESSMENT_REQUIRED", "has_task": True},
    ]
    blocked = rules.closure_criteria(_facts(chosen=chosen, recorded=one_capa))[-2]
    assert blocked["key"] == "FOLLOW_UPS" and blocked["result"] == "BLOCKED" and "CAPA required" in blocked["rationale"]
    without_task = [{"action_type": "CAPA_REQUIRED", "has_task": False}]
    assert _results(_facts(recorded=without_task))["FOLLOW_UPS"] == "BLOCKED"
    assert _results(_facts(recorded=[]))["FOLLOW_UPS"] == "BLOCKED"
    complete = [*one_capa, {"action_type": "CAPA_REQUIRED", "has_task": True}]
    assert _results(_facts(chosen=chosen, recorded=complete))["FOLLOW_UPS"] == "PASS"
    assert _results(_facts(chosen=[], recorded=[]))["FOLLOW_UPS"] == "NOT_REQUIRED"


def test_the_closing_reason_is_checked_when_given():
    assert _results(_facts(reason=None))["CLOSURE_REASON"] == "PASS"
    assert _results(_facts(reason="   short   "))["CLOSURE_REASON"] == "BLOCKED"
    assert _results(_facts(reason="The CAPA is open and tracked in the QMS"))["CLOSURE_REASON"] == "PASS"


def test_the_follow_ups_a_decision_chose_are_read_from_codes_or_objects():
    stored = [
        {"action_type": "CAPA_REQUIRED", "title": "Open a CAPA"},
        "risk_reassessment_required",
        {"type": "PRODUCT_CHANGE_REQUIRED"},
        {"action": "FIELD_ACTION_REVIEW_REQUIRED"},
        {"action_type": "NOT_AN_ACTION"},
        None,
        42,
    ]
    assert rules.chosen_actions(stored) == [
        "CAPA_REQUIRED",
        "RISK_REASSESSMENT_REQUIRED",
        "PRODUCT_CHANGE_REQUIRED",
        "FIELD_ACTION_REVIEW_REQUIRED",
    ]
    assert rules.chosen_actions(None) == [] and rules.chosen_actions([]) == []


# ------------------------------------------------------------------------------------------- impact assessments


def test_an_impact_conclusion_is_one_of_two_with_a_rationale_of_twenty_characters():
    for conclusion in ("NO_IMPACT", "MATERIAL_IMPACT"):
        payload = rules.ImpactCompletePayload(conclusion=conclusion, rationale=f"  {RATIONALE}  ")
        assert payload.conclusion == conclusion and payload.rationale == RATIONALE
    with pytest.raises(ValidationError):
        rules.ImpactCompletePayload(conclusion="SOME_IMPACT", rationale=RATIONALE)
    with pytest.raises(ValidationError):
        rules.ImpactCompletePayload(conclusion="no_impact", rationale=RATIONALE)
    with pytest.raises(ValidationError):
        rules.ImpactCompletePayload(conclusion="NO_IMPACT", rationale="Too short to say")
    with pytest.raises(ValidationError):
        rules.ImpactCompletePayload(conclusion="NO_IMPACT", rationale="  short  " + " " * 20)
    with pytest.raises(ValidationError):
        rules.ImpactCompletePayload(conclusion="NO_IMPACT", rationale="x" * 5001)
    assert rules.conclusion_label("MATERIAL_IMPACT").startswith("Material impact")
    assert rules.trigger_label("EVIDENCE_REQUEST_ACCEPTED") == "Evidence request answer accepted"
    assert rules.trigger_label(None) is None


def test_late_evidence_is_assessed_once_per_decision_and_evidence():
    decision, evidence = uuid.uuid4(), uuid.uuid4()
    assert rules.late_evidence_key(decision, evidence) == rules.late_evidence_key(str(decision), str(evidence))
    assert rules.late_evidence_key(decision, evidence) != rules.late_evidence_key(decision, uuid.uuid4())
    assert rules.late_evidence_key(decision, evidence) != rules.late_evidence_key(uuid.uuid4(), evidence)
    assert set(rules.DECIDED_STATES) == {"DECIDED", "CLOSED"}


def test_only_people_who_work_on_cases_complete_an_open_assessment():
    assert rules.impact_actions(status="OPEN", can_work=True) == {"can_complete": True}
    assert rules.impact_actions(status="OPEN", can_work=False) == {"can_complete": False}
    assert rules.impact_actions(status="COMPLETED", can_work=True) == {"can_complete": False}


# ---------------------------------------------------------------------------------------------------- follow-ups


def test_who_works_on_a_follow_up():
    me, other = uuid.uuid4(), uuid.uuid4()
    named = {"assignee_user_id": me, "assigned_role": "INVESTIGATOR"}
    assert rules.is_responsible(**named, user_uuid=me, role_codes=[]) is True
    # A named person keeps it: holding its role is not enough.
    assert rules.is_responsible(**named, user_uuid=other, role_codes=["INVESTIGATOR"]) is False
    by_role = {"assignee_user_id": None, "assigned_role": "Regulatory_Reviewer"}
    assert rules.is_responsible(**by_role, user_uuid=other, role_codes=["REGULATORY_REVIEWER"]) is True
    assert rules.is_responsible(**by_role, user_uuid=other, role_codes=["INVESTIGATOR"], holds_work=True) is False
    nobody = {"assignee_user_id": None, "assigned_role": None}
    assert rules.is_responsible(**nobody, user_uuid=other, role_codes=[], holds_work=True) is True
    assert rules.is_responsible(**nobody, user_uuid=other, role_codes=[], holds_work=False) is False
    assert rules.is_responsible(**named, user_uuid=None, role_codes=[]) is False


def test_follow_up_actions_follow_status_role_and_kind():
    def actions(**changes):
        values = {
            "status": "OPEN",
            "action_type": "CAPA_REQUIRED",
            "capa_id": None,
            "responsible": True,
            "can_assign": True,
            "can_work": True,
        }
        values.update(changes)
        return rules.follow_up_actions(**values)

    assert actions() == {
        "can_start": True,
        "can_complete": True,
        "can_cancel": True,
        "can_create_capa": True,
        "can_set_qms_reference": False,
    }
    assert actions(capa_id=uuid.uuid4())["can_set_qms_reference"] is True
    assert actions(capa_id=uuid.uuid4(), can_work=False)["can_set_qms_reference"] is False
    in_progress = actions(status="IN_PROGRESS")
    assert not in_progress["can_start"] and in_progress["can_complete"] and in_progress["can_cancel"]
    for finished in ("DONE", "CANCELLED"):
        done = actions(status=finished)
        assert not (done["can_start"] or done["can_complete"] or done["can_cancel"])
    assert actions(status="DONE")["can_create_capa"] is True
    assert actions(status="CANCELLED")["can_create_capa"] is False
    assert actions(capa_id=uuid.uuid4())["can_create_capa"] is False
    assert actions(action_type="RISK_REASSESSMENT_REQUIRED")["can_create_capa"] is False
    assert actions(can_work=False)["can_create_capa"] is False
    assert actions(responsible=False) == {
        "can_start": False,
        "can_complete": False,
        "can_cancel": True,
        "can_create_capa": True,
        "can_set_qms_reference": False,
    }
    assert actions(can_assign=False)["can_cancel"] is False


def test_follow_up_request_bodies():
    assert rules.FollowUpCompletePayload(note="  CAPA-INV1-1 opened and tracked  ").note == (
        "CAPA-INV1-1 opened and tracked"
    )
    for note in ("", "   too short   ", "x" * 5001):
        with pytest.raises(ValidationError):
            rules.FollowUpCompletePayload(note=note)
    assert rules.ReasonPayload(reason="  Duplicate of FUP000002  ").reason == "Duplicate of FUP000002"
    with pytest.raises(ValidationError):
        rules.ReasonPayload(reason="  no      ")
    capa = rules.CapaPayload(title="  Replace   the pressure  sensor ", due_at=datetime(2027, 1, 31, 12, 0))
    assert capa.title == "Replace the pressure sensor" and capa.due_at.tzinfo is not None
    assert rules.CapaPayload(title="Fix it").due_at is None
    for title in ("Fix", "  a  b  ", "x" * 256):
        with pytest.raises(ValidationError):
            rules.CapaPayload(title=title)


def test_capa_numbers_count_up_per_case():
    assert rules.capa_identifier("INV000147", []) == "CAPA-INV000147-1"
    assert rules.capa_identifier("INV000147", {"CAPA-INV000147-1", "CAPA-INV000147-2"}) == "CAPA-INV000147-3"
    assert rules.capa_identifier("INV000147", {"CAPA-INV000147-2"}) == "CAPA-INV000147-1"


def test_overdue_and_labels():
    now = datetime.now(timezone.utc)
    assert rules.is_overdue("OPEN", now - timedelta(days=1), now) is True
    assert rules.is_overdue("IN_PROGRESS", (now - timedelta(days=1)).replace(tzinfo=None), now) is True
    assert rules.is_overdue("DONE", now - timedelta(days=1), now) is False
    assert rules.is_overdue("OPEN", now + timedelta(days=1), now) is False
    assert rules.is_overdue("OPEN", None, now) is False
    assert rules.action_label("CAPA_REQUIRED") == "CAPA required"
    assert rules.status_label("IN_PROGRESS") == "In progress"
    assert set(rules.ACTION_LABELS) == {
        "CAPA_REQUIRED",
        "PRODUCT_CHANGE_REQUIRED",
        "FIELD_ACTION_REVIEW_REQUIRED",
        "RISK_REASSESSMENT_REQUIRED",
        "REGULATORY_ACTION_REQUIRED",
    }


# ------------------------------------------------------------------------------ routes, jobs, tasks, retention


def test_the_routes_and_their_guards():
    from backend.app.main import app
    from tests.route_inventory import api_routes

    routes = {(method, path): route for path, route in api_routes(app) for method in route.methods}

    def guarded(key) -> bool:
        return any(
            "require_permission" in getattr(dep.dependency, "__qualname__", "") for dep in routes[key].dependencies
        )

    for key in (
        ("POST", "/api/v1/follow-ups/{follow_up_id}/cancel"),
        ("POST", "/api/v1/follow-ups/{follow_up_id}/capa"),
        ("POST", "/api/v1/impact-assessments/{assessment_id}/complete"),
    ):
        assert key in routes and guarded(key), key
    for key in (
        ("GET", "/api/v1/investigations/{investigation_id}/follow-ups"),
        ("GET", "/api/v1/follow-ups"),
        ("GET", "/api/v1/follow-ups/{follow_up_id}"),
        ("POST", "/api/v1/follow-ups/{follow_up_id}/start"),
        ("POST", "/api/v1/follow-ups/{follow_up_id}/complete"),
        ("GET", "/api/v1/investigations/{investigation_id}/impact-assessments"),
        ("GET", "/api/v1/impact-assessments/{assessment_id}"),
        ("GET", "/api/v1/investigations/{investigation_id}/closure-check"),
    ):
        assert key in routes, key


def test_the_late_evidence_sweep_runs_hourly():
    from backend.app import scheduler

    job = next(job for job in scheduler.JOBS if job.name == "late_evidence_sweep")
    assert job.every == timedelta(minutes=60)


def test_impact_assessments_are_a_task_source_completed_by_their_conclusion():
    from backend.app.workflow import router as tasks_router
    from backend.app.workflow.labels import MANUAL_COMPLETION_TYPES, SOURCE_LABELS, TASK_TYPES

    assert SOURCE_LABELS[rules.IMPACT_SOURCE_TYPE] == "Impact assessment"
    assert tasks_router._source_models()[rules.IMPACT_SOURCE_TYPE].__tablename__ == "impact_assessments"
    assert TASK_TYPES[rules.IMPACT_TASK].permission == rules.INVESTIGATION_WORK
    assert rules.IMPACT_TASK in MANUAL_COMPLETION_TYPES and rules.FOLLOW_UP_TASK in MANUAL_COMPLETION_TYPES

    me = uuid.uuid4()
    actor = tasks_router.Actor(user_id=str(me), user_uuid=me, tenant_id=uuid.uuid4())

    def task(task_type: str, details: dict):
        return SimpleNamespace(
            task_type=task_type, details=details, status="ACCEPTED", assigned_user_id=me, assigned_role="INVESTIGATOR"
        )

    assessment_task = task("IMPACT_ASSESSMENT", {"impact_assessment_id": str(uuid.uuid4())})
    assert tasks_router._needs_impact_conclusion(assessment_task) is True
    assert tasks_router._actions(actor, assessment_task)["can_complete"] is False
    # An impact assessment task without an assessment, and every other manual task, still complete by hand.
    assert tasks_router._needs_impact_conclusion(task("IMPACT_ASSESSMENT", {})) is False
    assert tasks_router._actions(actor, task("IMPACT_ASSESSMENT", {}))["can_complete"] is True
    assert tasks_router._actions(actor, task("FOLLOW_UP", {"follow_up_id": str(uuid.uuid4())}))["can_complete"]


def test_the_two_tables_are_deleted_with_trial_data_and_kept_on_personal_erasure():
    from backend.app.tenant_purge import KEEP_TABLES, PERSONAL_ACCOUNT_TABLES
    from backend.app.trial.retention import TRIAL_DATA_TABLES

    order = {table: index for index, table in enumerate(TRIAL_DATA_TABLES)}
    assert order["decision_follow_ups"] < order["decisions"] < order["investigations"]
    assert order["impact_assessments"] < order["evidence"] < order["investigations"]
    assert order["capas"] < order["investigations"]
    for table in ("decision_follow_ups", "impact_assessments"):
        # Organization deletion and export discover every table with a tenant_id; erasing one person keeps these
        # business records (they hold account ids, never names or contact details).
        assert table not in KEEP_TABLES and table not in PERSONAL_ACCOUNT_TABLES
    from backend.app.db.models.decision_outcomes import DecisionFollowUp, ImpactAssessment

    for model in (DecisionFollowUp, ImpactAssessment):
        assert "tenant_id" in model.__table__.columns and "user_id" not in model.__table__.columns


# --------------------------------------------------------------------------------------------- hooks never raise


class _BrokenSession:
    def begin_nested(self):
        raise RuntimeError("database gone")

    def rollback(self):
        return None


def test_late_evidence_hooks_never_raise(caplog):
    from backend.app.decision_followups import impact

    tenant, case = uuid.uuid4(), uuid.uuid4()
    assert impact.after_late_evidence(None, None, tenant, case, [uuid.uuid4()], trigger="X", actor_ref="me") == 0
    assert impact.after_late_evidence(_BrokenSession(), None, tenant, case, [], trigger="X", actor_ref="me") == 0
    assert (
        impact.after_late_evidence(_BrokenSession(), None, tenant, None, [uuid.uuid4()], trigger="X", actor_ref="me")
        == 0
    )
    with caplog.at_level(logging.ERROR, logger="mdarix.workflow"):
        made = impact.after_late_evidence(
            _BrokenSession(), None, tenant, case, [uuid.uuid4()], trigger="EVIDENCE_LINKED", actor_ref="me"
        )
    assert made == 0
    assert any("late evidence" in record.getMessage() for record in caplog.records)
    assert impact.on_late_evidence(None, None, None, uuid.uuid4(), trigger="X", actor_ref="me") is None
    undecided = SimpleNamespace(workflow_state="IN_PROGRESS", status="open")
    assert impact.on_late_evidence(None, None, undecided, uuid.uuid4(), trigger="X", actor_ref="me") is None


def test_follow_up_hooks_never_raise(caplog):
    from backend.app.decision_followups import followups

    plain = SimpleNamespace(details={}, tenant_id=uuid.uuid4(), business_id="TSK000001", id=uuid.uuid4())
    assert followups.on_follow_up_task_completed(_BrokenSession(), plain, actor_ref="me") is None
    linked = SimpleNamespace(
        details={"follow_up_id": str(uuid.uuid4())}, tenant_id=uuid.uuid4(), business_id="TSK000002", id=uuid.uuid4()
    )
    with caplog.at_level(logging.ERROR, logger="mdarix.workflow"):
        assert followups.on_follow_up_task_completed(_BrokenSession(), linked, actor_ref="me") is None
        followups.on_case_closed(
            _BrokenSession(), None, SimpleNamespace(tenant_id=uuid.uuid4(), id=uuid.uuid4()), actor_user_id="me"
        )
    assert len(caplog.records) >= 2
