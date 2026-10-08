"""Server-side sorting helpers (backend/app/sorting.py): reading the request, ordering rows held in memory, and the
ORDER BY a list query gets. No database needed."""

from sqlalchemy import Column, DateTime, Integer, MetaData, String, Table, select
from sqlalchemy.dialects import postgresql

from backend.app.sorting import order_query, parse_sort, sort_rows

# parse_sort ----------------------------------------------------------------------------------------------------


def test_parse_sort_reads_key_and_direction():
    assert parse_sort("name", "asc") == ("name", False)
    assert parse_sort("name", "desc") == ("name", True)
    assert parse_sort("name", "DESC") == ("name", True)
    assert parse_sort(" name ", None) == ("name", False)


def test_parse_sort_leading_minus_means_descending():
    assert parse_sort("-created_at") == ("created_at", True)
    assert parse_sort("-created_at", "asc") == ("created_at", True)


def test_parse_sort_without_a_key_asks_for_nothing():
    assert parse_sort(None) == (None, False)
    assert parse_sort("") == (None, False)
    assert parse_sort("  ", "desc") == (None, True)
    assert parse_sort("-") == (None, True)


def test_parse_sort_unknown_order_is_ascending():
    assert parse_sort("name", "sideways") == ("name", False)


# sort_rows -----------------------------------------------------------------------------------------------------

ROWS = [
    {"id": 1, "name": "beta", "count": 3, "flag": True},
    {"id": 2, "name": "Alpha", "count": None, "flag": False},
    {"id": 3, "name": "", "count": 1, "flag": None},
    {"id": 4, "name": "alpha", "count": 3, "flag": True},
    {"id": 5, "name": None, "count": 2, "flag": False},
]
KEYS = {
    "name": lambda row: row["name"],
    "count": lambda row: row["count"],
    "flag": lambda row: row["flag"],
}


def ids(rows):
    return [row["id"] for row in rows]


def test_sort_rows_text_ignores_case_and_keeps_ties_stable():
    # "Alpha" and "alpha" tie; they keep the order they came in.
    assert ids(sort_rows(ROWS, "name", "asc", KEYS)) == [2, 4, 1, 3, 5]


def test_sort_rows_empty_values_last_in_both_directions():
    assert ids(sort_rows(ROWS, "name", "desc", KEYS))[-2:] == [3, 5]
    assert ids(sort_rows(ROWS, "count", "asc", KEYS)) == [3, 5, 1, 4, 2]
    assert ids(sort_rows(ROWS, "count", "desc", KEYS)) == [1, 4, 5, 3, 2]


def test_sort_rows_descending_keeps_ties_in_their_original_order():
    assert ids(sort_rows(ROWS, "-count", None, KEYS))[:2] == [1, 4]


def test_sort_rows_booleans_sort_false_before_true():
    assert ids(sort_rows(ROWS, "flag", "asc", KEYS)) == [2, 5, 1, 4, 3]


def test_sort_rows_unknown_or_missing_key_leaves_rows_unchanged():
    assert sort_rows(ROWS, "nope", "asc", KEYS) is ROWS
    assert sort_rows(ROWS, None, None, KEYS) is ROWS
    assert sort_rows(ROWS, "", "desc", KEYS) is ROWS


def test_sort_rows_does_not_change_the_input():
    before = [dict(row) for row in ROWS]
    sort_rows(ROWS, "name", "desc", KEYS)
    assert ROWS == before


# order_query ---------------------------------------------------------------------------------------------------

items = Table(
    "items",
    MetaData(),
    Column("id", Integer, primary_key=True),
    Column("name", String(50)),
    Column("size", Integer),
    Column("created_at", DateTime),
)
COLUMNS = {"name": [items.c.name], "size": [items.c.size], "made": [items.c.created_at, items.c.name]}


def sql(statement) -> str:
    return " ".join(str(statement.compile(dialect=postgresql.dialect())).split())


def order_by(statement) -> str:
    return sql(statement).split("ORDER BY", 1)[1].strip()


def test_order_query_sorts_text_without_regard_to_case_and_puts_nulls_last():
    statement = order_query(select(items), "name", "asc", COLUMNS, default=[items.c.id.desc()], tiebreak=[items.c.id])
    assert order_by(statement) == "lower(items.name) ASC NULLS LAST, items.id"


def test_order_query_descending_and_non_text_columns():
    statement = order_query(select(items), "size", "desc", COLUMNS, default=[items.c.id.desc()], tiebreak=[items.c.id])
    assert order_by(statement) == "items.size DESC NULLS LAST, items.id"
    statement = order_query(select(items), "-made", None, COLUMNS, default=[items.c.id.desc()], tiebreak=[items.c.id])
    assert order_by(statement) == "items.created_at DESC NULLS LAST, lower(items.name) DESC NULLS LAST, items.id"


def test_order_query_unknown_or_missing_key_uses_the_default_then_the_tiebreak():
    for sort in ("unknown", "", None):
        statement = order_query(
            select(items), sort, "desc", COLUMNS, default=[items.c.created_at.desc()], tiebreak=[items.c.id]
        )
        assert order_by(statement) == "items.created_at DESC, items.id"


def test_order_query_without_tiebreak():
    statement = order_query(select(items), "size", "asc", COLUMNS, default=[items.c.id])
    assert order_by(statement) == "items.size ASC NULLS LAST"
