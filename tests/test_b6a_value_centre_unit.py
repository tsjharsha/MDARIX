"""B6a P2 (D9): median and 90th percentile on known data, the baseline window and the months, the CSV rows; no
per-person figure (B6-43, B6-44), with no database."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from backend.app.oversight import value_centre

pytestmark = pytest.mark.unit
GO_LIVE = datetime(2026, 10, 1, 9, tzinfo=timezone.utc)


def test_median_and_p90_on_known_data():  # B6-43
    assert value_centre.summary([]) == {"count": 0, "median": None, "p90": None}
    assert value_centre.summary([5.0]) == {"count": 1, "median": 5.0, "p90": 5.0}
    # 1..10: median 5.5; nearest-rank p90 is the 9th value.
    assert value_centre.summary([float(n) for n in range(10, 0, -1)]) == {"count": 10, "median": 5.5, "p90": 9.0}
    assert value_centre.summary([1.0, 2.0, 100.0]) == {"count": 3, "median": 2.0, "p90": 100.0}


def test_the_baseline_is_the_first_30_days_after_go_live_and_months_are_apart():
    points = [
        (GO_LIVE - timedelta(days=1), 99.0),  # before go-live: not in the baseline
        (GO_LIVE, 2.0),
        (GO_LIVE + timedelta(days=29, hours=23), 4.0),
        (GO_LIVE + timedelta(days=30), 50.0),  # day 31: after the baseline
    ]
    found = value_centre.periods(points, GO_LIVE)
    assert found["baseline"] == {"count": 2, "median": 3.0, "p90": 4.0}
    assert [item["month"] for item in found["months"]] == ["2026-10", "2026-09"]
    assert found["months"][0]["count"] == 3
    assert value_centre.periods(points, None)["baseline"] is None


def test_the_csv_names_the_baseline_and_the_qms_history_apart_and_no_person():  # B6-44
    metric = {
        "label": "Time to triage",
        "unit": "hours",
        "baseline": {"count": 2, "median": 3.0, "p90": 4.0},
        "imported": {"count": 5, "median": 30.0, "p90": 70.0},
        "months": [{"month": "2026-10", "count": 3, "median": 4.0, "p90": 50.0}],
    }
    rows = value_centre.csv_rows({"metrics": [metric]})
    assert [row["period"] for row in rows] == [
        "Your baseline (first 30 days after go-live)",
        "From your QMS export, before MDARIX",
        "2026-10",
    ]
    assert set(rows[0]) == set(value_centre.CSV_FIELDS)
    text = json.dumps(rows).lower()
    assert not any(word in text for word in ("actor", "user", "owner", 'by"', "person"))
