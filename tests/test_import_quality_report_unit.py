"""R17: each governed import run's report counts rows read, accepted, quarantined and changed, and says whether
they agree with the file. Pure function: no database."""

import pytest

from backend.app.trial import imports
from backend.app.trial.imports import quality_report

pytestmark = pytest.mark.unit


def test_counts_agree_with_the_file():
    assert quality_report(10, 7, 3, 2) == {
        "rows_read": 10,
        "rows_accepted": 7,
        "rows_quarantined": 3,
        "rows_changed": 2,
        "rows_new": 5,
        "rows_unchanged": 0,
        "balanced": True,
    }


def test_rows_seen_again_without_a_change_are_unchanged_not_updated():
    report = quality_report(10, 10, 0, 1, new=2)
    assert (report["rows_new"], report["rows_changed"], report["rows_unchanged"]) == (2, 1, 7)


def test_a_lost_row_is_not_balanced():
    assert quality_report(10, 6, 3, 0)["balanced"] is False


def test_products_have_no_changed_count():
    report = quality_report(4, 4, 0, None)
    assert report["rows_changed"] is None and report["rows_new"] is None and report["rows_unchanged"] is None
    assert report["balanced"]


def test_a_row_with_extra_values_is_kept_with_its_problem_and_counted():
    raw = (
        "complaint_id,product_id,description\nC-1,P-1,Alarm sounded\nC-2,P-1,Pump stopped, patient hurt\n\n"
    ).encode()
    report = imports._Report()
    rows = imports._parse("complaints", raw, report, imports.WORKSPACE_POLICY, "ISO")
    assert [line for line, _ in rows] == [2, 3]
    assert report.row_problems[3] == ["This row has more values than the header has columns."]
    assert report.data_lines == 2  # the blank line is not a row
    # Read 2: one accepted, one quarantined: the run balances only because row 3 was kept.
    assert quality_report(report.data_lines, 1, 1, 0)["balanced"] is True
