"""B9 review 6: triage's provisional clocks and the watch's pending clocks count by the organization's role floor in the
market. A user facility's clock is 10 work days (803.30), never the manufacturer's 30 days; an importer has no 5-work-day
report; a manufacturer's clocks are unchanged; with a role's switch off the clocks are today's. No database."""

from __future__ import annotations

from datetime import date, datetime, timezone
from types import SimpleNamespace

import pytest

from backend.app.intake import rules
from backend.app.reportability import assessments, markets
from backend.app.reportability import rules as watch_rules
from backend.app.reportability.service import effective_roles

pytestmark = pytest.mark.unit

NOW = datetime(2026, 10, 1, 15, 0, tzinfo=timezone.utc)  # a Thursday
LEVELS = (rules.THREAT, rules.FLAGGED, rules.UNFLAGGED)
UNKNOWN = {"US1": {"answer": "NO"}}  # the rest Unknown: the US rules stay pending


@pytest.fixture(autouse=True)
def _switches(monkeypatch):
    monkeypatch.delenv("MDARIX_B9_US_IMPORTER", raising=False)
    monkeypatch.setenv("MDARIX_B9_US_USER_FACILITY", "on")
    monkeypatch.delenv("MDARIX_RULE_REGISTER", raising=False)


def _us(level: str, remedial: bool = False, answered: bool = True, roles: dict | None = None) -> dict:
    found = rules.provisional_deadlines(
        NOW, ["US"], level, NOW, remedial, own="US", org_zone="UTC", answered=answered, roles=roles
    )
    return found[0]


def _each():
    for level in LEVELS:
        for remedial in (False, True):
            for answered in (False, True):
                yield level, remedial, answered


def test_a_user_facility_triage_clock_is_10_work_days_at_every_tier():
    for level, remedial, answered in _each():
        found = _us(level, remedial, answered, {"US": "USER_FACILITY"})
        assert (found["days"], found["day_basis"]) == (10, "WORK"), (level, remedial, answered)
        assert "803.30" in found["basis"] and found["earliest_note"] is None
    # The manufacturer's unflagged clock is 30 days: the user facility's is earlier, so it never showed later.
    assert _us(rules.UNFLAGGED, roles={"US": "USER_FACILITY"})["due_at"] < _us(rules.UNFLAGGED)["due_at"]


def test_an_importer_has_no_5_work_day_clock():
    for level, remedial, answered in _each():
        found = _us(level, remedial, answered, {"US": "IMPORTER"})
        assert (found["days"], found["day_basis"]) == (30, "CALENDAR"), (level, remedial, answered)
        assert "803.40" in found["basis"]
    assert rules.earliest_report("US", NOW, "UTC", "IMPORTER").days == 30
    assert rules.earliest_report("US", NOW, "UTC").days == 5


def test_a_manufacturers_clocks_are_unchanged():
    for level, remedial, answered in _each():
        today = _us(level, remedial, answered)
        assert _us(level, remedial, answered, {}) == today
        assert _us(level, remedial, answered, {"IN": "IMPORTER", "CA": "IMPORTER"}) == today
    assert (_us(rules.THREAT)["days"], _us(rules.UNFLAGGED, answered=False)["days"]) == (5, 5)
    assert _us(rules.UNFLAGGED)["days"] == 30


def test_with_the_switches_off_the_clocks_are_todays(monkeypatch):
    monkeypatch.setenv("MDARIX_B9_US_IMPORTER", "off")
    monkeypatch.delenv("MDARIX_B9_US_USER_FACILITY")  # its default: off
    stored = {"US": "USER_FACILITY"}
    assert effective_roles(stored) == {} and effective_roles({"US": "IMPORTER"}) == {}
    for level, remedial, answered in _each():
        today = _us(level, remedial, answered)
        # Even a role passed straight in reads the manufacturer's floor: an off role floor is never picked.
        assert _us(level, remedial, answered, stored) == today == _us(level, remedial, answered, {"US": "IMPORTER"})


def _watch(roles: dict | None) -> dict:
    fda = watch_rules.clean_window(watch_rules.TEMPLATES[0])
    draft = SimpleNamespace(
        conclusion=None, answers=UNKNOWN, suggested_conclusion=markets.PENDING, report_type=None, version=1
    )
    aware, today = date(2026, 10, 1), date(2026, 10, 2)
    summary = assessments.markets_summary({"country": "USA"}, [fda], {markets.US: [draft]}, aware, today, "UTC", roles)
    return summary[0]["clock"]


def test_the_watchs_pending_clock_counts_by_the_role_floor():
    maker = _watch(None)
    assert maker["due_date"] == "2026-10-08"  # 5 work days: remedial action is not ruled out
    assert _watch({}) == maker
    facility = _watch({"US": "USER_FACILITY"})
    assert facility["due_date"] == "2026-10-15"  # 10 work days (803.30)
    importer = _watch({"US": "IMPORTER"})
    assert importer["due_date"] == "2026-10-31"  # 30 days (803.40), never 5 work days
