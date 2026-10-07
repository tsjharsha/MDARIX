"""Sorting a paged list on the server, so a column heading orders every page and not just the one on screen.

A list endpoint takes ``sort`` (a column key the screen shows) and ``order`` (``asc`` or ``desc``; a leading ``-`` on
``sort`` also means descending). Each endpoint names the keys it can sort by and what each key sorts on; any other key
is ignored and the list keeps its usual order. Empty values always come last, whichever the direction, and a
tiebreaker keeps the order stable, so a row never appears on two pages or on none.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Any

from sqlalchemy import func


def parse_sort(sort: str | None, order: str | None = None) -> tuple[str | None, bool]:
    """(key, descending) from the request; (None, False) when no sort was asked for."""
    key = (sort or "").strip()
    descending = (order or "").strip().lower() == "desc"
    if key.startswith("-"):
        key, descending = key[1:].strip(), True
    return (key or None), descending


def order_query(
    query,
    sort: str | None,
    order: str | None,
    columns: Mapping[str, Sequence[Any]],
    default: Sequence[Any],
    tiebreak: Sequence[Any] = (),
):
    """``query`` ordered by the requested column (``columns[key]``: one or more SQL expressions), else by
    ``default``; ``tiebreak`` (usually the primary key) is always last. Text sorts without regard to case."""
    key, descending = parse_sort(sort, order)
    expressions = columns.get(key) if key else None
    if not expressions:
        return query.order_by(*default, *tiebreak)
    ordering = []
    for expression in expressions:
        value = func.lower(expression) if _is_text(expression) else expression
        ordering.append((value.desc() if descending else value.asc()).nulls_last())
    return query.order_by(*ordering, *tiebreak)


def _is_text(expression: Any) -> bool:
    try:
        return expression.type.python_type is str
    except (AttributeError, NotImplementedError):
        return False


def sort_rows(
    rows: list,
    sort: str | None,
    order: str | None,
    keys: Mapping[str, Callable[[Any], Any]],
) -> list:
    """Rows already in memory (a list built in Python) in the requested order, else unchanged. Stable, empty values
    last, text without regard to case."""
    key, descending = parse_sort(sort, order)
    value_of = keys.get(key) if key else None
    if value_of is None:
        return rows
    present, empty = [], []
    for row in rows:
        value = value_of(row)
        (empty if value is None or value == "" else present).append((_comparable(value), row))
    present.sort(key=lambda pair: pair[0], reverse=descending)
    return [row for _, row in present] + [row for _, row in empty]


def _comparable(value: Any):
    if isinstance(value, str):
        return value.casefold()
    if isinstance(value, bool):
        return int(value)
    return value
