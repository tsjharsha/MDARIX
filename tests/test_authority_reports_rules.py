"""The obligation lifecycle's pure rules (backend/app/authority_reports/rules.py) and the forms' structure
(forms.py): G2b's decision table rows 1-4 with the eMDR defaults, the difference review, and the field order."""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from backend.app.authority_reports import forms, rules
import pytest

DUE = date(2026, 12, 4)
# The end of the latest day: 23:59:59 in the counting time zone (UTC here: no market, no organization zone; 0.10.63).
END = datetime(2026, 12, 4, 23, 59, 59, tzinfo=timezone.utc)


# B6b B3: the scenarios this file verifies (requirements.csv, class A); file level, so every test here carries them.
pytestmark = pytest.mark.requirement("RG-15", "RG-16", "RG-17")


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


def test_audit4_re_signing_with_the_same_report_type_supersedes_the_old_conclusions_snapshots(monkeypatch):
    """Code audit 4: a conclusion signed again (new version, same report type and date) ends the pending and approved
    snapshots of the old one, so its content cannot be submitted and the new signer cannot approve the old text; an
    approved report is a draft again. The same conclusion following again changes nothing."""
    import uuid
    from types import SimpleNamespace

    from backend.app.authority_reports import router

    old, new = uuid.uuid4(), uuid.uuid4()
    snapshots = [
        SimpleNamespace(id=uuid.uuid4(), version=1, state="SUPERSEDED"),
        SimpleNamespace(id=uuid.uuid4(), version=2, state="APPROVED"),
        SimpleNamespace(id=uuid.uuid4(), version=3, state="PENDING"),
    ]
    audits = []
    monkeypatch.setattr(router, "_snapshots", lambda db, obligation: snapshots)
    monkeypatch.setattr(router, "_audit", lambda db, ctx, action, obligation, *a, **k: audits.append((action, k)))
    obligation = SimpleNamespace(
        state=rules.APPROVED,
        report_type="US_30_DAY",
        due_on=DUE,
        due_provisional=False,
        assessment_id=old,
        parent_id=None,  # an initial report (0.10.96: a US follow-up keeps its own clock)
        form_code="FDA_3500A",
    )
    signed = SimpleNamespace(id=new, report_type="US_30_DAY", due_on=DUE, version=2)
    ended = router.follow_signed(None, None, obligation, signed, datetime(2026, 11, 10, tzinfo=timezone.utc))
    assert ended == [snapshots[2].id]
    assert [row.state for row in snapshots] == ["SUPERSEDED"] * 3
    assert (obligation.state, obligation.assessment_id) == (rules.DRAFT, new)
    assert audits == [("REPORT_RESIGNED_BY_CONCLUSION", {"version": 2, "superseded": [2, 3]})]
    snapshots.append(SimpleNamespace(id=uuid.uuid4(), version=4, state="PENDING"))
    assert router.follow_signed(None, None, obligation, signed, datetime(2026, 11, 10, tzinfo=timezone.utc)) == []
    assert snapshots[3].state == "PENDING" and len(audits) == 1
