"""The disposition rules, the escalation triggers read from a complaint's own fields, the root-cause attribution, the
classification's Unknown and the risk review's risk-control answers, without a database (T-G36, T-G36T, T-G39,
T-G1aR)."""

from __future__ import annotations

import uuid
from datetime import date
from types import SimpleNamespace

import pytest

from backend.app.case_reviews.rules import FindingPayload, findings_problem
from backend.app.complaint_classification.rules import code_source_value
from backend.app.complaint_disposition import rules, triggers
from backend.app.complaint_disposition.service import routine_offer
from backend.app.signer_training import service as training

# B6b B3: the scenarios this file verifies (requirements.csv, class A); file level, so every test here carries them.
pytestmark = [pytest.mark.unit, pytest.mark.requirement("IN-22")]

CASE = str(uuid.uuid4())


def _facts(**fields) -> triggers.Facts:
    base = {"death": None, "serious_injury": None, "patient_involved": None, "malfunction": None, "severity": None}
    complaint = SimpleNamespace(**{**base, **fields})
    return triggers.Facts(complaint, "CMP-1", "Pump", ["US", "EU_NI"])


def _assessment(market: str, version: int = 1, conclusion=None, harm_level=None, **answers):
    return SimpleNamespace(
        market=market,
        version=version,
        conclusion=conclusion,
        harm_level=harm_level,
        answers={key: {"answer": value} for key, value in answers.items()},
    )


def test_a_met_trigger_allows_only_escalation_and_no_trigger_refuses_it():
    assert "other branches are closed" in rules.branch_problem("SERVICE_LEVEL", True, [], None, "", "")
    assert "other branches are closed" in rules.branch_problem("KNOWN_ISSUE", True, [CASE], CASE, "same lot", "")
    assert rules.branch_problem("ESCALATED_BY_TRIGGER", True, [], None, "Product investigation needed", "") is None
    assert "No escalation trigger" in rules.branch_problem("ESCALATED_BY_TRIGGER", False, [], None, "x" * 20, "")
    assert rules.branch_problem("SERVICE_LEVEL", False, [], None, "", "") is None
    assert "open investigations that match" in rules.branch_problem(
        "KNOWN_ISSUE", False, [CASE], str(uuid.uuid4()), "x" * 20, ""
    )
    assert "why it is the same issue" in rules.branch_problem("KNOWN_ISSUE", False, [CASE], CASE, "short", "")
    # A matching case exists but another branch is taken: say why it is not that issue.
    assert "not that known issue" in rules.branch_problem("SERVICE_LEVEL", False, [CASE], None, "", "")
    assert rules.branch_problem("SERVICE_LEVEL", False, [CASE], None, "", "Different failure: cable wear") is None
    assert "why you escalate" in rules.branch_problem("ESCALATED_BY_CHOICE", False, [], None, "", "")


def test_the_attribution_is_required_and_undetermined_needs_its_reason():
    assert "root-cause attribution" in rules.attribution_problem(None, None)
    assert "root-cause attribution" in rules.attribution_problem("SUPPLIER", None)
    assert "Undetermined" in rules.attribution_problem("UNDETERMINED", "unclear")
    assert rules.attribution_problem("UNDETERMINED", "The device was not returned for evaluation") is None
    assert rules.attribution_problem("USE_RELATED", None) is None


def test_the_service_level_record_needs_every_field_and_the_no_investigation_rationale():
    full = {
        "troubleshooting": "Alarm check and filter inspection",
        "correction_type": "user_instructed",
        "correction": "User instructed to re-seat the filter",
        "result": "Alarm cleared",
        "service_ticket": "DIST-REF-2231",
        "no_investigation_rationale": "User-correctable seating fault, cleared at service level; no harm.",
    }
    record = rules.clean_service_record(full)
    assert record["correction_type"] == "USER_INSTRUCTED" and record["clause"] == "ISO 13485:2016 clause 8.2.2"
    assert rules.service_record_problem(record) is None
    for key, message in (
        ("troubleshooting", "troubleshooting"),
        ("correction_type", "Choose the correction"),
        ("no_investigation_rationale", "8.2.2"),
    ):
        assert message in rules.service_record_problem(rules.clean_service_record({**full, key: ""}))
    # B7-D3: the ticket is needed only when service work was done.
    assert rules.service_record_problem(rules.clean_service_record({**full, "service_ticket": ""})) is None
    replaced = rules.clean_service_record({**full, "service_ticket": "", "correction_type": "part_replaced"})
    assert "service ticket" in rules.service_record_problem(replaced)


def test_each_answer_is_kept_with_its_rationale_and_refused_branches_say_so():
    met = [{"code": "NEW_FAILURE_MODE", "fact": "Problem code BATTERY_SHUTDOWN not recorded before"}]
    escalated = rules.answers_of("ESCALATED_BY_TRIGGER", met, [], "Product investigation needed", "")
    assert escalated["TRIGGER"] == {
        "answer": "YES",
        "facts": "Problem code BATTERY_SHUTDOWN not recorded before",
        "rationale": "Product investigation needed",
    }
    assert {escalated[key]["answer"] for key in ("KNOWN_ISSUE", "SERVICE_LEVEL", "CHOICE")} == {"REFUSED"}
    service = rules.answers_of("SERVICE_LEVEL", [], [], "", "")
    assert service["KNOWN_ISSUE"]["answer"] == "NO" and "No open investigation" in service["KNOWN_ISSUE"]["rationale"]
    assert "CHOICE" not in service
    choice = rules.answers_of("ESCALATED_BY_CHOICE", [], [CASE], "Customer asks for an analysis", "Different lot")
    assert choice["KNOWN_ISSUE"]["rationale"] == "Different lot" and choice["CHOICE"]["answer"] == "YES"
    assert rules.hands_on(305.7) == 305 and rules.hands_on(-1) is None and rules.hands_on(10**9) == rules.HANDS_ON_MAX


def test_the_triggers_read_the_complaint_and_its_market_assessments():
    assert triggers.codes(triggers.safety(_facts(death=True))) == ["SAFETY"]
    harm = _facts()
    harm.assessments = [_assessment("US", harm_level="CATASTROPHIC")]
    assert triggers.safety(harm)[0]["field"] == "harm_level"
    assert triggers.injury(_facts(serious_injury=True))[0]["value"] == "Yes"
    unknown = triggers.injury(_facts(patient_involved=True, serious_injury=False))
    assert unknown[0]["value"] == "Unknown"  # death not recorded: the outcome is unknown
    assert triggers.injury(_facts(patient_involved=True, serious_injury=False, death=False)) == []
    assert triggers.injury(_facts(patient_involved=False)) == []
    assert triggers.injury(_facts(severity="Critical"))[0]["field"] == "harm_level"  # QMS severity mapped
    assert triggers.injury(_facts(severity="Minor")) == []
    reportable = _facts()
    reportable.assessments = [_assessment("EU_NI", conclusion="REPORTABLE"), _assessment("US", US5="YES")]
    assert [item["field"] for item in triggers.reportable(reportable)] == ["conclusion", "US5"]
    legacy = _facts()
    legacy.legacy = SimpleNamespace(decision="REPORTED")
    assert triggers.reportable(legacy)[0]["value"] == "REPORTED"
    assert triggers.reportable(_facts()) == []


def test_the_routine_path_is_offered_only_off_the_watch_without_a_flag_or_a_trigger():
    assert routine_offer(False, None, [])["offered"] is True
    for on_watch, flag, met in ((True, None, []), (False, {"decision": None}, []), (False, None, [{"code": "SAFETY"}])):
        offer = routine_offer(on_watch, flag, met)
        assert offer["offered"] is False and len(offer["blocked"]) == 1


@pytest.mark.parametrize(
    ("fields", "unrecorded"),
    [
        # Nothing recorded (an import without the harm columns): Unknown is never No.
        ({}, ["malfunction", "patient"]),
        ({"patient_involved": False}, ["malfunction"]),
        ({"malfunction": False}, ["patient"]),
        # A patient's absence settles death and injury; a known No for each settles them too.
        ({"malfunction": False, "patient_involved": False}, []),
        ({"malfunction": False, "death": False, "serious_injury": False}, []),
        ({"malfunction": False, "death": False}, ["patient"]),
    ],
)
def test_the_routine_path_concludes_not_reportable_only_on_recorded_facts(fields, unrecorded):
    """DEV-09, table ROUTINE (docs/compliance/REGULATORY_DECISION_TABLES.md): the routine path signs "not reportable"
    for each enabled market on the basis "no death, serious injury or malfunction recorded; patient outcome known". A
    complaint whose fields leave a malfunction or the patient's outcome unrecorded is off the watch, yet that basis
    does not hold: the routine path is not offered, and the reason names the missing facts."""
    record = {"death": None, "serious_injury": None, "patient_involved": None, "malfunction": None, **fields}
    found = rules.routine_unrecorded(record)
    assert [item["code"] for item in found] == [code.upper() for code in unrecorded]
    offer = routine_offer(False, None, [], found)
    assert offer["offered"] is (not unrecorded)
    if unrecorded:
        (reason,) = offer["blocked"]
        assert "only on recorded facts" in reason and "Unknown is never No" in reason


def test_a_source_value_off_the_list_stays_unknown_and_is_kept():
    assert code_source_value("use_environment", "Intensive care unit") == ("INTENSIVE_CARE_UNIT", "Intensive care unit")
    assert code_source_value("use_environment", "Step-down unit") == ("UNKNOWN", "Step-down unit")
    assert code_source_value("user_type", "nurse") == ("UNKNOWN", "nurse")  # never inferred from free text
    assert code_source_value("user_type", None) == ("UNKNOWN", None)


def test_a_disposition_relies_on_the_rules_and_the_coding_criteria_at_their_current_versions():
    assert [(item.code, item.version) for item in training.for_disposition()] == [
        ("DISPOSITION_RULES", "disposition-starter-2"),
        ("CODING_CRITERIA", "coding-starter-1"),
    ]
    assert training.content("DISPOSITION_RULES")["rules"][0].startswith("Answer in order")


def test_a_risk_review_answers_each_finding_and_a_no_or_a_new_failure_mode_needs_an_update():
    risk, owner, today = uuid.uuid4(), uuid.uuid4(), date(2026, 11, 2)
    due = date(2026, 12, 2)
    missing = findings_problem([risk], [], today)
    assert "needs its risk-control answer" in missing[0]
    no_owner = findings_problem(
        [risk], [FindingPayload(risk_id=risk, control_worked="NO", reason="The alarm did not sound")], today
    )
    assert "owner and a due date" in no_owner[0]
    problem, stored = findings_problem(
        [risk],
        [
            FindingPayload(
                risk_id=risk, control_worked="NO", reason="The alarm did not sound", owner_user_id=owner, due_on=due
            ),
            FindingPayload(description="Battery shutdown with a full indicator", owner_user_id=owner, due_on=due),
        ],
        today,
    )
    assert problem is None
    assert (
        stored[str(risk)]["control_worked"] == "NO" and stored[str(risk)]["risk_file_update"]["due_on"] == "2026-12-02"
    )
    assert stored["NEW-1"]["kind"] == "NOT_IN_RISK_FILE" and stored["NEW-1"]["risk_file_update"]["owner_user_id"]
    worked = findings_problem(
        [risk], [FindingPayload(risk_id=risk, control_worked="YES", reason="Alarm sounded")], today
    )
    assert worked[0] is None and worked[1][str(risk)]["risk_file_update"] is None
    past = FindingPayload(description="A new hazard found", owner_user_id=owner, due_on=date(2026, 1, 1))
    assert "past" in findings_problem([], [past], today)[0]
