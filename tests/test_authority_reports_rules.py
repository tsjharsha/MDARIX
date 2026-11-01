"""The obligation lifecycle's pure rules (backend/app/authority_reports/rules.py) and the forms' structure
(forms.py): G2b's decision table rows 1-4 with the eMDR defaults, the difference review, and the field order."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from backend.app.authority_reports import forms, rules

DUE = date(2026, 12, 4)
END = datetime(2026, 12, 5, tzinfo=timezone.utc)


def _row(left: timedelta) -> dict:
    return rules.follow_up(END - left, DUE, "EMDR")


def test_the_decision_table_with_the_emdr_defaults():
    assert _row(timedelta(days=1))["row"] == 1  # ample time: follow up after the wait
    assert _row(timedelta(hours=4, minutes=30))["row"] == 2  # the wait would end inside the margin
    assert _row(timedelta(hours=1)) == {"row": 3, "at": (END - timedelta(minutes=45)).isoformat(), "late": False}
    assert _row(timedelta(minutes=30))["row"] == 3  # 15 minutes left after the follow-up
    for left in (timedelta(minutes=29), timedelta(minutes=15), timedelta(minutes=5)):
        assert _row(left)["row"] == 4  # act at once
    late = rules.follow_up(END + timedelta(hours=1), DUE, "EMDR")
    assert late["row"] == 4 and late["late"]


def test_no_follow_up_leaves_less_than_the_earliest_follow_up_time():
    for minute in range(0, 24 * 60, 7):
        submitted = END - timedelta(minutes=minute)
        found = rules.follow_up(submitted, DUE, "EMDR")
        if found["row"] in (1, 2, 3):
            assert END - datetime.fromisoformat(found["at"]) >= timedelta(minutes=15)


def test_the_difference_review():
    assert rules.difference_problem([], False).startswith("Say whether")
    assert rules.difference_problem([], True) is None
    assert "re-approval" in rules.difference_problem([{"classification": "MATERIAL", "reason": ""}], False)
    assert "reason" in rules.difference_problem([{"classification": "NON_MATERIAL", "reason": "short"}], False)
    assert (
        rules.difference_problem([{"classification": "NON_MATERIAL", "reason": "Portal shortened B5"}], False) is None
    )


def test_the_forms_keep_the_authorities_section_order_and_unique_fields():
    assert [section.code for section in forms.FDA_3500A.sections] == ["FRONT", "A", "B", "C", "D", "E", "F", "G", "H"]
    assert [section.code for section in forms.MVPI_MDAE.sections][:4] == ["PRIMARY", "REPORTER", "CATEGORY", "A"]
    for form in forms.FORMS.values():
        ids = [item.id for item in form.fields()]
        assert len(ids) == len(set(ids)), form.code
    # Patient fields are never filled from a record.
    assert all(item.source is None for item in forms.FDA_3500A.fields() if item.personal)
