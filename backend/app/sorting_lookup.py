"""Sorting a list by a value the list's own table does not hold: a person's name kept in the control database, a
label kept in Python. ``lookup_order`` turns the known values into an SQL expression the list can be ordered by
(``backend/app/sorting.py`` ``order_query``); rows with no known value sort as empty (last).
"""

from __future__ import annotations

import uuid
from collections.abc import Iterable, Mapping
from typing import Any

from sqlalchemy import String, case, cast, null


def lookup_order(column, values: Mapping[Any, Any]):
    """An SQL expression giving each row ``values[row.column]`` (NULL when it has none)."""
    if not values:
        return cast(null(), String)
    return case(dict(values), value=column, else_=None)


def person_names(control_db, tenant_id, refs: Iterable) -> dict[uuid.UUID, str]:
    """``{user id: name}`` for the organization's people among ``refs`` (ids or id text), for ``lookup_order`` on a
    UUID column. Empty when the names cannot be read."""
    from backend.app.workflow.people import names_by_id

    try:
        names = names_by_id(control_db, tenant_id, refs)
    except Exception:
        return {}
    found: dict[uuid.UUID, str] = {}
    for ref, name in names.items():
        try:
            found[uuid.UUID(str(ref))] = name
        except (TypeError, ValueError):
            continue
    return found
