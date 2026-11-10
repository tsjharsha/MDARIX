"""The Case's rules (0.10.93, B2): states and moves, the Case check v2 (X1 rules), awareness H1 and ID-1 identifiers.
Pure functions, no database."""

import itertools
from datetime import datetime, timedelta, timezone

import pytest

from backend.app.intake import case_rules as cr
from backend.app.intake import rules

pytestmark = pytest.mark.unit

Y, N, U, NA, NS = rules.YES, rules.NO, rules.UNKNOWN, rules.NOT_APPLICABLE, rules.NOT_STATED
PLAIN = (Y, N, U, NA)
HARM = (Y, N, U, NA, NS)


def _answers(values: dict, note: str = "Not relevant to this device") -> dict:
    return {q: {"answer": a, "note": note if a == NA else ""} for q, a in values.items()}


def _expected(v: dict, requested: str) -> str:
    """The outcomes table read row by row, first match wins (G32; OD-5 for Inquiry). N/A carries its note here."""
    not_alleged = (N, NA)
    rows = (
        (lambda: any(v[q] == Y for q in ("Q1", "Q2", "Q3")), "COMPLAINT_ROW"),
        (
            lambda: (
                v["Q7"] == Y
                and all(v[q] in not_alleged for q in ("Q1", "Q2", "Q3", "Q4", "Q5", "Q6", "Q8"))
                and v["Q9"] in not_alleged
            ),
            "SERVICE_ROW",
        ),
        (
            lambda: any(v[q] == U for q in v) or any(v[q] == NS for q in ("Q4", "Q5", "Q6")),
            rules.PENDING,
        ),
        (lambda: all(v[q] in not_alleged for q in v), rules.PENDING_CONFIRM),
        (lambda: True, "COMPLAINT_ROW"),
    )
    found = next(result for test, result in rows if test())
    if found == "COMPLAINT_ROW":
        return rules.BOTH if v["Q8"] == Y else rules.COMPLAINT
    if found == "SERVICE_ROW":
        return cr.INQUIRY if requested in ("INFORMATION", "NONE") else rules.SERVICE_ONLY
    return found


def test_every_answer_combination_gives_the_tables_outcome():  # B2-12, exhaustive: 4^6 x 5^3 = 512,000
    order = ("Q1", "Q2", "Q3", "Q7", "Q8", "Q9", "Q4", "Q5", "Q6")
    counts: dict[str, int] = {}
    for combo in itertools.product(PLAIN, PLAIN, PLAIN, PLAIN, PLAIN, PLAIN, HARM, HARM, HARM):
        values = dict(zip(order, combo))
        answers = _answers(values)
        got = cr.case_outcome(answers, "REPAIR")
        assert got == _expected(values, "REPAIR"), values
        if got == rules.SERVICE_ONLY:
            assert cr.case_outcome(answers, "INFORMATION") == cr.INQUIRY
            assert cr.case_outcome(answers, None) == cr.INQUIRY
        counts[got] = counts.get(got, 0) + 1
    assert sum(counts.values()) == 4**6 * 5**3
    assert set(counts) == {rules.COMPLAINT, rules.BOTH, rules.SERVICE_ONLY, rules.PENDING, rules.PENDING_CONFIRM}


def _all_no(**changes) -> dict:
    values = {q: N for q in rules.QUESTION_IDS}
    values.update(changes)
    return values


def test_unknown_na_and_unanswered_are_kept_apart():  # B2-13
    base = _all_no(Q7=Y)
    assert cr.case_outcome(_answers(base), "CALIBRATION") == rules.SERVICE_ONLY
    # Unknown is never No.
    for question in rules.QUESTION_IDS:
        if question != "Q7":
            assert cr.case_outcome(_answers({**base, question: U}), "CALIBRATION") == rules.PENDING, question
    # Not applicable without its note is never No (questions 1-6 and 8).
    for question in ("Q1", "Q2", "Q3", "Q4", "Q5", "Q6", "Q8"):
        values = {**base, question: NA}
        assert cr.case_outcome(_answers(values), "CALIBRATION") == rules.SERVICE_ONLY
        assert cr.case_outcome(_answers(values, note=""), "CALIBRATION") != rules.SERVICE_ONLY, question
    # Unanswered is never Unknown: no outcome at all, and the follow-up never asks it.
    for question in rules.QUESTION_IDS:
        answers = _answers(base)
        answers[question] = {"answer": None, "note": ""}
        assert cr.case_outcome(answers, "CALIBRATION") == cr.UNANSWERED, question
        assert question not in cr.follow_up_questions(answers)
    asked = _answers(_all_no(Q2=U, Q4=NS))
    assert cr.follow_up_questions(asked) == ["Q2", "Q4"]


def test_every_answer_stores_the_version_of_its_question():
    answers = cr.clean_answers({"Q1": {"answer": "yes"}, "Q4": {"answer": "NOT_STATED"}, "Q1x": {"answer": "YES"}})
    assert set(answers) == set(rules.QUESTION_IDS)
    assert all(item["question_version"] == cr.QUESTION_VERSIONS[q] for q, item in answers.items())
    assert answers["Q1"]["answer"] == Y and answers["Q4"]["answer"] == NS and answers["Q2"]["answer"] is None


def test_a_recalculation_is_deterministic_and_names_what_changed():  # B2-14
    before = _answers(_all_no(Q7=Y))
    after = _answers(_all_no(Q7=Y, Q3=Y))
    at = datetime(2026, 11, 10, 9, 0, tzinfo=timezone.utc)
    old, new = cr.case_outcome(before, "REPAIR"), cr.case_outcome(after, "REPAIR")
    assert (old, new) == (rules.SERVICE_ONLY, rules.COMPLAINT)
    assert cr.case_outcome(after, "REPAIR") == new  # the same answers always give the same outcome
    entry = cr.recalculation(before, after, old, new, "user-1", at)
    assert entry == {"at": at.isoformat(), "by": "user-1", "changed": ["Q3"], "before": old, "after": new}


def test_what_may_be_signed():
    ok = cr.classification_problem
    assert ok(cr.UNANSWERED, rules.COMPLAINT, "", "") == "Answer every question first"
    assert ok(rules.COMPLAINT, rules.COMPLAINT, "", "") is None
    assert ok(rules.PENDING, rules.COMPLAINT, "", "") is not None  # an override needs its reason
    assert ok(rules.PENDING, rules.COMPLAINT, "The reporter says it failed twice", "") is None
    for answer_only in (rules.SERVICE_ONLY, cr.INQUIRY, rules.PENDING_CONFIRM):
        assert "only when the answers give it" in ok(rules.COMPLAINT, answer_only, "A long enough reason", "x" * 20)
    assert ok(rules.SERVICE_ONLY, cr.INQUIRY, "A long enough reason", "x" * 20) is not None
    assert ok(cr.INQUIRY, cr.INQUIRY, "", "") is not None  # a reason is needed
    assert ok(cr.INQUIRY, cr.INQUIRY, "", "Asked for a copy of the IFU") is None
    reason = "Reporter confirmed nothing was wrong"
    assert ok(rules.PENDING_CONFIRM, cr.NOT_A_COMPLAINT, "", reason) is not None
    assert ok(rules.PENDING_CONFIRM, cr.NOT_A_COMPLAINT, "", reason, no_deficiency_confirmed=True) is None
    assert ok(rules.PENDING, cr.NOT_A_COMPLAINT, "", reason, no_deficiency_confirmed=True) is not None


def test_only_the_listed_moves_are_allowed():  # B2-08
    for current in cr.STATES:
        for target in cr.STATES:
            problem = cr.transition_problem(current, target)
            assert (problem is None) == ((current, target) in cr.TRANSITIONS), (current, target)
    assert "its life continues on the complaint" in cr.transition_problem(cr.ESCALATED, cr.CLOSED)
    assert cr.transition_problem(cr.VOIDED, cr.OPEN) == "This case was withdrawn"
    assert cr.transition_problem(cr.OPEN, "DONE") == "Unknown case state DONE"
    # Escalation is reachable from every open state; nothing leaves ESCALATED or VOIDED.
    assert all((state, cr.ESCALATED) in cr.TRANSITIONS for state in (cr.OPEN, cr.PENDING, cr.IN_REVIEW))
    assert not [move for move in cr.TRANSITIONS if move[0] in (cr.ESCALATED, cr.VOIDED)]


def test_a_signed_classification_moves_the_case():
    assert cr.state_after(rules.COMPLAINT) == cr.state_after(rules.BOTH) == cr.ESCALATED
    assert cr.state_after(rules.SERVICE_ONLY) == cr.state_after(cr.INQUIRY) == cr.IN_REVIEW
    assert cr.state_after(cr.NOT_A_COMPLAINT) == cr.IN_REVIEW
    assert cr.state_after(rules.PENDING) == cr.state_after(rules.PENDING_CONFIRM) == cr.PENDING


def test_awareness_is_the_earliest_counted_knowledge():  # H1
    received = datetime(2026, 11, 3, 14, 20, tzinfo=timezone.utc)
    earlier = received - timedelta(days=2)
    assert cr.case_awareness(received, None, None) == received
    assert cr.case_awareness(received, earlier, "ACTS_FOR_MANUFACTURER") == earlier
    assert cr.case_awareness(received, earlier, "PROCEDURE_DEEMS") == earlier
    assert cr.case_awareness(received, earlier, "NOT_ACTING_FOR") == received
    assert cr.case_awareness(received, received + timedelta(hours=1), "ACTS_FOR_MANUFACTURER") == received


def test_identifiers_keep_not_sure_status_and_source_and_feed_missing_information():  # ID-1
    given = {"product": True, "serial": True}
    raw = {
        "product": {"status": "confirmed", "source": "label_or_photo"},
        "serial": {"status": "CONFIRMED"},  # no source: unconfirmed
        "lot": {"not_sure": True, "source": "CALLER"},
        "version": {"not_sure": True},
        "udi": {"not_sure": True},  # Not sure is not offered for the UDI
    }
    found = cr.clean_identifiers(raw, given)
    assert found == {
        "product": {"not_sure": False, "status": "CONFIRMED", "source": "LABEL_OR_PHOTO"},
        "version": {"not_sure": True, "status": "UNCONFIRMED", "source": None},
        "lot": {"not_sure": True, "status": "UNCONFIRMED", "source": "CALLER"},
        "serial": {"not_sure": False, "status": "UNCONFIRMED", "source": None},
    }
    missing = cr.missing_information(found, _answers(_all_no(Q6=U)))
    assert [item["label"] for item in missing] == [
        "Version: not sure",
        "Lot: not sure",
        "Serial number: unconfirmed",
        "Question 6: unknown",
    ]


def test_the_service_issue_category_list_matches_the_database_check():  # S-1
    from backend.app.db.models.intake import ISSUE_CATEGORIES

    assert tuple(cr.ISSUE_CATEGORIES) == ISSUE_CATEGORIES and len(ISSUE_CATEGORIES) == 17
    assert cr.issue_category(" usage_help ") == "USAGE_HELP" and cr.ISSUE_CATEGORIES["USAGE_HELP"] == "Help with use"
    assert cr.issue_category("Broken screen") is None and cr.issue_category(None) is None


def test_waiting_for_the_internal_team_is_a_state_beside_waiting_for_the_reporter():  # S-2
    from backend.app.db.models.intake import CASE_STATES

    assert set(cr.STATES) == set(CASE_STATES)
    assert cr.STATE_LABELS[cr.WAITING_INTERNAL] == "Waiting for internal team"
    assert cr.transition_problem(cr.OPEN, cr.WAITING_INTERNAL) is None
    assert cr.transition_problem(cr.WAITING_INTERNAL, cr.ESCALATED) is None
    assert cr.transition_problem(cr.WAITING_INTERNAL, cr.CLOSED) is not None  # closing goes through the QA review


class _Audit(list):
    add = list.append


def _case(status: str, summary: str | None = None):
    from types import SimpleNamespace

    return SimpleNamespace(id="case-1", reference="CASE-1", status=status, version=3, updated_at=None,
                           resolution_summary=summary)  # fmt: skip


def test_a_service_only_case_is_never_closed_without_its_resolution_summary():  # S-2
    from backend.app.intake import service

    now = datetime(2026, 11, 10, 9, 0, tzinfo=timezone.utc)
    audit, event = _Audit(), _case(cr.IN_REVIEW)
    with pytest.raises(service.CaseStateRefused, match="resolution summary"):
        service.set_case_status(None, audit, "t", event, cr.CLOSED, "u", now, classification=rules.SERVICE_ONLY)
    assert event.status == cr.IN_REVIEW and event.version == 3
    assert [row.action for row in audit] == ["CASE_STATE_REFUSED"]
    # An inquiry needs none; a service-only Case closes once the summary is written.
    service.set_case_status(None, audit, "t", _case(cr.IN_REVIEW), cr.CLOSED, "u", now, classification=cr.INQUIRY)
    event.resolution_summary = "Replaced the probe cable; readings normal on site."
    service.set_case_status(None, audit, "t", event, cr.CLOSED, "u", now, classification=rules.SERVICE_ONLY)
    assert event.status == cr.CLOSED and event.version == 4 and audit[-1].action == "CASE_STATE_CHANGED"


def test_one_function_refuses_and_audits_a_move_the_states_do_not_allow():  # B2-08
    from backend.app.intake import service

    now = datetime(2026, 11, 10, 9, 0, tzinfo=timezone.utc)
    audit, event = _Audit(), _case(cr.ESCALATED)
    with pytest.raises(service.CaseStateRefused):
        service.set_case_status(None, audit, "t", event, cr.IN_REVIEW, "u", now)
    assert event.status == cr.ESCALATED and audit[0].details["to"] == cr.IN_REVIEW


def test_hardware_revision_and_firmware_version_keep_status_and_source():  # S-3
    given = {"hardware_revision": True, "firmware_version": True}
    raw = {
        "hardware_revision": {"status": "CONFIRMED", "source": "SERVICE_RECORD"},
        "firmware_version": {"status": "CONFIRMED", "source": "caller"},
    }
    found = cr.clean_identifiers(raw, given)
    assert found["hardware_revision"] == {"not_sure": False, "status": "CONFIRMED", "source": "SERVICE_RECORD"}
    assert found["firmware_version"] == {"not_sure": False, "status": "CONFIRMED", "source": "CALLER"}
    found["firmware_version"]["status"] = cr.UNCONFIRMED
    assert [item["label"] for item in cr.missing_information(found)] == ["Firmware version: unconfirmed"]


def test_the_case_check_offers_six_classifications_each_with_why_it_is_disabled():
    # Spec 4.4: Complaint, Complaint and service, Service only, Inquiry, Pending, Not a complaint, in that order; those
    # the answers do not give are disabled with the signature's own reason, so the screen never offers a refusal.
    found = cr.choices(rules.BOTH)
    assert [item["code"] for item in found] == [
        rules.COMPLAINT,
        rules.BOTH,
        rules.SERVICE_ONLY,
        cr.INQUIRY,
        rules.PENDING,
        cr.NOT_A_COMPLAINT,
    ]
    open_codes = {item["code"] for item in found if item["disabled_reason"] is None}
    assert open_codes == {rules.COMPLAINT, rules.BOTH, rules.PENDING}
    assert [item["code"] for item in found if item["suggested"]] == [rules.BOTH]
    assert [item["code"] for item in found if item["escalates"]] == [rules.COMPLAINT, rules.BOTH]
    assert "only when the answers give it" in next(i for i in found if i["code"] == cr.INQUIRY)["disabled_reason"]
    # "Pending" reads the suggestion's own wording; Not a complaint opens only after the follow-up confirmed it.
    confirm = cr.choices(rules.PENDING_CONFIRM)
    assert rules.PENDING_CONFIRM in [item["code"] for item in confirm]
    assert next(i for i in confirm if i["code"] == cr.NOT_A_COMPLAINT)["disabled_reason"]
    confirmed = cr.choices(rules.PENDING_CONFIRM, no_deficiency_confirmed=True)
    assert next(i for i in confirmed if i["code"] == cr.NOT_A_COMPLAINT)["disabled_reason"] is None
    # Unanswered: nothing may be signed.
    assert all(item["disabled_reason"] for item in cr.choices(cr.UNANSWERED))
    assert all(item["disabled_reason"] for item in cr.choices(None))
