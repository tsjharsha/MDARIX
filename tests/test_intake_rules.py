"""The first contact, the triage flag, the awareness rule, provisional deadlines and duplicates as plain functions
(T-G32, T-G19, T-G20; MVP G32's outcomes table and acceptance A20, 5.1b). No database."""

from datetime import date, datetime, timedelta, timezone

import pytest

from backend.app.import_quarantine import harm_words as quarantine_harm
from backend.app.intake import rules

pytestmark = pytest.mark.unit


def answers(default: str = "NO", **given) -> dict:
    found = {question: {"answer": default} for question in rules.QUESTION_IDS}
    for question, value in given.items():
        found[question] = value if isinstance(value, dict) else {"answer": value}
    return rules.clean_answers(found)


def test_the_clear_outcomes_of_a20a():
    # Routine maintenance or an IFU request, no fault alleged: service only.
    assert rules.outcome(answers(Q7="YES")) == rules.SERVICE_ONLY
    # Not applicable needs a reason for "service only" to be offered.
    assert rules.outcome(answers(Q7="YES", Q4={"answer": "NOT_APPLICABLE", "note": "No patient use"})) == "SERVICE_ONLY"
    assert rules.outcome(answers(Q7="YES", Q4="NOT_APPLICABLE")) != rules.SERVICE_ONLY
    # An inaccurate reading with a repair needed: both, never service only.
    assert rules.outcome(answers(Q2="YES", Q8="YES")) == rules.BOTH


def test_pending_outcomes_of_a20b():
    assert rules.outcome(answers(Q1="UNKNOWN")) == rules.PENDING
    silent = answers(Q4="NOT_STATED", Q5="NOT_STATED", Q6="NOT_STATED")
    assert rules.outcome(silent) == rules.PENDING
    assert rules.outcome(answers(Q1="YES", Q4="NOT_STATED", Q5="NOT_STATED", Q6="NOT_STATED")) == rules.COMPLAINT
    # No on all of questions 1-9: confirm no deficiency, never complaint or service only by default.
    assert rules.outcome(answers()) == rules.PENDING_CONFIRM
    # Its follow-up closed unresolved after attempts: a complaint.
    assert rules.outcome(answers(), unresolved=True) == rules.COMPLAINT


def test_precedence_of_a20c():
    assert rules.outcome(answers(Q9="YES")) == rules.COMPLAINT
    assert rules.outcome(answers(Q2="YES", Q6="UNKNOWN", Q8="YES")) == rules.BOTH
    assert rules.outcome(answers(Q3="YES", Q5="UNKNOWN")) == rules.COMPLAINT
    assert rules.outcome(answers(Q8="YES")) == rules.BOTH
    # Unanswered counts as Unknown, never as No.
    assert rules.outcome({}) == rules.PENDING


def test_service_only_is_never_offered_with_not_stated_on_questions_4_to_6():
    for question in rules.HARM_QUESTIONS:
        result = rules.outcome(answers(Q7="YES", **{question: "NOT_STATED"}))
        assert result == rules.PENDING, question
        assert (
            rules.classification_problem(result, rules.SERVICE_ONLY, "Override reason long enough", "Reason x10")
            is not None
        )


def test_not_stated_is_kept_only_on_questions_4_to_6():
    cleaned = rules.clean_answers({"Q1": {"answer": "NOT_STATED"}, "Q4": {"answer": "not_stated"}})
    assert cleaned["Q1"]["answer"] is None and cleaned["Q4"]["answer"] == rules.NOT_STATED


def test_what_the_coordinator_may_sign():
    assert rules.classification_problem(rules.COMPLAINT, rules.COMPLAINT, "", "") is None
    assert "override" in rules.classification_problem(rules.PENDING, rules.COMPLAINT, "short", "")
    assert rules.classification_problem(rules.PENDING, rules.COMPLAINT, "The reporter confirmed a fault", "") is None
    assert "only when" in rules.classification_problem(rules.COMPLAINT, rules.SERVICE_ONLY, "a" * 20, "a" * 20)
    assert "written reason" in rules.classification_problem(rules.SERVICE_ONLY, rules.SERVICE_ONLY, "", "short")


def test_the_triage_flag_is_raised_at_once_by_harm_answers_and_words():
    assert [f["code"] for f in rules.intake_flags("CONTACT", "Pump alarmed", answers(Q5="UNKNOWN"))] == [
        "FIRST_CONTACT"
    ]
    assert rules.intake_flags("CONTACT", "Asked for a manual", answers(Q4="NOT_STATED")) == []
    with_word = rules.intake_flags("CONTACT", "The pt was moved to ICU", answers(Q4="NOT_STATED"))
    assert {f["code"] for f in with_word} == {"FIRST_CONTACT", "HARM_WORDS"}
    deficiency = rules.intake_flags("CONTACT", "Wrong reading", answers(Q1="YES", Q4="NOT_STATED"))
    assert [f["code"] for f in deficiency] == ["FIRST_CONTACT"]
    assert rules.intake_flags("URGENT", "Anything", {})[0]["code"] == "URGENT_INTAKE"


def test_harm_words_with_abbreviations_and_a_negated_mention():
    assert rules.harm_words("The pt was moved to ICU.") == ["ICU", "pt"]
    assert rules.harm_words("Device returned; no patient injury reported. No harm.") == []
    # "not" never negates: a conservative reading.
    assert rules.harm_words("Patient not injured, it seems") == ["injured"]
    assert rules.harm_words("Patient was harmed") == ["harmed"]
    # The set-aside rows read the same list.
    assert quarantine_harm({"description": "the patient was taken to hospital"}) == ["hospital"]


def test_complaint_flags():
    flags = rules.complaint_flags({"patient_involved": True, "malfunction": True, "description": "No harm."})
    assert [f["code"] for f in flags] == ["HARM_UNKNOWN", "MALFUNCTION"]
    assert rules.complaint_flags({"patient_involved": True, "serious_injury": False, "death": False}) == []
    assert rules.complaint_flags({"severity": "Critical"})[0]["code"] == "HARM_LEVEL"


NOW = datetime(2026, 11, 20, 12, 0, tzinfo=timezone.utc)


def test_the_awareness_rule():
    found = rules.awareness(None, [(NOW - timedelta(hours=30), "FIRST_KNOWLEDGE"), (NOW, "RECEIVED")], NOW)
    assert found == {"at": NOW - timedelta(hours=30), "source": "FIRST_KNOWLEDGE", "unresolved": True}
    assert rules.awareness(None, [(None, "RECEIVED")], NOW)["source"] == "AVAILABLE"
    recorded = rules.awareness(NOW - timedelta(days=1), [(NOW - timedelta(days=3), "RECEIVED")], NOW)
    assert recorded["source"] == "AWARENESS" and not recorded["unresolved"]
    earliest = rules.awareness(NOW - timedelta(days=1), [(NOW - timedelta(days=3), "RECEIVED")], NOW, earliest=True)
    assert earliest["source"] == "RECEIVED" and not earliest["unresolved"]


def test_provisional_deadlines_by_tier():
    today = date(2026, 11, 20)  # a Friday
    flagged = {d["market"]: d for d in rules.provisional_deadlines(NOW, ["US", "EU_NI"], rules.FLAGGED, today)}
    assert flagged["EU_NI"]["due_date"] == "2026-11-30" and flagged["US"]["due_date"] == "2026-12-20"
    threat = {d["market"]: d for d in rules.provisional_deadlines(NOW, ["US", "EU_NI"], rules.THREAT, today)}
    assert threat["EU_NI"]["due_date"] == "2026-11-22" and threat["US"]["due_date"] == "2026-11-27"
    remedial = rules.provisional_deadlines(NOW, ["US"], rules.FLAGGED, today, remedial=True)
    assert remedial[0]["days"] == 5 and remedial[0]["day_basis"] == "WORK"
    unflagged = {d["market"]: d["days"] for d in rules.provisional_deadlines(NOW, [], rules.UNFLAGGED, today)}
    # Canada (0.10.76): 30 days for an incident that could cause serious deterioration if it recurred.
    assert unflagged == {"US": 30, "EU_NI": 15, "GB": 15, "IN": 15, "CA": 30}


# Where the triage tier's date is later than the earliest clock the market rules give a pending assessment (code audit
# 3: the starter windows and the report an unanswered draft would start), once triage has answered the question.
TRIAGE_LATER_THAN_MARKET_RULES = {
    ("US", "FLAGGED"),  # 30 calendar days; an unanswered question 6 keeps the 5-work-day report (803.53)
    ("US", "UNFLAGGED"),
    ("EU_NI", "FLAGGED"),  # 10 days; an unanswered question 4 keeps the 2-day threat report (Art. 87(4))
    ("EU_NI", "UNFLAGGED"),  # 15 days
    ("GB", "FLAGGED"),
    ("GB", "UNFLAGGED"),
    ("CA", "UNFLAGGED"),  # 30 days; an unanswered question 3 keeps the 10-day report
}
LEVELS = ((rules.THREAT, False), (rules.FLAGGED, False), (rules.FLAGGED, True), (rules.UNFLAGGED, False))


def _pending_clock(market):
    from backend.app.reportability import markets
    from backend.app.reportability import rules as watch_rules

    windows = [watch_rules.clean_window(template) for template in watch_rules.TEMPLATES]
    if_reportable = markets.evaluate(market, {})["report_type_if_reportable"]
    return markets.market_clock(market, markets.PENDING, None, windows, NOW, NOW, None, if_reportable)


def test_triage_tier_dates_against_the_earliest_market_clock():
    """Check 3a (owner, 10 Nov 2026: "earliest until answered"): while triage has not answered the question that
    decides the shorter report, the triage date is never later than the clock a pending market assessment shows with
    no answer yet, for every market and tier; a date earlier than the tier's carries the plain note."""
    from backend.app.reportability import markets

    compared = 0
    for market in markets.MARKETS:
        clock = _pending_clock(market)
        for level, remedial in LEVELS:
            triage = rules.provisional_deadlines(NOW, [market], level, NOW, remedial, own=market, answered=False)[0]
            tier = rules.provisional_deadlines(NOW, [market], level, NOW, remedial, own=market)[0]
            compared += 1
            assert triage["due_date"] <= clock["due_date"], (market, level, remedial)
            assert (triage["earliest_note"] is not None) == (triage["due_at"] < tier["due_at"]), (market, level)
    assert compared == 4 * len(markets.MARKETS)


EARLIEST = {
    "US": ("5 work days unless remedial action is ruled out", "2026-11-27"),
    "EU_NI": ("2 days unless a public health threat is ruled out", "2026-11-22"),
    "GB": ("2 days unless a public health threat is ruled out", "2026-11-21"),  # the awareness day is day 1 in GB
    "CA": ("10 days unless death or serious deterioration is ruled out", "2026-11-30"),
}


@pytest.mark.parametrize("market", sorted(EARLIEST))
def test_unanswered_shows_the_earliest_report_and_answered_the_tier_date(market):
    """Check 3a, per market: an unflagged item before triage answers shows the earliest possible report with its note;
    once triage answers it, the tier date applies (later than the market's pending clock, as pinned above)."""
    note, due = EARLIEST[market]
    pending = rules.provisional_deadlines(NOW, [market], rules.UNFLAGGED, NOW, own=market, answered=False)[0]
    assert (pending["earliest_note"], pending["due_date"], pending["tier"]) == (note, due, rules.UNFLAGGED)
    answered = rules.provisional_deadlines(NOW, [market], rules.UNFLAGGED, NOW, own=market, answered=True)[0]
    assert answered["earliest_note"] is None and answered["due_date"] > due
    assert answered["due_date"] > _pending_clock(market)["due_date"]
    assert (market, rules.UNFLAGGED) in TRIAGE_LATER_THAN_MARKET_RULES
    # A marked threat (the THREAT tier) is the earliest report already: no note.
    threat = rules.provisional_deadlines(NOW, [market], rules.THREAT, NOW, own=market, answered=False)[0]
    assert threat["earliest_note"] is None


def test_india_has_no_earlier_report_to_show():
    pending = rules.provisional_deadlines(NOW, ["IN"], rules.UNFLAGGED, NOW, own="IN", answered=False)[0]
    assert pending["earliest_note"] is None and pending["days"] == 15


def test_both_clocks_and_the_delay():
    clock = rules.triage_clock(NOW - timedelta(hours=20), NOW)
    assert clock["hours_left"] == 4.0 and clock["state"] == "DUE_SOON"
    assert rules.triage_clock(NOW - timedelta(hours=30), NOW)["state"] == "OVERDUE"
    assert rules.delay_text(NOW - timedelta(days=8), NOW)["text"] == "8 days"


def test_possible_duplicates():
    a = {
        "product_id": 1,
        "lot_id": "L4",
        "serial": None,
        "site": None,
        "country": "Germany",
        "event_on": date(2026, 10, 18),
    }
    b = {**a, "site": "Klinikum", "event_on": date(2026, 10, 19)}
    assert rules.duplicate_reasons(a, b) == ["same product", "same lot", "event dates within 2 days", "same country"]
    assert rules.duplicate_reasons(a, {**b, "event_on": date(2026, 10, 22)}) == []
    assert rules.duplicate_reasons(a, {**b, "lot_id": "L3"}) == []
    assert rules.duplicate_reasons(a, {**b, "country": "France"}) == []
    assert rules.duplicate_reasons(a, {**b, "product_id": 2}) == []


def test_triage_shows_the_events_own_market_first_and_a_signed_conclusion_instead_of_its_provisional_deadline():
    # J3 (0.10.63): a US event showed "EU MDR ... 14 days overdue" first, the earliest across every enabled market, and
    # an EU event concluded reportable kept its 10-day provisional date beside the signed 15-day one.
    today = date(2026, 11, 20)
    us_event = rules.provisional_deadlines(NOW, ["US", "EU_NI", "IN"], rules.FLAGGED, today, own="US")
    assert [(d["market"], d["role"]) for d in us_event] == [("US", "OWN"), ("EU_NI", "IF_ALSO"), ("IN", "IF_ALSO")]
    assert us_event[1]["role_label"] == "If also reportable"
    signed_clock = {
        "window": "EU MDR: serious incident (15 days)",
        "days": 15,
        "day_basis": "CALENDAR",
        "due_date": "2026-12-05",
        "due_at": "2026-12-05T22:59:59+00:00",
        "due_zone": "Europe/Brussels",
        "due_label": "Sat 5 Dec 2026, 23:59 CET",
        "days_left": 15,
        "state": "RUNNING",
    }
    eu_event = rules.provisional_deadlines(
        NOW, ["US", "EU_NI"], rules.FLAGGED, today, own="EU_NI", signed={"EU_NI": signed_clock}
    )
    assert eu_event[0]["market"] == "EU_NI" and eu_event[0]["role"] == "SIGNED" and eu_event[0]["days"] == 15
    assert eu_event[0]["due_label"] == "Sat 5 Dec 2026, 23:59 CET" and eu_event[1]["role"] == "IF_ALSO"
    concluded = rules.provisional_deadlines(NOW, ["US", "EU_NI"], rules.FLAGGED, today, own="US", signed={"US": None})
    assert concluded[0]["market"] == "US" and concluded[0]["not_reportable"] and concluded[0]["due_at"] is None
    # No country: every enabled market, none of them "if also".
    unknown = rules.provisional_deadlines(NOW, ["US", "EU_NI"], rules.FLAGGED, today)
    assert {d["role"] for d in unknown} == {"NO_COUNTRY"}
    # A Great Britain event where only the US and the EU have windows: not "if also", its own market has none.
    british = rules.provisional_deadlines(NOW, ["US", "EU_NI"], rules.FLAGGED, today, own="GB")
    assert {d["role"] for d in british} == {"OWN_NO_WINDOW"}
    # An in-vitro diagnostic's EU deadline cites the IVDR (starter), not the MDR.
    ivd = rules.provisional_deadlines(NOW, ["EU_NI"], rules.FLAGGED, today, own="EU_NI", ivd=True)
    assert ivd[0]["basis"] == "10 days (EU IVDR Art. 82, starter)"
