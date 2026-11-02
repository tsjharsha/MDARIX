"""One legal deadline per market, counted one way (0.10.63, quality plan stage 2; backend/app/reportability/deadlines.py).

Starter counting rules, for the consultant to confirm: awareness is converted into a time zone before its day is
taken; the US and the EU count from the day after awareness, Great Britain and India count the awareness day as day 1;
the latest day is the earlier of the day counted in the authority's time zone and the organization's, and ends at the
earlier of the two ends of that day. Each case below failed on 0.10.62, which took the UTC date of awareness, added the
window's days, and ended the day at midnight UTC (J15).
"""

from __future__ import annotations

from datetime import date, datetime, timezone

from backend.app.intake import rules as intake_rules
from backend.app.reportability import deadlines, rules

UTC = timezone.utc


def test_india_counts_the_awareness_day_as_day_1_and_ends_in_india_time():
    # 0.10.62: day 15 was 8 Nov (awareness + 15) at midnight UTC (05:30 IST on 9 Nov).
    aware = datetime(2026, 10, 24, 12, 0, tzinfo=UTC)
    found = deadlines.count(aware, 15, rules.CALENDAR, "IN", "UTC")
    assert found.day == date(2026, 11, 7) and found.zone == "Asia/Kolkata"
    assert found.at == datetime(2026, 11, 7, 18, 29, 59, tzinfo=UTC)
    assert found.label == "Sat 7 Nov 2026, 23:59 IST"


def test_the_requirements_example_awareness_in_the_uk_evening_is_the_next_day_in_india():
    # MVP 5.1a: 21:35 BST on Fri 23 Apr 2027 is 02:05 IST on Sat 24 Apr: day 1 is 24 Apr, day 15 ends with 8 May (IST).
    aware = datetime(2027, 4, 23, 20, 35, tzinfo=UTC)
    found = deadlines.count(aware, 15, rules.CALENDAR, "IN", "Asia/Kolkata")
    assert found.day == date(2027, 5, 8) and found.label == "Sat 8 May 2027, 23:59 IST"


def test_a_late_evening_us_awareness_counts_from_the_us_day_across_the_end_of_daylight_saving():
    # 21:00 EDT on Fri 2 Oct 2026 is already Sat 3 Oct in UTC: 0.10.62 gave Mon 2 Nov. Day 30 from Fri 2 Oct is Sun 1 Nov,
    # the day New York leaves daylight saving: it ends at 23:59 EST (04:59 UTC on 2 Nov).
    aware = datetime(2026, 10, 3, 1, 0, tzinfo=UTC)
    found = deadlines.count(aware, 30, rules.CALENDAR, "US", "America/New_York")
    assert found.day == date(2026, 11, 1)
    assert found.at == datetime(2026, 11, 2, 4, 59, 59, tzinfo=UTC) and found.label == "Sun 1 Nov 2026, 23:59 EST"


def test_an_organization_in_india_reporting_to_the_fda_ends_at_the_end_of_its_own_day():
    # The earlier of the two ends: the US day ends at 23:59 IST in India, ten and a half hours before New York's.
    aware = datetime(2026, 10, 3, 1, 0, tzinfo=UTC)
    found = deadlines.count(aware, 30, rules.CALENDAR, "US", "Asia/Kolkata")
    assert found.day == date(2026, 11, 1) and found.zone == "Asia/Kolkata"
    assert found.label == "Sun 1 Nov 2026, 23:59 IST"


def test_the_authority_zone_binds_when_its_day_ends_before_the_organizations():
    # An EU report for an organization in New York: Brussels' day ends six hours earlier (CET; New York is already on
    # daylight time from 8 Mar 2026, Brussels only from 29 Mar).
    aware = datetime(2026, 3, 10, 12, 0, tzinfo=UTC)
    found = deadlines.count(aware, 15, rules.CALENDAR, "EU_NI", "America/New_York")
    assert found.day == date(2026, 3, 25) and found.zone == "Europe/Brussels"
    assert found.at == datetime(2026, 3, 25, 22, 59, 59, tzinfo=UTC) and found.label == "Wed 25 Mar 2026, 23:59 CET"


def test_great_britain_counts_day_1_across_the_start_of_british_summer_time():
    # Awareness at 00:30 GMT on Sun 29 Mar 2026, half an hour before the clocks go forward: day 1 is 29 Mar, day 10 is
    # 7 Apr, ending at 23:59 BST (22:59 UTC).
    aware = datetime(2026, 3, 29, 0, 30, tzinfo=UTC)
    found = deadlines.count(aware, 10, rules.CALENDAR, "GB", "UTC")
    assert found.day == date(2026, 4, 7) and found.label == "Tue 7 Apr 2026, 23:59 BST"
    assert found.at == datetime(2026, 4, 7, 22, 59, 59, tzinfo=UTC)


def test_the_earlier_day_of_the_two_time_zones_is_the_latest_day():
    # 00:30 in Brussels on Tue 10 Mar is still Mon 9 Mar in New York: the organization's day comes first.
    aware = datetime(2026, 3, 9, 23, 30, tzinfo=UTC)
    found = deadlines.count(aware, 15, rules.CALENDAR, "EU_NI", "America/New_York")
    assert found.day == date(2026, 3, 24) and found.zone == "Europe/Brussels"


def test_work_days_and_a_market_without_an_authority_zone():
    friday = datetime(2026, 10, 9, 15, 0, tzinfo=UTC)
    assert deadlines.count(friday, 5, rules.WORK, "US", "UTC").day == date(2026, 10, 16)
    # Canada has no authority zone here: the organization's, from the day after awareness.
    canada = deadlines.count(friday, 10, rules.CALENDAR, None, "Asia/Kolkata")
    assert canada.day == date(2026, 10, 19) and canada.zone == "Asia/Kolkata"
    assert deadlines.zone_abbreviation(friday, "Asia/Dubai") == "UTC+04"


def test_days_left_and_overdue_are_read_in_the_time_zone_that_binds():
    found = deadlines.count(datetime(2026, 10, 24, 12, 0, tzinfo=UTC), 15, rules.CALENDAR, "IN", "UTC")
    before = datetime(2026, 11, 7, 18, 0, tzinfo=UTC)  # 23:30 IST
    after = datetime(2026, 11, 7, 18, 31, tzinfo=UTC)  # 00:01 IST on 8 Nov, still 7 Nov in UTC
    assert deadlines.view(found, before, 15)["state"] == "DUE_SOON" and deadlines.days_left(found, before) == 0
    assert deadlines.view(found, after, 15) | {"due_label": None} == {
        "due_date": "2026-11-07",
        "due_at": "2026-11-07T18:29:59+00:00",
        "due_zone": "Asia/Kolkata",
        "due_label": None,
        "days_left": -1,
        "state": "OVERDUE",
    }


def test_the_watch_clock_and_triage_count_the_same_way():
    window = {"name": "India", "markets": ["India"], "triggers": ["DEATH"], "days": 15, "day_basis": rules.CALENDAR}
    aware = datetime(2026, 10, 24, 12, 0, tzinfo=UTC)
    now = datetime(2026, 11, 1, 12, 0, tzinfo=UTC)
    (clock,) = rules.clocks({"country": "India", "death": True}, [rules.clean_window(window)], aware, now, "UTC")
    triage = intake_rules.provisional_deadlines(aware, ["IN"], intake_rules.FLAGGED, now, own="IN", org_zone="UTC")[0]
    assert clock.due_label == triage["due_label"] == "Sat 7 Nov 2026, 23:59 IST"
    assert clock.days_left == triage["days_left"] == 6
