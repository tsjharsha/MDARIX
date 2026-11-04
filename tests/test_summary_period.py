"""The management review summary's period follows the organization's midnights (0.10.86 release gates).

Its "today" is the organization's day; the period ended at the UTC midnight after it, so in the US evening (after
00:00 UTC) anything signed that day fell out of the summary until the next day.
"""

import uuid
from datetime import date, datetime, timezone

from backend.app.oversight import rules, service
from backend.app.readiness_home import summary


def test_the_period_runs_between_the_organizations_midnights(monkeypatch):
    monkeypatch.setattr(service, "calendar_of", lambda db, tenant_id: rules.Calendar(zone="America/New_York"))
    begin, end = summary._bounds(None, uuid.uuid4(), date(2026, 11, 3), date(2026, 11, 3))
    # 3 Nov in New York (UTC-5 after the clocks went back on 1 Nov) runs from 05:00 UTC to 05:00 UTC the next day.
    assert begin == datetime(2026, 11, 3, 5, tzinfo=timezone.utc)
    assert end == datetime(2026, 11, 4, 5, tzinfo=timezone.utc)
    signed_in_the_evening = datetime(2026, 11, 4, 4, 40, tzinfo=timezone.utc)  # 23:40 on 3 Nov in New York
    assert begin <= signed_in_the_evening < end
