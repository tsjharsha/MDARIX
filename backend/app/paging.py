"""Offset paging for list endpoints that return a plain JSON array.

``?limit=`` (1-1000, default 1000) and ``?offset=`` select a page; the response keeps its array shape so existing
screens are unaffected, and says how many rows exist in ``X-Total-Count`` and where the next page starts in
``X-Next-Offset`` (empty on the last page). Screens show "first N of M" when there are more.
"""

from __future__ import annotations

from fastapi import Query, Response
from sqlalchemy import case, false, func, not_

MAX_PAGE = 1000


class Page:
    def __init__(
        self,
        limit: int = Query(MAX_PAGE, ge=1, le=MAX_PAGE, description="Rows per page (at most 1000)"),
        offset: int = Query(0, ge=0, description="Rows to skip"),
    ):
        self.limit = limit
        self.offset = offset

    def apply(self, query, response: Response) -> list:
        """The page of ``query`` (already ordered), with the paging headers set on ``response``."""
        total = query.order_by(None).count()
        response.headers["X-Total-Count"] = str(total)
        following = self.offset + self.limit
        response.headers["X-Next-Offset"] = str(following) if following < total else ""
        return query.limit(self.limit).offset(self.offset).all()


def open_first(query, key, is_open, newest, limit: int, cap: int | None = None) -> list:
    """In one statement: every row of ``query`` for which ``is_open`` holds, however many, then the newest ``limit``
    of the others (``newest``: the order clauses; ``key``: the rows' id column). For a list whose open, pending or
    overdue items must never fall behind its cap (0.10.86): the cap only ever drops finished history. ``cap``: an
    outer bound on all rows read (open ones first), for a list a paged one replaced."""
    flag = func.coalesce(is_open, false())
    newest_closed = query.filter(not_(flag)).order_by(*newest).limit(limit).with_entities(key)
    found = query.filter(flag | key.in_(newest_closed.scalar_subquery())).order_by(case((flag, 0), else_=1), *newest)
    return (found.limit(cap) if cap else found).all()
