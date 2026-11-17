"""The pg8000 placeholder rewrite is kept per statement text (performance: it costs ms per execution otherwise)."""

import pg8000.legacy
import pytest

from backend.app.db import session

pytestmark = pytest.mark.unit


def test_the_driver_uses_the_kept_rewrite_and_it_matches_the_scan():
    assert pg8000.legacy.convert_paramstyle is session.convert_paramstyle
    query = "SELECT a FROM t WHERE x = %s AND y LIKE 'p%%s' AND z = %s -- %s\n AND w = %s"
    assert session.convert_paramstyle("format", query, (1, 2, 3)) == session._scan_paramstyle(
        "format", query, (1, 2, 3)
    )
    before = session._format_statement.cache_info().hits
    assert session.convert_paramstyle("format", query, (4, 5, 6)) == (
        session._scan_paramstyle("format", query, ())[0],
        (4, 5, 6),
    )
    assert session._format_statement.cache_info().hits == before + 1


def test_other_styles_are_scanned_as_before():
    assert session.convert_paramstyle("named", "SELECT :a, :b, :a", {"a": 1, "b": 2}) == ("SELECT $1, $2, $1", (1, 2))
