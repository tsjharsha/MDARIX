"""B7 step 2: the routine path's pure rules (spec b7-routine-path, sections 1.2 and 6.1 G3-G5, G7, G11; B7-D2 to D5,
D7). No database."""

import pytest

from backend.app.complaint_disposition import rules

pytestmark = pytest.mark.unit

FULL = {
    "troubleshooting": "Alarm check and filter inspection",
    "correction_type": "USER_INSTRUCTED",
    "correction": "User instructed to re-seat the filter",
    "result": "Alarm cleared",
    "service_ticket": "",
    "no_investigation_reason": "USE_RELATED_INSTRUCTED",
}


def _problem(on_watch=False, **changes):
    return rules.service_record_problem(rules.clean_service_record({**FULL, **changes}), on_watch)


@pytest.mark.parametrize("correction", rules.CORRECTIONS)
def test_the_ticket_is_needed_only_when_service_work_was_done(correction):
    problem = _problem(correction_type=correction)
    if correction in ("PART_REPLACED", "SETTING_CORRECTED"):
        assert "service ticket" in problem
        assert _problem(correction_type=correction, service_ticket="SRV-1001") is None
    else:
        assert problem is None


def test_no_fault_found_is_a_correction_and_keeps_the_cause_undetermined():
    assert "NO_FAULT_FOUND" in rules.CORRECTIONS and rules.CORRECTION_LABELS["NO_FAULT_FOUND"] == "No fault found"
    record = rules.clean_service_record({**FULL, "correction_type": "no_fault_found"})
    assert rules.no_fault_problem(record, "DEVICE_RELATED") == "No fault found: the cause is undetermined; say why"
    assert rules.no_fault_problem(record, "UNDETERMINED") is None
    assert rules.no_fault_problem(rules.clean_service_record(FULL), "USE_RELATED") is None


@pytest.mark.parametrize("reason", list(rules.NO_INVESTIGATION_REASONS))
@pytest.mark.parametrize("on_watch", (False, True))
def test_each_reason_needs_words_only_for_other_and_withdrawal_only_off_the_watch(reason, on_watch):
    problem = _problem(on_watch, no_investigation_reason=reason)
    if reason == "OTHER":
        assert "8.2.2" in problem
        assert _problem(on_watch, no_investigation_reason=reason, no_investigation_rationale="x" * 20) is None
    elif reason == "REPORTER_WITHDREW" and on_watch:
        assert "withdrawal" in problem
    else:
        assert problem is None
        # The reason's words are kept as the signed rationale.
        record = rules.clean_service_record({**FULL, "no_investigation_reason": reason})
        assert record["no_investigation_rationale"] == rules.NO_INVESTIGATION_REASONS[reason]


def test_a_client_from_before_b7_sends_the_rationale_only_and_it_reads_as_other():
    record = rules.clean_service_record({**FULL, "no_investigation_reason": "", "no_investigation_rationale": "y" * 25})
    assert record["no_investigation_reason"] == "OTHER" and rules.service_record_problem(record) is None
    assert "Choose why" in _problem(no_investigation_reason="GUESS")


def test_device_returned_is_one_of_three():
    assert _problem(device_returned="not_returned") is None
    assert "returned" in _problem(device_returned="LOST")


@pytest.mark.parametrize(
    "requested, correction",
    [
        ("INFORMATION", "USER_INSTRUCTED"),
        ("NONE", "USER_INSTRUCTED"),
        (None, "USER_INSTRUCTED"),
        ("TRAINING", "USER_INSTRUCTED"),
        ("REPAIR", "PART_REPLACED"),
        ("CALIBRATION", "SETTING_CORRECTED"),
        ("MAINTENANCE", "SETTING_CORRECTED"),
    ],
)
def test_the_default_correction_follows_what_they_asked_for(requested, correction):
    assert rules.default_correction(requested) == correction


def test_customer_told_needs_how_or_not_possible_with_a_reason():
    assert rules.customer_told_problem({"how": "phone"}) is None
    assert "how the customer was told" in rules.customer_told_problem({})
    assert "why the customer could not be told" in rules.customer_told_problem({"how": "NOT_POSSIBLE"})
    assert rules.customer_told_problem({"how": "NOT_POSSIBLE", "reason": "Anonymous caller, no contact"}) is None
    # Connect: the QMS letter ID is enough; Complete still asks how.
    assert rules.customer_told_problem({"qms_letter_id": "LTR-77"}, connect=True) is None
    assert rules.customer_told_problem({"qms_letter_id": "LTR-77"}) is not None


def test_a_known_behaviour_answer_settles_only_a_new_failure_mode():
    met = [{"code": "NEW_FAILURE_MODE", "fact": "new"}, {"code": "RECURRENCE", "fact": "3 in 12 months"}]
    assert rules.answered_triggers(met, "") == met
    assert rules.answered_triggers(met, "IFU-12 section 4") == [met[1]]
    assert rules.answered_triggers(met[:1], "IFU rev 3") == []


@pytest.mark.parametrize("route_open", (True, False))
@pytest.mark.parametrize("routine_markets", (True, False))
def test_resolve_and_close_is_offered_in_full_only_when_nothing_else_blocks(route_open, routine_markets):
    settled_here = [
        {"code": "DECISION", "label": "The decision is signed"},
        {"code": "CUSTOMER_TOLD", "label": "The customer was told"},
    ]
    markets = [{"code": "MARKETS", "label": "Every relevant market is assessed and signed"}]
    offer = rules.combined_offer(route_open, settled_here + markets, routine_markets)
    assert offer["full"] is (route_open and routine_markets)
    assert offer["blocking"] == ([] if routine_markets else [markets[0]["label"]])
    task = [{"code": "TASKS", "label": "No task on the event is open"}]
    blocked = rules.combined_offer(route_open, settled_here + task, routine_markets)
    assert blocked == {"full": False, "blocking": ["No task on the event is open"]}


def test_the_rules_moved_to_version_2():
    assert rules.RULES_VERSION == "disposition-starter-2"
    assert any("known behaviour" in rule for rule in rules.DISPOSITION_RULES)
