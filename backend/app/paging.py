"""Offset paging for list endpoints that return a plain JSON array.

``?limit=`` (1-1000, default 1000) and ``?offset=`` select a page; the response keeps its array shape so existing
screens are unaffected, and says how many rows exist in ``X-Total-Count`` and where the next page starts in
``X-Next-Offset`` (empty on the last page). Screens show "first N of M" when there are more.
"""

from __future__ import annotations

from fastapi import Query, Response

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
