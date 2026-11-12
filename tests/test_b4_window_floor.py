"""B4 step 13 (FG-1, R-D10): an organization window longer than the law warns on saving and shows the legal deadline
beside it on the watch; such windows are never refused or changed. No database."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from backend.app import feature_set
from backend.app.reportability import markets, rules

# B6b B3: the scenarios this file verifies (requirements.csv, class A); file level, so every test here carries them.
pytestmark = [pytest.mark.unit, pytest.mark.requirement("DT-33", "DT-37", "RR-01", "RR-03")]


def _window(name: str, days: int, basis: str = rules.CALENDAR, markets_: list[str] | None = None) -> dict:
    raw = {"name": name, "markets": markets_ or [], "triggers": ["DEATH"], "days": days, "day_basis": basis}
    return rules.clean_window(raw)


@pytest.mark.parametrize(
    ("window", "warned"),
    [
        (_window("US 60 days", 60, markets_=["US"]), ["US"]),
        (_window("US 30 days", 30, markets_=["US"]), []),
        (_window("US 20 work days", 20, rules.WORK, ["US"]), []),  # 28 calendar days at most
        (_window("US 23 work days", 23, rules.WORK, ["US"]), ["US"]),  # 31 or more calendar days
        # B9 IN-floor-2: 15 days (FG-2 closed); switched off, India has no legal period in code again.
        (
            _window("India 60 days", 60, markets_=["India"]),
            ["IN"] if feature_set.switched_on("MDARIX_B9_INDIA") else [],
        ),
        # Longer than 15 days; US and Canada allow 30 (and India 15 with B9's IN-floor-2).
        (
            _window("Everywhere 20 days", 20),
            ["EU_NI", "GB", *(["IN"] if feature_set.switched_on("MDARIX_B9_INDIA") else [])],
        ),
    ],
)
def test_a_window_longer_than_the_law_is_named_with_the_legal_period(window, warned):
    found = markets.longer_than_law([window])
    assert [item["market"] for item in found] == warned
    assert all(item["window"] == window["name"] and item["legal"] in item["message"] for item in found)


def test_the_watch_shows_the_legal_deadline_beside_a_longer_window_only():
    aware = datetime(2027, 1, 4, 15, tzinfo=timezone.utc)
    record = {"country": "US", "death": True}
    (clock,) = rules.clocks(record, [_window("US 60 days", 60, markets_=["US"])], aware, aware)
    legal = clock.as_dict()["legal"]
    assert legal["label"] == markets.REPORT_TYPES["US_30_DAY"].label
    assert legal["due_date"] == "2027-02-03" and clock.due.isoformat() == "2027-03-05"
    (same,) = rules.clocks(record, [_window("US 30 days", 30, markets_=["US"])], aware, aware)
    assert "legal" not in same.as_dict()  # unchanged on the wire when the window is within the law


def test_switched_off_there_is_no_warning_and_no_legal_clock(monkeypatch):
    """Spec 6.4: with MDARIX_RULE_REGISTER=off the windows and the watch are today's, FG-1 included."""
    monkeypatch.setenv("MDARIX_RULE_REGISTER", "off")
    window = _window("US 60 days", 60, markets_=["US"])
    assert markets.longer_than_law([window]) == []
    aware = datetime(2027, 1, 4, 15, tzinfo=timezone.utc)
    (clock,) = rules.clocks({"country": "US", "death": True}, [window], aware, aware)
    assert "legal" not in clock.as_dict()
