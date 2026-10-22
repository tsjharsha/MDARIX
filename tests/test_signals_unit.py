"""Signals without a database: problem keys, grouping, suggested priority and due dates, the detection plan and its
idempotency, triage decisions, request validation, the actions offered, and hooks that never break their action."""

from __future__ import annotations

import uuid
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from backend.app.db.models.signals import OPEN_SIGNAL_STATUSES, SIGNAL_PRIORITIES, SIGNAL_STATUSES
from backend.app.signals import hooks, logic
from backend.app.signals.labels import (
    DUE_DAYS,
    EVENT_LABELS,
    PRIORITY_RANK,
    STATUS_LABELS,
    THRESHOLD_DEFAULTS,
    TRIAGE_TASK,
)
from backend.app.signals.logic import ComplaintFacts, SignalRuleError

pytestmark = pytest.mark.unit

NOW = datetime(2026, 10, 6, 12, 0, tzinfo=timezone.utc)
TODAY = NOW.date()


def _complaint(product=None, version=None, key="OCCLUSION", days=1, **extra) -> ComplaintFacts:
    return ComplaintFacts(
        id=uuid.uuid4(),
        product_id=product,
        product_version_id=version,
        problem_key=key,
        event_at=NOW - timedelta(days=days),
        **extra,
    )


def test_labels_cover_every_status_and_priority():
    assert set(STATUS_LABELS) == set(SIGNAL_STATUSES)
    assert set(PRIORITY_RANK) == set(DUE_DAYS) == set(SIGNAL_PRIORITIES)
    assert THRESHOLD_DEFAULTS == {"min_complaints": 3, "window_days": 30}
    assert {"CREATED", "DISPOSITIONED", "MERGED_INTO", "MERGED_FROM", "MONITOR_TRIGGERED"} <= set(EVENT_LABELS)


def test_problem_key_prefers_the_problem_code_then_the_complaint_type():
    assert logic.problem_key("  occlusion   alarm ", "Malfunction") == "OCCLUSION ALARM"
    assert logic.problem_key(None, " malfunction ") == "MALFUNCTION"
    assert logic.problem_key("", "  ") == "UNSPECIFIED"
    assert len(logic.problem_key("x" * 500, None)) == logic.PROBLEM_KEY_LENGTH


def test_event_time_falls_back_to_received_then_recorded():
    a, b, c = NOW, NOW - timedelta(days=1), NOW - timedelta(days=2)
    assert logic.event_time(a, b, c) == a
    assert logic.event_time(None, b, c) == b
    assert logic.event_time(None, None, c) == c


def test_highest_severity_ranks_known_severities_first():
    assert logic.highest_severity(["minor", None, "Serious", "moderate"]) == "SERIOUS"
    assert logic.highest_severity(["odd", "minor"]) == "MINOR"
    assert logic.highest_severity(["odd", "other"]) == "ODD"
    assert logic.highest_severity([None, ""]) is None


def test_highest_severity_does_not_depend_on_the_order_the_complaints_are_read_in():
    # 0.10.43: two different unrecognised severities (or two known ones of the same rank) gave whichever was read
    # first, and the reads have no ORDER BY. The first in alphabetical order is kept, whatever the order.
    for values, expected in (
        (["Grade B", "grade a", None, "Grade  C"], "GRADE A"),
        (["Unclassified", "Pending review"], "PENDING REVIEW"),
        (["severe", "Serious"], "SERIOUS"),
        (["major", "HIGH"], "HIGH"),
        (["medium", "Moderate", "odd"], "MEDIUM"),
        (["zeta", "alpha", "Minor"], "MINOR"),  # a known severity still outranks every unknown one
    ):
        for ordered in (values, list(reversed(values)), values[1:] + values[:1]):
            assert logic.highest_severity(ordered) == expected, ordered
    facts = [
        ComplaintFacts(
            id=uuid.uuid4(), product_id=None, product_version_id=None, problem_key="X", event_at=None, severity=s
        )
        for s in ("Level 3", "Level 1", "Level 2")
    ]
    assert logic.summarize(facts).highest_severity == "LEVEL 1"
    assert logic.summarize(reversed(facts)).highest_severity == "LEVEL 1"


@pytest.mark.parametrize(
    ("rows", "expected"),
    [
        ([_complaint(death=True), _complaint()], "CRITICAL"),
        ([_complaint(serious_injury=True)], "HIGH"),
        ([_complaint(severity="major")], "HIGH"),
        ([_complaint(severity="Severe")], "HIGH"),
        ([_complaint() for _ in range(6)], "MEDIUM"),
        ([_complaint() for _ in range(5)], "LOW"),
        ([], "LOW"),
    ],
)
def test_suggested_priority(rows, expected):
    assert logic.suggested_priority(logic.summarize(rows), 3) == expected


def test_summary_of_complaints():
    rows = [_complaint(days=10, severity="minor"), _complaint(days=2, serious_injury=True)]
    facts = logic.summarize(rows)
    assert facts.count == 2 and facts.serious_harm and not facts.death
    assert facts.first_event_at == NOW - timedelta(days=10) and facts.last_event_at == NOW - timedelta(days=2)
    assert facts.highest_severity == "MINOR"


def test_due_dates_by_priority():
    assert logic.due_at("CRITICAL", NOW) == NOW + timedelta(days=1)
    assert logic.due_at("HIGH", NOW) == NOW + timedelta(days=3)
    assert logic.due_at("MEDIUM", NOW) == NOW + timedelta(days=5)
    assert logic.due_at("LOW", NOW) == NOW + timedelta(days=10)
    assert logic.due_at(None, NOW) == NOW + timedelta(days=10)
    assert logic.effective_priority("HIGH", "LOW") == "HIGH" and logic.effective_priority(None, "LOW") == "LOW"


def test_rule_titles():
    assert (
        logic.rule_title(4, "OCCLUSION_ALARM", "Aster Pump", "Rev C", 30)
        == "4 complaints: occlusion alarm on Aster Pump Rev C in 30 days"
    )
    assert (
        logic.rule_title(1, "UNSPECIFIED", None, None, 7)
        == "1 complaint: unspecified problem on unknown product in 7 days"
    )
    assert len(logic.rule_title(3, "X" * 400, "P", None, 30)) <= logic.TITLE_LENGTH


def test_rule_titles_group_large_counts_the_en_us_way():
    # 0.10.44: "2290 complaints: unspecified problem on ..." read as a code; counts are grouped as the import result
    # groups them (DEV-025). A title is stored text: signals raised before keep theirs.
    assert (
        logic.rule_title(2290, "UNSPECIFIED", "Aster Pump", "Rev C", 30)
        == "2,290 complaints: unspecified problem on Aster Pump Rev C in 30 days"
    )
    assert logic.rule_title(999, "OCCLUSION_ALARM", "Aster Pump", None, 30).startswith("999 complaints: ")
    assert logic.rule_title(1234567, "X", "P", None, 30).startswith("1,234,567 complaints: ")


def test_rule_titles_from_before_grouped_counts_are_shown_grouped_and_nothing_else_changes():
    # Signals raised before 0.10.44 keep their stored titles; the API shows a rule title's count grouped (0.10.47).
    old = "2290 complaints: unspecified problem on Aster Pump Rev C in 30 days"
    assert (
        logic.display_title(old, "THRESHOLD_RULE")
        == "2,290 complaints: unspecified problem on Aster Pump Rev C in 30 days"
    )
    assert logic.display_title("1234567 complaints: x on P in 7 days", "THRESHOLD_RULE").startswith(
        "1,234,567 complaints"
    )
    for unchanged in (
        "2,290 complaints: unspecified problem on Aster Pump Rev C in 30 days",  # written since 0.10.44
        "999 complaints: occlusion alarm on Aster Pump in 30 days",
        "1 complaint: occlusion alarm on Aster Pump in 30 days",
        "2290 reports of occlusion",
        "02290 complaints: x on P in 30 days",
        "",
        None,
    ):
        assert logic.display_title(unchanged, "THRESHOLD_RULE") == unchanged
    # A person's (or an imported or suggested) title is shown as written, even one that reads like a rule's.
    for origin in ("MANUAL", "IMPORT", "AI_SUGGESTED", None):
        assert logic.display_title(old, origin) == old
    assert logic.display_task_title(f"Triage SIG000007: {old}", "SIG000007", "THRESHOLD_RULE") == (
        "Triage SIG000007: 2,290 complaints: unspecified problem on Aster Pump Rev C in 30 days"
    )
    assert logic.display_task_title(f"Triage SIG000007: {old}", "SIG000007", "MANUAL") == f"Triage SIG000007: {old}"
    assert logic.display_task_title(f"Triage SIG000008: {old}", "SIG000007", "THRESHOLD_RULE").endswith(old)
    assert logic.display_task_title("Review evidence 2290", None, "THRESHOLD_RULE") == "Review evidence 2290"
    assert logic.ungrouped_search("2,290 complaints") == "2290 complaints"
    assert logic.ungrouped_search("1,234,567") == "1234567"
    assert logic.ungrouped_search("2290 complaints") is None and logic.ungrouped_search("a,b 1,23") is None


def test_story_readiness_and_trend_sentences_group_their_counts():
    from backend.app.readiness_home import service as readiness_service
    from backend.app.readiness_home import summary as readiness_summary
    from backend.app.signals import trend_rules
    from backend.app.trial import story

    assert story._plural(2290, "signal") == "2,290 signals" and story._plural(1, "signal") == "1 signal"
    assert readiness_service._n(4993, "complaint") == "4,993 complaints"
    assert readiness_summary._n(4993, "complaint") == "4,993 complaints"
    text = trend_rules.sentence("Pump Rev B", trend_rules.check(recent=2290, history=1500, days_of_history=180))
    assert text.startswith("Pump Rev B: 2,290 complaints in the last ") and "(1,500 complaints)" in text
    assert "2290" not in text and "1500" not in text


def test_grouping_by_product_version_and_problem():
    product, version = uuid.uuid4(), uuid.uuid4()
    rows = [
        _complaint(product, version, "A"),
        _complaint(product, version, "A"),
        _complaint(product, None, "A"),  # unknown version is its own group
        _complaint(product, version, "B"),
        _complaint(None, None, "A"),  # no product: left out
    ]
    groups = logic.group(rows)
    assert sorted(len(items) for items in groups.values()) == [1, 1, 2]
    assert (None, None, "A") not in groups


def test_detection_plan_creates_links_and_is_idempotent():
    product, version = uuid.uuid4(), uuid.uuid4()
    rows = [_complaint(product, version, "A") for _ in range(3)] + [_complaint(product, version, "B")]
    first = [plan for plan in logic.plan_detection(rows, {}, {}, 3) if plan.action]
    assert [(plan.key[2], plan.action, len(plan.new)) for plan in first] == [("A", "CREATE", 3)]

    # After the run the three complaints are linked to a signal of the same key: nothing to do.
    key = (product, version, "A")
    signal_id = uuid.uuid4()
    linked = {row.id: {key} for row in rows[:3]}
    assert not [plan for plan in logic.plan_detection(rows, linked, {key: signal_id}, 3) if plan.action]

    # A new complaint of the same group joins the open signal.
    later = _complaint(product, version, "A")
    plans = [plan for plan in logic.plan_detection([*rows, later], linked, {key: signal_id}, 3) if plan.action]
    assert [(plan.action, plan.signal_id, [row.id for row in plan.new]) for plan in plans] == [
        ("LINK", signal_id, [later.id])
    ]

    # A complaint linked only to a signal about another problem is still new for its own group.
    other = {rows[0].id: {(product, version, "Z")}}
    assert [plan.action for plan in logic.plan_detection(rows[:3], other, {}, 3) if plan.action] == ["CREATE"]
    # Below the threshold nothing is raised.
    assert not [plan for plan in logic.plan_detection(rows[:2], {}, {}, 3) if plan.action]


def _refused(code, *args, **kwargs):
    with pytest.raises(SignalRuleError) as caught:
        logic.check_disposition(*args, today=TODAY, **kwargs)
    assert caught.value.code == code
    return caught.value


def test_dispositions_allowed_from_triage_states():
    for status in ("NEW", "TRIAGE", "MONITOR"):
        for disposition in ("NO_ACTION", "INVESTIGATION_REQUIRED", "ESCALATED"):
            logic.check_disposition(disposition, status, today=TODAY)
    logic.check_disposition("INVESTIGATION_REQUIRED", "ESCALATED", today=TODAY)
    assert _refused("SIGNAL_STATE_CONFLICT", "NO_ACTION", "ESCALATED").status == 409
    for status in ("NO_ACTION", "DUPLICATE", "MERGED", "INVESTIGATION_OPEN", "CLOSED", "INVESTIGATION_REQUIRED"):
        _refused("SIGNAL_STATE_CONFLICT", "NO_ACTION", status)
    _refused("UNKNOWN_DISPOSITION", "DELETE", "NEW")


def test_duplicate_needs_another_original_signal():
    me, other = uuid.uuid4(), uuid.uuid4()
    _refused("CANONICAL_REQUIRED", "DUPLICATE", "NEW", signal_id=me)
    _refused("CANONICAL_INVALID", "DUPLICATE", "NEW", signal_id=me, canonical_signal_id=me, canonical=None)
    _refused("CANONICAL_INVALID", "DUPLICATE", "NEW", signal_id=me, canonical_signal_id=other, canonical=None)
    for status in ("DUPLICATE", "MERGED"):
        _refused(
            "CANONICAL_INVALID",
            "DUPLICATE",
            "NEW",
            signal_id=me,
            canonical_signal_id=other,
            canonical={"id": other, "status": status},
        )
    logic.check_disposition(
        "DUPLICATE",
        "TRIAGE",
        signal_id=me,
        canonical_signal_id=other,
        canonical={"id": other, "status": "NO_ACTION"},
        today=TODAY,
    )


def test_monitoring_needs_a_future_review_date_and_a_trigger():
    _refused("MONITOR_DETAILS_REQUIRED", "MONITOR", "TRIAGE", monitor_review_date=TODAY + timedelta(days=5))
    _refused("MONITOR_DETAILS_REQUIRED", "MONITOR", "TRIAGE", monitor_trigger="Two more complaints")
    _refused("REVIEW_DATE_NOT_FUTURE", "MONITOR", "TRIAGE", monitor_review_date=TODAY, monitor_trigger="More cases")
    logic.check_disposition(
        "MONITOR", "TRIAGE", monitor_review_date=TODAY + timedelta(days=1), monitor_trigger="More cases", today=TODAY
    )


def test_priority_reason_and_case_rules():
    assert logic.needs_priority_reason("HIGH", "LOW") and not logic.needs_priority_reason("LOW", "LOW")
    assert all(logic.can_open_case(status) for status in ("INVESTIGATION_REQUIRED", "ESCALATED", "INVESTIGATION_OPEN"))
    assert not logic.can_open_case("NEW") and not logic.can_open_case("TRIAGE")
    assert all(logic.is_open(status) for status in OPEN_SIGNAL_STATUSES) and not logic.is_open("MERGED")


def test_request_validation():
    from backend.app.signals.router import (
        AddComplaintsRequest,
        CreateInvestigationRequest,
        CreateSignalRequest,
        DispositionRequest,
        MergeRequest,
        PriorityRequest,
        RuleRequest,
    )

    product = str(uuid.uuid4())
    assert CreateSignalRequest(title="  Occlusion   alarms  ", product_id=product).title == "Occlusion alarms"
    for bad in (
        {"title": "abc", "product_id": product},
        {"title": "Valid title", "product_id": product, "priority": "URGENT"},
        {"title": "Valid title", "product_id": product, "priority": "HIGH", "reason": "short"},
        {"title": "Valid title"},
    ):
        with pytest.raises(ValidationError):
            CreateSignalRequest(**bad)
    assert PriorityRequest(priority="HIGH").reason is None
    with pytest.raises(ValidationError):
        PriorityRequest(priority="HIGH", reason="too short")
    with pytest.raises(ValidationError):
        DispositionRequest(disposition="CLOSED", reason="A reason long enough")
    with pytest.raises(ValidationError):
        DispositionRequest(disposition="NO_ACTION", reason="short")
    assert DispositionRequest(
        disposition="MONITOR", reason="Watch it for a month", monitor_review_date="2030-01-01"
    ).monitor_review_date == date(2030, 1, 1)
    with pytest.raises(ValidationError):
        MergeRequest(source_signal_ids=[], reason="A reason long enough")
    with pytest.raises(ValidationError):
        AddComplaintsRequest(complaint_ids=[], reason="A reason long enough")
    assert CreateInvestigationRequest(investigation_question="Why do alarms rise?").complaint_ids is None
    with pytest.raises(ValidationError):
        CreateInvestigationRequest(investigation_question="Why?", investigation_identifier="bad id!")
    for bad in ({"min_complaints": 1}, {"min_complaints": 1001}, {"window_days": 0}, {"window_days": 366}):
        with pytest.raises(ValidationError):
            RuleRequest(
                **{"enabled": True, "min_complaints": 3, "window_days": 30, "reason": "Tuned after review", **bad}
            )


def _actor(*permissions):
    return SimpleNamespace(holds=lambda permission: permission in permissions)


def test_actions_follow_permissions_and_status():
    from backend.app.signals.router import _actions

    signal = SimpleNamespace(status="NEW", product_id=uuid.uuid4())
    lead = _actions(_actor("signal.triage", "investigation.create"), signal)
    assert lead["can_start"] and lead["can_disposition"] and lead["can_merge"] and not lead["can_create_investigation"]
    assert not any(_actions(_actor(), signal).values())
    escalated = SimpleNamespace(status="ESCALATED", product_id=uuid.uuid4())
    investigator = _actions(_actor("investigation.create"), escalated)
    assert investigator["can_create_investigation"] and not investigator["can_disposition"]
    # One click opens a case before triage as well, for anyone who may open cases.
    assert _actions(_actor("investigation.create"), signal)["can_open_case"]
    assert investigator["can_open_case"]
    assert not _actions(_actor("signal.triage"), signal)["can_open_case"]
    closed = SimpleNamespace(status="NO_ACTION", product_id=uuid.uuid4())
    assert not _actions(_actor("investigation.create"), closed)["can_open_case"]
    assert _actions(_actor("signal.triage"), escalated)["can_disposition"]
    merged = _actions(
        _actor("signal.triage", "investigation.create"), SimpleNamespace(status="MERGED", product_id=None)
    )
    assert not any(merged.values())


def test_list_filters_accept_comma_separated_values():
    from fastapi import HTTPException

    from backend.app.signals.router import _codes

    assert _codes("new, triage,MONITOR", (*SIGNAL_STATUSES, "OPEN"), "status") == ["NEW", "TRIAGE", "MONITOR"]
    assert _codes("HIGH,CRITICAL", SIGNAL_PRIORITIES, "priority") == ["HIGH", "CRITICAL"]
    assert _codes(None, SIGNAL_PRIORITIES, "priority") == []
    with pytest.raises(HTTPException) as caught:
        _codes("HIGH,URGENT", SIGNAL_PRIORITIES, "priority")
    assert caught.value.status_code == 422 and caught.value.detail["code"] == "UNKNOWN_PRIORITY"


def test_imports_that_trigger_detection():
    assert hooks.imported_complaints({"entity": "complaints", "created": 2, "updated": 0})
    assert hooks.imported_complaints({"status": "IMPORTED", "entity": "complaints", "created": 0, "updated": 1})
    assert not hooks.imported_complaints({"entity": "complaints", "created": 0, "updated": 0})
    assert not hooks.imported_complaints({"entity": "products", "created": 5})
    assert not hooks.imported_complaints(None)


class _BrokenSession:
    """A session whose savepoint fails, as a database error inside a hook would."""

    def __init__(self):
        self.rolled_back = False
        self.committed = False

    def begin_nested(self):
        raise RuntimeError("database unavailable")

    def rollback(self):
        self.rolled_back = True

    def commit(self):
        self.committed = True


def test_a_failing_signal_hook_is_logged_and_never_raises(caplog):
    session = _BrokenSession()
    assert hooks.after_complaints_saved(session, uuid.uuid4(), source="CSV import") is None
    assert session.rolled_back and not session.committed
    decision = SimpleNamespace(tenant_id=uuid.uuid4(), investigation_id=uuid.uuid4(), business_id="DEC000001")
    hooks.on_case_decision_signed(_BrokenSession(), decision, actor_user_id=uuid.uuid4())
    case = SimpleNamespace(tenant_id=uuid.uuid4(), id=uuid.uuid4(), status="closed", business_id="INV000001")
    hooks.on_investigation_status_changed(
        _BrokenSession(), None, case, actor_user_id=uuid.uuid4(), before_status="open"
    )
    assert "Signal hook" in caplog.text
    # Nothing to do without a session or an organization.
    assert hooks.after_complaints_saved(None, uuid.uuid4(), source="x") is None
    assert hooks.after_complaints_saved(_BrokenSession(), "not-an-id", source="x") is None


def test_a_case_status_that_did_not_change_touches_no_signal():
    session = _BrokenSession()
    case = SimpleNamespace(tenant_id=uuid.uuid4(), id=uuid.uuid4(), status="open", business_id="INV000001")
    hooks.on_investigation_status_changed(session, None, case, actor_user_id=uuid.uuid4(), before_status="open")
    assert not session.rolled_back and not session.committed


def test_signals_are_a_task_source_and_triage_is_a_task_type():
    from backend.app.workflow.labels import SOURCE_LABELS, TASK_TYPES
    from backend.app.workflow.router import _source_models

    assert SOURCE_LABELS["Signal"] == "Signal"
    assert _source_models()["Signal"].__tablename__ == "signals"
    assert TASK_TYPES[TRIAGE_TASK].permission == "signal.triage" and TASK_TYPES[TRIAGE_TASK].queue_role == "TRIAGE_LEAD"


def test_the_triage_routes_are_registered_and_writes_are_guarded():
    from backend.app.main import app
    from tests.route_inventory import api_routes

    routes = {
        (method, path): route
        for path, route in api_routes(app)
        if path.startswith("/api/v1/triage")
        for method in route.methods
    }
    expected_writes = {
        ("POST", "/api/v1/triage/signals"): "signal.triage",
        ("POST", "/api/v1/triage/signals/{signal_id}/start"): "signal.triage",
        ("POST", "/api/v1/triage/signals/{signal_id}/priority"): "signal.triage",
        ("POST", "/api/v1/triage/signals/{signal_id}/disposition"): "signal.triage",
        ("POST", "/api/v1/triage/signals/{signal_id}/merge"): "signal.triage",
        ("POST", "/api/v1/triage/signals/{signal_id}/complaints"): "signal.triage",
        ("POST", "/api/v1/triage/signals/{signal_id}/create-investigation"): "investigation.create",
        ("POST", "/api/v1/triage/signals/{signal_id}/open-case"): "investigation.create",
        ("POST", "/api/v1/triage/signals/{signal_id}/summary"): "ai.run",
        ("PUT", "/api/v1/triage/rules/{rule_code}"): "signal.triage",
        ("POST", "/api/v1/triage/rules/run"): "signal.triage",
    }
    for key in expected_writes:
        assert key in routes, key
        guards = [dep.dependency for dep in routes[key].dependencies]
        assert any("require_permission" in getattr(guard, "__qualname__", "") for guard in guards), key
    for key in (
        ("GET", "/api/v1/triage/signals"),
        ("GET", "/api/v1/triage/signals/{signal_id}"),
        ("GET", "/api/v1/triage/summary"),
        ("GET", "/api/v1/triage/rules"),
        ("GET", "/api/v1/triage/trends"),
        ("GET", "/api/v1/triage/signals/{signal_id}/insight"),
    ):
        assert key in routes, key


def test_detection_runs_hourly_in_the_scheduler():
    from backend.app import scheduler

    job = next(job for job in scheduler.JOBS if job.name == "signal_detection")
    assert job.every == timedelta(minutes=60)


def test_signal_tables_are_deleted_with_trial_data_children_first():
    from backend.app.trial.retention import TRIAL_DATA_TABLES

    order = {table: index for index, table in enumerate(TRIAL_DATA_TABLES)}
    for child in ("signal_events", "signal_complaints", "investigation_signals"):
        assert order[child] < order["signals"]
    for parent in ("complaints", "products", "investigations", "product_versions"):
        assert order["signals"] < order[parent]
    assert "signal_rules" in order


def test_recurring_words_leave_out_what_did_not_happen_outcomes_boilerplate_and_identifiers():
    """A complaint saying "no patient injury reported" never counts as the word "injury" (it reads as five injuries);
    nor do outcome words, which have their own sentence, "returned for evaluation" or a lot number."""
    from backend.app.signals.insight import _words

    sample = (
        "Customer reported pressure alarm during infusion on Rev B, lot SAMPLE-ORBIT-300-LOT-003. "
        "Device returned for evaluation; no patient injury reported."
    )
    assert _words(sample) == {"pressure", "alarm", "infusion"}
    assert _words("Occlusion alarm without harm or delay to therapy") == {"occlusion", "alarm"}
    assert _words("The alarm did not sound during an occlusion") == {"alarm"}
    assert _words("Alarm didn't sound; display froze") == {"alarm", "display", "froze"}
    assert _words("Patient was injured when the door opened, but no death") == {"door", "opened"}
    assert _words("Screen flicker, never caused delay") == {"screen", "flicker"}
    assert _words(None) == set()
