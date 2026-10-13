"""The second look's and the backlog board's rules (backend/app/complaint_review/rules.py), without a database."""

from __future__ import annotations

from datetime import date

import pytest

from backend.app.complaint_review import rules


@pytest.mark.parametrize(
    "status", ["Cancelled", "CANCELED", " void ", "Rejected", "not_a_complaint", "Not-A-Complaint"]
)
def test_cancelled_in_the_spellings_systems_use(status):
    assert rules.is_cancelled(status)


@pytest.mark.parametrize("status", ["open", "Closed", "Under investigation", "", None, "cancel pending review"])
def test_other_statuses_are_not_cancelled(status):
    assert not rules.is_cancelled(status)


def test_inquiries_and_service_records_by_status_or_type():
    assert rules.is_inquiry("Inquiry", None)
    assert rules.is_inquiry("open", "Service Request")
    assert rules.is_inquiry(None, "General enquiry")
    assert rules.is_inquiry("RMA", None)
    assert not rules.is_inquiry("open", "Device malfunction")


@pytest.mark.parametrize(
    "value,family",
    [
        ("NFF", rules.NO_FAULT_FOUND),
        ("No fault found", rules.NO_FAULT_FOUND),
        ("NO_PROBLEM_FOUND", rules.NO_FAULT_FOUND),
        ("Could not reproduce", rules.NO_FAULT_FOUND),
        ("Unable to duplicate", rules.NO_FAULT_FOUND),
        ("User Error", rules.USER_ERROR),
        ("use-error", rules.USER_ERROR),
        ("Customer misuse", rules.USER_ERROR),
        ("OCCLUSION", None),
        ("Sniff test failed", None),
        (None, None),
    ],
)
def test_no_fault_found_and_user_error_families(value, family):
    assert rules.nff_family(value) == family


def test_words_match_whole_words_and_phrases_across_separators():
    words = rules.DEFAULT_WORDS
    found = rules.matched_words("Patient had SHORTNESS-OF-BREATH and was choking; device not painted", words)
    assert "shortness of breath" in found and "choking" in found
    assert "pain" not in found  # "painted" is not the word "pain"
    assert rules.matched_words("Pump stopped working, error code E12", words) == ["stopped working", "error code"]
    assert rules.matched_words("", words) == []


def _record(**fields):
    base = {
        "status": "open",
        "complaint_type": None,
        "problem_code": None,
        "severity": None,
        "description": "Customer feedback about the colour of the casing",
        "patient_involved": None,
        "serious_injury": None,
        "death": None,
        "malfunction": None,
        "product_name": "Infusion Pump",
    }
    return {**base, **fields}


def test_a_cancelled_record_with_a_death_is_flagged_first():
    death = rules.flag(_record(status="Cancelled", death=True), rules.DEFAULT_WORDS)
    words = rules.flag(_record(status="Cancelled", description="Patient was choking"), rules.DEFAULT_WORDS)
    assert death and words
    assert [item["code"] for item in death.reasons] == [rules.CANCELLED]
    assert [item["code"] for item in death.signs] == ["DEATH"]
    assert death.score > words.score
    assert words.words == ["choking"]
    assert "Cancelled or rejected (status: Cancelled)" == death.reasons[0]["label"]


def test_a_cancelled_record_or_an_inquiry_without_a_complaint_sign_is_not_flagged():
    assert rules.flag(_record(status="Cancelled"), rules.DEFAULT_WORDS) is None
    assert rules.flag(_record(complaint_type="Inquiry"), rules.DEFAULT_WORDS) is None
    # An ordinary open complaint is not a second-look record at all.
    assert rules.flag(_record(death=True), rules.DEFAULT_WORDS) is None


def test_an_inquiry_with_complaint_signs_is_flagged():
    found = rules.flag(
        _record(complaint_type="Service request", malfunction=True, problem_code="E12"), rules.DEFAULT_WORDS
    )
    assert [item["code"] for item in found.reasons] == [rules.INQUIRY]
    assert {item["code"] for item in found.signs} == {"MALFUNCTION", "PROBLEM_CODE"}


def test_no_fault_found_is_flagged_only_when_it_recurs():
    record = _record(status="closed", problem_code="NFF")
    assert rules.flag(record, rules.DEFAULT_WORDS, nff_count=2) is None
    found = rules.flag(record, rules.DEFAULT_WORDS, nff_count=3)
    assert [item["code"] for item in found.reasons] == [rules.NFF_RECURRING]
    assert found.reasons[0]["label"] == "No Fault Found recurs: 3 records on Infusion Pump in 12 months"
    # The No Fault Found code is the reason, not a problem-code sign.
    assert not any(item["code"] == "PROBLEM_CODE" for item in found.signs)


def test_the_organizations_own_words_replace_the_defaults():
    record = _record(status="Void", description="Casing discoloured after cleaning")
    assert rules.flag(record, rules.DEFAULT_WORDS) is None
    assert rules.flag(record, ["discoloured"]).words == ["discoloured"]


def test_what_counts_as_open_on_the_backlog_board():
    assert rules.counts_as_open("open", None, None)
    assert rules.counts_as_open("Under investigation", "Device malfunction", None)
    assert not rules.counts_as_open("Closed", None, None)
    assert not rules.counts_as_open("Cancelled", None, None)
    assert not rules.counts_as_open("open", "Inquiry", None)
    # Confirmed on the second look: it counts until it is closed. Dismissed: never.
    assert rules.counts_as_open("Cancelled", None, "CONFIRMED")
    assert rules.counts_as_open("open", "Inquiry", "CONFIRMED")
    assert not rules.counts_as_open("Closed", None, "CONFIRMED")
    assert not rules.counts_as_open("open", None, "DISMISSED")


@pytest.mark.parametrize(
    "age,state", [(0, "ON_TRACK"), (23, "ON_TRACK"), (24, "DUE_SOON"), (30, "DUE_SOON"), (31, "PAST_TARGET")]
)
def test_backlog_state_against_a_30_day_target(age, state):
    assert rules.backlog_state(age, 30) == state


def test_a_short_target_has_no_negative_due_soon_window():
    assert rules.backlog_state(0, 5) == "DUE_SOON"
    assert rules.backlog_state(6, 5) == "PAST_TARGET"


@pytest.mark.parametrize("age,band", [(0, "0-30"), (30, "0-30"), (31, "31-60"), (90, "61-90"), (91, "90+")])
def test_age_bands(age, band):
    assert rules.age_band(age) == band


def test_age_in_days():
    assert rules.age_days(date(2026, 9, 1), date(2026, 10, 1)) == 30
    assert rules.age_days(date(2026, 10, 2), date(2026, 10, 1)) == 0
    assert rules.age_days(None, date(2026, 10, 1)) is None


def test_word_lists_are_cleaned_and_checked():
    assert rules.clean_words(["  Choking ", "choking", "", "Short  of breath", None]) == ["choking", "short of breath"]
    assert rules.clean_words("choking") == []
    assert rules.words_problem([]) == "Keep at least one word"
    assert rules.words_problem(["x" * 61]).startswith('"xxxxxxxxxxxxxxxxxxxx…" is longer')
    assert rules.words_problem([f"w{i}" for i in range(101)]) == "Keep at most 100 words"
    assert rules.words_problem(["choking"]) is None
