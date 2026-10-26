"""R17: each governed import run's report counts rows read, accepted, quarantined and changed, and says whether
they agree with the file. Pure function: no database."""

import pytest

from backend.app.trial.imports import quality_report

pytestmark = pytest.mark.unit


def test_counts_agree_with_the_file():
    assert quality_report(10, 7, 3, 2) == {
        "rows_read": 10,
        "rows_accepted": 7,
        "rows_quarantined": 3,
        "rows_changed": 2,
        "rows_new": 5,
        "balanced": True,
    }


def test_a_lost_row_is_not_balanced():
    assert quality_report(10, 6, 3, 0)["balanced"] is False


def test_products_have_no_changed_count():
    report = quality_report(4, 4, 0, None)
    assert report["rows_changed"] is None and report["rows_new"] is None and report["balanced"]
