"""A CSV import stops reading at the row limit (code audit 9 Nov 2026, fix 2): an oversized file is refused with the
workbook's "too many rows" message, without building every row in memory."""

import csv
from dataclasses import replace

import pytest

from backend.app.trial import imports, xlsx

pytestmark = pytest.mark.unit


def _csv(rows: int) -> bytes:
    lines = ["complaint_id,description"] + [f"C-{n},Reading drifted on unit {n}" for n in range(rows)]
    return "\n".join(lines).encode()


def test_an_over_limit_csv_is_refused_without_reading_every_row(monkeypatch):
    policy = replace(imports.TRIAL_POLICY, row_limit=10)
    cap = 1 + 10 + xlsx.ROW_MARGIN
    read = []
    real_reader = csv.reader

    class CountingReader:
        """Counts the rows read and keeps the real reader's line_num, which the import names in its errors."""

        def __init__(self, *args, **kwargs):
            self._reader = real_reader(*args, **kwargs)

        def __iter__(self):
            return self

        def __next__(self):
            row = next(self._reader)
            read.append(1)
            return row

        @property
        def line_num(self):
            return self._reader.line_num

    monkeypatch.setattr(imports.csv, "reader", CountingReader)
    report = imports._Report()

    assert imports._table(_csv(cap * 20), report, policy) is None
    assert len(read) <= cap + 1
    assert [issue["message"] for issue in report.issues] == [xlsx.too_many_rows(10)]


def test_a_csv_within_the_margin_is_still_read_whole():
    policy = replace(imports.TRIAL_POLICY, row_limit=10)
    report = imports._Report()

    table = imports._table(_csv(10 + xlsx.ROW_MARGIN), report, policy)

    assert table is not None and len(table) == 1 + 10 + xlsx.ROW_MARGIN
    assert report.issues == []
